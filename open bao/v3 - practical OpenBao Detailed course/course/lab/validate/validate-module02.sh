#!/usr/bin/env bash
# =============================================================================
# validate-module02.sh - replay the Module 02 command flow end to end
# =============================================================================
# Every command in Module 02 is replayed here and its exit code is asserted.
# If this script passes, the module's commands work on a real OpenBao 2.7.1.
#
# Usage:
#   cd lab
#   ./validate/validate-module02.sh
#
# Requires: a running, unsealed OpenBao reachable at $BAO_ADDR with a token
# in $BAO_TOKEN. It RE-CREATES the ai/platform and ai/scratch mounts, so run it
# against a lab you are happy to reset - NOT against production.
# =============================================================================
export BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
export BAO_BIN="${BAO_BIN:-bao}"
if [[ -z "${BAO_TOKEN:-}" ]]; then
  if [[ -f "$(dirname "${BASH_SOURCE[0]}")/../secrets/root-token" ]]; then
    export BAO_TOKEN="$(cat "$(dirname "${BASH_SOURCE[0]}")/../secrets/root-token")"
  else
    echo "Set BAO_TOKEN, or run lab/scripts/init-lab.sh first." >&2
    exit 1
  fi
fi
FAIL=0
ck() { # ck <label> <expected-rc> <cmd...>
  local label="$1"; local want="$2"; shift 2
  local out; out="$("$@" 2>&1)"; local rc=$?
  if [[ "$rc" == "$want" ]]; then echo "  OK   ${label} (rc=${rc})";
  else echo "  FAIL ${label} (rc=${rc}, want ${want})"; echo "$out" | head -6; FAIL=1; fi
}
ckq() { # ckq <label> <expected-rc> <shell>
  local label="$1"; local want="$2"; shift 2
  local out; out="$(eval "$*" 2>&1)"; local rc=$?
  if [[ "$rc" == "$want" ]]; then echo "  OK   ${label} (rc=${rc})";
  else echo "  FAIL ${label} (rc=${rc}, want ${want})"; echo "$out" | head -6; FAIL=1; fi
}

echo "### reset to a clean lab state"
$BAO_BIN secrets disable ai/legacy2 >/dev/null 2>&1
$BAO_BIN secrets disable ai/platform >/dev/null 2>&1
$BAO_BIN secrets disable ai/scratch >/dev/null 2>&1
$BAO_BIN kv metadata delete ai/scratch/llm/gemini >/dev/null 2>&1
ck "enable ai/platform kv-v2" 0 $BAO_BIN secrets enable -path=ai/platform kv-v2
ck "enable ai/scratch kv" 0 $BAO_BIN secrets enable -path=ai/scratch kv

echo "### section 4.2 - the other three Meridian AI secrets"
ck "4.2 put postgres"  0 $BAO_BIN kv put -cas=0 ai/platform/db/postgres username=meridian_app password=Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK host=postgres port=5432 dbname=meridian_ai sslmode=require
ck "4.2 put redis"     0 $BAO_BIN kv put -cas=0 ai/platform/cache/redis host=redis port=6379 password=Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU db=0
ck "4.2 put keycloak"  0 $BAO_BIN kv put -cas=0 ai/platform/oidc/keycloak issuer="http://keycloak:8080/realms/meridian-ai" client_id=ai-harness client_secret=meridian-ai-harness-client-secret-rotate-me admin_password=admin
ck "4.2 list"          0 $BAO_BIN kv list ai/platform

echo "### section 3.3 / 3.4"
ck "enable ai/legacy2 kv" 0 $BAO_BIN secrets enable -path=ai/legacy2 kv
ck "put on v1" 0 $BAO_BIN kv put ai/legacy2/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash"
ck "enable-versioning" 0 $BAO_BIN kv enable-versioning ai/legacy2
ck "v1 metadata get" 1 $BAO_BIN kv metadata get ai/scratch/llm/gemini
ck "v1 config read" 2 $BAO_BIN read ai/scratch/config
ck "v1 rollback" 2 $BAO_BIN kv rollback -version=1 ai/scratch/llm/gemini

echo "### section 4-6"
ck "put gemini" 0 $BAO_BIN kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
ck "get gemini" 0 $BAO_BIN kv get ai/platform/llm/gemini
ck "metadata get gemini" 0 $BAO_BIN kv metadata get ai/platform/llm/gemini
ck "put v1 scratch" 0 $BAO_BIN kv put ai/scratch/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"

echo "### section 7"
ck "tune wrong endpoint" 0 $BAO_BIN write sys/mounts/ai/platform/tune cas_required=true max_versions=10
ck "write config" 0 $BAO_BIN write ai/platform/config cas_required=true max_versions=10 delete_version_after=0s

echo "### section 8"
ck "put no cas" 2 $BAO_BIN kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
ck "put stale cas" 2 $BAO_BIN kv put -cas=0 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
ck "put cas=1" 0 $BAO_BIN kv put -cas=1 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
# postgres was already seeded in 4.2 - assert it is there and readable
ck "postgres seeded (4.2)" 0 $BAO_BIN kv get ai/platform/db/postgres
ck "postgres is v1" 0 sh -c "$BAO_BIN kv metadata get -format=json ai/platform/db/postgres | python3 -c \"import sys,json;d=json.load(sys.stdin)['data'];sys.exit(0 if d.get('current_version')==1 else 1)\""
ck "per-secret cas_required=false" 0 $BAO_BIN write ai/platform/metadata/llm/gemini cas_required=false
ck "metadata_cas_required=true" 0 $BAO_BIN write ai/platform/config metadata_cas_required=true
ck "metadata put blocked" 2 $BAO_BIN kv metadata put -custom-metadata="owner=platform-team" ai/platform/db/postgres
ckq "metadata_cas=0" 0 "echo '{\"metadata_cas\":0,\"custom_metadata\":{\"owner\":\"platform-team\"}}' | $BAO_BIN write ai/platform/metadata/db/postgres -"
ckq "metadata_cas=5 stale" 2 "echo '{\"metadata_cas\":5,\"custom_metadata\":{\"owner\":\"data-team\"}}' | $BAO_BIN write ai/platform/metadata/db/postgres -"
ckq "metadata_cas=current" 0 "mc=\$($BAO_BIN kv metadata get -format=json ai/platform/llm/gemini | jq -r '.data.current_metadata_version'); echo \"{\\\"metadata_cas\\\":\$mc,\\\"custom_metadata\\\":{\\\"owner\\\":\\\"platform-team\\\"}}\" | $BAO_BIN write ai/platform/metadata/llm/gemini -"
ck "metadata_cas_required=false (reset)" 0 $BAO_BIN write ai/platform/config metadata_cas_required=false

echo "### section 9 (must now work)"
ck "metadata put custom" 0 $BAO_BIN kv metadata put -custom-metadata="owner=platform-team" -custom-metadata="rotation=90d" ai/platform/llm/gemini
ck "metadata patch" 0 $BAO_BIN kv metadata patch -custom-metadata="last_rotated=2026-10-21" -remove-custom-metadata="rotation" ai/platform/llm/gemini
ckq "custom_metadata after patch" 0 "$BAO_BIN kv metadata get ai/platform/llm/gemini | grep custom_metadata"

echo "### section 10"
ck "put bad model" 0 $BAO_BIN kv put -cas=2 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-1.0-pro" project_id="meridian-ai-prod-01"
ck "rollback v2" 0 $BAO_BIN kv rollback -version=2 ai/platform/llm/gemini
ck "get v3" 0 $BAO_BIN kv get -version=3 ai/platform/llm/gemini
ck "dva=168h" 0 $BAO_BIN write ai/platform/config delete_version_after=168h
ck "put v5" 0 $BAO_BIN kv put -cas=4 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-1.0-pro" project_id="meridian-ai-prod-01"
ck "rollback to deleted" 2 $BAO_BIN kv rollback -version=5 ai/platform/llm/gemini
ck "dva=0s" 0 $BAO_BIN write ai/platform/config delete_version_after=0s
ck "rollback still refused" 2 $BAO_BIN kv rollback -version=5 ai/platform/llm/gemini
ck "destroy postgres v1" 0 $BAO_BIN kv destroy -versions=1 ai/platform/db/postgres
ck "rollback to destroyed" 2 $BAO_BIN kv rollback -version=1 ai/platform/db/postgres

echo "### section 11"
ck "delete wrong flag" 1 $BAO_BIN kv delete -version=1 ai/platform/cache/redis
# redis was already seeded in 4.2
ck "redis seeded (4.2)" 0 $BAO_BIN kv get ai/platform/cache/redis
ck "delete v1" 0 $BAO_BIN kv delete -versions=1 ai/platform/cache/redis
ck "undelete v1" 0 $BAO_BIN kv undelete -versions=1 ai/platform/cache/redis
ck "destroy v1" 0 $BAO_BIN kv destroy -versions=1 ai/platform/cache/redis
ck "undestroy (no such subcommand)" 1 $BAO_BIN kv undestroy -versions=1 ai/platform/cache/redis
ck "metadata delete session key" 0 $BAO_BIN kv metadata delete ai/platform/cache/redis-session-key

echo "### section 12 (must now work)"
ck "metadata put dva 10s" 0 $BAO_BIN kv metadata put -delete-version-after=10s -custom-metadata="purpose=session-signing-key" ai/platform/cache/redis-session-key
ck "put session key" 0 $BAO_BIN kv put -cas=0 ai/platform/cache/redis-session-key key="mrd_sess_8nD2kL5pR7yT4wC9hB3vX6zQ1sF0gJ8eU"
code0=$(curl -s -o /dev/null -w '%{http_code}' -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/ai/platform/data/cache/redis-session-key")
sleep 12
code1=$(curl -s -o /dev/null -w '%{http_code}' -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/ai/platform/data/cache/redis-session-key")
if [[ "$code0" == "200" && "$code1" == "404" ]]; then echo "  OK   expiry 200 -> 404"; else echo "  FAIL expiry $code0 -> $code1"; FAIL=1; fi

echo "### section 14"
ck "list ai/platform" 0 $BAO_BIN kv list ai/platform
ck "list ai/platform/llm" 0 $BAO_BIN kv list ai/platform/llm
ck "scan" 0 $BAO_BIN kv scan -format=json ai/platform

echo "### section 16 (fresh mount)"
$BAO_BIN secrets disable ai/platform >/dev/null 2>&1
ck "16.1 enable" 0 $BAO_BIN secrets enable -path=ai/platform kv-v2
ck "16.1 config" 0 $BAO_BIN write ai/platform/config cas_required=true max_versions=10 delete_version_after=0s metadata_cas_required=true
ck "16.2 gemini" 0 $BAO_BIN kv put -cas=0 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
ck "16.2 postgres" 0 $BAO_BIN kv put -cas=0 ai/platform/db/postgres host="meridian-db.internal" port=5432 database="meridian_ai" username="meridian_app" password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" sslmode="verify-full"
ck "16.2 redis" 0 $BAO_BIN kv put -cas=0 ai/platform/cache/redis host="meridian-cache.internal" port=6379 username="meridian_app" password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"
ck "16.2 keycloak" 0 $BAO_BIN kv put -cas=0 ai/platform/oidc/keycloak issuer="https://sso.meridian-ai.internal/realms/meridian-ai" client_id="ai-harness" client_secret="meridian-ai-harness-client-secret-rotate-me"
ck "16.3 friendly blocked" 2 $BAO_BIN kv metadata put -custom-metadata="owner=platform-team" ai/platform/llm/gemini
ckq "16.3 raw gemini" 0 "echo '{\"metadata_cas\":0,\"custom_metadata\":{\"owner\":\"platform-team\",\"rotation\":\"90d\",\"ticket\":\"MER-1841\"}}' | $BAO_BIN write ai/platform/metadata/llm/gemini -"
ckq "16.3 raw postgres" 0 "echo '{\"metadata_cas\":0,\"custom_metadata\":{\"owner\":\"data-team\",\"rotation\":\"60d\"}}' | $BAO_BIN write ai/platform/metadata/db/postgres -"
ckq "16.3 raw redis" 0 "echo '{\"metadata_cas\":0,\"custom_metadata\":{\"owner\":\"platform-team\",\"rotation\":\"30d\"}}' | $BAO_BIN write ai/platform/metadata/cache/redis -"
ckq "16.3 raw keycloak" 0 "echo '{\"metadata_cas\":0,\"custom_metadata\":{\"owner\":\"platform-team\",\"rotation\":\"90d\"}}' | $BAO_BIN write ai/platform/metadata/oidc/keycloak -"
ck "16.4 rotate" 0 $BAO_BIN kv put -cas=1 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash" project_id="meridian-ai-prod-01"
ck "16.5 bad write" 0 $BAO_BIN kv put -cas=2 ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-1.0-pro" project_id="meridian-ai-prod-01"
ck "16.5 rollback" 0 $BAO_BIN kv rollback -version=2 ai/platform/llm/gemini
ck "16.5 get bad" 0 $BAO_BIN kv get -version=3 ai/platform/llm/gemini
ck "16.6 soft delete" 0 $BAO_BIN kv delete -versions=1 ai/platform/cache/redis
ck "16.6 undelete" 0 $BAO_BIN kv undelete -versions=1 ai/platform/cache/redis
ck "16.6 destroy" 0 $BAO_BIN kv destroy -versions=1 ai/platform/cache/redis
ckq "16.7 raw metadata dva" 0 "echo '{\"metadata_cas\":0,\"delete_version_after\":\"1h\",\"custom_metadata\":{\"purpose\":\"session-signing-key\"}}' | $BAO_BIN write ai/platform/metadata/cache/redis-session-key -"
ck "16.7 put session key" 0 $BAO_BIN kv put -cas=0 ai/platform/cache/redis-session-key key="mrd_sess_8nD2kL5pR7yT4wC9hB3vX6zQ1sF0gJ8eU"
ck "16.10 put cas=1" 0 $BAO_BIN kv put -cas=1 ai/platform/cache/redis host="meridian-cache.internal" port=6379 username="meridian_app" password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"
ck "16.10 patch cas=2" 0 $BAO_BIN kv patch -cas=2 ai/platform/cache/redis tls=false pool_size=32
ck "16.9 get gemini" 0 $BAO_BIN kv get ai/platform/llm/gemini

echo
echo "### 16.9 final state"
$BAO_BIN read ai/platform/config
$BAO_BIN kv scan -format=json ai/platform | jq
$BAO_BIN kv metadata get ai/platform/llm/gemini | grep -E "current_"

echo
if [[ $FAIL -eq 0 ]]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; fi
exit $FAIL
