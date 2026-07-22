variable "hcloud_token" {
  description = "Hetzner Cloud API token (Project > Security > API tokens)"
  type        = string
  sensitive   = true
}

variable "location" {
  description = "Hetzner location: nbg1/fsn1 (Germany), hel1 (Finland)"
  type        = string
  default     = "nbg1"
}

variable "network_zone" {
  description = "Network zone matching the location (eu-central for nbg1/fsn1/hel1)"
  type        = string
  default     = "eu-central"
}

variable "app_server_type" {
  description = "Server type for app nodes (cx22 = 2 vCPU / 4 GB)"
  type        = string
  default     = "cx22"
}

variable "db_server_type" {
  description = "Server type for the Postgres node"
  type        = string
  default     = "cx22"
}

variable "app_count" {
  description = "Number of app servers behind the load balancers"
  type        = number
  default     = 2
}

variable "container_image" {
  description = "App image reference in a registry the servers can pull (e.g. ghcr.io/<you>/sis:latest or docker.io/<you>/sis:latest)"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for admin access to the servers"
  type        = string
}

variable "db_volume_size" {
  description = "Postgres data volume size (GB)"
  type        = number
  default     = 20
}

variable "db_name" {
  type    = string
  default = "sis"
}

variable "db_username" {
  type    = string
  default = "sis"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "sis_secret_key" {
  description = "Flask SIS_SECRET_KEY shared by all app nodes"
  type        = string
  sensitive   = true
}
