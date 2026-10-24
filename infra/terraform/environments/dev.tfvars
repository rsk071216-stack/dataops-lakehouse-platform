# Non-secret settings for dev. subscription_id, image and postgres_entra_admin
# are injected by .github/workflows/deploy.yml as TF_VAR_* from GitHub
# environment variables, so nothing tenant-specific is committed.
environment           = "dev"
location              = "westeurope"
name_suffix           = "001"
network_mode          = "public"
schedule_cron         = "0 5 * * *"
log_retention_days    = 30
monthly_budget_amount = 40
