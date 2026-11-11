# Offline checks of what this configuration would build, with the Google
# provider mocked: nothing here talks to Google Cloud, and no project is
# needed. Run from infra/terraform:
#
#   terraform init -backend=false && terraform test
#
# The values below are placeholders, not a real project or billing account.

mock_provider "google" {
  mock_data "google_project" {
    defaults = {
      number = "123456789012"
    }
  }
}

variables {
  project_id      = "fieldclub-example"
  billing_account = "000000-000000-000000"
  run_workloads   = true
  image_tag       = "abc1234"
  terms_url       = "https://example.org/terms"
}

run "foundations_only_on_the_first_apply" {
  command = plan

  variables {
    run_workloads = false
  }

  assert {
    condition     = length(google_cloud_run_v2_service.web) == 0 && length(google_cloud_run_v2_job.job) == 0
    error_message = "The first apply must not create workloads, whose secrets have no value yet."
  }

  assert {
    condition     = length(google_secret_manager_secret.managed) == 12
    error_message = "Every secret the settings need is created, empty."
  }

  assert {
    condition     = !contains(local.services, "compute.googleapis.com")
    error_message = "Compute Engine stays off without the CDN, because it brings an Editor service account."
  }
}

run "the_workloads_need_the_contributor_terms" {
  command = plan

  variables {
    terms_url = ""
  }

  expect_failures = [google_cloud_run_v2_service.web]
}

run "the_terms_reach_every_workload" {
  command = plan

  variables {
    terms_summary = "Short terms."
  }

  assert {
    condition     = local.common_env["FIELDCLUB_TERMS_URL"] == "https://example.org/terms" && local.service_env["FIELDCLUB_TERMS_SUMMARY"] == "Short terms."
    error_message = "Every workload gets the terms address, and the service the summary when one is given."
  }
}

run "every_mounted_bucket_is_writable_by_its_job" {
  command = plan

  # A job's bucket mount is read-write, so its service account needs objectUser on the
  # whole bucket, or the mount or the first write fails.
  assert {
    condition = alltrue([
      for name, job in local.jobs : job.mount.bucket == "" || anytrue([
        for access in values(local.bucket_access) :
        access.workload == name && access.bucket == job.mount.bucket && access.role == "roles/storage.objectUser" && try(access.only, "") == ""
      ])
    ])
    error_message = "Every job that mounts a bucket has objectUser on that bucket."
  }
}

run "the_service_runs_in_production_mode" {
  command = plan

  assert {
    condition     = local.service_env["FIELDCLUB_ENV"] == "prod" && local.service_env["FIELDCLUB_TRUSTED_PROXY_HOPS"] == "1"
    error_message = "The service runs as prod behind exactly one proxy."
  }

  assert {
    condition     = !contains(keys(local.service_env), "FIELDCLUB_DEV_LOGIN") && !contains(keys(local.service_env), "FIELDCLUB_MAIL_BACKEND")
    error_message = "No development login, and no mailer until a relay is configured."
  }

  assert {
    condition     = local.service_env["FIELDCLUB_STORAGE_BACKEND"] == "gcs" && local.service_env["FIELDCLUB_GCS_BUCKET"] == "fieldclub-example-cache"
    error_message = "Runtime data goes to the cache bucket, never the instance's memory disk."
  }

  assert {
    condition     = jsondecode(local.service_env["FIELDCLUB_GCS_NAMESPACE_BUCKETS"]).media == "fieldclub-example-photos"
    error_message = "Photos go to their own bucket."
  }

  assert {
    condition     = local.public_url == "https://fieldclub-123456789012.europe-west2.run.app"
    error_message = "Without a domain the site is its run.app address."
  }

  assert {
    condition     = google_cloud_run_v2_service.web[0].template[0].containers[0].image == "europe-west2-docker.pkg.dev/fieldclub-example/fieldclub/fieldclub:abc1234"
    error_message = "The service runs the tagged image from the project's registry."
  }

  assert {
    condition     = google_cloud_run_v2_service.web[0].template[0].scaling[0].min_instance_count == 0
    error_message = "The service scales to zero by default."
  }

  assert {
    condition = toset([for item in local.secret_env["service"] : item.env]) == toset([
      "FIELDCLUB_DATABASE_URL", "FIELDCLUB_SECRET_KEY", "DEFRA_SFTP_HOST", "DEFRA_SFTP_USER", "DEFRA_SFTP_PASSWORD",
    ])
    error_message = "With no provider configured the service gets only the core and SFTP secrets."
  }
}

run "providers_are_wired_only_when_configured" {
  command = plan

  variables {
    google_client_id = "example.apps.googleusercontent.com"
    mail             = { host = "smtp.example.org", username = "fieldclub", from = "Field Club <signin@example.org>" }
  }

  assert {
    condition     = contains([for item in local.secret_env["service"] : item.env], "FIELDCLUB_GOOGLE_CLIENT_SECRET")
    error_message = "A provider with a client id gets its secret."
  }

  assert {
    condition     = !contains([for item in local.secret_env["service"] : item.env], "FIELDCLUB_OSM_CLIENT_SECRET")
    error_message = "A provider without a client id gets nothing."
  }

  assert {
    condition     = local.service_env["FIELDCLUB_MAIL_BACKEND"] == "smtp" && contains([for item in local.secret_env["service"] : item.env], "FIELDCLUB_SMTP_PASSWORD")
    error_message = "A mail relay brings the smtp backend and its password."
  }
}

run "jobs_get_only_what_they_use" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_job.job) == 6
    error_message = "Schema, ingest, channel scan, source refresh, elevation copy and national overview."
  }

  assert {
    condition     = google_cloud_run_v2_job.job["elevation-copy"].template[0].task_count == 4 && google_cloud_run_v2_job.job["elevation-copy"].template[0].parallelism == 2
    error_message = "The copy is four shares, two at a time: two connections to Defra."
  }

  assert {
    condition     = !contains([for item in local.secret_env["elevation-copy"] : item.env], "FIELDCLUB_DATABASE_URL")
    error_message = "The elevation copy never touches the database."
  }

  assert {
    condition     = !contains([for item in local.secret_env["ingest"] : item.env], "DEFRA_SFTP_PASSWORD")
    error_message = "Only the copy and the service hold Defra's credentials."
  }

  assert {
    condition     = alltrue([for workload in local.all_workloads : contains([for item in local.secret_env[workload] : item.env], "FIELDCLUB_SECRET_KEY")])
    error_message = "Every production process needs the session key, or the settings refuse to load."
  }

  assert {
    condition     = length(google_cloud_scheduler_job.run) == 2
    error_message = "The channel scan and the source refresh are scheduled by default."
  }

  assert {
    condition     = tonumber(local.service_env["FIELDCLUB_EVENTS_MAX_STREAM_S"]) < 600
    error_message = "An event stream must end itself before Cloud Run's 600 s request timeout."
  }

  assert {
    condition     = tonumber(local.service_env["FIELDCLUB_EVENTS_MAX_STREAMS"]) < var.service_concurrency
    error_message = "Event streams must leave an instance slots for other requests."
  }

  assert {
    condition     = local.jobs["refresh-sources"].timeout == local.jobs["ingest"].timeout && local.jobs["refresh-sources"].mount.bucket == "cache"
    error_message = "The source refresh runs ingests, so it gets an ingest's time and its downloads."
  }

  assert {
    condition     = !contains(keys(google_project_iam_member.sql_client), "elevation-copy") && !contains(keys(google_project_iam_member.sql_client), "national-build")
    error_message = "Only workloads that use the database may connect to it."
  }
}

run "scheduled_ingest_needs_overrides" {
  command = plan

  variables {
    ingest_schedules = { "he-nhle-scheduled-monuments" = "0 3 1 * *" }
    schedules        = { scan_channels = "15 */6 * * *" }
  }

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler["ingest"].role == "roles/run.jobsExecutorWithOverrides"
    error_message = "Starting ingest with a source key needs the overrides role."
  }

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler["scan-channels"].role == "roles/run.invoker"
    error_message = "A job started as it stands needs only the invoker role."
  }
}

run "the_cdn_adds_a_proxy_and_closes_run_app" {
  command = plan

  variables {
    cdn = { enabled = true, domain = "fieldclub.example.org" }
  }

  assert {
    condition     = local.service_env["FIELDCLUB_TRUSTED_PROXY_HOPS"] == "2"
    error_message = "Behind the load balancer there are two proxies."
  }

  assert {
    condition     = google_cloud_run_v2_service.web[0].ingress == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    error_message = "The run.app address must not bypass the load balancer."
  }

  assert {
    condition     = local.public_url == "https://fieldclub.example.org"
    error_message = "The site's address is the domain."
  }

  assert {
    condition     = length(module.cdn) == 1
    error_message = "The CDN module is built."
  }
}

run "the_service_is_open_unless_held_back" {
  command = plan

  assert {
    condition     = google_cloud_run_v2_service.web[0].invoker_iam_disabled == true
    error_message = "By default anyone can reach the site."
  }
}

run "a_held_back_service_checks_every_caller" {
  command = plan

  variables {
    service_public = false
  }

  assert {
    condition     = google_cloud_run_v2_service.web[0].invoker_iam_disabled == false
    error_message = "With service_public false, Cloud Run lets in only callers the project's IAM allows."
  }
}

run "a_held_back_service_cannot_sit_behind_the_cdn" {
  command = plan

  variables {
    service_public = false
    cdn            = { enabled = true, domain = "fieldclub.example.org" }
  }

  expect_failures = [google_cloud_run_v2_service.web]
}

run "a_recurring_job_can_be_left_unscheduled" {
  command = plan

  variables {
    schedules = { refresh_sources = "" }
  }

  assert {
    condition     = keys(google_cloud_scheduler_job.run) == ["scan-channels"]
    error_message = "An empty schedule leaves that job unscheduled, and the other keeps its default."
  }
}

run "the_elevation_mirror_can_only_grow" {
  command = plan

  assert {
    condition = alltrue([
      for key, grant in local.bucket_access : contains(["roles/storage.objectViewer", "roles/storage.objectCreator"], grant.role)
      if grant.bucket == "elevation" && try(grant.only, "") == ""
    ])
    error_message = "No workload may delete or replace a mirror file."
  }

  assert {
    condition     = google_storage_bucket_iam_member.workload["national-build/elev-national"].condition[0].expression == "resource.name.startsWith(\"projects/_/buckets/fieldclub-example-elevation/objects/england/national/\")"
    error_message = "The national build may change only the national overview's folder."
  }

  assert {
    condition     = google_storage_bucket_iam_member.workload["service/elev-add"].role == "roles/storage.objectCreator"
    error_message = "While it fetches missing tiles, the service may add to the mirror."
  }
}

run "a_finished_copy_leaves_the_service_reading_only" {
  command = plan

  variables {
    service_fetches_elevation = false
  }

  assert {
    condition     = !contains(keys(local.bucket_access), "service/elev-add") && contains(keys(local.bucket_access), "service/elev-read")
    error_message = "Once the copy is done the service only reads the mirror."
  }

  assert {
    condition     = !contains([for item in local.secret_env["service"] : item.env], "DEFRA_SFTP_PASSWORD")
    error_message = "Once the copy is done the service no longer holds Defra's credentials."
  }
}

run "the_database_survives_a_mistaken_delete" {
  command = plan

  assert {
    condition     = google_sql_database_instance.main.settings[0].deletion_protection_enabled && google_sql_database_instance.main.deletion_protection
    error_message = "Both Google and Terraform refuse to delete the instance."
  }

  assert {
    condition     = google_sql_database_instance.main.settings[0].retain_backups_on_delete && google_sql_database_instance.main.settings[0].final_backup_config[0].enabled
    error_message = "Deleting the instance keeps its backups and takes one more."
  }
}

run "only_the_deploy_workflow_may_federate" {
  command = plan

  variables {
    github_repository    = "example-owner/fieldclub"
    github_repository_id = "123456789"
  }

  assert {
    condition = alltrue([for clause in [
      "assertion.repository_id == '123456789'",
      "assertion.job_workflow_ref == 'example-owner/fieldclub/.github/workflows/deploy.yml@refs/heads/main'",
      "assertion.event_name == 'workflow_dispatch'",
    ] : strcontains(google_iam_workload_identity_pool_provider.github[0].attribute_condition, clause)])
    error_message = "The token must come from deploy.yml, run by hand, in the repository with this id."
  }

  assert {
    condition     = google_storage_bucket_iam_member.deployer_state[0].role == "roles/storage.objectViewer"
    error_message = "The deployer reads the state and can't rewrite it."
  }
}

run "federation_needs_the_repository_id" {
  command = plan

  variables {
    github_repository = "example-owner/fieldclub"
  }

  expect_failures = [google_iam_workload_identity_pool_provider.github]
}
