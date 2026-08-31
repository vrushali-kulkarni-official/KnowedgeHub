# Keycloak, OAuth/OIDC/JWT, and Infisical — A Complete Course for Your AI SaaS Stack

> A beginner-to-advanced walkthrough with production-grade implementation steps for **Keycloak**, **OAuth 2.0/2.1**, **OpenID Connect**, **JWT**, and **Infisical** — wired into your Python / FastAPI / Docker / Cloudflare stack.

**Stack you told me about:** Python, FastAPI, PostgreSQL, MongoDB, Qdrant, LangChain, LangGraph, Deep Agents, Redis, Docker Compose, Git, GitHub, GitHub Actions, GHCR, Docker Hub, WatchTower, Ubuntu 26, CloudFlare DNS, CloudFlare Tunnel.

**Stack I will add to it:** Keycloak (identity), Infisical (secrets + PKI), Traefik (reverse proxy, optional). All free, all open source, all production-grade.

**What you will get from this course:**

1. A mental model of *why* authentication, authorization, and secrets are three different problems
2. The JWT/OAuth/OIDC layered model in plain language
3. A production-ready Keycloak setup (Docker Compose, PostgreSQL, reverse proxy, HA-ready)
4. A production-ready Infisical setup (Docker Compose, PostgreSQL, Redis, machine identities)
5. End-to-end FastAPI integration code (token validation, role-based access)
6. A Cloudflare Tunnel + Cloudflare Access front for the entire stack
7. A security-hardening checklist
8. A bootstrap script and `docker-compose.yml` you can copy and run

---

## Table of Contents

- **Module 0** — Why central auth and central secrets matter
- **Module 1** — JSON Web Tokens (JWT), from scratch
- **Module 2** — OAuth 2.0 and OAuth 2.1
- **Module 3** — OpenID Connect (OIDC)
- **Module 4** — Keycloak in depth
- **Module 5** — Infisical in depth
- **Module 6** — Reverse proxy, TLS, and Cloudflare Tunnel
- **Module 7** — FastAPI integration (code, with explanations)
- **Module 8** — End-to-end implementation: bootstrap your full stack
- **Module 9** — Production security hardening checklist
- **Module 10** — What to learn next, and what to ignore

---

## Module 0 — Why Central Auth and Central Secrets Matter

Before you write a single line of code, you need a mental model. Almost every security disaster in the history of software came from teams thinking *"we can roll our own auth later."* Don't be that team.

### 0.1 The three problems people confuse

Most developers conflate three different problems. They are not the same problem, and the solutions to each are different libraries, different protocols, and different operational models.

| Problem | What it answers | Example question | Typical solution |
| --- | --- | --- | --- |
| **Authentication** (AuthN) | *Who is this user?* | "Is this request really from Alice?" | OIDC, SAML, Keycloak |
| **Authorization** (AuthZ) | *What is this user allowed to do?* | "Can Alice delete this record?" | OAuth 2.0 scopes, RBAC, Keycloak roles |
| **Secrets management** | *Where do we keep API keys, DB passwords, TLS certs?* | "How does my FastAPI process get the DB password without it being in `.env` on the dev's laptop?" | Infisical, HashiCorp Vault, OpenBao |

A common beginner mistake: "I'll just put passwords in the database, hash them with bcrypt, and write my own session middleware." That solves *one* piece of authentication for *one* app. It does not solve:

- Single sign-on (SSO) across multiple apps
- Federated identity (let users log in with Google, GitHub, Microsoft)
- Multi-factor authentication (MFA / TOTP / passkeys)
- Password reset flows
- Account lockout after failed logins
- Audit logs of who did what, when
- Token revocation when a user is fired
- Centralized enforcement of password complexity rules
- Anomaly detection (impossible travel, brute force)

Every one of those is something Keycloak does out of the box. Every one of them is also a place custom auth code introduces vulnerabilities. **The most dangerous part of any auth system is the part the team did not write.**

### 0.2 The "central auth" security model

Instead of every app having its own login, you have one **identity provider** (Keycloak) and every app delegates auth to it. The apps trust Keycloak, not the user's password.

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ FastAPI  │     │ Streamlit│     │ Landing  │
│ Backend  │     │ Frontend │     │ Page     │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     │  OIDC / OAuth  │  OIDC / OAuth  │  OIDC / OAuth
     ▼                ▼                ▼
   ┌──────────────────────────────┐
   │   Keycloak (Identity Hub)    │
   │   - Users / Groups / Roles   │
   │   - Passwords / MFA / Passkey│
   │   - OIDC & SAML & OAuth 2.0  │
   │   - Audit logs               │
   └──────────────────────────────┘
```

If a vulnerability is discovered in the auth flow, you patch **one** place, and every app gets the fix. If a user is fired, you revoke their session in **one** place, and they lose access to every app immediately. If a regulator asks "who accessed this data on March 15?", you have a single audit log to query.

This is the same architecture used by Google Workspace, GitHub Enterprise, Salesforce — but you can self-host it free with Keycloak.

### 0.3 The "central secrets" security model

Same logic, different domain. Instead of `.env` files scattered across developer laptops, CI runners, and production servers, secrets live in one encrypted vault (Infisical). Apps fetch what they need at startup, with a short-lived token that expires.

```
┌──────────────┐  short-lived tokens  ┌──────────────┐
│   FastAPI    │ ───────────────────► │  Infisical   │
│   Worker     │                      │  (Vault)     │
│   CI/CD      │ ◄─────────────────── │              │
└──────────────┘  secrets as env vars └──────────────┘
```

Why this matters:

- A developer's laptop is stolen → no production secrets on disk
- A log line accidentally prints an env var → no real secret leaks because the secret was a *reference*, not the value
- A secret needs to be rotated → you rotate it in one place, and every connected service picks up the new value within seconds
- An audit shows "who read the DB password, and when" → you have a queryable log

### 0.4 What "free" actually means in this stack

| Tool | License | Who else uses it |
| --- | --- | --- |
| Keycloak | Apache 2.0 | Red Hat builds and sells a supported version (RH-SSO); the community version is identical core code |
| Infisical | MIT | Y Combinator-backed; thousands of companies |
| Traefik | MIT | Used by millions of Docker deployments |
| PostgreSQL | PostgreSQL License | The world's most-used database |
| Redis | BSD | Industry standard cache / queue |
| FastAPI | MIT | Industry standard Python async framework |
| PyJWT | MIT | Used by Django, Flask-JWT-Extended, FastAPI |

There is no "free but worse" here. You are using the same code that companies pay six figures a year to license with support contracts. The only thing you give up is the support ticket.

---

## Module 1 — JSON Web Tokens (JWT), From Scratch

JWT is the token format that almost every modern auth system uses. You will see it inside Keycloak, OAuth, OIDC, and dozens of other places. If you do not understand JWT deeply, you cannot debug auth issues, you cannot reason about token expiration, and you cannot spot the security footguns.

### 1.1 What a JWT actually is

A JWT is a string that looks like this:

```
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkFsaWNlIiwiZW1haWwiOiJhbGljZUBleGFtcGxlLmNvbSIsImV4cCI6MTczNTY4OTYwMH0.signature_here_abc123
```

Three parts, separated by dots:

1. **Header** (base64url-encoded JSON)
2. **Payload** (base64url-encoded JSON)
3. **Signature** (cryptographic signature over the first two)

Each part is base64url-encoded — that means anyone with the token can read it. *Encoding is not encryption.* A JWT is a signed JSON, not an encrypted one. If you need encrypted, that is JWE (JSON Web Encryption), which is a different thing.

Let's decode the parts:

```json
// Header
{
  "alg": "RS256",   // signing algorithm
  "typ": "JWT",     // token type
  "kid": "key-2024" // key ID, used to look up the verification key
}

// Payload
{
  "sub": "1234567890",     // subject = user ID
  "name": "Alice",
  "email": "alice@example.com",
  "exp": 1735689600,        // expiration time (Unix epoch seconds)
  "iat": 1735686000,        // issued at
  "iss": "https://auth.your-saas.com/realms/prod",  // issuer
  "aud": "fastapi-backend" // audience = intended recipient
}

// Signature
RSASSA-PKCS1-v1_5-SHA256(
  base64url(header) + "." + base64url(payload),
  private_key_of_issuer
)
```

Anyone can read the payload, but only the holder of the issuer's private key can create a valid signature. Conversely, anyone with the issuer's *public* key can verify that a signature was made by that issuer. The math is asymmetric.

### 1.2 The three signing algorithm families

| Family | Algorithms | Key model | When to use |
| --- | --- | --- | --- |
| **HMAC** (symmetric) | HS256, HS384, HS512 | One shared secret signs *and* verifies | Same service issues and verifies; high-entropy secret (32+ random bytes) |
| **RSA / ECDSA / EdDSA** (asymmetric) | RS256, ES256, EdDSA, PS256 | Private key signs, public key verifies | Distributed systems: one issuer, many verifiers |
| **none** | `none` | No signature | **Never use in production. This is a footgun. Reject on sight.** |

For Keycloak, which is the central identity provider in your stack, the right choice is asymmetric (RS256, ES256, or EdDSA). Why?

- Your FastAPI service can verify a token using Keycloak's *public* key
- Your FastAPI service does not have any secret that lets it *forge* tokens
- A compromise of your FastAPI service cannot escalate into a token-minting capability

This is the principle of **least privilege for verifiers**: they should not be able to mint, only check.

### 1.3 The standard claims you must understand

These are the fields you'll see in every OIDC-compliant token. They have precise meanings defined by RFC 7519 and the OIDC core spec.

| Claim | Full name | Meaning |
| --- | --- | --- |
| `iss` | Issuer | URL of the token issuer. For Keycloak: `https://auth.your-saas.com/realms/prod` |
| `sub` | Subject | A stable, unique identifier for the user. For Keycloak: a UUID per user per realm |
| `aud` | Audience | The intended recipient. For an access token intended for the FastAPI API: the client ID of the API. **This is your protection against token-substitution attacks.** |
| `exp` | Expiration | Unix epoch seconds. The token must be rejected after this time. |
| `iat` | Issued at | Unix epoch seconds. When the token was minted. |
| `nbf` | Not before | Unix epoch seconds. The token is invalid before this time. |
| `jti` | JWT ID | A unique identifier for this specific token. Used for replay detection and revocation. |
| `auth_time` | Authentication time (OIDC-specific) | When the user actually authenticated. Useful for step-up auth. |
| `acr` | Authentication context class reference (OIDC) | What level of auth was done (e.g., `0` = password, `1` = MFA, `2` = passkey) |
| `amr` | Authentication methods reference (OIDC) | Array of methods used, e.g. `["pwd", "otp", "passkey"]` |
| `nonce` | Nonce (OIDC) | Random value the client set in the auth request, echoed back in the ID token. Prevents replay. |
| `scope` | Scope (OAuth) | Space-separated list of permissions, e.g. `openid profile email` |
| `realm_access` | Keycloak custom | `{ "roles": ["user", "admin"] }` — realm-level roles |
| `resource_access` | Keycloak custom | `{ "fastapi-backend": { "roles": ["api-admin"] } }` — client-level roles |

For FastAPI specifically, you'll inspect `sub` to know *which* user is calling, `aud` to confirm the token was meant for *your* service, `exp` to know if it's still valid, and `realm_access` / `resource_access` for role checks.

### 1.4 How signature verification actually works

This is the part most tutorials gloss over. When your FastAPI service receives a token, it does this:

1. Parse token into header.payload.signature
2. Read header.kid (key ID)
3. Fetch the issuer's public keys from `<issuer>/.well-known/openid-configuration` → that JSON has `jwks_uri`, which points to the JWKS endpoint
4. Find the public key whose `kid` matches the token's header.kid
5. Verify the signature using that public key and the algorithm in header.alg
6. Verify that the current time is before exp and after nbf (with small clock skew tolerance)
7. Verify that iss matches the expected issuer (exact match, not substring)
8. Verify that aud contains your service identifier
9. If any check fails → reject with 401 Unauthorized

Steps 3 and 4 are key. Keycloak publishes its signing keys at:

```
https://auth.your-saas.com/realms/<realm>/protocol/openid-connect/certs
```

This endpoint is called the **JWKS** (JSON Web Key Set) endpoint. It returns a JSON document listing every public key the realm currently uses to sign tokens. Keycloak rotates these keys periodically. Your FastAPI service must:

- Cache the JWKS document (don't fetch it on every request — that's a DoS waiting to happen)
- Refresh the cache when it sees an unknown `kid`
- Verify that the `kid` is actually one of the keys Keycloak published (not one an attacker invented)

### 1.5 Common JWT attacks and why naive code is dangerous

These are real CVEs from real systems. Read them. Then never write that code.

**Attack 1: `alg: none`**

In 2015, a famous vulnerability surfaced: a library accepted tokens with `"alg": "none"` and treated them as valid. The attacker could mint a token with whatever claims they wanted, the library would skip signature verification, and the attacker was in.

```
# This token should be REJECTED, but vulnerable libraries accept it
eyJhbGciOiJub25lIn0.eyJzdWIiOiJhZG1pbiIsImV4cCI6OTk5OTk5OTk5OX0.
```

Defense: always pass an explicit `algorithms=["RS256"]` list to your JWT library. Never let `alg` from the header determine which algorithm you use.

**Attack 2: Algorithm confusion (HS256 vs RS256)**

This is the one the libraries have actually gotten wrong. The attack: the verifier code says "use the algorithm in the token header." An attacker sends an HS256-signed token. The library interprets the *public key* (which the verifier fetched as an RSA public key) as an HMAC shared secret. The attacker signs with the public key, the library verifies with the same public key, and accepts the token.

This is **CVE-2026-48526** in PyJWT 2.x and a long history in other libraries [1]. Defense: pin the algorithm. Do not derive it from the token.

**Attack 3: Weak HMAC secret**

HS256 with a 6-character secret is brute-forceable in seconds. Defense: 32+ random bytes if you must use HMAC. But for distributed systems, use asymmetric.

**Attack 4: Not validating `exp`**

If your code does not check expiration, a leaked token is valid forever. Always check `exp`.

**Attack 5: Not validating `aud`**

If your code accepts a token meant for service A when validating a request to service B, an attacker can use service A's token to call service B. Always check `aud`.

**Attack 6: Trusting the user-id (`sub`) without re-checking**

JWT payload is *not* a database. If you need current user attributes (email, role, status), query your database after validating the token. JWT roles can go stale.

### 1.6 JWT is *not* a session. Stop treating it like one.

This is the most common architectural mistake. A JWT is a **signed statement of claims at a point in time**. It is not state.

- You cannot reliably "revoke" a JWT before its `exp`. There is no central list of "live tokens" in the default setup. (You can build one with token introspection, but it's not free.)
- A token with 24-hour expiry is valid for 24 hours, period. If a user logs out, the token still works until `exp`.
- A token with role `admin` in the payload is an admin until `exp`, even if you just removed the role from the user.

The right architecture:

- Access tokens: short lifetime (5–15 minutes)
- Refresh tokens: longer lifetime, stored server-side, revocable
- A logout endpoint that revokes the *refresh* token, ending the session
- For sensitive operations, call the userinfo endpoint or query your DB

### 1.7 Mental model summary

A JWT is a sealed envelope with a wax stamp. The envelope is not locked — anyone can read it. But the stamp proves it came from the issuer, and the signature proves no one tampered with the contents. Your job, as a verifier, is to check the seal, check the date, check the addressee, and reject anything that fails.

---

## Module 2 — OAuth 2.0 and OAuth 2.1

OAuth 2.0 is the most widely deployed authorization protocol in the world. Every "Sign in with Google" button you've ever clicked uses it. It is also widely misunderstood, and the misunderstandings lead to real vulnerabilities.

### 2.1 What OAuth is — and what it is not

**OAuth 2.0 is an authorization delegation framework.** It is *not* an authentication protocol. Saying "we use OAuth to log in" is a category error. Authentication answers "who is this user?" OAuth answers "is this user allowed to access this resource on my behalf?"

The protocol that *is* authentication is **OpenID Connect (OIDC)**, which is built *on top of* OAuth 2.0. OIDC adds the ID token that proves identity. We will cover OIDC in Module 3.

This confusion causes real bugs. A team uses OAuth's access token to authenticate the user, stores the `sub` claim, and never verifies that the user actually exists. Then an attacker can mint a fake token (or replay a leaked one), pass it to the API, and the API trusts it because the signature is valid — but the user might have been deleted, banned, or never existed.

### 2.2 The four roles

OAuth defines four roles. Every flow involves all four.

| Role | What it is | Example |
| --- | --- | --- |
| **Resource Owner** | The human (or sometimes a machine) who owns the data | You, when you click "Allow" on a Google sign-in dialog |
| **Client** | The app that wants to act on the resource owner's behalf | A third-party calendar app wanting to read your Google Calendar |
| **Authorization Server** | The service that authenticates the user and issues tokens | Google, Keycloak, Okta, Auth0 |
| **Resource Server** | The API that holds the protected data | Google Calendar API |

In your stack, Keycloak is the Authorization Server. Your FastAPI backend is the Resource Server. The user's browser session is the Resource Owner. The Streamlit frontend or LangChain agent is the Client.

### 2.3 The grant types you need to know

A "grant type" is the mechanism a client uses to obtain an access token. OAuth 2.0 has six, but two of them are deprecated (Implicit, Resource Owner Password) and two are very specialized. For 95% of real apps, you need exactly three.

#### 2.3.1 Authorization Code + PKCE (for any user-facing client)

This is the canonical flow. It is mandatory in OAuth 2.1 for *all* clients, including confidential server-side ones.

**The flow:**

```
┌─────────┐                ┌─────────┐               ┌─────────┐
│  User   │                │ Client  │               │   AS    │
│ (RO)    │                │ (App)   │               │ (KC)    │
└────┬────┘                └────┬────┘               └────┬────┘
     │                          │                         │
     │ 1. Click "Login"         │                         │
     ├─────────────────────────►│                         │
     │                          │                         │
     │                          │ 2. Generate              │
     │                          │    code_verifier (random│
     │                          │    43-128 chars)        │
     │                          │    code_challenge =     │
     │                          │    SHA256(verifier)     │
     │                          │                         │
     │                          │ 3. 302 Redirect          │
     │                          │    to /authorize?       │
     │                          │    response_type=code   │
     │                          │    &client_id=...       │
     │                          │    &redirect_uri=...    │
     │                          │    &scope=openid+profile│
     │                          │    &code_challenge=...  │
     │                          │    &code_challenge_     │
     │                          │     method=S256         │
     │ 4. Browser follows redirect                        │
     ├───────────────────────────────────────────────────►│
     │                          │                         │
     │ 5. Login form            │                         │
     │◄──────────────────────────────────────────────────┤
     │                          │                         │
     │ 6. Submit credentials    │                         │
     ├───────────────────────────────────────────────────►│
     │                          │                         │
     │ 7. AS redirects back     │                         │
     │    to redirect_uri       │                         │
     │    with ?code=xyz123     │                         │
     │◄──────────────────────────────────────────────────┤
     │ 8. Browser follows       │                         │
     │    redirect              │                         │
     ├─────────────────────────►│                         │
     │                          │                         │
     │                          │ 9. POST /token          │
     │                          │    grant_type=          │
     │                          │     authorization_code  │
     │                          │    &code=xyz123         │
     │                          │    &code_verifier=...   │
     │                          │    &client_id=...       │
     │                          │    (if confidential:    │
     │                          │     &client_secret=...) │
     │                          ├────────────────────────►│
     │                          │                         │
     │                          │ 10. AS verifies:        │
     │                          │    - code is valid      │
     │                          │    - code_verifier      │
     │                          │      hashes to the      │
     │                          │      stored challenge   │
     │                          │    - client identity    │
     │                          │                         │
     │                          │ 11. Return tokens       │
     │                          │◄────────────────────────┤
     │                          │  {                     │
     │                          │    access_token,       │
     │                          │    id_token,           │
     │                          │    refresh_token,      │
     │                          │    expires_in          │
     │                          │  }                     │
     │                          │                         │
     │                          │ 12. Use access_token    │
     │                          │     to call API:        │
     │                          │     Authorization:      │
     │                          │      Bearer <token>     │
```

**Why PKCE matters (the security argument):**

Without PKCE, the authorization code is the only thing protecting the user's identity. If an attacker can intercept the redirect (a malicious browser extension, a phishing site, a poorly-configured mobile app), they get the code, exchange it for tokens at the token endpoint (they have the `client_id`; for confidential clients they also need the `client_secret`, but for public clients — SPAs, mobile — they don't), and now they're authenticated as the user.

With PKCE, the attacker also needs the `code_verifier` — a 43-character random string the client generated locally and never sent over the wire. Without it, the token endpoint rejects the code. PKCE binds the token exchange to the client that initiated the request.

**Use this flow for:**

- FastAPI backend with a frontend (Streamlit, React, Vue)
- Single-page applications (SPAs)
- Mobile apps
- Native desktop apps

#### 2.3.2 Client Credentials (for machine-to-machine)

No user. No browser. Service A authenticates to Keycloak with its `client_id` and `client_secret`, gets an access token, and calls Service B.

```
┌──────────┐                              ┌──────────┐
│ Service  │                              │   Keycloak│
│   A      │                              │          │
└────┬─────┘                              └────┬─────┘
     │                                         │
     │ POST /token                            │
     │   grant_type=client_credentials         │
     │   client_id=service-a                  │
     │   client_secret=abc123                 │
     ├────────────────────────────────────────►│
     │                                         │
     │ { access_token: "eyJ...", expires_in:600 }│
     │◄────────────────────────────────────────┤
     │                                         │
     │ GET /api/some-resource                 │
     │   Authorization: Bearer eyJ...         │
     ├──────────►  (to Service B)              │
```

**Use this for:**

- A backend service calling another backend service
- A scheduled job / cron task
- Your LangChain agent calling internal APIs
- A CI/CD pipeline calling your deployment API

**Important:** In Keycloak, you must enable "Service accounts roles" on the client for this to work. By default, only the `admin-cli` client has it.

#### 2.3.3 Refresh Token

Access tokens are short-lived (5–15 minutes). Refresh tokens are long-lived (hours to days). The client uses the refresh token to get a new access token without bothering the user.

```
┌─────────┐                              ┌─────────┐
│ Client  │                              │   KC    │
└────┬────┘                              └────┬────┘
     │                                         │
     │ 1. Initial login                       │
     │   {                                    │
     │     access_token,                      │
     │     refresh_token,                     │
     │     expires_in: 600                    │
     │   }                                    │
     │                                         │
     │ ... 10 minutes pass ...                │
     │                                         │
     │ 2. POST /token                         │
     │    grant_type=refresh_token            │
     │    refresh_token=old_refresh           │
     ├────────────────────────────────────────►│
     │                                         │
     │ 3. { new access_token,                 │
     │      new refresh_token }               │
     │◄────────────────────────────────────────┤
```

**Keycloak default:** refresh tokens are single-use. Every refresh issues a new refresh token and invalidates the old one. This is called **refresh token rotation**, and it's required by OAuth 2.1 for public clients because it limits the damage of a stolen refresh token (the attacker uses it once, the legitimate user's next refresh fails, and the system detects the breach).

**You can disable rotation** in Keycloak, but you probably shouldn't. Rotation is the secure default.

#### 2.3.4 Deprecated flows you should NOT use

- **Implicit grant** (`response_type=token`): tokens were returned in the URL fragment. Vulnerable to history-theft and referrer leaks. Removed in OAuth 2.1.
- **Resource Owner Password Credentials (ROPC)**: the app collected the user's username and password directly. This is what the early "Sign in with Facebook" apps did, and it's why we have to trust random apps with our passwords. Deprecated in OAuth 2.0, removed in OAuth 2.1.
- **Client credentials with a public client**: public clients can't keep secrets, so they shouldn't use the client credentials flow. Use authorization code + PKCE instead.

### 2.4 OAuth 2.1 — what's new and why you should care

OAuth 2.1 is the in-progress consolidation of OAuth 2.0 with ten years of security best practices [2]. It removes the deprecated flows and makes PKCE mandatory for everyone.

| Change | OAuth 2.0 | OAuth 2.1 |
| --- | --- | --- |
| PKCE for authorization code flow | Optional (recommended for public clients) | **Mandatory for all clients** |
| Implicit grant | Allowed | **Removed** |
| Resource Owner Password Credentials | Allowed (discouraged) | **Removed** |
| Redirect URI matching | Loose (some implementations allowed wildcards) | **Exact string match only** |
| Refresh tokens for public clients | Allowed with caveats | **Must be sender-constrained OR rotated** |
| Bearer tokens in URL query strings | Allowed | **Discouraged; use header or body** |
| Client types | Confusing trichotomy | Simplified: confidential = has credentials, public = doesn't |

Keycloak has supported all of these for years. If you configure Keycloak correctly, you are already OAuth 2.1 compliant.

### 2.5 Scopes

Scopes are how the client tells the authorization server *what* it wants access to. They are space-separated strings in the authorization request:

```
scope=openid profile email https://your-api.com/scope/admin
```

The `openid` scope is what makes the request an OIDC request instead of plain OAuth. The other standard scopes (`profile`, `email`, `address`, `phone`) are OIDC-defined. Anything else is application-defined.

The authorization server may not grant all the requested scopes. It will return only the ones it approved, and the access token will reflect the granted set.

### 2.6 Mental model summary

OAuth 2.0 is a delegation protocol. A user goes to an authorization server, says "I authorize this app to access these resources on my behalf," and the authorization server hands the app a token. The app uses that token at the resource server. Three flows cover 95% of cases: authorization code with PKCE (interactive), client credentials (machine-to-machine), and refresh token (renewal). OAuth 2.1 removes the dangerous old flows and makes PKCE mandatory.

---

## Module 3 — OpenID Connect (OIDC)

OIDC is the layer on top of OAuth 2.0 that adds identity. If you want to know *who* the user is (not just *what they're allowed to do*), you need OIDC.

### 3.1 What OIDC adds

OAuth gives you an access token (a bearer credential for an API). OIDC adds:

1. **ID Token** — a JWT that proves the user just authenticated
2. **UserInfo Endpoint** — an API you call with the access token to get user attributes
3. **Standard Claims** — a defined set of user attributes (name, email, picture, etc.)
4. **Discovery Document** — a JSON at a well-known URL that tells clients everything about the IdP
5. **JWKS Endpoint** — a JSON that lists the IdP's public keys for signature verification
6. **Dynamic Client Registration** — clients can register themselves at runtime
7. **Session Management** — ways to log out, check session, etc.

### 3.2 The ID token vs the access token

This confuses everyone the first time. You get *both* when you complete the authorization code flow.

| | Access token | ID token |
| --- | --- | --- |
| **Format** | Usually JWT (Keycloak) or opaque | Always JWT |
| **Audience** | The resource server (your API) | The client application (your frontend) |
| **Purpose** | Prove the user is authorized for an API call | Prove the user is who they say they are |
| **Lifetime** | Short (5–15 min) | Short (same as access token by default) |
| **Used by** | Backend services | Frontend, then optionally passed to backend |
| **Contains** | Permissions, scopes, roles | Identity claims (name, email, sub, etc.) |
| **Verified by** | Resource server | Client application |

The flow: the client (Streamlit, for example) receives the ID token, verifies it, extracts the user identity, and stores it in session. The client also receives the access token. The frontend can call the backend's API with the access token. The backend verifies the access token and uses the claims to authorize the request.

**Important security rule:** the access token should *not* be sent to anyone who is not the resource server. The ID token should *not* be sent to anyone who is not the client that requested it. The `aud` claim enforces this — your FastAPI service checks that the access token's `aud` matches your service, and your frontend checks that the ID token's `aud` matches the frontend's client ID.

### 3.3 The discovery document

Every OIDC provider publishes a "well-known" JSON document. For Keycloak:

```
https://auth.your-saas.com/realms/<realm>/.well-known/openid-configuration
```

This is the equivalent of an API spec for the identity provider. It tells clients:

```json
{
  "issuer": "https://auth.your-saas.com/realms/prod",
  "authorization_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/auth",
  "token_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/token",
  "userinfo_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/userinfo",
  "jwks_uri": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/certs",
  "end_session_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/logout",
  "revocation_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/revoke",
  "introspection_endpoint": "https://auth.your-saas.com/realms/prod/protocol/openid-connect/token/introspect",
  "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token", "urn:ietf:params:oauth:grant-type:token-exchange"],
  "response_types_supported": ["code", "id_token", "token id_token", "code id_token"],
  "scopes_supported": ["openid", "profile", "email", "address", "phone", "offline_access"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "private_key_jwt"],
  "id_token_signing_alg_values_supported": ["PS384", "ES384", "RS384", "HS256", "HS512", "ES256", "RS256", "HS384", "ES512", "PS256", "PS512", "RS512", "EdDSA"],
  "subject_types_supported": ["public", "pairwise"],
  "code_challenge_methods_supported": ["plain", "S256"]
}
```

The first thing any well-built OIDC client does on startup is fetch this document, cache it, and read the endpoints from it. **You do not hardcode URLs in your app.** You read them from the discovery document. If you move Keycloak to a different domain, the app keeps working.

### 3.4 The userinfo endpoint

The ID token contains a *minimal* set of claims. For more (e.g., the user's profile picture, address, custom attributes), the client calls:

```
GET /realms/<realm>/protocol/openid-connect/userinfo
Authorization: Bearer <access_token>
```

Keycloak returns a JSON document with the user's claims. This is the right place to fetch data that's too large or too sensitive to put in every ID token.

### 3.5 OIDC logout

Logging out is harder than it looks. There are three flavors:

| Flavor | Who initiates | Mechanism |
| --- | --- | --- |
| **RP-Initiated Logout** | The client (relying party) | Client redirects user to Keycloak's `end_session_endpoint`. Keycloak clears the SSO session. Client clears its local session. |
| **Front-Channel Logout** | Keycloak | Keycloak makes a GET request to each registered client's logout URL via the browser |
| **Back-Channel Logout** | Keycloak | Keycloak makes a server-to-server POST to each registered client's back-channel logout URL |

For your use case, RP-initiated is what you want. The frontend redirects to:

```
https://auth.your-saas.com/realms/prod/protocol/openid-connect/logout?client_id=streamlit-frontend&post_logout_redirect_uri=https://app.your-saas.com
```

And Keycloak kills the session.

**Caveat:** RP-initiated logout only kills the user's session *at Keycloak*. If the user has refresh tokens stored in your app, those are still valid until expiry. The cleanest way: on logout, also revoke the refresh token at Keycloak's revocation endpoint, then clear the access token in the app.

### 3.6 Mental model summary

OIDC is OAuth plus identity. The ID token is the proof of authentication; the access token is the credential for authorization; the userinfo endpoint is for additional profile data; the discovery document is the spec; the JWKS endpoint is the public key directory. Implement OIDC and you get single sign-on, logout, profile data, and standards-compliant verification.

---

## Module 4 — Keycloak in Depth

Now we get to the actual product. Keycloak is the open-source identity and access management (IAM) server originally created by JBoss, now maintained by the community under Red Hat's stewardship. It is what companies like Cloudflare, Zalando, and the UK government use to manage millions of identities.

### 4.1 What Keycloak is and isn't

**Keycloak is:** an identity provider, an identity broker, a single sign-on server, a user federation hub, an OAuth 2.0 / OIDC / SAML 2.0 server, a fine-grained authorization server, and a credential manager (passwords, OTP, WebAuthn/passkeys, X.509).

**Keycloak is not:** a database (it stores user data in PostgreSQL/MariaDB/etc., not its own engine), a user-facing directory service for end-users (it's an admin/developer tool with user-facing screens as a byproduct), or a self-service password reset portal out of the box (it has one, but it's basic).

### 4.2 Architecture

As of version 26.x (current stable: 26.7, released July 2026), Keycloak runs on the Quarkus runtime (previously WildFly/JBoss). It is written in Java and requires JDK 21+ for production [3].

```
┌─────────────────────────────────────────────────────────────┐
│  Keycloak Server (Quarkus runtime)                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Admin REST   │  │ Account      │  │ OIDC / SAML      │  │
│  │ API          │  │ Console      │  │ Endpoints        │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────┴─────────────────┴────────────────────┴────────┐  │
│  │         Authentication & Authorization Engine         │  │
│  │  (SPI-based, pluggable authenticators, mappers)       │  │
│  └──────┬─────────────────┬────────────────────┬────────┘  │
│         │                 │                    │            │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌────────┴─────────┐  │
│  │  Infinispan  │  │  User        │  │  Identity        │  │
│  │  (Cache &    │  │  Federation  │  │  Brokering       │  │
│  │  Sessions)   │  │  (LDAP/AD)   │  │  (OIDC/SAML)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
   PostgreSQL (or MariaDB, Oracle, MS SQL, etc.)
```

The key architectural insight: **Keycloak is stateless at the application level**. All persistent state lives in the database. Sessions and short-lived caches live in Infinispan, which is embedded by default but can be externalized for HA across multiple Keycloak instances.

### 4.3 Core concepts

These are the entities you work with. Get these in your head and the rest of Keycloak is just configuration.

| Concept | What it is | When you use it |
| --- | --- | --- |
| **Realm** | A top-level tenant. A realm contains users, clients, roles, groups, identity providers — fully isolated from other realms. | One realm per environment (dev, staging, prod) or per major business unit |
| **Client** | An application that can request authentication. The client is registered with Keycloak. | One client per app: `fastapi-backend`, `streamlit-frontend`, `langchain-agent` |
| **User** | An end-user account. Has a username, email, attributes, credentials. | Every person who logs in |
| **Group** | A named collection of users. Used for bulk role assignment. | "engineering", "billing", "beta-testers" |
| **Role** | A named permission. Two types: realm roles (global to the realm) and client roles (scoped to one client). | "admin", "user", "billing-manager", "api-reader" |
| **Composite Role** | A role that contains other roles. When assigned, all child roles come with it. | "super-admin" = realm admin + several client-specific roles |
| **Client Scope** | A named bundle of protocol mappers and role scope mappings that can be attached to clients. | "openid-profile" scope applied to all OIDC clients |
| **Protocol Mapper** | A piece of code that translates Keycloak data into a token claim. | Add a user's department to a token, or transform a role name |
| **Identity Provider** | A federated IdP that Keycloak can delegate authentication to. | "Log in with Google", "Log in with GitHub", "Log in with corporate SAML" |
| **Authentication Flow** | A configurable sequence of steps: username/password → OTP → WebAuthn. | Custom flow for high-security logins, passwordless, etc. |
| **Required Action** | An action a user must complete before they can do anything else. | Force password change on first login, configure TOTP, verify email |
| **Event** | A record of something that happened (login, token issuance, role assignment). | Audit trail |
| **Theme** | Customizable HTML/CSS for login, account, admin, and email pages. | White-label the login screen |

### 4.4 The two roles, and why you should care

Many tutorials tell you to "create a role." They rarely tell you *which kind* of role.

| | Realm role | Client role |
| --- | --- | --- |
| **Namespace** | The whole realm | One specific client |
| **Appears in token at** | `realm_access.roles` | `resource_access.<client-id>.roles` |
| **Use for** | Cross-cutting permissions: "admin", "user", "billing" | App-specific permissions: "api-reader", "api-writer", "agent-executor" |
| **Best practice** | Few of these, mostly for org-wide tiers | Most of your roles should be these |

The general guideline: **start with client roles**. They are more granular, they don't pollute the global namespace, and they map cleanly to microservice architecture. Promote to realm roles only when a permission truly crosses app boundaries.

### 4.5 Authentication flows

A flow is a sequence of "executions" (e.g., "username + password form", "TOTP challenge", "WebAuthn authentication"). Keycloak ships with three built-in flows:

1. **Browser flow** — username/password → optional OTP → success
2. **Registration flow** — registration form → email verification
3. **Reset credentials flow** — email → click link → set new password

You can copy and customize any of these. The customization is what makes Keycloak powerful:

- Want passwordless with WebAuthn only? Create a new flow, set the WebAuthn authenticator as required, set username/password as disabled.
- Want step-up auth? Make a flow that requires MFA only when accessing a specific client.
- Want conditional auth based on IP? Use a conditional authenticator with an IP condition.

For your AI SaaS, a sensible default:

- Standard users: username/password + WebAuthn (passkey) as optional second factor
- Admins: required WebAuthn
- Service-to-service: client credentials (no flow needed)

### 4.6 Required actions

Required actions are things the user *must* do before their session is useful. Keycloak comes with several:

- **Verify Email** — user clicks a link sent to their email
- **Update Password** — force a password change
- **Configure TOTP** — set up Time-based OTP (Google Authenticator, Authy, etc.)
- **Configure WebAuthn** — register a passkey (YubiKey, Touch ID, Windows Hello)
- **Update Profile** — fill in missing required profile fields
- **Delete Credential** — remove a specific credential
- **Terms and Conditions** — display a T&C page

You configure which actions are *default* (applied to all new users in the realm) and which are *available* (the user can opt in).

### 4.7 Protocol mappers — the underused superpower

A protocol mapper is a piece of code that takes a piece of Keycloak data (a user attribute, a role, a group membership) and translates it into a token claim. This is how you get custom data into your JWT.

Example: you want to put the user's subscription tier in the access token so your FastAPI service can check it without a database call.

1. Create a user attribute called `subscription_tier`
2. Go to Clients → `fastapi-backend` → Mappers → Create
3. Mapper type: User Attribute
4. User attribute: `subscription_tier`
5. Token claim name: `tier`
6. Claim type: String
7. Save

Now every access token for that client will have `"tier": "premium"` (or whatever value) inside.

You can also write mappers in Java or JavaScript. The JavaScript mapper lets you write inline code that transforms Keycloak data into a claim. The Java mapper gives you full power but requires you to deploy a custom Keycloak build (or use the new "Plugin SPIs" feature in 26.x, which is preview).

### 4.8 The Admin REST API

The Admin Console is a nice UI. The real power is the API. The base URL is:

```
{server}/admin/realms
```

To get a token:

```bash
curl -X POST "https://auth.your-saas.com/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli" \
  -d "username=admin" \
  -d "password=YOUR_ADMIN_PASSWORD" \
  -d "grant_type=password"
```

Returns an access token. Use it as a bearer token on Admin API calls:

```bash
TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

# List users in a realm
curl -H "Authorization: Bearer $TOKEN" \
  "https://auth.your-saas.com/admin/realms/prod/users"

# Create a user
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","enabled":true}' \
  "https://auth.your-saas.com/admin/realms/prod/users"

# Assign a role to a user
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '[{"id":"role-uuid","name":"api-admin"}]' \
  "https://auth.your-saas.com/admin/realms/prod/users/{user-uuid}/role-mappings/realm"
```

The Admin API is your friend for scripting user creation, bulk operations, and CI/CD [4].

### 4.9 Fine-grained authorization (UMA 2.0)

Beyond simple role-based access, Keycloak has a "Authorization Services" feature built on UMA 2.0. This lets you define resources, scopes, permissions, and policies in a JSON config, and Keycloak issues a different kind of access token (a "Requesting Party Token" or RPT) that your API can evaluate.

For most use cases, plain RBAC is enough. UMA shines when you have:

- Resources owned by users (Alice's documents, Bob's projects)
- Sharing semantics (Alice shares Document X with Bob for read-only)
- Group-based policies (everyone in the "engineering" group can read)
- Time-based policies (this token is valid only between 9-5)
- Attribute-based policies (only users with `subscription_tier=enterprise` can access this endpoint)

For your AI SaaS, the resource ownership case is interesting — when a user has a private project in Qdrant, you might want a fine-grained policy that says "the project owner can read/write, the project members can read, everyone else cannot." That's a UMA use case.

### 4.10 Token exchange (RFC 8693)

Keycloak supports the OAuth 2.0 Token Exchange spec. This lets you exchange one token for another. The classic use case:

- User logs in to your web app, gets an access token for `web-app`
- Web app wants to call an internal API on behalf of the user
- Web app exchanges its access token for a new access token scoped to the internal API

This is more secure than passing the original token around, because the new token has a narrower audience and a shorter lifetime.

### 4.11 Identity brokering (federation)

Keycloak can act as a broker. Your FastAPI app only knows about Keycloak. Users can log in to Keycloak with their Google, GitHub, Microsoft, or corporate SAML account, and Keycloak translates the external identity into a local user (or just proxies the external user).

This is the "Sign in with Google" button without you having to integrate Google's OAuth directly. You integrate Keycloak once; Keycloak integrates with everything else.

### 4.12 High availability

For a small AI SaaS, a single Keycloak instance is fine. When you grow, you scale to two or more instances behind a load balancer, all pointing at the same PostgreSQL database.

Single-cluster (the default for HA):
- 2+ Keycloak instances
- PostgreSQL with replication
- Embedded Infinispan (each instance has its own cache, but invalidation is coordinated via the DB)
- Load balancer with sticky sessions (or session affinity via cookie)

Multi-cluster v1 (cross-data-center):
- Two Keycloak clusters in two data centers
- External Infinispan cluster with cross-site replication
- Synchronous database replication
- Load balancer that detects site failure

Multi-cluster v2 (newer, 26.7 preview):
- No external Infinispan needed
- Embedded Infinispan only
- Higher DB load (sessions in DB)
- Simpler architecture

For your use case, single-cluster with 2 instances is the right starting point. You scale to multi-cluster only when you have compliance requirements or actual cross-region latency needs [6].

### 4.13 Backup and recovery

Keycloak stores everything in the database. To back up, back up the database. To restore, restore the database. That's it. No separate LDAP dump, no secret store, no extra state.

You should:

- Take automated PostgreSQL dumps at least daily
- Test your restore procedure quarterly
- Encrypt the dumps
- Store the dumps in a different region/zone than the primary

### 4.14 Observability

Keycloak exposes:

- `/health` — liveness/readiness
- `/metrics` — Prometheus-format metrics
- OpenTelemetry traces (supported as of 26.1)
- Structured JSON logs (configurable)

For production, you should:

- Scrape `/metrics` with Prometheus
- Send traces to Jaeger or Tempo
- Pipe logs to Loki or your central log store
- Alert on failed logins, error rates, slow responses

---

## Module 5 — Infisical in Depth

Infisical is the open-source secret management platform. It is to secrets what Keycloak is to identities. Where Keycloak answers "who is this user?", Infisical answers "what's the database password?"

### 5.1 What Infisical is and isn't

**Infisical is:** a secret manager, an internal PKI, a privileged access manager, a secret rotation engine, a dynamic secrets broker, a Kubernetes-native secret store, an SSH certificate authority, and a cryptographic key manager.

**Infisical is not:** HashiCorp Vault. The two products overlap heavily but are not identical. Infisical's UI is more developer-friendly, the API is more consistent, and the open-source feature set is more generous. Vault has more enterprise features and a longer track record.

### 5.2 The mental model

```
┌────────────────────────────────────────────────────────────┐
│  Organization (your company)                                │
│  └── Project: "AI SaaS Backend"                             │
│      ├── Environment: Development                           │
│      │   ├── Folder: /database                              │
│      │   │   ├── POSTGRES_PASSWORD = "dev-pwd-123"          │
│      │   │   └── MONGODB_URI = "mongodb://..."              │
│      │   ├── Folder: /third-party                            │
│      │   │   ├── OPENAI_API_KEY = "sk-..."                  │
│      │   │   └── STRIPE_SECRET_KEY = "sk_test_..."          │
│      │   └── Folder: /feature-flags                         │
│      │       └── ENABLE_BETA = "true"                       │
│      ├── Environment: Staging                               │
│      │   └── (same folder structure, different values)      │
│      └── Environment: Production                            │
│          └── (same folder structure, different values)      │
└────────────────────────────────────────────────────────────┘
```

- **Organization** = the company
- **Project** = one application or product
- **Environment** = a deployment target (dev, staging, prod)
- **Folder** = a grouping within an environment (use them to organize by component: `/database`, `/third-party`, `/feature-flags`)
- **Secret** = a key-value pair. The key is the name, the value is the secret. The value can also be a *reference* to another secret.

### 5.3 Secret references — the killer feature

A secret's value can be a reference to another secret:

```
JWT_SIGNING_KEY = ${INTERNAL_JWT_KEY}
DATABASE_URL = postgresql://user:${POSTGRES_PASSWORD}@db:5432/myapp
```

When the application fetches `DATABASE_URL`, Infisical resolves the reference at read time. This means:

- Rotate `POSTGRES_PASSWORD` once, and every secret that references it gets the new value automatically
- You can have environment-specific overrides: `POSTGRES_PASSWORD` is `dev-pwd` in Development but `prod-XYZ-prod-XYZ` in Production
- References are visible in audit logs, so you can see "this secret depends on these other secrets"

This is one of those features you don't appreciate until you've spent three hours chasing a "rotated the DB password but my service is still using the old one" bug.

### 5.4 Self-hosting Infisical

Infisical self-hosts with Docker Compose. The minimum stack is:

- Infisical backend (Node.js)
- PostgreSQL
- Redis (for caching and queue)

The official docker-compose.prod.yml from the Infisical repo gets you up in 5 minutes. The required environment variables are [8]:

| Variable | What it is | How to generate |
| --- | --- | --- |
| `ENCRYPTION_KEY` | Master key for encrypting secrets at rest | `openssl rand -hex 16` |
| `AUTH_SECRET` | Session cookie signing key | `openssl rand -base64 32` |
| `SITE_URL` | Public URL of Infisical | `https://secrets.your-saas.com` |
| `DB_CONNECTION_URI` | PostgreSQL connection string | `postgresql://user:pass@db:5432/infisical` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379` |

The encryption key is the most critical. **Lose it, lose all your secrets.** Back it up in a separate location (an encrypted USB drive in a safe, a paper backup in a bank vault, whatever fits your threat model). Without it, the encrypted database is unreadable.

### 5.5 Machine identities

A human logs into Infisical with username + password (and ideally MFA). But your FastAPI service is not a human. It needs an identity too. That's a **machine identity**.

A machine identity is an account that:

- Belongs to a service, not a person
- Authenticates with a client ID + client secret (or a more advanced method like Kubernetes service account, AWS IAM, GCP service account, Azure managed identity)
- Has scoped permissions (read-only on specific environments, write on specific folders, etc.)
- Has a revocable, optionally-rotatable secret

The default auth method is **Universal Auth** (client ID + client secret). The more advanced methods:

- **Kubernetes Auth** — your pod uses its service account token to authenticate. No secret to manage. Infisical verifies the token against the K8s API.
- **AWS Auth** — your EC2 instance or Lambda uses its IAM role. No secret to manage.
- **GCP Auth** — your GCE/GKE workload uses its service account. No secret.
- **Azure Auth** — same idea for Azure VMs and AKS.

For your use case with Docker Compose, Universal Auth with a client secret is the right starting point. The secret goes into... Infisical itself (yes, there's a chicken-and-egg, which we'll handle in Module 8 with a bootstrap pattern).

### 5.6 Dynamic secrets

A dynamic secret is one that is generated on-demand when fetched, used for a short time, and then destroyed. The classic use case: a database credential.

Normally, you have a `POSTGRES_PASSWORD` set once and used forever. If that password leaks, the database is compromised. With dynamic secrets:

1. Your app asks Infisical for a "Postgres dynamic secret"
2. Infisical creates a new user in PostgreSQL with a random password
3. The credentials are returned to your app
4. After the lease expires (default 1 hour), Infisical revokes the user from PostgreSQL

The blast radius of a leak is now bounded to the lease duration, not forever. Infisical supports dynamic secrets for:

- PostgreSQL
- MySQL
- MongoDB
- AWS IAM
- GCP IAM
- Azure
- Kubernetes
- Redis
- Elasticsearch

For your AI SaaS, dynamic DB credentials are a meaningful upgrade. Your Qdrant connection strings can be static (they're API keys, not passwords), but your PostgreSQL connection strings should be dynamic.

### 5.7 Internal PKI

This is the other big Infisical feature. A PKI (Public Key Infrastructure) issues and manages X.509 certificates. Why would you want this?

- Internal mTLS between your services (your FastAPI and your Qdrant can authenticate each other with certificates)
- TLS for internal services that aren't behind a public reverse proxy
- SSH certificates for short-lived SSH access to your servers
- Code signing for your releases

Infisical implements a CA hierarchy [9]:

- **Root CA** — the trust anchor, top of the chain. Compromise is fatal.
- **Intermediate CA** — issues end-entity certificates. Can be revoked without invalidating the whole chain.
- **End-entity certificates** — what your services actually use.

Best practice: the root CA is kept offline (or in HSM). Intermediate CAs do the day-to-day issuing. End-entity certs have short lifetimes (30-90 days) and are automatically renewed.

Infisical supports issuance via:

- REST API
- ACME (Let's Encrypt's protocol — Certbot, cert-manager, etc., can use it)
- EST (Enrollment over Secure Transport — for network devices)
- SCEP (Simple Certificate Enrollment Protocol — for older devices)

For a small operation, REST API + cert-manager for K8s is plenty. For your Docker Compose world, REST API is enough; you write a small script that asks Infisical for a cert at deploy time.

### 5.8 SSH certificates

SSH key management is its own nightmare. People generate keys, never rotate them, share them across machines, lose track of which key belongs to which ex-employee. SSH certificates solve this by issuing *short-lived certificates* signed by a CA.

Your users have a CA-trusted SSH cert valid for 8 hours. They log in. After 8 hours, the cert is useless. You don't need to revoke anything; the cert expired. Ex-employees lose access automatically.

Infisical can be your SSH CA. Users authenticate to Infisical (with their OIDC identity, presumably from Keycloak), request an SSH cert, get it for 8 hours, use it. When you fire them, you just remove them from Keycloak. No more grepping `~/.ssh/authorized_keys` across your fleet.

### 5.9 Secret rotation

Manual rotation is a chore nobody does. Automated rotation is a chore you set up once.

Infisical's rotation engine:

1. Generates a new secret value
2. Stores it as a "pending" version
3. Sends notifications to subscribed services (via webhooks, or you can poll)
4. After the grace period, promotes it to "active" and invalidates the old value
5. Audits the whole process

For database passwords, the typical pattern is "dual rotation" — the new password is added to the DB alongside the old one, the application is updated to use the new one, the old one is removed. The grace period is when both work. If something breaks, you can roll back to the old one.

### 5.10 What "free" means here

| Infisical feature | Free / OSS | Cloud paid tier |
| --- | --- | --- |
| Unlimited secrets | Yes | Yes |
| Unlimited environments | Yes | Yes |
| Unlimited users | Yes (with team limits) | Yes |
| Machine identities | Yes | Yes |
| Secret rotation | Yes | Yes |
| Dynamic secrets | Yes | Yes |
| Internal PKI | Yes | Yes |
| SSH certificates | Yes | Yes |
| Audit logs | Yes | Longer retention |
| HSM integration | Yes | Yes |
| SAML SSO (to log in to Infisical itself) | Limited | Yes |

You can run the entire OSS feature set for free. The paid tier is for compliance-grade audit retention, multi-org, and SAML/SSO login to the Infisical console.

---

## Module 6 — Reverse Proxy, TLS, and Cloudflare Tunnel

Your Keycloak and Infisical are running on private IPs. How do users reach them safely? And how do you avoid opening inbound ports on your server?

### 6.1 The reverse proxy role

A reverse proxy sits in front of your services and:

- Terminates TLS (so the app doesn't have to)
- Routes requests to the right backend by hostname or path
- Adds security headers
- Handles gzip, rate limiting, request size limits
- Optionally caches

For Keycloak, the reverse proxy is **required** if you don't want to manage TLS in Keycloak itself. Keycloak is strict about its hostname configuration because the issuer URL in tokens must match the URL the user actually used.

Common choices:

- **Traefik** — Docker-native, dynamic config via labels, automatic Let's Encrypt. The default for Docker Compose.
- **Caddy** — Automatic HTTPS with zero config. Smaller community than Traefik for Docker.
- **Nginx** — The workhorse, the most documentation, the most setup steps. Excellent when you have a complex config.
- **HAProxy** — Used in many of Keycloak's own HA docs. Best for raw load balancing performance.

For your stack, Traefik is the right choice. It reads labels off your Docker services, auto-discovers them, and handles TLS with Let's Encrypt without you writing a single nginx.conf.

### 6.2 Cloudflare Tunnel — the secret weapon

Cloudflare Tunnel is the most underrated security feature in the self-hosting world. It works like this:

```
┌──────────┐                  ┌─────────────┐
│  User    │                  │  Cloudflare │
│ Browser  │                  │  Edge       │
└────┬─────┘                  └──────┬──────┘
     │                                │
     │  HTTPS request to              │
     │  auth.your-saas.com            │
     ├───────────────────────────────►│
     │                                │
     │                                │ Outbound QUIC/TCP
     │                                │ connection from your
     │                                │ server to Cloudflare
     │                                │ (port 7844)
     │                                │   ┌──────────────────┐
     │                                ├──►│  cloudflared     │
     │                                │   │  (in your Docker)│
     │                                │   └────────┬─────────┘
     │                                │            │
     │                                │            ▼
     │                                │   ┌────────────────┐
     │                                │   │ Traefik        │
     │                                │   │ Keycloak       │
     │                                │   │ Infisical      │
     │                                │   │ FastAPI        │
     │                                │   └────────────────┘
```

The critical insight: **your server makes an outbound connection to Cloudflare**. There are no inbound ports. No firewall rules. No "wait, do I need to forward port 443 on my router?" Your home IP is never exposed. You cannot be port-scanned because you have no open ports.

This works because `cloudflared` (the Cloudflare daemon) runs as a Docker container, opens an outbound QUIC connection to Cloudflare's edge, and Cloudflare routes requests for your domain down that connection.

The DNS record for `auth.your-saas.com` points to Cloudflare's network, not to your IP. Anyone who does `dig auth.your-saas.com` sees a Cloudflare IP, not your server. If your home IP changes, the tunnel keeps working.

This is the same model Cloudflare uses for their enterprise customers paying $X,000/month. You get it for free [7].

### 6.3 Cloudflare Access — defense in depth

Cloudflare Access is a zero-trust access layer. You put it in front of any application. The user hits your domain, Cloudflare intercepts, demands authentication (via OIDC — e.g., Keycloak), checks the policy (is this email allowed? is this IP allowed? does this user have the right group?), and only then proxies the request to your server.

This is **additional** to Keycloak. Why both?

- Keycloak is the source of truth for identity and authentication
- Cloudflare Access is the network-level gate that blocks traffic before it even reaches your server
- Even if an attacker steals a user's session cookie, they can't reach your server without first going through Cloudflare's edge (which is a different attack surface)
- Cloudflare Access can enforce IP-based, geo-based, and device-based policies that Keycloak doesn't natively handle

Configuration flow:

1. Create a Cloudflare Tunnel for your domain
2. Add a public hostname (`auth.your-saas.com` → `http://traefik:80`)
3. In Cloudflare Zero Trust, create an Access application for `auth.your-saas.com`
4. Configure an OIDC IdP pointing to your Keycloak realm
5. Set a policy: "Allow users in Keycloak group `admins`"
6. (Optional) Add a One-Time PIN MFA requirement

Now an attacker who somehow gets a Keycloak session token still needs to come through Cloudflare, which checks for a valid Access JWT in addition to whatever Keycloak token they're carrying.

### 6.4 The complete network architecture

```
Internet
   │
   ▼
Cloudflare Edge (TLS termination, DDoS protection, WAF, Access policies)
   │
   │ (outbound connection from cloudflared)
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│  Your Docker Host (Ubuntu 26)                                │
│                                                              │
│  ┌─────────────────┐                                         │
│  │  cloudflared    │ ◄── outbound only, port 7844            │
│  └────────┬────────┘                                         │
│           │                                                  │
│  ┌────────▼────────┐                                         │
│  │  Traefik        │ ◄── internal port 443, no public exposure│
│  │  (TLS optional) │                                         │
│  └────────┬────────┘                                         │
│           │                                                  │
│  ┌────────┴────────┬──────────────┬──────────────┐            │
│  ▼                 ▼              ▼              ▼            │
│ Keycloak        Infisical      FastAPI       Streamlit       │
│  :8080           :8080          :8000         :8501           │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │Postgres │  │Postgres │  │MongoDB  │  │Qdrant   │         │
│  │(Keycloak│  │(Infisi- │  │         │  │         │         │
│  │  DB)    │  │  cal)   │  │         │  │         │         │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘         │
│                                                              │
│  ┌─────────┐  ┌─────────┐                                    │
│  │ Redis   │  │  Redis  │                                    │
│  │(Keycloak│  │(Infisi- │                                    │
│  │ cache)  │  │  cal)   │                                    │
│  └─────────┘  └─────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

No ports are open to the internet. All traffic flows through Cloudflare's edge, through the tunnel, to your services. Your services only talk to each other over the internal Docker network.

---

## Module 7 — FastAPI Integration (Code, With Explanations)

Now the fun part. We wire Keycloak to your FastAPI service so it validates JWTs and enforces roles.

### 7.1 The choice of JWT library

As of mid-2026, there are two viable Python JWT libraries: **PyJWT** and **python-jose** [1].

| | PyJWT | python-jose |
| --- | --- | --- |
| Maintained | Yes (active in 2026) | Yes (resumed 2025 after a 3.7-year gap) |
| Algorithm support | HS*, RS*, ES*, EdDSA, PS* | HS*, RS*, ES*, PS* |
| JWE support | No | Yes |
| Used by | Django, Flask-JWT-Extended, FastAPI (now) | Legacy code |
| Pin to | 2.10+ to avoid CVE-2026-48526 (HS256/RS256 confusion when JWKs are mixed) | 3.5.0+ |

For this course we use **PyJWT** because:

- FastAPI's own documentation moved to it in 2024 [5]
- It is the most-downloaded JWT library on PyPI
- It has a clean API that is hard to misuse
- We do not need JWE (encrypted tokens) for OIDC; we need JWS (signed)

`requirements.txt`:

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
PyJWT[crypto]>=2.10.0
httpx>=0.28.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
python-dotenv>=1.0.0
```

Note: `PyJWT[crypto]` installs the optional `cryptography` package, which gives you RS256/ES256/EdDSA support. Without it, you're stuck on HS256.

### 7.2 Configuration

Create `config.py`:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Every value has a default, but in production we always pass these 
    explicitly (via Infisical, Docker, or systemd).
    """
    
    # Keycloak connection
    keycloak_url: str = "https://auth.your-saas.com"
    keycloak_realm: str = "prod"
    keycloak_client_id: str = "fastapi-backend"
    
    # Optional: client secret for confidential clients doing client_credentials
    # (NOT used for user JWT validation)
    keycloak_client_secret: str = ""
    
    # Computed URLs
    @property
    def issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"
    
    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"
    
    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/token"
    
    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"
    
    @property
    def userinfo_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/userinfo"
    
    @property
    def discovery_uri(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

What this does:

- `BaseSettings` reads from environment variables and `.env` file
- `keycloak_url` becomes the env var `KEYCLOAK_URL`
- Properties compute the OIDC URLs so we don't hardcode them
- `@lru_cache` ensures we only instantiate `Settings` once (config is read once, used many times)

### 7.3 The JWKS key cache

When your FastAPI service receives a token, it needs Keycloak's public key to verify the signature. It fetches this from the JWKS endpoint. But you should not fetch it on every request — that would DDoS Keycloak.

The standard pattern is to cache the JWKS in memory and refresh it when needed. Keycloak rotates its signing keys periodically. When you see a token with a `kid` you don't recognize, you refresh the cache.

Use the built-in `PyJWKClient` — it handles the caching, thread safety, and refresh logic for you:

```python
from jwt import PyJWKClient
from config import get_settings


# Module-level singleton. PyJWKClient handles caching internally.
_settings = get_settings()
jwks_client = PyJWKClient(
    _settings.jwks_uri,
    cache_keys=True,    # cache the public keys
    lifespan=300,       # refresh every 5 minutes
)


def get_signing_key(token: str):
    """
    Look up the verification key for this token.
    
    PyJWKClient handles the cache and the HTTP fetch transparently.
    """
    return jwks_client.get_signing_key_from_jwt(token)
```

For most apps, this is all you need. You only roll your own if you have a specific reason (e.g., you need to log every cache miss, or you want to plug in a custom HTTP client).

### 7.4 The token validation function

This is the heart of the auth system. Every protected endpoint will call it.

```python
import jwt
from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings, Settings


# HTTPBearer tells FastAPI to look for "Authorization: Bearer <token>"
# auto_error=False means we handle missing tokens ourselves
security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """The claims we care about from a verified token."""
    sub: str  # user ID
    email: Optional[str] = None
    preferred_username: Optional[str] = None
    realm_roles: list[str] = []
    client_roles: list[str] = []
    scope: str = ""
    raw: dict  # the full decoded payload, for advanced use


class AuthError(HTTPException):
    """Raised when authentication fails."""
    def __init__(self, detail: str = "Invalid authentication credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    settings: Settings = Depends(get_settings),
) -> TokenPayload:
    """
    FastAPI dependency. Use on any endpoint that requires a valid user token.
    
    Example:
        @app.get("/me")
        def get_me(user: TokenPayload = Depends(get_current_user)):
            return {"id": user.sub, "email": user.email}
    """
    if credentials is None:
        raise AuthError("Missing Authorization header")
    
    token = credentials.credentials
    
    try:
        # 1. Get the signing key from Keycloak's JWKS
        signing_key = get_signing_key(token)
        
        # 2. Decode and verify the token
        #    CRITICAL: algorithms is an allowlist, not derived from the token
        #    CRITICAL: audience is checked against the expected value
        #    CRITICAL: issuer is checked for exact match
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],  # Allowlist, not derivation
            audience=settings.keycloak_client_id,  # Token must be for our client
            issuer=settings.issuer,  # Token must come from our Keycloak realm
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "iat", "iss", "sub", "aud"],
            },
            # Allow 30 seconds of clock skew between us and Keycloak
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidAudienceError:
        raise AuthError("Token audience does not match")
    except jwt.InvalidIssuerError:
        raise AuthError("Token issuer is not trusted")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {str(e)}")
    
    # 3. Extract Keycloak-specific claims
    realm_access = payload.get("realm_access", {})
    resource_access = payload.get("resource_access", {})
    client_access = resource_access.get(settings.keycloak_client_id, {})
    
    return TokenPayload(
        sub=payload["sub"],
        email=payload.get("email"),
        preferred_username=payload.get("preferred_username"),
        realm_roles=realm_access.get("roles", []),
        client_roles=client_access.get("roles", []),
        scope=payload.get("scope", ""),
        raw=payload,
    )
```

**Every line of this is intentional. Let me explain the dangerous ones:**

`algorithms=["RS256"]` — This is the algorithm allowlist. **Never omit this parameter.** If you do, the library will read the algorithm from the token header, which is attacker-controlled. PyJWT 2.10+ has the CVE-2026-48526 fix that prevents the HS256/RS256 confusion attack when JWKs are mixed, but you should still pin the algorithm as defense in depth [1].

`audience=settings.keycloak_client_id` — This is the audience check. The token's `aud` claim must contain our client ID. Without this, a token meant for `streamlit-frontend` could be used to call our `fastapi-backend`.

`issuer=settings.issuer` — Exact match on the issuer URL. No substring matching, no "starts with." Keycloak's `iss` is the full realm URL; it must match exactly.

`require=["exp", "iat", "iss", "sub", "aud"]` — If any of these claims is missing, the token is invalid. This prevents weird edge cases where a malformed token passes the basic checks.

`leeway=30` — Allow 30 seconds of clock skew. If your server's clock is 10 seconds ahead of Keycloak's, you don't want to reject every token. Don't make this larger than 60 seconds.

### 7.5 Role-based access control

The user is authenticated. Now what do they get to do?

```python
from typing import Callable
from fastapi import Depends


def require_realm_role(role: str) -> Callable:
    """
    Dependency factory that checks if the user has a specific realm role.
    
    Example:
        @app.delete("/users/{user_id}")
        def delete_user(
            user_id: str,
            user: TokenPayload = Depends(require_realm_role("admin")),
        ):
            ...
    """
    def check_role(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if role not in user.realm_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {role}",
            )
        return user
    
    return check_role


def require_client_role(role: str) -> Callable:
    """
    Same as require_realm_role but for client-specific roles.
    """
    def check_role(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if role not in user.client_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required client role: {role}",
            )
        return user
    
    return check_role


def require_any_realm_role(*roles: str) -> Callable:
    """
    Check that the user has at least one of the given roles.
    """
    def check_role(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if not any(r in user.realm_roles for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required one of roles: {', '.join(roles)}",
            )
        return user
    
    return check_role
```

Use them in your routes:

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# Public endpoint, no auth
@app.get("/health")
def health():
    return {"status": "ok"}

# Any authenticated user
@app.get("/me")
def get_me(user: TokenPayload = Depends(get_current_user)):
    return {
        "id": user.sub,
        "email": user.email,
        "username": user.preferred_username,
        "roles": user.realm_roles,
    }

# Requires realm role "admin"
@app.get("/admin/users")
def list_users(user: TokenPayload = Depends(require_realm_role("admin"))):
    # ... query the admin API or your DB
    pass

# Requires client role "api-writer" on the "fastapi-backend" client
@app.post("/documents")
def create_document(
    doc: DocumentCreate,
    user: TokenPayload = Depends(require_client_role("api-writer")),
):
    # ... save to MongoDB
    pass

# Requires either "admin" or "moderator"
@app.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    user: TokenPayload = Depends(require_any_realm_role("admin", "moderator")),
):
    # ...
    pass
```

### 7.6 Service-to-service (client credentials)

Your LangChain agent or a cron job needs to call FastAPI. It's not a human. Use the client credentials flow.

```python
import httpx
import time
from threading import Lock
from config import get_settings


class ServiceTokenManager:
    """
    Caches a service-to-service access token.
    Refreshes it before expiry.
    """
    
    def __init__(self):
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = Lock()
    
    def get_token(self) -> str:
        with self._lock:
            # Refresh if within 60 seconds of expiry
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            
            settings = get_settings()
            response = httpx.post(
                settings.token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.keycloak_client_id,
                    "client_secret": settings.keycloak_client_secret,
                },
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            
            self._token = data["access_token"]
            self._expires_at = time.time() + data["expires_in"]
            return self._token


service_auth = ServiceTokenManager()


def call_internal_api(path: str, **kwargs) -> dict:
    """
    Helper for service-to-service calls.
    """
    token = service_auth.get_token()
    response = httpx.get(
        f"http://fastapi-backend:8000{path}",
        headers={"Authorization": f"Bearer {token}"},
        **kwargs,
    )
    response.raise_for_status()
    return response.json()
```

In Keycloak, you must:

1. Go to the `fastapi-backend` client
2. Settings tab → enable "Service accounts roles"
3. Save
4. Service account roles tab → assign the realm/client roles your service needs

The service account is a built-in user named `service-account-fastapi-backend`. It shows up in the user list, but it's not a human.

### 7.7 Refresh token handling in the frontend

The frontend (Streamlit, React) needs to handle token refresh. The pattern:

```python
import streamlit as st
import httpx
import time
import secrets
import hashlib
import base64
import urllib.parse
from config import get_settings


def login_with_keycloak():
    """
    OIDC Authorization Code flow with PKCE.
    
    Note: Streamlit is a server-rendered app, not an SPA.
    The PKCE flow is implemented as redirect-based.
    """
    settings = get_settings()
    
    # Generate PKCE verifier and challenge
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    
    state = secrets.token_urlsafe(16)
    
    # Store in session for the callback
    st.session_state["pkce_verifier"] = verifier
    st.session_state["oauth_state"] = state
    
    auth_url = (
        f"{settings.authorization_endpoint}"
        f"?client_id=streamlit-frontend"
        f"&response_type=code"
        f"&scope=openid profile email"
        f"&redirect_uri={urllib.parse.quote('https://app.your-saas.com/callback')}"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    st.markdown(f"[Login with Keycloak]({auth_url})")


def handle_callback(code: str, state: str):
    settings = get_settings()
    
    # Verify state
    if state != st.session_state.get("oauth_state"):
        st.error("State mismatch — possible CSRF")
        return
    
    verifier = st.session_state.pop("pkce_verifier")
    
    response = httpx.post(
        settings.token_endpoint,
        data={
            "grant_type": "authorization_code",
            "client_id": "streamlit-frontend",
            "code": code,
            "redirect_uri": "https://app.your-saas.com/callback",
            "code_verifier": verifier,
        },
    )
    response.raise_for_status()
    tokens = response.json()
    
    st.session_state["access_token"] = tokens["access_token"]
    st.session_state["refresh_token"] = tokens["refresh_token"]
    st.session_state["token_expires_at"] = time.time() + tokens["expires_in"]


def get_valid_token() -> str | None:
    """Return a non-expired access token, refreshing if needed."""
    if time.time() >= st.session_state.get("token_expires_at", 0) - 60:
        # Refresh
        settings = get_settings()
        response = httpx.post(
            settings.token_endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": "streamlit-frontend",
                "refresh_token": st.session_state["refresh_token"],
            },
        )
        response.raise_for_status()
        tokens = response.json()
        st.session_state["access_token"] = tokens["access_token"]
        st.session_state["refresh_token"] = tokens.get("refresh_token", st.session_state["refresh_token"])
        st.session_state["token_expires_at"] = time.time() + tokens["expires_in"]
    
    return st.session_state.get("access_token")
```

For React SPAs, use **authlib-js** or **oidc-client-ts** instead of rolling your own. The PKCE mechanics are subtle and easy to get wrong.

---

## Module 8 — End-to-End Implementation: Bootstrap Your Full Stack

This is the implementation guide. By the end of this module, you will have a working production stack.

### 8.1 Prerequisites

| Component | Recommended | Minimum |
| --- | --- | --- |
| Server | Ubuntu 26.04 LTS, 4 vCPU, 8 GB RAM | Ubuntu 24.04, 2 vCPU, 4 GB RAM |
| Storage | 100 GB SSD (encrypted) | 40 GB SSD |
| DNS | Cloudflare-managed domain | Any domain with Cloudflare nameservers |
| Local tools | Docker 24+, Compose v2, git, jq | Docker 20+ |

### 8.2 Directory layout

```
saas-infra/
├── .env                        # Secrets loaded by Docker Compose (NEVER commit)
├── .env.example                # Template, committed to git
├── .gitignore
├── docker-compose.yml          # All services
├── docker-compose.override.yml # Local dev overrides (gitignored)
├── traefik/
│   ├── traefik.yml             # Static config
│   └── dynamic/                # Dynamic config (routers, middlewares)
├── keycloak/
│   ├── realm-export.json       # Realm config, version controlled
│   └── themes/                 # Custom login theme (optional)
├── infisical/
│   └── bootstrap.sh            # Initial admin user creation
├── backup/
│   ├── backup.sh               # Daily DB dumps
│   └── restore.sh
├── watchtower/
│   └── .env                    # Watchtower config
└── README.md
```

### 8.3 The `.env` file

`.env.example` (commit this):

```bash
# Domain
DOMAIN=your-saas.com

# Keycloak
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=CHANGE_ME_TO_A_32_CHAR_RANDOM_STRING
KEYCLOAK_DB_PASSWORD=CHANGE_ME_TO_ANOTHER_32_CHAR_STRING
KEYCLOAK_HOSTNAME=auth.${DOMAIN}
KEYCLOAK_HTTP_RELATIVE_PATH=/

# Keycloak Postgres
KEYCLOAK_DB_NAME=keycloak
KEYCLOAK_DB_USER=keycloak

# Infisical
INFISICAL_ENCRYPTION_KEY=CHANGE_ME_OPENSSL_RAND_HEX_16
INFISICAL_AUTH_SECRET=CHANGE_ME_OPENSL_RAND_BASE64_32
INFISICAL_SITE_URL=https://secrets.${DOMAIN}
INFISICAL_DB_PASSWORD=CHANGE_ME_ANOTHER_RANDOM_STRING
INFISICAL_DB_NAME=infisical
INFISICAL_DB_USER=infisical

# Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...your-token...

# GitHub Container Registry
GHCR_USER=yourusername
WATCHTOWER_LABEL_ENABLE=true
```

`.env` (gitignored, populated by you):

```bash
cp .env.example .env
nano .env
# Replace every CHANGE_ME with a generated value
openssl rand -hex 16    # for ENCRYPTION_KEY
openssl rand -base64 32 # for AUTH_SECRET and admin passwords
```

### 8.4 The `docker-compose.yml`

```yaml
# docker-compose.yml
# All services for the AI SaaS infrastructure

networks:
  backend:
    driver: bridge
  frontend:
    driver: bridge
  tunnel:
    driver: bridge

volumes:
  keycloak_db:
  keycloak_data:
  infisical_db:
  infisical_data:
  infisical_redis:
  traefik_letsencrypt:
  traefik_logs:

services:
  # ============================================
  # Cloudflare Tunnel — outbound only
  # ============================================
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    networks:
      - tunnel
    depends_on:
      - traefik
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

  # ============================================
  # Traefik — reverse proxy, no public exposure
  # ============================================
  traefik:
    image: traefik:v3.2
    container_name: traefik
    restart: unless-stopped
    command:
      - "--api.dashboard=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.websecure.http.tls=true"
      - "--certificatesresolvers.cloudflare.acme.dnschallenge=true"
      - "--certificatesresolvers.cloudflare.acme.dnschallenge.provider=cloudflare"
      - "--certificatesresolvers.cloudflare.acme.email=ops@${DOMAIN}"
      - "--certificatesresolvers.cloudflare.acme.storage=/letsencrypt/acme.json"
      - "--accesslog=true"
      - "--accesslog.filepath=/var/log/traefik/access.log"
      - "--log.level=WARN"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik_letsencrypt:/letsencrypt
      - traefik_logs:/var/log/traefik
    networks:
      - tunnel
      - frontend
    ports:
      # Only cloudflared talks to this; nothing else
      - "443:443"
    environment:
      - "CF_API_EMAIL=ops@${DOMAIN}"
      - "CF_API_KEY_FILE=/run/secrets/cf_api_key"
    secrets:
      - cf_api_key
    labels:
      - "traefik.enable=true"
      - "com.centurylinklabs.watchtower.enable=true"

  # ============================================
  # Keycloak — Identity provider
  # ============================================
  keycloak-db:
    image: postgres:16-alpine
    container_name: keycloak-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${KEYCLOAK_DB_NAME}
      POSTGRES_USER: ${KEYCLOAK_DB_USER}
      POSTGRES_PASSWORD: ${KEYCLOAK_DB_PASSWORD}
    volumes:
      - keycloak_db:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${KEYCLOAK_DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    container_name: keycloak
    restart: unless-stopped
    command: start --optimized
    environment:
      # Admin bootstrap (one-time)
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_ADMIN}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
      # Database
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/${KEYCLOAK_DB_NAME}
      KC_DB_USERNAME: ${KEYCLOAK_DB_USER}
      KC_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD}
      # Hostname
      KC_HOSTNAME: https://${KEYCLOAK_HOSTNAME}
      KC_HOSTNAME_STRICT: "true"
      KC_HOSTNAME_STRICT_HTTPS: "true"
      # Behind reverse proxy
      KC_PROXY_HEADERS: xforwarded
      KC_HTTP_ENABLED: "true"
      # Health and metrics
      KC_HEALTH_ENABLED: "true"
      KC_METRICS_ENABLED: "true"
      # Logging
      KC_LOG: console,file
      KC_LOG_FILE: /opt/keycloak/data/log/keycloak.log
    volumes:
      - keycloak_data:/opt/keycloak/data
    networks:
      - backend
      - frontend
    depends_on:
      keycloak-db:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=frontend"
      - "traefik.http.routers.keycloak.rule=Host(`${KEYCLOAK_HOSTNAME}`)"
      - "traefik.http.routers.keycloak.entrypoints=websecure"
      - "traefik.http.routers.keycloak.tls.certresolver=cloudflare"
      - "traefik.http.routers.keycloak.tls=true"
      - "traefik.http.services.keycloak.loadbalancer.server.port=8080"
      # Block access to admin console from outside Cloudflare Access
      - "traefik.http.middlewares.keycloak-admin-ipwhitelist.ipwhitelist.sourcerange=127.0.0.1/32,10.0.0.0/8"
      - "traefik.http.routers.keycloak-admin.rule=Host(`${KEYCLOAK_HOSTNAME}`) && (PathPrefix(`/admin`) || PathPrefix(`/realms/master`))"
      - "traefik.http.routers.keycloak-admin.entrypoints=websecure"
      - "traefik.http.routers.keycloak-admin.tls.certresolver=cloudflare"
      - "traefik.http.routers.keycloak-admin.middlewares=keycloak-admin-ipwhitelist"
      # Health endpoint always public (for monitoring)
      - "traefik.http.routers.keycloak-health.rule=Host(`${KEYCLOAK_HOSTNAME}`) && Path(`/health`)"
      - "traefik.http.routers.keycloak-health.entrypoints=websecure"
      - "traefik.http.routers.keycloak-health.tls.certresolver=cloudflare"
      - "com.centurylinklabs.watchtower.enable=true"

  # ============================================
  # Infisical — Secrets management
  # ============================================
  infisical-db:
    image: postgres:16-alpine
    container_name: infisical-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${INFISICAL_DB_NAME}
      POSTGRES_USER: ${INFISICAL_DB_USER}
      POSTGRES_PASSWORD: ${INFISICAL_DB_PASSWORD}
    volumes:
      - infisical_db:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${INFISICAL_DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  infisical-redis:
    image: redis:7-alpine
    container_name: infisical-redis
    restart: unless-stopped
    volumes:
      - infisical_redis:/data
    networks:
      - backend
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  infisical:
    image: infisical/infisical:latest
    container_name: infisical
    restart: unless-stopped
    environment:
      SITE_URL: ${INFISICAL_SITE_URL}
      ENCRYPTION_KEY: ${INFISICAL_ENCRYPTION_KEY}
      AUTH_SECRET: ${INFISICAL_AUTH_SECRET}
      DB_CONNECTION_URI: postgresql://${INFISICAL_DB_USER}:${INFISICAL_DB_PASSWORD}@infisical-db:5432/${INFISICAL_DB_NAME}
      REDIS_URL: redis://infisical-redis:6379
      NODE_ENV: production
    volumes:
      - infisical_data:/usr/src/app/data
    networks:
      - backend
      - frontend
    depends_on:
      infisical-db:
        condition: service_healthy
      infisical-redis:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=frontend"
      - "traefik.http.routers.infisical.rule=Host(`secrets.${DOMAIN}`)"
      - "traefik.http.routers.infisical.entrypoints=websecure"
      - "traefik.http.routers.infisical.tls.certresolver=cloudflare"
      - "traefik.http.routers.infisical.tls=true"
      - "traefik.http.services.infisical.loadbalancer.server.port=8080"
      - "com.centurylinklabs.watchtower.enable=true"

  # ============================================
  # Watchtower — auto-update Docker images
  # ============================================
  watchtower:
    image: containrrr/watchtower:latest
    container_name: watchtower
    restart: unless-stopped
    command:
      - "--label-enable"
      - "--schedule"
      - "0 0 4 * * *"
      - "--cleanup"
      - "--include-stopped"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - backend
    environment:
      - WATCHTOWER_LABEL_ENABLE=${WATCHTOWER_LABEL_ENABLE}

secrets:
  cf_api_key:
    file: ./secrets/cf_api_key.txt
```

### 8.5 Step-by-step deployment

**Step 1: Provision the server**

Spin up an Ubuntu 26 instance on your VPS of choice (Hetzner, OVH, DigitalOcean, etc.). 4 vCPU / 8 GB RAM / 100 GB SSD is a good starting point.

```bash
# Initial server setup
apt update && apt upgrade -y
apt install -y ufw fail2ban unattended-upgrades

# Enable automatic security updates
dpkg-reconfigure -plow unattended-upgrades

# Firewall: SSH in, everything else out
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw enable

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $USER
```

**Step 2: Clone the repo and configure**

```bash
git clone https://github.com/yourorg/saas-infra.git
cd saas-infra

# Create your secrets file
cp .env.example .env
nano .env  # fill in values

# Generate values
openssl rand -hex 16    # paste into INFISICAL_ENCRYPTION_KEY
openssl rand -base64 32 # paste into INFISICAL_AUTH_SECRET
openssl rand -base64 32 # paste into KEYCLOAK_ADMIN_PASSWORD
openssl rand -base64 32 # paste into KEYCLOAK_DB_PASSWORD
openssl rand -base64 32 # paste into INFISICAL_DB_PASSWORD

# Create Cloudflare API key file (for DNS-01 challenge)
mkdir -p secrets
echo "your-cloudflare-api-key" > secrets/cf_api_key.txt
chmod 600 secrets/cf_api_key.txt
```

**Step 3: Set up the Cloudflare Tunnel**

In the Cloudflare dashboard:

1. Go to Zero Trust → Networks → Tunnels → Create a tunnel
2. Choose "Cloudflared" connector
3. Name it `saas-tunnel`
4. Copy the tunnel token
5. Paste into `CLOUDFLARE_TUNNEL_TOKEN` in `.env`

Don't add public hostnames yet — we'll do that after Traefik is up.

**Step 4: Start the stack**

```bash
docker compose up -d
```

This pulls and starts all services. Watch the logs:

```bash
docker compose logs -f keycloak
```

Wait for Keycloak to print "Keycloak ... started in XXs" — that takes 30-60 seconds the first time.

**Step 5: Set up Cloudflare public hostnames**

In the Cloudflare tunnel settings, add these public hostnames:

| Subdomain | Domain | Type | URL |
| --- | --- | --- | --- |
| `auth` | `your-saas.com` | HTTP | `traefik:443` |
| `secrets` | `your-saas.com` | HTTP | `traefik:443` |
| `app` | `your-saas.com` | HTTP | `traefik:443` |
| `api` | `your-saas.com` | HTTP | `traefik:443` |

(Or use the UI to add your actual app subdomains.)

**Step 6: Add Cloudflare Access (optional but recommended)**

In Cloudflare Zero Trust → Access → Applications:

1. Create application → Self-hosted
2. Application domain: `auth.your-saas.com`
3. Name: "Keycloak Admin"
4. Policy: Allow → Emails → your-email@yourcompany.com
5. Save

Now `auth.your-saas.com` requires Cloudflare login before you can reach Keycloak. Even your team must authenticate with Cloudflare first.

**Step 7: Verify Keycloak**

Visit `https://auth.your-saas.com/admin/master/console/`. You should see the Keycloak admin login. Log in with the admin user from `.env`.

**Step 8: Create your production realm**

1. Hover over "Master" realm in the top-left → Create Realm
2. Realm name: `prod`
3. Enabled: ON
4. Create

**Step 9: Create your first client (FastAPI backend)**

In the `prod` realm:

1. Clients → Create client
2. Client ID: `fastapi-backend`
3. Client type: OpenID Connect
4. Next
5. **Client authentication: ON** (this makes it confidential — has a secret)
6. **Authorization: ON** (this enables fine-grained authz services if you want them later)
7. **Service accounts roles: ON** (this enables client credentials for service-to-service)
8. Next
9. Root URL: `https://api.your-saas.com`
10. Valid redirect URIs: `https://api.your-saas.com/*`
11. Web origins: `https://api.your-saas.com`
12. Save
13. Go to the Credentials tab, copy the client secret → put in Infisical

**Step 10: Create roles**

In the `prod` realm:

1. Realm roles → Create role
2. Role name: `user`
3. Save
4. Create role: `admin`
5. Create role: `beta-tester`

For client-specific roles:

1. Clients → `fastapi-backend` → Roles tab
2. Create role: `api-reader`
3. Create role: `api-writer`
4. Create role: `api-admin`

**Step 11: Create your first user**

1. Users → Add user
2. Username: `yourname`
3. Email: `your@email.com`
4. Email verified: ON (for testing)
5. Save
6. Credentials tab → Set password
7. Temporary: OFF
8. Save
9. Role mapping tab → Assign role → `admin`

**Step 12: Configure Infisical**

Visit `https://secrets.your-saas.com`. Create the first admin user.

Then:

1. Create an organization: "Your Company"
2. Create a project: "AI SaaS Backend"
3. Create environments: dev, staging, prod (use defaults)
4. Create folders: `/database`, `/third-party`, `/internal`
5. Add your first secret: `POSTGRES_PASSWORD` in `/database` for prod environment
6. In Access Control → Machine Identities, create a "fastapi-backend" identity
7. Save the Client ID and Client Secret
8. Give it read access to the prod environment

**Step 13: Update your `.env` to pull secrets from Infisical at runtime**

This is where it gets interesting. The chicken-and-egg problem: your services need secrets, but secrets are in Infisical, and authenticating to Infisical needs... secrets.

The bootstrap pattern:

1. The first secret you put in Infisical is the machine identity's client secret itself
2. But how do you get that secret into the container?
3. Answer: at first, you put it in the `.env` file on the server (one-time bootstrap)
4. As soon as the FastAPI container starts, it fetches everything else from Infisical
5. You can then rotate the bootstrap secret in Infisical and use a runtime fetch to get the new value

For now, do this:

```bash
# In .env, add:
INFISICAL_MACHINE_CLIENT_ID=<your machine identity client id>
INFISICAL_MACHINE_CLIENT_SECRET=<your machine identity client secret>
INFISICAL_PROJECT_ID=<your project id>
```

Then your FastAPI container uses the `infisical run` pattern:

```dockerfile
# In your FastAPI Dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN curl -1sLf 'https://artifacts-cli.infisical.com/setup.deb.sh' | bash \
    && apt-get update && apt-get install -y infisical

# ... your app ...

CMD ["infisical", "run", "--projectId", "${INFISICAL_PROJECT_ID}", "--env", "prod", "--", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Now your app starts with all its secrets injected as environment variables. The `INFISICAL_TOKEN` env var is set from `.env` (or directly in compose), and the CLI does the rest.

**Step 14: Set up backups**

`backup/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR=/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
S3_BUCKET="s3://your-backup-bucket"

# Keycloak database
docker exec keycloak-db pg_dump -U ${KEYCLOAK_DB_USER} ${KEYCLOAK_DB_NAME} \
  | gzip > ${BACKUP_DIR}/keycloak_${TIMESTAMP}.sql.gz

# Infisical database
docker exec infisical-db pg_dump -U ${INFISICAL_DB_USER} ${INFISICAL_DB_NAME} \
  | gzip > ${BACKUP_DIR}/infisical_${TIMESTAMP}.sql.gz

# Upload to S3
aws s3 cp ${BACKUP_DIR}/keycloak_${TIMESTAMP}.sql.gz ${S3_BUCKET}/keycloak/
aws s3 cp ${BACKUP_DIR}/infisical_${TIMESTAMP}.sql.gz ${S3_BUCKET}/infisical/

# Clean up local backups older than 7 days
find ${BACKUP_DIR} -name "*.sql.gz" -mtime +7 -delete
```

```bash
chmod +x backup/backup.sh
echo "0 2 * * * /opt/saas-infra/backup/backup.sh" | crontab -
```

**Step 15: Set up Watchtower for image auto-updates**

Watchtower is already in the compose file. It runs daily at 4am and updates any container with the `com.centurylinklabs.watchtower.enable=true` label. Keycloak, Traefik, and Infisical will all auto-update.

For your own app image (e.g., `ghcr.io/yourorg/fastapi-backend`), you need to also tag it with the label.

**Step 16: Verify the full flow**

```bash
# Test that everything is up
docker compose ps

# Test that Keycloak is responding
curl -k https://auth.your-saas.com/realms/prod/.well-known/openid-configuration | jq .

# Test that Infisical is responding
curl -k https://secrets.your-saas.com/api/status

# Test that a token can be obtained
curl -X POST https://auth.your-saas.com/realms/prod/protocol/openid-connect/token \
  -d "client_id=fastapi-backend" \
  -d "client_secret=YOUR_SECRET" \
  -d "grant_type=client_credentials" | jq .

# Test that a protected API endpoint works
TOKEN="..."
curl -H "Authorization: Bearer $TOKEN" https://api.your-saas.com/me | jq .
```

---

## Module 9 — Production Security Hardening Checklist

This is the list of things you should not skip. Each item is short, the rationale is short, the action is specific.

### 9.1 Keycloak hardening

- [ ] **Disable the `master` realm admin in production.** Create your own realm and admin user, then disable the master realm's admin console. (Path: `master` realm → `admin` user → disable)
- [ ] **Enable brute force detection.** Default: 30 failed logins = 15-minute lockout. Tune as needed. (Realm Settings → Security Defenses → Brute Force Detection)
- [ ] **Enable login logging and event listeners.** (Realm Settings → Events → Save Events: ON; Event Listeners: `jboss-logging` + `email` if you want email alerts)
- [ ] **Set `KC_HOSTNAME_STRICT=true`.** Don't allow Keycloak to accept tokens with the wrong `iss` claim.
- [ ] **Set `KC_HOSTNAME_STRICT_HTTPS=true`.** Don't allow HTTP downgrades.
- [ ] **Disable the `account` console at the realm level if you don't need it.** Or restrict it via the same Traefik IP whitelist as the admin console.
- [ ] **Use the latest Keycloak patch version.** 26.x is the supported line; pin to a specific patch (e.g., 26.0.5, not 26.0 or 26).
- [ ] **Generate the master realm's initial admin via `KC_BOOTSTRAP_ADMIN_*` env vars, not the deprecated `KEYCLOAK_USER`/`KEYCLOAK_PASSWORD`.** The old vars are gone in 26.x.
- [ ] **Set short access token lifetime (5–15 minutes) and longer refresh token lifetime (hours to days) with rotation enabled.** (Realm Settings → Tokens)
- [ ] **Disable the `Direct grant` flow unless you really need it.** It allows password-based login that bypasses the browser, and is the gateway for credential stuffing.
- [ ] **Set up WebAuthn/passkeys for admin users.** (Required action → Configure WebAuthn)
- [ ] **Set up TOTP as a backup second factor for admin users.**
- [ ] **Configure CORS.** (Realm Settings → Client → your client → Web Origins: only the exact origins you need, no wildcards)
- [ ] **Review the `Verify email` and `Update password` required actions** to make sure they're configured for your user base.
- [ ] **Back up the database daily** to an encrypted, offsite location.
- [ ] **Test your restore procedure** quarterly.

### 9.2 Infisical hardening

- [ ] **Back up the encryption key in a separate physical location.** Lose it = lose all secrets.
- [ ] **Use machine identities with `read` access scoped to specific environments and folders**, not blanket `admin` access.
- [ ] **Enable audit logging** and ship it to your central log store.
- [ ] **Rotate the master `AUTH_SECRET` periodically.** (This invalidates all user sessions, so do it during a maintenance window.)
- [ ] **Restrict the admin console to your team only** via Cloudflare Access.
- [ ] **Set up SAML or OIDC login to Infisical itself**, with your Keycloak as the IdP. This way your team uses the same credentials and MFA everywhere.
- [ ] **Enable MFA on all Infisical human users.**
- [ ] **Use secret references** (`${OTHER_SECRET}`) to enable one-line rotation of upstream dependencies.
- [ ] **Set up dynamic secrets for databases** with a lease of 1 hour.
- [ ] **Tag every secret** with its owner and purpose.
- [ ] **Set up secret scanning in your repos** to catch accidental secret commits.

### 9.3 FastAPI / application hardening

- [ ] **Always pass an `algorithms=[...]` allowlist to `jwt.decode()`.** Never derive from the token.
- [ ] **Always verify `iss`, `aud`, `exp`, `nbf`.** No exceptions.
- [ ] **Allow no more than 60 seconds of clock skew** (`leeway=60`).
- [ ] **Don't store JWTs in `localStorage` in the browser.** Use HTTP-only, Secure, SameSite=Strict cookies.
- [ ] **Set `aud` on every token explicitly** — never accept tokens without an audience.
- [ ] **Rate limit auth endpoints** (login, token, refresh) to defeat brute force.
- [ ] **Use HTTPS everywhere.** No `http://` in production URLs, ever.
- [ ] **Set CORS** to only your actual frontend origins. No `*`.
- [ ] **Set security headers:** `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy`, `Referrer-Policy: strict-origin-when-cross-origin`.
- [ ] **Don't log tokens or PII.** Use structured logging and redact sensitive fields.
- [ ] **Don't return detailed error messages to clients** on 500 errors. Log the detail, return a generic message.
- [ ] **Use dependency pinning** in `requirements.txt` with hashes. `pip-compile --generate-hashes`.
- [ ] **Run a dependency scanner** in CI (Snyk, Dependabot, Trivy, Grype).
- [ ] **Don't accept the `Authorization: Bearer` query string.** Only the header.
- [ ] **Refresh tokens only on the server side** (the client never sees them).

### 9.4 Network / infrastructure hardening

- [ ] **No public ports on the server.** Use Cloudflare Tunnel. (UDP/TCP 7844 outbound to Cloudflare is the only exception.)
- [ ] **No SSH password login.** Use SSH keys only.
- [ ] **Disable root login over SSH.**
- [ ] **Run `fail2ban`** with sane defaults.
- [ ] **Enable unattended security updates** for the OS.
- [ ] **Restrict the Keycloak admin console to a specific IP range** (or a VPN) via Traefik middleware.
- [ ] **Restrict the Infisical admin console** the same way.
- [ ] **Use a separate database for Keycloak and Infisical.** Don't reuse your app database.
- [ ] **Back up both databases daily** to an encrypted, offsite location.
- [ ] **Test your restore procedure** quarterly.
- [ ] **Enable Cloudflare Access** for at least your admin consoles.
- [ ] **Enable Cloudflare WAF and rate limiting rules** for your public apps.
- [ ] **Set up monitoring:** Prometheus for metrics, Loki/Elastic for logs, Jaeger/Tempo for traces.
- [ ] **Set up alerts:** Keycloak login failure rate, Infisical fetch failure rate, certificate expiry, disk usage, high CPU.

### 9.5 Common failure modes to plan for

| Failure | Impact | Mitigation |
| --- | --- | --- |
| Keycloak DB is down | No one can log in | HA cluster, database replication, alert on DB connectivity |
| Keycloak service is down | Same as above | Multiple instances behind LB, health checks |
| Infisical is down | Apps can't fetch secrets; if they're already loaded in memory, they keep running | Multiple instances, cache secrets in memory with a TTL, have a fallback to environment variables for non-sensitive defaults |
| PostgreSQL data corruption | Loss of users, secrets, or both | Daily encrypted backups, quarterly restore tests, point-in-time recovery (WAL archiving) |
| Cloudflare Tunnel goes down | All external traffic stops | Multiple cloudflared instances, monitor tunnel status, consider a fallback |
| TLS certificate expiry | Service is unreachable | Let's Encrypt via Cloudflare DNS-01 auto-renews; alert 14 days before any cert expiry |
| Secret rotation breaks an app | App can't connect to DB | Dual-rotation grace period, canary deployment of rotated secrets, rollback plan |
| Keycloak key rotation | Old tokens become unverifiable | Token lifetime ≤ 5 min means worst case is 5 min of failed validations; alert on unknown `kid` |

---

## Module 10 — What to Learn Next, and What to Ignore

You've absorbed a lot. Here's the map of what to study in what order, and what to skip.

### 10.1 The next 30 days

- [ ] Set up the full Docker Compose stack from Module 8
- [ ] Create your realm, clients, roles, and first user
- [ ] Wire up your FastAPI service to validate Keycloak tokens
- [ ] Add Cloudflare Tunnel and Access
- [ ] Deploy Infisical and migrate your `.env` secrets to it
- [ ] Enable WebAuthn (passkeys) for your admin user
- [ ] Set up daily backups
- [ ] Set up at least one observability alert

### 10.2 The next 90 days

- [ ] Add a second Keycloak instance behind the load balancer (HA)
- [ ] Implement token exchange if you have a microservice architecture
- [ ] Set up dynamic database credentials in Infisical
- [ ] Wire up OpenTelemetry across all services
- [ ] Implement fine-grained authorization (UMA) if you need resource-level access control
- [ ] Set up CI/CD with GitHub Actions to deploy new versions of your services
- [ ] Implement secret rotation with dual-phase grace period
- [ ] Set up a security incident response plan (what to do if a token leaks, if a developer laptop is stolen, if you detect brute force)

### 10.3 What to ignore (for now)

- **SAML 2.0.** Legacy enterprise stuff. OIDC is better in every way. Only add SAML if a specific customer requires it.
- **Custom Keycloak themes.** Nice-to-have. Ship the default. Customize later if your users complain.
- **Fine-grained authorization (UMA).** Skip until you actually need it. RBAC is enough for 90% of use cases.
- **Custom Keycloak SPIs.** Powerful but Java. Skip until you can't do what you need with built-in features.
- **Custom Infisical plugins.** Same logic.
- **Active Directory / LDAP federation.** Only relevant if you're integrating with an enterprise customer who has an AD.
- **HashiCorp Vault.** Great product, but Infisical is enough for your scale and has a much gentler learning curve. Switch to Vault only if you have a specific Vault feature you need.
- **Service mesh (Istio, Linkerd).** Powerful but adds operational complexity. Skip until you have > 10 services or need mTLS at the mesh level.
- **Custom auth flows.** Use the built-in browser flow. Customize only if you can't meet a requirement with built-ins.
- **Token introspection on every request.** Slower than local validation. Use introspection only for sensitive operations (e.g., token revocation checks, "is this token still valid right now?").

### 10.4 The mental shift

The most important thing this course is trying to teach is not the syntax of `jwt.decode()` or the exact `docker-compose.yml` syntax. It's the shift in how you think about security:

- **Centralize everything you can centralize.** Identity in Keycloak, secrets in Infisical, logs in Loki, metrics in Prometheus, certificates in Infisical PKI. The fewer places a vulnerability can live, the fewer places an attacker can break in.
- **Use the standards.** Don't invent your own auth flow. Don't invent your own session format. Don't invent your own token format. Use OIDC, use JWT, use SAML if you must. Auditors know these. Libraries know these. Attackers know these.
- **Verify locally.** Don't call back to the authorization server on every request. Cache the JWKS, validate the signature, check the claims. The verification is a pure function of (token, public_key, time).
- **Defend in depth.** Keycloak AND Cloudflare Access. JWT signature AND token introspection for sensitive ops. HTTPS AND HSTS AND CSP. Each layer catches what the next one misses.
- **Automate the boring.** Backups, certificate renewal, secret rotation, image updates, vulnerability scanning. The boring stuff is the stuff that bites you when nobody's watching.
- **Encrypt everything that matters.** Data at rest (database encryption, secret encryption), data in transit (TLS everywhere), data in use (memory isolation in containers). Encryption is not optional; it's the cost of admission.
- **Audit everything.** Who logged in, who accessed what, who rotated which secret, who deployed which version. When (not if) something goes wrong, the audit log is your detective.
- **Fail safely.** When something goes wrong, default to denying access. Fail closed, not open. A 503 from your auth system is better than a silent skip.

You now have the same identity and secrets infrastructure that billion-dollar companies run. The same code, the same protocols, the same patterns. The only thing you don't have is the support contract — and you have the community, the documentation, and the source code instead.

That's enough to build a serious AI SaaS on a serious foundation.

---

## References

[1] devuru.com — "python-jose or PyJWT — and what the swap breaks" (verified 2026-08-16). https://devuru.com/fastapi/jwt-library/

[2] oauth.net — OAuth 2.1 specification draft. https://oauth.net/2.1/

[3] keycloak.org — Release Notes (Keycloak 26.7.0). https://www.keycloak.org/docs/latest/release_notes/index.html

[4] keycloak.org — Admin REST API reference. https://www.keycloak.org/docs-api/latest/rest-api/index.html

[5] github.com/fastapi/fastapi Discussion #9587 — FastAPI's JWT library decision (PyJWT). https://github.com/fastapi/fastapi/discussions/9587

[6] keycloak.org — High availability guide. https://www.keycloak.org/high-availability/introduction

[7] cloudflare.com — Cloudflare Tunnel + Cloudflare Access docs. https://developers.cloudflare.com/cloudflare-one/

[8] infisical.com — Self-hosting Infisical. https://infisical.com/docs/self-hosting/overview

[9] infisical.com — Internal PKI announcement. https://infisical.com/blog/introducing-pki

[10] openid.net — OpenID Connect Core 1.0 specification. https://openid.net/specs/openid-connect-core-1_0.html

[11] ietf.org — RFC 7519: JSON Web Token (JWT). https://www.ietf.org/rfc/rfc7519.html

[12] openid.net — OpenID Connect Discovery 1.0 specification. https://openid.net/specs/openid-connect-discovery-1_0.html

[13] aembit.io — "OAuth 2.0 vs 2.1: What Changed and How to Migrate". https://aembit.io/blog/oauth-2-1-guide-migration-security/

[14] skycloak.io — "FastAPI Authentication with Keycloak". https://skycloak.io/blog/keycloak-fastapi-python-api-authentication/

[15] github.com/Infisical/infisical — Open-source secret management platform. https://github.com/Infisical/infisical

[16] keycloak.org — Server Administration Guide. https://www.keycloak.org/docs/latest/server_admin/index.html

[17] ietf.org — RFC 7636: Proof Key for Code Exchange (PKCE). https://www.ietf.org/rfc/rfc7636.html
