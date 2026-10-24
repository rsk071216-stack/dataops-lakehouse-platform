# Key Vault (RBAC mode). The core pipeline needs no secrets at all (Entra ID for
# Postgres and storage); the vault holds credentials for future third-party
# sources, which the Container Apps Job references by identity, never by value.
resource "azurerm_key_vault" "this" {
  name                          = local.names.key_vault
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 30
  public_network_access_enabled = true

  network_acls {
    default_action             = local.private ? "Deny" : "Allow"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = local.private ? [azurerm_subnet.aca[0].id] : []
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "pipeline_kv_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.pipeline.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "to-log-analytics"
  target_resource_id         = azurerm_key_vault.this.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id

  enabled_log {
    category_group = "audit"
  }
}
