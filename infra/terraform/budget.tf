# A budget alert. It warns; it never stops anything. The billing account's
# administrators are emailed by default, and so is every address in
# var.budget.emails.

resource "google_monitoring_notification_channel" "budget" {
  for_each = toset(var.budget.emails)

  display_name = "Open Antiquity budget: ${each.value}"
  type         = "email"
  labels = {
    email_address = each.value
  }

  depends_on = [google_project_service.enabled]
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account
  display_name    = "${var.name} monthly"

  budget_filter {
    projects        = ["projects/${data.google_project.this.number}"]
    calendar_period = "MONTH"
  }

  amount {
    specified_amount {
      currency_code = var.budget.currency
      units         = tostring(floor(var.budget.amount))
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [for channel in google_monitoring_notification_channel.budget : channel.id]
    disable_default_iam_recipients   = false
  }

  depends_on = [google_project_service.enabled]
}
