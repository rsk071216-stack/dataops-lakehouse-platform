# Non-secret settings for prod. See dev.tfvars for how the rest is injected.
environment           = "prod"
location              = "westeurope"
name_suffix           = "001"
network_mode          = "private"
schedule_cron         = "0 5 * * *"
log_retention_days    = 90
raw_retention_days    = 730
monthly_budget_amount = 120
