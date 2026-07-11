# Root Terraform module for AECP's cloud infrastructure: network, KMS,
# managed Postgres, and the Kubernetes cluster the services in
# deploy/k8s run on. Provider/backend left unpinned deliberately — set
# these once a target cloud (AWS/GCP/Azure) is chosen; do not default to
# one silently.

terraform {
  required_version = ">= 1.9"
  # backend "s3" | "gcs" | "azurerm" { ... } — configure per environment,
  # never local state for anything beyond a laptop experiment.
}

module "network" {
  source = "./modules/network"
}

module "kms" {
  source = "./modules/kms"
}

module "postgres" {
  source = "./modules/postgres"
}

module "cluster" {
  source = "./modules/cluster"
}
