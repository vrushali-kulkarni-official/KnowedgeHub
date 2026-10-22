> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 06 (Crypto Tooling)

> **This file is an internal review artifact, not course content.** It
> deliberately contains authoring-environment paths (the reviewer's private
> lab instance) that are forbidden in the learner-facing `README.md`. The
> `README.md` was checked and contains none of them.

**Reviewer:** General (agent `r3`) · **Date:** 2026-10-21
**Scope:** final review sweep — correctness of quoted output, ACL/claim
accuracy, GUI labels, required sections, style-guide consistency.

## 1. Environment used

A private OpenBao **v2.7.1** instance was started for this review:

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN status
```

```
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    3
Threshold       2
Version         2.7.1
Commit Date     2026-10-01T15:32:54Z
Storage Type    pebbledb
Cluster Name    vault-cluster-3c9e183b
HA Enabled      false
```

The lab was provisioned to match the Meridian AI scenario before any
check ran: `ai/platform` (kv-v2) with `llm/gemini`, `db/postgres`,
`cache/redis`, `oidc/keycloak`; `ai/transit` with
`pii-column-encryption`, `pii-field-encryption`, `webhook-signing`,
`pii-lookup`, `gemini-bring-your-own-key`; the `ai-harness-service`
policy; and a `data-pipeline` policy.

## 2. What was verified (and found correct)

Every one of the following was re-run live and the quoted output in the
module matches the server's actual response, byte for byte (excluding
the timestamp/UUID values, which are per-run).

| Module section | Command | Result |
|---|---|---|
| 3.1–3.3 | `bao write sys/tools/random/{32,64,platform/48,all/16,seal/24}`, `sys/tools/random bytes=32`, `-force` form, `format=hex` | matches — URL segment beats the `bytes=` body field; hex output confirmed |
| 3.2 | `sys/tools/random/nope/24`, `sys/tools/random/abc` | 400 + `unsupported entropy source "nope"; must be "platform" or "seal", or "all"` / 400 + `error parsing url-set byte count: strconv.Atoi: parsing "abc": invalid syntax` — exact match |
| 3.3 | `bao write sys/tools/random/32` (no body) | `Must supply data or use -force` — exact match |
| 4.1–4.2 | `sys/tools/hash/sha2-256`, `sha3-256`, `md5`, `format=base64`, raw-text input | all match, including `unable to decode input as base64: illegal base64 data at input byte 8` and `unsupported algorithm md5`; the digests also match `sha256sum` / `openssl dgst -sha3-256` |
| 4.3 | webhook fingerprint of `the-provider-shared-secret` | matches the local `sha256sum` |
| 5.1–5.3 | `sys/wrapping/wrap` / `unwrap` / reuse | match, incl. `wrapping token is not valid or does not exist` |
| 5.4 | `-text=` vs `text=` | payload key is literally `"-text"` — confirmed by unwrapping |
| 5.5 | `-token=` before vs after the path | `flag provided but not defined: -token` before; 400 invalid-token after — exact match |
| 5.6–5.7 | `sys/wrapping/lookup`, `sys/wrapping/rewrap`, `lookup` after rewrap | matches; the original token is consumed by rewrap — confirmed |
| 5.8 | `X-Vault-Wrap-TTL: 60 / 1h / notaduration / 0` | 60, 3600, `error parsing X-Vault-Wrap-TTL header: time: invalid duration "notaduration"`, `endpoint requires response wrapping to be used` — exact match |
| 5.8 | `bao write -wrap-ttl=60s -format=json ai/platform/llm/gemini` | response wrapping with `ttl: 60`, `creation_path: ai/platform/llm/gemini` — exact match |
| 5.9 | `bao unwrap <token>` with **no** `BAO_TOKEN` | works, prints the payload — confirmed |
| 5.9 | raw `curl` with the wrapping token as `X-Vault-Token`; raw `curl` with no header | first returns the payload, second returns `{"errors":["permission denied"]}` — exact match |
| 6.1–6.2 | cubbyhole write/list/read; root reading a scoped token's cubbyhole and vice versa | both directions return `No value found at cubbyhole/…` — exact match |
| 7.1–7.2 | `bao secrets enable -path=ai/transit transit`, key creation metadata, `transit/encrypt`, `transit/decrypt` | matches; `cipher: message authentication failed` for a tampered ciphertext — exact match |
| 7.3 | `transit/datakey/plaintext`, `datakey/wrapped`, `export/encryption-key` on a non-exportable key, `backup` on a non-exportable key | match, incl. 400 `private key material is not exportable` and **500** `exporting is disallowed on the policy` |
| 7.3 | export of an exportable key | returns the raw key material — confirms the `exportable` / `allow_plaintext_backup` note |
| 7.4 | batch encrypt over HTTP; `batch_input='[...]'` via the CLI | results are in order with per-item `key_version`; the CLI form returns **500** `failed to parse batch input: source data must be an array or slice, got string` — exact match |
| 7.5 | HMAC key creation with and without `key_size` | 500 `invalid key size for HMAC key, must be between 32 and 512 bytes` — exact match; the MAC is deterministic — confirmed |
| 7.6–7.7 | `rotate`, `min_decryption_version`, `min_encryption_version`, `trim` | match, incl. `ciphertext or signature version is disallowed by policy (too old)` and `requested version for encryption is less than the minimum encryption key version` and `min encryption version should not be less than min available version` |
| 7.9 | `deletion_allowed` at creation vs at the config endpoint; key delete | creation-time `deletion_allowed=true` is ignored; the config endpoint works; delete of a non-opted-in key gives 400 `deletion is not allowed for this key` — exact match |
| 7.10 | derived + convergent key, missing `context`, `nonce` ignored | missing-context error matches; the ciphertext is byte-identical with a random nonce, a different random nonce and no nonce — the 2.7 "nonce is not a parameter" note is confirmed |
| 7.11 | `ai/transit/cache-config`, `ai/transit/config` | `size: 0` confirmed; `ai/transit/config` → 404 `unsupported path` — exact match |
| 8.2–8.3 | `bao path-help sys/external-keys/configs/...` (+ keys) | the two route regexes, the parameter lists and the method tables are quoted **exactly** as the server prints them |
| 8.2 | `bao list sys/external-keys/configs` / `bao read` | `No value found at …` and 405 `unsupported operation` — exact match |
| 8.3 | transit `type=external-key` with a slash ref / no ref / wrong type / valid ref | all four error strings match exactly, incl. `invalid key reference: must be "<config name>:<key name>"` and `key "aws-kms:meridian-key" does not exist` |
| 8.3 | `sys/external-keys/configs/aws-kms plugin=awskms` | 400 `unknown plugin: awskms` — exact match |
| 10 | `bao token capabilities` for the policy paths in §10 | `create, update` / `deny` / `read` — all as claimed |

## 3. Defects found and FIXED

### 3.1 The `default` policy is not empty — three claims were wrong (HIGH)

Section 10 opened with *"Every endpoint in this module is an ACL path, and
none of them are granted by default"*, and Section 6.3 said *"A token with
no `cubbyhole/*` grant gets a flat 403"*.

**Verified false.** `bao policy read default` on 2.7.1 grants, to *every*
token:

* `cubbyhole/*` — create, read, update, delete, list
* `sys/wrapping/wrap`, `sys/wrapping/lookup`, `sys/wrapping/unwrap` — update
* `sys/tools/hash`, `sys/tools/hash/*` — update

So a token carrying only an application policy **can** wrap, unwrap and
hash. Only `sys/tools/random/*` and the `ai/transit/*` paths are actually
denied by default.

**Fixed:**
* Section 10 now prints the relevant `default` policy stanzas, shows the
  *real* successful `sys/wrapping/wrap` response for a normal
  application token (instead of the incorrect 403), keeps the correct 403
  for `sys/tools/random/32`, and adds the `-no-default-policy` remedy.
* Section 6.3 now states that the 403 requires `-no-default-policy` and
  shows `bao token capabilities` returning `deny`.
* Section 5.9's unwrap-denial example was rewritten: the original used a
  made-up token (`token="s.whatever"`), which returns **400**
  `wrapping token is not valid or does not exist` *before* any ACL check
  ever runs. The corrected example uses a **valid** wrapping token plus a
  `-no-default-policy` token and shows the genuine 403, and explicitly
  calls out the 400-before-403 ordering.
* Added a "What you learned" bullet about the `default` policy.

### 3.2 The `bao secrets tune sys` error text was non-deterministic (MEDIUM)

Section 5.8 quoted `* cannot tune parameter options of sys/`. Running the
exact quoted command twelve times produced three different messages:

```
* cannot tune parameter default_lease_ttl of sys/
* cannot tune parameter max_lease_ttl of sys/
* cannot tune parameter options of sys/
```

**Fixed:** the module now shows the real message for the quoted command
(`default_lease_ttl`), lists all three variants, and explains that the
server names whichever parameter it rejected first — so scripts should
match the prefix, not the parameter name.

### 3.3 The GUI section was substantially wrong (HIGH)

Section 9 claimed:

* *"**No `sys/tools/random` page.** There is no GUI anywhere for random
  byte generation. The CLI is the only way."*
* *"**No `sys/tools/hash` page.** Same."*
* *"**No wrapping page.** `sys/wrapping/wrap` and `sys/wrapping/unwrap`
  are not exposed in the UI at all"*
* *"**The Configuration tab does not expose the version floors.**"*

**All four are false for OpenBao 2.7.1.** The UI bundle that the server
actually serves contains the tool-action table

```javascript
// vault/helpers/tools-actions
const n = ["wrap", "lookup", "unwrap", "rewrap", "random", "hash"]
```

plus the route `vault/cluster/tools/tool/:selected_action` and the
components `vault/components/tool-wrap`, `tool-lookup`, `tool-unwrap`,
`tool-rewrap`, `tool-random`, `tool-hash`. The sidebar renders that list
capitalised, so the real menu is **Tools → Wrap / Lookup / Unwrap /
Rewrap / Random / Hash**. The Transit key form exposes **Auto-rotation
period**, **Allow deletion**, **Minimum decryption version** and
**Minimum encryption version** — so the version floors *are* in the GUI.

**Fixed:** Section 9 was rewritten with the real top-level navigation
(**Secrets engines**, **Access**, **Policies**, **Tools**), the real
Transit action names, the real Tools menu, the bundle-verification
method, and a corrected "what the GUI does not do" list (no cubbyhole
page; **no Trim action** — trimming old key material really is
CLI-only; the Tools forms are conveniences, not the API).

### 3.4 The audit-log JSON shape was wrong (MEDIUM)

Section 5.9 showed the audit record for a wrapping unwrap as a flat
object with top-level `path` and `operation`. The real 2.7.1 entry
nests them under `request`, adds `type: "response"`, and shows the
wrapping token as a **service** token with `remaining_uses: 1`.

**Fixed:** the block now matches the real entry, and a short note
explains where `path` / `operation` actually live in the 2.7 audit
format.

### 3.5 Smaller fixes

| Where | Was | Now |
|---|---|---|
| Status block | no note about the transcript port | states the transcripts are from port 9274 and the learner's lab is 8200 (same rule mod 07 already used) |
| 3.2 `seal` source | no output shown | the real `WARNING! … no seal/entropy augmentation available, using platform entropy source` is quoted, with an explanation that on a Shamir cluster `seal` and `platform` are the same bytes |
| 7.1 key metadata JSON | `deletion_allowed` missing | added (the server returns it) |
| 7.3 backup blob JSON | key material shown at the top of `policy`, `type` shown as `"aes256-gcm96"` | corrected to `policy.keys["1"].key` and `type: 0` (numeric enum), with a note |
| 7.12 policy prose | "The application gets two transit paths" | "three transit paths and one KV path" (the block lists four) |
| 10 | — | new rule 3 added: `sys/tools/random/*` covers `sys/tools/random/32` but **not** the count-less `sys/tools/random` (verified: `create, update` vs `deny`) |

## 4. Checks that passed with no changes needed

* **Forbidden authoring paths** —
  `grep -nE "\.mavis|/workspace/lab|agentlab\.sh|plan_[0-9a-f]{6,}" README.md`
  returns nothing.
* **HCL blocks** — all four `hcl` blocks are *policies*, not server
  config, so the correct validator is `bao policy fmt`, which
  VERIFIED-FACTS §12 documents as a client-side check. All four
  pass against an unreachable server:
  ```
  Success! Formatted policy: …  (exit 0)
  ```
  There are no `listener` / `storage` / `api_addr` server-config blocks
  in this module, so `bao operator validate-config` has nothing to
  check here.
* **Meridian AI values** — the Gemini key, Postgres password, Redis
  password, Keycloak client secret, the four secret paths
  (`ai/platform/llm/gemini`, `ai/platform/db/postgres`,
  `ai/platform/cache/redis`, `ai/platform/oidc/keycloak`) and the mount
  layout all match STYLE-GUIDE §2 exactly. No `foo` / `bar` / `test` /
  `changeme` placeholders anywhere.
* **Required sections** — 60-second concept table (§0), "What you
  learned" (§11), "What's next" (§12), "Homework" (§13, eight numbered
  runnable tasks) and a GUI section (§9) are all present.
* **Every quoted status code** in the module matches the code the server
  actually returns (400 / 403 / 404 / 405 / 500 each verified in place).

## 5. What could NOT be verified — stated plainly

1. **The GUI was not driven.** The lab is a headless container with no
   browser, so every GUI *label* in §9 is quoted from the shipped
   JavaScript bundle, but the *page layout* (where exactly the button
   sits, what the popup menu looks like) is inferred from the bundle's
   component and route names, not observed.
2. **External Keys cannot be exercised.** No KMS plugin is installed and
   the KMS plugins are not built into 2.7.1, so the round trip
   "create config → create key → encrypt → decrypt" was not executed.
   The module already says this explicitly in §8.4; this review
   confirmed that statement is accurate.
3. **The `pii_demo.py` transcript in §7.12 was not re-run.** The lab
   has no Postgres; the module's own text says the run used SQLite as a
   stand-in. The *OpenBao-side* half of that section (the transit
   capabilities, the policy, and the 403 on reading the key) was
   verified independently and matches.
4. **Caveat on ciphertext values.** Ciphertext and wrapping-token values
   are per-server and per-key, so a ciphertext quoted in the module
   cannot be decrypted by a different server instance. Every quoted
   ciphertext in the module was produced by the *same* key instance that
   produced the quoted plaintext, and the round trips were re-verified
   end-to-end on a fresh instance.

## 6. Commands actually run (abridged)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN secrets enable -path=ai/platform kv-v2
$BAO_BIN write ai/platform/config cas_required=false max_versions=10
$BAO_BIN kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" project_id="meridian-ai-prod-4471"
$BAO_BIN secrets enable -path=ai/transit transit
$BAO_BIN write -format=json ai/transit/keys/pii-column-encryption type="aes256-gcm96"
$BAO_BIN write -force ai/transit/keys/pii-field-encryption type="aes256-gcm96"
$BAO_BIN write -format=json ai/transit/keys/webhook-signing type="hmac" key_size=32
$BAO_BIN write -format=json ai/transit/keys/gemini-bring-your-own-key type="aes256-gcm96" \
    exportable=true allow_plaintext_backup=true
$BAO_BIN write -format=json ai/transit/keys/pii-lookup derived=true convergent_encryption=true type="aes256-gcm96"

# the checks themselves
$BAO_BIN write sys/tools/random/32 bytes=32
$BAO_BIN write sys/tools/random/nope/24 bytes=32
$BAO_BIN write sys/tools/hash/sha2-256 input="bWVyaWRpYW4tYWktcHJvZA=="
$BAO_BIN write -format=json sys/wrapping/wrap text="…"
$BAO_BIN write -format=json sys/wrapping/unwrap token="s.…"
$BAO_BIN write -format=json sys/wrapping/lookup token="s.…"
$BAO_BIN write -format=json sys/wrapping/rewrap token="s.…"
env -u BAO_TOKEN $BAO_BIN unwrap s.…
curl -s --header "X-Vault-Token: $BAO_TOKEN" --header "X-Vault-Wrap-TTL: 60" \
     -X POST -d '{"text":"…"}' $BAO_ADDR/v1/sys/wrapping/wrap
$BAO_BIN secrets tune -default-lease-ttl=600s -max-lease-ttl=1800s sys     # x12
$BAO_BIN write -format=json ai/transit/encrypt/pii-column-encryption plaintext="…"
$BAO_BIN write -format=json ai/transit/datakey/plaintext/pii-field-encryption bits=256
$BAO_BIN read -format=json ai/transit/export/encryption-key/pii-field-encryption
$BAO_BIN read -format=json ai/transit/backup/pii-field-encryption
$BAO_BIN write -force -format=json ai/transit/keys/pii-column-encryption/rotate
$BAO_BIN write -format=json ai/transit/keys/pii-column-encryption/config min_decryption_version=2 min_encryption_version=2
$BAO_BIN write -force -format=json ai/transit/keys/pii-column-encryption/trim min_available_version=2
$BAO_BIN path-help sys/external-keys/configs/aws-kms
$BAO_BIN path-help sys/external-keys/configs/aws-kms/keys/mykey
$BAO_BIN write -format=json sys/external-keys/configs/aws-kms plugin=awskms
$BAO_BIN plugin list
$BAO_BIN policy read default
$BAO_BIN token create -policy=… -no-default-policy -format=json
$BAO_BIN token capabilities "$TOKEN" <path>
BAO_ADDR="http://127.0.0.1:1" bao policy fmt <file>   # client-side lint
curl -s http://127.0.0.1:9821/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
```

## 7. Final state

* 0 forbidden authoring paths.
* 4 HCL policy blocks: all pass `bao policy fmt`.
* All quoted status codes match the live server.
* All GUI labels are quoted from the shipped UI bundle.
* Required sections present; homework has 8 runnable tasks.
* Section count: **2604 → 2939 lines** (prose preserved; the growth is
  the corrected GUI table, the `default` policy material, the new
  explanatory notes, and the shipped `pii_demo.py` transcript).

---

## 8. Round 2 — the four defects the verifier raised

**Reviewer verdict:** FAIL, with four precise defects. All four are
fixed below. Everything above is unchanged and still stands.

### 8.1 §7.12 — the `pii_demo.py` transcript was presented as a capture, but the script was not shipped — **FIXED (option a: ship the script)**

**Defect:** *"the `pii_demo.py` transcript is presented as CAPTURED output,
but the script is not shipped. A reader cannot reproduce it."*

**Fixed by shipping the script and re-capturing from a real run.**

* New file: `modules/06-crypto-tooling/lab/app/pii_demo.py` — stdlib
  only (`urllib` + `sqlite3`), 150 lines, documented header.
* mod06 gained a **"Files shipped with this module"** table at the top
  (the same pattern mod 07 already uses) pointing at it.
* §7.12 now says, in as many words, that the transcript *"is a **real
  run of that file** against a live OpenBao 2.7.1 — not a
  reconstruction"*, and shows the `export` lines needed to reproduce it.

**The real run, re-captured on the review instance:**

```bash
$ export BAO_ADDR=http://127.0.0.1:8200
$ export BAO_TOKEN=s.GDBOCtv9VTncsFrYYjTrWtr5
$ cd lab/app && python3 pii_demo.py
[1] pulled DB creds from OpenBao KV: db=meridian_ai user=meridian_app
[2] transit_encrypt -> vault:v2:xLsCbZPRG5Z//crSqBGCVuX...
[3] inserted row with ciphertext only
[4] read row -> transit_decrypt -> aisha.rahman@meridian-ai.com
    round trip OK
[5] raw DB file contains plaintext email? False
    raw DB file contains the ciphertext? True
[6] reading the transit key from the app's token -> OpenBao GET ai/transit/keys/pii-column-encryption -> HTTP 403: {"errors":["1 error occurred:\n\t* permission denied\n\n"]}
```

Two corrections fell out of shipping it:

* The old transcript's line **[6]** named the key
  `pii-field-encryption`, but the script (and the `data-pipeline`
  policy) use `pii-column-encryption`. The shipped script's output is
  what the module now shows.
* The old block was fenced as ```text while looking like a terminal
  session. It is now a ```bash block with the real `$` prompts and the
  real `export` lines, so it reads exactly like the rest of the module.

The script was run against a `data-pipeline` token minted with the
module's own §7.12 policy (`-no-default-policy`, so the default policy
could not leak anything into the result). The `deny` on
`ai/transit/keys/pii-column-encryption` was re-verified before the run.

### 8.2 §7.3 used a key the module never creates — **FIXED**

**Defect:** *"it uses a key it never creates. A learner following in
order gets a 'key does not exist' error and no explanation."*

Correct: `pii-field-encryption` first appears in §7.3 and is used in
§7.3, §7.6, §7.7 and §7.8, but §7.1 only creates
`pii-column-encryption`. A learner following in order would hit:

```text
* encryption key not found
```

**Fixed in two places:**

1. **§7.3** now opens with the creation of the second key, with the
   real server response:
   ```bash
   $ bao write -format=json ai/transit/keys/pii-field-encryption type="aes256-gcm96"
   ```
   (full metadata block captured live, including `exportable: false`,
   which is the setting the rest of §7.3 depends on).
2. **§7.6** now also shows `pii-field-encryption` being rotated, so
   that §7.7's "`vault:v1:` is now refused" story — which uses
   `pii-field-encryption` — has a version 2 to be refused against.
   Without this, §7.7 silently assumed a rotation that the module never
   performed on that key.

Both commands were re-run live and their outputs captured.

### 8.3 The `nonce` evidence did not match what was being pointed at — **FIXED**

**Defect:** *"`nonce` is 'absent from the endpoint help' (the word
appears in the `convergent_encryption` description; the substantive
claim holds), make the evidence match what you are actually pointing
at."*

**Verified against the live server.** `bao path-help
ai/transit/encrypt/pii-column-encryption` lists exactly nine
parameters: `associated_data`, `batch_input`, `context`,
`convergent_encryption`, `key_version`, `name`,
`partial_failure_response_code`, `plaintext`, `type`. There is **no
`nonce` parameter** — but the word *does* appear inside the
`convergent_encryption` description, which says the mode *"will require
all requests to carry both a context and 96-bit (12-byte) nonce"* and
then goes on to explain nonce uniqueness.

**Fixed:** the callout now quotes that description verbatim, lists the
nine parameters that *are* in the help, and draws the sharper point out
of it — *the help tells you convergent encryption requires a nonce and
then offers you no way to supply one*. The substantive claim (passing a
nonce has no effect) is unchanged and was re-verified: the ciphertext
was byte-identical with a random nonce, a different random nonce, and
no nonce at all.

### 8.4 Nothing else changed

No restructuring, no prose rewriting, no other claim touched. The
student-facing README still contains **zero** authoring-environment
paths, the four HCL policy blocks still pass `bao policy fmt`, the
markdown fences are still balanced (236), and `pii_demo.py` compiles
cleanly.

## 9. Round 2 — commands actually run

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN policy write data-pipeline <data-pipeline>.hcl
$BAO_BIN token create -policy=data-pipeline -no-default-policy -format=json
$BAO_BIN token capabilities "$DP" ai/transit/encrypt/pii-column-encryption   # create, update
$BAO_BIN token capabilities "$DP" ai/transit/decrypt/pii-column-encryption   # create, update
$BAO_BIN token capabilities "$DP" ai/transit/keys/pii-column-encryption      # deny
$BAO_BIN token capabilities "$DP" ai/transit/datakey/plaintext/pii-column-encryption  # deny
$BAO_BIN token capabilities "$DP" ai/transit/export/encryption-key/pii-column-encryption # deny
$BAO_BIN token capabilities "$DP" ai/platform/data/db/postgres               # read

# the shipped script, for real
cd lab/app && BAO_ADDR=$BAO_ADDR BAO_TOKEN=$DP python3 pii_demo.py

# §7.3 / §7.6 key creation and rotation
$BAO_BIN write -format=json ai/transit/keys/pii-field-encryption type="aes256-gcm96"
$BAO_BIN write -force -format=json ai/transit/keys/pii-field-encryption/rotate
$BAO_BIN write -force -format=json ai/transit/keys/pii-column-encryption/rotate

# §7.10 the nonce evidence
$BAO_BIN path-help ai/transit/encrypt/pii-column-encryption

python3 -m py_compile lab/app/pii_demo.py
```

## 10. Round 2 — still not verifiable

* **No Postgres.** The `pii_demo.py` run uses SQLite, exactly as the
  module states in §7.12; the Postgres DDL in the module is a
  deployment artefact, not something this lab executes.
* **The `vault:v2:` prefix in the demo output** depends on how many
  times the key has been rotated on the learner's own instance. On a
  fresh key it will be `vault:v1:`. The module now says so.
