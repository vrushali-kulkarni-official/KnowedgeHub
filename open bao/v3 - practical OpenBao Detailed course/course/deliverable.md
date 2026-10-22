# Course deliverable — OpenBao: From Zero to Production

**Target:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`), Linux x86-64,
`pebbledb` storage, `bao` CLI and the 2.7.1 web UI.

**Scenario:** Meridian AI — FastAPI + LangChain + Gemini + Postgres + Redis +
Keycloak, all containerised.

---

## 1. What was built

| | |
|---|---|
| **9 teaching modules** | 23,703 lines of prose, commands and captured output |
| **Front door + reference docs** | 2,463 lines (`README.md`, `GLOSSARY.md`, `TROUBLESHOOTING.md`, `VERIFIED-FACTS.md`, `STYLE-GUIDE.md`, `MODULE-BRIEFS.md`) |
| **A runnable Docker lab** | Pinned OpenBao image, declarative audit device, 6 scripts, 5 policies, a FastAPI service, unit + integration suites, an acceptance-check script |
| **9 verification records** | One `VERIFICATION.md` per module: what was checked live, what changed, what could not be checked |

### The nine modules

| # | Module | Lines | Teaches | Hands-on artefact |
|---|---|---|---|---|
| 01 | Foundations | 1,903 | Seal/unseal, Shamir, the barrier, break-glass root-token recovery | A running unsealed server; a break-glass script that **verifies its own output** |
| 02 | KV v2 Secrets | 2,428 | The two-layer model, versioning, CAS, custom metadata, soft delete | The Gemini key at `ai/platform/llm/gemini`, versioned and CAS-guarded |
| 03 | Policies & ACLs | 2,555 | Capabilities, deny semantics, the `default` policy, path grants | Five policies and a live allow/deny matrix proving the AI harness cannot read the DB password |
| 04 | Namespaces, Entities & Leases | 2,084 | Isolation, the identity store, the lease lifecycle, `generate_lease` | Three namespaces; entities, aliases, groups; a traced lease lifecycle |
| 05 | Auth, MFA & OIDC | 2,599 | AppRole, userpass, OIDC↔Keycloak, TOTP, `login-enforcement` | Three login paths; TOTP enrolled and actually enforced |
| 06 | Crypto Tooling | 2,939 | Transit, wrapping, hashing, randomness, datakeys, convergent encryption | A PII-in-Postgres demo that encrypts a column without storing a key |
| 07 | App Integration | 2,961 | Token lifecycle in code, three secret-delivery patterns, rotation | `openbao_client.py` (299 lines), a FastAPI service, a container that writes no secret to disk |
| 08 | Other Engines | 3,283 | PKI chains, ACME, SSH signing, the Postgres database engine | A root→intermediate→leaf chain; dynamic database credentials |
| 09 | Production Hardening | 2,951 | TLS, HA, audit, auto-unseal, backups, container hardening, monitoring, CI/CD, runbook | A hardened configuration, a threat model and an incident runbook |

---

## 2. How the work was verified

Every command and output block in every module was executed against a live
OpenBao 2.7.1 server. Nothing was copied from Vault-era documentation.

**The four review passes.** Each module group was written by one author and
then checked by an independent reviewer instructed to *fail* a module that was
correct but thin. Reviewers re-ran the module's own bash blocks in a private
instance and compared the real output against the module, field by field.

**The owner's own verification.** Beyond the review passes, the following
were executed end-to-end against a live server:

| Check | Result |
|---|---|
| `prepare-lab.sh` → `init-lab.sh` → `setup-platform.sh` → app client | Full learner journey, clean |
| AppRole login + KV v2 read from the application client | Works |
| Unit suite (`test_openbao_client.py`) | **10/10 pass** — and still 10/10 with credentials in the environment, proving the isolation holds |
| Integration suite (`test_integration.py`, live) | **6/6 pass** — including "the harness cannot read the database password" and "the harness cannot write" |
| `validate-module02.sh` | **ALL CHECKS PASSED**, three consecutive runs |
| **Clean-room rebuild** | A fresh server started from the **shipped `lab/config/openbao.hcl`**, then `init-lab.sh` → `setup-platform.sh` → unit 10/10 → integration 6/6 → `validate-module02.sh` 3× — all green, with no Docker and no hand-set environment |
| `break-glass.sh` | New root token authenticates; the old token still works (correct — no rotation happened) |
| Restart → `unseal-lab.sh` | Clean |
| Every HCL config block | Passes `bao operator validate-config` |
| Every claimed GUI label | Grepped out of the shipped 2.7.1 UI bundle |
| Every quoted status code | Confirmed against the live server |

**Deliberately not verified, and labelled as such in the modules.** The
PostgreSQL and Redis transcripts in Module 08 (no database or Redis in this
lab); the `openssl` rendering of ML-DSA certificates (depends on the
reader's OpenSSL build); External Keys against a real HSM; Kubernetes and
RabbitMQ engines; multi-node Raft, real cloud KMS, and a production SIEM.
Each is marked in the module and listed in that module's `VERIFICATION.md`.

---

## 3. Contradictions found and how they were resolved

The interesting part of a course like this is not that it was written, but
what the live server disagreed with.

### Against Vault-era documentation

| The claim | What the server said | Resolution |
|---|---|---|
| Shamir `init` produces recovery keys | `recovery_keys_b64: null` | Recovery keys are auto-unseal only. Module 01 says so explicitly and explains why the tutorial is wrong. |
| `storage "file"` | Removed in 2.7.0 | `pebbledb` everywhere; Module 01 §3.3 explains the migration |
| `bao audit enable file` | `400 cannot enable audit device via API; use declarative, config-based audit device management instead` | The declarative `audit` stanza, with the two gotchas (duplicate label refuses to start; `file_path` outside `options` is silently ignored) |
| `sys/renew`, `sys/revoke`, `sys/revoke-prefix`, `sys/revoke-force` | All 404 | `sys/leases/*` |
| `sys/mounts/<path>/tune` for KV CAS settings | Silently no-ops | CAS config lives at `<mount>/config` |
| `kv` is KV v2 | `kv` is v1, `kv-v2` is v2 | Module 02 opens with the distinction |
| `mfa_require=true` on a role | Silently ignored | `identity/mfa/login-enforcement` — Module 05 §7.4 demonstrates the no-op |
| MFA methods at `sys/mfa/method/totp` | `404 unsupported path` | `identity/mfa/method/totp` — confirmed against the server's own OpenAPI spec |
| `bao token lookup -token=…` | `flag provided but not defined: -token` | The current token is implicit in `BAO_TOKEN` |

### Against this course's own earlier drafts

These are the ones worth keeping a record of — they were all caught by
re-running the module against a real server rather than by reading it.

| # | Defect | Why it mattered | Fix |
|---|---|---|---|
| 1 | **Module 01 taught "if the decoded token does not start with `s.`, you used the wrong OTP."** | A one-character OTP typo still produces an `s.`-prefixed, 26-character string. A reader would install a **corrupted break-glass root token** believing it was good. | Heuristic deleted. The only check now is to **use** the token: `bao token lookup` must return `display_name: root`. The break-glass script gained a verifying step. |
| 2 | The wrong-OTP transcript itself was **impossible** — the two OTPs differed in one character, so a position-wise XOR could not have produced outputs differing in 25 | It taught a mechanism that cannot exist | Re-captured live from one attempt decoded twice; the two outputs differ in exactly one byte **and both still start with `s.`** |
| 3 | Module 02's version counters read `1` / `1` | Contradicted the module's own sequence | `current_version 2` / `current_metadata_version 3`, with a per-step progression table, plus the finding that a metadata write the server *ignores* still counts |
| 4 | Five Module 02 transcripts showed pre-patch metadata | Contradicted §9.2 | All five re-captured against the post-§9.2 state |
| 5 | Module 02's "how I verified it" grep output was unreproducible | The literal did not exist in the bundle | Real eight-line output pasted, with an explanation of why a route grep is the wrong tool |
| 6 | Module 04 put `-format=json` **after** the path | The module contradicted its own gotcha two hundred lines later; live it yields `warnings: ["Endpoint ignored these unrecognized parameters: [-format]"]` and an empty `lease_id` | Flag moved before the path, output re-captured, and the §5.5 / §6.6 tie-back made explicit |
| 7 | The `token_type: "service"` block was presented as an AppRole-login response | Live, `token create` and AppRole login both return **11** auth keys with **no** `token_type` | The block now shows the real 11-key shape; the module teaches the three real envelopes — `token create` / AppRole login (11 keys, no `token_type`), `token lookup` (`type: "service"` under `data`), and `sys/mfa/validate` (12 keys, `token_type` + `num_uses`) |
| 8 | Module 06 claimed the `default` policy grants nothing | It grants `cubbyhole/*`, `sys/wrapping/{wrap,lookup,unwrap}` and `sys/tools/hash/*` | Corrected, with the real stanzas quoted; the unreachable 403 examples rewritten |
| 9 | Module 06's GUI section said Tools had no Random/Hash/Wrap | The 2.7.1 bundle **does** have all of them — and has no Trim action and no cubbyhole page | Section rewritten against the shipped bundle |
| 10 | Module 06 §7.12 showed a `pii_demo.py` transcript but shipped no script | An unshipped script cannot be run, so the "captured output" was uncheckable | Script shipped at `lab/app/pii_demo.py`, transcript re-captured from a real run |
| 11 | Module 06 §7.3 used a Transit key it never created | A learner following in order hits "key does not exist" | The key is now created — and rotated — in the section that uses it |
| 12 | Module 07's Status block promised a runnable `jwt` auth role that did not exist | A broken promise in the module's own summary | `jwt_login_demo.py` written, shipped, and run live: OpenBao validates a locally-served JWKS, the issued token is scoped exactly like the AppRole one, a wrong `sub` is refused |
| 13 | Module 07's honest-caveat cross-reference said "section 10" | Pointed at the wrong section | Corrected to section 11 |
| 14 | Module 08's ACME section described a `cluster { path = … }` config stanza | The 2.7.1 parser **rejects** it: `Unknown or unsupported field cluster` | The real mechanism — the mount endpoint `ai/pki/config/cluster`, whose value must be a URL (`invalid, non-URL path given to cluster: meridian-ai`) |
| 15 | Module 08 embedded a captured issuer UUID in a copy-pasteable `curl` | Copy-pasting it points at an issuer that does not exist: `400 … issuer does not exist` | The module now says the UUID is the capture's, shows how to read your own, and quotes the exact error you would otherwise get — plus the separate fact that `allowed_issuers` takes issuer **names** and is validated at write time |
| 16 | Module 09's PKI chain dead-ended | `issuer_name` on `root/sign-intermediate` is **silently ignored**, and the signing role was never created | The chain now captures the imported issuer id, names it, creates the role (`key_type=ec key_bits=521 issuer_ref=…`) and issues — re-run verbatim on a fresh mount |
| 17 | Module 09 called `ai/platform/db/postgres` the metadata read | It is the **rejected pre-v2 path** (`data:null` + `Invalid path for a versioned K/V secrets engine`); the metadata read is `ai/platform/metadata/…` | A three-row table of the three paths, the real `curl` body, and a widened regex |
| 18 | Module 09's rotation workflow used `-cas=0` to replace a secret | `-cas=0` is a literal version, not a wildcard — it fails with `check-and-set parameter did not match the current version` | Reads `current_version` from the metadata path and uses it as the CAS value |
| 19 | Module 04's `bao token create` transcript showed `lease_id: ""`, `lease_duration: 0`, `renewable: false` | Looked wrong | **Verified genuine**: those are the top-level *lease* fields, and a token is not a lease. The table view shows `token_duration 30m` / `token_renewable true`. The section's point is exactly this. |
| 20 | All nine `VERIFICATION.md` files leaked authoring-environment paths | A learner would hit paths that do not exist on their machine | Scrubbed; each file now opens with a note saying what it is |
| 21 | Two authoring artefacts sat inside module folders | — | Moved out of the learner-facing tree |
| 22 | Three relative links were broken | — | Fixed; **52 of 52 links now resolve** |
| 23 | **The lab's saved AppRole `secret_id` expired with no documented way to renew it** | The role has `secret_id_ttl=1h` — correct by design — but a learner whose session ran long hit `403 permission denied` on login with no idea why | New `lab/scripts/refresh-credentials.sh`: mints a fresh `secret_id`, **verifies it authenticates** before printing it, and explains why the expiry is the design working. Documented in the README and as entry 17 of the troubleshooting runbook |

### Bugs fixed in the shipped code and scripts

Not teaching errors — real defects in the lab you would run:

* The app client never released its cached token (no `close()`), so a rotated
  credential kept working in-process.
* The client's environment fallback swallowed an **explicitly empty**
  credential instead of refusing to run.
* `unseal-lab.sh` read `threshold` and `total_shares` from the JSON status
  endpoint, which returns `t` and `n` — so it never found the keys.
* `init-lab.sh`'s wait loop broke on `bao status`, which **exits 2** when the
  server is sealed or uninitialised, combined with `pipefail`.
* `setup-platform.sh` crashed with a raw traceback when the policies directory
  was missing.
* The unseal-key list was printed as a Python repr — with quotes and
  brackets — so copying it produced an invalid key.
* `role_id` was saved JSON-quoted, with the quotes included.

---

## 4. What is in the box

```
course/
├── README.md                    # the front door
├── deliverable.md               # this file
├── docs/
│   ├── GLOSSARY.md              # every term, defined, with a first-appearance pointer
│   ├── TROUBLESHOOTING.md       # 16 reproduced errors: text, cause, fix
│   ├── VERIFIED-FACTS.md        # where 2.7.1 differs from what you remember
│   ├── STYLE-GUIDE.md           # the house style and the canonical values
│   └── MODULE-BRIEFS.md         # what each module must cover
├── modules/01..09/
│   ├── README.md                # the lesson
│   └── VERIFICATION.md          # the verification record
└── lab/
    ├── config/openbao.hcl       # pinned image, declarative audit, pebbledb
    ├── scripts/                 # prepare / init / setup-platform / bao-lab /
    │                            # unseal / break-glass
    ├── policies/                # five least-privilege HCL policies
    ├── app/                     # openbao_client.py, main.py, FastAPI app,
    │                            # Dockerfile, unit + integration suites
    ├── keycloak/                # realm export for the OIDC module
    ├── validate/                # acceptance checks
    └── secrets/                 # gitignored
```

---

## 5. Honest limits

* **The lab is single-node.** Raft HA, real cloud KMS auto-unseal, TLS
  termination and a production SIEM are taught from the specification and
  from the 2.7.1 config parser, and each is labelled as such.
* **No PostgreSQL or Redis in the authoring lab.** Module 08's database-side
  transcripts are labelled; the OpenBao side of every one of them is verified.
* **Keycloak is not running in the lab.** Module 05's OIDC flow is taught
  against a local JWKS double that *was* run, and every Keycloak console
  screenshot is labelled as an illustration.
* **The GUI section in the 2.7.1 UI has no audit screen.** Module 09 says so
  instead of inventing one.
* **The frontend of the `bao` CLI changes.** Every command in this course was
  checked against the 2.7.1 binary; if your CLI is older, some flags differ.

---

## 6. Reproducing the verification yourself

```bash
cd lab
docker compose up -d openbao
./scripts/init-lab.sh
./scripts/setup-platform.sh
./scripts/refresh-credentials.sh     # if your session ran long

cd app
python3 -m unittest test_openbao_client -v     # 10 tests
export BAO_ADDR=http://127.0.0.1:8200
export BAO_TOKEN="$(cat ../secrets/root-token)"
export BAO_ROLE_ID="$(cat ../secrets/ai-harness-role-id)"
export BAO_SECRET_ID="$(cat ../secrets/ai-harness-secret-id)"
python3 -m unittest test_integration -v         # 6 tests, live

cd ..
./validate/validate-module02.sh                 # ALL CHECKS PASSED
```

---

*Every output block in this course was captured from a live OpenBao 2.7.1
server. Where a block could not be reproduced in the lab, it says so on the
page rather than being quietly presented as real.*
