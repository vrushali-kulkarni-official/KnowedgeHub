# PER-MODULE BRIEFS

Each agent gets ONE module. This file says exactly what to cover, what depth
means for that module, and what "done" looks like. Follow your brief plus
`STYLE-GUIDE.md` and `VERIFIED-FACTS.md`.

**Universal requirements for every module:**

1. **Verify every command against a live server.** You have a private
   OpenBao 2.7.1 instance. Use it:

   ```bash
   cd lab && ./scripts/init-lab.sh     # provisions and unseals on :8200
   source lab/scripts/bao-lab.sh       # exports BAO_ADDR / BAO_TOKEN
   bao status                          # must show Sealed false
   ```

   If you are working in parallel with other authors, give each instance its
   own port and data dir — no interference.

   **Every output block in your module must come from a command you actually
   ran.** If you can't verify it, don't show it.

2. **Write the module to
   `modules/<module-folder>/README.md`** — overwrite the
   existing outline.

3. **Do not modify any file outside your module folder.** Other agents are
   writing other modules concurrently. The only exception: create scratch
   files under a scratch directory of your own.

4. **The `docs/VERIFIED-FACTS.md` file is your ground truth.** If your memory
   of OpenBao contradicts it, the file wins. If you find something in the
   file that's wrong, note it in your final report — but do not "correct"
   the file yourself.

5. **Length target: 600–1000 lines of markdown**, deep not padded.

---

## mod01 → `modules/01-foundations/README.md`

**Title:** Module 01 — Foundations: Your First Production-Shaped OpenBao

**Must cover:**
- What OpenBao is and the problem it solves (replace the `.env` file —
  walk through the 6 questions: who can read it, is it in git history, can
  you rotate it, can you audit it, can you scope it, does it reach the app
  at runtime)
- The mental model: secret, storage, **barrier / root key**, seal, unseal
  key, root token, token, policy, mount, lease, audit device
- **The architecture, drawn out:** plaintext → barrier key → encryption at
  rest. What "sealed" physically means (the root key is not in the process).
- Docker install: pinned image, `server -config=` vs the default `-dev`,
  why loopback-only publishing, `pebbledb` vs the removed `file` backend,
  `cap_drop`/`cap_add IPC_LOCK`/`no-new-privileges`, non-root uid 100
- `bao operator init` with 3 shares / threshold 2 — what Shamir's Secret
  Sharing actually does, and how to size shares for production
- **The recovery-key trap** — full treatment: Shamir mode has NO recovery
  keys, verified, and what that means operationally
- Seal / unseal; **restart always re-seals** (demonstrate it)
- **Break-glass `generate-root`** — the complete 4-step flow with the
  nonce/OTP/`Encoded Token` gotchas, and a copy-paste script
- Root token vs unseal keys vs leases — the three-credential distinction
- The GUI tour: every top-level screen and its CLI equivalent
- Debugging: reading `logs/server.log`, `bao status`, the seal-status fields
  on `bao status` output

**Must include:** a "what breaks" note for `-dev` mode, for loopback
publishing, and for not distributing unseal shares.

---

## mod02 → `modules/02-kv-secrets/README.md`

**Title:** Module 02 — KV v2: Storing Meridian AI's Gemini API Key

**Must cover:**
- Mount layout design — `ai/platform/` and *why* not `secret/`; naming
  rules (lowercase, no "prod" suffix, realistic values)
- **KV v1 vs KV v2** — with the proof that `kv` gives you v1
- The two-layer structure: `data/` vs `metadata/`
- Writing the Gemini key; reading it; the **double `.data`** in JSON output
- Metadata fields, and **custom metadata** for ownership/rotation tracking
- Version history, **rollback** semantics (new version, old retained)
- **CAS** — the lost-update race it prevents; where the config really lives
  (`<mount>/config` vs `sys/mounts/<path>/tune`); `metadata_cas_required`
- Soft delete vs destroy vs undelete; `delete_version_after` for
  right-to-erasure
- `max_versions` vs lease TTL — two different mechanisms, often confused
- Listing and why `list` leaks secret names
- The GUI: Secrets → ai/platform → llm → gemini, History and Metadata tabs
- A full lifecycle lab

**Must include:** the exact 400 error text for a missing CAS parameter.

---

## mod03 → `modules/03-policies/README.md`

**Title:** Module 03 — Policies & ACLs: Least Privilege

**Must cover:**
- The authorization model: path + token + policies; **allow-list, absence
  is deny**; the full capability verb table
- `default` policy — what it actually contains in 2.7 and why to keep it
  minimal (or disable it for machine tokens with `-no-default-policy`)
- `root` policy — why it must never be on a long-lived token
- Writing the five Meridian AI policies (they exist in
  `lab/policies/*.hcl` — reference and explain them)
- The **read/write separation** pattern and why it is the single most
  important pattern
- `sudo` — what requires it (seal/unseal, generate-root, policy authoring,
  audit enabling), and the security property that no human session can
  unilaterally lock the company out
- **Control Groups** (new in 2.7) — the `control_group` policy stanza,
  two-person approval on sensitive paths. Verify what you can and be
  explicit about what you couldn't verify
- Path patterns, wildcards, and wildcards as a privilege-escalation vector
- `deny` — when it's a patch over an over-broad grant
- `bao token capabilities` — the testing tool; use it on every policy
- The enforcement matrix as a lab exercise, with real PASS/FAIL output
- Policies-as-code: version control, CI application, drift detection
- Production checklist

---

## mod04 → `modules/04-namespaces-entities/README.md`

**Title:** Module 04 — Namespaces, Entities, Groups & Leases

**Must cover:**
- **Namespaces** — the multi-tenancy layer; what is isolated (mounts,
  policies, auth methods, `sys/`); creating, listing, using
  (`-namespace=`), enabling engines inside one; verifying isolation
- **When to use namespaces vs paths+policies** — the decision, with
  trade-offs; the cost of undoing a namespace
- **Per-namespace sealing** (2.6) — tenant-revocable access
- **Entities** — the canonical identity; `identity/entity` (NOT
  `auth/token/identities/entity`); entities outlive tokens; aliases
- **Groups** — the unit of authorization; group→role mapping
- **Leases** — the full lifecycle diagram; TTL, renewal, expiry, revocation
- **2.7 lease endpoint changes** — the removed `sys/renew`/`sys/revoke*`
  (CVE-2026-45808) and the surviving `sys/leases/*`; the full table
- Token TTL vs `max_ttl`; what happens at expiry; renewal and the cap
- `sys/leases/count`, `revoke-prefix` — incident-response levers
- Why `auth.lease_duration` holds the token TTL while top-level
  `lease_id` is for dynamic secrets

**Must include:** verified 404 vs 200 output for the removed vs surviving
lease endpoints.

---

## mod05 → `modules/05-auth-mfa-oidc/README.md`

**Title:** Module 05 — Auth Methods, MFA & OIDC with Keycloak

**Must cover:**
- Two audiences, two mechanisms: humans (OIDC) vs machines (AppRole) —
  and *why* using one mechanism for both is a design error
- The built-in auth inventory for 2.7.1 (approle, cert, jwt, kubernetes,
  oidc, userpass) and what moved to external plugins
- **AppRole in depth** — role_id vs secret_id (which is secret), the role
  configuration options, `token_ttl`/`token_max_ttl`/`secret_id_ttl`,
  `secret_id_num_uses`, `secret_id_bound_cidrs`, `token_bound_cidrs`,
  `token_policies` vs `token_num_uses`; the full login round trip
- **How `secret_id` is delivered to a workload** — the hard part. Options:
  CI/CD injection, a mounted file, a bootstrap init container, and the
  trade-offs of each. This is where the `.env` pattern dies.
- **OIDC with Keycloak** — the realm export in `lab/keycloak/realm-export.json`;
  discovery URL, client_id/secret, role mapping, `bound_claims` for groups
- **MFA** — the `totp` engine, TOTP enrollment, and enforcing MFA at the role
  level (`mfa_require`); why a secret store demands MFA
- The decision table: which auth method for which situation
- The full human-login + machine-login flow side by side

**Note:** Keycloak is not running in your agent lab, so OIDC steps cannot be
executed. Be explicit about which steps are verified and which are
configuration you must verify in your own lab. **Never fabricate Keycloak
output.** You MAY verify the OpenBao-side OIDC config commands parse
(`bao write auth/oidc/config ...` with a dummy URL) and show that.

---

## mod06 → `modules/06-crypto-tooling/README.md`

**Title:** Module 06 — Crypto Tooling: wrap, random, hash, Transit

**Must cover:**
- The mental model table: wrap / random / hash / transit — reversible?
  key in OpenBao? use when
- **`sys/tools/random`** — generating secrets properly, and *why* not
  `openssl rand` in your app
- **`sys/tools/hash`** — one-way hashing, base64 input, hex output; the
  webhook-HMAC verification use case; why hashing a password is not enough
  (use Argon2/scrypt, not SHA-256)
- **Wrapping** — `wrap`/`unwrap`/`lookup`/`rewrap`; the single-use token;
  the transport use case (onboarding a new engineer); the `-text` vs `text=`
  gotcha; `token` is a data field; TTL and `-ttl`; rewrap for rotating a
  wrapped secret
- **Cubbyhole** — per-token private storage; the correct home for a secret
  that only one token should see
- **Transit in depth** — the key model, `encrypt`/`decrypt`, `datakey`
  (exportable vs non-exportable), batch encryption, HMAC signing, key
  rotation, `min_decryption_version`, and why Transit beats "encrypt it
  yourself" (no key material in your app, rotation without re-encrypting)
- **External Keys** (2.7) — PKI/Transit backed by KMS/HSM, key material
  never entering OpenBao
- The PII-in-Postgres use case for Meridian AI, end to end
- A clear "when NOT to use transit" note

---

## mod07 → `modules/07-app-integration/README.md`

**Title:** Module 07 — App Integration: The Secret Reaches the App

**Must cover:**
- The end-to-end flow diagram: container start → AppRole login → KV read →
  in-memory only
- **The client code** — explain `lab/app/openbao_client.py` line by line:
  stdlib-only rationale (supply chain in the trust boundary), fail-fast
  and never-fallback, in-memory only, re-auth at 80% of TTL, the
  **`<mount>/data/<key>`** path layout trap, TLS/`ca_cert` handling,
  `list` needing a `list` capability
- **The FastAPI app** — `lab/app/main.py`: lifespan startup fetch, the
  refuse-to-boot rule, the `/health` endpoint reporting OpenBao's seal
  state, the LangChain integration point with `ChatGoogleGenerativeAI` and
  `google_api_key` from OpenBao
- **The Dockerfile** — non-root, no ENV/ARG secrets, no `.env` copy, health
  check, pinned deps; why ARG is worse than ENV for secrets (image history)
- **The Docker Compose integration** — `depends_on: service_healthy`,
  `BAO_ROLE_ID` (not secret) vs `BAO_SECRET_ID` (secret)
- **Delivering `secret_id` to a container** — the three realistic patterns
  and their trade-offs; a `docker compose` example using a `.env` file that
  is *not* committed, and the CI/CD variant
- **Rotation without a restart** — demonstrate it
- **Proving the secret is gone** from env, filesystem, and `/proc`
- The honest caveat: the key IS in memory — and what that means
- Testing: unit-test the client with a mock, and a real integration test
- The `hvac` vs stdlib decision — when `hvac` earns its keep (HA, retry,
  standby handling)

---

## mod08 → `modules/08-other-engines/README.md`

**Title:** Module 08 — PKI, SSH, Transit, TOTP and the Postgres Database Engine

**Must cover:**
- Static vs dynamic secrets, and the strategic argument for moving from
  static to dynamic
- The built-in engine inventory for 2.7.1 and what needs external plugins
- **The Postgres database engine in depth** — the config, the role with
  `creation_statements`, reading `creds/<role>`, how the generated username
  looks, lease-driven expiry, and how Postgres itself is unaware of
  OpenBao. The "static password vs dynamic role" argument.
- **PKI in depth** — root CA generation, intermediate CA, roles, issuing
  leaf certs, the ACME integration for cert-manager, ML-DSA (2.7
  post-quantum), and External Keys
- **SSH** — signing keys, roles, one-time user certs, why this replaces
  `authorized_keys` management
- **TOTP** as a secret engine
- The `kubernetes` and `rabbitmq` engines briefly
- The comparison table: engine, secret type, lifetime, revocation
- A "which engines does Meridian AI actually need, and when" recommendation

**Note:** you have a live OpenBao but **no Postgres**. Verify everything
OpenBao-side (engine enable, config writes, role writes, PKI issuance) and
show the Postgres-side SQL/behavior as clearly-labeled *not executed in this
lab*. **Never fabricate database output.**

---

## mod09 → `modules/09-production-hardening/README.md`

**Title:** Module 09 — Production Hardening

**Must cover:**
- **TLS** — the real config, mTLS on the cluster port, the cert lifecycle,
  pure-PQC TLS and ML-DSA certs (2.7)
- **Audit architecture** — the declarative stanza, shipping off-host via
  syslog/socket, what to alert on, `log_raw` danger, the CVE that caused
  the change
- **Auto-unseal** — Transit seal config, and how it differs from Shamir:
  **it gives you recovery keys** (Shamir has none), and it survives
  restarts unattended. Also the KMS external-plugin seals.
- **High availability** — Raft, odd node counts, failure domains, standby
  nodes, the new PostgreSQL horizontal scalability
- **Backups and restore** — `operator raft snapshot save`, what a snapshot
  does and does not contain, restore drill, backing up BOTH data and
  unseal/recovery keys to different places
- **Container & runtime hardening** — mlock, `ulimit -c 0`, non-root,
  capability dropping, read-only rootfs, pinned digests, the OpenBao image's
  `/openbao/file` ownership quirk
- **Monitoring** — `/v1/sys/metrics` Prometheus metrics, seal-state
  alerting, audit-device health, lease counts
- **CI/CD** — policies as code, secret rotation automation, a GitHub
  Actions shape for the rotation job (their stack includes GitHub Actions)
- **The incident runbook** — leaked credential, lost unseal shares, sealed
  cluster, compromised admin token
- **The complete production checklist** and a **threat model** table
  (asset / threat / control / OpenBao mechanism)

**Include** a final "Meridian AI secrets architecture" diagram (ASCII) tying
all nine modules together.

---

## Common mistakes to avoid (all agents)

1. **Writing about HashiCorp Vault** as if it were OpenBao.
2. **Unverified output blocks.** Run the command, copy the real output.
3. **Placeholder values** — `foo`, `bar`, `test`, `changeme`.
4. **Concepts before commands** — always teach the idea first.
5. **Skipping the "what breaks" angle** — the user explicitly asked for it.
6. **Skipping the GUI** — the user explicitly asked for GUI + CLI mastery.
7. **Overwriting another agent's module** — only touch your own folder.
8. **Truncating the depth** to hit a line count. Depth is the goal.
