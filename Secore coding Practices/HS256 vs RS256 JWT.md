Short answer: **HS256 is safe when used correctly.** You do **not** have to use RS256 just because it is considered "more enterprise". The right choice depends on your architecture.

## HS256 vs RS256

| Feature             | HS256                                           | RS256                                                       |
| ------------------- | ----------------------------------------------- | ----------------------------------------------------------- |
| Algorithm           | HMAC SHA-256                                    | RSA SHA-256                                                 |
| Keys                | One shared secret                               | Public/private key pair                                     |
| Performance         | Faster                                          | Slower                                                      |
| Complexity          | Simple                                          | More complex                                                |
| Secret distribution | Every service verifying tokens needs the secret | Only issuer has private key; verifiers only need public key |
| Good for            | Single backend, monolith, small APIs            | Microservices, third-party verification, SSO                |

---

# When HS256 is the better choice

Use **HS256** if:

* You have one FastAPI backend.
* Your backend both creates and verifies JWTs.
* No third-party service needs to verify your tokens.
* The secret is stored securely (environment variable, Vault, Docker secret, etc.).

This describes **most FastAPI applications**.

Example:

```python
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
```

This is completely secure provided that:

* Your secret is long (at least 32 random bytes, ideally 64 bytes).
* You never hardcode it in Git.
* You use HTTPS.
* You validate expiration, issuer, audience (when applicable), and signature.

---

# When RS256 is better

Use **RS256** when:

* Multiple services verify the token.
* You expose a public API.
* You use OAuth2/OpenID Connect.
* You use an identity provider such as:

  * Auth0
  * Keycloak
  * Authentik
  * AWS Cognito
  * Azure AD
  * Google Identity

In this model:

```
Private Key
     │
     ▼
 Sign JWT
     │
     ▼
JWT
     │
     ▼
Many APIs verify using Public Key
```

The private key never leaves the authentication server.

---

# Why many people recommend RS256

Suppose you have:

```
API Gateway
Backend A
Backend B
Backend C
```

With **HS256**:

Every service must know:

```
SECRET_KEY
```

If Backend B is compromised, an attacker can create valid JWTs.

With **RS256**:

Only the authentication server has:

```
Private Key
```

Every backend only has:

```
Public Key
```

If Backend B is compromised, it still cannot forge new tokens because it lacks the private key.

---

# Is HS256 considered insecure?

No.

HS256 is still widely used and considered cryptographically secure.

The common problems are not the algorithm itself but poor implementation, such as:

* Weak secrets (e.g. `"password"` or `"secret"`).
* Secrets committed to Git.
* Missing token expiration.
* Failure to verify the algorithm properly.
* Accepting `alg=none` (a historical vulnerability in some JWT libraries; modern libraries generally prevent this when configured correctly).

---

# For your planned architecture

From our previous discussions, you're building:

* FastAPI
* React
* PostgreSQL
* Traefik
* Cloudflare Tunnel
* Docker
* Authentik/Keycloak planned for future authentication

For that setup, I would recommend:

### Phase 1 (building yourself)

Use:

```python
JWT_ALGORITHM = "HS256"
```

with a strong random secret stored securely. It's simpler, faster, and entirely appropriate for a single FastAPI service.

### Phase 2 (when adding Authentik or Keycloak)

Switch to **RS256**, because those identity providers issue JWTs signed with a private key, and your FastAPI service verifies them using the public key.

---

## Recommendation

For your current FastAPI application:

```python
jwt_algorithm = "HS256"
```

is a solid, secure choice.

Move to **RS256** when you introduce a dedicated identity provider, multiple independently deployed services, or a need for third parties to verify your JWTs.
