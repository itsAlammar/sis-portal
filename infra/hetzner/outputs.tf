output "load_balancer_ips" {
  description = "Public IPv4 of each load balancer. Point DNS here (both, for redundancy) or hand out either."
  value       = [for lb in hcloud_load_balancer.lb : lb.ipv4]
}

output "app_server_ips" {
  description = "Admin SSH IPs of the app servers"
  value       = hcloud_server.app[*].ipv4_address
}

output "db_server_ip" {
  description = "Admin SSH IP of the Postgres server (DB itself is private only)"
  value       = hcloud_server.db.ipv4_address
}
