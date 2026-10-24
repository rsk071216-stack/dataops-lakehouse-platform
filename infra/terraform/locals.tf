locals {
  project = "lakehouse"
  private = var.network_mode == "private"

  names = {
    resource_group = "rg-${local.project}-${var.environment}"
    identity       = "id-${local.project}-pipeline-${var.environment}"
    log_analytics  = "log-${local.project}-${var.environment}"
    storage        = "st${local.project}${var.environment}${var.name_suffix}"
    key_vault      = "kv-${local.project}-${var.environment}-${var.name_suffix}"
    postgres       = "psql-${local.project}-${var.environment}-${var.name_suffix}"
    acr            = "cr${local.project}${var.environment}${var.name_suffix}"
    aca_env        = "cae-${local.project}-${var.environment}"
    job            = "caj-${local.project}-pipeline-${var.environment}"
    vnet           = "vnet-${local.project}-${var.environment}"
    action_group   = "ag-${local.project}-${var.environment}"
  }

  database_name = "lakehouse"
  raw_container = "raw"

  tags = merge(
    {
      project     = "dataops-lakehouse-platform"
      environment = var.environment
      managed_by  = "terraform"
      repository  = "github.com/rsk071216-stack/dataops-lakehouse-platform"
    },
    var.tags,
  )
}
