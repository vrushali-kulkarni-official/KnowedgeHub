ui           = true
api_addr     = "https://openbao:8200"
cluster_addr = "https://openbao:8201"
cluster_name = "openbao-ci-lab"

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-ci-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable     = true          # lab only — see Level 5 for production TLS
}

# ── Audit device (declarative) ──────────────────────────────────
# In OpenBao 2.7.1 audit devices CANNOT be created via the API.
# Declaring it here guarantees the node comes up with audit already on.
audit "file" "file" {
  description = "Local audit log (declarative)."
  options {
    file_path = "/openbao/logs/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}

telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = false
}
