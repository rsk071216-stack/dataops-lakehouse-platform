# Unit tests for the platform module. They run `plan` against a mocked azurerm
# provider, so they need no Azure account and run on every pull request.

mock_provider "azurerm" {
  source = "./tests/mocks"
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  environment     = "dev"
  image           = "ghcr.io/rsk071216-stack/dataops-lakehouse-platform@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  alert_email     = "data-platform@example.com"
  postgres_entra_admin = {
    object_id      = "77777777-7777-7777-7777-777777777777"
    principal_name = "github-oidc-lakehouse"
    principal_type = "ServicePrincipal"
  }
}

run "landing_zone_is_private_adls_gen2_without_shared_keys" {
  command = plan

  assert {
    condition     = azurerm_storage_account.lake.is_hns_enabled
    error_message = "The landing zone must be ADLS Gen2 (hierarchical namespace)."
  }
  assert {
    condition     = !azurerm_storage_account.lake.shared_access_key_enabled
    error_message = "Shared keys must be disabled; access is Entra ID only."
  }
  assert {
    condition     = !azurerm_storage_account.lake.allow_nested_items_to_be_public
    error_message = "Blob public access must be disabled."
  }
  assert {
    condition = alltrue([
      azurerm_storage_container.raw.container_access_type == "private",
      azurerm_storage_container.archive.container_access_type == "private",
    ])
    error_message = "raw and archive containers must be private."
  }
  assert {
    condition     = azurerm_storage_account.lake.min_tls_version == "TLS1_2"
    error_message = "TLS 1.2 minimum is required."
  }
}

run "postgres_uses_entra_id_only_on_a_burstable_sku" {
  command = plan

  assert {
    condition     = azurerm_postgresql_flexible_server.this.authentication[0].active_directory_auth_enabled
    error_message = "Entra ID authentication must be enabled."
  }
  assert {
    condition     = !azurerm_postgresql_flexible_server.this.authentication[0].password_auth_enabled
    error_message = "Password authentication must be disabled (no database passwords)."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.this.sku_name == "B_Standard_B1ms"
    error_message = "Default SKU must stay on the cost-efficient Burstable B1ms."
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.this.public_network_access_enabled
    error_message = "Public mode keeps the public endpoint (firewalled)."
  }
  assert {
    condition     = length(azurerm_postgresql_flexible_server_firewall_rule.azure_services) == 1
    error_message = "Public mode allows Azure services by default."
  }
  assert {
    condition     = length(azurerm_virtual_network.this) == 0
    error_message = "Public mode must not create a VNet."
  }
}

run "identity_and_rbac_are_least_privilege" {
  command = plan

  assert {
    condition     = azurerm_key_vault.this.rbac_authorization_enabled && azurerm_key_vault.this.purge_protection_enabled
    error_message = "Key Vault must use RBAC and purge protection."
  }
  assert {
    condition     = toset(keys(azurerm_role_assignment.pipeline_raw)) == toset(["raw", "archive"])
    error_message = "Pipeline gets blob data access on the two containers only."
  }
  assert {
    condition = alltrue([
      for ra in azurerm_role_assignment.pipeline_raw : ra.role_definition_name == "Storage Blob Data Contributor"
    ])
    error_message = "Use the data-plane role, never Owner/Contributor."
  }
  assert {
    condition     = length(azurerm_container_registry.this) == 0
    error_message = "ACR is opt-in; GHCR is the default registry."
  }
}

run "scheduled_job_runs_the_digest_pinned_image_with_managed_identity" {
  command = plan

  assert {
    condition     = azurerm_container_app_job.pipeline.schedule_trigger_config[0].cron_expression == "0 5 * * *"
    error_message = "Job must run on the daily schedule."
  }
  assert {
    condition     = azurerm_container_app_job.pipeline.identity[0].type == "UserAssigned"
    error_message = "Job must run as the user-assigned managed identity."
  }
  assert {
    condition     = strcontains(azurerm_container_app_job.pipeline.template[0].container[0].image, "@sha256:")
    error_message = "Image must be pinned by digest."
  }
  assert {
    condition = anytrue([
      for e in azurerm_container_app_job.pipeline.template[0].container[0].env : e.name == "LAKEHOUSE_PG_AUTH" && e.value == "entra"
    ])
    error_message = "The pipeline must authenticate to Postgres with Entra ID."
  }
  assert {
    condition     = output.landing_url == "az://raw"
    error_message = "Landing URL must point at the raw container."
  }
}

run "alerts_and_budget_are_wired" {
  command = plan

  assert {
    condition     = strcontains(azurerm_monitor_scheduled_query_rules_alert_v2.check_failed.criteria[0].query, "lakehouse.check")
    error_message = "The data check alert must query the structured check events."
  }
  assert {
    condition     = azurerm_monitor_scheduled_query_rules_alert_v2.no_successful_run.criteria[0].operator == "LessThan"
    error_message = "The dead man's switch fires when there are fewer than 1 successful runs."
  }
  assert {
    condition     = length(azurerm_consumption_budget_resource_group.this) == 1
    error_message = "A budget is created when an alert email is configured."
  }
}

run "private_mode_moves_postgres_and_storage_off_the_public_internet" {
  command = plan

  variables {
    environment  = "prod"
    network_mode = "private"
  }

  assert {
    condition     = !azurerm_postgresql_flexible_server.this.public_network_access_enabled
    error_message = "Private mode disables the Postgres public endpoint."
  }
  assert {
    condition     = length(azurerm_subnet.postgres) == 1 && length(azurerm_private_dns_zone.postgres) == 1
    error_message = "Private mode needs a delegated subnet and a private DNS zone."
  }
  assert {
    condition     = azurerm_storage_account.lake.network_rules[0].default_action == "Deny"
    error_message = "Private mode denies public storage traffic by default."
  }
  assert {
    condition     = length(azurerm_postgresql_flexible_server_firewall_rule.azure_services) == 0
    error_message = "Private mode must not open firewall rules."
  }
  assert {
    condition     = azurerm_storage_account.lake.account_replication_type == "ZRS"
    error_message = "Prod storage is zone redundant."
  }
}

run "acr_opt_in_grants_acr_pull" {
  command = plan

  variables {
    create_acr = true
  }

  assert {
    condition     = length(azurerm_role_assignment.pipeline_acr_pull) == 1
    error_message = "ACR mode must grant AcrPull to the pipeline identity."
  }
}

run "mutable_image_tags_are_rejected" {
  command = plan

  variables {
    image = "ghcr.io/rsk071216-stack/dataops-lakehouse-platform:latest"
  }

  expect_failures = [var.image]
}

run "unknown_network_mode_is_rejected" {
  command = plan

  variables {
    network_mode = "hybrid"
  }

  expect_failures = [var.network_mode]
}
