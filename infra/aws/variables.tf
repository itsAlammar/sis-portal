variable "region" {
  description = "AWS region"
  type        = string
  default     = "me-central-1" # UAE; use me-south-1 (Bahrain) or another as you prefer
}

variable "project" {
  description = "Name prefix for all resources"
  type        = string
  default     = "sis"
}

variable "container_image" {
  description = "Full ECR image reference (repo:tag) to run. Push the image first, then set this."
  type        = string
}

variable "desired_count" {
  description = "Number of app tasks (ECS Fargate)"
  type        = number
  default     = 2
}

variable "cpu" {
  description = "Fargate task CPU units"
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory (MiB)"
  type        = number
  default     = 1024
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
  description = "RDS master password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro" # scale up (db.t4g.medium / large) as enrollment grows
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "sis_secret_key" {
  description = "Flask SIS_SECRET_KEY shared by all workers"
  type        = string
  sensitive   = true
}
