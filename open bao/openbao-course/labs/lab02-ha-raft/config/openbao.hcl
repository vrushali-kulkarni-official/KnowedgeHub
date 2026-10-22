# ─────────────────────────────────────────────────────────────────
#  OpenBao HA node configuration (Level 6 reference config)
#
#  node_id and api_addr differ per node — the environment variables
#  BAO_RAFT_NODE_ID / BAO_ADDR override them in the Compose file,
#  so this single file works for all 5 nodes.
#
#  NOTE ON api_addr: in this single-host lab the client-facing
#  address must be reachable from your laptop, hence 127.0.0.1.
#  In production use the real DNS name of each node, and put a
#  load balancer in front of them.
# ─────────────────────────────────────────────────────────────────

ui           = true
cluster_name = "openbao-lab02"

api_addr     = "https://127.0.0.1:8200"
cluster_addr = "https://openbao:8201"

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-1"          # overridden by BAO_RAFT_NODE_ID

  # Production tuning
  performance_multiplier = 1
  snapshot_threshold     = 8192
  snapshot_interval      = 120
  trailing_logs          = 10000
}

# ── Single listener: API on 8200, cluster traffic on 8201 ───────
#
#  IMPORTANT (verified against the 2.7.x docs):
#  The cluster listener created from `cluster_address` INHERITS this
#  listener's TLS settings. You cannot give the cluster port a
#  different TLS configuration in the same listener block, and a
#  second `listener "tcp"` block on 8201 would collide on the port.
#
#  => Enforce mTLS on 8201 at the NETWORK layer (firewall 8201 to
#     node-to-node only) rather than with client certificates.
#     If you truly need client-cert auth on the cluster port, put
#     the whole listener behind mTLS (which then also applies to the
#     API port) or use a proxy that terminates mTLS on 8201.
listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
  tls_auto_reload  = true

  # Legacy unauthenticated rekey endpoints stay disabled (listener-level)
  disable_unauthed_rekey_endpoints = true

  # Client certs are requested but not required (default). Set
  # tls_require_and_verify_client_cert = true only if EVERY client
  # of the API port also presents a cert.
  tls_disable_client_certs = false
}

default_lease_ttl = "24h"
max_lease_ttl     = "168h"

telemetry {
  prometheus_retention_time = "30s"
  disable_hostname   = false
  usage_gauge_period = "1m"
}

# These must stay off
raw_storage_endpoint    = false
introspection_endpoint  = false
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
