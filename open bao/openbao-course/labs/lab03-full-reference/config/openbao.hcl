# ─────────────────────────────────────────────────────────────────
#  OpenBao server configuration — production reference
#  (verified against the OpenBao 2.7.x documentation)
# ─────────────────────────────────────────────────────────────────

ui           = true
cluster_name = "openbao-lab03"

api_addr     = "https://openbao:8200"
cluster_addr = "https://openbao:8201"

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-1"

  performance_multiplier = 1
  snapshot_threshold     = 8192
  snapshot_interval      = 120
  trailing_logs          = 10000
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
  tls_auto_reload  = true

  # Request hardening
  max_request_duration    = "60s"
  max_request_size        = 33554432
  max_request_json_memory = 34078720
  http_read_timeout       = "30s"

  # Legacy unauthenticated rekey endpoints stay disabled
  disable_unauthed_rekey_endpoints = true
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

# Plugins: 2.5.0+ OCI distribution, hardened defaults for 2.7.0
plugin_directory = "/openbao/plugins"
plugin_auto_download     = true
plugin_auto_register     = true
plugin_download_behavior = "fail"

# Keep these OFF
raw_storage_endpoint      = false
introspection_endpoint    = false
unsafe_cross_namespace_identity = false

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
