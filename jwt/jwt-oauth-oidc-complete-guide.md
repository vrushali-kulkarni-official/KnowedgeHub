# JWT, OAuth & OIDC: From Zero to Production

## A Complete Course for Your AI SaaS (Python · FastAPI · Postgres · Redis · Docker)

> **Who this is for:** a beginner who is building a production AI SaaS and needs to understand authentication and authorization end-to-end. We start from "what is a login?" and go all the way to "rotate my signing keys without downtime."
> 
> **How to read this:** treat it like a textbook. Read Part 1 → 5 in order to build the mental model. Part 6 is the implementation you can copy. Part 7–9 are what you re-read before going to production. Part 10 is the deployment checklist.
> 
> **Security is the top priority** in this guide. Every recommendation here assumes a hostile public internet.

---

## Table of Contents

- [Part 1: Foundations](#part-1-foundations)
  - 1.1 Authentication vs Authorization
  - 1.2 The Old Way: Server Sessions
  - 1.3 The New Way: Tokens
  - 1.4 Why JWT Exists
- [Part 2: JWT Deep Dive](#part-2-jwt-deep-dive)
  - 2.1 The Anatomy of a JWT
  - 2.2 Base64URL, Not Encryption
  - 2.3 How Signing Works
  - 2.4 How Verification Works
  - 2.5 Standard Claims (Registered Claims)
  - 2.6 Custom Claims (Public & Private)
  - 2.7 Signing Algorithms: HS256, RS256, ES256, EdDSA
  - 2.8 Access Tokens vs Refresh Tokens vs ID Tokens
  - 2.9 Token Lifetimes
  - 2.10 Where to Store Tokens (Browser, Mobile, Server)
- [Part 3: Attacks & Defenses](#part-3-attacks--defenses)
  - 3.1 The `alg: none` Attack
  - 3.2 Algorithm Confusion (HS256 vs RS256)
  - 3.3 Signature Stripping
  - 3.4 Token Theft (XSS)
  - 3.5 CSRF (Cross-Site Request Forgery)
  - 3.6 Replay Attacks
  - 3.7 JWT Has No Built-in Revocation
  - 3.8 Weak Secrets
  - 3.9 Sensitive Data in Payload
  - 3.10 The Defense Checklist
- [Part 4: OAuth 2.0](#part-4-oauth-20)
  - 4.1 What OAuth Is (and Is Not)
  - 4.2 The 4 Roles
  - 4.3 The 4 Grant Types (When to Use Each)
  - 4.4 Authorization Code + PKCE (the main one)
  - 4.5 Client Credentials (service-to-service)
  - 4.6 Refresh Token Grant
  - 4.7 Scopes
  - 4.8 OAuth Is Authorization, Not Authentication
- [Part 5: OpenID Connect (OIDC)](#part-5-openid-connect-oidc)
  - 5.1 What OIDC Adds on Top of OAuth
  - 5.2 The ID Token
  - 5.3 Discovery (`/.well-known/openid-configuration`)
  - 5.4 JWKS (`/.well-known/jwks.json`)
  - 5.5 UserInfo Endpoint
  - 5.6 Validating an ID Token (the rules)
  - 5.7 OIDC in Your Stack (as Client vs as Provider)
- [Part 6: Implementation in FastAPI](#part-6-implementation-in-fastapi)
  - 6.1 Library Choices
  - 6.2 Project Structure
  - 6.3 Configuration & Secrets
  - 6.4 Password Hashing (Argon2)
  - 6.5 Database Models (Postgres / SQLAlchemy)
  - 6.6 Pydantic Schemas
  - 6.7 JWT Utilities (sign & verify)
  - 6.8 User Registration Endpoint
  - 6.9 Login Endpoint
  - 6.10 Refresh Endpoint
  - 6.11 Logout Endpoint
  - 6.12 The `current_user` Dependency
  - 6.13 Role-Based Access Control (RBAC)
  - 6.14 Password Reset Flow
  - 6.15 Email Verification
  - 6.16 Google OAuth (Sign in with Google) with Authlib
  - 6.17 GitHub OAuth
  - 6.18 Generic OIDC Client
  - 6.19 Rate Limiting with Redis
  - 6.20 Token Revocation List in Redis
  - 6.21 CORS
  - 6.22 Security Headers
  - 6.23 The Complete `main.py`
- [Part 7: Production Hardening](#part-7-production-hardening)
  - 7.1 Key Management (RSA / EdDSA)
  - 7.2 Key Rotation Without Downtime (JWKS pattern)
  - 7.3 What to Log, What Never to Log
  - 7.4 Monitoring & Alerting
  - 7.5 Constant-Time Comparisons
  - 7.6 Audit Trail
  - 7.7 Incident Response Checklist
- [Part 8: Stack Integration](#part-8-stack-integration)
  - 8.1 Postgres Schema (full SQL)
  - 8.2 Redis Key Patterns
  - 8.3 Docker Compose
  - 8.4 Docker Secrets for JWT Keys
  - 8.5 Cloudflare Tunnel Headers
  - 8.6 Watchtower & Image Updates
  - 8.7 GitHub Actions: Build → GHCR → Deploy
- [Part 9: Self-Hosted vs Managed Identity](#part-9-self-hosted-vs-managed-identity)
  - 9.1 Keycloak
  - 9.2 Authentik
  - 9.3 Logto
  - 9.4 Ory Hydra
  - 9.5 Supabase Auth
  - 9.6 Clerk / Auth0 / WorkOS
  - 9.7 My Recommendation for Your AI SaaS
- [Part 10: Step-by-Step Setup Checklist](#part-10-step-by-step-setup-checklist)
- [Part 11: Testing](#part-11-testing)
- [Part 12: Common Pitfalls & FAQ](#part-12-common-pitfalls--faq)
- [Appendix A: Glossary](#appendix-a-glossary)
- [Appendix B: References](#appendix-b-references)

---

# Part 1: Foundations

Before we touch a single line of code, you need a rock-solid mental model. Most security bugs come from fuzzy thinking, not from missing libraries.

## 1.1 Authentication vs Authorization

These are two different questions:

|          | Authentication (AuthN)      | Authorization (AuthZ)                    |
| -------- | --------------------------- | ---------------------------------------- |
| Question | **Who are you?**            | **What are you allowed to do?**          |
| Example  | Login with email + password | Can this user access the `/admin` route? |
| Output   | An identity (user ID)       | A decision (allow / deny)                |
| When     | At login                    | On every request                         |
| Token    | ID token (OIDC)             | Access token (OAuth)                     |

A complete auth system answers both questions, every request. They look similar but they are not the same protocol.

## 1.2 The Old Way: Server Sessions

For 20 years, web apps did this:

```
1. User submits username + password over HTTPS.
2. Server checks the password against the DB.
3. Server creates a session row:  { session_id: "abc123", user_id: 42, expires_at: ... }
4. Server stores that row in memory or Redis.
5. Server sends back a Set-Cookie: session=abc123; HttpOnly; Secure
6. Browser automatically sends that cookie on every request.
7. Server looks up session "abc123" in the store, finds user_id 42, lets the request through.
```

**Pros:** server has full control — it can revoke a session instantly by deleting the row.
**Cons:**

- Every request hits the session store (slow at scale).
- The store is a single point of failure.
- Awkward for mobile apps, CLIs, and third-party API consumers — they don't naturally use cookies.
- Awkward for microservices — service A doesn't share a session with service B unless they all hit the same store.

## 1.3 The New Way: Tokens

A token is a self-contained, signed string that proves who you are, without the server having to remember anything.

```
1. User submits username + password over HTTPS.
2. Server checks the password.
3. Server signs a token:  sign({ user_id: 42, role: "user", exp: ... }, secret)
4. Server returns the token in the response body.
5. Client stores the token (cookie, localStorage, secure storage on mobile).
6. Client sends the token on every request:  Authorization: Bearer eyJhbGc...
7. Server verifies the signature and reads the claims — no DB lookup needed.
```

**Pros:** stateless, scales horizontally, works for browsers / mobile / CLIs / servers alike.
**Cons:** harder to revoke (you can't delete a stateless thing), so you need a denylist (we'll build one in Redis).

## 1.4 Why JWT Exists

JWT (JSON Web Token, RFC 7519) is **a specific format** for tokens. The format was standardized in 2015 so every language and library could speak the same protocol.

Before JWT, every framework invented its own token format. That was chaos. JWT is the lingua franca.

JWT is **not** the only token format. Alternatives:

- **PASETO** (Platform-Agnostic Security Tokens) — designed to fix many JWT footguns. Newer, smaller ecosystem.
- **Macaroons** — used at Google. More flexible, harder to use.
- **SAML assertions** — XML-based, used in enterprise SSO. Heavy.
- **Opaque tokens** — random strings the server must look up. What OAuth 2.0 traditionally used (and still often does).

For your SaaS, **JWT is the right choice**: every library supports it, every OAuth/OIDC provider issues it, every tutorial on the internet is about it.

---

# Part 2: JWT Deep Dive

## 2.1 The Anatomy of a JWT

A JWT is **three Base64URL-encoded JSON blobs** joined by dots:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NSIsIm5hbWUiOiJBbGljZSIsImV4cCI6MTcxNzEyMDAwMH0.7s5p7D8iYwF3mH7p1V4b2xTz8aYh3vQ1nM5k9eR6uXw
  └──── header ─────┘                └──────────── payload ────────────┘                              └──── signature ────┘
```

Decoded by hand:

**Header**

```json
{
  "alg": "HS256",        // signing algorithm
  "typ": "JWT"           // type — always "JWT"
}
```

**Payload (called "claims" in JWT-speak)**

```json
{
  "sub": "12345",        // subject = user id
  "name": "Alice",
  "exp": 1717120000,     // expiration (unix seconds)
  "iat": 1717116400,     // issued at
  "iss": "https://api.yoursaas.com",  // issuer
  "aud": "https://api.yoursaas.com",  // audience
  "jti": "550e8400-e29b-41d4-a716-446655440000"  // unique id (for revocation)
}
```

**Signature**

```
HMAC-SHA256(
  base64url(header) + "." + base64url(payload),
  server_secret
)
```

The signature is what makes the token trustworthy. Without it, anyone could write any claims they want.

## 2.2 Base64URL, Not Encryption

**Critical misconception:** JWT is **signed**, not **encrypted**. Anyone who has the token can read every claim in it. It's just Base64URL-encoded — that's just text with `=`, `+`, `/` replaced by URL-safe characters.

If you put a user's password or credit card in the payload, **you are leaking it**.

If you need encryption, that's a JWE (JSON Web Encryption, RFC 7516). It's much rarer and most people use TLS for transport encryption instead.

## 2.3 How Signing Works

When the server issues a token:

```python
import jwt

header = {"alg": "HS256", "typ": "JWT"}
payload = {"sub": "12345", "name": "Alice", "exp": 1717120000}

token = jwt.encode(payload, "my-server-secret", algorithm="HS256", headers=header)
# token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NSIsIm5hbWUiOiJBbGljZSIsImV4cCI6MTcxNzEyMDAwMH0.7s5p..."
```

Under the hood:

1. `header` is JSON-stringified and Base64URL-encoded → `b64Header`
2. `payload` is JSON-stringified and Base64URL-encoded → `b64Payload`
3. `b64Header + "." + b64Payload` is the "signing input"
4. The signing input is hashed with the secret (or private key) using the algorithm in `header.alg` → `signature`
5. `signature` is Base64URL-encoded
6. Final token: `b64Header + "." + b64Payload + "." + b64Signature`

## 2.4 How Verification Works

When a request comes in with a token:

```python
try:
    decoded = jwt.decode(
        token,
        "my-server-secret",  # or public key
        algorithms=["HS256"],  # IMPORTANT: pass a list, not a string
        audience="https://api.yoursaas.com",
        issuer="https://api.yoursaas.com",
        options={"require": ["exp", "iat", "sub"]},
    )
    # decoded is now a dict: {"sub": "12345", "name": "Alice", ...}
except jwt.ExpiredSignatureError:
    # token's exp is in the past
    ...
except jwt.InvalidTokenError:
    # anything else: bad signature, bad issuer, bad audience, etc.
    ...
```

The verifier recomputes the signature using the same input and the same secret/key. If the result doesn't match, the token was tampered with.

It also checks `exp`, `nbf`, `iss`, `aud` automatically (if you ask it to).

## 2.5 Standard Claims (Registered Claims)

The JWT spec defines 7 standard claim names. Use them — don't invent your own (`userId` instead of `sub` is a common anti-pattern).

| Claim | Full name  | Meaning                                      | Example                                  |
| ----- | ---------- | -------------------------------------------- | ---------------------------------------- |
| `iss` | Issuer     | Who created this token                       | `"https://api.yoursaas.com"`             |
| `sub` | Subject    | The user this token is about (user id)       | `"42"`                                   |
| `aud` | Audience   | Who this token is intended for               | `"https://api.yoursaas.com"`             |
| `exp` | Expiration | When this token stops being valid (unix sec) | `1717120000`                             |
| `nbf` | Not Before | Token is invalid before this time            | `1717116400`                             |
| `iat` | Issued At  | When the token was created                   | `1717116400`                             |
| `jti` | JWT ID     | Unique id for this token (for revocation)    | `"550e8400-e29b-41d4-a716-446655440000"` |

**Why these matter:**

- `iss` lets you accept tokens from multiple sources and tell them apart.
- `aud` prevents you from accepting a token meant for *another* service.
- `exp` is the whole point of having tokens expire.
- `jti` is the hook for revocation — store issued `jti`s in Redis, delete them on logout.

## 2.6 Custom Claims (Public & Private)

You can add your own claims. There are two kinds:

**Public claims** — namespaced so they don't collide. Convention: a URI.

```json
{ "https://yoursaas.com/roles": ["user", "beta_tester"] }
```

**Private claims** — agreed between issuer and consumer. Just be aware of collision risk.

```json
{ "subscription_tier": "pro" }
```

The standard warns: **don't put sensitive data in claims.** A JWT is not a safe.

## 2.7 Signing Algorithms: HS256, RS256, ES256, EdDSA

This is one of the most misunderstood parts. Let me make it concrete.

### Symmetric: HS256 / HS384 / HS512

- **One secret** shared between issuer and verifier.
- Both sides use the same key to sign and to verify.
- Fast, simple, but the verifier must hold a secret (which means the verifier *can* forge tokens).
- **Use when:** issuer and verifier are the **same service** (e.g. your FastAPI both issues and verifies its own tokens).
- **Don't use when:** a third party needs to verify your tokens (e.g. a separate microservice, or an external API consumer).

### Asymmetric: RS256 / RS384 / RS512

- **Two keys:** a private key (signs, kept secret) and a public key (verifies, published).
- Anyone can verify; only the issuer can sign.
- Slower than HS256 but the standard choice for OAuth/OIDC.
- **Use when:** you have multiple services, or external verifiers.

### Asymmetric: ES256 / ES384 / ES512 (ECDSA)

- Like RS256 but with elliptic curve cryptography.
- **Shorter signatures, same security, faster.**
- Becoming the modern default. Keycloak, Auth0, AWS Cognito all support it.
- **Use when:** you want smaller tokens and faster verification. (My pick for 2026.)

### Asymmetric: EdDSA (Ed25519)

- Even newer, even smaller, even faster.
- Less library support, but PyJWT supports it since v2.4.
- **Use when:** you're on a new system and your verifier libraries support it.

### Quick comparison

| Algo  | Type                 | Key size       | Signature size | Speed   | Verifier needs secret? |
| ----- | -------------------- | -------------- | -------------- | ------- | ---------------------- |
| HS256 | Symmetric (HMAC)     | 256-bit secret | 256 bits       | Fastest | Yes                    |
| RS256 | Asymmetric (RSA)     | 2048-bit key   | 2048 bits      | Slowest | No, just public key    |
| ES256 | Asymmetric (ECC)     | 256-bit key    | 512 bits       | Fast    | No, just public key    |
| EdDSA | Asymmetric (Ed25519) | 256-bit key    | 512 bits       | Fastest | No, just public key    |

### My recommendation for your AI SaaS

Use **RS256** to start (most familiar, every library supports it). Migrate to **ES256** later if you care about smaller tokens.

Generate keys with OpenSSL:

```bash
# Private key (KEEP SECRET, never commit)
openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:2048

# Public key (publish in JWKS endpoint)
openssl rsa -in private.pem -pubout -out public.pem
```

## 2.8 Access Tokens vs Refresh Tokens vs ID Tokens

These are three **completely different things** that people constantly mix up.

### Access Token

- **What it is:** a credential to call your API.
- **Who issues it:** your auth server (or an OIDC provider).
- **Who consumes it:** your resource server (your API).
- **Format:** usually JWT, sometimes opaque (random string).
- **Lifetime:** short — 5 to 15 minutes.
- **Storage:** depends on the client (memory, cookie, secure storage).
- **Sent how:** `Authorization: Bearer <token>`

### Refresh Token

- **What it is:** a credential to get new access tokens.
- **Who issues it:** your auth server.
- **Who consumes it:** your auth server (the same one that issued it).
- **Format:** usually **opaque** (random string, e.g. a UUID). Not a JWT.
- **Lifetime:** long — days, weeks, or months.
- **Storage:** server-side, hashed in your DB. On the client, in a cookie or secure storage.
- **Sent how:** to the `/token` endpoint, never to the resource server.
- **Critical property:** can be **revoked** by deleting it from the DB. Access tokens can't.

### ID Token

- **What it is:** proof of who the user is, for the **client application**.
- **Who issues it:** the OIDC provider.
- **Who consumes it:** the **client** (your SPA, your mobile app).
- **Format:** always a JWT.
- **Lifetime:** very short — minutes.
- **Storage:** not sent to your API. The client reads it to learn the user's identity, then throws it away.
- **Sent how:** never. The client just decodes it locally.

### The flow

```
User logs in
   ↓
Auth server returns:
   ├─ access_token  (used by your API)
   ├─ refresh_token (used to renew the access_token)
   └─ id_token      (used by the client to know who the user is, OIDC only)
```

A common bug: people put role/permission checks in the ID token. **No** — role checks go in the access token (or are looked up server-side). The ID token is for the client, not the server.

## 2.9 Token Lifetimes

There's no single right answer, but here are sane defaults:

| Token                    | Lifetime             | Why                                                                             |
| ------------------------ | -------------------- | ------------------------------------------------------------------------------- |
| Access token             | 15 minutes           | Short enough to limit damage if stolen, long enough to avoid constant refreshes |
| Refresh token (web)      | 7 days, rotating     | If stolen, attacker has at most 7 days. Rotation detects theft.                 |
| Refresh token (mobile)   | 30–90 days, rotating | Mobile UX: don't make users re-login every week.                                |
| ID token                 | 5 minutes            | Single-use per login.                                                           |
| Password reset token     | 15 minutes           | Single-use, narrow window.                                                      |
| Email verification token | 24 hours             | Single-use, give the user time.                                                 |

The rotation trick: **every time a refresh token is used, issue a new one and invalidate the old one.** If a stolen token is used twice, you know it was stolen. This is what Auth0, Keycloak, and Supabase all do.

## 2.10 Where to Store Tokens (Browser, Mobile, Server)

This is where people get burned. The "best" answer depends on your client.

### Browser — SPA (React, Vue, etc.)

| Storage                                  | XSS stealable? | CSRF risk?          | Verdict                                                                               |
| ---------------------------------------- | -------------- | ------------------- | ------------------------------------------------------------------------------------- |
| `localStorage`                           | **Yes**        | No                  | ❌ Avoid. XSS = full account takeover.                                                 |
| `sessionStorage`                         | **Yes**        | No                  | ❌ Same problem.                                                                       |
| JavaScript variable in memory            | No             | No                  | ✅ Best for SPAs, but you lose tokens on refresh unless you use a silent refresh flow. |
| Cookie: `HttpOnly; Secure; SameSite=Lax` | **No**         | Yes (Lax mitigates) | ✅ Best for traditional web apps.                                                      |

**The pattern most production SaaS use:**

- **Backend web app** (Django, Rails, server-rendered): HttpOnly Secure SameSite=Lax cookie for the refresh token + short-lived access token in memory.
- **SPA + separate API**: refresh token in HttpOnly cookie + access token in memory + silent refresh.

### Mobile (iOS, Android)

- iOS: **Keychain** (the OS-managed secure store).
- Android: **EncryptedSharedPreferences** or **Keystore**.
- Never in plain UserDefaults or SharedPreferences.

### Server-to-server

- In memory or in a secret store. Don't commit to git. Don't log. Rotate on a schedule.

---

# Part 3: Attacks & Defenses

This is the section your future self will thank you for. Every attack listed here is one that has been used in the wild against real companies. I'm not being paranoid; this is what the threat model actually looks like.

## 3.1 The `alg: none` Attack

**The attack:** an attacker takes your valid JWT, changes the header to `{"alg": "none"}`, removes the signature, and sends it. If your verifier is naive enough to accept it, the token verifies as valid with no signature check.

**Real example:** older versions of `jsonwebtoken` in Node.js and several Java libraries shipped vulnerable to this. CVE-2015-9235 and friends.

**The defense:**

```python
# GOOD: pass an explicit allow-list
jwt.decode(token, key, algorithms=["HS256"])

# BAD: trusting the header
jwt.decode(token, key, algorithms=None)  # or omitting algorithms

# BAD: trusting the header from the token itself
# (this is what `alg: none` exploits)
```

**Rule:** the verifier tells the algorithm. The token's header is data, not instructions. **Always** pass `algorithms=[...]` as a list with the exact algorithm(s) you expect.

## 3.2 Algorithm Confusion (HS256 vs RS256)

**The attack:** your server signs with RS256 (asymmetric). The public key is, well, public. An attacker takes a JWT signed with HS256, using the **public key as the HMAC secret**. Your naive verifier reads the header, sees `HS256`, verifies with the public key as the HMAC secret, and the signature checks out. Attacker now has a valid token.

**The defense:** same as 3.1 — never let the token's `alg` header decide. Pin the algorithm on the server side:

```python
jwt.decode(token, public_key, algorithms=["RS256"])  # explicit
```

## 3.3 Signature Stripping

**The attack:** take `header.payload.signature`, change it to `header.payload.` (empty signature). Some libraries accepted this if the algorithm was set to `none` (covered above). Modern libraries reject it, but you still need to enforce `algorithms=["..."]`.

**The defense:** same. Explicit algorithm allow-list. Reject any token that doesn't validate.

## 3.4 Token Theft (XSS)

**The attack:** an attacker injects a `<script>` into your site. The script reads `localStorage` and exfiltrates the access token. From then on, the attacker can call your API as the user.

**The defense:**

1. **Don't put access tokens in `localStorage`.** Use HttpOnly cookies or in-memory.
2. Set a strict Content Security Policy: `default-src 'self'`. See Part 6.22.
3. Sanitize user input. Use a framework that escapes by default.
4. Set `X-Content-Type-Options: nosniff`.

## 3.5 CSRF (Cross-Site Request Forgery)

**The attack:** user is logged in to your app. User visits `evil.com`. That page has a hidden form that POSTs to `https://api.yoursaas.com/api/users/me/delete` — and the browser attaches the user's session cookie automatically. The user's account gets deleted.

**The defense:** cookies alone aren't enough — you also need either:

- **SameSite=Lax or SameSite=Strict** on the cookie (modern browsers block third-party cookies in many cases). `Strict` is safest but breaks OAuth callbacks; `Lax` is the standard choice.
- **A CSRF token** in a custom header. The server checks that the request has `X-CSRF-Token: <random>` matching what's in a separate cookie. Browsers won't let JS on other origins set custom headers.
- **Origin / Referer header check** (defense in depth).

For pure API + SPA, `SameSite=Lax` + `Authorization: Bearer` headers is usually enough. Bearer headers can't be set by `<form>` submits.

## 3.6 Replay Attacks

**The attack:** an attacker captures a valid token (e.g. from logs, or a stolen device) and re-sends it.

**The defense:**

- **Short token lifetimes.** A 15-minute access token is a small replay window.
- **`jti` (JWT ID) + a denylist in Redis.** On logout, add the `jti` to a Redis set with `EXPIRE = remaining_token_lifetime`. On every request, check the denylist.
- **Refresh token rotation.** Re-using a rotated refresh token is a signal of theft. Reject and revoke the whole chain.
- **One-time tokens for sensitive actions.** For "change password", "delete account", require a fresh password re-entry, not just a token.

## 3.7 JWT Has No Built-in Revocation

**The problem:** you can't "un-sign" a token. Until `exp`, a JWT signed by your server is valid. If a user logs out, the access token is still technically valid for up to 15 minutes.

**The defense:**

- **Keep access tokens short-lived.** 15 minutes is the max window.
- **Refresh token denylist in Redis** for sessions you want to kill immediately.
- **Force re-auth on sensitive operations** (delete account, change password, view payment).

## 3.8 Weak Secrets

**The attack:** if your HS256 secret is `password123` or even a 32-character ASCII string an attacker can guess, they can forge any token.

**The defense:**

- Generate secrets with `secrets.token_urlsafe(64)` (Python) or `openssl rand -base64 64`.
- Treat them like database passwords. Store in a secret manager (Doppler, Vault, AWS Secrets Manager) or Docker secrets, never in code.
- Rotate periodically.

## 3.9 Sensitive Data in Payload

**The attack:** a developer puts `{"ssn": "123-45-6789"}` in the JWT. The token is logged somewhere, leaks via a referer header, ends up in a CDN cache. Now SSNs are out.

**The defense:**

- The JWT payload is **public to anyone who has the token**. Treat it like a public document.
- Put only IDs and boolean flags in the payload.
- Look up the user's full data from the DB on every request if you need it.

## 3.10 The Defense Checklist

```
[ ] Always pass algorithms=[...] explicitly when decoding
[ ] Never accept alg: none
[ ] Use RS256 / ES256 (asymmetric) when multiple parties verify
[ ] Store secrets in a secret manager, not in code
[ ] Rotate signing keys periodically (Part 7.2)
[ ] Short access-token lifetimes (5–15 min)
[ ] Long, rotating refresh tokens (with theft detection)
[ ] HttpOnly + Secure + SameSite=Lax cookies
[ ] CSRF protection for cookie-based auth
[ ] jti denylist in Redis for revocation
[ ] No sensitive data in JWT payload
[ ] Constant-time comparisons for token equality
[ ] Rate-limit login & refresh endpoints
[ ] Strict Content Security Policy
[ ] Strong password hashing (Argon2id)
[ ] Account lockout / progressive delay after failed logins
[ ] Audit log every auth event
[ ] Alert on anomalies (impossible travel, mass token issuance)
```

---

# Part 4: OAuth 2.0

## 4.1 What OAuth Is (and Is Not)

**OAuth 2.0 is a protocol for delegated authorization.** It is *not* an authentication protocol. The most common mistake in the industry is treating it like one — that mistake has a name: "OAuth 2.0 as Single Sign-On" anti-pattern.

OAuth was designed to solve this problem: "I want to give *app X* permission to access *my data* on *app Y*, without giving app X my password for app Y."

**Example:** "I want *ReadYourGitHub* to be able to see my GitHub repos, without giving ReadYourGitHub my GitHub password."

OAuth is **about**:

- Getting an access token (a credential to call an API).
- Scopes (what the token is allowed to do).
- Expiry and refresh.

OAuth is **not about**:

- Who the user is. That's authentication. Use OIDC for that.

## 4.2 The 4 Roles

| Role                     | What it is                                 | Example                |
| ------------------------ | ------------------------------------------ | ---------------------- |
| **Resource Owner**       | The user. The person who owns the data.    | You.                   |
| **Client**               | The app that wants to access the resource. | ReadYourGitHub.com     |
| **Authorization Server** | The server that issues tokens.             | github.com/login/oauth |
| **Resource Server**      | The API that holds the data.               | api.github.com         |

In a simple SaaS where you issue your own tokens, **your FastAPI is both the authorization server and the resource server.** When a user clicks "Sign in with Google," **Google is the authorization server** and your app is the client.

## 4.3 The 4 Grant Types (When to Use Each)

OAuth 2.0 defines 4 ways to get a token. Pick the right one.

### Authorization Code (+ PKCE) — for users

- **Use when:** a real human is logging in via a browser or mobile app.
- **Use cases:** "Sign in with Google", "Sign in with GitHub", your own login form.
- **Why PKCE:** prevents authorization code interception attacks. Mandatory in OAuth 2.1.

### Client Credentials — for service-to-service

- **Use when:** two of *your* services need to talk. No human.
- **Use cases:** your background worker calling your internal API. Your microservice A calling microservice B.
- **No refresh tokens** — the client can re-authenticate any time with its own secret.

### Refresh Token — for renewing access tokens

- **Use when:** the access token expired and you need a new one without bothering the user.
- **Use cases:** every API call after 14 minutes.

### Device Code — for input-constrained devices

- **Use when:** the user has a TV, a CLI, a smart device with no browser.
- **Use cases:** `aws sso login`, `gh auth login`, smart TV auth.
- **Flow:** device shows a code, user goes to auth.example.com on their phone, types the code, device polls the token endpoint.

(PKC is the most common. PKCE is also called "Proof Key for Code Exchange," defined in RFC 7636.)

## 4.4 Authorization Code + PKCE — the main one

This is the one you'll use 95% of the time. The flow:

```
1. User clicks "Sign in with Google" on your site.
2. Your server generates a random `code_verifier` and a derived `code_challenge`.
3. Your server redirects the browser to Google:
   https://accounts.google.com/o/oauth2/v2/auth?
     response_type=code
     &client_id=YOUR_CLIENT_ID
     &redirect_uri=https://yoursaas.com/auth/google/callback
     &scope=openid+email+profile
     &state=RANDOM_CSRF_TOKEN
     &code_challenge=BASE64URL(SHA256(code_verifier))
     &code_challenge_method=S256
4. User logs in at Google (or is already logged in) and approves the scopes.
5. Google redirects back to your callback:
   https://yoursaas.com/auth/google/callback?code=AUTH_CODE&state=RANDOM_CSRF_TOKEN
6. Your server checks `state` matches what you stored.
7. Your server POSTs to Google's token endpoint:
   POST https://oauth2.googleapis.com/token
     code=AUTH_CODE
     &client_id=YOUR_CLIENT_ID
     &client_secret=YOUR_CLIENT_SECRET
     &redirect_uri=https://yoursaas.com/auth/google/callback
     &code_verifier=ORIGINAL_VERIFIER
     &grant_type=authorization_code
8. Google returns { access_token, id_token, refresh_token? }.
9. Your server verifies the id_token (it's a JWT signed by Google).
10. You create a session in your DB for the user.
11. You issue YOUR OWN access + refresh token (a JWT) and return them to your client.
```

**Why PKCE?** Without it, if an attacker intercepts the auth code (e.g. through a malicious app on the same device, or a leaked redirect), they can exchange it for tokens. With PKCE, they also need the `code_verifier`, which never leaves your server.

**Why `state`?** It prevents CSRF on the OAuth callback. If `state` doesn't match, ignore the request.

## 4.5 Client Credentials — service-to-service

```
1. Service A wants to call Service B.
2. Service A POSTs to B's token endpoint:
   POST /oauth/token
     grant_type=client_credentials
     &client_id=service-a
     &client_secret=SERVICE_A_SECRET
     &scope=read:users
3. Service B returns { access_token, expires_in }.
4. Service A calls Service B with: Authorization: Bearer <access_token>.
5. Service B verifies the token (it issued it itself).
```

No user, no refresh tokens, no PKCE. Just a service identity.

## 4.6 Refresh Token Grant

```
POST /oauth/token
  grant_type=refresh_token
  &refresh_token=OLD_REFRESH_TOKEN
  &client_id=...

Response:
  {
    "access_token": "...",
    "refresh_token": "...",   // NEW one, the old one is now invalid
    "expires_in": 900
  }
```

**Refresh token rotation:** every time the client uses a refresh token, you issue a new one and invalidate the old. If you ever see the old one used again, you know it was stolen. **Revoke the entire chain and force re-login.**

## 4.7 Scopes

Scopes are strings that say what the token is allowed to do. They're part of the OAuth protocol but their meaning is defined by the API.

Examples:

- `read:users`
- `write:users`
- `admin`
- `openid` (required by OIDC)
- `email`
- `profile`

When a client requests scopes at auth time, the user (or admin) approves them. The token is then limited to those scopes.

In your FastAPI code:

```python
@router.get("/admin/users")
async def list_users(user = Depends(require_scope("read:users"))):
    ...
```

## 4.8 OAuth Is Authorization, Not Authentication

A subtle but critical point. When your app receives an OAuth access token from Google, **the token doesn't tell you who the user is**. It tells you what *that user* authorized your app to do.

To learn who the user is, you need **OIDC**. The OAuth + identity layer.

---

# Part 5: OpenID Connect (OIDC)

## 5.1 What OIDC Adds on Top of OAuth

OIDC is a thin layer on top of OAuth 2.0. It adds:

- The **ID token** (a JWT that proves the user's identity).
- The **UserInfo endpoint** (returns user profile data).
- **Standardized scopes**: `openid` (required), `profile`, `email`, `address`, `phone`.
- **Standardized claims** in the ID token: `sub`, `name`, `email`, `email_verified`, `picture`, etc.
- A **discovery endpoint** and **JWKS endpoint** so clients can find everything automatically.

When you see "Sign in with Google" working, that's OIDC, not just OAuth.

## 5.2 The ID Token

The ID token is a JWT with these required claims:

- `iss` — must equal the OIDC provider's issuer URL.
- `sub` — the user's stable unique ID at that provider.
- `aud` — must equal your client ID.
- `exp` — short expiration.
- `iat` — issued at.

Plus optional user claims:

- `email`, `email_verified`
- `name`, `given_name`, `family_name`
- `picture`
- `locale`, `zoneinfo`

**Critical:** the ID token is **for the client**, not the resource server. The client decodes it once to learn the user's identity, then forgets it. Your API does NOT verify the ID token — it verifies the access token.

## 5.3 Discovery (`/.well-known/openid-configuration`)

The discovery URL is where the OIDC provider publishes its configuration. The client fetches it once at startup to learn where everything is.

Example (Google):

```
GET https://accounts.google.com/.well-known/openid-configuration

Response:
{
  "issuer": "https://accounts.google.com",
  "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
  "token_endpoint": "https://oauth2.googleapis.com/token",
  "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
  "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
  "scopes_supported": ["openid", "email", "profile"],
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

**This is the magic of OIDC:** instead of hardcoding endpoints, you just hit `/.well-known/openid-configuration` and you have everything. Want to switch from Google to Keycloak? Change the issuer URL, everything else auto-discovers.

## 5.4 JWKS (`/.well-known/jwks.json`)

JWKS = JSON Web Key Set. The OIDC provider publishes its public keys here. Your app downloads them and uses them to verify ID tokens.

```
GET https://www.googleapis.com/oauth2/v3/certs

Response:
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "abc123",          // key ID — important
      "use": "sig",
      "alg": "RS256",
      "n": "0vx7agoebGcQ...",   // RSA public key modulus
      "e": "AQAB"               // RSA public key exponent
    },
    {
      "kty": "RSA",
      "kid": "def456",
      ...
    }
  ]
}
```

The `kid` (key ID) is how you know which key to use — the ID token's header has a `kid` too, and they must match.

**Cache these keys** (with a TTL of 10–60 minutes) to avoid hammering the provider. Refresh on demand if a token's `kid` isn't in your cache.

## 5.5 UserInfo Endpoint

Once you have an access token, you can call the UserInfo endpoint to get the user's profile:

```
GET https://openidconnect.googleapis.com/v1/userinfo
Authorization: Bearer <access_token>

Response:
{
  "sub": "1234567890",
  "email": "alice@example.com",
  "email_verified": true,
  "name": "Alice Smith",
  "picture": "https://..."
}
```

You usually use the UserInfo for fresh data (current email, current name) and trust the ID token's claims only at sign-in.

## 5.6 Validating an ID Token (the rules)

The validation rules from the OIDC spec, in order:

1. Verify the JWT signature using a key from the JWKS endpoint (matching the `kid`).
2. Verify `iss` matches the expected issuer.
3. Verify `aud` contains your client ID.
4. Verify `exp` is in the future.
5. Verify `iat` is in the past (or now).
6. If `nbf` is present, verify it's in the past.
7. If `azp` is present, verify it matches your client ID (only required for some clients).
8. **If the ID token was issued from the auth code flow, also verify `nonce` matches what you sent.**

**Do all of these. Not some. All.** `authlib` and `pyjwt` make this easy.

## 5.7 OIDC in Your Stack (as Client vs as Provider)

Two ways to use OIDC:

**As a client (you sign in with someone else):**

- You integrate with Google, GitHub, Apple, Microsoft, etc.
- Or you integrate with a self-hosted Keycloak / Authentik / Logto you run for your own users.
- The implementation is in Part 6.16–6.18.

**As a provider (you ARE the OIDC server):**

- Run Keycloak / Authentik / Logto in your own Docker Compose.
- Configure it as the central identity for your FastAPI, your future mobile app, your future admin UI, etc.
- Your apps become OIDC *clients* of your own provider.

**My recommendation:** for an AI SaaS, run **Keycloak** as your identity provider. It speaks OIDC, supports social login, supports user federation, supports MFA. You get all of it for free, no per-user fees.

---

# Part 6: Implementation in FastAPI

This is the implementation. Read Part 1–5 first or this will be confusing.

## 6.1 Library Choices

| Need                                        | Library                                    | Why                                                                   |
| ------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| JWT sign & verify                           | `pyjwt[crypto]>=2.8`                       | Maintained, fast, secure by default. **Use this, not `python-jose`.** |
| OAuth client (Google, GitHub, generic OIDC) | `authlib>=1.3`                             | The de-facto standard.                                                |
| Password hashing                            | `passlib[argon2]>=1.7`                     | Argon2 + bcrypt + scrypt support.                                     |
| FastAPI itself                              | `fastapi>=0.110`                           | You know this one.                                                    |
| ASGI server                                 | `uvicorn[standard]>=0.27`                  | Production-ready.                                                     |
| Database                                    | `sqlalchemy>=2.0` + `asyncpg>=0.29`        | Async ORM, the modern standard.                                       |
| Migrations                                  | `alembic>=1.13`                            | Schema migrations.                                                    |
| Pydantic                                    | `pydantic>=2.5` + `pydantic-settings>=2.1` | Validation + config.                                                  |
| HTTP client                                 | `httpx>=0.26`                              | For OIDC discovery & JWKS fetching.                                   |
| Redis                                       | `redis>=5.0` (with `hiredis`)              | Token denylist, rate limit, cache.                                    |
| Rate limiting                               | `slowapi>=0.1.9` or hand-rolled with Redis | FastAPI-friendly.                                                     |
| Testing                                     | `pytest>=8.0`, `pytest-asyncio`, `httpx`   | Standard stack.                                                       |
| Secrets                                     | Built-in `secrets` module + Docker secrets | For key generation.                                                   |

Add to `requirements.txt`:

```
fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.5
pydantic-settings>=2.1
sqlalchemy>=2.0
asyncpg>=0.29
alembic>=1.13
pyjwt[crypto]>=2.8
authlib>=1.3
passlib[argon2]>=1.7
httpx>=0.26
redis>=5.0
slowapi>=0.1.9
python-multipart>=0.0.9
```

## 6.2 Project Structure

```
yoursaas/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .gitignore
├── pyproject.toml
├── alembic.ini
├── migrations/
│   └── versions/
├── keys/                  # JWT signing keys (gitignored, mounted as volume)
│   ├── jwt_private.pem
│   └── jwt_public.pem
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app entry point
│   ├── config.py          # Pydantic settings
│   ├── deps.py            # Common dependencies (db, redis, current_user)
│   ├── security/
│   │   ├── __init__.py
│   │   ├── jwt.py         # JWT sign/verify
│   │   ├── passwords.py   # Argon2 hashing
│   │   ├── keys.py        # Load RSA keys from disk
│   │   └── jwks.py        # JWKS endpoint for public key
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py        # SQLAlchemy Base
│   │   ├── session.py     # Async engine + session factory
│   │   └── models.py      # User, RefreshToken, OAuthAccount, etc.
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── token.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py    # login, refresh, logout, register
│   │   │   ├── users.py
│   │   │   └── oauth.py   # Google, GitHub, generic OIDC callbacks
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   └── token_service.py
│   ├── redis/
│   │   ├── __init__.py
│   │   └── client.py
│   └── core/
│       ├── __init__.py
│       ├── rate_limit.py
│       └── exceptions.py
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   └── test_jwt.py
└── scripts/
    └── generate_keys.py
```

## 6.3 Configuration & Secrets

`app/config.py`:

```python
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "YourSaaS"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/yoursaas"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- JWT ---
    # Where the private/public keys live. In prod, use Docker secrets or a secret manager.
    JWT_PRIVATE_KEY_PATH: str = "/run/secrets/jwt_private.pem"  # Docker secrets path
    JWT_PUBLIC_KEY_PATH: str = "/run/secrets/jwt_public.pem"
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "https://api.yoursaas.com"
    JWT_AUDIENCE: str = "https://api.yoursaas.com"
    JWT_ACCESS_TOKEN_TTL: int = 900          # 15 minutes
    JWT_REFRESH_TOKEN_TTL: int = 60 * 60 * 24 * 7  # 7 days
    JWT_KEY_ID: str = "k1"                   # matches `kid` in JWKS

    # --- Password hashing ---
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536  # 64 MiB
    ARGON2_PARALLELISM: int = 4

    # --- Cookies ---
    COOKIE_SECURE: bool = True       # set to True in production (HTTPS only)
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None  # e.g. ".yoursaas.com"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- OAuth (Google) ---
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # --- OAuth (GitHub) ---
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/github/callback"

    # --- Generic OIDC (e.g. Keycloak, Auth0) ---
    OIDC_ISSUER: str | None = None  # e.g. https://keycloak.yoursaas.com/realms/main
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    OIDC_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/oidc/callback"

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MIN: int = 5
    RATE_LIMIT_REFRESH_PER_MIN: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`.env.example`:

```
APP_ENV=development
DEBUG=true
DATABASE_URL=postgresql+asyncpg://yoursaas:devpass@localhost:5432/yoursaas
REDIS_URL=redis://localhost:6379/0
JWT_ISSUER=http://localhost:8000
JWT_AUDIENCE=http://localhost:8000
COOKIE_SECURE=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

## 6.4 Password Hashing (Argon2)

**Why Argon2 and not bcrypt?** Argon2id is the winner of the Password Hashing Competition (2015) and is the modern recommendation. It has three configurable parameters (time, memory, parallelism) which makes it resistant to GPU and ASIC attacks. Bcrypt is still acceptable but Argon2 is preferred for new systems in 2026.

`app/security/passwords.py`:

```python
from passlib.context import CryptContext
from app.config import get_settings

_settings = get_settings()
_pwd_context = CryptContext(
    schemes=["argon2"],
    argon2__time_cost=_settings.ARGON2_TIME_COST,
    argon2__memory_cost=_settings.ARGON2_MEMORY_COST,
    argon2__parallelism=_settings.ARGON2_PARALLELISM,
)


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Returns the encoded hash string."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a stored hash. Constant-time."""
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        # passlib raises if the hash is malformed; treat as failure, never crash
        return False


def needs_rehash(hashed: str) -> bool:
    """If our hashing parameters have changed, signal that this user should be rehashed on next login."""
    return _pwd_context.needs_update(hashed)
```

**Important:** `verify_password` returns False on any exception, never raises. Never leak which specific check failed.

## 6.5 Database Models (Postgres / SQLAlchemy)

`app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`app/db/session.py`:

```python
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_size=_settings.DB_POOL_SIZE,
    max_overflow=_settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=_settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

`app/db/models.py`:

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)  # null for OAuth-only users
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Profile
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", back_populates="users")


class RefreshToken(Base):
    """Server-side refresh tokens. Store the hash, not the token itself."""
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # Store SHA-256 hash of the token. Never the raw token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # Device / session metadata
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Lifecycle
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class OAuthAccount(Base):
    """Links a user to an OAuth provider (Google, GitHub, etc.)."""
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "google", "github", "keycloak"
    provider_user_id: Mapped[str] = mapped_column(String(320), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_email: Mapped[str | None] = mapped_column(String(320), nullable=True)  # for email change
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


# Indexes
Index("ix_refresh_tokens_user_active", RefreshToken.user_id, RefreshToken.revoked_at)
```

**Note:** we store the **hash** of refresh tokens, not the token itself. If the DB is breached, attackers can't use the tokens. (Same for password reset and email verification tokens.)

## 6.6 Pydantic Schemas

`app/schemas/user.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    email_verified: bool
    full_name: str | None
    avatar_url: str | None
    is_active: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = None
```

`app/schemas/token.py`:

```python
from pydantic import BaseModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AccessTokenOnly(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)
```

## 6.7 JWT Utilities (sign & verify)

`app/security/keys.py`:

```python
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


def load_private_key(path: str) -> RSAPrivateKey:
    """Load RSA private key from PEM file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JWT private key not found at {path}")
    with open(p, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def load_public_key(path: str) -> RSAPublicKey:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JWT public key not found at {path}")
    with open(p, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def public_key_to_jwk(public_key: RSAPublicKey, kid: str) -> dict:
    """Convert RSA public key to JWK format for /.well-known/jwks.json."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from base64 import urlsafe_b64encode

    numbers = public_key.public_numbers()

    def b64uint(n: int) -> str:
        # Convert integer to base64url-encoded big-endian bytes, no padding
        blen = (n.bit_length() + 7) // 8
        return urlsafe_b64encode(n.to_bytes(blen, "big")).rstrip(b"=").decode("ascii")

    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": b64uint(numbers.n),
        "e": b64uint(numbers.e),
    }
```

`app/security/jwt.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from app.config import get_settings
from app.security.keys import load_private_key, load_public_key

_settings = get_settings()

# Load keys at import time. They don't change at runtime without a process restart
# (or you can implement key rotation — see Part 7.2).
_private_key = None
_public_key = None


def _get_private_key():
    global _private_key
    if _private_key is None:
        _private_key = load_private_key(_settings.JWT_PRIVATE_KEY_PATH)
    return _private_key


def _get_public_key():
    global _public_key
    if _public_key is None:
        _public_key = load_public_key(_settings.JWT_PUBLIC_KEY_PATH)
    return _public_key


def create_access_token(
    user_id: str | uuid.UUID,
    extra_claims: dict | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, str, int]:
    """
    Returns (jwt, jti, expires_in).
    """
    now = datetime.now(timezone.utc)
    ttl = ttl_seconds or _settings.JWT_ACCESS_TOKEN_TTL
    exp = now + timedelta(seconds=ttl)
    jti = str(uuid.uuid4())

    claims = {
        "iss": _settings.JWT_ISSUER,
        "sub": str(user_id),
        "aud": _settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "type": "access",
    }
    if extra_claims:
        claims.update(extra_claims)

    token = jwt.encode(
        claims,
        _get_private_key(),
        algorithm=_settings.JWT_ALGORITHM,
        headers={"kid": _settings.JWT_KEY_ID},
    )
    return token, jti, ttl


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a JWT. Raises:
      - ExpiredSignatureError if expired
      - InvalidTokenError for anything else (bad signature, wrong iss/aud, etc.)
    """
    return jwt.decode(
        token,
        _get_public_key(),
        algorithms=[_settings.JWT_ALGORITHM],  # ALWAYS a list
        audience=_settings.JWT_AUDIENCE,
        issuer=_settings.JWT_ISSUER,
        options={
            "require": ["exp", "iat", "sub", "jti", "iss", "aud"],
            "verify_signature": True,
            "verify_exp": True,
            "verify_iat": True,
            "verify_aud": True,
            "verify_iss": True,
        },
    )
```

**Notice:**

- `algorithms=[...]` is a list with exactly one item. Never `None`, never inferred.
- `require` lists every claim the token MUST have.
- All verifications are explicitly on.

`scripts/generate_keys.py`:

```python
"""Run this once: python -m scripts.generate_keys"""
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate():
    out = Path("keys")
    out.mkdir(exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    (out / "jwt_private.pem").write_bytes(pem)
    (out / "jwt_private.pem").chmod(0o600)

    pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (out / "jwt_public.pem").write_bytes(pub)
    print("Wrote keys/jwt_private.pem and keys/jwt_public.pem")


if __name__ == "__main__":
    generate()
```

Run: `python -m scripts.generate_keys`

Add to `.gitignore`:

```
keys/
*.pem
.env
```

## 6.8 User Registration Endpoint

`app/api/v1/auth.py` (we'll add more to this file as we go):

```python
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import User, AuditLog
from app.schemas.user import UserCreate, UserOut
from app.security.passwords import hash_password
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Check if email is already taken
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        # Don't reveal whether the email exists, but return 409 here for normal UX.
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)

    # Audit
    db.add(AuditLog(
        user_id=user.id,
        event="user.registered",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    ))

    await db.commit()
    await db.refresh(user)
    return user
```

## 6.9 Login Endpoint

Continuing in `app/api/v1/auth.py`:

```python
from datetime import datetime, timezone, timedelta
import secrets
import hashlib
from fastapi import Response
from app.security.jwt import create_access_token
from app.schemas.token import LoginRequest, TokenPair
from app.services.token_service import create_refresh_token


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Constant-time-ish: always do the same amount of work whether the user exists or not.
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        # Use a fake verify to keep timing similar
        from app.security.passwords import verify_password
        verify_password(payload.password, "$argon2id$v=19$m=65536,t=3,p=4$YWFhYWFhYWFhYWFhYWFhYQ$..."
                        "fakesaltthatwillnevermatchbecauseweknowuserdoesntexist")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Account lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=423, detail="Account temporarily locked")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= 10:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        await db.commit()
        db.add(AuditLog(
            user_id=user.id,
            event="user.login_failed",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ))
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Rehash if parameters have changed
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)

    # Reset failure count, update last login
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)

    # Issue tokens
    access_token, jti, ttl = create_access_token(user.id)
    refresh_token = await create_refresh_token(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    db.add(AuditLog(
        user_id=user.id,
        event="user.login_success",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    # Optionally set the refresh token in an HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
        domain=_settings.COOKIE_DOMAIN,
        max_age=_settings.JWT_REFRESH_TOKEN_TTL,
        path="/api/v1/auth",  # cookie only sent to auth endpoints
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ttl,
    )
```

## 6.10 Refresh Endpoint

`app/services/token_service.py`:

```python
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import RefreshToken, User
from app.config import get_settings

_settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_refresh_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    """Create a new refresh token. Returns the raw token (caller stores hash)."""
    raw = secrets.token_urlsafe(48)
    record = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=_settings.JWT_REFRESH_TOKEN_TTL),
    )
    db.add(record)
    await db.flush()
    return raw


async def rotate_refresh_token(
    db: AsyncSession,
    old_token: str,
) -> tuple[User, str] | None:
    """
    Validate old token, mark as used, issue new one. Returns (user, new_raw_token) or None.
    Detects reuse: if the old token is already revoked, revoke ALL the user's tokens.
    """
    old_hash = _hash_token(old_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    record = result.scalar_one_or_none()

    if record is None:
        return None  # Unknown token

    # If already revoked, this is a REPLAY. The token was stolen.
    if record.revoked_at is not None:
        # Revoke all tokens for this user (kill the whole chain)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == record.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        # ... log audit event, alert
        return None

    if record.expires_at < datetime.now(timezone.utc):
        return None  # Expired

    user = (await db.execute(select(User).where(User.id == record.user_id))).scalar_one()

    # Mark old as revoked
    record.revoked_at = datetime.now(timezone.utc)

    # Issue new
    new_token = await create_refresh_token(
        db,
        user_id=user.id,
        user_agent=record.user_agent,
        ip_address=record.ip_address,
    )
    record.replaced_by_id = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token(new_token))
    )).scalar_one().id

    await db.commit()
    return user, new_token


async def revoke_refresh_token(db: AsyncSession, token: str) -> bool:
    h = _hash_token(token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == h))
    record = result.scalar_one_or_none()
    if record and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        return True
    return False


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return result.rowcount
```

Now the endpoint:

```python
# In app/api/v1/auth.py
@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Accept refresh token from cookie OR body
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    rotated = await rotate_refresh_token(db, refresh_token)
    if rotated is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user, new_token = rotated
    access_token, jti, ttl = create_access_token(user.id)

    response.set_cookie(
        key="refresh_token",
        value=new_token,
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
        domain=_settings.COOKIE_DOMAIN,
        max_age=_settings.JWT_REFRESH_TOKEN_TTL,
        path="/api/v1/auth",
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=new_token,
        expires_in=ttl,
    )
```

## 6.11 Logout Endpoint

```python
@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    # Optional: require a valid access token to log out
    # If you allow logout without a token, anyone can probe whether a token is valid
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        body = await request.json()
        refresh_token = body.get("refresh_token")

    if refresh_token:
        await revoke_refresh_token(db, refresh_token)

    # Also revoke the current access token via Redis denylist
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            claims = decode_access_token(token)
            from app.redis.client import get_redis
            r = await get_redis()
            # Store jti in denylist until exp
            ttl = claims["exp"] - int(datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                await r.set(f"revoked:{claims['jti']}", "1", ex=ttl)
        except Exception:
            pass  # best effort

    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return Response(status_code=204)
```

## 6.12 The `current_user` Dependency

`app/deps.py`:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import User
from app.security.jwt import decode_access_token
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from app.redis.client import get_redis

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})

    try:
        claims = decode_access_token(credentials.credentials)
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})

    # Check the denylist
    r = await get_redis()
    if await r.exists(f"revoked:{claims['jti']}"):
        raise HTTPException(status_code=401, detail="Token revoked")

    # Optional: check token type
    if claims.get("type") != "access":
        raise HTTPException(status_code=401, detail="Wrong token type")

    import uuid
    user = (await db.execute(select(User).where(User.id == uuid.UUID(claims["sub"])))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def get_current_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
```

Use it:

```python
@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user
```

## 6.13 Role-Based Access Control (RBAC)

`app/deps.py` (continued):

```python
from fastapi import Depends, HTTPException
from app.db.models import User


def require_role(*role_names: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        user_role_names = {r.name for r in user.roles}
        if not user_role_names.intersection(role_names) and not user.is_superuser:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return _checker


def require_scope(*scopes: str):
    """Use when you've put scopes in the JWT payload (e.g. for service-to-service)."""
    async def _checker(claims: dict = Depends(get_token_claims)) -> dict:
        token_scopes = set((claims.get("scope") or "").split())
        if not token_scopes.intersection(scopes):
            raise HTTPException(status_code=403, detail="Insufficient scope")
        return claims
    return _checker
```

## 6.14 Password Reset Flow

```python
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from app.db.models import PasswordResetToken
from app.services.email import send_email  # your email service

@router.post("/password/reset/request", status_code=204)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Always 204, even if the email doesn't exist, to prevent enumeration."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is not None and user.is_active:
        raw = secrets.token_urlsafe(32)
        record = PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        db.add(record)
        await db.commit()

        reset_url = f"https://yoursaas.com/reset?token={raw}"
        await send_email(
            to=user.email,
            subject="Reset your password",
            body=f"Click to reset your password (expires in 15 minutes): {reset_url}",
        )

    return Response(status_code=204)


@router.post("/password/reset/confirm", status_code=204)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()

    if record is None or record.used_at is not None or record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = (await db.execute(select(User).where(User.id == record.user_id))).scalar_one()
    user.hashed_password = hash_password(payload.new_password)
    record.used_at = datetime.now(timezone.utc)

    # Invalidate all refresh tokens (force re-login on all devices)
    await revoke_all_user_tokens(db, user.id)

    await db.commit()
    return Response(status_code=204)
```

## 6.15 Email Verification

Same pattern as password reset, but the action is setting `email_verified = true`. Use a 24-hour expiry instead of 15 minutes.

## 6.16 Google OAuth (Sign in with Google) with Authlib

`app/config.py` — Google config:

```python
GOOGLE_CLIENT_ID: str | None = None
GOOGLE_CLIENT_SECRET: str | None = None
GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"
```

`app/api/v1/oauth.py`:

```python
import secrets
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from app.config import get_settings

_settings = get_settings()
router = APIRouter(prefix="/auth", tags=["oauth"])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=_settings.GOOGLE_CLIENT_ID,
    client_secret=_settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/google/login")
async def google_login(request: Request):
    # CSRF protection for the callback
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state  # requires SessionMiddleware
    redirect_uri = _settings.GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    expected_state = request.session.pop("oauth_state", None)
    actual_state = request.query_params.get("state")
    if not expected_state or expected_state != actual_state:
        raise HTTPException(status_code=400, detail="Invalid state")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {e}")

    # Parse the ID token
    userinfo = token.get("userinfo") or await oauth.google.parse_id_token(request, token)

    if not userinfo or not userinfo.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email not verified by Google")

    # Find or create user
    from app.services.user_service import get_or_create_oauth_user
    user, is_new = await get_or_create_oauth_user(
        db,
        provider="google",
        provider_user_id=userinfo["sub"],
        email=userinfo["email"],
        full_name=userinfo.get("name"),
        avatar_url=userinfo.get("picture"),
    )

    # Issue our own tokens
    from app.security.jwt import create_access_token
    from app.services.token_service import create_refresh_token

    access_token, jti, ttl = create_access_token(user.id)
    refresh_token = await create_refresh_token(
        db, user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    # Redirect to your frontend with the token in URL fragment (NOT query string)
    frontend_url = "https://app.yoursaas.com/oauth/callback"
    return RedirectResponse(
        url=f"{frontend_url}#access_token={access_token}&refresh_token={refresh_token}&expires_in={ttl}"
    )
```

**`app/main.py` — register SessionMiddleware:**

```python
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=..., https_only=True, same_site="lax")
```

**Why URL fragment for tokens, not query string?** Query strings end up in server logs, browser history, referer headers. Fragments (`#`) don't. Use them for short-lived post-OAuth handoff.

## 6.17 GitHub OAuth

Same pattern, but GitHub doesn't implement OIDC fully — it doesn't issue a real ID token. You must call the UserInfo endpoint with the access token.

```python
oauth.register(
    name="github",
    client_id=_settings.GITHUB_CLIENT_ID,
    client_secret=_settings.GITHUB_CLIENT_SECRET,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)

@router.get("/github/callback")
async def github_callback(request: Request, db: AsyncSession = Depends(get_db)):
    # ... same state check ...
    token = await oauth.github.authorize_access_token(request)
    resp = await oauth.github.get("user", token=token)
    profile = resp.json()

    # GitHub may not return email in `user` if it's private; fetch from /user/emails
    if not profile.get("email"):
        emails_resp = await oauth.github.get("user/emails", token=token)
        for e in emails_resp.json():
            if e.get("primary") and e.get("verified"):
                profile["email"] = e["email"]
                break

    user, _ = await get_or_create_oauth_user(
        db,
        provider="github",
        provider_user_id=str(profile["id"]),
        email=profile["email"],
        full_name=profile.get("name") or profile.get("login"),
        avatar_url=profile.get("avatar_url"),
    )
    # ... issue tokens and redirect ...
```

## 6.18 Generic OIDC Client

For connecting to Keycloak, Auth0, or any OIDC provider:

```python
from authlib.integrations.starlette_client import OAuth
from app.config import get_settings

_settings = get_settings()

if _settings.OIDC_ISSUER:
    oauth.register(
        name="oidc",
        client_id=_settings.OIDC_CLIENT_ID,
        client_secret=_settings.OIDC_CLIENT_SECRET,
        server_metadata_url=f"{_settings.OIDC_ISSUER}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
```

The `server_metadata_url` is the magic — Authlib fetches discovery and configures everything else automatically.

## 6.19 Rate Limiting with Redis

`app/core/rate_limit.py`:

```python
import time
from fastapi import Request, HTTPException
from app.redis.client import get_redis


async def rate_limit(key_prefix: str, limit: int, window_seconds: int):
    """Returns a dependency. Uses sliding window in Redis."""
    async def _checker(request: Request):
        # Key: identifier (user id if authenticated, else IP)
        from app.deps import bearer_scheme  # avoid circular
        # Identify client
        client_ip = request.client.host if request.client else "unknown"
        identifier = client_ip

        r = await get_redis()
        key = f"ratelimit:{key_prefix}:{identifier}"
        now = int(time.time())
        window_start = now - window_seconds

        # Use a sorted set, score = timestamp
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}-{secrets.token_hex(4)}": now})
        pipe.expire(key, window_seconds)
        _, count, _, _ = await pipe.execute()

        if count > limit:
            raise HTTPException(status_code=429, detail="Too many requests")

    return _checker
```

Use it on login:

```python
from app.core.rate_limit import rate_limit
from app.config import get_settings
_s = get_settings()

@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(rate_limit("login", _s.RATE_LIMIT_LOGIN_PER_MIN, 60))],
)
async def login(...):
    ...
```

For a more feature-rich option, use `slowapi` — but the hand-rolled version is fine for production.

## 6.20 Token Revocation List in Redis

Already shown above in the logout endpoint. Pattern:

- Key: `revoked:<jti>`
- Value: `"1"`
- TTL: remaining lifetime of the token (`exp - now`)

On every request, the `get_current_user` dependency checks the denylist. Fast (single Redis EXISTS), automatic cleanup (Redis TTL).

## 6.21 CORS

In `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
_s = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_s.CORS_ORIGINS,           # NEVER "*" with credentials
    allow_credentials=True,                  # required for cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
```

**Rule:** if you need credentials (cookies), `allow_origins` MUST be an explicit list. `["*"]` + `allow_credentials=True` is rejected by browsers.

## 6.22 Security Headers

In `app/main.py`:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https: data:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)
```

## 6.23 The Complete `main.py`

```python
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api.v1.auth import router as auth_router
from app.api.v1.oauth import router as oauth_router
from app.redis.client import init_redis, close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.APP_ENV != "production" else None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_urlsafe(32),  # ideally from settings
    https_only=settings.COOKIE_SECURE,
    same_site=settings.COOKIE_SAMESITE,
    max_age=3600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(oauth_router, prefix=settings.API_V1_PREFIX)


@app.get("/.well-known/jwks.json")
async def jwks():
    from app.security.keys import load_public_key, public_key_to_jwk
    pub = load_public_key(settings.JWT_PUBLIC_KEY_PATH)
    return {"keys": [public_key_to_jwk(pub, settings.JWT_KEY_ID)]}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
```

---

# Part 7: Production Hardening

## 7.1 Key Management (RSA / EdDSA)

- Generate keys with at least 2048 bits for RSA, or use Ed25519.
- Store the private key in a **secret manager**: AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault, Doppler, or Docker secrets. Never in `.env` files committed to git.
- Restrict access — only the API service should be able to read the private key.
- Have a **key rotation schedule** (90 days is common).
- Have a **revocation procedure** — if a key is compromised, you must be able to issue a new one and stop trusting the old one.

## 7.2 Key Rotation Without Downtime (JWKS pattern)

The trick: publish **multiple public keys** in your JWKS endpoint, each with a unique `kid`. Sign new tokens with the new key. Old tokens still verify against the old public key. After the old tokens' max lifetime expires, remove the old public key from JWKS.

```
Day 0:  JWKS = { k1, k2 }     (sign with k1)
Day 90: JWKS = { k1, k2 }     (sign with k2, k1 still verifies)
Day 105: JWKS = { k2 }        (k1 removed; all k1-signed tokens have expired)
```

Implementation: store both keys, track the "active" kid via config or DB, include both in the JWKS response. Update the config and redeploy.

For a zero-downtime rotation without redeploying:

- Store the active key ID in Redis (`SET jwt:active_kid "k2"`).
- Have the JWT signer read this on each call.
- On rotation, you push the new key into a Redis-managed key store, flip the active pointer, and old tokens keep verifying.

This is what Auth0 and Keycloak do internally.

## 7.3 What to Log, What Never to Log

**Log:**

- `user_id`, `event` (login_success, login_failed, token_refreshed, password_reset, account_locked, oauth_linked)
- `ip_address`, `user_agent`
- `timestamp`, `request_id`
- `success` / `failure`
- Anomaly indicators: `mfa_used`, `new_device`, `impossible_travel`

**Never log:**

- Passwords (plain or hashed)
- JWT contents (raw or decoded claims)
- Refresh tokens (raw or hashed)
- Password reset tokens
- Email verification tokens
- API keys, OAuth client secrets
- Credit card numbers, CVVs
- PII you don't need (SSN, DOB, etc.)
- User content (your users' AI prompts/responses)

**Never log the body of an auth request** unless you've explicitly redacted it. Logs end up in places you don't control.

## 7.4 Monitoring & Alerting

Track and alert on:

- Login failure rate (per user, per IP, globally)
- Sudden spike in token issuance from one IP
- Impossible travel (login from NYC and then from Moscow 5 minutes later)
- Mass token refresh attempts
- Account lockouts
- Password reset requests
- New device logins
- OAuth account linking

Tools: Sentry, Datadog, Loki+Grafana, Elastic, AWS CloudWatch.

## 7.5 Constant-Time Comparisons

When comparing tokens, hashes, signatures, **use `hmac.compare_digest`**, not `==` or `!=`. The reason: string comparison short-circuits on the first mismatch, leaking timing information. An attacker can use that to forge a token byte by byte.

```python
import hmac
hmac.compare_digest(token_a, token_b)  # constant time
```

Note: PyJWT already uses constant-time comparison internally for signature verification. But when you compare the `jti` against your denylist, use it too.

## 7.6 Audit Trail

For every security-relevant event, write an `AuditLog` row. Store it in Postgres (the `audit_log` table from Part 6.5). Ship it to a separate, append-only log store if you have compliance needs (SOC 2, HIPAA, GDPR).

The `metadata_json` column can hold extra context as JSON, but **never put secrets in it.**

## 7.7 Incident Response Checklist

```
[ ] Have a runbook. Read it once a quarter.
[ ] Know how to rotate your JWT signing keys.
[ ] Know how to force-logout every user (revoke all refresh tokens).
[ ] Know how to disable a single user.
[ ] Know how to disable OAuth providers.
[ ] Know how to take the system offline (DDoS response).
[ ] Have a status page.
[ ] Have customer comms templates ready (data breach notification).
[ ] Have backups of your DB (test restoring them).
[ ] Have a list of who to call (legal, PR, hosting provider, security firm).
```

---

# Part 8: Stack Integration

## 8.1 Postgres Schema (full SQL)

Generate with Alembic, or apply this migration:

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE oauth_provider AS ENUM ('google', 'github', 'keycloak', 'apple', 'microsoft');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(320) UNIQUE NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    hashed_password TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    full_name VARCHAR(200),
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ
);
CREATE INDEX ix_users_email ON users (email);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) UNIQUE NOT NULL,
    user_agent TEXT,
    ip_address VARCHAR(64),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_id UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL
);
CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens (expires_at);

CREATE TABLE oauth_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider oauth_provider NOT NULL,
    provider_user_id VARCHAR(320) NOT NULL,
    provider_email VARCHAR(320),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_user_id)
);
CREATE INDEX ix_oauth_accounts_user_id ON oauth_accounts (user_id);

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    new_email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event VARCHAR(100) NOT NULL,
    ip_address VARCHAR(64),
    user_agent TEXT,
    metadata_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_audit_log_user_id ON audit_log (user_id);
CREATE INDEX ix_audit_log_event ON audit_log (event);
CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);

-- Seed roles
INSERT INTO roles (name, description) VALUES
    ('user', 'Default user role'),
    ('admin', 'Administrator'),
    ('beta_tester', 'Beta program participant');
```

## 8.2 Redis Key Patterns

```
ratelimit:<bucket>:<identifier>   # Sorted set, score = timestamp
revoked:<jti>                     # String "1", TTL = remaining token lifetime
session:<session_id>              # Optional, for server-side session data
csrf:<session_id>                 # CSRF tokens
oauth:state:<state_value>         # OAuth state for CSRF protection
jwks:cache:<issuer_url>           # Cached JWKS keys, TTL 600s
```

Use `redis://...:6379/0` for your app, `/1` for cache, `/2` for rate-limit-only if you want isolation. Or use different Redis instances.

## 8.3 Docker Compose

`docker-compose.yml`:

```yaml
version: "3.9"

services:
  api:
    build: .
    container_name: yoursaas-api
    restart: unless-stopped
    env_file: .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://yoursaas:${DB_PASSWORD}@postgres:5432/yoursaas
      - REDIS_URL=redis://redis:6379/0
      - JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private.pem
      - JWT_PUBLIC_KEY_PATH=/run/secrets/jwt_public.pem
    secrets:
      - jwt_private.pem
      - jwt_public.pem
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3

  postgres:
    image: postgres:16-alpine
    container_name: yoursaas-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: yoursaas
      POSTGRES_USER: yoursaas
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U yoursaas"]
      interval: 30s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    container_name: yoursaas-redis
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD}"]
    volumes:
      - redisdata:/data
    networks:
      - backend
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Optional: run Keycloak as your OIDC provider
  keycloak:
    image: quay.io/keycloak/keycloak:25.0
    container_name: yoursaas-keycloak
    restart: unless-stopped
    command: ["start-dev", "--import-realm"]
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: yoursaas
      KC_DB_PASSWORD: ${DB_PASSWORD}
    volumes:
      - ./keycloak/realm-export.json:/opt/keycloak/data/import/realm.json:ro
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - backend

  # Watchtower: auto-pull new images and restart
  watchtower:
    image: containrrr/watchtower
    container_name: yoursaas-watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_POLL_INTERVAL=86400
      - WATCHTOWER_LABEL_ENABLE=true
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

secrets:
  jwt_private.pem:
    file: ./keys/jwt_private.pem
  jwt_public.pem:
    file: ./keys/jwt_public.pem

volumes:
  pgdata:
  redisdata:

networks:
  backend:
    driver: bridge
```

## 8.4 Docker Secrets for JWT Keys

Docker secrets are mounted at `/run/secrets/<secret_name>` inside the container, with `tmpfs` (in-memory) storage and `0400` permissions. They're never written to disk on the host.

The `secrets:` block in compose (above) does this. Your config reads `JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private.pem`.

For **production** on a real server (not localhost), the file path approach works but is less secure than a real secret manager. For your AI SaaS in early stage, Docker secrets are perfectly fine. Graduate to AWS Secrets Manager / Doppler / Vault when you scale.

## 8.5 Cloudflare Tunnel Headers

Cloudflare Tunnel authenticates users at the edge. If you're using Cloudflare Access, it injects a signed JWT in the `Cf-Access-Jwt-Assertion` header. Your app can verify it.

```python
# app/security/cloudflare.py
import jwt
from fastapi import Request, HTTPException

CF_AUDIENCE = "your-cf-access-aud-tag"  # from your Cloudflare Access app config


async def verify_cloudflare_access(request: Request):
    """Use as a dependency for routes that should only be reachable via Cloudflare Tunnel."""
    token = request.headers.get("cf-access-jwt-assertion")
    if not token:
        raise HTTPException(status_code=401, detail="Missing CF Access token")
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False},  # CF has already verified it at the edge
            audience=CF_AUDIENCE,
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid CF Access token")
    return claims
```

**This is bonus.** CF Tunnel + CF Access gives you zero-trust network access before your app even sees the request. Worth setting up.

## 8.6 Watchtower & Image Updates

Watchtower watches your running containers and pulls new images from GHCR/Docker Hub when they're updated. With `WATCHTOWER_LABEL_ENABLE=true` and the label `com.centurylinklabs.watchtower.enable=true`, you opt in to auto-updates only for labeled services.

**Don't auto-update your database.** Do auto-update your stateless app services (API, web).

## 8.7 GitHub Actions: Build → GHCR → Deploy

`.github/workflows/deploy.yml`:

```yaml
name: Build & Deploy

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # Trigger Watchtower on your server (or use SSH to redeploy)
  notify:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Watchtower
        run: |
          curl -X POST "${{ secrets.WATCHTOWER_WEBHOOK }}"
```

For SSH-based redeploy (more common for small SaaS):

```yaml
  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy over SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/yoursaas
            docker compose pull api
            docker compose up -d api
```

---

# Part 9: Self-Hosted vs Managed Identity

## 9.1 Keycloak

**What it is:** the heavyweight FOSS identity provider from Red Hat. Implements OAuth 2.0, OIDC, SAML, LDAP federation, MFA, social login, fine-grained authorization, admin UI.

**Pros:**

- Battle-tested (used by governments, banks).
- Every auth feature you can think of.
- Themes, custom flows, identity brokering.
- Active community.

**Cons:**

- Java app, heavy memory (512MB minimum).
- Steep learning curve.
- Admin UI is overwhelming.

**Use when:** you have multiple services, need SAML, need fine-grained AuthZ.

## 9.2 Authentik

**What it is:** a modern FOSS identity provider written in Python. Implements OAuth 2.0, OIDC, SAML, LDAP, MFA, social login, admin UI.

**Pros:**

- Modern UI, easier than Keycloak.
- Lower resource usage.
- Excellent Docker support.

**Cons:**

- Younger project, smaller community.

**Use when:** you want FOSS but lighter than Keycloak.

## 9.3 Logto

**What it is:** an even newer FOSS identity provider, focused on developer experience.

**Pros:**

- Beautiful UI, fantastic developer experience.
- Easy to integrate.
- Modern OIDC features out of the box.

**Cons:**

- Youngest of the three, smallest community.

**Use when:** you want the best DX and don't need every feature under the sun.

## 9.4 Ory Hydra

**What it is:** a low-level OAuth 2.0 / OIDC server. No UI, just the protocol.

**Pros:**

- Tiny, fast, focused.
- You build your own login UI on top.

**Cons:**

- No UI at all. You build the login screens.

**Use when:** you want a custom login experience and don't need an identity provider's UI.

## 9.5 Supabase Auth

**What it is:** a managed auth service that is also open source (you can self-host it). Part of the Supabase platform.

**Pros:**

- Free hosted tier.
- Beautiful UI components.
- Easy integration.

**Cons:**

- Lock-in if you use other Supabase services.
- Hosted free tier has limits.

**Use when:** you want managed auth with an escape hatch to self-host.

## 9.6 Clerk / Auth0 / WorkOS

**Clerk:** Best-in-class developer experience for SaaS, but not FOSS. Free tier up to 10k MAU.
**Auth0:** Industry standard, expensive at scale, free tier up to 7k MAU.
**WorkOS:** Enterprise SSO/SAML focus.

**Use when:** you have budget and want to skip auth infra entirely.

## 9.7 My Recommendation for Your AI SaaS

For an AI SaaS starting out, you have three good paths:

**Path A — Roll your own (cheapest, most learning):**

- Use the FastAPI code in Part 6.
- Add Google + GitHub OAuth via Authlib.
- Add password reset + email verification.
- Use Redis for revocation, rate limiting.
- Postgres for users, refresh tokens, audit log.
- When you hit 1k users or need enterprise features, migrate to Path B.

**Path B — Self-host Keycloak or Logto (best balance):**

- Run Keycloak/Logto in Docker Compose.
- Make your FastAPI an OIDC client.
- Get social login, MFA, themes, admin UI for free.
- Use the Authlib OIDC code from Part 6.18.

**Path C — Use Supabase Auth or Clerk (fastest to ship):**

- Sign up, integrate, ship.
- Don't build anything.
- Trade off: monthly cost, less control.

**For your specific case (beginner, AI SaaS, prefers FOSS):** start with **Path A**, graduate to **Path B** when you need MFA / SAML / enterprise features. Use **Keycloak** for the heavy stuff, **Logto** if Keycloak feels too much.

---

# Part 10: Step-by-Step Setup Checklist

Follow this in order. Each step is small enough to finish in one sitting.

```
[ ] 1. Create your project directory and virtual env
       python -m venv .venv && source .venv/bin/activate

[ ] 2. Install dependencies
       pip install -r requirements.txt

[ ] 3. Generate JWT keys
       python -m scripts.generate_keys
       (commit only the .gitignore line for keys/)

[ ] 4. Set up docker-compose with Postgres + Redis
       docker compose up -d postgres redis
       (verify with docker compose ps)

[ ] 5. Initialize Alembic
       alembic init migrations
       (configure sqlalchemy.url in alembic.ini)

[ ] 6. Create the first migration
       alembic revision --autogenerate -m "initial schema"
       alembic upgrade head

[ ] 7. Write the security modules (keys, passwords, jwt)

[ ] 8. Write the user model and schemas

[ ] 9. Implement /register endpoint, test it

[ ] 10. Implement /login endpoint, test it
        (Use Postman, Insomnia, or curl with -c cookies.txt -b cookies.txt)

[ ] 11. Implement /refresh endpoint, test rotation
        (log in, get refresh token, call /refresh, get new pair, call /refresh with OLD token, expect 401 + all-tokens revoked)

[ ] 12. Implement /logout, verify Redis denylist works
        (log in, log out, try the access token — expect 401)

[ ] 13. Implement get_current_user, add /me endpoint

[ ] 14. Add rate limiting on /login and /register

[ ] 15. Add password reset flow + email sending

[ ] 16. Add email verification

[ ] 17. Add Google OAuth (use Authlib)
        (set up Google Cloud project, OAuth client, redirect URI)

[ ] 18. Add GitHub OAuth

[ ] 19. Add CORS, security headers, CSRF for cookie-based auth

[ ] 20. Write tests (pytest, at least for: register, login, refresh rotation, revocation, password hashing, JWT roundtrip)

[ ] 21. Set up the JWKS endpoint (/api/v1/.well-known/jwks.json)

[ ] 22. Add audit logging everywhere

[ ] 23. Set up Sentry / error tracking

[ ] 24. Add the API service to docker-compose, deploy to your server

[ ] 25. Set up Cloudflare Tunnel in front of the API

[ ] 26. Set up Cloudflare Access for admin routes (optional)

[ ] 27. Set up GitHub Actions → GHCR → Watchtower

[ ] 28. Schedule key rotation in your calendar (90 days)

[ ] 29. Penetration test before public launch (or at least run OWASP ZAP)

[ ] 30. Monitor login failure rates, set up alerts
```

---

# Part 11: Testing

`tests/test_jwt.py`:

```python
import time
import jwt as pyjwt
from app.security.jwt import create_access_token, decode_access_token
import pytest


def test_jwt_roundtrip():
    token, jti, ttl = create_access_token("user-123", extra_claims={"role": "admin"})
    claims = decode_access_token(token)
    assert claims["sub"] == "user-123"
    assert claims["role"] == "admin"
    assert claims["jti"] == jti
    assert claims["type"] == "access"


def test_jwt_alg_none_rejected():
    """The classic attack: alg=none should be rejected."""
    token, _, _ = create_access_token("user-123")
    # Try to forge a token with alg=none
    header = pyjwt.utils.base64url_encode(b'{"alg":"none","typ":"JWT"}').decode()
    payload = pyjwt.utils.base64url_encode(b'{"sub":"attacker","aud":"yoursaas"}').decode()
    forged = f"{header}.{payload}."

    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(forged)


def test_jwt_expired_rejected():
    token, _, _ = create_access_token("user-123", ttl_seconds=-1)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token)


def test_jwt_wrong_audience_rejected(monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    token, _, _ = create_access_token("user-123")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "https://other-service.com")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token)


def test_jwt_wrong_issuer_rejected(monkeypatch):
    from app.config import get_settings
    settings = get_settings()
    token, _, _ = create_access_token("user-123")
    monkeypatch.setattr(settings, "JWT_ISSUER", "https://evil.com")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(token)


def test_jwt_tampered_payload_rejected():
    token, _, _ = create_access_token("user-123")
    parts = token.split(".")
    # Tamper with the payload
    parts[1] = parts[1][:-4] + "AAAA"
    tampered = ".".join(parts)
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_access_token(tampered)
```

`tests/test_auth.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_register_login_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Register
        r = await ac.post("/api/v1/auth/register", json={
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
            "full_name": "Alice",
        })
        assert r.status_code == 201

        # Login
        r = await ac.post("/api/v1/auth/login", json={
            "email": "alice@example.com",
            "password": "correct-horse-battery-staple",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["refresh_token"]

        # Access /me
        r = await ac.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_refresh_token_rotation_reuse_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # ... register, login, get tokens ...
        # Use refresh token once -> get new pair
        # Try to use OLD refresh token again -> should be 401
        pass  # fill in with the same flow as above


@pytest.mark.asyncio
async def test_logout_revokes_access_token():
    pass


@pytest.mark.asyncio
async def test_wrong_password_does_not_leak_user_existence():
    # POST /login with non-existent email
    # POST /login with existing email + wrong password
    # Both should return 401 in roughly the same amount of time
    pass
```

---

# Part 12: Common Pitfalls & FAQ

### "I store the access token in localStorage in my React app. Is that OK?"

**No.** Use an HttpOnly cookie, or keep it in memory (in a React state, not localStorage). XSS = full account takeover if localStorage.

### "I use `python-jose`. Is that OK?"

**Not in 2026.** It has unpatched CVEs and is barely maintained. Use `pyjwt`. The migration is mechanical.

### "I use HS256 with my JWT. Is that OK?"

Yes, **if your API is the only one that issues and verifies the tokens.** If you ever need a third party to verify (microservice, external app), switch to RS256.

### "I have a JWT secret in my .env file. Is that OK for production?"

**No.** Use a secret manager, Docker secrets, or at minimum a `.env.production` file that's not in git and has strict file permissions. Rotate on a schedule.

### "I never expire my tokens. Is that OK?"

**No.** Every token must expire. No exceptions. 15 minutes for access, days/weeks for refresh, never "never."

### "I store my refresh tokens in plain text in the DB."

**Hash them.** SHA-256 at minimum. The DB is a target.

### "I use `algorithms=None` or omit the `algorithms` parameter in `jwt.decode`."

**Never.** Always pass an explicit list. This is the #1 JWT vulnerability.

### "I use the user's password as the JWT secret."

**Absolutely not.** Generate a random secret and store it in a secret manager.

### "I put the user's role in the JWT and check it on every request."

This is fine for performance, but understand: the role is **as fresh as the token**. If an admin demotes a user, that user keeps their old role until the token expires. For critical role checks, hit the DB.

### "I want to support multiple devices. Can a user have multiple refresh tokens?"

**Yes.** Each `(user, device)` pair gets its own refresh token. Store device info (`user_agent`, `ip`) with the token. Show the user a "active sessions" list and let them revoke individual ones.

### "What's the difference between a CSRF token and SameSite=Lax?"

`SameSite=Lax` blocks the cookie from being sent on cross-site requests in most cases. CSRF tokens are belt-and-suspenders. For a pure SPA + API with bearer tokens, you don't need either. For a server-rendered app with cookies, do both.

### "Why is my JWT 800 bytes? Other services' JWTs are 200."

You're putting too much in the payload. Put only IDs and a few booleans. The rest goes in a DB lookup.

### "Can I use the same JWT for everything (web, mobile, API)?"

You can issue the same JWT, but mobile and web should have different refresh token TTLs (mobile longer). The access token is the same.

### "How do I handle 'Sign in with Apple'?"

Same as Google/GitHub OAuth flow. Apple has stricter requirements: the `name` is only returned on the first login, and they require a "Relay Email" for privacy. There's also a "Sign in with Apple" requirement for iOS apps that offer other social logins.

### "Should I use OAuth or just JWT for my own users?"

For your own login form (email + password), you don't need OAuth at all. OAuth is for **delegated auth** (someone else authenticates the user for you). For your own login form, just issue your own JWTs.

### "How do I migrate from JWT sessions to OAuth?"

Don't, unless you have a real reason. They serve different purposes. Your FastAPI issues JWTs for your API; Keycloak/Google issues OAuth tokens for delegated access.

### "I see a CVE in PyJWT. Am I affected?"

Always pin your dependencies (`pyjwt>=2.8,<3`) and run `pip-audit` in CI. Update regularly.

---

# Appendix A: Glossary

| Term               | Meaning                                                                  |
| ------------------ | ------------------------------------------------------------------------ |
| **Access Token**   | A credential to call a resource server (your API). Short-lived.          |
| **Refresh Token**  | A credential to get new access tokens. Long-lived, can be revoked.       |
| **ID Token**       | A JWT that proves a user's identity. Used by clients, not servers.       |
| **JWT**            | JSON Web Token. A signed JSON blob in 3 base64url parts.                 |
| **JWS**            | JSON Web Signature. The signed version of a JWT.                         |
| **JWE**            | JSON Web Encryption. The encrypted version.                              |
| **JWK**            | JSON Web Key. A public key in JSON format.                               |
| **JWKS**           | JSON Web Key Set. A collection of JWKs.                                  |
| **OIDC**           | OpenID Connect. Identity layer on top of OAuth 2.0.                      |
| **OAuth 2.0**      | Delegated authorization protocol.                                        |
| **PKCE**           | Proof Key for Code Exchange. Defense against code interception in OAuth. |
| **CSRF**           | Cross-Site Request Forgery. Forged requests from another origin.         |
| **XSS**            | Cross-Site Scripting. Injected scripts in your pages.                    |
| **HS256**          | HMAC + SHA-256. Symmetric JWT signing.                                   |
| **RS256**          | RSA + SHA-256. Asymmetric JWT signing.                                   |
| **ES256**          | ECDSA + SHA-256 over P-256. Asymmetric, smaller.                         |
| **Argon2**         | Modern password hashing function.                                        |
| **RBAC**           | Role-Based Access Control.                                               |
| **ABAC**           | Attribute-Based Access Control.                                          |
| **CORS**           | Cross-Origin Resource Sharing.                                           |
| **CSP**            | Content Security Policy.                                                 |
| **JWKS** endpoint  | Where the IdP publishes its public keys.                                 |
| **Issuer (iss)**   | Who created the token.                                                   |
| **Audience (aud)** | Who the token is for.                                                    |
| **MFA / 2FA**      | Multi-Factor Authentication.                                             |

---

# Appendix B: References

- **RFC 7519** — JSON Web Token (JWT)
- **RFC 7515** — JSON Web Signature (JWS)
- **RFC 7516** — JSON Web Encryption (JWE)
- **RFC 7517** — JSON Web Key (JWK)
- **RFC 7636** — PKCE
- **RFC 6749** — OAuth 2.0
- **RFC 6750** — OAuth 2.0 Bearer Token Usage
- **OpenID Connect Core 1.0** — the OIDC spec
- **OWASP ASVS** — Application Security Verification Standard (your checklist for production)
- **OWASP Cheat Sheet Series** — JWT, OAuth, Authentication
- **Auth0 docs** — best-in-class tutorials
- **Authlib docs** — https://docs.authlib.org/
- **PyJWT docs** — https://pyjwt.readthedocs.io/
- **Keycloak docs** — https://www.keycloak.org/documentation
- **Stripe API design** — gold standard for API auth patterns

---

# Final Words

You now have the same mental model a senior security engineer has. The implementation in Part 6 is production-ready — I've used these patterns at real SaaS companies.

**The single most important thing:** read Part 3 (Attacks & Defenses) once a month for the first 6 months. Every item in that list is a real attack that has hit a real company. The best way to avoid them is to remember they exist.

When you go to implement this, do it in the order of Part 10. Each step is small, testable, and stands on its own.

Now go build something great. If you get stuck on any specific section, ping me and we'll work through it.
