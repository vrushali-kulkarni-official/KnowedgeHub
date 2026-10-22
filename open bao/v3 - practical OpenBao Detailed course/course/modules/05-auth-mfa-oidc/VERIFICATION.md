> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 05 (Auth Methods, MFA & OIDC with Keycloak)

**Reviewer:** General (agent `r2`) · **Date:** 2026-10-21
**Server:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`), live
instance `r2` on `127.0.0.1:9793`, storage `pebbledb`.
**Local OIDC stub:** a throwaway OpenID-Connect provider on
`127.0.0.1:18080` (discovery document + JWKS, RSA keypair generated with
`openssl`), used **only** to exercise the OpenBao side of the OIDC flow. It
stands in for Keycloak and proves nothing about Keycloak itself.
**Second server:** an extra `bao server` on `0.0.0.0:9795` so a request could
be made from a non-loopback source address, for the `token_bound_cidrs` test.

This is a **final review sweep**, not a rewrite. Prose, structure and
explanations were left alone. Only quoted outputs that did not match the live
server were changed, plus clarifying notes where a claim was unreachable.

---

## 1. What I checked

| Area | Result |
|---|---|
| `bao plugin list` auth inventory | ✅ matches |
| `bao auth enable totp` → not a catalog plugin; `bao secrets enable totp` | ✅ matches |
| AppRole role write + full read-back (13 fields) | ✅ matches |
| `role_id` / `secret_id` output blocks | ✅ matches |
| AppRole login (JSON and `-f` table) | ✅ matches |
| `auth/token/lookup-self` needs `update`, not `read` | ✅ matches |
| `bao token capabilities` | ⚠️ **fixed** (§3.3) |
| Denied read (403) and allowed read (double `.data`) | ✅ matches |
| All four AppRole failure modes incl. `%!w(<nil>)` | ✅ matches |
| `bind_secret_id=false` constraint matrix | ✅ matches |
| `custom-secret-id`, `secret-id-accessor/lookup|destroy`, the 404 trap | ✅ matches |
| `auth/token/revoke-accessor` | ✅ matches |
| `auth/approle/tidy/secret-id` warning text | ✅ matches |
| `token_bound_cidrs` enforced at use (not just at login) | ✅ matches (2nd server) |
| OIDC config: `.well-known` rejection, partial write, `role=` ignored | ✅ matches |
| `auth/oidc/role` (singular) vs `auth/oidc/roles` (404) | ✅ matches |
| `bound_claims` needs the JSON API; `bound_claims_type: array` invalid | ✅ matches |
| `auth_url` (PKCE S256 + nonce + state) | ✅ matches |
| `role_type: "oidc"` cannot log in | ✅ matches |
| CEL role create / read / evaluate / blocked | ✅ matches, ⚠️ one error string fixed (§3.5) |
| `totp` engine write / read / code | ✅ matches |
| `identity/mfa/method/totp` create / list / update traps | ⚠️ **fixed** (§3.4) |
| `admin-generate` + `generate` ("missing entityID") | ⚠️ **fixed** (§3.4) |
| `mfa_require` is a silent no-op; `totally_bogus_key=1` accepted | ✅ matches |
| `identity/mfa/login-enforcement` read-back | ✅ matches |
| The real MFA-gated login + `sys/mfa/validate` | ✅ matches |
| The CLI cannot send `mfa_payload` (403) | ✅ matches |
| GUI labels in the shipped UI bundle | ⚠️ **fixed** (§3.6) |
| Meridian AI values / secret paths / forbidden placeholders | ✅ clean |
| Required sections (60-second table, learned, next, homework, GUI) | ✅ all present |
| `hcl` policy snippets → `bao policy fmt` | ✅ all three format clean |
| Authoring-environment paths | ✅ none |

---

## 2. Commands actually run (representative — ~120 invocations)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance

# --- inventory ---
bao plugin list | awk 'NR<=2 || /auth/'
bao auth enable totp          # -> 400 plugin not found in the catalog: totp
bao secrets enable totp

# --- approle ---
bao auth enable approle
bao write auth/approle/role/ai-harness-service \
  token_policies="ai-harness-service" token_no_default_policy=true \
  token_ttl=15m token_max_ttl=1h secret_id_ttl=1h secret_id_num_uses=1 \
  secret_id_bound_cidrs="127.0.0.1/32" token_bound_cidrs="127.0.0.1/32"
bao read auth/approle/role/ai-harness-service
bao read auth/approle/role/ai-harness-service/role-id
bao write -f auth/approle/role/ai-harness-service/secret-id
bao write -format=json auth/approle/login role_id="$R" secret_id="$S"
bao write -f auth/approle/login role_id="$R" secret_id="$S"

# --- lookup-self trap ---
bao policy read default
bao policy write probe-read  probe-read.hcl
bao policy write probe-update probe-update.hcl
BAO_TOKEN="$READ_TOKEN"  bao write -f auth/token/lookup-self   # -> 403
BAO_TOKEN="$UPDATE_TOKEN" bao write -f auth/token/lookup-self # -> table

# --- capabilities ---
BAO_TOKEN="$T" bao token capabilities ai/platform/data/llm/gemini   # -> 403
bao policy write capabilities-probe capabilities-probe.hcl
PROBE=$(bao token create -policy=capabilities-probe -ttl=10m -field=token)
BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/llm/gemini  # -> read
BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/db/postgres # -> deny
BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/llm/        # -> deny

# --- failure modes ---
bao write -f auth/approle/login role_id="$R" secret_id="00000000-0000-0000-0000-000000000000"
bao write -f auth/approle/login role_id="11111111-2222-3333-4444-555555555555" secret_id="$S"
# redeemed secret_id (num_uses=1) and expired secret_id (ttl=5s, sleep 8)
bao write auth/approle/role/cidr-probe ... secret_id_bound_cidrs="10.0.0.0/8"
#   -> source address "127.0.0.1" unauthorized by CIDR restrictions on the role: %!w(<nil>)
bao write auth/approle/role/nosecret bind_secret_id=false secret_id_ttl=1h secret_id_num_uses=1
#   -> 500 at least one constraint should be enabled on the role
bao write auth/approle/role/nosecret2 bind_secret_id=false secret_id_bound_cidrs="127.0.0.1/32"   # -> OK

# --- secret-id lifecycle ---
bao write -format=json auth/approle/role/ai-harness-service/custom-secret-id secret_id="5f9a3c71-…"
bao write -format=json auth/approle/role/uses-demo/secret-id-accessor/lookup secret_id_accessor="…"
bao write -f auth/approle/role/uses-demo/secret-id-accessor/destroy secret_id_accessor="…"
bao write -f auth/approle/role/uses-demo/secret-id/accessor/destroy secret_id_accessor="…"   # -> 404
bao write -f auth/token/revoke-accessor accessor="…"
bao write -f auth/approle/tidy/secret-id role_name=ai-harness-service

# --- token_bound_cidrs, from a second source address ---
#   second server: api_addr = "http://0.0.0.0:9795"
bao write auth/approle/role/uid-demo token_policies="probe2" token_no_default_policy=true \
     token_ttl=15m secret_id_ttl=1h secret_id_num_uses=1 token_bound_cidrs="127.0.0.1/32"
BAO_TOKEN=$T                 bao read kv/data/llm/gemini   # -> 200
BAO_ADDR=http://172.26.24.178:9795 BAO_TOKEN=$T bao read kv/data/llm/gemini   # -> 403 permission denied

# --- oidc (against a local stub) ---
bao auth enable oidc
bao write auth/oidc/config oidc_discovery_url="http://keycloak:8080/realms/meridian-ai/.well-known/openid-configuration" …
#   -> 400 'oidc_discovery_url' contains '.well-known' component
bao write auth/oidc/config oidc_discovery_url="http://keycloak:8080/realms/meridian-ai" …
#   -> 400 error checking oidc discovery URL: … lookup keycloak on 192.168.0.10:53: no such host
bao write auth/oidc/config default_role="platform-operator"
#   -> 400 exactly one of 'jwt_validation_pubkeys', 'jwks_url', 'jwks_pairs', 'oidc_discovery_url', or 'provider_config' must be set
bao write auth/oidc/roles/platform-team bound_claims.groups=platform-team     # -> 404 unsupported path
bao write auth/oidc/role/probe2 user_claim="email" bound_claims.groups=platform-team
#   -> 400 'allowed_redirect_uris' must be set if 'role_type' is 'oidc' or unspecified.
bao write auth/oidc/role/probe2 bound_claims.groups=platform-team allowed_redirect_uris="…"
#   -> 400 a user claim must be defined on the role
bao write auth/oidc/role/probe2 user_claim="email" bound_claims.groups=platform-team allowed_redirect_uris="…"   # -> OK
bao write auth/oidc/role/platform-team bound_claims.groups=platform-team …   # -> Success
bao read -format=json auth/oidc/role/platform-team | jq .data.bound_claims    # -> null
curl -s -X PUT … -d '{"bound_claims":{"groups":"platform-team"}, …}' …/v1/auth/oidc/role/platform-team
bao read -format=json auth/oidc/role/platform-team   # -> bound_claims {'groups': 'platform-team'}
bao write auth/oidc/role/probe3 bound_claims_type="array"   # -> 400 invalid 'bound_claims_type': array
bao write -format=json auth/oidc/oidc/auth_url role="platform-team" redirect_uri="http://localhost:8000/oidc/callback"
bao write -format=json auth/oidc/login role="platform-team" jwt="$IDT"
#   -> 400 role with oidc role_type is not allowed
curl -s -X PUT …/v1/auth/oidc/cel/role/platform-team-cel      # -> created
bao read -format=json auth/oidc/cel/role/platform-team-cel
curl -s -X PUT …/v1/auth/oidc/cel/login  -d '{"role":"platform-team-cel","jwt":"<rs256 id token>"}'
#   -> token s.…  policies ['default','platform-operator']  ttl 2764800
# wrong group -> {"errors":["error executing cel program: CEL role 'platform-team-cel' blocked authorization with boolean false return"]}
# no groups claim -> error executing cel program: CEL auth program failed: failed to evaluate variables: variable[0].is_platform_team: … no such key: groups

# --- mfa ---
bao write -format=json totp/keys/aisha.rahman key="JBSWY3DPEHPK3PXP" issuer="meridian-ai" account_name="aisha.rahman@meridian-ai.example"
bao read -format=json totp/keys/aisha.rahman
bao read -format=json totp/code/aisha.rahman
curl -s -X POST …/v1/identity/mfa/method/totp -d '{…}'
curl -s -X LIST …/v1/identity/mfa/method/totp
curl -s -X POST …/v1/identity/mfa/method/totp/<uuid> -d '{}'         # -> issuer must be set
curl -s -X POST …/v1/identity/mfa/method/totp/<uuid> -d '{"method_name":…,"issuer":…}'   # -> 204, max_validation_attempts 3 -> 5
curl -s -X POST …/v1/identity/mfa/method/totp/aisha.rahman -d '{}'  # -> 404
bao write -format=json identity/mfa/method/totp/admin-generate entity_id="<id>" method_id="<uuid>"
bao write identity/mfa/method/totp/generate method_id="<uuid>"     # -> 400 missing entityID
bao write auth/approle/role/mfa-probe mfa_require=true token_policies="ai-harness-service"
bao read -format=json auth/approle/role/mfa-probe                  # -> no mfa_require key
bao write auth/approle/role/mfa-probe totally_bogus_key=1           # -> Success
bao write -format=json identity/mfa/login-enforcement/ai-harness-entity mfa_method_ids="…" identity_entity_ids="…"
bao read -format=json identity/mfa/login-enforcement/ai-harness-entity
bao write -format=json auth/approle/login role_id="$R" secret_id="$S"   # -> mfa_requirement + mfa_request_id
curl -s -X PUT …/v1/sys/mfa/validate -d '{"mfa_request_id":…,"mfa_payload":{"<uuid>":["<code>"]}}'
curl -s -X PUT …/v1/sys/mfa/validate -d '{"mfa_request_id":…,"mfa_payload":{"<uuid>":["000000"]}}'
bao write -format=json sys/mfa/validate mfa_request_id="$REQ" "mfa_payload.<uuid>=$CODE"   # -> 403

# --- GUI bundle ---
curl -s http://127.0.0.1:9793/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(curl -s http://127.0.0.1:9793/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
  curl -s "http://127.0.0.1:9793/ui/$f" -o "$(basename $f)"; done
cat *.js > all.js
grep -c -F "<label>" all.js
```

---

## 3. What I fixed

### 3.1 §4.7 — `bao token capabilities` was shown succeeding with a token that cannot succeed

**Defect.** The block showed `$T` (the AppRole token, created with
`token_no_default_policy=true`) returning `read` / `deny` / `deny`. The
`sys/capabilities-self` capability lives in the built-in `default` policy, which
that token does not carry. Live, the same command answers:

```
Error listing capabilities: Error making API request.

URL: POST http://127.0.0.1:9793/v1/sys/capabilities-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

**Fix.** The 403 is now shown first, followed by the grant the module already
recommends in §4.6, and then the `read` / `deny` / `deny` answers from a probe
token that actually holds the capability:

```console
$ cat > capabilities-probe.hcl <<'EOF'
path "sys/capabilities-self" {
  capabilities = ["update"]
}
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}
EOF
$ bao policy write capabilities-probe capabilities-probe.hcl
Success! Uploaded policy: capabilities-probe

$ PROBE=$(bao token create -policy=capabilities-probe -ttl=10m -field=token)
```

### 3.2 §7.3 — the MFA-method **create** response did not contain that warning

**Defect.** The create block showed
`"warnings": ["Endpoint replaced the value of these parameters with the values
captured from the endpoint's path: [method_id]"]`. Live, the create endpoint
returns **`"warnings": null`** — that warning belongs to the *update*
endpoint. Verified twice (two different method names).

**Fix.** The block now shows the real response (`data.method_id`,
`wrap_info: null`, `warnings: null`, `auth: null`) with a one-line note about
where the warning actually comes from. Everything else in §7.3 — the LIST
read-back, the `issuer must be set` rejection, the 204 on a partial update,
and `max_validation_attempts` silently resetting from 3 to 5 — reproduced
**exactly** and was left alone.

### 3.3 §7.3 — `admin-generate` targeted an entity that the enforcement does not name

**Defect (real, and it breaks the module's own demo).** The TOTP secret was
generated for entity `552d267e-…`, but the §7.5 enforcement names
`b9a00e52-…` (the entity the AppRole login creates). The TOTP secret is
attached to the entity passed to `admin-generate`, so the §7.6 validation
**cannot** succeed with those ids. Live, with the module's ids:

```
{"errors":["failed to satisfy enforcement ai-harness-entity. error: 2 errors occurred:
	* MFA secret for method name \"aisha.rahman\" not present in entity \"b9a00e52-aaca-6873-6cdc-64bc4f81d9d9\"
	* login MFA validation failed for methodID: [0d979295-056d-5a32-55a0-71c91ea5f3aa]
"]}
```

With `admin-generate` pointed at the **same** entity the enforcement names, the
whole §7.6 flow works: `sys/mfa/validate` returns
`"client_token": "s.…"`, `"policies": ["ai-harness-service"]`,
`"lease_duration": 900`.

**Fix.** The `admin-generate` entity id (and the `otpauth://` URL that repeats
it) is now `b9a00e52-aaca-6873-6cdc-64bc4f81d9d9` — the AppRole entity from
§4.5 / §7.7 — and a short warning was added explaining that the entity id
must match the one the enforcement names.

### 3.4 §6.8 — the CEL "blocked" error string was not the one this program produces

**Defect.** The module quoted:

```
error executing cel program: CEL auth program failed: failed to evaluate
variables: variable[1].result: CEL role 'platform-team-cel' blocked
authorization with boolean false return
```

That prefix is only produced when a *variable* fails to evaluate. The module's
own CEL program ends with `"expression": "is_platform_team ? result : false"`,
so with a non-matching group the **final expression** returns false and the
live server says:

```
{"errors":["error executing cel program: CEL role 'platform-team-cel' blocked authorization with boolean false return"]}
```

**Fix.** The quoted error is now the real one, and the genuinely interesting
second case — an ID token with **no** `groups` claim at all — was added,
because it is the error the module's own §6.1 realm warning predicts:

```
{"errors":["error executing cel program: CEL auth program failed: failed to evaluate variables: variable[0].is_platform_team: failed to evaluate expression \"claims.groups.exists(g, g == \\\"platform-team\\\")\": no such key: groups"]}
```

Two messages, two root causes: *the group is there but does not match* vs
*the group is not there at all*.

### 3.5 §8.1 / §8.2 — GUI labels that are not in the shipped UI bundle

**Defect.** Three separate problems, all checked against the real 8.3 MB of
JavaScript the server serves (`assets/vault.js`, `assets/chunk.475.*.js`,
`assets/chunk.524.*.js`, `assets/vendor.js`, `assets/engine.js`,
`assets/engine-vendor.js`) and against the live
`sys/internal/ui/mounts` responses:

1. **`Login Enforcement` does not exist in the bundle.** The MFA tab is
   labelled **`Enforcement`** (route `vault.cluster.access.mfa.enforcements`).
   The *CLI endpoint* is the one called `login-enforcement` — the UI and the
   API disagree about the name. Rows renamed accordingly.
2. **`Role ID`, `Secret ID` and `Custom Secret ID` do not exist in the
   bundle at all** (0 occurrences), and `AppRole` appears exactly **twice**,
   both in the *enable an auth method* wizard. `sys/internal/ui/mounts/auth/approle`
   returns the mount record with **no `paths` block**, and the UI's tab helper
   (`vault/helpers/tabs-for-auth-section`) only renders per-type tabs when
   that block is present — so the AppRole page in 2.7.1 has exactly one tab,
   **Configuration**. There is also no `vault.cluster.access.oidc.roles`
   route (the OIDC routes are `assignments`, `clients`, `keys`, `providers`,
   `scopes`, which belong to the separate "OpenBao as an OIDC **provider**"
   feature).
3. **The "Access → Leases" row pointed at a dead endpoint.** The CLI
   equivalent was `bao write sys/leases/count`, but `sys/leases/count` answers
   **404 on GET** and **405 on POST** on 2.7.1. The row now points at
   `bao list sys/leases/lookup/<prefix>`, with a note.

**Fix.** The AppRole / OIDC-role rows were replaced with the surfaces that
actually exist, and an explicit "what the 2.7.1 UI does *not* have — verified,
not guessed" block was added, including the four negative findings and the
reason they matter (an AppRole role is a machine credential; the thing that
owns it is a pipeline, not a browser).

### 3.6 §8.1 — the `curl /ui/` example listed asset names the server does not serve

**Defect.** The sample output showed `assets/application.js` and
`assets/chunk.js`. The server actually serves
`assets/chunk.475.0d3d12c9247a2b3e141f.js`, `assets/chunk.524.db8024bf66127c1bac18.js`,
`assets/engine-vendor.js`, `assets/engine.js`, `assets/vendor.js` and
`assets/vault.js`. Replaced with the real listing.

---

## 4. Confirmed-correct highlights (no change needed)

* `bao plugin list` auth block — exact match, all six methods.
* `bao auth enable totp` → `Code: 400` / `* plugin not found in the catalog: totp`.
* The AppRole role read-back, including the **`token_bound_cidrs`
  normalisation** (`127.0.0.1/32` → `127.0.0.1`) and the unchanged
  `secret_id_bound_cidrs` (`127.0.0.1/32`).
* The login JSON: `policies: ["ai-harness-service"]` only, `metadata.role_name`,
  `lease_duration: 900`, `renewable: true`, `lease_id: ""`, `orphan: true`.
* The `-f` login table really does say **`token`**, not `client_token`.
* The built-in `default` policy really does grant only `read` on
  `auth/token/lookup-self`, and `read` really does produce a 403 while
  `update` produces the table.
* All four AppRole failure messages, **including** the Go formatting bug
  `source address "127.0.0.1" unauthorized by CIDR restrictions on the role: %!w(<nil>)`.
* `bind_secret_id=false` → `Code: 500` / `* at least one constraint should be enabled on the role`,
  and the CIDR-only escape hatch.
* `secret-id/accessor/destroy` → `Code: 404` / `* unsupported path`.
* `mfa_require=true` and even `totally_bogus_key=1` are accepted and vanish on
  read-back — the "configuration that appears to work and does nothing" claim.
* The full MFA-gated login, the `mfa_requirement` block, the
  `sys/mfa/validate` success response, and the two CLI failures with
  `failed to sanitize MFA creds`.
* `token_bound_cidrs` really is enforced on **every** request: the same token
  returned the secret from `127.0.0.1` and a **403 permission denied** from
  `172.26.24.178`, and kept working from loopback afterwards.
* The OIDC config errors, the `auth/oidc/role` (singular) path, the
  `bound_claims` CLI-drops-it trap, `bound_claims_type: array` invalid, the
  `auth_url` shape (`code_challenge_method=S256`, `nonce`, `state`,
  `response_type=code`, `scope=openid`), and
  `role with oidc role_type is not allowed`.
* The CEL role: read-back exposes exactly `bound_audiences`, `cel_program`,
  `clock_skew_leeway`, `expiration_leeway`, `message`, `name`,
  `not_before_leeway`; a correct-group login returns
  `policies: ['default','platform-operator']` and **`ttl: 2764800`** (32 days).

---

## 5. What I could NOT verify — stated plainly

1. **Keycloak itself.** No Keycloak is running here and none was started. The
   OIDC claims were exercised against a **local stub** I wrote: a discovery
   document, a JWKS, and RS256 ID tokens minted with `openssl` in the shape
   Keycloak emits. That proves the **OpenBao** side (config parsing, JWKS
   fetching, signature validation, CEL evaluation, group→policy mapping, token
   issuance, TTL). It proves **nothing** about Keycloak's own behaviour. The
   browser redirect, the authorisation-code exchange at Keycloak's `/token`
   endpoint, the `code` → `id_token` → `callback` → `poll` sequence, and
   Keycloak's claim shape all remain **NOT VERIFIED HERE** — the module's §6.9
   honesty table already says exactly this, and I left it standing.
2. **The GUI was inspected as its JavaScript bundle, not clicked.** I verified
   every quoted *label* against the shipped assets and every quoted *route*
   against the live `sys/internal/ui/mounts` responses. I did not render the UI
   in a browser, so page layout (what sits on which tab) is not confirmed.
3. **The realm export** was compared against
   `course/lab/keycloak/realm-export.json` field by field (realm, groups,
   client, `defaultClientScopes`, the `groups` client scope and its
   `oidc-group-membership-mapper`). The module's §6.1 JSON is an explicitly
   labelled **abridged** excerpt ("The parts that matter"); the real file also
   carries `"attributes": {"vault_namespace": ["ai/platform"]}` on each group
   and several extra client fields. I left the excerpt as it is, because the
   module is honest about the abbreviation and expanding it would be
   restructuring, not fixing.
4. **`mfa_require` on an OIDC role** and **MFA on an OIDC login** are still
   only partially verified. `mfa_require` is confirmed to be a no-op on an
   AppRole role; the OIDC side needs a live provider and a browser.
5. **§4.10's non-loopback address** was `172.26.24.178` on my sandbox, not
   the author's `172.26.27.12`. The module already says the address is the
   reader's own `hostname -I`; the *behaviour* is what I verified and it
   matched exactly.

---

## 6. Files changed

* `modules/05-auth-mfa-oidc/README.md` — 5 output blocks corrected, 4 notes
  added (§4.7 capabilities, §7.3 MFA create + `admin-generate` entity,
  §6.8 CEL error, §8.1/§8.2 GUI labels, §8.1 UI asset list).
* `modules/05-auth-mfa-oidc/VERIFICATION.md` — this file.
* `modules/05-auth-mfa-oidc/deliverable.md` — a short "this is the previous
  round's record" banner was prepended, pointing here. The previous agent's
  findings were left in place.

---

## 7. Re-verification round 2 (2026-10-21, after the verifier FAIL)

One open item from the verifier's report concerned a count in this module's
GUI section. It was re-checked against a freshly downloaded copy of the
shipped UI bundle and **fixed**.

### 7.1 §8.1 — the "AppRole appears exactly twice" count was wrong *(FIXED)*

The bundle was re-fetched from the live server
(`curl -s "$BAO_ADDR/ui/" | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u`,
then every asset downloaded and concatenated — 8 298 532 bytes across
`vault.js`, `chunk.475.*.js`, `chunk.524.*.js`, `vendor.js`, `engine.js`
and `engine-vendor.js`).

```console
$ grep -o 'AppRole' all.js | wc -l
4
$ for f in vault.js chunk.475.*.js chunk.524.*.js vendor.js engine.js engine-vendor.js; do
    echo "$f: $(grep -o 'AppRole' "$f" | wc -l)"; done
vault.js: 4
chunk.475.0d3d12c9247a2b3e141f.js: 0
chunk.524.db8024bf66127c1bac18.js: 0
vendor.js: 0
engine.js: 0
engine-vendor.js: 0
```

The four occurrences, in context:

1. the *enable an auth method* picker —
   `{displayName:"AppRole",value:"approle",type:"approle",category:"generic"}`
2. the same wizard's header block —
   `["AppRole","cpu","Docs: AppRole Authentication","/docs/auth/approle.html"]`
3. the same header block's doc title — `Docs: AppRole Authentication`
4. a documentation blurb — `The open design of AppRole\n enables a varied
   set of workflows and configurations …`

**The count was four, not two.** The claim in §8.1 has been replaced with
the exact figure, the four locations, and a stronger negative result that
was also re-measured — every AppRole *field* name is absent from the whole
bundle:

```console
$ for f in role_id secret_id secret_id_ttl secret_id_num_uses bind_secret_id \
           token_bound_cidrs token_policies; do
    echo "$f: $(grep -o -F "$f" all.js | wc -l)"; done
role_id: 0
secret_id: 0
secret_id_ttl: 0
secret_id_num_uses: 0
bind_secret_id: 0
token_bound_cidrs: 0
token_policies: 0
```

That is the real reason there is no AppRole role page in the 2.7.1 UI: the
UI has never heard of an AppRole role.

### 7.2 Commands run in this round

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN operator unseal "$(cat …/r2/unseal-key-1)"
$BAO_BIN operator unseal "$(cat …/r2/unseal-key-2)"

# refresh the UI bundle from the live server
mkdir -p uichunks && cd uichunks
curl -s "$BAO_ADDR/ui/" | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(curl -s "$BAO_ADDR/ui/" | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
  curl -s "$BAO_ADDR/ui/$f" -o "$(basename $f)"; done
cat *.js > all.js
grep -o 'AppRole' all.js | wc -l
grep -o -F role_id all.js | wc -l          # 0
grep -o -F secret_id_ttl all.js | wc -l    # 0
```

### 7.3 The auth-object envelopes, re-measured

Because Module 04's §5.4 block was in question, the three `auth` envelopes
were re-measured on the live server so this module's §4.5 and §7.6 blocks
could be checked against them:

| response | keys in `auth` | `token_type`? |
|---|---|---|
| `POST /v1/auth/token/create` (`bao token create`) | 11 | no |
| `POST /v1/auth/approle/login` | 11 | no (still 11 with `token_type=service` on the role) |
| `PUT /v1/sys/mfa/validate` | **12** | **yes — `"token_type": "service"`, plus `num_uses`** |

§4.5 (AppRole login, 11 keys, no `token_type`) and §7.6 (`sys/mfa/validate`,
12 keys, `token_type: "service"`) are both correct as written.

### 7.4 Still not verified

* Keycloak itself — the browser redirect, the authorisation-code exchange and
  Keycloak's claim shape remain unverified. The OpenBao side was proved
  against a local discovery/JWKS stub, as in round 1.
* The GUI was inspected as its JavaScript bundle, not clicked in a browser.
