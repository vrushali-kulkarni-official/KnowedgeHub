#!/usr/bin/env bash
# Run every example in the course and report pass/fail.
#
#   ./scripts/run_all.sh
#
# Set GOOGLE_API_KEY in .env to use real Gemini; without it every example
# runs against the deterministic offline model.

set -uo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; fi

echo "=============================================================================="
echo "  Phase 7 - LangGraph Core : running all examples"
echo "=============================================================================="

pass=0
fail=0
for f in examples/L*.py; do
  printf "%-46s" "$f"
  if out=$("$PY" "$f" 2>&1); then
    echo "PASS"
    pass=$((pass + 1))
  else
    echo "FAIL"
    echo "$out" | tail -n 15 | sed 's/^/      /'
    fail=$((fail + 1))
  fi
done

echo "------------------------------------------------------------------------------"
echo "  $pass passed, $fail failed"
echo "=============================================================================="
exit $(( fail > 0 ? 1 : 0 ))
