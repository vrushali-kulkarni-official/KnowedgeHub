#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  bootstrap-cluster.sh — bring up a 5-node Raft cluster
#
#  Usage:
#     ./gen-certs.sh
#     docker compose up -d
#     ./bootstrap-cluster.sh
#
#  You will be prompted for the 5 unseal keys. The script:
#    1. initialises the cluster (once)
#    2. unseals node 1
#    3. joins nodes 2-5 to the Raft cluster
#    4. unseals nodes 2-5
#    5. enables an audit device
#    6. prints the cluster state
#
#  In a real run, the unseal keys are NEVER typed in plaintext on a
#  shared terminal. Use a secure input method, or better, an
#  auto-unseal mechanism (transit seal or a KMS plugin).
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

export BAO_ADDR="${BAO_ADDR:-https://127.0.0.1:8200}"
export BAO_CACERT="${BAO_CACERT:-./certs/ca.crt}"

NODES=(openbao-1 openbao-2 openbao-3 openbao-4 openbao-5)
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

unseal_node() {
  local node="$1"
  echo "    Unsealing $node (3 of 5 keys needed)..."
  for i in 1 2 3; do
    local key
    read -r -s -p "    unseal key $i/3 for $node: " key
    echo
    BAO_ADDR="https://${node}:8200" bao operator unseal "$key" >/dev/null
  done
}

say "Step 1/6 — Initialise the cluster (one node is enough)"
if bao operator init -status >/dev/null 2>&1; then
  echo "    Already initialised."
else
  echo "    You will now get 5 unseal keys and 1 root token."
  echo "    Copy them somewhere safe. Do NOT paste them into a chat."
  bao operator init -key-shares=5 -key-threshold=3 | tee ./init-output.txt
  echo
  echo "    (init output saved to ./init-output.txt — delete it after you"
  echo "     have moved the keys to a password manager)"
fi

say "Step 2/6 — Unseal node 1"
unseal_node "${NODES[0]}"

say "Step 3/6 — Join nodes 2-5 to the Raft cluster"
for node in "${NODES[@]:1}"; do
  echo "    Joining $node..."
  BAO_ADDR="https://${node}:8200" bao operator raft join "https://${NODES[0]}:8200" || {
    echo "    !! join failed for $node — check that $node can reach ${NODES[0]}:8201" >&2
  }
done

say "Step 4/6 — Unseal nodes 2-5"
for node in "${NODES[@]:1}"; do
  unseal_node "$node"
done

say "Step 5/6 — Verify the audit device (before storing anything)"
# NOTE: in OpenBao 2.7.1 audit devices cannot be created via the API.
# The device is declared in config/openbao.hcl:
#     audit "file" "file" {
#       description = "Local audit log (declarative)."
#       options { file_path = "/openbao/logs/audit.log" mode = "0600" log_raw = "false" }
#     }
bao audit list -detailed

say "Step 6/6 — Cluster state"
bao status
echo
bao operator raft list-peers
echo
bao operator raft autopilot state

cat <<'EOF'

──────────────────────────────────────────────────────────────
  NEXT STEPS
    1. REVOKE THE ROOT TOKEN:
         bao token revoke <root-token>
    2. Set up auth (OIDC / AppRole) and policies.
    3. Take a snapshot:
         bao operator raft snapshot save ./backup-$(date +%F).snap
──────────────────────────────────────────────────────────────
EOF
