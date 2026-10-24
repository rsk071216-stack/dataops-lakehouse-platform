resource "azurerm_container_app_environment" "this" {
  name                       = local.names.aca_env
  location                   = azurerm_resource_group.this.location
  resource_group_name        = azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id   = local.private ? azurerm_subnet.aca[0].id : null

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }

  tags = local.tags
}

# The whole pipeline (land -> load -> dbt WAP -> checks -> publish) runs as one
# scheduled job execution of the same image CI tested. Pay per second of runtime.
resource "azurerm_container_app_job" "pipeline" {
  name                         = local.names.job
  location                     = azurerm_resource_group.this.location
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 3600
  replica_retry_limit          = 1

  schedule_trigger_config {
    cron_expression          = var.schedule_cron
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.pipeline.id]
  }

  dynamic "registry" {
    for_each = var.create_acr ? [1] : []
    content {
      server   = azurerm_container_registry.this[0].login_server
      identity = azurerm_user_assigned_identity.pipeline.id
    }
  }

  template {
    container {
      name   = "pipeline"
      image  = var.image
      cpu    = 1
      memory = "2Gi"
      args   = ["run"]

      dynamic "env" {
        for_each = merge(var.pipeline_env, {
          LAKEHOUSE_TARGET           = "postgres"
          LAKEHOUSE_PG_AUTH          = "entra"
          LAKEHOUSE_LANDING_URL      = "az://${local.raw_container}"
          AZURE_STORAGE_ACCOUNT_NAME = azurerm_storage_account.lake.name
          AZURE_CLIENT_ID            = azurerm_user_assigned_identity.pipeline.client_id
          PGHOST                     = azurerm_postgresql_flexible_server.this.fqdn
          PGDATABASE                 = local.database_name
          PGUSER                     = azurerm_user_assigned_identity.pipeline.name
          PGSSLMODE                  = "require"
          PGPORT                     = "5432"
        })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  tags = local.tags

  lifecycle {
    # deploy.yml rolls new image digests with `az containerapp job update`.
    ignore_changes = [template[0].container[0].image]
  }

  depends_on = [
    azurerm_role_assignment.pipeline_raw,
    azurerm_role_assignment.pipeline_acr_pull,
  ]
}
