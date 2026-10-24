data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = local.names.resource_group
  location = var.location
  tags     = local.tags
}

# One identity for the pipeline: storage, Key Vault, Postgres (Entra) and ACR pull.
resource "azurerm_user_assigned_identity" "pipeline" {
  name                = local.names.identity
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = local.names.log_analytics
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  # Cost guard rail: cap ingestion so a log storm cannot run up the bill.
  daily_quota_gb = var.environment == "prod" ? 2 : 0.5
  tags           = local.tags
}

resource "azurerm_container_registry" "this" {
  count                         = var.create_acr ? 1 : 0
  name                          = local.names.acr
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  sku                           = "Basic"
  admin_enabled                 = false
  public_network_access_enabled = true
  tags                          = local.tags
}

resource "azurerm_role_assignment" "pipeline_acr_pull" {
  count                = var.create_acr ? 1 : 0
  scope                = azurerm_container_registry.this[0].id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.pipeline.principal_id
  principal_type       = "ServicePrincipal"
}
