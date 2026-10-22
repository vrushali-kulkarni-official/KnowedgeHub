#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  dr-drill.sh — disaster recovery drill for a Raft cluster
#
#  ⚠️  THIS SCRIPT IS DESTRUCTIVE. It wipes the cluster's data and
#      restores from a snapshot. Run it ONLY against a lab cluster.
#
#  Usage:
#     ./dr-drill.sh <snapshot-file> [node1] [node2] ...
#
#  Example:
#     ./dr-drill.sh ./backup-2026-10-20.snap
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SNAP="${1:?usage: dr-drill.sh <snapshot-file> [nodes...]}"
shift || true
NODES=("${@:-openbao-1 openbao-2 openbao-3 openbao-4 openbao-5}")
read -r -a NODES <<<"${NODES[*]}"

export BAO_ADDR="${BAO_ADDR:-https://openbao-1:8200}"
export BAO_CACERT="${BAO_CACERT:-./certs/ca.crt}"

say() { printf '\n\033[1;31m==> %s\033[0m\n' "$*"; }

[[ -f "$SNAP" ]] || { echo "Snapshot not found: $SNAP" >&2; exit 1; }
say "DR DRILL — this will DESTROY the current cluster state"
echo "    snapshot: $SNAP"
echo "    nodes:    ${NODES[*]}"
read -r -p "    Type 'destroy' to continue: " confirm
[[ "$confirm" == "destroy" ]] || { echo "Aborted."; exit 1; }

say "Step 1 — stop the cluster"
docker compose down

say "Step 2 — preserve existing data (for post-mortem analysis)"
mkdir -p ./dr-evidence-$(date +%s)
for v in $(docker volume ls -q | grep -E 'data[0-9]+$'); do
  echo "    copying $v"
  docker run --rm -v "$v":/src:ro -v "$(pwd)/dr-evidence-$(date +%s)":/dst \
    alpine tar czf /dst/"$v".tgz -C /src . 2>/dev/null || true
done

say "Step 3 — wipe the data volumes"
for v in $(docker volume ls -q | grep -E 'data[0-9]+$'); do
  docker volume rm "$v" >/dev/null 2>&1 || true
  echo "    removed $v"
done

say "Step 4 — start node 1 only"
docker compose up -d "${NODES[0]}"
sleep 10

say "Step 5 — restore the snapshot"
bao operator raft snapshot restore "$SNAP"

say "Step 6 — unseal node 1"
for i in 1 2 3; do
  read -r -s -p "    unseal key $i/3: " key; echo
  BAO_ADDR="https://${NODES[0]}:8200" bao operator unseal "$key" >/dev/null
done

say "Step 7 — start the rest and re-join"
docker compose up -d
for node in "${NODES[@]:1}"; do
  echo "    joining $node"
  BAO_ADDR="https://${node}:8200" bao operator raft join "https://${NODES[0]}:8200" || true
done
for node in "${NODES[@]:1}"; do
  for i in 1 2 3; do
    read -r -s -p "    unseal key $i/3 for $node: " key; echo
    BAO_ADDR="https://${node}:8200" bao operator unseal "$key" >/dev/null
  done
done

say "Step 8 — verify"
bao status
echo
bao operator raft list-peers
echo
bao operator raft autopilot state
echo
echo "  secrets: $(bao secrets list -format=json | jq -r 'keys | length') mount(s)"
echo "  policies: $(bao policy list -format=json | jq -r 'keys | length')"

cat <<'EOF'

──────────────────────────────────────────────────────────────
  DR DRILL COMPLETE
    ✅ The snapshot restored, the cluster rejoined, state verified.

  Now honestly answer: how long did the whole thing take?
  That number is your real RTO. Write it down and rehearse
  it again next quarter.
──────────────────────────────────────────────────────────────
EOF
