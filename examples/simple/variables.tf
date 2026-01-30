# examples/simple/variables.tf

variable "project" {
  description = "Project name"
  type        = string
  default     = "demo"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
