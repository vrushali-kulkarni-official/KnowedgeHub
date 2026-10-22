# =============================================================================
# OpenBao server configuration - production-shaped, single node
# =============================================================================
# Validated against OpenBao v2.7.1 (binary run, not copied from docs).
#
# Container path: /openbao/config/openbao.hcl
# The docker entrypoint runs: bao server -config=/openbao/config
# and the server loads every .hcl/.json file in that directory.
# =============================================================================

# -----------------------------------------------------------------------------
# Listener
# -----------------------------------------------------------------------------
# TLS is disabled HERE ON PURPOSE for the local lab only, because generating a
# trusted cert requires a CA and every student hits TLS trust errors on day one.
#
# In production you MUST enable TLS. The checklist in
# modules/09-production-hardening covers the exact steps, and the dev-listen
# address override in the compose file proves the same code path works.
# -----------------------------------------------------------------------------
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true

  # Production: replace the two lines above with a TLS block.
  #   tls_cert_file   = "/openbao/tls/tls.crt"
  #   tls_key_file    = "/openbao/tls/tls.key"
  #   tls_client_ca_file = "/openbao/tls/ca.crt"
  #   tls_min_version = "tls12"
  #   tls_max_version = "tls13"

  # ---- Production tuning (keep these even in dev) ----
  # Reject oversized request bodies early. A 32MB cap is the OpenBao default;
  # you can lower it for your workload.
  # max_request_size = "33554432"

  # The cluster listener MUST be TLS in production. The dev override in
  # docker-compose sets BAO_CLUSTER_ADDR for you.
}

# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------
# IMPORTANT (2.7.x): the `file` storage backend was REMOVED in v2.7.0.
# Older tutorials telling you to use `storage "file"` are wrong for 2.7+.
#
# `pebbledb` is the modern single-node durable backend. For HA you would
# instead use integrated Raft:
#   storage "raft" { path = "/openbao/data" }
#
# `pebbledb` is deliberately non-HA. That is a safety feature, not a bug:
# it refuses to run in a multi-node cluster so you cannot accidentally
# deploy a split-brain topology.
storage "pebbledb" {
  # NOTE: the directory is "/openbao/file" for a container-ownership reason,
  # not because we use the removed `file` backend. The upstream image only
  # creates and chowns logs/, file/ and config/ under /openbao, so a Docker
  # named volume mounted at /openbao/file inherits the right (non-root)
  # ownership. See the comment in docker-compose.yml.
  path = "/openbao/file"
}

# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
ui = true

# -----------------------------------------------------------------------------
# API / cluster addressing
# -----------------------------------------------------------------------------
# In the container the server must advertise the in-network address, not
# 127.0.0.1 (which would be unreachable from another container).
# The compose file sets BAO_REDIRECT_ADDR / BAO_CLUSTER_ADDR which override
# these at runtime.
api_addr    = "http://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"

# -----------------------------------------------------------------------------
# Audit device - DECLARATIVE (this is the only supported way in 2.7+)
# -----------------------------------------------------------------------------
# Since 2.7.0, audit devices CANNOT be created via the API/CLI. Attempting
# `bao audit enable file` returns:
#   "cannot enable audit device via API; use declarative, config-based
#    audit device management instead"
#
# This was a deliberate security change (CVE-2025-54997 / HCSEC-2025-14):
# API-driven audit creation lets an API-level admin write to arbitrary host
# files or sockets, which breaks privilege separation. The fix moves audit
# device lifecycle into the operator-controlled config file.
#
# Syntax: audit "<type>" "<path>" { description = "..." options = { ... } }
# The second label is the mount path of the audit device.
audit "file" "local-file" {
  description = "Local JSON audit log"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"    # HMAC sensitive values. NEVER set true in prod.
  }
}

# -----------------------------------------------------------------------------
# Production hardening toggles
# -----------------------------------------------------------------------------
# Uncomment in production. Each one is explained in
# modules/09-production-hardening.
#
# disable_mlock is a SERVER CLI FLAG, not a config field. Setting it in this
# file causes: "unknown or unsupported field disable_mlock found in
# configuration". The container handles it via capabilities instead.
#
# Require TLS on the cluster port (always on in production):
# cluster_disable = false
#
# Refuse to start if the host name cannot be resolved (prevents a
# misconfigured HA cluster from coming up in a broken state):
# disable_clustering = false
#
# Do not leak the raft node ID in response headers:
# enable_response_header_raft_node_id = false

# -----------------------------------------------------------------------------
# Telemetry - Prometheus metrics
# -----------------------------------------------------------------------------
# Exposes /v1/sys/metrics for Prometheus. Use this for alerting on
# seal state, audit device health, and lease counts.
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}
