#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Step 4 — prove it in the audit log.
#
#  This is the payoff of the whole pattern: the audit log shows
#  EXACTLY which workflow, which ref, which actor read which secret.
#  No long-lived secret was involved, and the record is complete.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

AUDIT_LOG="${AUDIT_LOG:-./logs/audit.log}"
[ -f "$AUDIT_LOG" ] || { echo "audit log not found at $AUDIT_LOG" >&2; exit 1; }

echo
echo "══════════════════════════════════════════════════════════════"
echo "  The audit trail for the CI secret read"
echo "══════════════════════════════════════════════════════════════"
echo

# The most recent read of secret/data/myapp
jq -c '
  select(.type == "response")
  | select(.request.path == "secret/data/myapp")
  | {
      time:   .time,
      op:     .request.operation,
      path:   .request.path,
      ip:     .request.remote_address,
      accessor: .auth.accessor,
      policies: .auth.policies,
      entity: .auth.entity_id,
      # The claim-derived identity, as OpenBao recorded it
      metadata: .auth.metadata
    }
' "$AUDIT_LOG" | tail -3 | while read -r row; do
  echo "$row" | jq .
  echo
done

echo "─── what the token's metadata proves ──────────────────────────"
echo "  auth.metadata carries the OIDC claims that OpenBao mapped:"
echo "    actor       → who triggered the workflow"
echo "    repository  → which repo"
echo "    ref         → which branch"
echo "    workflow    → which workflow file"
echo "    environment → which GitHub environment"
echo
jq -r '
  select(.type == "response")
  | select(.request.path == "secret/data/myapp")
  | .auth.metadata
  | to_entries[]
  | "    \(.key) = \(.value | if type == "string" then . else tojson end)"
' "$AUDIT_LOG" 2>/dev/null | tail -12 || echo "  (no metadata on this token — add claim_mappings to the role)"
echo
