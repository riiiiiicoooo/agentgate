# AgentGate Terraform Configuration
# Deploys AgentGate to AWS ECS Fargate with RDS PostgreSQL backend

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "agentgate-terraform-state"
    key            = "agentgate/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "agentgate-terraform-lock"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "AgentGate"
      Environment = var.environment
      ManagedBy   = "Terraform"
      CreatedAt   = timestamp()
    }
  }
}

# VPC
resource "aws_vpc" "agentgate" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "agentgate-vpc"
  }
}

# Public Subnets
resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.agentgate.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  map_public_ip_on_launch = true

  tags = {
    Name = "agentgate-public-${count.index + 1}"
  }
}

# Private Subnets
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.agentgate.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 2)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "agentgate-private-${count.index + 1}"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "agentgate" {
  vpc_id = aws_vpc.agentgate.id

  tags = {
    Name = "agentgate-igw"
  }
}

# Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.agentgate.id

  route {
    cidr_block      = "0.0.0.0/0"
    gateway_id      = aws_internet_gateway.agentgate.id
  }

  tags = {
    Name = "agentgate-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Application Load Balancer
resource "aws_lb" "agentgate" {
  name               = "agentgate-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false

  tags = {
    Name = "agentgate-alb"
  }
}

resource "aws_lb_target_group" "agentgate" {
  name        = "agentgate-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.agentgate.id
  target_type = "ip"

  health_check {
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 3
    interval            = 30
    path                = "/health"
    matcher             = "200"
  }

  tags = {
    Name = "agentgate-tg"
  }
}

resource "aws_lb_listener" "agentgate" {
  load_balancer_arn = aws_lb.agentgate.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.ssl_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.agentgate.arn
  }
}

# RDS Database
resource "aws_db_subnet_group" "agentgate" {
  name       = "agentgate-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "agentgate-db-subnet-group"
  }
}

resource "aws_rds_cluster" "agentgate" {
  cluster_identifier      = "agentgate-cluster"
  engine                  = "aurora-postgresql"
  engine_version          = "15.2"
  database_name           = var.db_name
  master_username         = var.db_master_username
  master_password         = random_password.db_password.result
  db_subnet_group_name    = aws_db_subnet_group.agentgate.name
  vpc_security_group_ids  = [aws_security_group.rds.id]

  backup_retention_period      = 30
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "mon:04:00-mon:05:00"

  enable_cloudwatch_logs_exports = ["postgresql"]

  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = "agentgate-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  tags = {
    Name = "agentgate-db-cluster"
  }

  depends_on = [aws_db_subnet_group.agentgate]
}

resource "aws_rds_cluster_instance" "agentgate" {
  count              = var.db_instance_count
  cluster_identifier = aws_rds_cluster.agentgate.id
  instance_class     = var.db_instance_class
  engine             = aws_rds_cluster.agentgate.engine
  engine_version     = aws_rds_cluster.agentgate.engine_version

  performance_insights_enabled = var.environment == "production"

  tags = {
    Name = "agentgate-db-${count.index + 1}"
  }
}

# ElastiCache Redis
resource "aws_elasticache_subnet_group" "agentgate" {
  name       = "agentgate-redis-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "agentgate-redis-subnet-group"
  }
}

resource "aws_elasticache_cluster" "agentgate" {
  cluster_id           = "agentgate-redis"
  engine               = "redis"
  node_type            = var.redis_node_type
  num_cache_nodes      = var.redis_num_nodes
  parameter_group_name = "default.redis7"
  engine_version       = "7.0"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.agentgate.name
  security_group_ids   = [aws_security_group.redis.id]

  automatic_failover_enabled = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Name = "agentgate-redis"
  }

  depends_on = [aws_elasticache_subnet_group.agentgate]
}

# ECS Cluster
resource "aws_ecs_cluster" "agentgate" {
  name = "agentgate-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "agentgate-cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "agentgate" {
  cluster_name           = aws_ecs_cluster.agentgate.name
  capacity_providers     = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 100
    base              = 1
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "agentgate" {
  name              = "/ecs/agentgate"
  retention_in_days = 30

  tags = {
    Name = "agentgate-logs"
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "agentgate" {
  family                   = "agentgate"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "agentgate"
      image     = "${var.ecr_repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "DB_HOST"
          value = aws_rds_cluster.agentgate.endpoint
        },
        {
          name  = "DB_NAME"
          value = var.db_name
        },
        {
          name  = "DB_USER"
          value = var.db_master_username
        },
        {
          name  = "REDIS_HOST"
          value = aws_elasticache_cluster.agentgate.cache_nodes[0].address
        },
        {
          name  = "REDIS_PORT"
          value = tostring(aws_elasticache_cluster.agentgate.port)
        }
      ]

      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = aws_secretsmanager_secret.db_password.arn
        },
        {
          name      = "JWT_SECRET"
          valueFrom = aws_secretsmanager_secret.jwt_secret.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.agentgate.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = {
    Name = "agentgate-task-definition"
  }
}

# ECS Service
resource "aws_ecs_service" "agentgate" {
  name            = "agentgate"
  cluster         = aws_ecs_cluster.agentgate.id
  task_definition = aws_ecs_task_definition.agentgate.arn
  desired_count   = var.service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.agentgate.arn
    container_name   = "agentgate"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.agentgate,
    aws_rds_cluster_instance.agentgate
  ]

  tags = {
    Name = "agentgate-service"
  }
}

# Auto Scaling
resource "aws_autoscaling_target" "ecs_target" {
  max_capacity       = var.service_max_capacity
  min_capacity       = var.service_min_capacity
  resource_id        = "service/${aws_ecs_cluster.agentgate.name}/${aws_ecs_service.agentgate.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_autoscaling_policy" "ecs_policy_cpu" {
  name               = "agentgate-cpu-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_autoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_autoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_autoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

# Secrets Manager
resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "aws_secretsmanager_secret" "db_password" {
  name_prefix             = "agentgate/db-password-"
  recovery_window_in_days = 7

  tags = {
    Name = "agentgate-db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id       = aws_secretsmanager_secret.db_password.id
  secret_string   = random_password.db_password.result
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name_prefix             = "agentgate/jwt-secret-"
  recovery_window_in_days = 7

  tags = {
    Name = "agentgate-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id       = aws_secretsmanager_secret.jwt_secret.id
  secret_string   = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# Data source for availability zones
data "aws_availability_zones" "available" {
  state = "available"
}
