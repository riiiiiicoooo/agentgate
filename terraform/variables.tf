# AgentGate Terraform Variables

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "ecr_repository_url" {
  description = "ECR repository URL for AgentGate image"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag"
  type        = string
  default     = "latest"
}

variable "ssl_certificate_arn" {
  description = "ARN of SSL certificate for ALB"
  type        = string
}

# Database variables
variable "db_name" {
  description = "Database name"
  type        = string
  default     = "agentgate"
}

variable "db_master_username" {
  description = "Database master username"
  type        = string
  default     = "postgres"
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.small"
}

variable "db_instance_count" {
  description = "Number of RDS instances in cluster"
  type        = number
  default     = 2
  validation {
    condition     = var.db_instance_count >= 1 && var.db_instance_count <= 5
    error_message = "Database instance count must be between 1 and 5."
  }
}

# Redis variables
variable "redis_node_type" {
  description = "Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_nodes" {
  description = "Number of Redis nodes"
  type        = number
  default     = 2
  validation {
    condition     = var.redis_num_nodes >= 1 && var.redis_num_nodes <= 6
    error_message = "Redis node count must be between 1 and 6."
  }
}

# ECS variables
variable "task_cpu" {
  description = "CPU units for ECS task"
  type        = number
  default     = 512
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.task_cpu)
    error_message = "Valid CPU values are 256, 512, 1024, 2048, 4096."
  }
}

variable "task_memory" {
  description = "Memory in MB for ECS task"
  type        = number
  default     = 1024
  validation {
    condition     = contains([512, 1024, 2048, 4096, 8192], var.task_memory)
    error_message = "Valid memory values are 512, 1024, 2048, 4096, 8192."
  }
}

variable "service_desired_count" {
  description = "Desired number of running tasks"
  type        = number
  default     = 2
  validation {
    condition     = var.service_desired_count >= 1 && var.service_desired_count <= 10
    error_message = "Service desired count must be between 1 and 10."
  }
}

variable "service_min_capacity" {
  description = "Minimum service capacity for auto-scaling"
  type        = number
  default     = 1
}

variable "service_max_capacity" {
  description = "Maximum service capacity for auto-scaling"
  type        = number
  default     = 4
}

# Monitoring and logging
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention must be a valid CloudWatch value."
  }
}

variable "enable_enhanced_monitoring" {
  description = "Enable enhanced monitoring for RDS"
  type        = bool
  default     = true
}

variable "enable_audit_logging" {
  description = "Enable audit logging to S3"
  type        = bool
  default     = true
}

variable "audit_log_bucket" {
  description = "S3 bucket for audit logs"
  type        = string
  default     = ""
}

# Tags
variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project    = "AgentGate"
    ManagedBy  = "Terraform"
    CostCenter = "Engineering"
  }
}

# Feature flags
variable "enable_waf" {
  description = "Enable AWS WAF for ALB"
  type        = bool
  default     = true
}

variable "enable_backup" {
  description = "Enable backup and snapshots"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 30
  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 365
    error_message = "Backup retention must be between 1 and 365 days."
  }
}

# Performance and scaling
variable "db_enable_multi_az" {
  description = "Enable Multi-AZ for RDS"
  type        = bool
  default     = true
}

variable "db_performance_insights_enabled" {
  description = "Enable Performance Insights for RDS"
  type        = bool
  default     = false
}

variable "redis_automatic_failover" {
  description = "Enable automatic failover for Redis"
  type        = bool
  default     = true
}

# Security
variable "enable_encryption_at_rest" {
  description = "Enable encryption at rest for all data stores"
  type        = bool
  default     = true
}

variable "enable_encryption_in_transit" {
  description = "Enable encryption in transit"
  type        = bool
  default     = true
}

variable "cidr_allowed_ips" {
  description = "CIDR blocks allowed to access the service"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# Notifications
variable "enable_sns_alerts" {
  description = "Enable SNS alerts for critical events"
  type        = bool
  default     = true
}

variable "sns_email_endpoint" {
  description = "Email for SNS alerts"
  type        = string
  default     = ""
}

variable "enable_slack_alerts" {
  description = "Enable Slack notifications"
  type        = bool
  default     = false
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for alerts"
  type        = string
  sensitive   = true
  default     = ""
}
