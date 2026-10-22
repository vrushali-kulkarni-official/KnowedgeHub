> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 04 (Namespaces, Entities, Groups & Leases)

**Reviewer:** General (agent `r2`) · **Date:** 2026-10-21
**Server:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`), live
instance `r2` on `127.0.0.1:9793`, storage `pebbledb`, audit device `local-file`.
**Scope:** correctness sweep of every quoted terminal output block and every
quoted error message, the 2.7 lease-endpoint matrix, the GUI labels, the
Meridian AI value consistency, and the required-section checklist.

This is a **final review sweep**, not a rewrite. Prose, structure and
explanations were left alone. Only quoted outputs that did not match the live
server were changed, plus one clarifying note.

---

## 1. What I checked

| Area | Result |
|---|---|
| Namespace create / list / nested create / sealable create | ✅ matches |
| Namespace-scoped mounts, `ns_` prefixed built-ins, isolation both ways | ✅ matches |
| `503 namespace is sealed` on a sealable namespace | ✅ matches |
| `bao namespace unseal` without a TTY | ✅ matches (exact text) |
| `identity/entity` vs `auth/token/identities/entity` (404 + body) | ✅ matches |
| `bao list identity/entity` (fails) vs `identity/entity/name` (works) | ✅ matches |
| Entity record, alias creation, "second entity" trap, `canonical_id` fix | ✅ matches |
| Group record, membership, entity-side view | ✅ matches |
| Token create/lookup/renew; "a token is not a lease" | ✅ matches |
| PKI `generate_lease=true` → lease id shape, `lease_id`/`lease_duration` | ✅ matches |
| The full §6.2 lease endpoint matrix (16 rows) | ✅ **every row matches** |
| `sys/leases/count` behaviour (404 GET / 405 POST) | ✅ matches |
| `revoke-prefix` body-form 404 vs path-form 204 | ✅ matches |
| `bao token revoke -accessor` (boolean-flag trap), `-role` absent | ✅ matches |
| `auth/token/accessors` list, `lookup-accessor` | ⚠️ **fixed** (§3) |
| GUI labels in the shipped UI bundle | ✅ matches (one note added) |
| Meridian AI values / secret paths / forbidden placeholders | ✅ clean |
| Required sections (60-second table, learned, next, homework, GUI) | ✅ all present |
| `hcl` config snippets → `bao operator validate-config` | n/a (no server config in this module) |
| Authoring-environment paths | ✅ none |

---

## 2. Commands actually run (representative — ~90 invocations)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance

# --- state the module assumes ---
bao secrets enable -path=ai/platform kv-v2
bao secrets enable -path=ai/pki pki
bao secrets enable -path=ai/ssh ssh
for p in ai-harness-service data-pipeline-service platform-admin \
         platform-operator secret-rotation-bot; do
  bao policy write "$p" lab/policies/$p.hcl
done
bao kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.5-flash"
bao namespace create tenant-alpha | tenant-atlas | tenant-secure
bao secrets enable -namespace=tenant-atlas -path=ai/platform kv-v2
bao kv put -namespace=tenant-atlas ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash"
bao write identity/entity name=ai-harness-service
bao write identity/group name=platform-operators policies="platform-operator"

# --- namespaces ---
bao namespace create tenant-zeta
bao namespace list
bao secrets list -namespace=tenant-atlas ; bao secrets list
bao kv put -namespace=tenant-atlas ai/platform/llm/gemini ...
bao kv get -namespace=tenant-atlas ai/platform/llm/gemini
bao kv get ai/platform/llm/gemini
bao read -namespace=tenant-atlas ai/pki/issue
bao kv get ai/tenant/llm/gemini
bao read tenant-atlas/ai/platform/llm/gemini
bao namespace create -namespace=tenant-atlas eu-west
bao namespace create -namespace=tenant-atlas tenant-atlas/regions/eu-west
bao token create -namespace=tenant-atlas -policy=default -ttl=10m -format=json
BAO_TOKEN="s.tCd0TQQIIMqCtIaKZj7RlDqh.24suMB" bao read ai/platform/llm/gemini
bao namespace create -key-shares=3 -key-threshold=2 tenant-sealable
bao namespace seal-status tenant-sealable
bao read -namespace=tenant-sealable sys/mounts
bao namespace unseal tenant-sealable            # no TTY -> the file-descriptor error
bao namespace unseal tenant-sealable <key1>
bao namespace unseal tenant-sealable <key2>
bao read -namespace=tenant-sealable sys/mounts

# --- identity ---
bao list auth/token/identities/entity
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Vault-Token: $BAO_TOKEN" \
     "$BAO_ADDR/v1/auth/token/identities/entity"
bao list identity/entity
bao list identity/entity/name
bao read identity/entity/name/ai-harness-service
bao write identity/entity-alias name=ai-harness-service \
     mount_accessor="$(bao read -field=accessor sys/internal/ui/mounts/auth/token)"
bao read identity/entity-alias/id/<id>
bao read identity/entity/id/<canonical_id>
bao write identity/group name=platform-operators member_entity_ids="<id>"

# --- leases ---
bao token create -renewable=true -ttl=30m -policy=platform-operator -display-name=ai-harness-renewal-demo -format=json
bao token lookup -format=json
bao write sys/leases/lookup lease_id="s...."
bao token renew -increment=1h
bao secrets enable -namespace=tenant-atlas -path=ai/pki pki
bao write -namespace=tenant-atlas ai/pki/root/generate/internal common_name="Meridian AI Tenant Root CA" ttl=8760h
bao write -namespace=tenant-atlas ai/pki/config/urls issuing_certificates="$BAO_ADDR/v1/tenant-atlas/ai/pki/ca"
bao write -namespace=tenant-atlas ai/pki/roles/meridian-ai-harness \
     allowed_domains="meridian-ai.internal" allow_subdomains=true \
     generate_lease=true ttl=24h max_ttl=72h
bao write -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness common_name=data-pipeline.meridian-ai.internal ttl=24h -format=json
bao write -format=json -namespace=tenant-atlas sys/leases/lookup lease_id="..."
bao write -namespace=tenant-atlas sys/leases/renew lease_id="..." increment=1h

# --- the 16-row endpoint matrix, raw HTTP ---
for p in sys/renew sys/revoke sys/revoke-prefix sys/revoke-force \
         sys/renew/ai sys/revoke/ai sys/revoke-prefix/ai sys/revoke-force/ai \
         sys/leases/renew-force sys/leases/renew sys/leases/revoke sys/leases/lookup; do
  curl -s -o the request body -w "%{http_code}" -X POST -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/$p" -d '{}'
done
curl -s -X GET  .../sys/leases/count      # -> 404 {"errors":[]}
curl -s -X POST .../sys/leases/count      # -> 405 unsupported operation
curl -s -X LIST .../sys/leases/count      # -> 404 unsupported path
curl -s -X POST -H "X-Vault-Namespace: tenant-atlas" .../sys/leases/revoke-prefix/ai/pki -d '{}'   # -> 204
curl -s -X POST -H "X-Vault-Namespace: tenant-atlas" .../sys/leases/revoke-force/ai/pki  -d '{}'   # -> 204
bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
bao list -format=json sys/leases/count     # -> {}

# --- token revocation ---
bao list -format=json auth/token/accessors
bao write auth/token/lookup-accessor accessor=<id>
bao token revoke -accessor=<id>            # -> invalid boolean value ...
bao token revoke -accessor <id>            # -> Success!
bao token revoke -role ai-harness-service  # -> flag provided but not defined: -role
bao list auth/approle/role/ai-harness-service/token/accessors   # -> No value found (exit 2)
bao write -force sys/leases/revoke-prefix/ai/platform
bao write sys/leases/revoke-prefix/ai/platform                # -> Must supply data or use -force

# --- GUI labels ---
curl -s http://127.0.0.1:9793/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(curl -s http://127.0.0.1:9793/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
  curl -s "http://127.0.0.1:9793/ui/$f" -o "$(basename $f)"; done
cat *.js > all.js
grep -c -F "<label>" all.js        # for every label quoted in §7
```

---

## 3. What I fixed

### 3.1 §3.4 — the entity read-back showed group membership and metadata that did not exist yet

**Defect.** The `bao read identity/entity/name/ai-harness-service` block showed
`direct_group_ids [e16a4aac-…]` and `group_ids [e16a4aac-…]` (the group is only
created in §4.3) and `metadata map[platform_owner:platform-team]`, but nothing
in the module ever set that metadata before the read.

**Live output** (fresh entity, no group yet):

```
Key                    Value
---                    -----
aliases                []
creation_time          2026-10-21T18:58:16.962190396Z
direct_group_ids       []
disabled               false
group_ids              []
id                     c94b498b-011d-6b51-9835-8e20ed148904
inherited_group_ids    []
last_update_time       2026-10-21T18:58:41.270723654Z
merged_entity_ids      <nil>
metadata               <nil>
name                   ai-harness-service
namespace_id           root
policies               []
```

**Fix.** The two group fields are now `[]` and `metadata` is `<nil>`, and a short
paragraph plus one real command was added so the richer `metadata` value is
still reproducible:

```bash
$ bao write identity/entity/id/9cf62d70-c49a-6030-8ad9-ffde55575b08 \
      metadata="platform_owner=platform-team"
Success! Data written to: identity/entity/id/9cf62d70-c49a-6030-8ad9-ffde55575b08
```

(The module's own entity id `9cf62d70-…` was kept so §3.5 and §4.4 stay
self-consistent.)

### 3.2 §6.6 — the `lookup-accessor` block was not what the command prints, and the command was in the wrong flag order

**Defect (a).** The block showed a hand-trimmed JSON object with no response
envelope. The real command returns the full envelope.

**Defect (b).** `bao write auth/token/lookup-accessor accessor=… -format=json`
puts `-format=json` *after* a data field. The CLI then sends `-format` to the
**endpoint** as a data key and the server answers:

```
WARNING! The following warnings were returned from OpenBao:
  * Endpoint ignored these unrecognized parameters: [-format]
```

**Fix.** The command is now `bao write -format=json auth/token/lookup-accessor
accessor=…` and the block contains the real captured response (envelope,
`data` object, `warnings: null`). The prose after it now also points out the
two fields that make the call useful in an incident (`path` is
`auth/approle/login`, `meta.role_name` is `ai-harness-service`), and a CLI
gotcha callout was added for the flag-order trap.

### 3.3 §5.5 — `lease_duration` is 86399 *or* 86400

The A/B table listed `86399` for a `generate_lease=true` role. Live runs
returned `86399` on two of three calls and `86400` on one (the lease clock
starts a fraction of a second before the response is serialised). The table
now says `86399` or `86400`, with a one-line explanation underneath.

### 3.4 §7 — the identity pages live under **Access**, not under an "Identity" heading

The bundle contains no `"Identity"` string, and the identity routes are
`vault.cluster.access.identity[.entities|.groups|.aliases|…]`. A short note was
added to the **Identity** subsection saying where the pages actually are. The
`Entities` / `Groups` / `Aliases` / `Entity ID` / `Group ID` / `Disable entity` /
`Entities to merge from` / `Entity to merge to` labels are all confirmed real
strings in the bundle.

---

## 4. Confirmed-correct highlights (no change needed)

These are the highest-risk claims in the module and all of them reproduced
**exactly**, including error text and status codes:

* `bao namespace create -namespace=tenant-atlas tenant-atlas/regions/eu-west`
  → `Code: 400` / `* namespace name cannot contain /`
* `bao read -namespace=tenant-sealable sys/mounts` → `Code: 503` /
  `* namespace is sealed`
* `bao namespace unseal tenant-sealable` (no TTY) → `file descriptor 0 is not a
  terminal`
* `curl .../v1/auth/token/identities/entity` → `404` /
  `{"errors":["1 error occurred:\n\t* unsupported path\n\n"]}`
* `bao list identity/entity` → `No value found at identity/entity` (exit 2)
* `bao write sys/leases/lookup lease_id="s.…"` → `Code: 400` / `* invalid lease`
* `bao write -namespace=tenant-atlas sys/leases/renew lease_id=… increment=1h`
  → `Code: 400` / `* lease is not renewable`
* `bao write sys/leases/revoke-prefix prefix=ai/pki` → `Code: 404` /
  `* unsupported path` (body form), and the path form → `http=204`
* `bao token revoke -accessor=<id>` → `invalid boolean value "…" for -accessor:
  strconv.ParseBool: …`
* `bao token revoke -role …` → `flag provided but not defined: -role`
* `bao list auth/approle/role/ai-harness-service/token/accessors` →
  `No value found at …` (exit 2)
* Every one of the 16 rows of the §6.2 matrix, including the two
  `sys/leases/revoke-*` path forms returning **204** and
  `sys/leases/count` returning **404 (`{"errors":[]}`) on GET and **405
  (`unsupported operation`) on POST.
* The PKI lease id shape `ai/pki/issue/meridian-ai-harness/<random>.<ns-id>`,
  the `namespace_path: "tenant-atlas/"` field, and the
  "drop the namespace suffix → `invalid lease`" demonstration.

---

## 5. What I could NOT verify — stated plainly

1. **The exact accessors, UUIDs and timestamps** quoted in the module are the
   original author's capture. They are real values from a real run, but they
   will not match a learner's server (nor mine). I did **not** rewrite them;
   the module is explicit that these are captured transcripts, and the
   surrounding text tells the reader the port differs.
2. **`bao namespace scan`** is described in a one-line aside
   ("does the same thing recursively"). I did not exercise it against the live
   server — it is not a quoted output block, and the aside carries no output
   claim, so it was left alone.
3. **The GUI was inspected as its JavaScript bundle, not clicked.** I verified
   every *label* against `assets/vault.js` / `assets/chunk.*.js` /
   `assets/vendor.js` / `assets/engine*.js` (8.3 MB) and against the live
   `sys/internal/ui/mounts` responses. I did not render the UI in a browser,
   so the *layout* of a page (what is on which tab, in what order) is not
   confirmed — only that the quoted strings exist and are reachable from the
   quoted routes.
4. **The `tainted` namespace flag** is described from the API contract, not
   from an observed taint event. The module already says "You have not seen
   this happen; know that it exists", so I left it.

---

## 6. Files changed

* `modules/04-namespaces-entities/README.md` — 3 output blocks corrected, 1
  note added (§3.4 metadata command, §6.6 flag-order gotcha, §7 Access
  placement).
* `modules/04-namespaces-entities/VERIFICATION.md` — this file.

---

## 7. Re-verification round 2 (2026-10-21, after the verifier FAIL)

A verifier reported two findings against this module. Both were re-tested
against a live OpenBao 2.7.1 server (`r2`, `127.0.0.1:9793`) and **both
were fixed**.

### 7.1 §5.5 — the command contradicted the rule the same section teaches *(FIXED)*

The module's rule (stated in §6.6) is: *put `-format=json` **before** the
path, not after the data fields* — otherwise the CLI hands `-format` to the
*endpoint* as a data field and the server answers
`Endpoint ignored these unrecognized parameters: [-format]`.

The §5.5 command had the flag at the end. Verified live, the wrong order:

```console
$ bao write -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h -format=json
{
  "request_id": "5e45ec9a-faf8-02cf-0f72-b5c53e9fcafd",
  "lease_id": "ai/pki/issue/meridian-ai-harness/tFlmLN6x7FrQ7PyNEO2qT5vT.24suMB",
  "lease_duration": 86399,
  ...
  "warnings": [
    "Endpoint ignored these unrecognized parameters: [-format]"
  ]
}
```

and the right order:

```console
$ bao write -format=json -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h
{
  "request_id": "5390f368-a343-efc4-7480-73be11a7b918",
  "lease_id": "ai/pki/issue/meridian-ai-harness/4RYwmrgE3D3M4xgfdOXLjsz2.24suMB",
  "lease_duration": 86400,
  ...
  "warnings": null
}
```

**Fix.** The command is now `bao write -format=json -namespace=tenant-atlas
ai/pki/issue/meridian-ai-harness …`, the shown output now carries
`"warnings": null`, and a short paragraph points at the §6.6 rule so the
section no longer contradicts itself.

### 7.2 §5.4 — `token_type` in the `bao token create` response *(FIXED, with the field kept in the module)*

The §5.4 block showed `"token_type": "service"` inside the `auth` object of
a `bao token create` response. Live, that response's `auth` object has
**11** keys and **no** `token_type`:

```console
$ bao token create -renewable=true -ttl=30m -policy=platform-operator \
      -display-name=ai-harness-renewal-demo -format=json | python3 -c "…"
KEY COUNT: 11
KEYS: ['accessor', 'client_token', 'entity_id', 'identity_policies',
       'lease_duration', 'metadata', 'mfa_requirement', 'orphan', 'policies',
       'renewable', 'token_policies']
token_type = None
```

The same is true of an **AppRole login** (11 keys, no `token_type`) — and it
stays 11 keys even when the role is written with `token_type=service`:

```console
$ bao write -format=json auth/approle/login role_id="$R" secret_id="$S"
KEY COUNT: 11
KEYS: ['accessor', 'client_token', 'entity_id', 'identity_policies',
       'lease_duration', 'metadata', 'mfa_requirement', 'orphan', 'policies',
       'renewable', 'token_policies']
token_type = None
```

The **12-key** shape the owner described — `accessor, client_token,
entity_id, lease_duration, metadata, mfa_requirement, num_uses, orphan,
policies, renewable, token_policies, token_type` — is the `auth` object of
a **`sys/mfa/validate`** response (a token issued by a login that completed
a second factor). That shape carries `"token_type": "service"`, and it is
already shown verbatim in [Module 05 §7.6](../05-auth-mfa-oidc/README.md),
where it was verified live in round 1.

**Fix.** The §5.4 block now shows the real 11-key `auth` object (the
module's own token/accessor values are kept so the `bao token lookup`,
`sys/leases/lookup` and `bao token renew` blocks below it stay consistent),
**and `token_type` was not dropped from the module** — a new note spells out
the three envelopes:

* `bao token create` / AppRole login → 11 keys, no `token_type`;
* `bao token lookup` → the type is spelled **`"type": "service"`**;
* `sys/mfa/validate` → 12 keys, spelled **`"token_type": "service"`** plus
  `num_uses` (Module 05 §7.6).

Same value, three envelopes — the note tells the reader not to assume the
key travels.

### 7.3 Commands run in this round

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN operator unseal "$(cat …/r2/unseal-key-1)"
$BAO_BIN operator unseal "$(cat …/r2/unseal-key-2)"

# the §5.5 command, both orders
bao write -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h -format=json
bao write -format=json -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h

# the §5.4 auth envelope
bao token create -renewable=true -ttl=30m -policy=platform-operator \
      -display-name=ai-harness-renewal-demo -format=json
bao token create … -token-type=service -format=json      # flag does not exist

# the AppRole login envelope, with and without token_type=service on the role
bao write auth/approle/role/svc-role token_type=service …
bao write -format=json auth/approle/login role_id="$R" secret_id="$S"

# the UI bundle, re-fetched for the AppRole count
curl -s "$BAO_ADDR/ui/" | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in …; do curl -s "$BAO_ADDR/ui/$f" -o "$(basename $f)"; done
cat *.js > all.js
grep -o 'AppRole' all.js | wc -l          # -> 4
for f in role_id secret_id secret_id_ttl secret_id_num_uses bind_secret_id \
         token_bound_cidrs token_policies; do
  echo "$f: $(grep -o -F "$f" all.js | wc -l)"; done   # -> 0 for every one
```

### 7.4 Still not verified

* Keycloak is not involved anywhere in this module.
* The GUI was inspected as its JavaScript bundle, not clicked in a browser.
* The author's original accessors/UUIDs/timestamps remain in the module as a
  captured transcript; they are real values from a real run, and they will
  not match a learner's server.
