terraform {
  # 1.8+ for provider-defined functions and `terraform test` mock providers.
  required_version = ">= 1.8.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
  }

  # Partial configuration: storage account, container and key are passed at
  # `terraform init -backend-config=...` time by .github/workflows/deploy.yml.
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  use_oidc        = true
  # The storage account disables shared keys, so any data-plane call must use Entra ID.
  storage_use_azuread = true

  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}
