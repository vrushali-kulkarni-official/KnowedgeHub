ui = true

# API address for clients
api_addr = "http://127.0.0.1:8200"

# Cluster address for HA communication (set as requested)
cluster_addr = "https://127.0.0.1:8201"

# PebbleDB storage backend (single-server, no HA)
storage "pebbledb" {
  path = "/openbao/data"
}

# Listener configuration
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true   # API is HTTP as requested; disable TLS for the listener
}
