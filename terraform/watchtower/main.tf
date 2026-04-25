# terraform/watchtower/main.tf
terraform {
  cloud {
    organization = "littlewolfacres"
    workspaces {
      name = "watchtower"
    }
  }
}