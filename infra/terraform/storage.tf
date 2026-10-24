# ADLS Gen2 landing zone. Shared keys are disabled: every caller (pipeline,
# humans, Terraform) authenticates with Entra ID, so there is no key to leak.
resource "azurerm_storage_account" "lake" {
  name                              = local.names.storage
  location                          = azurerm_resource_group.this.location
  resource_group_name               = azurerm_resource_group.this.name
  account_kind                      = "StorageV2"
  account_tier                      = "Standard"
  account_replication_type          = var.environment == "prod" ? "ZRS" : "LRS"
  is_hns_enabled                    = true
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  shared_access_key_enabled         = false
  default_to_oauth_authentication   = true
  allow_nested_items_to_be_public   = false
  infrastructure_encryption_enabled = true
  public_network_access_enabled     = true

  network_rules {
    default_action             = local.private ? "Deny" : "Allow"
    bypass                     = ["AzureServices", "Logging", "Metrics"]
    virtual_network_subnet_ids = local.private ? [azurerm_subnet.aca[0].id] : []
  }

  blob_properties {
    delete_retention_policy {
      days = 14
    }
    container_delete_retention_policy {
      days = 14
    }
  }

  tags = local.tags
}

resource "azurerm_storage_container" "raw" {
  name                  = local.raw_container
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "archive" {
  name                  = "archive"
  storage_account_id    = azurerm_storage_account.lake.id
  container_access_type = "private"
}

# Least privilege: data access on the two containers only, not the whole account.
resource "azurerm_role_assignment" "pipeline_raw" {
  for_each = {
    raw     = azurerm_storage_container.raw.id
    archive = azurerm_storage_container.archive.id
  }
  scope                = each.value
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.pipeline.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_storage_management_policy" "lake" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "raw-tiering"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["${local.raw_container}/"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
        delete_after_days_since_modification_greater_than       = var.raw_retention_days
      }
    }
  }

  rule {
    name    = "archive-tiering"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["archive/"]
    }
    actions {
      base_blob {
        tier_to_cold_after_days_since_modification_greater_than = 30
      }
    }
  }
}
