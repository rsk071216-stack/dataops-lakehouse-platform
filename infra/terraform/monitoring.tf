# Alerting design: the pipeline prints one JSON line per check
# ({"event": "lakehouse.check", "passed": false, ...}) and one per run
# ({"event": "lakehouse.run", "success": true, ...}). Container Apps ships stdout
# to Log Analytics; two KQL alert rules turn those lines into pages.

resource "azurerm_monitor_action_group" "data_platform" {
  name                = local.names.action_group
  resource_group_name = azurerm_resource_group.this.name
  short_name          = "lakehouse"

  dynamic "email_receiver" {
    for_each = var.alert_email == "" ? [] : [var.alert_email]
    content {
      name                    = "data-platform"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }

  tags = local.tags
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "check_failed" {
  name                 = "lakehouse-${var.environment}-data-check-failed"
  location             = azurerm_resource_group.this.location
  resource_group_name  = azurerm_resource_group.this.name
  description          = "A freshness, volume or dbt check failed in the scheduled pipeline."
  severity             = 2
  scopes               = [azurerm_log_analytics_workspace.this.id]
  evaluation_frequency = "PT15M"
  window_duration      = "PT1H"

  criteria {
    query                   = <<-KQL
      ContainerAppConsoleLogs_CL
      | where ContainerJobName_s == "${local.names.job}"
      | where Log_s has "lakehouse.check"
      | extend e = parse_json(Log_s)
      | where tobool(e.passed) == false
      | project TimeGenerated, check = tostring(e.check), message = tostring(e.message)
    KQL
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0

    dimension {
      name     = "check"
      operator = "Include"
      values   = ["*"]
    }

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.data_platform.id]
  }

  tags = local.tags
}

# Dead man's switch: no successful run in the last day means the data is stale,
# whatever the reason (job never started, crashed, image pull failure ...).
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "no_successful_run" {
  name                 = "lakehouse-${var.environment}-no-successful-run"
  location             = azurerm_resource_group.this.location
  resource_group_name  = azurerm_resource_group.this.name
  description          = "The pipeline has not completed successfully in the last 24 hours."
  severity             = 1
  scopes               = [azurerm_log_analytics_workspace.this.id]
  evaluation_frequency = "PT1H"
  window_duration      = "P1D"

  criteria {
    query                   = <<-KQL
      ContainerAppConsoleLogs_CL
      | where ContainerJobName_s == "${local.names.job}"
      | where Log_s has "lakehouse.run"
      | extend e = parse_json(Log_s)
      | where tobool(e.success) == true
    KQL
    time_aggregation_method = "Count"
    operator                = "LessThan"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.data_platform.id]
  }

  tags = local.tags
}

resource "azurerm_consumption_budget_resource_group" "this" {
  count             = var.monthly_budget_amount > 0 && var.alert_email != "" ? 1 : 0
  name              = "budget-${local.project}-${var.environment}"
  resource_group_id = azurerm_resource_group.this.id
  amount            = var.monthly_budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
