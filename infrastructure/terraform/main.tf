terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region"     { default = "us-east-1" }
variable "project_name"   { default = "atlas-rtb" }
variable "environment"    { default = "prod" }

# ----------- S3 data lake (Parquet, Hive partitioned) -----------
resource "aws_s3_bucket" "data_lake" {
  bucket = "${var.project_name}-${var.environment}-datalake"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Compression = "parquet-snappy"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    id     = "raw-events-tiering"
    status = "Enabled"
    filter { prefix = "raw/" }
    transition { days = 30  storage_class = "STANDARD_IA" }
    transition { days = 90  storage_class = "GLACIER_IR"  }
    transition { days = 365 storage_class = "DEEP_ARCHIVE" }
  }
}

# ----------- MSK (Kafka) -----------
resource "aws_msk_cluster" "ad_events" {
  cluster_name           = "${var.project_name}-events"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 6
  broker_node_group_info {
    instance_type   = "kafka.m5.2xlarge"
    client_subnets  = var.private_subnet_ids
    storage_info {
      ebs_storage_info { volume_size = 1000 }
    }
    security_groups = [aws_security_group.msk.id]
  }
}

# ----------- Redshift warehouse -----------
resource "aws_redshift_cluster" "warehouse" {
  cluster_identifier  = "${var.project_name}-warehouse"
  database_name       = "ads_warehouse"
  master_username     = "awsuser"
  master_password     = var.redshift_password
  node_type           = "ra3.4xlarge"
  cluster_type        = "multi-node"
  number_of_nodes     = 4
  encrypted           = true
  publicly_accessible = false
  enhanced_vpc_routing = true
}

# ----------- ElastiCache (Redis feature store) -----------
resource "aws_elasticache_replication_group" "feature_store" {
  replication_group_id       = "${var.project_name}-features"
  description                = "Real-time RTB feature store"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.r6g.xlarge"
  num_cache_clusters         = 3
  automatic_failover_enabled = true
  multi_az_enabled           = true
  parameter_group_name       = "default.redis7.cluster.on"
}

# ----------- Network plumbing (placeholders) -----------
variable "private_subnet_ids" { type = list(string)  default = [] }
variable "redshift_password"  { sensitive = true }

resource "aws_security_group" "msk" { name = "${var.project_name}-msk-sg" }

output "data_lake_bucket"     { value = aws_s3_bucket.data_lake.bucket }
output "redshift_endpoint"    { value = aws_redshift_cluster.warehouse.endpoint }
output "feature_store_node"   { value = aws_elasticache_replication_group.feature_store.primary_endpoint_address }
