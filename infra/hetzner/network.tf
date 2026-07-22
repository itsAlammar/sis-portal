# Private network: app servers reach Postgres and the load balancers reach the
# app servers over private IPs; nothing but the LBs is exposed publicly.
resource "hcloud_network" "main" {
  name     = "sis-net"
  ip_range = "10.30.0.0/16"
}

resource "hcloud_network_subnet" "main" {
  network_id   = hcloud_network.main.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = "10.30.1.0/24"
}

resource "hcloud_ssh_key" "admin" {
  name       = "sis-admin"
  public_key = var.ssh_public_key
}

# App servers: SSH for admin + app port only from inside the private network
# (the load balancers live in that network).
resource "hcloud_firewall" "app" {
  name = "sis-app-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "8000"
    source_ips = ["10.30.0.0/16"]
  }
}

# DB server: Postgres reachable only from the private network.
resource "hcloud_firewall" "db" {
  name = "sis-db-fw"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "5432"
    source_ips = ["10.30.0.0/16"]
  }
}
