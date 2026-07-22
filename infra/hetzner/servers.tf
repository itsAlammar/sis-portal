locals {
  db_private_ip = "10.30.1.10"
  database_url  = "postgresql://${var.db_username}:${var.db_password}@${local.db_private_ip}:5432/${var.db_name}"
}

# ---- Postgres node -----------------------------------------------------
resource "hcloud_volume" "pgdata" {
  name              = "sis-pgdata"
  size              = var.db_volume_size
  server_id         = hcloud_server.db.id
  automount         = false
  delete_protection = false
}

resource "hcloud_server" "db" {
  name         = "sis-db"
  server_type  = var.db_server_type
  image        = "ubuntu-24.04"
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.db.id]

  network {
    network_id = hcloud_network.main.id
    ip         = local.db_private_ip
  }

  user_data = templatefile("${path.module}/cloud-init/db.yaml.tftpl", {
    db_name     = var.db_name
    db_username = var.db_username
    db_password = var.db_password
  })

  depends_on = [hcloud_network_subnet.main]
}

# ---- App nodes ---------------------------------------------------------
resource "hcloud_server" "app" {
  count        = var.app_count
  name         = "sis-app-${count.index + 1}"
  server_type  = var.app_server_type
  image        = "ubuntu-24.04"
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.app.id]
  labels       = { role = "app" }

  network {
    network_id = hcloud_network.main.id
  }

  user_data = templatefile("${path.module}/cloud-init/app.yaml.tftpl", {
    container_image = var.container_image
    database_url    = local.database_url
    secret_key      = var.sis_secret_key
  })

  depends_on = [hcloud_server.db]
}
