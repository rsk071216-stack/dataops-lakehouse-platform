# Production warehouse. Password authentication is disabled: humans and the
# pipeline sign in with Entra ID tokens, so no database password exists anywhere.
resource "azurerm_postgresql_flexible_server" "this" {
  name                          = local.names.postgres
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  version                       = "16"
  sku_name                      = var.postgres_sku_name
  storage_mb                    = var.postgres_storage_mb
  storage_tier                  = "P4"
  auto_grow_enabled             = true
  backup_retention_days         = var.environment == "prod" ? 14 : 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = !local.private
  delegated_subnet_id           = local.private ? azurerm_subnet.postgres[0].id : null
  private_dns_zone_id           = local.private ? azurerm_private_dns_zone.postgres[0].id : null

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  tags = local.tags

  lifecycle {
    # Azure picks an availability zone on create; do not fight it afterwards.
    ignore_changes = [zone]
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "deployer" {
  server_name         = azurerm_postgresql_flexible_server.this.name
  resource_group_name = azurerm_resource_group.this.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = var.postgres_entra_admin.object_id
  principal_name      = var.postgres_entra_admin.principal_name
  principal_type      = var.postgres_entra_admin.principal_type
}

resource "azurerm_postgresql_flexible_server_database" "lakehouse" {
  name      = local.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_min_duration" {
  name      = "log_min_duration_statement"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "5000" # log statements slower than 5s
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  count            = !local.private && var.postgres_allow_azure_services ? 1 : 0
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "clients" {
  for_each         = local.private ? {} : var.postgres_allowed_ip_ranges
  name             = each.key
  server_id        = azurerm_postgresql_flexible_server.this.id
  start_ip_address = each.value.start_ip
  end_ip_address   = each.value.end_ip
}

resource "azurerm_monitor_diagnostic_setting" "postgres" {
  name                       = "to-log-analytics"
  target_resource_id         = azurerm_postgresql_flexible_server.this.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category = "PostgreSQLLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
