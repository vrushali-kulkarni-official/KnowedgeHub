#!/usr/bin/env bash
# =============================================================================
# prepare-lab.sh - one-time host preparation for the lab
# =============================================================================
# Run this ONCE before `docker compose up`.
#
# Why it exists:
#   The OpenBao container runs as uid 100 (non-root). The directories it
#   writes to must therefore be owned by that uid on the host, otherwise
#   the audit log write fails and the pebbledb volume cannot be created.
#
#   We deliberately do NOT let the container chown its own directories: the
#   upstream entrypoint aborts if chown fails, and running the container as
#   root just so it can chown itself defeats the point of running as non-root.
# =============================================================================
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${LAB_DIR}"

# uid 100 / gid 1000 = the `openbao` user in the upstream image.
OPENBAO_UID=100
OPENBAO_GID=1000

echo "==> Preparing lab directories in ${LAB_DIR}"

mkdir -p logs secrets config keycloak app policies
chmod 700 secrets                       # holds unseal keys + root token
chmod 750 logs

if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "${OPENBAO_UID}:${OPENBAO_GID}" logs
  echo "  ✓ logs/ owned by ${OPENBAO_UID}:${OPENBAO_GID}"
else
  echo "  ! Not running as root - cannot chown logs/."
  echo "    If OpenBao cannot write the audit log, run:"
  echo "      sudo chown -R ${OPENBAO_UID}:${OPENBAO_GID} ${LAB_DIR}/logs"
fi

# The config directory is mounted read-only; it only needs to be readable.
chmod -R a+rX config

echo "  ✓ secrets/ is 0700 (never commit this directory - see .gitignore)"
echo "  ✓ config/ is world-readable"

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 READY

  docker compose up -d openbao
  ./scripts/init-lab.sh
  ./scripts/setup-platform.sh

──────────────────────────────────────────────────────────────────────────────
EOF
