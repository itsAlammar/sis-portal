# Two managed Hetzner Cloud Load Balancers (per the owner's request). Both
# select the same app servers by label and reach them over the private network.
# Point DNS at either public IP, or round-robin/fail over between the two.
resource "hcloud_load_balancer" "lb" {
  count              = 2
  name               = "sis-lb-${count.index + 1}"
  load_balancer_type = "lb11"
  location           = var.location
}

resource "hcloud_load_balancer_network" "lb" {
  count            = 2
  load_balancer_id = hcloud_load_balancer.lb[count.index].id
  network_id       = hcloud_network.main.id
  depends_on       = [hcloud_network_subnet.main]
}

resource "hcloud_load_balancer_target" "app" {
  count            = 2
  type             = "label_selector"
  load_balancer_id = hcloud_load_balancer.lb[count.index].id
  label_selector   = "role=app"
  use_private_ip   = true
  depends_on       = [hcloud_load_balancer_network.lb]
}

resource "hcloud_load_balancer_service" "http" {
  count            = 2
  load_balancer_id = hcloud_load_balancer.lb[count.index].id
  protocol         = "http"
  listen_port      = 80
  destination_port = 8000

  health_check {
    protocol = "http"
    port     = 8000
    interval = 15
    timeout  = 5
    retries  = 3
    http {
      path         = "/healthz"
      status_codes = ["2??"]
    }
  }
}
