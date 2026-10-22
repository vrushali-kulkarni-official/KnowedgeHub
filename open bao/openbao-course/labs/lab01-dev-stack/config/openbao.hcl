// Lab 01 — OpenBao server configuration (learning)
//
// ⚠️ LEARNING CONFIG. It uses a self-signed CA and a single node.
//    For the production reference see labs/lab03-full-reference.

ui           = true
api_addr     = "https://127.0.0.1:8200"
cluster_addr = "https://openbao:8201"
cluster_name = "openbao-lab01"

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-node-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
}

default_lease_ttl = "24h"
max_lease_ttl     = "168h"

telemetry {
  prometheus_retention_time = "30s"
  disable_hostname   = false
  usage_gauge_period = "1m"
}

user_lockout "all" {
  lockout_threshold     = 5
  lockout_duration      = "15m"
  lockout_counter_reset = "15m"
}

# ── Declarative audit device (2.4.0+) ──────────────────────────────
#  In OpenBao 2.7.1 audit devices CANNOT be created via the API by
#  default ("cannot enable audit device via API; use declarative,
#  config-based audit device management instead").  Defining the
#  device here guarantees a node never comes up with audit missing.
audit "file" "file" {
  description = "Local audit log (declarative, 2.4.0+)."
  options {
    file_path = "/openbao/logs/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}
