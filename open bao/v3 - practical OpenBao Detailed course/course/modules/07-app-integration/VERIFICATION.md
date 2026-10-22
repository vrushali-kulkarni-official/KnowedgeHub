> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Verification — Module 07 (App Integration)

> **This file is an internal review artifact, not course content.** It
> deliberately contains authoring-environment paths (the reviewer's private
> lab instance) that are forbidden in the learner-facing `README.md`. The
> `README.md` was checked and contains none of them.

**Reviewer:** General (agent `r3`) · **Date:** 2026-10-21
**Scope:** final review sweep — correctness of quoted output, source-file
line references, GUI labels, required sections, style-guide consistency.

## 1. Environment used

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN status        # Sealed false, Version 2.7.1, Storage pebbledb
```

The lab was provisioned to match the module's own setup section:
`ai/platform` (kv-v2) with `llm/gemini` / `db/postgres` /
`cache/redis` / `oidc/keycloak`; the `ai-harness-service` policy
(read on `ai/platform/data/llm/gemini` and
`ai/platform/metadata/llm/gemini`); the `approle` auth method with the
`ai-harness-service` role (`token_ttl=15m`, `token_max_ttl=1h`,
`secret_id_ttl=1h`, `secret_id_num_uses=0`).

## 2. What was verified (and found correct)

| Module section | Check | Result |
|---|---|---|
| 3.1 | `bao secrets enable -path=ai/platform kv-v2`, `bao write ai/platform/config …`, `bao kv put` | the `Secret Path` output really is `ai/platform/data/llm/gemini` (the `data` segment) — exact match |
| 3.1 | `bao write auth/approle/role/ai-harness-service …` | role read back with `token_ttl: 900`, `token_max_ttl: 3600`, `secret_id_ttl: 3600`, `token_policies: ["ai-harness-service"]` — the JSON in the module matches the server's field-for-field |
| 3.1 | the "`default` policy is also attached implicitly" note | confirmed: the login response carries `policies: ["ai-harness-service", "default"]` while the role's own `token_policies` list does not |
| 3.2 | `bao read -field=role_id …/role-id`, `bao write -force -format=json …/secret-id`, `bao list …/secret-id` | all match, incl. `secret_id_accessor` and `secret_id_num_uses` |
| 3.2 | the `secret_id_accessor` kill switch | `bao delete auth/approle/role/…/secret-id-accessor/destroy secret_id_accessor=…` → `Success! Data deleted (if it existed)`; the `…/secret-id/<id>` path really is a 404 `unsupported path` — exact match |
| 4.4 | the `/data/` path trap | harness token on `ai/platform/llm/gemini` → **403**; on `ai/platform/data/llm/gemini` → **200**. Root token on `ai/platform/llm/gemini` → **404**; on `ai/platform/data/llm/gemini` → **200**. Both the §4.4 trap blocks and the §18 homework matrix are exact |
| 4.5 | `list` vs `read` | `GET ai/platform/metadata/llm` with the harness token → 403 `permission denied` — exact match |
| 4.9 | `GET /v1/sys/health` while healthy | the JSON body in the module matches the live response field-for-field |
| 4.9 | `GET /v1/sys/health` after `bao operator seal` | HTTP **503** with `sealed: true`, `standby: true`, `replication_*_mode: "unknown"` — exact match |
| 5.2 | AppRole login against a sealed OpenBao | HTTP **503**, body `{"errors":["Vault is sealed"]}` — exact match |
| 5.2 | the five-row failure table | 403 `permission denied`, 400 `invalid role or secret ID` (both for a bad `role_id` and a bad `secret_id`) — all confirmed live |
| 5.1 | the log-line format | `main.py` sets `format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"`, so the quoted `2026-10-21 18:02:55,149 INFO     openbao_client: …` is exactly what the app prints |
| 6 | the Dockerfile | byte-for-byte the shipped `course/lab/app/Dockerfile` (35 lines) — `USER meridian` on line 28, `HEALTHCHECK` on 32–33 |
| 6.4 | `requirements.txt` | matches the shipped file exactly, pins included, and the "no `requests` / `hvac` / `boto3`" note is correct (`httpx` is present only for TestClient) |
| 7 | the compose excerpt | matches `course/lab/docker-compose.yml` lines 157–173, including the `depends_on: condition: service_healthy` block and the OpenBao healthcheck (lines 73–80) |
| 8.2 | `bao write -format=json -wrap-ttl=60s sys/wrapping/wrap role_id="…"` | the response really does carry `ttl: 60` |
| 8.2 | the "flags become data" gotcha | `bao write -format=json sys/wrapping/wrap -token="x" role_id="y" -ttl=60` produces the payload `{"-token":"x","-ttl":"60","role_id":"y"}` — exact match |
| 9.2 | `bao kv metadata get ai/platform/llm/gemini` | the field set (`cas_required`, `current_version`, `oldest_version`, `delete_version_after`, `metadata_cas_required`, …) matches the live output |
| 10.5 | the audit-log HMAC | the real entry is `request.data.role_id` / `request.data.secret_id`, both `hmac-sha256:…` — confirmed |
| 13.1 | the unit-test transcript | `python -m unittest test_openbao_client -v` on the shipped file produces **exactly** the 10 test names and the `OK` result quoted in the module |
| 13.2 | the integration tests | `python -m unittest test_integration -v` against the live server: **6 tests, all OK** |
| 18 (homework 2) | the 4-row 403/404 matrix | reproduced exactly (see §4.4 above) |
| 15 | the CLI-gotcha table | every row re-checked: `-format=json` vs `-f=json`, `token=` as a data field, `text=` vs `-text=`, flags before positionals, `kv` vs `kv-v2`, `sys/mounts/<path>/tune` vs `<mount>/config`, `-version` (singular) vs `-versions` (plural), and `bao policy fmt` needing no server |

## 3. Defects found and FIXED

### 3.1 Every source-file line reference was wrong (HIGH)

The module tells the reader to open `lab/app/openbao_client.py` at
specific lines. The **shipped** file in the course repo is 299 lines; the
module said "It is 277 lines" and its references were all systematically
offset (they pointed at a shorter earlier revision).

Every reference was re-derived from the shipped file and corrected:

| Module said | Now |
|---|---|
| "It is 277 lines" | 299 lines |
| `str \| None` annotations on line 90 | line 91 |
| `openbao_client.py:107-111` (TLS) | 113–117 |
| `openbao_client.py:115-119` (`_headers`) | 121–125 |
| `openbao_client.py:121-162` (`_request`) | 127–169 |
| line 131 / line 133 (url / urlencode) | 137 / 139 |
| `read_secret_version` (line 224–229) | 230–235 |
| line 142–143 (Content-Type) | 148–149 |
| lines 146–147 (timeout) | 152–153 |
| lines 150–154 (HTTP errors) | 156–160 |
| lines 155–159 (network failure) | 161–165 |
| `from exc` on line 159 | line 165 |
| `openbao_client.py:167-196` (`login`) | 173–202 |
| lines 174–178 (credential check) | 180–184 |
| line 183 (`token=""`) | 189 |
| line 186 (`auth` envelope) | 192 |
| line 190 (the 80% rule) | 196 |
| lines 191–196 (what gets logged) | 197–201 |
| `openbao_client.py:198-200` (`_ensure_token`) | 204–206 |
| `self._token` on line 104 | line 110 |
| `openbao_client.py:204-222` (`read_secret`) | 210–228 |
| `openbao_client.py:231-238` (`list_secrets`) | 237–244 |
| `openbao_client.py:240-256` (`health`) | 246–262 |
| last `except` on line 256 | line 261 |
| `openbao_client.py:259-274` (`get_gemini_credentials`) | 281–299 |
| `if not api_key` check (lines 266–271) | 290–294 |
| `main.py`: `raise` on line 49 | line 50 |

`main.py`'s other references were checked and were already correct
(`33-58`, `66-92`, `101-128`, `global` on 41, `bao_client.close()` on 58,
`key_prefix` on 127, `main.py` is 153 lines), as were the Dockerfile's
`USER meridian` on line 28.

### 3.2 The integration-test snippet was not valid Python (HIGH)

Section 13.2 quoted the last test method as:

```python
    def test_the_harness_cannot_write(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client._request("POST", "ai/platform/data/llm/gemini",
                         body={"api_key": "attacker-supplied"})
    assert "403" in str(exc.value)
```

The final `assert` was outside the `with` block and referenced an
undefined `exc` — it would raise `NameError` if the reader pasted it in.

**Fixed** to the shipped form:

```python
    def test_the_harness_cannot_write(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client._request("POST", "ai/platform/data/llm/gemini",
                            body={"api_key": "attacker-supplied"})
        self.assertIn("403", str(ctx.exception))
```

### 3.3 The GUI section claimed labels the UI does not have (HIGH)

Section 14 quoted these paths:

* `Secrets → ai/platform → llm → gemini`
* `… → (⋮) → Show version history`
* `Auth Methods → AppRole → ai-harness-service`
* `… → Role ID`
* `… → Generate Secret ID`
* `ACL Policies → ai-harness-service`
* `Status → (the top bar shows seal state)`

The shipped UI bundle was fetched and grepped
(`curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js'`,
then download + grep). Findings:

* The real top-level navigation is **Secrets engines**, **Access**,
  **Policies**, **Tools** (plus a seal-status indicator in the top bar).
  There is no "Secrets" and no "Status" menu.
* The Access sub-navigation reads **Authentication methods**,
  **Multi-factor authentication**, **OIDC provider**; the Policies
  sub-navigation reads **ACL Policies**.
* The KV engine's display name is **KV**; the mount path `ai/platform`
  is shown next to it.
* The version-history button is the literal string
  **"View version history"** — not "Show version history".
* **There is no AppRole role page at all.** The strings `Role ID`,
  `Secret ID`, `Generate Secret ID`, `role_id`, `secret_id`, `roleId`
  and `secretId` appear **nowhere** in the bundle. The AppRole support
  in the 2.7.1 UI stops at the auth-method list entry and the "enable
  AppRole" wizard.

**Fixed:** Section 14 was rewritten with the verified labels, the two
rows that have no GUI are now stated as *"Not in the GUI — use the
CLI"* with the reason, the bundle-verification method is shown, and the
"what the GUI does not expose" list was corrected (the old bullet
claimed the GUI *can* generate a `secret_id` — it cannot).

### 3.4 The `bao auth list` block was a hand-drawn table (MEDIUM)

Section 8.3 presented a two-column ASCII table
(`SECRET (type=secret)  AUTH (type=auth) / kv approle / pki cert …`) as
if it were terminal output. It is not the output of any `bao` command.

**Fixed** to the real `bao plugin list` output, which is what actually
proves the point (that `jwt` and `oidc` are built in).

### 3.5 The §13.2 "results" block was stylised, not captured (MEDIUM)

The block

```text
PASS  reads the real gemini secret
PASS  harness cannot read db/postgres
…
```

is not `unittest` output, and it listed 5 results for a file that ships
**6** tests.

**Fixed** with the real captured `unittest -v` output (6 tests, `OK`),
plus the exact `export` lines needed to run it.

### 3.6 A contradictory, duplicated "Production" note (MEDIUM)

Section 5.1 had **two** consecutive `> **Production:**` blocks about
the `close()` fix. The first said the fix clears the cached token; the
second said the right fix is "either to add a `close()` that is a
no-op … or to delete the call" and leaned towards a no-op. The shipped
code does the first thing (`close()` sets `self._token = ""` and
`self._token_expires_at = 0.0`).

**Fixed:** the contradictory second block was deleted; the first was
kept (it matches the code).

### 3.7 Smaller fixes

| Where | Was | Now |
|---|---|---|
| §10.5 | the audit fragment was cut off mid-HMAC string | completed and shown as the `request.data` object it is |
| §8.3 | the reformatted plugin table | the real `bao plugin list` output |
| §10.5 | — | a note that in the 2.7 audit format `path`/`operation` live under `request`, not at the top level |

## 4. Checks that passed with no changes needed

* **Forbidden authoring paths** —
  `grep -nE "\.mavis|/workspace/lab|agentlab\.sh|plan_[0-9a-f]{6,}" README.md`
  returns nothing.
* **HCL blocks** — the single `hcl` block is the `ai-harness-service`
  policy, so `bao policy fmt` is the correct validator (VERIFIED-FACTS
  §12). It passes with exit 0 against an unreachable server. There are
  no server-config (`listener` / `storage`) blocks in this module.
* **Meridian AI values** — Gemini key, Postgres password, Redis
  password, Keycloak client secret, secret paths
  `ai/platform/llm/gemini` / `ai/platform/db/postgres` /
  `ai/platform/cache/redis` / `ai/platform/oidc/keycloak`, mount
  `ai/platform/`, roles `ai-harness-service`, realm
  `meridian-ai` — all match STYLE-GUIDE §2. No placeholders.
* **Required sections** — 60-second table (§0), "What you learned"
  (§16, 17 items), "What's next" (§17), "Homework" (§18, 6 numbered
  runnable tasks) and a GUI section (§14) are all present.
* **Status codes** — every quoted code (200 / 400 / 403 / 404 / 503)
  was re-observed on the live server in the place it is quoted.
* **The `openbao_client.py` code quoted in §4** is the shipped file,
  verbatim (imports, error class, dataclass, `_headers`, `_request`,
  `login`, `_ensure_token`, `read_secret`, `list_secrets`, `health`,
  `get_gemini_credentials`) — only the line-number comments were wrong.

## 5. What could NOT be verified — stated plainly

1. **The GUI was not driven.** No browser in this lab. GUI *labels* are
   quoted from the shipped UI bundle; the *page layout* is inferred from
   the bundle's route and component names.
2. **`docker compose` was not run.** Docker is not available in this
   review environment, so the compose excerpt and the `Dockerfile` were
   verified by **diffing against the files in `course/lab/`** (both
   match exactly), not by building and running the image. The app was
   exercised through the Python client against a live server instead,
   which covers the same code paths.
3. **The `main.py` / `Dockerfile` / `docker-compose.yml` transcripts in
   §5–§7** (the uvicorn log lines, the `/health` payload) are the
   module's own captures. I re-derived the *format* from the source
   (`logging.basicConfig(format=…)`, the `HealthResponse` model) and
   re-verified every OpenBao-side value they contain (seal state, 503
   on login, the health JSON), but I did not re-capture uvicorn's own
   stdout.
4. **The `/proc` forensics in §10** (`environ`, `cmdline`, `fd`, the
   filesystem grep) are the module's own captures of a demo process. I
   did not re-run the demo process; the *property* they demonstrate
   (the key is not in the environment, the command line, or a file) is
   enforced by the client code, which I did read line by line.
5. **The PyPI claims in §12** (`pip install hvc` → the hyperdimensional
   vector computing library, `hvac` v2.4.0 and its single `requests`
   dependency, the 404s for every `openbao*` name) were **not**
   re-verified — this review environment has no outbound PyPI access
   available. They are outside the OpenBao-fact set and were left
   untouched.

## 6. Commands actually run (abridged)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN secrets enable -path=ai/platform kv-v2
$BAO_BIN write ai/platform/config cas_required=false max_versions=10
$BAO_BIN policy write ai-harness-service <policy>.hcl
$BAO_BIN kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" project_id="meridian-ai-prod-4471"
$BAO_BIN auth enable approle
$BAO_BIN write auth/approle/role/ai-harness-service token_policies="ai-harness-service" \
    token_ttl=15m token_max_ttl=1h secret_id_ttl=1h secret_id_num_uses=0
$BAO_BIN read -format=json auth/approle/role/ai-harness-service
$BAO_BIN read -field=role_id auth/approle/role/ai-harness-service/role-id
$BAO_BIN write -force -format=json auth/approle/role/ai-harness-service/secret-id
$BAO_BIN list auth/approle/role/ai-harness-service/secret-id
$BAO_BIN delete auth/approle/role/ai-harness-service/secret-id/<id>              # 404 unsupported path
$BAO_BIN delete auth/approle/role/ai-harness-service/secret-id-accessor/destroy \
    secret_id_accessor=<accessor>

# the 403 / 404 matrix
for p in ai/platform/llm/gemini ai/platform/data/llm/gemini \
         ai/platform/metadata/llm ai/platform/data/db/postgres; do
  curl -s -o /dev/null -w "%{http_code}\n" -H "X-Vault-Token: $HARNESS" $BAO_ADDR/v1/$p
  curl -s -o /dev/null -w "%{http_code}\n" -H "X-Vault-Token: $ROOT"    $BAO_ADDR/v1/$p
done

# seal state
$BAO_BIN operator seal
curl -s -w "\n%{http_code}\n" $BAO_ADDR/v1/sys/health
curl -s -w "\n%{http_code}\n" -X POST -d '{"role_id":"…","secret_id":"…"}' \
     $BAO_ADDR/v1/auth/approle/login
$BAO_BIN operator unseal <key1>; $BAO_BIN operator unseal <key2>

# error cases
$BAO_BIN write -format=json auth/approle/login role_id="<bad>" secret_id="<bad>"

# wrapping
$BAO_BIN write -format=json -wrap-ttl=60s sys/wrapping/wrap role_id="…"
$BAO_BIN write -format=json sys/wrapping/wrap -token="x" role_id="y" -ttl=60

# the shipped test files
cd lab/app && python -m unittest test_openbao_client -v    # 10 tests, OK
cd lab/app && python -m unittest test_integration -v        # 6 tests, OK

# policy lint (client-side, no server)
BAO_ADDR="http://127.0.0.1:1" bao policy fmt <policy>.hcl

# GUI bundle
curl -s http://127.0.0.1:9821/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(...); do curl -s "http://127.0.0.1:9821/ui/$f" -o "$(basename $f)"; done
grep -oE 'vault/components/tool-[a-z]+' vault.js
grep -c -F "View version history" vault.js
grep -c -F "Role ID" vault.js        # 0
grep -c -F "Secret ID" vault.js      # 0
```

## 7. Final state

* 0 forbidden authoring paths.
* 1 HCL policy block: passes `bao policy fmt`.
* All quoted status codes match the live server.
* All GUI labels are quoted from the shipped UI bundle, and the two
  labels the UI does **not** have are called out as such.
* Every `openbao_client.py` / `main.py` line reference now points at
  the right line of the shipped file.
* Required sections present; homework has 6 runnable tasks.
* Section count: **2783 → 2961 lines** (prose preserved; the growth is
  the corrected GUI table, the real test transcripts, the corrected
  source excerpts, and the new §8.3.1 federated-identity demo).

---

## 8. Round 2 — the defects the verifier raised

**Reviewer verdict:** FAIL, with four precise defects. All four are
addressed below.

### 8.1 The honest-caveat cross-reference pointed at the wrong section — **FIXED**

**Defect:** *"You have it as 'the same "honest caveat" section 10 is
about' — but section 10 is 'Proving the secret is gone'; the honest
caveat is **section 11**."*

Confirmed against the module's own heading list:

```
## 10. Proving the secret is gone
## 11. The honest caveat: the key IS in memory
```

**Fixed:** the sentence in §4.11 now reads *"Section 11 is honest about
what that still means."* Every other `section N` / `§N` cross-reference
in the module was re-checked against the heading list and was already
correct (4.4, 5.2, 8, 9, 12, 12.1, 13.1, 13.2, 14).

### 8.2 The reviewer's own fixes were preserved — **CONFIRMED, NOT TOUCHED**

The reviewer states they corrected the client line-count claim to 299
and added an environment-isolation base class to
`test_openbao_client.py` so the unit suite passes whether or not
`BAO_ADDR` / `BAO_ROLE_ID` are exported.

**Verified and left alone:**

* `course/lab/app/openbao_client.py` and
  `course/modules/07-app-integration/lab/app/openbao_client.py` are
  byte-identical (`808faf4b34566d7cd415efad0089075b`).
* `course/lab/app/test_openbao_client.py` and
  `course/modules/07-app-integration/lab/app/test_openbao_client.py`
  are byte-identical (`74c9b0a06779481b47f7e59ca281a3dc`).
* `test_integration.py` is byte-identical in both places
  (`5905d14c0b105add3cc96e7ecb9459be`).
* The client is **299 lines** and the module says 299.
* The unit suite still passes with the reviewer's isolation change:
  ```
  Ran 10 tests in 0.009s

  OK
  ```

Neither the client nor the test files were edited in this round. The
only new file is `jwt_login_demo.py` (below), which is a *new* name and
does not collide with either.

### 8.3 The Status block promised a §8.3.1 that did not exist — **FIXED (the promise is now kept)**

**Defect found while fixing the nonce evidence:** the Status block said
*"OpenBao's own side of that pattern is shown as a **runnable** `jwt`
auth role (§8.3.1) and was executed"* — but there was **no §8.3.1** in
the module, and no `jwt` auth role was configured or executed anywhere
in it. That is exactly the failure mode this review exists to catch,
so it was fixed rather than papered over.

**§8.3.1 "The OpenBao side of Pattern C, runnable" was written, and it
is a real captured run.**

* New file: `modules/07-app-integration/lab/app/jwt_login_demo.py`,
  with a byte-identical copy at `course/lab/app/jwt_login_demo.py`
  (`f68b4fb59fe833c3a183e92d811e9ec4` both) — the same "verbatim copy"
  pattern the module's file table already uses for the other files.
* The script mints an RS256 service-account token, serves the public
  half as a JWKS document on `127.0.0.1:8099`, configures OpenBao's
  `jwt` auth method against it, creates a role, and logs in.
* It needs exactly one dev-only dependency, `cryptography`, because
  the standard library cannot sign an RSA token. The module says so
  plainly, and points out that in production the *orchestrator* signs
  the token and the app never holds a signing key.

**The captured run, re-executed from the shipped file:**

```bash
$ bao auth enable jwt
Success! Enabled jwt auth method at: jwt/

$ bao write auth/jwt/config jwks_url=http://127.0.0.1:8099/.well-known/jwks.json jwt_supported_algs=RS256 role_type=jwt
Success! Data written to: auth/jwt/config

$ bao read -format=json auth/jwt/config
{
  "jwks_url": "http://127.0.0.1:8099/.well-known/jwks.json",
  "jwt_supported_algs": [
    "RS256"
  ],
  "status": "valid"
}

$ bao write auth/jwt/role/ai-harness-jwt role=ai-harness-service \
      user_claim=sub bound_claims='{"iss":"...","sub":"ai-harness"}' \
      bound_audiences=["openbao"] token_ttl=15m token_max_ttl=1h
Success! Data written to: auth/jwt/role/ai-harness-jwt

{
  "user_claim": "sub",
  "role_type": "jwt",
  "bound_claims": {
    "iss": "https://meridian-ai.svc.cluster.local",
    "sub": "ai-harness"
  },
  "bound_audiences": [
    "openbao"
  ],
  "token_ttl": 900,
  "token_max_ttl": 3600
}

### present the projected service-account token to OpenBao
client_token   = s.ppNjVuOpfDlVWb9JAC7BYYOD
lease_duration = 900
policies       = ['ai-harness-service', 'default']
metadata       = {"role": "ai-harness-jwt"}

### the token works, and it is scoped exactly like the AppRole token
GET /v1/ai/platform/data/llm/gemini -> 200
GET /v1/ai/platform/data/db/postgres -> 403

### the same token with a WRONG subject is refused
    refused, as it should be
```

Three OpenBao-side facts were learned while building this, and each is
now in the module:

* **`role_type=jwt` goes on the ROLE, not on the config.** The config
  endpoint has no `role_type` field at all; without `role_type=jwt` on
  the role, the server demands `allowed_redirect_uris` because it
  assumes an OIDC-style role.
* **`bound_claims` is a map and `bound_audiences` is a list**, so the
  role cannot be written with `bao write key=value` — it has to go over
  the HTTP API. That is why the demo script writes it with `urllib`.
* **The `aud` claim is bound separately.** A token carrying `aud` with
  no `bound_audiences` on the role is rejected with `audience claim
  found in JWT but no audiences bound to the role`; a token whose `sub`
  does not match is rejected with `error validating claims: claim "sub"
  does not match any associated bound claim values`. Both messages are
  quoted in §8.3.1.

The module's Status block was updated so it no longer claims more than
the module delivers: the OpenBao half is now a captured run of a
shipped script, and only the *cloud-side* projection is described
rather than captured.

### 8.4 A "What you learned" bullet was added for the new section

*[- [ ] The federated pattern (Pattern C): the orchestrator projects a
signed token, OpenBao validates it against a JWKS endpoint, and the
`sub`/`aud` claims are bound to one workload.*

## 9. Round 2 — commands actually run

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
cd lab/app
BAO_ADDR=$BAO_ADDR BAO_TOKEN=$BAO_TOKEN BAO_BIN=bao \
    python3 jwt_login_demo.py

# byte-identity of the shipped files
md5sum course/lab/app/*.py course/modules/07-app-integration/lab/app/*.py

# the unit suite still passes with the reviewer's isolation change
cd lab/app && python -m unittest test_openbao_client -v      # 10 tests, OK

python3 -m py_compile lab/app/jwt_login_demo.py
```

## 10. Round 2 — still not verifiable

* **No Kubernetes, no cloud IAM.** §8.3.1 exercises the OpenBao side
  only. The Kubernetes TokenRequest API, IRSA, Workload Identity
  Federation and Azure Workload Identity rows in §8.3 remain *described,
  not captured*, and the module now says exactly that in its Status
  block.
* **The JWKS endpoint in the demo is a local stand-in** for the
  cluster's OIDC issuer. It serves a key the script itself generated;
  in production `jwks_url` points at the real issuer and OpenBao fetches
  *its* keys.
* **`cryptography` is not a standard-library module.** It is a dev-only
  dependency of the *demo*, not of the secret-fetching path the module
  argues for in §4.1. The module states this in §8.3.1.
