output "load_balancer_dns" {
  description = "Public DNS of each load balancer. Point Route 53 records here (weighted or failover) or hand them to users directly."
  value       = { for k, lb in aws_lb.sis : k => lb.dns_name }
}

output "ecr_repository_url" {
  description = "Push your image here, then set container_image = <this>:<tag>"
  value       = aws_ecr_repository.sis.repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL address (private)"
  value       = aws_db_instance.sis.address
}

output "cluster_name" {
  value = aws_ecs_cluster.sis.name
}
