output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "storage_account_name" {
  value = azurerm_storage_account.lake.name
}

output "landing_url" {
  description = "LAKEHOUSE_LANDING_URL for the pipeline."
  value       = "az://${azurerm_storage_container.raw.name}"
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.this.fqdn
}

output "postgres_database" {
  value = azurerm_postgresql_flexible_server_database.lakehouse.name
}

output "pipeline_identity" {
  description = "Managed identity used by the job; deploy.yml maps it to a Postgres role."
  value = {
    name         = azurerm_user_assigned_identity.pipeline.name
    client_id    = azurerm_user_assigned_identity.pipeline.client_id
    principal_id = azurerm_user_assigned_identity.pipeline.principal_id
  }
}

output "container_app_job_name" {
  value = azurerm_container_app_job.pipeline.name
}

output "key_vault_uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.workspace_id
}

output "network_mode" {
  value = var.network_mode
}
