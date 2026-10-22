# VERIFIED FACTS — OpenBao 2.7.1

**Everything in this file was executed against a live OpenBao v2.7.1 server.**
It is not copied from documentation or from memory. If something here
contradicts a tutorial you find online, the tutorial is describing
HashiCorp Vault, not OpenBao 2.7.

**Your job:** teach these facts. Do not soften them, do not "mention both
options", and do not teach Vault-era behavior as if it were current.

---

## 0. The version

```
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
```

Latest release as of 2026-10-21. Image tag: `openbao/openbao:2.7.1`.
Go 1.27.1. Storage default in the image: `pebbledb`.

---

## 1. Sealing, recovery, and the recovery-key trap

### 1.1 Shamir mode produces NO recovery keys

```bash
$ bao operator init -key-shares=3 -key-threshold=2 \
      -recovery-shares=5 -recovery-threshold=3 -format=json | jq .recovery_keys_b64
null
```

`-recovery-shares` / `-recovery-threshold` are **auto-unseal only**
(Transit / KMS / HSM). CLI help says so verbatim:

> `-recovery-shares=<int>` … *This is only used in Auto Unseal mode. The default is 5.*

**In Shamir mode, the unseal keys ARE the recovery mechanism.** There is no
separate backup quorum. Losing too many unseal shares = cryptographically
unrecoverable data, by design.

### 1.2 `generate-root` — exact mechanics

```bash
# 1. OTP (prints ONLY the 26-char string, no label, no table)
bao operator generate-root -generate-otp
#   -> 8BL7xUkLdWlcoY9WmPJBkP9F0Z

# 2. Start the attempt (OTP must be exactly 26 chars)
bao operator generate-root -init -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z"
#   Nonce         08837b17-2e2e-7b80-7988-e2c818e1c396
#   Started       true
#   Progress      0/2
#   Complete      false
#   OTP Length    26

# 3. Submit each share — the NONCE must be passed every time
bao operator generate-root -nonce="08837b17-..." -otp="8BL7..." "<unseal-key-1>"
bao operator generate-root -nonce="08837b17-..." -otp="8BL7..." "<unseal-key-2>"
#   Progress      2/2
#   Complete      true
#   Encoded Token    JVoBXS0CXXwCAyowNFZeOzczPh8Xei8hK2c

# 4. Decode with the SAME OTP
bao operator generate-root -decode="JVoBXS0CXXwCAyowNFZeOzczPh8Xei8hK2c" \
  -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z"
#   -> s.d5wIhHSwiZrokAEZLSNOylC7
```

**Gotchas that are real and reproducible:**
- `-generate-otp` prints the bare string. `| grep OTP | awk '{print $2}'` yields
  empty. Use `| tail -1`.
- The **nonce is required** on every subsequent call. Without `-nonce`:
  `Missing nonce value: specify it via the -nonce flag`.
  The CLI does **not** auto-carry it.
- The output field is **`Encoded Token`** (two words) → `awk '/^Encoded Token/{print $3}'`.
  `Encoded Root Token` matches nothing.
- The attempt is consumed on completion; a fresh `-init` is needed to re-read it.
- A short OTP → HTTP 400.
- `generate-root` requires a token with **`sudo`** (the 2.6+ authenticated
  `/sys/generate-root-token` endpoints). An unrelated low-privilege token gets 403.
- `generate-root` does **not** rotate the root key. Use `bao operator rekey`
  for that (and that invalidates existing shares).

### 1.3 Seal / unseal

```bash
bao operator seal     # -> Sealed  true
bao operator unseal "<key1>"   # Sealed  false after the threshold is met
```

Seal/unseal need **no token**. After every restart the server comes back
**sealed** — verified.

---

## 2. Storage

- The **`file` storage backend was REMOVED in v2.7.0.** Any tutorial using
  `storage "file"` is out of date.
- `pebbledb` — durable, non-HA, new in 2.7.0. Refuses to run multi-node
  (deliberate split-brain guard).
- `raft` — the integrated HA backend.
- A second instance against the same data dir fails with
  `error initializing storage of type pebbledb: failed to open database: resource temporarily unavailable`.

---

## 3. Audit devices — declarative only (big 2.7 change)

`bao audit enable file file_path=...` **fails**:

```
* cannot enable audit device via API; use declarative, config-based audit
  device management instead
```

The working syntax has **two labels** and an `options` map:

```hcl
audit "file" "local-file" {
  description = "Local JSON audit log"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"
  }
}
```

⚠️ Two malformed forms, verified on 2.7.1 by booting a server with each:

**(a) One label, no `options` map — the server REFUSES TO START:**
```hcl
audit "file" {
  file_path = "/openbao/logs/audit.log"
}
```
```
error loading configuration from openbao.hcl: error parsing 'audit':
audit.0: audit type must be specified: &ast.ObjectItem{...}
```
This is a hard startup failure, not a silent no-op. You get a loud error
and the server never comes up.

**(b) Two labels, but `file_path` inline instead of in `options` — the
server STARTS and the field is IGNORED:**
```hcl
audit "file" "local-file" {
  file_path = "/openbao/logs/audit.log"
}
```
```
2026-10-21T18:32:50.122Z [WARN]  unknown or unsupported field file_path
found in configuration at openbao.hcl:6:3
```
The server comes up, but `file_path` never reached the device. This is the
nastier one, because it only warns — check the startup log for that WARN
line if your audit log is not where you expect it.

**(c) The working form** — two labels AND an `options` map — starts
clean, registers the device, and writes the log. That is the only form to
use.

With `log_raw = "false"` the audit log HMACs secret values:

```json
"api_key": "hmac-sha256:99573bf8d5f6f359999ebb2e953a1b1994fdc3dc6d98ab7df96aec3b91934d47"
```

Rationale: CVE-2025-54997 / HCSEC-2025-14 — API-driven audit creation lets
an API-level admin write to arbitrary host files, breaking privilege
separation.

---

## 4. Leases — breaking endpoint changes (2.7)

Removed (404), due to CVE-2026-45808 (cross-namespace lease revocation):

| Endpoint | Status |
|---|---|
| `sys/renew` | ❌ removed |
| `sys/revoke` | ❌ removed |
| `sys/revoke-prefix` | ❌ removed |
| `sys/revoke-force` | ❌ removed |
| `sys/leases/renew-force` | ❌ removed (404) |
| `sys/leases/renew` | ✅ |
| `sys/leases/revoke` | ✅ |
| `sys/leases/lookup` | ✅ |
| `sys/leases/revoke-prefix` | ✅ |
| `sys/leases/count` | ✅ (GET) |

Token TTL lives in `auth.lease_duration` (e.g. 1800). The top-level
`lease_id` / `lease_duration` are for **dynamic** secrets (database creds,
PKI certs) — a plain token's top-level `lease_id` is `""`.

```bash
bao write sys/leases/lookup    lease_id="..."
bao write sys/leases/renew     lease_id="..." increment="1h"
bao write sys/leases/revoke    lease_id="..."
bao write sys/leases/revoke-prefix prefix="ai/platform"
```

---

## 5. KV v2

### 5.1 `kv` is KV **v1**. `kv-v2` is v2.

```bash
$ bao secrets enable -path=ai/scratch kv      # <- KV v1 !
$ bao secrets enable -path=ai/platform kv-v2  # <- KV v2
```

Proof via the mount table:

```bash
$ bao read sys/mounts -format=json | jq -r '.data | to_entries[]
    | select(.key|startswith("ai/")) | "\(.key) options=\(.value.options)"'
ai/platform/ options={"version":"2"}     <- v2
ai/scratch/  options=null                <- v1
```

KV v1 has **no** `config` endpoint and **no** `metadata` layer.

### 5.2 KV v2 config lives at `<mount>/config`

```bash
$ bao write sys/mounts/ai/platform/tune cas_required=true max_versions=10
Success! Data written to: sys/mounts/ai/platform/tune     # <- LIES
$ bao read ai/platform/config
cas_required             false                              # <- unchanged
```

```bash
$ bao write ai/platform/config cas_required=true max_versions=10 delete_version_after=168h
Success! Data written to: ai/platform/config                # <- CORRECT
$ bao read ai/platform/config
cas_required             true
delete_version_after     168h0m0s
max_versions             10
metadata_cas_required    false
```

`sys/mounts/<path>/tune` is for **generic** engine tuning (lease TTLs,
listing visibility). `<mount>/config` is for **KV v2** specifics.

### 5.3 With `cas_required=true`, EVERY write needs CAS — including the first

```bash
$ bao kv put ai/platform/llm/gemini api_key="..."   # -> 400 check-and-set parameter required
$ bao kv put -cas=0 ai/platform/llm/gemini api_key="..."   # -> OK, creates version 1
```

### 5.4 Rollback creates a NEW version

```bash
bao kv rollback -version=1 ai/platform/llm/gemini
```

Result: `current_version` goes 4 → 5. Version 1 is **still readable**. The
audit trail stays honest — the rollback is itself recorded.

### 5.5 Other verified behaviors

- `bao kv metadata put -custom-metadata="owner=platform-team" -custom-metadata="rotation=90d" <path>`
  (repeatable) → `custom_metadata  map[owner:platform-team rotation:90d]`
- `bao kv list ai/platform/llm` → prints `gemini` (no trailing slash).
- JSON output: `.data.data.<key>` is the secret, `.data.metadata` is metadata.
  (Two `.data` levels — a classic stumble.)
- `bao kv tune` **does not exist**. `bao kv metadata` has get/put/patch/delete.

### 5.5b `kv` version flags are INCONSISTENT — learn them individually

This trips people constantly because the flag changes meaning per subcommand:

| Subcommand | Flag | Type | Note |
|---|---|---|---|
| `bao kv get` | `-version=N` | **int**, single | singular |
| `bao kv rollback` | `-version=N` | **int**, single | singular |
| `bao kv delete` | `-versions=N` | **string**, comma-separated | **PLURAL** |
| `bao kv undelete` | `-versions=N` | **string**, comma-separated | **PLURAL** |
| `bao kv destroy` | `-versions=N` | **string**, comma-separated | **PLURAL** |

Using the wrong one gives:

```
$ bao kv destroy -version=1 ai/platform/llm/gemini
flag provided but not defined: -version
```

Confirmed live on 2.7.1 for all three plural-flag subcommands. The
plural form also accepts a comma-separated list: `-versions=1,2,3`.

**Rule of thumb:** `get` and `rollback` take ONE version (`-version`).
Anything that acts ON versions in bulk takes the plural (`-versions`).

---

## 6. Built-in plugin inventory (2.7.1)

From `bao plugin list` on the live server:

```
SECRET (type=secret)          AUTH (type=auth)
  kv                            approle
  pki                           cert
  ssh                           jwt
  transit                       kubernetes
  totp                          oidc
  database                     userpass
  rabbitmq
  kubernetes
```

Database plugins: `postgresql-database-plugin`, `redis-database-plugin`,
`valkey-database-plugin`, `mysql-database-plugin` (+ aurora/rds/legacy),
`cassandra-database-plugin`, `influxdb-database-plugin`.

**NOT built-in** (moved to `openbao-plugins`, must be installed as external
plugins): `aws`, `gcp`, `azure`, `ad`, `ldap`, `consul`, `nomad` secret
engines; `ldap` and `kerberos` auth; **all** KMS seals — `awskms`,
`gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`, `pkcs11`.

`transit` seal is built-in. `shamir` is the default.

---

## 7. Config-file gotchas

| Mistake | Result |
|---|---|
| `disable_mlock = true` in HCL | `unknown or unsupported field disable_mlock` — it is a **CLI flag** |
| `api_addr = "127.0.0.1:8200"` | `Error parsing synthesized cluster address ... invalid URI` — needs a full URL |
| `audit "file" { file_path = ... }` (one label) | **Refuses to start** - `audit type must be specified` |
| `audit "file" "local-file" { file_path = ... }` (two labels, field inline) | Starts, but `[WARN] unknown or unsupported field file_path` and the path is **ignored** |
| Second instance, same data dir | `resource temporarily unavailable` (pebbledb lock) |

---

## 8. CLI argument-order rules (the #1 papercut)

**Flags go BEFORE positionals.**

```bash
bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h ai/platform   # OK
bao secrets tune ai/platform -default-lease-ttl=1h                       # FAILS
#   Command flags must be provided before positional arguments.
#   Too many arguments (expected 1, got 3)

bao write -format=json sys/wrapping/unwrap token="s.xxx"   # OK
bao write -format=json -token="s.xxx" sys/wrapping/unwrap  # FAILS
#   flag provided but not defined: -token
```

- JSON output flag is **`-format=json`**, NOT `-f=json`. `-f` is `--force` on writes.
- `bao write sys/wrapping/unwrap token="..."` — `token` is a **data field**.
- `bao write sys/wrapping/wrap text="..."` — use `text=`, **not** `-text=`
  (the latter creates a payload key literally named `"-text"`).
- `bao secrets enable -path=<mount> <type>` — the TYPE is the positional.
- `bao read sys/mounts -format=json` — fine (path is first, no positional conflict).

---

## 9. Namespaces, entities, groups

```bash
bao namespace create tenant-alpha
bao namespace list
bao secrets list -namespace=tenant-alpha     # separate cubbyhole/identity/sys
bao secrets enable -namespace=tenant-alpha -path=ai/tenant kv-v2
```

A child-namespace mount is **not visible** from the root namespace.

**Identity store is `identity/entity`**, NOT `auth/token/identities/entity`
(the latter 404s with "unsupported path").

```bash
bao write identity/entity name=ai-harness-service
bao list identity/entity/name
#   ai-harness-service
#   entity_a72925d7.root
```

---

## 10. 2.7.0 feature highlights (from the official CHANGELOG)

- **PebbleDB storage backend** (new)
- **Control Groups** — new ACL policy stanza `control_group`; a second party
  must approve a request on a path
- **External Keys** — PKI and Transit can use KMS-backed key material that
  never enters OpenBao (`/sys/external-keys`)
- **ML-DSA (FIPS 204)** in PKI, Transit, and TLS — post-quantum
- **Pure-PQC TLS** via `tls_key_exchange_preferences`
- **PostgreSQL horizontal scalability** (read replicas)
- **Strong Consistency Control** — `X-Vault-Index` / `X-Vault-Inconsistent`
- `tls_auto_reload`, `plugin_auto_register` default `true`, OCI plugin pinning
  by digest, `revoke-self` with wrapping tokens

2.6.0 added: per-namespace sealing, workflow engine, distroless images,
authenticated root generation.

---

## 11. Container specifics (openbao/openbao:2.7.1)

- Alpine-based, non-root user `openbao` = **uid 100, gid 1000**.
- Default `CMD` is `server -dev -dev-no-store-token` (in-memory, always unsealed).
- Entrypoint runs `bao server -config=/openbao/config`, loading every
  `.hcl`/`.json` in that dir. `BAO_LOCAL_CONFIG` writes `local.json` there.
- Entrypoint chowns `/openbao/{config,logs,file}` and **aborts** if chown
  fails (`set -e`). It does **not** chown `/openbao/data`.
  → To run non-root: set `SKIP_CHOWN=true` and pre-own host dirs, and mount
  the data volume at **`/openbao/file`** (one of the three dirs the image
  creates, so a named volume inherits uid 100). Mounting at `/openbao/data`
  yields a root-owned volume and the server will not start.
- `bao` is symlinked as `vault` inside the image.
- Distroless variant: `openbao/openbao-distroless` (added 2.6).

---

## 12. `bao policy fmt` validates policies CLIENT-SIDE (no server needed)

Proven by pointing the CLI at an unreachable address
(`BAO_ADDR=http://127.0.0.1:1`) — it still parsed and rejected bad policies.

```bash
$ BAO_ADDR="http://127.0.0.1:1" bao policy fmt bad-policy.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": path
"ai/platform/data/llm/gemini": invalid capability "reed"
exit=1

$ BAO_ADDR="http://127.0.0.1:1" bao policy fmt good-policy.hcl
Success! Formatted policy: good-policy.hcl
exit=0
```

It catches, with the same messages the server produces:
- invalid capability names
- unknown top-level keys in a `path` block
- invalid keys inside a `control_group` block

**Why this matters:** policies can be linted in GitHub Actions with **no
OpenBao server and no credentials**. That is the correct shape for
policies-as-code — validate in CI, then apply.

`bao policy fmt <file>` rewrites the file in canonical formatting.

---

## 12b. The dev-server root token is RANDOM in 2.7.1 (not "root")

Verified in Module 01's correctness sweep.

```bash
$ bao server -dev
# ... "Root Token: s.XXXXXXXXXXXXXXXXXXXX"   <- random, per run
```

- 2.7.1's dev server generates a **random** root token and prints it on stdout.
- You only get the literal string `root` if you ask for it:
  `-dev-root-token-id=root` (or `BAO_DEV_ROOT_TOKEN_ID=root`).
- The token is written to the CLI helper file `~/.vault-token` (mode 600)
  UNLESS the server runs with `-dev-no-store-token`.
- **The container image's default CMD is `server -dev -dev-no-store-token`**,
  so in the image the token exists ONLY in the container's stdout:
  ```bash
  docker logs meridian-openbao | grep -i "root token"
  ```
- A tutorial that says the dev root token is `root` is describing
  **HashiCorp Vault's** default, not OpenBao's.

---

## 13. How to get REAL GUI menu paths (do not guess them)

The OpenBao UI is an Ember app served at `/ui/`. Its JavaScript bundle
contains the literal menu labels. To extract the real navigation strings
instead of guessing them:

```bash
# 1. list the UI's JS assets
curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u

# 2. pull them down
mkdir -p /tmp/uichunks && cd /tmp/uichunks
for f in $(curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
  curl -s "http://127.0.0.1:8200/ui/$f" -o "$(basename $f)"
done

# 3. grep for a label you want to confirm
grep -c -F "ACL Policies" vault.js
grep -oE '"[A-Z][A-Za-z ]{3,40}"' vault.js | sort -u | head -60
```

This is how you get the EXACT wording of menu items ("ACL Policies",
"Enable secrets engine", "Wrap Data", "Authentication methods") instead of
guessing and getting a screenshot's worth of wrong navigation. Use it for
every GUI section you write.

---

## 12c. Seal / unseal and key-status — three things that bite

### 12c.1 `sys/unseal` needs NO token and NO `sudo`

```bash
$ bao operator unseal "<share>"      # works with no BAO_TOKEN at all
$ bao write sys/unseal key="<share>" # also works with a non-sudo token
```

Unsealing is deliberately unauthenticated — you cannot authenticate to
unseal a server whose auth backend depends on secrets that are still
encrypted. **Do not write a policy table claiming `sys/unseal` requires
`sudo` and returns 403. It does neither.** A `platform-admin` token
without `sudo` can unseal the vault.

### 12c.2 `Encryption Count` does NOT increment on seal/unseal

```bash
$ bao operator key-status | grep -i "Encryption Count"
Encryption Count    223
$ bao operator seal && bao operator unseal <k1> && bao operator unseal <k2>
$ bao operator key-status | grep -i "Encryption Count"
Encryption Count    223      # UNCHANGED
```

Verified across two full seal/unseal cycles on a live server. The counter
does **not** move when you seal and unseal. So the common advice "if the
encryption count climbs, something is sealing your vault on a schedule" is
a **guaranteed false alarm** — the number does not track seal cycles.

Never teach that as a detection signal without verifying it. If you want
a real "is it being sealed" signal, use `sealed` in `sys/health` plus the
`core: marked as sealed` line in `server.log`.

### 12c.3 `bao operator rekey` is DEPRECATED in 2.7.1

```
$ bao operator rekey -help
  WARNING: this method is deprecated, please use:
    $ bao operator rotate-keys
  instead.
```

And the old init endpoint no longer works:

```bash
$ bao operator rekey -init
URL: PUT http://127.0.0.1:8200/v1/sys/rekey/init
Code: 405. Errors: ...
```

Use `bao operator rotate-keys` (same quorum requirement: unseal shares in
Shamir mode). Rotating shares **invalidates every old share immediately**.

---

## 13a. Round 4 — the auth envelopes, MFA paths and ACME identifiers

### The three auth envelopes (they are NOT interchangeable)

| Call | Where the payload lives | Keys |
|---|---|---|
| `bao token create` | `auth` | **11** — `accessor`, `client_token`, `entity_id`, `identity_policies`, `lease_duration`, `metadata`, `mfa_requirement`, `orphan`, `policies`, `renewable`, `token_policies` |
| `auth/approle/login` | `auth` | the same **11** — **no `token_type`**, no `num_uses` |
| `bao token lookup` | **`data`** (not top level) | `type` = `"service"`, `num_uses`, `display_name`, `policies`, `path`, `id`, … |
| `sys/mfa/validate` | `auth` | **12** — includes `token_type: "service"` and `num_uses` |

> A block that shows `"token_type": "service"` next to an 11-key `auth`
> object is **wrong for AppRole**. That shape belongs to the MFA-gated
> login. Vault-era material conflates the two.

`bao token create` returns `lease_id: ""`, `lease_duration: 0` and
`renewable: false` at the top level, while the table view shows
`token_duration 30m` / `token_renewable true`. The top-level fields are
*lease* fields; a token is not a lease. This is correct, not a bug.

### MFA methods live under `identity/`, not `sys/mfa/`

| Endpoint | 2.7.1 |
|---|---|
| `identity/mfa/method/totp` (POST) | **create** — the server generates the id and returns `data.method_id` |
| `identity/mfa/method/totp/{method_id}` (POST) | **update** — returns **204**; omitted fields are reset to defaults; an empty body → `{"errors":["issuer must be set"]}` |
| `identity/mfa/method/totp/admin-generate` | needs `entity_id` + `method_id`; returns `barcode` + `url` |
| `identity/mfa/method/totp/generate` | self-service; needs the caller to **have an entity** → `400 missing entityID` (the root token has none) |
| `identity/mfa/login-enforcement/{name}` | needs one of `auth_method_accessors`, `auth_method_types`, `identity_group_ids`, `identity_entity_ids`, else `400 One of … must be specified` |
| `sys/mfa/method/totp` | **404 `unsupported path`** |
| `sys/mfa/methods/totp` | **404 `unsupported path`** |
| `sys/mfa/validate` | still exists (POST, unauthenticated) — it is the *login-completion* endpoint, not a method-creation one |

`mfa_require` on an auth-method role is **silently ignored** in 2.7.1.

### The OpenAPI spec needs a token

`GET /v1/sys/internal/specs/openapi` returns a well-formed spec with an
**empty** `paths` object unless you send `X-Vault-Token`. With the header it
returns all 251 paths. Always send it.

### PKI / ACME identifier rules

| Where | What it takes | Failure |
|---|---|---|
| `ai/pki/config/acme` → `allowed_issuers` | issuer **names** | `500 failed validating allowed_issuers: unable to fetch issuer: <name>: unable to find PKI issuer for reference: <name>` |
| `/ai/pki/issuer/<id>/acme/directory` | the issuer **UUID** | `400 … issuer does not exist` |
| `ai/pki/config/cluster` → `path` | a **URL** | `500 invalid, non-URL path given to cluster: <name>` |

A fresh mount's default PKI issuer has an **empty `issuer_name`** until you
name it, so it cannot appear in `allowed_issuers` before that:

```bash
bao write ai/pki/issuer/$ISSUER_ID issuer_name=meridian-ai-root-2026
```

### Operational facts

- `bao status` **exits 2** when the server is sealed or uninitialised. Test
  the JSON payload, never the exit code — and capture before matching, because
  `set -o pipefail` turns that exit 2 into a failed pipeline.
- Three names for two numbers: `sys/seal-status` returns **`t` / `n`**;
  `bao status`'s table prints **`Threshold` / `Total Shares`**;
  `bao operator init -format=json` returns **`unseal_threshold` /
  `unseal_shares`**.
- A sealed or uninitialised server answers **`503 Vault is sealed`** to every
  read.
- An AppRole with `secret_id_ttl=1h` expires: the next login fails
  `403 permission denied`, or `400 invalid role or secret ID` once fully
  expired. Re-mint with
  `bao write -force auth/approle/role/<role>/secret-id`. The lab ships
  `lab/scripts/refresh-credentials.sh` for exactly this.

---

## 13b. NEVER leak authoring-environment paths into the course

The course is read by a learner running the lab on THEIR machine. Any path
or port from the machine where the module was authored is wrong for them.

**Forbidden in module text:**
- authoring sandbox paths (e.g. `/workspace/lab/agents/<name>/...`)
- internal plan or session paths (`/workspace/.mavis/plans/...`)
- helper scripts the learner does not have (`agentlab.sh`) — note that `lab/scripts/bao-lab.sh` **does** ship, so it is fine to name
- scratch files (`/tmp/m3env.sh`, `/tmp/ids.txt`)
- the scratch instance's port, when the learner's lab uses a different one

**Correct values for a learner running the repo's lab:**
- port `8200` (the default)
- config `lab/config/openbao.hcl`, run from inside `lab/` so relative
  paths like `./data` and `./logs/audit.log` resolve
- in Docker: `/openbao/file` (storage) and `/openbao/logs/audit.log`

A port that differs in a *captured transcript* is fine (it is real captured
output) — but say so in one line so the reader knows theirs will differ.

**Before finishing a module, run:**
```bash
grep -nE "\.mavis|/workspace/lab|agents/[a-z0-9]+/|agentlab\.sh|/tmp/[a-z0-9]+" \
  modules/<module>/README.md
```
It must return nothing.

---

## 14. How to verify anything yourself

```bash
export BAO_ADDR=http://127.0.0.1:<your-port>
export BAO_TOKEN=$(cat <your-dir>/root-token)
$BAO_BIN status
$BAO_BIN plugin list
$BAO_BIN secrets list
$BAO_BIN auth list
$BAO_BIN read sys/mounts -format=json
$BAO_BIN read sys/config/state/sanitized
```

**Never state a command's output in the course unless you ran it.** If you
are unsure, run it. An unverified output block is worse than no output block.
