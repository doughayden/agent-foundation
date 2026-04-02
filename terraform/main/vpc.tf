locals {
  cloud_iap_ip_cidr = "35.235.240.0/20"
}

resource "google_compute_network" "main" {
  name                    = local.resource_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name                     = local.resource_name
  ip_cidr_range            = "10.0.0.0/24"
  region                   = var.region
  network                  = google_compute_network.main.id
  private_ip_google_access = true
}

# Private Services Access — allocates an IP range for Cloud SQL private IP
resource "google_compute_global_address" "private_db" {
  name          = "${local.resource_name}-private-db"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_db" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_db.name]
}

# NAT for bastion outbound (pull proxy image, reach Cloud SQL Admin API)
resource "google_compute_router" "main" {
  name    = local.resource_name
  region  = var.region
  network = google_compute_network.main.id
}

resource "google_compute_router_nat" "main" {
  name                               = local.resource_name
  router                             = google_compute_router.main.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Allow IAP TCP SSH + SQL forwarding to bastion
resource "google_compute_firewall" "iap_ssh" {
  name    = "${local.resource_name}-iap-ssh"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges           = [local.cloud_iap_ip_cidr]
  target_service_accounts = [google_service_account.bastion.email]
}

resource "google_compute_firewall" "iap_postgres" {
  name    = "${local.resource_name}-iap-postgres"
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_ranges           = [local.cloud_iap_ip_cidr]
  target_service_accounts = [google_service_account.bastion.email]
}
