# examples/simple/main.tf
# Simple AWS infrastructure for demonstration

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = "${var.region}${count.index == 0 ? "a" : "b"}"

  tags = {
    Name = "${var.project}-public-${count.index + 1}"
  }
}

# Security Group
resource "aws_security_group" "web" {
  name        = "${var.project}-web-sg"
  description = "Security group for web servers"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.web.id]
  subnets            = aws_subnet.public[*].id
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"
}

# DynamoDB Table
resource "aws_dynamodb_table" "main" {
  name         = "${var.project}-data"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

# S3 Bucket
resource "aws_s3_bucket" "assets" {
  bucket = "${var.project}-assets-${var.region}"
}

# SQS Queue
resource "aws_sqs_queue" "tasks" {
  name = "${var.project}-tasks"
}
