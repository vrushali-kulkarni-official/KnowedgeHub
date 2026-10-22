# Troubleshooting runbook

> **Every error string in this file was reproduced against a live OpenBao
> 2.7.1 server.** Nothing here is copied from a tutorial or from another
> version. Where a message could not be reproduced in the lab, it is marked
> **NOT REPRODUCED** rather than guessed.
>
> Reproduced against OpenBao **2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`),
> `bao` CLI and `pebbledb` storage. The lab ships at `lab/`; the commands below
> assume `BAO_ADDR` and `BAO_TOKEN` are exported (see `lab/scripts/bao-lab.sh`
> and `use_lab_token`).
>
> Search with `⌘F` / `grep` — the first line of each entry is the exact text
> you will see in your terminal.

---

## Contents

| # | Symptom | Error / status |
|---|---|---|
| 1 | KV v2 write is rejected | `check-and-set parameter required for this call` |
| 2 | KV v2 write is rejected | `check-and-set parameter did not match the current version` |
| 3 | Reading a KV v2 secret returns a warning and nothing | `Invalid path for a versioned K/V secrets engine` |
| 4 | Path looks doubled up | `No value found at ai/platform/data/llm/gemini/data` |
| 5 | A flag is ignored | `Command flags must be provided before positional arguments` |
| 6 | A flag is rejected | `flag provided but not defined: -token` |
| 7 | A JSON flag is ignored, `lease_id` is empty | `Endpoint ignored these unrecognized parameters: [-format]` |
| 8 | Nothing is returned for a path you know exists | `no handler for route "…"` |
| 9 | A lease endpoint 404s | `sys/renew`, `sys/revoke*` removed in 2.7 |
| 10 | List is denied | `permission denied` / `preflight capability check returned 403` |
| 11 | The server answers 503 | `Vault is sealed` |
| 12 | The server will not start | `failed to open database: resource temporarily unavailable` |
| 13 | An audit device will not register | `cannot enable audit device via API` |
| 14 | MFA enforcement will not save | `One of auth_method_accessors, … must be specified` |
| 15 | A TOTP method update is rejected | `issuer must be set` |
| 16 | TOTP enrollment fails | `missing entityID` |
| 17 | The app stopped authenticating | `403 permission denied` on `auth/approle/login` |

---

## 1. `check-and-set parameter required for this call`

```
Error writing data to ai/platform/data/llm/gemini: Error making API request.

URL: PUT http://127.0.0.1:8200/v1/ai/platform/data/llm/gemini
Code: 400. Errors:

* check-and-set parameter required for this call
```

**Cause.** The KV v2 mount at `ai/platform` has `cas_required = true`. Every
write must carry the version the client believes is current. Without it the
server refuses, because it cannot tell whether your write is based on stale
data.

**Fix.** Read the current version and pass it:

```bash
bao kv metadata get -format=json ai/platform/llm/gemini | jq -r .data.current_version
# -> 2

bao kv put -cas=2 ai/platform/llm/gemini api_key="$GEMINI_KEY"
```

**If you are writing in a loop**, use `cas_required = false` on the mount
instead — but understand what you are giving up: two writers can now silently
overwrite each other. See Module 02, §6.

---

## 2. `check-and-set parameter did not match the current version`

```
Error writing data to ai/platform/data/llm/gemini: Error making API request.

URL: PUT http://127.0.0.1:8200/v1/ai/platform/data/llm/gemini
Code: 400. Errors:

* check-and-set parameter did not match the current version
```

**Cause.** Same mount as §1, but the version you supplied is stale — someone
else (usually your own rotation bot) wrote between your read and your write.

**Fix.** Re-read the version and retry. In a script, loop on this error:

```bash
for attempt in 1 2 3; do
  version=$(bao kv metadata get -format=json ai/platform/llm/gemini | jq -r .data.current_version)
  if bao kv put -cas="$version" ai/platform/llm/gemini api_key="$NEW_KEY"; then
    break
  fi
  echo "CAS conflict on attempt $attempt — retrying" >&2
done
```

**Do not** "fix" this with `-cas=0`. `-cas=0` is a literal version number, not
a wildcard — it fails with this exact error whenever the current version is
not `0`. Module 09 §10.4 shows the correct pattern for a rotation job.

---

## 3. `Invalid path for a versioned K/V secrets engine`

```
WARNING! The following warnings were returned from OpenBao:

  * Invalid path for a versioned K/V secrets engine. See the API docs for the
  appropriate API endpoints to use. If using the OpenBao CLI, use 'bao kv get'
  for this operation.
```

**Cause.** You used the KV v1 read path (`bao read <mount>/<key>`) against a KV
**v2** mount. In KV v2 the secret lives one level deeper, under `data/`, and
the metadata lives under `metadata/`. The v1 path resolves to a *real* route
(the metadata path), so the server does not 404 — it warns and returns
nothing. That silence is what makes this error annoying.

**Fix.** Use the version-aware CLI commands:

```bash
bao kv get ai/platform/llm/gemini          # reads data/ for you
bao kv metadata get ai/platform/llm/gemini  # reads metadata/
```

**How to tell which mount is which.** `kv` is v1, `kv-v2` is v2, and the mount
list tells you the truth:

```bash
bao list sys/mounts
```

---

## 4. `No value found at ai/platform/data/llm/gemini/data`

```
No value found at ai/platform/data/llm/gemini/data
```

**Cause.** You added `data/` to a path that already had it. `bao kv get`
already appends `data/` for you, so `bao kv get ai/platform/llm/gemini/data`
looks for `ai/platform/data/llm/gemini/data`.

**Fix.** Drop the extra `data/`:

```bash
bao kv get ai/platform/llm/gemini
```

The rule: **with `bao kv …` commands, write the path as it appears in the
GUI** — `ai/platform/llm/gemini`. The `data/` and `metadata/` layers are the
CLI's business, not yours.

---

## 5. `Command flags must be provided before positional arguments`

```
Command flags must be provided before positional arguments. The following arguments will not be parsed as flags: [-version=2]
Too many arguments (expected 1, got 2)
```

**Cause.** You put the flag after the path:

```bash
bao kv get ai/platform/llm/gemini -version=2     # wrong
```

The CLI parses everything after the first positional argument as data, not
flags, so `-version=2` is treated as a second path and the command fails with
*both* messages.

**Fix.** Flags first, path last:

```bash
bao kv get -version=2 ai/platform/llm/gemini     # right
```

**Why this is worth knowing.** The failure is not always loud. With a *known*
global flag such as `-format=json` the CLI consumes it and you get only the
second, quieter message:

```
Too many arguments (expected 1, got 2)
```

…which tells you nothing about the cause. Put flags before the path and the
whole class of problem disappears. This matters most for `bao write`, where
an unparsed flag is silently sent to the server as a data field — see §7.

---

## 6. `flag provided but not defined: -token`

```
flag provided but not defined: -token
```

**Cause.** The flag does not exist on that command. The usual reason is a
**Vault-era habit**: in Vault you look a token up with `-token`, but in
OpenBao 2.7.1 the CLI has no `-token` flag at all.

**Fix.** The current token is implicit — the CLI reads `BAO_TOKEN` from the
environment:

```bash
bao token lookup
```

To look up a *different* token, pass it in the environment for that one
command:

```bash
BAO_TOKEN=s.someOtherToken bao token lookup
```

To look a token up by its accessor instead of its value:

```bash
bao write auth/token/lookup-accessor accessor=<accessor>
```

---

## 7. `Endpoint ignored these unrecognized parameters: [-format]`

```
{
  "request_id": "…",
  "lease_id": "",
  "warnings": [
    "Endpoint ignored these unrecognized parameters: [-format]"
  ],
  …
}
```

**Cause.** You put `-format=json` *after* the data fields in a `bao write`:

```bash
bao write -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h -format=json   # wrong
```

`bao write` forwards unrecognised trailing arguments to the **server** as
data fields. The server does not know a field called `-format`, so it warns
and ignores it — and because you asked for JSON, the response you get is
whatever the CLI's default format is. The empty `lease_id` in the same
response is the tell-tale that you are reading the wrong payload.

**Fix.** Put `-format=json` before the path:

```bash
bao write -format=json -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h
```

You then get `"warnings": null` and a populated `lease_id`. Module 04 §5.5
demonstrates both orderings side by side.

---

## 8. `no handler for route "…"`

```
HTTP/1.1 404 Not Found
{"errors":["no handler for route \"nonexistent/deep/path\". route entry not found."]}
```

**Cause.** The path does not exist. In 2.7.1 a request to an unknown route
returns this exact text — note that it is **not** "no route for …" as in
Vault, so a tutorial quoting the Vault string will not match.

**Fix.** Check the route exists in the API you are on. The authoritative list
is the spec the server itself serves:

```bash
curl -s -H "X-Vault-Token: $BAO_TOKEN" \
  "$BAO_ADDR/v1/sys/internal/specs/openapi" | jq -r '.paths | keys[]' | grep mfa
```

> **Note the header.** Without `X-Vault-Token` the same URL returns a
> well-formed but **empty** spec (`"paths":{}`) — a silent trap. Always send
> the token.

---

## 9. `sys/renew` and `sys/revoke*` return 404

```
$ curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/sys/renew"
404
```

**Cause.** These Vault-era endpoints were **removed in 2.7.0**. All four are
gone:

| Removed (Vault) | Use instead (OpenBao 2.7.1) |
|---|---|
| `sys/renew` | `sys/leases/renew` |
| `sys/renew/<lease_id>` | `sys/leases/renew/<lease_id>` |
| `sys/revoke` | `sys/leases/revoke` |
| `sys/revoke/<lease_id>` | `sys/leases/revoke/<lease_id>` |
| `sys/revoke-prefix/<prefix>` | `sys/leases/revoke-prefix/<prefix>` |
| `sys/revoke-force/<prefix>` | `sys/leases/revoke-force/<prefix>` |

**Fix.** Use the `sys/leases/*` family. Module 04 §5 walks the whole lease
lifecycle against the real endpoints.

---

## 10. `permission denied` when listing

There are two different 403s here, and they mean different things.

**Variant A — the path itself is outside your policy:**

```
Error making API request.

URL: GET http://127.0.0.1:8200/v1/sys/internal/ui/mounts/ai/platform/llm
Code: 403. Errors:

* preflight capability check returned 403, please ensure client's policies grant access to path "ai/platform/llm/"
```

The CLI checks the *listing* path before it lists. Your policy grants
`read` on `ai/platform/llm/*` but not `list` on `ai/platform/llm/`, so the
preflight fails.

**Variant B — the policy is fine but the operation is still denied:**

```
Error listing ai/platform/metadata/llm: Error making API request.

URL: GET http://127.0.0.1:8200/v1/ai/platform/metadata/llm?list=true
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

**Cause.** On a KV **v2** mount, `bao kv list` reads the **metadata** layer.
Your policy has to grant `list` on `ai/platform/metadata/llm`, not on
`ai/platform/llm`. A policy that looks right at a glance:

```hcl
path "ai/platform/llm/*" { capabilities = ["read"] }
```

…silently grants no list access at all.

**Fix.** Grant the metadata layer explicitly:

```hcl
path "ai/platform/metadata/llm" {
  capabilities = ["list"]
}
path "ai/platform/data/llm/*" {
  capabilities = ["read"]
}
```

Note the **data** path in the second stanza — the KV v2 data layer is
`ai/platform/data/llm/*`, not `ai/platform/llm/*`. Getting this wrong is the
single most common policy bug in this course; Module 03 §7 works through it
with a live allow/deny matrix.

---

## 11. `Vault is sealed`

```
Error reading secret/foo: Error making API request.

URL: GET http://127.0.0.1:9701/v1/secret/foo
Code: 503. Errors:

* Vault is sealed
```

**Cause.** The server is running but its storage is locked. This is the
normal state after a restart, and the state of a brand-new server before
`bao operator init`.

**Fix.** Unseal with the key shares:

```bash
bao operator unseal <share-1>
bao operator unseal <share-2>
bao operator unseal <share-3>
```

`bao status` tells you how far along you are:

```
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/3
Unseal Nonce       n/a
```

> **`Total Shares` / `Threshold` vs `t` / `n`.** The `bao status` **table**
> prints `Total Shares` and `Threshold`. The `sys/seal-status` **API**
> returns `t` and `n`. They are the same numbers under different names — do
> not write a script that reads `threshold` from the JSON API.

**If `Initialized` is `false`**, the server has never been initialised and
there is nothing to unseal — run `bao operator init` first.

---

## 12. `failed to open database: resource temporarily unavailable`

```
error initializing storage of type pebbledb: failed to open database: resource temporarily unavailable
```

**Cause.** Two OpenBao processes are trying to open the same `pebbledb`
directory. The first one holds an exclusive lock on the database; the second
cannot get it. You get this by accident when you start a second server
against the same data directory — or intentionally, when you want to prove
that a data directory cannot be opened twice.

**Fix.** Each server needs its own data directory. Give the second instance a
different path:

```hcl
storage "pebbledb" {
  path = "/openbao/data-second"
}
```

**If you thought you killed the old server**, check first. `pkill -f "bao
server"` is a trap: the pattern matches your own shell's command line, so it
kills the shell too. Find the PID first and kill that one:

```bash
pgrep -f "bao server -config=…" | grep -v "^$$\$" | xargs -r kill
```

---

## 13. `cannot enable audit device via API`

```
Error enabling audit device: Error making API request.

URL: PUT http://127.0.0.1:9797/v1/sys/audit/file
Code: 400. Errors:

* cannot enable audit device via API; use declarative, config-based audit device management instead
```

**Cause.** **Audit devices cannot be created via the API in 2.7.0 and later.**
This is a deliberate security change, not a bug: an operator who can add an
audit device at runtime can also *replace* the one that records their
actions.

**Fix.** Declare the device in the server configuration file and restart:

```hcl
audit "file" "local-file" {
  description = "Audit log"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"
  }
}
```

Then confirm it registered:

```bash
bao audit list
```

```
Path           Type    Description
----           ----    -----------
local-file/    file    Audit log
```

**Two gotchas in the same stanza:**

* The label must be unique. Two `audit "file"` blocks with **different**
  labels are fine; two with the **same** label make the server refuse to
  start.
* `file_path` belongs in `options`. Writing `file_path` as a sibling of
  `options` produces a warning and the path is **ignored** — the device
  registers but writes nowhere.

Module 09 §4.1 covers the declarative rule, and the lab ships a working
configuration in `lab/config/openbao.hcl`.

---

## 14. `One of auth_method_accessors, auth_method_types, identity_group_ids, identity_entity_ids must be specified`

```
Error writing data to identity/mfa/login-enforcement/ai-harness-entity: Error making API request.

URL: PUT http://127.0.0.1:9797/v1/identity/mfa/login-enforcement/ai-harness-entity
Code: 400. Errors:

* One of auth_method_accessors, auth_method_types, identity_group_ids, identity_entity_ids must be specified
```

**Cause.** You created an MFA enforcement with only `mfa_method_ids`. An
enforcement says *who* must present the MFA method, so it needs at least one
**scope** as well: an entity, a group, an auth method type, or an auth method
accessor.

**Fix.**

```bash
bao write identity/mfa/login-enforcement/ai-harness-entity \
    mfa_method_ids="$METHOD_ID" \
    identity_entity_ids="$ENTITY_ID"
```

**Related trap, same section of the API.** `mfa_require=true` on an auth
method role is **silently ignored** in 2.7.1 — it is not an error, it simply
does nothing. Enforcement is the only mechanism that works. Module 05 §7.4
demonstrates the silent no-op and §7.5 shows the mechanism that replaced it.

---

## 15. `issuer must be set`

```
{"errors":["issuer must be set"]}
```

**Cause.** You POSTed an empty body to a TOTP method's **update** endpoint:

```bash
curl -s -X POST -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
    -d '{}' "$BAO_ADDR/v1/identity/mfa/method/totp/$METHOD_ID"
```

**Fix.** The update endpoint **rewrites** the method, and fields you leave
out are reset to their defaults. Always send the complete method body:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
    -d '{"method_name":"aisha.rahman","issuer":"meridian-ai"}' \
    "$BAO_ADDR/v1/identity/mfa/method/totp/$METHOD_ID"
# -> 204
```

Note the `204` with an **empty body**. A successful update prints nothing —
that is normal, not a failure.

---

## 16. `missing entityID`

```
{
  "errors": [
    "missing entityID"
  ]
}
```

**Cause.** You called a self-service TOTP enrollment endpoint with a token
that has **no entity** attached — which includes the root token:

```bash
bao write identity/mfa/method/totp/generate method_id="$METHOD_ID"
```

**Fix.** Use the **admin** variant and pass the entity explicitly:

```bash
bao write identity/mfa/method/totp/admin-generate \
    entity_id="$ENTITY_ID" \
    method_id="$METHOD_ID"
```

The TOTP secret is attached to the entity you name here. Point it at the same
entity your login-enforcement names, or the validation later fails with
`MFA secret for method name "…" not present in entity "…"`.

Module 05 §7.3 runs this end to end.

---

## 17. The app stopped authenticating: `403 permission denied` on login

```
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:8200/v1/auth/approle/login
Code: 403. Errors:

* permission denied
```

Or, once the credential has expired outright:

```
Code: 400. Errors:

* invalid role or secret ID
```

**Cause.** The AppRole `secret_id` expired. The lab's AI-harness role has
`secret_id_ttl=1h` **on purpose** — the credential a workload uses to fetch a
token is meant to be short-lived and rotated by whatever delivers it. The copy
you saved when you ran `setup-platform.sh` went stale.

This is not a policy problem, and it is not a broken mount. Check it:

```bash
bao read -format=json auth/approle/role/ai-harness-service | jq '.data | {secret_id_ttl, secret_id_num_uses}'
```

**Fix.** Mint a new one — the script also **verifies it logs in** before you
point anything at it:

```bash
./scripts/refresh-credentials.sh
export BAO_SECRET_ID=$(cat lab/secrets/ai-harness-secret-id)
```

`role_id` does **not** change: it identifies the role and is stable for the
life of the role. Only the `secret_id` rotates.

> **Production:** *this is the design working, not a failure. Whatever
> delivers the `secret_id` to the workload — a deployment pipeline, a
> sidecar, a secrets broker — mints a fresh one on a schedule and hands it
> over out of band. If your app has been running for an hour and suddenly
> cannot log in, the fix is a rotation mechanism, not a longer TTL.*

---

## Still stuck?

Three places, in this order:

1. **`docs/VERIFIED-FACTS.md`** — the behaviours of 2.7.1 that differ from
   older documentation. If your tutorial and this course disagree, this file
   is right and the tutorial is wrong.
2. **The module's `VERIFICATION.md`** — each module ships one recording what
   was checked against a live server and what could **not** be verified.
3. **Reproduce it, then read the raw API.** The CLI rewrites errors. The
   server's own words are in the JSON:

   ```bash
   curl -s -i -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/<path>" | head -20
   ```
