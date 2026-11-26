terraform {
  required_version = "~> 1.9.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.50"
    }
  }
  # Separate bootstrap state, never the legacy backend. Keep its local state secure
  # until moved to a separately agreed administrative backend after bucket creation.
  backend "local" {}
}

provider "google" {
  user_project_override = true
}

variable "projects" {
  type = map(string)
  default = {
    staging = "onolys-staging"
    eval    = "onolys-eval"
  }
  validation {
    condition     = alltrue([for env, project in var.projects : contains(["staging", "eval"], env) && project == "onolys-${env}"])
    error_message = "Bootstrap may create state buckets only in onolys-staging and onolys-eval."
  }
}

resource "google_project_service" "storage" {
  for_each           = var.projects
  project            = each.value
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "state" {
  for_each                    = var.projects
  project                     = each.value
  name                        = "${each.value}-tfstate"
  location                    = "US"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning {
    enabled = true
  }
  # Saved plans (plans/, written by terraform.yml on main) are throwaway: drop them after 7 days, including the noncurrent
  # versions bucket versioning keeps. State objects are not under plans/ and are never touched.
  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["plans/"]
    }
    action {
      type = "Delete"
    }
  }
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 7
      matches_prefix             = ["plans/"]
    }
    action {
      type = "Delete"
    }
  }
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [google_project_service.storage]
}

output "state_buckets" {
  value = { for env, bucket in google_storage_bucket.state : env => bucket.name }
}
