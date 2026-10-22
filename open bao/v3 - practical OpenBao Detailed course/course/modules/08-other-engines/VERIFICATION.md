> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 08 (PKI, SSH, Transit, TOTP & the Postgres Database Engine)

**Reviewer:** General agent (`r4`) — final review sweep, round 2
**Date:** 2026-10-21
**Live server used:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`),
`pebbledb` storage, Shamir seal, one declarative `file` audit device, on
`http://127.0.0.1:9599`.
**Method:** every quoted terminal block and every quoted error message was
re-run against that live server. Every HCL block was passed to
`bao operator validate-config`. Every claimed GUI label was grepped out of
the shipped 2.7.1 UI bundle. Nothing was accepted on the strength of the
previous review round.

---

## 1. Commands actually run

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN status
$BAO_BIN plugin list
$BAO_BIN secrets list
$BAO_BIN secrets enable -path=ai/pki pki          # + ssh, transit, totp, database
$BAO_BIN operator validate-config -config=<each HCL block in the module>
$BAO_BIN policy fmt <policy files>               # client-side, BAO_ADDR=http://127.0.0.1:1
curl -s http://127.0.0.1:9599/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(…); do curl -s "http://127.0.0.1:9599/ui/$f" -o "$(basename $f)"; done
for L in "Enable Engine" "Create Role" …; do printf "%-30s -> " "$L"; grep -c -F "$L" vault.js; done
grep -nE "\.mavis|/workspace/lab|agentlab\.sh|plan_[0-9a-f]{6,}" README.md
```

---

## 2. Claims checked, and the result

| # | Claim in the module | Command | Result |
|---|---|---|---|
| 1 | The 2.7.1 built-in plugin inventory (§2.1) | `bao plugin list` | **MATCH** — all 22 rows identical |
| 2 | `bao secrets list` after enabling 5 engines (§2.4) | `bao secrets enable` ×5 + `bao secrets list` | **MATCH** |
| 3 | `ssh/config/generate_signing_key` is gone (§5.2) | `bao write ai/ssh/config/generate_signing_key=true` | **MATCH** — `Must supply data or use -force`, then `404` |
| 4 | `ai/ssh/config/ca` → `issuer_id` / `issuer_name: n/a` / `public_key` (§5.3) | `bao write ai/ssh/config/ca generate_signing_key=true key_type=ed25519 issuer_name=meridian-ssh-ca` | **MATCH** |
| 5 | SSH role `default_extensions` must be a map (§5.4) | `bao write ai/ssh/roles/meridian-engineer default_extensions="permit-pty=,…"` | **MATCH** — `400` / `Field validation failed: error converting input for field "default_extensions": '' expected type 'map[string]interface {}', got unconvertible type 'string'` |
| 6 | `root/generate/internal` accepts `issuer_name` (§4.2) | `bao write ai/pki/root/generate/internal … issuer_name=meridian-ai-root-2026` | **MATCH** |
| 7 | §4.2 shows **only** the AIA warning | same command **after** `bao secrets tune -max-lease-ttl=8760h` | **MATCH** — the tune removes the TTL warning, so the block is correct as written |
| 8 | `intermediate/generate/internal` ignores `issuer_name` (§4.3) | `… issuer_name=… key_type=ec key_bits=256` | **MATCH** — `Endpoint ignored these unrecognized parameters: [issuer_name]` |
| 9 | `ai/pki/issuers` (plural) lists ids; the singular lists `{}` (§4.4) | `bao list -format=json ai/pki/issuers` / `… ai/pki/issuer` | **MATCH** |
| 10 | `ai/pki/crl/rotate` is a **GET** in 2.7 (§4.7) | `bao read …` / `bao write -force …` | **MATCH** — `success true` vs `405 unsupported operation` |
| 11 | `key_type=ml-dsa-44` rejected; use `mldsa` (§4.9) | `bao write ai/pki/root/generate/internal key_type=ml-dsa-44` | **MATCH** — `unknown key type ml-dsa-44` |
| 12 | Transit spells it `mldsa-44` (§4.9) | `bao write ai/transit/keys/pqc type=mldsa-65` | **MATCH** — accepted; `ml-dsa-65` → `unknown key type ml-dsa-65` |
| 13 | `sys/external-keys/configs` empty / not readable (§4.10) | `bao list` / `bao read` | **MATCH** — `{}` and `405` |
| 14 | `sys/leases/revoke-prefix` needs the prefix **in the path** (§3.8) | `bao write sys/leases/revoke-prefix prefix="…"` | **MATCH** — `404 unsupported path`. The module's correction of `VERIFIED-FACTS.md` §4 is **correct** |
| 15 | `sys/leases/count` is a GET that renders nothing (§3.8) | `curl` GET / PUT | **MATCH** — GET → `404` body `{"errors":[]}`; PUT → `405` |
| 16 | TOTP does not generate the secret (§6.2) | `bao write ai/totp/keys/aisha.rahman type=otp key_size=32 issuer=meridian-ai` | **MATCH** — `the key value is required` |
| 17 | `key_size` invalid for chacha20-poly1305 (§7.2) | `bao write ai/transit/keys/… type=chacha20-poly1305 key_size=32` | **MATCH** |
| 18 | An AES transit key cannot sign (§7.5) | `bao write ai/transit/sign/meridian-data …` | **MATCH** — `key type aes256-gcm96 does not support signing` |
| 19 | `transit/keys/<n>/rotate` needs `-force` (§7.6) | `bao write ai/transit/keys/meridian-data/rotate` | **MATCH** |
| 20 | `ai/pki/config/cluster` needs a **URL** (§4.8) | `bao write ai/pki/config/cluster path="meridian-ai"` | **MATCH** — `invalid, non-URL path given to cluster: meridian-ai` |
| 21 | There is no `cluster { path = … }` config stanza (§4.8) | `bao operator validate-config -config=cluster-path.hcl` | **MATCH** — `Unknown or unsupported field cluster …`, exit 2 |
| 22 | `/acme/directory` resolves the **default** issuer (§4.8) | `allowed_issuers=<non-default>` then `curl …/acme/directory` | **MATCH** — `500` + `{"type":"urn:ietf:params:acme:error:serverInternal","detail":"the server experienced an internal error: specified issuer not allowed by ACME policy"}`. With the default issuer in `allowed_issuers` → `200`. The issuer-scoped path `/ai/pki/issuer/<id>/acme/directory` → `200` for a non-default issuer |
| 23 | Every GUI label in §11 | downloaded the bundle, `grep -c -F` | **MATCH** for 20 of 21 labels; `Configure PKI` is in `vendor.js` (0 hits in `vault.js`), `Root Certificate` is 0 hits in **any** chunk — which the module already discloses. The real `grep -c` output is now pasted into the module |
| 24 | No authoring-environment paths | `grep -nE "\.mavis\|lab\|agentlab\.sh\|plan_[0-9a-f]{6,}"` | **CLEAN** |
| 25 | Meridian AI values match `STYLE-GUIDE.md` §2 | `grep` for the four secrets and paths | **MATCH** |
| 26 | No placeholder values | `grep -nE '\b(foo\|bar\|baz\|changeme\|your-secret-here\|random-string\|mysecret\|hello)\b'` | **CLEAN** |
| 27 | Required sections | structural read | **PRESENT** — §0 60-second table, §11 GUI section, §13 "What you learned", §14 "What's next", §15 Homework (6 runnable tasks) |
| 28 | All HCL blocks | `bao operator validate-config` | The one HCL block in the module is the **intentionally wrong** `cluster { path = … }` trap; it fails exactly as the module says |

---

## 3. Fixed in this round

| # | Severity | What was wrong | The truth (verified live) | Fix |
|---|---|---|---|---|
| **F1** | high | §4.8 said the ACME "cluster path" prerequisite is a `cluster { path = "meridian-ai" }` stanza in the server config file | The 2.7.1 parser **rejects** that stanza (`Unknown or unsupported field cluster`, exit 2). The real mechanism is the **PKI mount's own** endpoint `ai/pki/config/cluster`, and the value must be a **URL** | §4.8 rewritten around `bao write ai/pki/config/cluster path="https://…:8200"`, with the live `invalid, non-URL path given to cluster` output and a "there is no `cluster { path }` stanza" trap. §12 cheat sheet and §11 GUI note updated |
| **F8** | high | §4.8 claimed `/acme/directory` returns `200` after a config that names only the **intermediate** in `allowed_issuers` | `/acme/directory` resolves the **default** issuer (the root). With the intermediate named, it returns **500** `specified issuer not allowed by ACME policy` | §4.8 now shows the default issuer in `allowed_issuers` for the `200`, documents the `500` with its real body, and adds the issuer-scoped path `/ai/pki/issuer/<id>/acme/directory` (verified `200`). New row in the §12 cheat sheet |
| **F9** | medium | §3.5b pointed at Redis on `127.0.0.1:6399` with the Meridian password | The shipped lab ships `redis:7-alpine` on **`127.0.0.1:6379`** with the throwaway `lab-only-redis-pass` — the `6399`/`Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU` combination is not runnable by a learner | §3.5b now opens with the `docker compose up -d redis` step, uses the lab's real port and password, and states in a **Production** note that Meridian's Redis credential is `ai/platform/cache/redis` = `Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU` and is exactly the kind of secret that should be dynamic |
| **F10** | medium | The module asserted "PostgreSQL 15.19" and "Redis 7.0.15" in seven places | The course's own `lab/docker-compose.yml` ships `postgres:17-alpine` and `redis:7-alpine`. A learner following the lab gets **PostgreSQL 17** | All version claims changed to "PostgreSQL 17" and "Redis 7" |
| **F11** | minor | The `redis-cli ACL LIST` block showed one line while the capture has two, presented as verbatim | The capture has the generated user **and** the untouched `default` user | Both lines are now shown, and the prose explains that the plugin did not touch `default` |
| **F12** | minor | The `intermediate/generate/internal` output block showed the "ignored `issuer_name`" warning, but the command above it did not pass `issuer_name` | — | `issuer_name=meridian-ai-intermediate-2026` added to the command, so the quoted warning is now produced by the quoted command |
| **F13** | minor | "The exact field names, all seven of them:" above an **eight**-row table | — | "all eight of them" |
| **F14** | minor | "the last **three** digits of the username" | The embedded unix timestamp is the last **ten** digits | Fixed |
| **F15** | minor | `docker compose ps postgres` showed `0.0.0.0:5432->5432/tcp` | The compose file maps `127.0.0.1:5432:5432` | Fixed |
| **F16** | minor | §11 asserted the GUI labels "are the actual strings in the UI bundle" without showing the check | — | The **real** `grep -c -F` output for all 21 labels is now pasted into §11, including the two zero-hit cases and why they are zero |

---

## 4. Not verified — stated plainly

| Item | Why it could not be verified here |
|---|---|
| §3.5 / §3.5c — the **PostgreSQL** transcripts (`psql`, `pg_authid`, `rolvaliduntil`, the generated `v-root-meridian-…` username) | This lab has **no PostgreSQL** (no `psql`, no Docker daemon), and nothing is listening on 5432. I re-verified the **OpenBao side** of every one of those blocks — the `connection refused` error text, the config write/read shape, `verify_connection` semantics, the Redis plugin-schema trap, the `db_name` → `failed to find entry for connection with name` error — all match the live server. The **database-side** output could not be regenerated. The module's Status block says these came from a real PostgreSQL server; that is an authoring-lab capture and is labelled as such |
| §3.5b — the **Redis** transcript | Same: no Redis and no `redis-cli` here. The ACL line was **copied verbatim** from the authoring lab's own capture (`the authoring lab's Redis 7 `ACL LIST` capture`), which is in real Redis 7 `ACL LIST` format, and the section is now anchored to the shipped lab's Redis (port 6379) so a learner can reproduce the *OpenBao* side |
| §4.9 — the `openssl x509 -text` output for the ML-DSA certs | The 2.7.1 binary contains `mldsa-44/65/87`, `key_type=mldsa` is accepted and `key_type=ml-dsa-44` is refused — all confirmed. The exact `openssl` rendering of OID `2.16.840.1.101.3.4.3.17` was **not** re-derived, because it depends on the OpenSSL version on the reader's machine (the module already notes `Unable to load Public Key` is expected there) |
| §4.10 — External Keys with a real HSM/KMS | No HSM or KMS in this lab. The API shape and the empty-list behaviour were verified; the signing flow was not, and the module says so |
| The `kubernetes` and `rabbitmq` engines | No Kubernetes cluster and no RabbitMQ broker here. The module already labels them "not verified in this module" |

---

## 5. Result

Sixteen defects fixed across the two rounds (F1, F8–F16 here; F1 from round 1).
Every other quoted output block, error message, status code, GUI label, HCL
snippet and Meridian AI value in this module was reproduced against a live
OpenBao 2.7.1 server and matches.

---

## 6. Round 3 — the captured-issuer-id defect

**Defect.** §4.8 showed the issuer-scoped ACME directory path with the
issuer UUID captured on the authoring mount
(`9570ada9-a818-cb6c-af7c-d66649ce225c`). A learner who copies that literal
points the request at an issuer that does not exist on their own mount.

**Reproduced live.** With ACME enabled and a named default issuer:

```console
$ curl -s -w "\n%{http_code}\n" \
    "$BAO_ADDR/v1/ai/pki/issuer/9570ada9-a818-cb6c-af7c-d66649ce225c/acme/directory"
{"type":"urn:ietf:params:acme:error:malformed","detail":"the request message was malformed: issuer does not exist"}
400

$ curl -s -o /dev/null -w "%{http_code}\n" \
    "$BAO_ADDR/v1/ai/pki/issuer/40a6c7f2-8d0d-4fce-03d5-44eda1ab2d03/acme/directory"
200
```

**Fix applied.** §4.8 now says the UUID is the capture's, not the reader's;
shows how to read their own (`bao read -field=issuer_id ai/pki/issuer/default`,
or the `imported_issuers` list from `set-signed`); and shows the exact
`400 … issuer does not exist` body they would otherwise get.

**Second fact added while fixing it.** `allowed_issuers` takes issuer
**names**, not UUIDs, and the server validates them at write time:

```console
$ bao write ai/pki/config/acme enabled=true allowed_roles="ai-harness" \
    allowed_issuers="meridian-ai-root-2026" \
    dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
Code: 500. Errors:

* 1 error occurred:
	* failed validating allowed_issuers: unable to fetch issuer: meridian-ai-root-2026: unable to find PKI issuer for reference: meridian-ai-root-2026
```

A fresh mount's default issuer has an **empty** `issuer_name`, so it has to
be named (`bao write ai/pki/issuer/<id> issuer_name=…`) before it can appear
in `allowed_issuers`. Verified: after naming it, the ACME write succeeds and
`/ai/pki/acme/directory` returns `200`.
