> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 09 (Production Hardening)

**Reviewer:** General agent (`r4`) — final review sweep, round 2
**Date:** 2026-10-21
**Live server used:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`),
`pebbledb` storage, Shamir seal, one declarative `file` audit device, plus
throw-away servers on ports 9250/9251 to reproduce the audit-stanza failure
modes, and throw-away PKI mounts to reproduce the §3.4 chain.
**Method:** every quoted terminal block and every quoted error message was
re-run; every HCL block was passed to `bao operator validate-config`; every
claimed GUI label was grepped out of the shipped UI bundle.

---

## 1. Commands actually run

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance

# every HCL block in the module, extracted and validated
bao operator validate-config -config=<block>.hcl

# audit architecture
bao audit enable file file_path=./evil.log
bao audit list
bao read sys/audit
bao read sys/audit -format=json

# three throw-away servers to reproduce the malformed audit stanzas
bao server -config=onelabel.hcl
bao server -config=twolabel-noopts.hcl   # + bao operator init + bao operator unseal
bao server -config=twolabel-inline.hcl

# seal / unseal / status / health / key-status
bao operator seal ; bao status ; bao status -format=json ; bao read sys/health
bao operator unseal <share> ; bao operator key-status

# break-glass
bao operator generate-root -generate-otp | -init | -update | -decode | -cancel

# metrics
curl -s -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/sys/metrics?format=prometheus"

# policies (client-side, server deliberately unreachable)
export BAO_ADDR="http://127.0.0.1:1"; export -n BAO_TOKEN
bao policy fmt bad-policy.hcl ; good-policy.hcl ; bad-key.hcl ; bad-cg.hcl ; -

# diagnostics
bao operator diagnose -config=lab/config/openbao.hcl

# GUI bundle
curl -s http://127.0.0.1:9599/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in <those assets>; do curl -s "http://127.0.0.1:9599/ui/$f" -o "$f"; done
grep -l -F "<each label>" *.js

# hygiene
grep -nE "\.mavis|/workspace/lab|agentlab\.sh|plan_[0-9a-f]{6,}" README.md
```

---

## 2. Claims checked, and the result

| # | Claim in the module | Result |
|---|---|---|
| 1 | `bao audit enable file …` fails with `cannot enable audit device via API; use declarative, config-based audit device management instead` (§4.1) | **MATCH** — `400`, exact body, exit 2 |
| 2 | `bao audit list` / `bao read sys/audit` shape, incl. the resolved `options` map (§4.2) | **MATCH** |
| 3 | `bao read sys/audit -format=json` warns `Endpoint ignored these unrecognized parameters: [-format]` (§4.2) | **MATCH** |
| 4 | **Wrong #1** — one-label audit stanza is a hard config error (§4.2) | **MATCH** — `audit type must be specified`, exit 1 |
| 5 | **Wrong #2** — two labels, no `options`: passes `validate-config`, dies at unseal with `file_path is required`, `sys/audit` → 503 | **MATCH — reproduced end to end**, including the `[ERROR] core: post-unseal setup failed during init: error="failed to create new audit device local-file/: file_path is required"` log line |
| 6 | **Wrong #3** — two labels, `file_path` inline: server starts, one WARN line (§4.2) | **MATCH** — `2026-10-21T19:02:47.081Z [WARN] unknown or unsupported field file_path found in configuration at twolabel-inline.hcl:12:3` |
| 7 | The 2.7.1 UI has no audit screen; `sys/audit` never appears (§4.6) | **MATCH** — 0 hits across every shipped asset |
| 8 | `bao operator raft -help` subcommand list (§6.2) | **MATCH** — identical wording |
| 9 | `operator raft snapshot save` is raft-only; 404s on `pebbledb` (§7.2) | **MATCH** |
| 10 | `bao operator diagnose` output (§9.4) | **MATCH** — all seven result lines identical |
| 11 | `bao policy fmt` is client-side and catches bad capability / bad key / bad `control_group` key (§10.1) | **MATCH** — all four outputs verbatim, exit codes 1/0/1/1 |
| 12 | `bao policy fmt -` (stdin) fails (§10.3) | **MATCH** — `Error reading source file: open -: no such file or directory` |
| 13 | Sealed-state transcripts: `seal`, `status`, `status -format=json`, `sys/health` → 503, `unseal` → `Unseal Progress 1/2` (§11.3) | **MATCH** — every field identical |
| 14 | The encryption count does **not** move across a seal/unseal cycle (§9.2) | **MATCH** — 97 before and 97 after |
| 15 | `generate-root`: bare 26-char OTP, `-init` output, second `-init` → `root generation already in progress for this namespace`, `-cancel`, missing nonce (§11.2, §11.4) | **MATCH** — all reproduced |
| 16 | `validate-config` is a schema check, not a file-existence check, and accepts `api_addr = "127.0.0.1:8200"` (§3.2) | **MATCH** — `[ success ]`, exit 0 |
| 17 | The `audit "syslog" "siem"` stanza is a valid config (§4.4) | **MATCH** |
| 18 | All other HCL blocks | **MATCH** — every one passes `validate-config` (exit 0) |
| 19 | The `path "sys/metrics" { … }` block (§9.1) | It is an **ACL policy**, not a server config, so `validate-config` rejects it — correctly. It is linted with `bao policy fmt` (§10.1). No change needed |
| 20 | GUI: **Status** shows seal type and storage backend (§3.6) | **MATCH** — `Status` is a literal string in `vault.js`; the module does not claim `Seal Type`/`Storage Type` are literal bundle strings |
| 21 | No authoring-environment paths | **CLEAN** |
| 22 | Meridian AI values match `STYLE-GUIDE.md` §2 | **MATCH** |
| 23 | Required sections | **PRESENT** — §0 60-second table, §3.6 and §4.6 GUI sections, §12 threat model, §13 checklist, §14 "What you learned", §15 "What's next", §16 Homework (6 runnable tasks), §17 ASCII diagram |

---

## 3. Fixed in this round

| # | Severity | What was wrong | The truth (verified live) | Fix |
|---|---|---|---|---|
| **F2** | **high** | §3.4's certificate-lifecycle chain ended at `bao write ai/pki/issue/meridian-ai-pki-int …` and **dead-ends**: the role `meridian-ai-pki-int` is never created anywhere in the course, and `issuer_name` on `root/sign-intermediate` is **silently ignored** so the imported intermediate comes in with an empty name and the role's `issuer_ref` cannot resolve | Verified: `root/sign-intermediate … issuer_name="meridian-ai-pki-intermediate"` → the imported issuer's `issuer_name` is `''`; and issuing against a role that points at that name gives `500` / `could not fetch the CA certificate (was one set?): unable to find PKI issuer for reference: meridian-ai-pki-intermediate` | §3.4 now: (1) drops the no-op `issuer_name` from `sign-intermediate`; (2) captures the `imported_issuers` id from the `set-signed` output; (3) **names** the imported issuer with `bao write ai/pki/issuer/<id> issuer_name=…` and shows the `bao read -field=issuer_name` check; (4) **creates the role** with `key_type=ec key_bits=521` and `issuer_ref=…`; (5) issues. The whole chain was then **re-run verbatim** on a fresh mount: the leaf issues with `ca_chain`, `certificate`, `private_key` (`private_key_type ec`), `serial_number`, `expiration`, `not_before` |
| **F6** | **high** | §11.1 said the bare path `ai/platform/db/postgres` is the **metadata** read, and prescribed the regex `^ai/platform/(data/)?db/postgres$` | The bare path is the **rejected pre-v2 path**: `{"data":null,"warnings":["Invalid path for a versioned K/V secrets engine. …"]}`. The **metadata** read is `ai/platform/metadata/db/postgres`. Verified audit paths: `data/db/postgres` → `read`/`create`/`update`; `db/postgres` → `read` (the invalid one); `metadata/db/postgres` → `read`. The prescribed regex **missed the real metadata read** | §11.1 now has a three-row table (pre-v2 path / value path / metadata path), the real `curl` body of the rejected path, and the regex widened to `^ai/platform/(data/|metadata/)?db/postgres$`. The warning that a plain `startswith("ai/platform/db/postgres")` is not enough is kept, with the reason |
| **F17** | **high** | §10.4's rotation workflow used `bao kv put -cas=0` to **replace** an existing secret. `-cas=0` means "this secret must not exist" | On an existing secret: `400` / `check-and-set parameter did not match the current version`. A scheduled job that fails this way rotates nothing and still reports success | The workflow now reads the current version and uses it as the CAS value: `CAS="$(bao read -field=current_version ai/platform/metadata/llm/gemini)"` then `bao kv put -cas="$CAS" …`. (Verified: `bao read -field=current_version ai/platform/metadata/db/postgres` → `2`; `-cas=2` → `Success!`; `-cas=0` → the 400 above.) The prose was rewritten to match the module's own pre-existing note, and the 400 is now shown |
| **F18** | minor | `bao policy fmt` output quoted `invalid key "bananas" on line 3` without saying the line number is per-file | The line number is the line **in the file you passed** | A note was added: the message text is the stable part, the line number is per-file |

### Fixed in round 1 and confirmed correct by the independent verifier

| # | What it was | Verifier's result |
|---|---|---|
| **F3** | §3.5 ML-DSA spellings: `type=ml-dsa-65` → `type=mldsa-65` (Transit), `key_type=ml-dsa-65` → `key_type=mldsa` (PKI), `pki/role/` → `pki/roles/` | **CORRECT** — all three rejections reproduced, correct spellings confirmed |
| **F4** | §9.1 metric list: removed `vault_policy_list_policies`, `vault_seal_encrypt`, `vault_seal_shamir_encrypt`; added the "only after first use" note | **CORRECT** — the three names are indeed absent |
| **F5** | §10.4: `sys/audit-test-marker` (404) → `sys/audit-hash/local-file` | **CORRECT** — `sys/audit-hash/local-file` → `hmac-sha256:…` |
| **F7** | §8.2: a YAML Compose snippet was fenced as `hcl`; retagged `yaml` | **CORRECT** — all YAML blocks parse |

---

## 4. Not verified — stated plainly

| Item | Why it could not be verified here |
|---|---|
| A real 3-node Raft cluster, `bao operator raft join`, `list-peers` output | This lab is single-node `pebbledb`, which by design refuses to cluster. The **subcommand list** and the **404 on the raft snapshot endpoint** were verified; the join transcript is not. The module already states "No 3-node raft cluster was run in this module" and shows the join commands without a transcript |
| A real TLS / mTLS listener, the certificate lifecycle, the renewal job, `tls_auto_reload`, and a pure-PQC handshake | The lab listener is `tls_disable = true` and there is no client to negotiate against. What **was** verified: the listener and mTLS HCL blocks pass `validate-config`, `tls_key_exchange_preferences` is a field the 2.7.1 parser accepts, and the binary contains `tls_key_exchange_preferences` and the `mldsa-44/65/87` parameter sets. The module labels the runtime handshake as coming from the 2.7 release notes |
| The `seal "transit"` / `seal "awskms"` seals actually unsealing a server | No second OpenBao and no KMS in this lab, and every KMS seal is an external plugin in 2.7. Only the **config validity** was verified (`validate-config` → success). The module presents the transit seal as a config shape |
| The `audit "syslog"` device actually shipping a record to a SIEM | No syslog collector here. The stanza passes `validate-config`; the shipping path was not exercised |
| The `pebbledb` "second instance" failure (§6.1) | Reproduced in principle by the same storage lock the `diagnose` output shows, but the module's transcript comes from the authoring lab's own data directory. The error text matches `VERIFIED-FACTS.md` §2 exactly |
| Backup / restore drill, Docker image facts, container hardening | No Docker daemon in this lab. The image facts (uid 100 / gid 1000, `/openbao/file`, default `CMD`) come from `VERIFIED-FACTS.md` §11 and the repo's own `lab/config/openbao.hcl` comments; they were not re-derived from an image here |
| The `ai/pki/issue/meridian-ai-pki-int` leaf's **certificate contents** | The issuance succeeds and returns all eight fields, but the leaf is signed by the *root* of the throw-away mount, so the exact serial and expiry are per-run. The module shows the command, not a transcript, so nothing depends on a fixed value |

---

## 5. Result

Seven defects fixed across the two rounds (F2, F6, F17, F18 here; F3–F5, F7 from
round 1, all confirmed correct by the independent verifier). All other quoted
output blocks, error messages, status codes, GUI claims, HCL snippets and
Meridian AI values in this module were reproduced against a live OpenBao 2.7.1
server and match.
