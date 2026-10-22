# Module 05 — Auth Methods, MFA & OIDC

> **Where we are.** OpenBao can store secrets. Now it needs to know **who**
> is asking. Humans authenticate with Keycloak's OIDC; machines authenticate
> with AppRole.

**Status: outline — full lesson in a later session.** Covers:

---

## 1. The two audiences

| | Human | Machine |
|---|---|---|
| Example | Aisha, platform engineer | The AI harness container |
| Auth method | **OIDC** (Keycloak) | **AppRole** |
| MFA | Yes (TOTP) | N/A |
| TTL | 1h, renewed on activity | 15m, auto-renewed |
| Credential | IdP session | role_id + secret_id |

**Never use the same mechanism for both.** OIDC for a service means a
service account with a password — the `.env` pattern again. AppRole for a
human means a shared secret — no MFA, no per-user audit.

---

## 2. Built-in auth methods in 2.7.1

Verified from the live plugin catalog:

```
approle       auth     v2.7.1+builtin.bao
cert          auth     v2.7.1+builtin.bao
jwt           auth     v2.7.1+builtin.bao
kubernetes    auth     v2.7.1+builtin.bao
oidc          auth     v2.7.1+builtin.bao
userpass      auth     v2.7.1+builtin.bao
```

⚠️ **LDAP auth and Kerberos are NOT built in** as of 2.7 — they moved to
`openbao-plugins` and must be installed as external plugins.

---

## 3. AppRole — machine identity (already working)

```bash
bao auth enable approle
bao write auth/approle/role/ai-harness-service \
  token_policies="ai-harness-service" \
  token_ttl=15m token_max_ttl=1h \
  secret_id_ttl=1h
```

Login (verified in the lab):
```json
{
  "client_token": "s.cysctA7AhAt9W3fve5A7jWq4",
  "lease_duration": 900,
  "renewable": true,
  "policies": ["default"],
  "metadata": { "role_name": "ai-harness-service" }
}
```

**`role_id` is not secret. `secret_id` is.** The `role_id` can be baked
into the app image; the `secret_id` must be delivered at deploy time.

**Production hardening (Module 09):** `secret_id_bound_cidrs`,
`secret_id_num_uses=1`, and a short `secret_id_ttl`.

---

## 4. OIDC ↔ Keycloak

Meridian AI's Keycloak realm (`lab/keycloak/realm-export.json`) defines
the `meridian-ai` realm, the `ai-harness` client, groups, and users.

```bash
bao auth enable oidc
bao write auth/oidc/config \
  oidc_discovery_url="http://keycloak:8080/realms/meridian-ai/.well-known/openid-configuration" \
  oidc_client_id="ai-harness" \
  oidc_client_secret="meridian-ai-harness-client-secret-rotate-me" \
  role="platform-operator"
```

Then map Keycloak groups → OpenBao groups:
```bash
bao write auth/oidc/roles/platform-team \
  allowed_bound_ids="..." bound_claims="groups" \
  claim_prefix="platform_team"
```

**OIDC is the right choice when you already run an IdP** (Keycloak, Okta,
Entra ID, Auth0). It gives you MFA, password policies, and offboarding
for free — because Keycloak already solved them.

**Use `userpass` only for small teams with no IdP.** It means OpenBao
stores your passwords, which means you now own password storage, MFA, and
lockout policy.

---

## 5. MFA — TOTP as a second factor

```bash
bao auth enable totp
bao write auth/totp/keys/alice-rahman type=otp
# → returns the base32 secret; scan it in an authenticator app
```

Or require MFA at the **role** level (recommended):
```bash
bao write auth/oidc/roles/platform-admin \
  mfa_require=true
```

**Why MFA matters for a secret store:** an OpenBao token is often a
complete-compromise credential. Password-only auth means a phished
password gives an attacker the whole vault.

---

## 6. Choosing the right method — decision table

| Situation | Use |
|---|---|
| Company runs Keycloak/Okta/Entra | **OIDC** |
| CI/CD pipeline, container, IoT | **AppRole** |
| Kubernetes workload | **Kubernetes** auth |
| Mutual-TLS clients | **cert** auth |
| Tiny team, no IdP, short-lived lab | **userpass** (+ TOTP) |
| Service-to-service, already in OpenBao | **JWT** auth |

---

**Next:** [Module 06 — Crypto Tooling](06-crypto-tooling/)
