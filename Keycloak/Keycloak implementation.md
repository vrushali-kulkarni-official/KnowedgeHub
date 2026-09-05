Yes. Since you already understand the OAuth2/OIDC/JWT theory, the best way to learn Keycloak is to treat it like a real identity platform and build a small **Keycloak + FastAPI laboratory** from scratch.

We will use the current Keycloak 26.7.x behavior and a deliberately small architecture that we will harden progressively. Keycloak's current documentation is version 26.7.x, and its recommended integration approach is to use the OIDC support of your application/framework rather than depending on old Keycloak-specific adapters. ([keycloak.org][1])

By the end you will have done all of this yourself:

```text
                         ┌──────────────────────┐
                         │      Keycloak        │
                         │   localhost:8080     │
                         │                      │
                         │   Realm: fastapi-lab │
                         └──────────┬───────────┘
                                    │
             ┌──────────────────────┼────────────────────┐
             │                      │                    │
             ▼                      ▼                    ▼
      Postman OAuth2         FastAPI API          Service Client
      Authorization Code     Resource Server      Client Credentials
      + PKCE                  localhost:8000       machine-to-machine
             │                      │                    │
             └────────────── JWT access token ───────────┘
                                    │
                                    ▼
                           Role / audience checks
```

We will deliberately start with a loose development configuration, verify that everything works, and then tighten security one layer at a time.

---

# Part 0 — Your lab

You already have:

```text
Keycloak
http://localhost:8080
```

We will run FastAPI on:

```text
http://localhost:8000
```

Use these names consistently throughout the tutorial.

| Thing               | Value                   |
| ------------------- | ----------------------- |
| Keycloak            | `http://localhost:8080` |
| Realm               | `fastapi-lab`           |
| API client/resource | `fastapi-api`           |
| Postman client      | `postman-public`        |
| Service client      | `fastapi-service`       |
| FastAPI             | `http://localhost:8000` |

One very important distinction:

```text
Realm
   ↓
Clients
   ↓
Users
   ↓
Roles
   ↓
Client Scopes
   ↓
Authentication flows
   ↓
Tokens
```

You should become comfortable navigating through each of those.

---

# Part 1 — First, verify your Keycloak installation

Open:

```text
http://localhost:8080
```

Log into the **Admin Console**.

For a Docker development installation, current Keycloak documentation uses the `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD` mechanism for the initial administrator. Development mode is explicitly intended for development/testing and should not be used as-is in production. ([Keycloak][2])

From your terminal:

```bash
docker ps
```

You should see something similar to:

```text
quay.io/keycloak/keycloak:...
```

Now test OIDC discovery.

Open:

```text
http://localhost:8080/realms/master/.well-known/openid-configuration
```

You should receive JSON containing things such as:

```json
{
  "issuer": "...",
  "authorization_endpoint": "...",
  "token_endpoint": "...",
  "userinfo_endpoint": "...",
  "jwks_uri": "...",
  ...
}
```

This endpoint is extremely important.

Instead of your Python program memorizing every Keycloak URL, it can discover the authorization endpoint, token endpoint, JWKS endpoint, issuer, etc. from:

```text
/.well-known/openid-configuration
```

Keycloak documents this as the OpenID Provider configuration endpoint. ([Keycloak][3])

---

# Part 2 — Create your first realm

Do **not** use the `master` realm for your application.

The `master` realm is primarily the management realm for Keycloak itself.

Create a dedicated realm.

In the Admin Console:

```text
top-left realm selector
        ↓
Create realm
```

Enter:

```text
Realm name:
fastapi-lab
```

Create it.

You should now see:

```text
fastapi-lab
```

selected in the realm dropdown.

Now test:

```text
http://localhost:8080/realms/fastapi-lab/.well-known/openid-configuration
```

It should return metadata.

Congratulations: you now have your application's identity domain.

---

# Part 3 — Understand the Admin Console by actually exploring it

Before touching FastAPI, spend a few minutes clicking through these sections:

```text
Realm settings
Clients
Client scopes
Realm roles
Users
Groups
Authentication
Identity providers
User federation
Sessions
Events
```

We will eventually use almost all of them.

The important mental model is:

```text
Realm
 ├── Users
 ├── Groups
 ├── Realm Roles
 ├── Clients
 │    ├── Client Roles
 │    └── Client Scopes
 ├── Authentication Flows
 └── Realm-level security policies
```

Do not think:

> "Keycloak is my JWT generator."

Think:

> "Keycloak manages identities, authentication, authorization metadata, OAuth/OIDC clients, sessions and ultimately issues tokens representing those decisions."

---

# Part 4 — Create your first user

Go to:

```text
Users
→ Create user
```

Create:

```text
Username:
alice
```

You can set:

```text
Email:
alice@example.com

First name:
Alice

Last name:
Example
```

Create the user.

Now:

```text
Users
→ alice
→ Credentials
→ Set password
```

Use something like:

```text
LabPassword123











!
```

For this laboratory only.

Make sure:

```text
Temporary = OFF
```

Otherwise Keycloak will force a password change on first login.

---

# Part 5 — Create your API client

Now we create something extremely important.

Go to:

```text
Clients
→ Create client
```

Enter:

```text
Client type:
OpenID Connect

Client ID:
fastapi-api
```

Continue.

For this client:

```text
Client authentication:
OFF
```

Why?

Because this client is going to represent the **API/resource server**, not a confidential application that needs to authenticate to Keycloak.

The API itself receives bearer access tokens.

So we don't need:

```text
client_secret
```

for FastAPI to validate JWTs.

Save it.

---

# Part 6 — Create API roles

Now:

```text
Clients
→ fastapi-api
→ Roles
→ Create role
```

Create:

```text
user
```

Then:

```text
admin
```

Then:

```text
writer
```

You now have:

```text
fastapi-api
     │
     ├── user
     ├── writer
     └── admin
```

These are **client roles**, not realm roles.

For our application this is useful because the permissions belong to this API.

For example:

```text
fastapi-api:user
fastapi-api:writer
fastapi-api:admin
```

---

# Part 7 — Assign Alice a role

Go to:

```text
Users
→ alice
→ Role mapping
```

Find:

```text
Client roles
→ fastapi-api
```

Assign:

```text
user
```

Do not assign `admin` yet.

Alice is now:

```text
alice
   ↓
fastapi-api:user
```

---

# Part 8 — Create a second user

Create:

```text
bob
```

Set his password.

Assign:

```text
fastapi-api:user
fastapi-api:writer
```

Then create:

```text
admin
```

Assign:

```text
fastapi-api:user
fastapi-api:admin
```

We now have:

```text
alice
 └── user

bob
 ├── user
 └── writer

admin
 ├── user
 └── admin
```

This will let us test authorization properly later.

---

# Part 9 — Create an audience for your API

This is one of the most important practical Keycloak steps.

We want tokens intended for:

```text
fastapi-api
```

to contain:

```json
"aud": "fastapi-api"
```

Don't just validate:

```text
signature
```

Validate:

```text
issuer
audience
expiration
algorithm
```

as well.

We'll create a client scope.

Go to:

```text
Client scopes
→ Create client scope
```

Enter:

```text
Name:
fastapi-api-scope

Protocol:
OpenID Connect
```

Save.

Now go to:

```text
fastapi-api-scope
→ Mappers
→ Configure a new mapper
```

Select:

```text
Audience
```

Configure:

```text
Name:
fastapi-api-audience

Included Client Audience:
fastapi-api

Add to access token:
ON
```

Save.

Now we want this scope available to our Postman client later.

---

# Part 10 — Create the Postman client

Go to:

```text
Clients
→ Create client
```

Create:

```text
Client ID:
postman-public
```

Protocol:

```text
OpenID Connect
```

For this client:

```text
Client authentication:
OFF

Authorization:
OFF

Standard flow:
ON


Direct access grants:
OFF

Implicit flow:
OFF

Service accounts:
OFF
```

We deliberately disable the things we don't need.

For a browser/public-client-style flow, a client secret cannot safely be hidden in the client. Keycloak's current administration documentation similarly emphasizes careful redirect-URI configuration for public clients. ([Keycloak][4])

---

# Part 11 — Configure Postman redirect URI

Postman currently documents this callback as:

```text
https://oauth.pstmn.io/v1/browser-callback
```

when using browser-based authorization. ([Postman Docs][5])

In:

```text
postman-public
→ Settings
```

set:

```text
Valid redirect URIs:

https://oauth.pstmn.io/v1/browser-callback
```

Keep the URI **exact**.

Do not do:

```text
*
```

Do not do:

```text
https://oauth.pstmn.io/*
```

Do not do:

```text
http://localhost/*
```

unless you intentionally need it.

Redirect URI mistakes are one of the first Keycloak configuration problems people encounter.

---

# Part 12 — Make PKCE mandatory

Still inside:

```text
postman-public
```

Look for the OpenID Connect / advanced configuration containing:

```text
PKCE method
```

Set:

```text
S256
```

Keycloak supports making S256 mandatory for the client. ([Keycloak][4])

Do not choose:

```text
plain
```

for this exercise.

Why?

Because our desired flow is:

```text
Authorization Code
+
PKCE S256
```

Postman's own current documentation recommends Authorization Code + PKCE when using browser-based OAuth authorization because it protects against authorization-code interception. ([Postman Docs][5])

---

# Part 13 — Attach the API scope to Postman

Go to:

```text
Clients
→ postman-public
→ Client scopes
```

Add:

```text
fastapi-api-scope
```

as:

```text
Default
```

Now the token requested by Postman will receive the mapper from that scope.

---

# Part 14 — Your first OIDC login through Postman

Open Postman.

Create:

```text
GET http://localhost:8000/me
```

We haven't implemented FastAPI yet, so this will fail.

That's okay.

Go to:

```text
Authorization
```

Select:

```text
OAuth 2.0
```

Create a new token.

Use:

```text
Token Name:
keycloak-alice
```

Grant type:

```text
Authorization Code (With PKCE)
```

Callback URL:

```text
https://oauth.pstmn.io/v1/browser-callback
```

Auth URL:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/auth
```

Access Token URL:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/token
```

Client ID:

```text
postman-public
```

Client Secret:

```text
leave empty
```

Scope:

```text
openid profile email
```

Then select:

```text
Authorize using browser
```

Click:

```text
Get New Access Token
```

A browser window should open.

Keycloak login:

```text
Username:
alice

Password:
LabPassword123!
```

After successful authentication, Keycloak redirects the browser to Postman.

Postman exchanges the authorization code for tokens.

Postman documents this complete flow, including browser authorization and PKCE configuration. ([Postman Docs][5])

---

# Part 15 — Inspect the token

Postman should show the returned token.

Copy the **access token**.

It will look like:

```text
eyJhbGciOiJSUzI1NiIs...
```

Now decode it with a JWT decoder such as jwt.io purely for learning.

Do **not** put production credentials/tokens into third-party websites.

Look at the payload.

You'll see claims such as:

```json
{
  "exp": ...,
  "iat": ...,
  "iss": "http://localhost:8080/realms/fastapi-lab",
  "sub": "...",
  "aud": "...",
  "azp": "postman-public",
  ...
}
```

Eventually we want something resembling:

```json
"aud": [
  "fastapi-api"
]
```

and:

```json
"resource_access": {
  "fastapi-api": {
    "roles": [
      "user"
    ]
  }
}
```

That is where the practical distinction becomes very important:

```text
iss
    Who issued the token?

sub
    Which user?

aud
    Which API is the token meant for?

azp
    Which client initiated the token request?

realm_access
    Realm roles

resource_access
    Client roles
```

---

# Part 16 — Now build FastAPI

We have reached the Python portion.

Create a project:

```bash
mkdir keycloak-fastapi-lab
cd keycloak-fastapi-lab
```

If using `uv`:

```bash
uv init
```

Install:

```bash
uv add fastapi uvicorn pyjwt[crypto] httpx pydantic-settings
```

FastAPI's current security documentation uses standard OAuth2/JWT mechanisms, and PyJWT is suitable for JWT encoding/verification; FastAPI specifically recommends `pyjwt[crypto]` when using RSA/ECDSA algorithms. ([FastAPI][6])

Create:

```text
app/
    __init__.py
    main.py
    config.py
    security.py
```

---

# Part 17 — Configuration

Create:

```text
app/config.py
```

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "fastapi-lab"
    keycloak_client_id: str = "fastapi-api"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def issuer(self) -> str:
        return (
            f"{self.keycloak_url}/realms/"
            f"{self.keycloak_realm}"
        )

    @property
    def jwks_url(self) -> str:
        return (
            f"{self.issuer}/protocol/openid-connect/certs"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `.env`:

```dotenv
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=fastapi-lab
KEYCLOAK_CLIENT_ID=fastapi-api
```

Add to `.gitignore`:

```gitignore
.env
```

There are no secrets in this `.env` yet, but get into the habit of keeping deployment configuration outside source code.

---

# # Part 18 — Implement JWT validation

Create:

```text
app/security.py
```

```python
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import get_settings


bearer_scheme = HTTPBearer(auto_error=True)


class KeycloakSecurity:
    def __init__(self) -> None:
        settings = get_settings()

        self.issuer = settings.issuer
        self.audience = settings.keycloak_client_id
        self.jwks_url = settings.jwks_url

        self.jwks_client = PyJWKClient(self.jwks_url)

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(
                token
            )

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "sub",
                    ]
                },
            )

            return payload

        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            ) from exc

        except jwt.InvalidAudienceError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
            ) from exc

        except jwt.InvalidIssuerError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
            ) from exc

        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from exc


keycloak_security = KeycloakSecurity()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
) -> dict[str, Any]:
    return keycloak_security.decode_token(
        credentials.credentials
    )
```

This is an important piece of code.

FastAPI receives:

```http
Authorization: Bearer <JWT>
```

then:

```text
FastAPI
   ↓
extract JWT
   ↓
read kid
   ↓
download/select Keycloak public key
   ↓
verify RSA signature
   ↓
verify expiration
   ↓
verify issuer
   ↓
verify audience
   ↓
accept token
```

The token is **not** accepted merely because it is a JWT.

---

# Part 19 — Why JWKS is used

Your Keycloak token header contains something resembling:

```json
{
  "alg": "RS256",
  "kid": "some-key-id"
}
```

FastAPI calls:

```text
/realms/fastapi-lab/protocol/openid-connect/certs
```

Keycloak exposes its public signing keys through this OIDC JWKS endpoint.

Your application uses the:

```text
kid
```

to select the correct public key.

This is extremely important during key rotation.

You do **not** hard-code Keycloak's current public key into your application.

---

# Part 20 — Create FastAPI routes

Create:

```text
app/main.py
```

```python
from typing import Any

from fastapi import Depends, FastAPI

from .security import get_current_user


app = FastAPI(
    title="Keycloak FastAPI Lab",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/public")
async def public() -> dict[str, str]:
    return {
        "message": "Anyone can access this"
    }


@app.get("/me")
async def me(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "subject": user.get("sub"),
        "username": user.get("preferred_username"),
        "email": user.get("email"),
        "roles": user.get("resource_access", {}),
    }
```

Run it:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Test:

```text
http://localhost:8000/health
```

You should receive:

```json
{
  "status": "ok"
}
```

Test:

```text
http://localhost:8000/public
```

You should receive:

```json
{
  "message": "Anyone can access this"
}
```

Now:

```text
http://localhost:8000/me
```

will return:

```text
401
```

because no bearer token was provided.

That's exactly what we want.

---

# Part 21 — Give Postman the token

Return to your Postman request:

```text
GET http://localhost:8000/me
```

Authorization:

```text
OAuth 2.0
```

Choose your previously generated token.

Click:

```text
Use Token
```

Postman should send:

```http
Authorization: Bearer eyJ...
```

Send the request.

You should now receive something resembling:

```json
{
  "subject": "....",
  "username": "alice",
  "email": "alice@example.com",
  "roles": {
    "fastapi-api": {
      "roles": [
        "user"
      ]
    }
  }
}
```

You have now completed the fundamental integration:

```text
Postman
   ↓
Keycloak login
   ↓
Authorization Code
   ↓
PKCE
   ↓
Access Token
   ↓
FastAPI
   ↓
JWKS
   ↓
RSA signature verification
   ↓
Issuer verification
   ↓
Audience verification
   ↓
Authorization
```

This is the first milestone.

---

# Part 22 — Add role authorization in FastAPI

Authentication answers:

> Who are you?

Authorization answers:

> Are you allowed to do this?

Create a role dependency.

Modify `security.py`:

```python
from typing import Any

from fastapi import Depends, HTTPException, status


def require_role(required_role: str):
    async def dependency(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:

        resource_access = user.get(
            "resource_access",
            {},
        )

        api_access = resource_access.get(
            get_settings().keycloak_client_id,
            {},
        )

        roles = api_access.get(
            "roles",
            [],
        )

        if required_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return dependency
```

Then:

```python
from fastapi import Depends


@app.get("/user")
async def user_endpoint(
    user: dict[str, Any] = Depends(
        require_role("user")
    ),
):
    return {
        "message": "You have the user role"
    }


@app.get("/writer")
async def writer_endpoint(
    user: dict[str, Any] = Depends(
        require_role("writer")
    ),
):
    return {
        "message": "You have the writer role"
    }


@app.get("/admin")
async def admin_endpoint(
    user: dict[str, Any] = Depends(
        require_role("admin")
    ),
):
    return {
        "message": "You have the admin role"
    }
```

Now test with Alice.

```text
GET /user
```

→ `200`

```text
GET /writer
```

→ `403`

```text
GET /admin
```

→ `403`

Now authenticate as Bob.

Bob should get:

```text
/user   → 200
/writer → 200
/admin  → 403
```

Admin:

```text
/user   → 200
/writer → 403
/admin  → 200
```

You have now implemented RBAC end-to-end.

---

# Part 23 — Turn off Full Scope Allowed

Now we start hardening Keycloak.

Go to:

```text
Clients
→ postman-public
→ Client scopes
```

Find the dedicated scope / scope configuration.

Keycloak's current administration guide recommends restricting role scope mappings rather than leaving `Full Scope Allowed` enabled in production. ([Keycloak][7])

The security principle is:

```text
Don't allow:

client
   ↓
all user permissions
```

Instead:

```text
postman-public
      ↓
fastapi-api-scope
      ↓
fastapi-api roles
```

Only permissions relevant to this API should enter the access token.

This becomes increasingly important in a larger SaaS with:

```text
frontend
API gateway
chat API
admin API
billing API
document API
agent API
MCP API
```

You don't want every token carrying every permission.

---

# Part 24 — Understand `aud` properly

Try intentionally breaking your audience.

Temporarily remove:

```text
fastapi-api-audience
```

from the client scope.

Generate a new access token.

Decode it.

Your FastAPI validator expects:

```text
aud = fastapi-api
```

The new token may no longer satisfy that.

Your request should become:

```text
401 Invalid token audience
```

This is a very valuable test.

You just proved that an attacker cannot simply bring you a legitimate Keycloak token issued for some unrelated client and have your API accept it.

---

# Part 25 — Create a machine-to-machine client

Now we move into a completely different authentication scenario.

A user isn't involved.

Imagine:

```text
AI Worker → FastAPI
```

The AI worker needs access to your API.

Create:

```text
Clients
→ Create client
```

Use:

```text
Client ID:
fastapi-service
```

OpenID Connect.

 Set:

```text
Client authentication:
ON

Service account roles:
ON

Standard flow:
OFF

Direct access grants:
OFF

Implicit flow:
OFF
```

Save.

Keycloak now generates a client credential.

Go to:

```text
Credentials
```

You'll see:

```text
Client secret
```

Treat this as an actual secret.

---

# Part 26 — Assign service account permissions

Go to:

```text
Service Account Roles
```

Assign only the roles that this machine actually needs.

For example:

```text
fastapi-api
    writer
```

Do not give it:

```text
admin
```

unless absolutely necessary.

The principle is:

```text
service account
    ↓
minimum roles
```

Keycloak's current documentation describes service accounts as the client-credentials mechanism and recommends carefully limiting the roles available to the service account. ([Keycloak][7])

---

# Part 27 — Test Client Credentials manually

Use curl.

```bash
curl -X POST \
  "http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=fastapi-service" \
  -d "client_secret=YOUR_SECRET"
```

You should receive:

```json
{
  "access_token": "...",
  "expires_in": ...,
  "token_type": "Bearer",
  ...
}
```

Keycloak's token endpoint for service accounts is:

```text
/realms/{realm}/protocol/openid-connect/token
```

with:

```text
grant_type=client_credentials
```

and the client credentials. ([Keycloak][7])

Now copy the access token.

```bash
curl \
  http://localhost:8000/writer \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

This should succeed if the service account has the required role.

You've now implemented:

```text
machine → machine
```

as well as:

```text
user → API
```

---

# Part 28 — Make FastAPI itself obtain a Keycloak token

Now let's do the reverse direction.

Suppose FastAPI needs to call another protected service.

We can create:

```python
import httpx

from .config import get_settings


async def get_service_token() -> str:
    settings = get_settings()

    token_url = (
        f"{settings.issuer}"
        "/protocol/openid-connect/token"
    )

    payload = {
        "grant_type": "client_credentials",
        "client_id": "fastapi-service",
        "client_secret": "YOUR_SECRET",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data=payload,
            timeout=10,
        )

    response.raise_for_status()

    return response.json()["access_token"]
```

But **do not** actually put:

```text
YOUR_SECRET
```

inside source code.

We'll fix that immediately.

---

# Part 29 — Put secrets in configuration

Update `.env`:

```dotenv
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=fastapi-lab
KEYCLOAK_CLIENT_ID=fastapi-api

KEYCLOAK_SERVICE_CLIENT_ID=fastapi-service
KEYCLOAK_SERVICE_CLIENT_SECRET=...
```

Update:

```python
class Settings(BaseSettings):
    ...

    keycloak_service_client_id: str
    keycloak_service_client_secret: str
```

Use:

```python
from pydantic import SecretStr
```

and:

```python
keycloak_service_client_secret: SecretStr
```

Then:

```python
settings.keycloak_service_client_secret.get_secret_value()
```

This is the pattern you should use when integrating Keycloak into your real application.

---

# Part 30 — Learn the difference between authentication and authorization in your actual code

Your FastAPI stack now looks like:

```text
HTTP Request
     │
     ▼
Authorization Header
     │
     ▼
Bearer JWT
     │
     ▼
Cryptographic validation
     │
     ├── signature
     ├── exp
     ├── issuer
     └── audience
     │
     ▼
Authenticated Principal
     │
     ▼
Role / permission check
     │
     ▼
Business endpoint
```

Never mix all of these into one enormous function.

A production architecture should resemble:

```text
security.py
    ↓
identity extraction
    ↓
authorization.py
    ↓
permissions
    ↓
routers
    ↓
services
    ↓
repositories
```

This is especially important for your larger FastAPI AI SaaS architecture.

---

# Part 31 — Password security

Go to:

```text
Authentication
→ Policies
```

Keycloak currently supports password policies including things like:

```text
length
digits
lowercase
uppercase
special characters
not username
not email
password history
expiration
```

and uses Argon2 as the default password hashing algorithm in non-FIPS deployments. ([Keycloak][7])

For your lab configure something like:

```text
Minimum length:
12

Digits:
1

Lowercase:
1

Uppercase:
1

Special:
1

Not Username:
ON

Not Email:
ON
```

Don't obsess over arbitrary password complexity rules in a real product. Long passwords/passphrases and MFA matter much more than endlessly complicated character requirements.

---

# Part 32 — Enable brute-force detection

Go to:

```text
Realm settings
→ Security defenses
```

Enable:

```text
Brute Force Detection
```

Keycloak provides built-in brute-force detection specifically to protect against repeated failed authentication attempts. ([Keycloak][8])

Now deliberately test it.

Use an incorrect password repeatedly for:

```text
alice
```

Observe what Keycloak does.

Then inspect:

```text
Events
```

You should begin seeing authentication failures.

This is one of the things you should become very comfortable investigating in the GUI.

---

# Part 33 — Enable email verification

Later we'll configure SMTP.

For now understand the workflow.

Go to:

```text
Realm settings
→ Login
```

Enable the appropriate:

```text
Verify email
```

Then:

```text
Users
→ alice
```

You can trigger the verification/reset actions from the user management interface.

Keycloak supports email verification and password-reset actions through the realm email configuration. ([Keycloak][4])

---

# Part 34 — Configure MFA

Go to:

```text
Authentication
→ Policies
→ OTP Policy
```

Review:

```text
OTP type
Hash algorithm
Digits
Period
Look around window
```

For the lab, use TOTP.

Then inspect:

```text
Authentication
→ Required actions
```

You will see things such as:

```text
Configure OTP
Verify Email
Update Password
...
```

You can require an individual user to configure OTP.

For example:

```text
Users
→ alice
→ Required actions
→ Configure OTP
```

Next time Alice logs in, Keycloak will force OTP setup.

Keycloak's current documentation supports TOTP configuration through this policy and required-action mechanism. ([Keycloak][7])

---

# Part 35 — Learn authentication flows

This is where you start getting into serious Keycloak administration.

Go to:

```text
Authentication
→ Flows
```

Inspect:

```text
Browser
Direct Grant
Registration
Reset Credentials
```

Do not immediately modify the built-in Browser flow.

Instead, learn to read it.

You will see structures resembling:

```text
Browser
 ├── Cookie
 ├── Identity Provider Redirector
 └── Forms
      ├── Username Password Form
      └── OTP
```

The important thing is understanding:

```text
Flow
   ↓
Subflow
   ↓
Execution
   ↓
Requirement
```

Requirements commonly include:

```text
Required
Alternative
Disabled
Conditional
```

Experiment in a **test realm**, not your eventual production realm.

---

# Part 36 — Create a custom MFA browser flow

Clone the browser flow.

For example:

```text
Browser
→ Copy
```

Name:

```text
browser-mfa
```

Then inspect it.

Configure the OTP execution so that users who authenticate with password proceed to:

```text
Password
    ↓
OTP
    ↓
Success
```

Bind it as the realm's browser flow.

The exact UI presentation can vary slightly across Keycloak patch releases, but the current administration model is still based on authentication flows and executions. ([Keycloak][7])

---

# Part 37 — Configure token lifetimes

Go to:

```text
Realm settings
→ Tokens
```

You will see controls such as:

```text
Access Token Lifespan
SSO Session Idle
SSO Session Max
Client login timeout
User initiated action lifespan
...
```

Keycloak documents token and session timeout configuration in the Realm Settings `Sessions` and `Tokens` sections. ([Keycloak][7])

For the laboratory, intentionally make tokens short so you can observe expiration.

For example:

```text
Access Token Lifespan:
5 minutes
```

This is useful for testing.

In production, don't blindly copy some magic value from a tutorial. Choose based on:

```text
threat model
UX
token exposure risk
refresh behavior
session model
```

---

# Part 38 — Test expired access tokens

Generate a token.

Call:

```text
GET /me
```

Wait for expiry.

Call again.

FastAPI should return:

```text
401 Token expired
```

This is a very important test.

You've demonstrated:

```text
Keycloak
   ↓
exp claim
   ↓
FastAPI
   ↓
jwt verification
```

---

# Part 39 — Refresh token exercise

When using the authorization-code flow, Keycloak generally returns a refresh token along with the access token where applicable.

Postman can use refresh tokens to obtain a new access token; its current OAuth2 tooling supports automatic refresh when a refresh token exists. ([Postman Docs][5])

In Postman:

```text
Manage Tokens
```

inspect:

```text
access_token
refresh_token
expires_in
```

When the access token expires, refresh it.

Observe:

```text
old access token
      ↓
refresh token
      ↓
new access token
```

---

# Part 40 — Enable refresh-token rotation

Go to:

```text
Realm settings
→ Tokens
```

Find:

```text
Revoke Refresh Token
```

For a hardened environment, understand and test enabling it.

Keycloak documents this as issuing a replacement refresh token during refresh operations, meaning clients must store/use the latest token. ([Keycloak][7])

This exercise is useful because you will see why refresh-token handling in an actual application isn't just:

```python
refresh_token = forever
```

---

# Part 41 — Disable dangerous client flows

Go through:

```text
Clients
→ postman-public
```

Verify:

```text
Standard flow             ON
Implicit flow             OFF
Direct access grants      OFF
Service accounts          OFF
Device flow               OFF
Token exchange            OFF
```

Only enable a flow when you actually need it.

The general principle is:

```text
Attack surface
     =
features you enable
```

Don't enable ten OAuth mechanisms because "maybe I'll need them someday."

---

# Part 42 — Learn Direct Access Grants

For educational purposes, now create a temporary client:

```text
postman-password-lab
```

Enable:

```text
Direct access grants
```

Then in Postman use:

```text
Grant Type:
Password Credentials
```

Keycloak will accept:

```text
username
password
client_id
```

and issue a token.

Postman currently still supports Password Credentials, but its documentation explicitly says this flow involves sending the username and password directly from the client and is not recommended for third-party scenarios. ([Postman Docs][5])

Understand it.

Then delete the client.

Your normal architecture should use:

```text
Authorization Code + PKCE
```

for interactive users, rather than asking your frontend to collect their Keycloak password.

---

# Part 43 — Learn the Device Authorization Grant

Now create another temporary client:

```text
device-lab
```

Explore the client capability:

```text
OAuth 2.0 Device Authorization Grant
```

Keycloak supports the device authorization flow as a client capability. ([Keycloak][4])

This is useful for things such as:

```text
CLI applications
TV apps
headless devices
developer tools
```

You should understand how it differs from browser login.

---

# Part 44 — Configure logout

Inspect:

```text
Realm
→ OpenID Connect endpoints
```

The logout flow is separate from simply deleting a token in Postman.

A bearer JWT is generally self-contained.

Your FastAPI server does not automatically know that:

```text
Alice clicked logout
```

unless you introduce a mechanism for that.

This is why you need to understand the difference between:

```text
Keycloak session
access token
refresh token
application session
```

Keycloak documents front-channel and back-channel logout separately, with back-channel logout generally being more reliable where appropriate. ([Keycloak][7])

---

# Part 45 — Learn revocation

Go to:

```text
Sessions
```

Experiment with:

```text
Revocation
```

Keycloak can revoke active sessions and apply a revocation policy, but existing access tokens don't magically disappear merely because a logout action occurred; outstanding tokens may remain usable until expiry depending on the integration. ([Keycloak][7])

This is a crucial production-security concept.

---

# Part 46 — Understand JWT vs introspection

Your FastAPI implementation currently does:

```text
local JWT verification
```

Advantages:

```text
fast
no network request per API call
easy to scale
```

But:

```text
revoked token
```

may remain valid until expiration.

Alternatively, the API can call Keycloak's introspection endpoint.

That gives you more centralized token state at the cost of:

```text
network call
Keycloak dependency
latency
higher load
```

A practical architecture often looks like:

```text
normal API call
      ↓
local JWT verification
```

and uses introspection only where it is specifically justified.

---

# Part 47 — Learn key rotation

Go to:

```text
Realm settings
→ Keys
```

Inspect the active signing keys.

Generate/rotate keys in the lab.

Then issue a new token.

Look at:

```text
kid
```

in the JWT header.

It will change when a new signing key becomes active.

Your FastAPI application should continue functioning because it retrieves the correct signing key from the JWKS endpoint.

This is exactly why this:

```python
PyJWKClient(...)
```

approach is preferable to hard-coding a PEM file.

---

# Part 48 — Test algorithm confusion

Your code currently explicitly specifies:

```python
algorithms=["RS256"]
```

Do not change this to:

```python
algorithms=["RS256", "HS256"]
```

based on the token.

The verifier should decide what algorithms are trusted.

Never do something conceptually like:

```python
algorithm = token["alg"]
jwt.decode(..., algorithms=[algorithm])
```

The attacker must not get to choose your cryptographic policy.

---

# Part 49 — Improve your FastAPI security model

At this point, your validator should explicitly enforce:

```text
signature
issuer
audience
expiration
required claims
trusted algorithm
```

For example:

```python
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],
    issuer=self.issuer,
    audience=self.audience,
    options={
        "require": [
            "exp",
            "iat",
            "iss",
            "sub",
        ]
    },
)
```

This is much better than:

```python
jwt.decode(token, key)
```

---

# Part 50 — Never trust claims blindly

Do not do this:

```python
username = payload["preferred_username"]
```

and then use the username as your application's primary identity.

Prefer:

```text
sub
```

as the stable external identity identifier.

Use:

```text
preferred_username
email
name
```

as attributes.

Conceptually:

```text
User identity:
sub

Display name:
preferred_username

Email:
email
```

In your database:

```text
external_identity_provider = keycloak
external_subject = sub
```

is much safer than:

```text
username = preferred_username
```

because usernames can change.

---

# Part 51 — Groups

Go to:

```text
Groups
```

Create:

```text
engineering
admins
support
```

Put:

```text
alice → engineering
bob   → engineering
admin → admins
```

Then explore group role mappings.

This lets you create structures like:

```text
engineering
   ↓
fastapi-api:user
```

rather than assigning every permission manually.

---

# Part 52 — Realm roles vs client roles

Now deliberately create a realm role:

```text
Realm roles
→ Create role
```

Call it:

```text
platform-user
```

Then compare it with:

```text
fastapi-api:user
```

You now have:

```text
realm role
platform-user

client role
fastapi-api:user
```

Use client roles for permissions that are specifically about one application/API.

Use realm roles when you genuinely need a realm-wide concept.

Keycloak places realm roles and client roles into different token structures; client roles are represented under `resource_access`. ([Keycloak][7])

---

# Part 53 — Composite roles

Create:

```text
fastapi-api:editor
```

and make it composite of:

```text
user
writer
```

Then assign:

```text
editor
```

to Bob.

Now inspect Bob's token.

You'll start understanding how permission hierarchies can be built:

```text
editor
 ├── user
 └── writer
```

This becomes useful as your SaaS gets more complex.

---

# Part 54 — Client scopes

Client scopes are one of the Keycloak concepts you should become very comfortable with.

You created:

```text
fastapi-api-scope
```

Now create:

```text
profile-lite
```

Inside it, experiment with:

```text
protocol mappers
```

You can control things such as:

```text
username
email
groups
audience
roles
custom claims
```

This gives you a powerful pipeline:

```text
User
 ↓
Roles/groups/attributes
 ↓
Client scope
 ↓
Protocol mapper
 ↓
JWT claim
 ↓
FastAPI authorization
```

That is the practical heart of Keycloak token customization.

---

# Part 55 — Add a custom claim

Create a user attribute:

```text
tenant_id = tenant-a
```

Then create a mapper that puts:

```text
tenant_id
```

into the access token.

Your token becomes conceptually:

```json
{
  "sub": "...",
  "tenant_id": "tenant-a"
}
```

FastAPI can then do:

```python
tenant_id = user["tenant_id"]
```

and establish tenant isolation.

For your SaaS, this concept will eventually become extremely useful.

---

# Part 56 — Multi-tenancy experiment

Create:

```text
tenant-a
tenant-b
```

Create:

```text
alice → tenant-a
bob   → tenant-b
```

Make a protected endpoint:

```text
GET /documents
```

Then return data based on:

```text
tenant_id
```

The conceptual architecture becomes:

```text
JWT
 │
 ├── sub
 ├── tenant_id
 └── roles
       │
       ▼
 FastAPI authorization
       │
       ▼
 PostgreSQL query
 WHERE tenant_id = JWT.tenant_id
```

Do not blindly trust a `tenant_id` sent by the frontend.

Take the tenant identity from the authenticated principal or your server-side user mapping.

---

# Part 57 — CORS

Your current Postman-only architecture does not really need CORS.

But eventually you'll have:

```text
React frontend
      ↓
FastAPI
```

Then configure CORS deliberately.

Do **not** use:

```python
allow_origins=["*"]
allow_credentials=True
```

in a production authenticated application.

Instead:

```python
from fastapi.middleware.cors import CORSMiddleware


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

Later replace:

```text
http://localhost:3000
```

with your actual frontend origin.

---

# Part 58 — Secure the Keycloak realm itself

Your application is only as secure as your identity server.

First:

```text
master realm
```

should have strong administrator accounts.

Don't build your application's everyday administrative workflow around one all-powerful admin user.

Keycloak supports dedicated realm administration with specific `realm-management` roles rather than requiring everyone to be a super-admin. ([Keycloak][7])

Examples:

```text
realm-admin
manage-users
view-users
manage-clients
view-clients
```

Create administrators with only the necessary privileges.

---

# Part 59 — Never expose the Admin Console unnecessarily

Your local lab:

```text
localhost:8080
```

is fine.

Production:

```text
Internet
    ↓
Keycloak
```

should not automatically imply:

```text
Internet
    ↓
Admin Console
Admin API
```

Keycloak's administration documentation specifically warns about externally exposing administrative endpoints when external access is unnecessary. ([Keycloak][8])

You want administrative access controlled separately.

---

# Part 60 — HTTPS

Your lab currently uses:

```text
http://localhost:8080
```

That's appropriate for a local development environment.

Production should use:

```text
https://auth.example.com
```

Keycloak has realm SSL modes including:

```text
None
External requests
All requests
```

For production, HTTPS should be mandatory. Keycloak documents these options under Realm Settings → General → Require SSL. ([Keycloak][4])

---

# Part 61 — Understand why `localhost` is special

Keycloak allows HTTP in some development/private-address scenarios.

That does **not** mean:

```text
HTTP is safe in production.
```

For your lab:

```text
localhost
```

is fine.

For production:

```text
https://auth.vbcreators.com
```

should be the public issuer.

This affects:

```text
iss
redirect_uri
JWKS URI
authorization URI
token URI
audience
cookies
```

---

# Part 62 — Production-style hostname

Eventually you'll deploy something like:

```text
https://auth.vbcreators.com
```

behind:

```text
Cloudflare
Traefik
```

Then Keycloak must know its externally visible hostname.

This matters because Keycloak will emit URLs into:

```text
OIDC discovery
redirects
issuer
emails
tokens
```

The external/public hostname must be consistent.

Never casually mix:

```text
http://localhost:8080
https://auth.vbcreators.com
http://192.168.x.x
```

in one realm's production configuration.

---

# Part 63 — Token lifetimes

A useful production starting mindset is:

```text
Access token
short-lived

Refresh token
longer-lived

SSO session
longer-lived than access token
```

But don't choose values blindly.

For an API:

```text
access token
~5–15 min
```

is often a reasonable starting point.

Then carefully choose:

```text
SSO idle
SSO max
refresh behavior
```

Keycloak exposes separate controls for these. ([Keycloak][7])

---

# Part 64 — Refresh-token compromise exercise

Do this deliberately in your lab.

Get:

```text
access token
refresh token
```

Then:

1. Log out.
2. Try the refresh token.
3. Observe whether it remains usable.
4. Enable refresh-token revocation/rotation.
5. Repeat.
6. Try using the old refresh token after replacement.

This is one of the best ways to turn abstract OAuth knowledge into practical intuition.

---

# Part 65 — Events

Go to:

```text
Realm settings
→ Events
```

Look at:

```text
Login
Login error
Logout
Register
Code to token
Refresh token
...
```

Then generate events:

```text
successful login
failed password
logout
refresh
```

and inspect them.

For production this becomes invaluable for:

```text
security monitoring
incident investigation
audit
fraud detection
user support
```

---

# Part 66 — Create a security test matrix

Now start testing your system like an engineer.

Make a checklist:

| Test                  | Expected |
| --------------------- | -------- |
| No token              | 401      |
| Invalid signature     | 401      |
| Expired token         | 401      |
| Wrong issuer          | 401      |
| Wrong audience        | 401      |
| Missing `sub`         | 401      |
| User role missing     | 403      |
| Correct role          | 200      |
| Malformed JWT         | 401      |
| Wrong signing key     | 401      |
| Correct service token | 200      |
| Wrong service role    | 403      |

This is much more valuable than merely seeing:

> "Login works."

---

# Part 67 — Add tests to FastAPI

Install:

```bash
uv add --dev pytest httpx
```

Create:

```text
tests/
    test_security.py
```

Your eventual test suite should test:

```text
valid token
expired token
wrong audience
wrong issuer
missing claims
role authorization
```

Do not make unit tests depend on a running Keycloak unless the test specifically needs Keycloak integration.

Use two levels:

```text
unit tests
    ↓
mock JWT verification

integration tests
    ↓
real Keycloak
```

This distinction becomes extremely important in CI.

---

# Part 68 — Add an integration Keycloak container

Eventually create a test `docker-compose.yml`:

```yaml
services:

  keycloak:
    image: quay.io/keycloak/keycloak:26.7.2
    command: start-dev
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: admin
    ports:
      - "8080:8080"

  api:
    build: .
    ports:
      - "8000:8000"
```

Current Keycloak's Docker documentation uses the `quay.io/keycloak/keycloak` image and `start-dev` for development/testing. ([Keycloak][2])

In CI, seed the realm automatically rather than manually configuring the GUI every time.

---

# Part 69 — Learn realm import/export

This is where your GUI work becomes reproducible infrastructure.

Once you have a working lab realm, learn to export:

```text
fastapi-lab
```

Then inspect the JSON.

You'll begin seeing representations of:

```text
clients
roles
users
client scopes
protocol mappers
flows
identity providers
```

This is the bridge from:

```text
"I know how to click Keycloak"
```

to:

```text
"I can provision Keycloak reproducibly."
```

For your real project, this is essential.

---

# Part 70 — Do not blindly commit exported secrets

Realm exports can contain information you don't want casually committing to Git.

Treat exports carefully.

Especially inspect:

```text
client secrets
user credentials
service account credentials
```

Use environment-specific configuration and secret management.

For your eventual architecture, your secret-management system can be used for:

```text
Keycloak admin bootstrap secrets
client secrets
SMTP credentials
service account secrets
```

rather than putting them directly in Git.

---

# Part 71 — Learn Admin REST API

Now we move from GUI administration to automation.

Keycloak exposes an Admin REST API.

Your future automation can do things such as:

```text
create user
create client
create role
assign role
disable user
reset password
```

rather than requiring a human to click.

The Admin REST API is documented by Keycloak as part of its API documentation. ([Keycloak][1])

But here's a security principle:

Do **not** let your ordinary FastAPI application possess unrestricted Keycloak admin credentials.

Separate:

```text
application client
```

from:

```text
Keycloak administrative automation client
```

---

# Part 72 — Learn least privilege for the Admin API

Suppose an internal provisioning service needs to:

```text
create users
```

It should not necessarily receive:

```text
realm-admin
```

Keycloak provides fine-grained realm management roles such as:

```text
create-client
manage-users
view-users
manage-clients
```

etc. ([Keycloak][7])

Your provisioning service should get only what it needs.

---

# Part 73 — Client secrets vs private-key JWT

You've already used:

```text
client_id
client_secret
```

Now learn another confidential-client mechanism:

```text
private_key_jwt
```

Instead of:

```text
shared secret
```

the client proves possession of a private key by signing a client assertion.

This eliminates a shared static secret between the application and Keycloak.

Keycloak supports signed JWT client authentication, including private-key based client authentication. ([Keycloak][7])

For your production learning path, absolutely practice this.

---

# Part 74 — mTLS / sender-constrained tokens

This is advanced territory.

Keycloak 26.x has capabilities related to sender-constrained tokens such as:

```text
DPoP
mTLS-bound tokens
```

These bind tokens more strongly to a key/client rather than making the token purely bearer-style.

You don't need these for your initial FastAPI application.

But once you're comfortable with normal JWT bearer tokens, this is the correct place to start exploring more advanced token-binding mechanisms. Keycloak's current administration guide documents DPoP and certificate-bound token capabilities. ([Keycloak][4])

---

# Part 75 — Fine-grained authorization with Keycloak

Until now you've done:

```text
RBAC
```

using:

```text
roles
```

Keycloak also has **Authorization Services**.

There you can work with:

```text
resources
scopes
policies
permissions
```

Current Keycloak Authorization Services supports combinations including RBAC, ABAC, user-based, context-based and rule-based authorization. ([Keycloak][9])

Imagine:

```text
Resource:
document-123

Scopes:
read
write
delete
```

Policies:

```text
owner
editor
admin
```

Permission:

```text
owner can write document
editor can read document
admin can delete document
```

This is a different level of authorization from merely:

```text
user.has_role("admin")
```

---

# Part 76 — Don't put all application authorization in Keycloak

This is a very important architectural lesson.

Use Keycloak for identity and broad authorization metadata.

Your application should still enforce business rules.

For example:

```text
JWT:
role = editor
```

does not automatically mean:

```text
editor can modify ANY document
```

Your application might enforce:

```text
editor
+
tenant matches
+
document belongs to tenant
+
document not archived
```

So:

```text
Keycloak
    ↓
identity / coarse permission
    ↓
FastAPI
    ↓
business authorization
```

is often the better design.

---

# Part 77 — OpenAPI integration

FastAPI can expose its security requirements through OpenAPI.

Eventually you want Swagger UI to show:

```text
Authorize
```

and your API documented as:

```text
Bearer authentication
```

FastAPI's security utilities integrate authentication schemes into its generated OpenAPI documentation. ([FastAPI][10])

For your project, the API docs should make it obvious:

```text
GET /me
Security: Bearer

GET /admin
Security: Bearer
Role: admin
```

---

# Part 78 — Add a proper current-user model

Don't let dictionaries like:

```python
dict[str, Any]
```

spread throughout your whole application.

Create:

```python
from pydantic import BaseModel


class CurrentUser(BaseModel):
    subject: str
    username: str | None = None
    email: str | None = None
    roles: set[str]
```

Then your security layer becomes:

```text
JWT
 ↓
CurrentUser
 ↓
application
```

Instead of:

```text
application
 ↓
raw Keycloak JWT dictionary
```

This is much cleaner.

---

# Part 79 — Extract client roles cleanly

Create:

```python
def extract_client_roles(
    payload: dict[str, Any],
    client_id: str,
) -> set[str]:
    resource_access = payload.get(
        "resource_access",
        {}
    )

    client_access = resource_access.get(
        client_id,
        {}
    )

    return set(
        client_access.get("roles", [])
    )
```

Then:

```python
roles = extract_client_roles(
    payload,
    settings.keycloak_client_id,
)
```

Your application now has an explicit abstraction:

```text
Keycloak JWT
     ↓
KeycloakClaims
     ↓
Application identity
```

---

# Part 80 — The architecture you should eventually reach

Your current lab can evolve into:

```text
src/
└── ai_rag/
    ├── main/
    │   └── app.py
    │
    ├── core/
    │   ├── config.py
    │   └── security.py
    │
    ├── auth/
    │   ├── dependencies.py
    │   ├── models.py
    │   ├── permissions.py
    │   └── keycloak.py
    │
    ├── domains/
    │
    ├── api/
    │   ├── routers/
    │   └── dependencies/
    │
    └── services/
```

Eventually:

```text
JWT
 ↓
Authentication dependency
 ↓
CurrentPrincipal
 ↓
Authorization dependency
 ↓
Permission
 ↓
Router
 ↓
Service
```

That's the model I would use for your larger FastAPI SaaS.

---

# Part 81 — Now make the GUI your playground

At this stage, start deliberately changing things and observing tokens.

Do this exercise:

### Exercise A — role experiment

Remove Alice's:

```text
user
```

role.

Generate a new token.

Call:

```text
GET /user
```

Expected:

```text
403
```

---

### Exercise B — audience experiment

Remove:

```text
fastapi-api-audience
```

Generate a new token.

Expected:

```text
401
```

---

### Exercise C — issuer experiment

Change FastAPI's expected realm:

```text
fastapi-lab
```

to:

```text
another-realm
```

Expected:

```text
401
```

---

### Exercise D — expiration experiment

Reduce:

```text
Access Token Lifespan
```

to:

```text
1 minute
```

Get token.

Wait.

Expected:

```text
401 Token expired
```

---

### Exercise E — PKCE experiment

Change:

```text
PKCE method
S256
```

to disabled.

Observe the behavioral difference.

Then restore:

```text
S256
```

---

# Part 82 — Learn what should NOT be in the access token

A common beginner mistake is:

```text
"Let's put everything about the user into JWT."
```

Don't.

JWTs are sent repeatedly.

For example:

```text
GET /chat
Authorization: Bearer ...
```

```text
POST /documents
Authorization: Bearer ...
```

```text
GET /profile
Authorization: Bearer ...
```

If the token contains huge amounts of information, every request carries it.

Keep claims useful:

```text
sub
iss
aud
exp
roles
tenant
small identity claims
```

and retrieve larger profile/application data from your database when appropriate.

---

# Part 83 — Keycloak is not your application database

Don't make every FastAPI request call:

```text
Keycloak → give me user
```

unless needed.

A useful model is:

```text
Keycloak
    Identity provider

PostgreSQL
    Application data
```

For example:

```text
Keycloak:
sub = 12345

PostgreSQL:

user_id = 77
keycloak_subject = 12345
tenant_id = 4
plan = pro
preferences = ...
```

This cleanly separates:

```text
identity
```

from:

```text
application state
```

---

# Part 84 — Identity providers

Now inspect:

```text
Identity providers
```

You can later connect:

```text
Google
GitHub
Microsoft
Apple
LDAP
another OIDC provider
another SAML provider
```

Your application doesn't necessarily need to know how the user authenticated.

It receives the same basic Keycloak identity.

The resulting architecture is:

```text
Google ───────┐
GitHub ───────┤
Microsoft ────┤
LDAP ─────────┤
              ▼
           Keycloak
              ▼
           FastAPI
```

This is one of Keycloak's biggest practical advantages.

---

# Part 85 — User Federation

Explore:

```text
User federation
```

This becomes important when you integrate:

```text
LDAP
Active Directory
legacy identity stores
```

Do not implement LDAP directly in every service.

Instead:

```text
LDAP
 ↓
Keycloak
 ↓
OIDC
 ↓
your application
```

This keeps your application focused on OIDC rather than identity-provider-specific protocols.

---

# Part 86 — Back to Postman: make a collection

Create:

```text
Keycloak FastAPI Lab
```

Requests:

```text
01 health
02 public
03 me
04 user
05 writer
06 admin
07 service-user
08 service-writer
```

Create environment variables:

```text
base_url = http://localhost:8000
keycloak_url = http://localhost:8080
realm = fastapi-lab
```

Then requests become:

```text
{{base_url}}/me
```

and:

```text
{{base_url}}/admin
```

This starts turning the experiment into a repeatable test system.

---

# Part 87 — Add Postman tests

For:

```text
GET /admin
```

you can add tests checking:

```text
status == 200
```

For Alice's token:

```text
/admin
```

should assert:

```text
403
```

For Bob:

```text
/writer
```

should assert:

```text
200
```

Now you're testing authorization behavior rather than manually looking at responses.

Postman supports collection/request tests and OAuth2 token handling; its current OAuth documentation also notes that deleting a token in Postman does not revoke it at the authorization server. ([Postman Docs][5])

---

# Part 88 — Security checklist for your client

For every client, ask:

```text
1. Is this public or confidential?
2. Does it really need a client secret?
3. Does it need Standard Flow?
4. Does it need PKCE?
5. Does it need Direct Access Grants?
6. Does it need implicit flow?
7. Does it need service accounts?
8. Which redirect URIs are valid?
9. Which post-logout URIs are valid?
10. Which scopes does it need?
11. Which audiences should its tokens contain?
12. Which roles should its tokens contain?
13. What is its token lifespan?
```

Do this every time.

---

# Part 89 — Security checklist for your realm

Your realm should eventually have:

```text
HTTPS
strong admin authentication
least-privilege administrators
strong password policy
brute-force protection
MFA
email verification
short-lived access tokens
carefully configured refresh behavior
limited client scopes
limited role scopes
restricted redirect URIs
disabled unused grant types
secure hostname configuration
event logging
appropriate session timeout
secure SMTP
secret management
regular backups
```

Do not interpret this as:

> "Turn every feature on."

Interpret it as:

> "Every enabled capability should have a reason."

---

# Part 90 — Your final FastAPI security dependency

Eventually your application should conceptually look like:

```python
@app.get("/admin")
async def admin(
    principal: CurrentUser = Security(
        require_permission("fastapi-api:admin")
    ),
):
    ...
```

rather than every endpoint individually doing:

```python
if "admin" not in token:
    ...
```

Centralize authorization.

---

# Part 91 — The most important Keycloak URLs to memorize

For your realm:

```text
Issuer
http://localhost:8080/realms/fastapi-lab
```

OIDC discovery:

```text
http://localhost:8080/realms/fastapi-lab/.well-known/openid-configuration
```

Authorization endpoint:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/auth
```

Token endpoint:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/token
```

JWKS:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/certs
```

UserInfo:

```text
http://localhost:8080/realms/fastapi-lab/protocol/openid-connect/userinfo
```

The OIDC endpoint structure is documented by Keycloak's current OpenID Connect documentation. ([Keycloak][3])

---

# Part 92 — The complete authentication flow you should now be able to reproduce manually

You should now be able to draw this without looking it up:

```text
                ┌───────────┐
                │  Postman  │
                └─────┬─────┘
                      │
                      │ authorization request
                      ▼
              ┌───────────────┐
              │   Keycloak    │
              │               │
              │ login user    │
              └───────┬───────┘
                      │
                      │ authorization code
                      ▼
                ┌───────────┐
                │  Postman  │
                └─────┬─────┘
                      │
                      │ code + code_verifier
                      ▼
              ┌───────────────┐
              │   Keycloak    │
              └───────┬───────┘
                      │
                      │ access token
                      ▼
                ┌───────────┐
                │  Postman  │
                └─────┬─────┘
                      │
                      │ Bearer JWT
                      ▼
               ┌────────────┐
               │  FastAPI   │
               └─────┬──────┘
                     │
              verify signature
                     │
              verify issuer
                     │
              verify audience
                     │
              verify expiry
                     │
                check roles
                     │
                     ▼
                  resource
```

And machine-to-machine:

```text
FastAPI Worker
      │
      │ client_id + secret
      ▼
   Keycloak
      │
      │ access token
      ▼
 FastAPI API
```

---

# Part 93 — What "expert" should mean for you

After this lab, you should be able to look at any Keycloak configuration and answer:

### Realm

```text
What security boundary does this represent?
```

### Client

```text
Who is the OAuth client?
Is it public or confidential?
```

### Client scope

```text
What permissions/claims does this scope introduce?
```

### Mapper

```text
Why is this claim appearing in the JWT?
```

### Role

```text
Is this a realm role or client role?
```

### Authentication flow

```text
What exactly happens when the user authenticates?
```

### Token

```text
Why does this claim exist?
```

### FastAPI

```text
Which authority am I trusting?
Which audience am I protecting?
How am I enforcing permissions?
```

Once those answers become instinctive, you are comfortable with Keycloak rather than merely familiar with its terminology.

---

# Part 94 — Your practical mastery checklist

You should be able to do each of these **without following a tutorial**:

```text
[ ] Create a realm
[ ] Create users
[ ] Set passwords
[ ] Create groups
[ ] Create realm roles
[ ] Create client roles
[ ] Create clients
[ ] Configure public clients
[ ] Configure confidential clients
[ ] Configure redirect URIs
[ ] Configure PKCE
[ ] Create client scopes
[ ] Create protocol mappers
[ ] Add an audience
[ ] Add custom claims
[ ] Assign roles
[ ] Configure role scope mappings
[ ] Disable Full Scope Allowed
[ ] Configure token lifetimes
[ ] Enable brute-force detection
[ ] Configure password policy
[ ] Configure OTP
[ ] Configure authentication flows
[ ] Configure required actions
[ ] Configure email
[ ] Configure logout
[ ] Inspect sessions
[ ] Inspect events
[ ] Rotate keys
[ ] Understand JWKS
[ ] Use Authorization Code + PKCE
[ ] Use Client Credentials
[ ] Understand Direct Access Grants
[ ] Understand Device Authorization
[ ] Configure service accounts
[ ] Restrict service-account roles
[ ] Call Keycloak token endpoint from Python
[ ] Validate Keycloak JWT in FastAPI
[ ] Validate issuer
[ ] Validate audience
[ ] Validate expiration
[ ] Validate signature
[ ] Validate roles
[ ] Handle 401
[ ] Handle 403
[ ] Test with Postman
[ ] Test with automated tests
[ ] Export/import a realm
[ ] Use Admin REST API
[ ] Understand private_key_jwt
[ ] Understand Authorization Services
[ ] Understand identity brokering
[ ] Understand user federation
[ ] Understand production HTTPS/hostname configuration
```

---

# One important thing about how I recommend you continue

Don't try to jump straight from this laboratory into:

```text
Keycloak
+
PostgreSQL
+
FastAPI
+
React
+
Cloudflare
+
Traefik
+
MFA
+
Google login
+
RBAC
+
ABAC
```

all at once.

The best progression is:

```text
Level 1
Realm + User + Client

        ↓

Level 2
Postman + Authorization Code + PKCE

        ↓

Level 3
FastAPI JWT verification

        ↓

Level 4
Roles + permissions + audience

        ↓

Level 5
Client Credentials + service accounts

        ↓

Level 6
Scopes + mappers + custom claims

        ↓

Level 7
MFA + authentication flows

        ↓

Level 8
Sessions + refresh + logout + revocation

        ↓

Level 9
Admin REST API + automation

        ↓

Level 10
Authorization Services

        ↓

Level 11
Identity brokering + LDAP

        ↓

Level 12
Production hardening

        ↓

Level 13
Automated CI/CD provisioning
```

And most importantly, **don't just read this**.

For your lab, the first concrete target is:

```text
Keycloak
   ↓
fastapi-lab
   ↓
postman-public
   ↓
Authorization Code + PKCE
   ↓
access token
   ↓
FastAPI
   ↓
JWKS + RS256 validation
   ↓
audience
   ↓
roles
   ↓
/me
/user
/writer
/admin
```

Once that is working, you have crossed the most important practical boundary: you can actually operate Keycloak and make a real FastAPI application trust and authorize Keycloak-issued identities. The next layer is turning this exact lab into a **production-grade FastAPI/Keycloak implementation with a clean `src/` architecture, typed principals, permission dependencies, automated tests, Docker Compose, realm-as-code, and secure production settings**.

[1]: https://www.keycloak.org/docs/?utm_source=chatgpt.com "Documentation - Keycloak"
[2]: https://www.keycloak.org/getting-started/getting-started-docker?utm_source=chatgpt.com "Docker - Keycloak"
[3]: https://www.keycloak.org/securing-apps/oidc-layers?utm_source=chatgpt.com "Securing applications and services with OpenID Connect - Keycloak"
[4]: https://www.keycloak.org/docs/latest/server_admin/?utm_source=chatgpt.com "Server Administration Guide"
[5]: https://learning.postman.com/docs/use/send-requests/authorization/oauth-20?utm_source=chatgpt.com "Authenticate with OAuth 2.0 authentication in Postman | Postman Docs"
[6]: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/?utm_source=chatgpt.com "OAuth2 with Password (and hashing), Bearer with JWT tokens - FastAPI"
[7]: https://www.keycloak.org/docs/latest/server_admin/index.html?utm_source=chatgpt.com "Server Administration Guide"
[8]: https://www.keycloak.org/docs/21.1.2/server_admin/?utm_source=chatgpt.com "Server Administration Guide"
[9]: https://www.keycloak.org/docs/latest/authorization_services/?utm_source=chatgpt.com "Authorization Services Guide"
[10]: https://fastapi.tiangolo.com/tutorial/security/?utm_source=chatgpt.com "Security - FastAPI"
