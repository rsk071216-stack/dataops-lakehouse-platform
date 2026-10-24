variable "subscription_id" {
  description = "Azure subscription that hosts the platform."
  type        = string
}

variable "environment" {
  description = "Deployment stage. Drives naming, sizing and network defaults."
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "westeurope"
}

variable "name_suffix" {
  description = "Short suffix that makes globally unique names (storage, Key Vault, Postgres) unique."
  type        = string
  default     = "001"
  validation {
    condition     = can(regex("^[a-z0-9]{2,5}$", var.name_suffix))
    error_message = "name_suffix must be 2-5 lowercase letters or digits."
  }
}

variable "network_mode" {
  description = <<-EOT
    public  - Postgres and storage are reachable over public endpoints, restricted by
              firewall rules. Cheapest; fine for dev and demos.
    private - Postgres gets VNet integration (delegated subnet + private DNS), storage
              denies public traffic except the Container Apps subnet. Use for prod.
  EOT
  type        = string
  default     = "public"
  validation {
    condition     = contains(["public", "private"], var.network_mode)
    error_message = "network_mode must be public or private."
  }
}

variable "vnet_address_space" {
  description = "Address space for the platform VNet (private mode only)."
  type        = string
  default     = "10.40.0.0/16"
}

variable "postgres_allowed_ip_ranges" {
  description = "Public mode only: extra client IP ranges allowed through the Postgres firewall."
  type = map(object({
    start_ip = string
    end_ip   = string
  }))
  default = {}
}

variable "postgres_allow_azure_services" {
  description = "Public mode only: allow Azure-internal traffic (Container Apps consumption egress is not static)."
  type        = bool
  default     = true
}

variable "postgres_sku_name" {
  description = "Flexible Server SKU. Burstable B1ms is plenty for this workload."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Flexible Server storage size in MB."
  type        = number
  default     = 32768
}

variable "postgres_entra_admin" {
  description = <<-EOT
    Entra ID principal that administers the server, normally the GitHub Actions
    deployment identity (OIDC). It creates the non-admin pipeline role at deploy time.
  EOT
  type = object({
    object_id      = string
    principal_name = string
    principal_type = string
  })
  validation {
    condition     = contains(["ServicePrincipal", "Group", "User"], var.postgres_entra_admin.principal_type)
    error_message = "principal_type must be ServicePrincipal, Group or User."
  }
}

variable "image" {
  description = "Pipeline container image, pinned by digest (ghcr.io/<owner>/<repo>@sha256:...)."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$", var.image))
    error_message = "image must be pinned by digest (registry/repo@sha256:<64 hex>); tags are mutable."
  }
}

variable "create_acr" {
  description = "Create a private Azure Container Registry (else the public GHCR image is pulled)."
  type        = bool
  default     = false
}

variable "schedule_cron" {
  description = "UTC cron expression for the scheduled pipeline job."
  type        = string
  default     = "0 5 * * *"
}

variable "pipeline_env" {
  description = "Extra non-secret environment variables for the pipeline container."
  type        = map(string)
  default = {
    LAKEHOUSE_SOURCE = "live"
    LAKEHOUSE_MONTH  = "2024-01"
  }
}

variable "log_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

variable "raw_retention_days" {
  description = "Days before raw landing files are deleted (archive keeps its own copy longer)."
  type        = number
  default     = 365
}

variable "alert_email" {
  description = "Where data quality and pipeline alerts are sent. Empty disables the action group email."
  type        = string
  default     = ""
}

variable "monthly_budget_amount" {
  description = "Monthly cost budget for the resource group, in the billing currency. 0 disables it."
  type        = number
  default     = 50
}

variable "budget_start_date" {
  description = "First day of the first budget month (RFC3339). Must be the first of a month."
  type        = string
  default     = "2026-11-01T00:00:00Z"
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}
