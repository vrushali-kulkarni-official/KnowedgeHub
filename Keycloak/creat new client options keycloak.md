Yes. This screen is **Keycloak → Clients → Create client → Capability config**.

This page is essentially where you tell Keycloak:

> **“What kind of OAuth/OIDC client is this, and which authentication/authorization flows is it allowed to use?”**

The options are not all independent. Some are disabled because another capability must be enabled first.

I’ll explain **every visible option**, what it does internally, when to use it, and what I would choose for a **FastAPI backend**.

---

# 1. First, understand what a “Client” means

In Keycloak, a **client** is an application/service that wants to use Keycloak for authentication or authorization.

Examples:

```text
React SPA
    ↓
Keycloak

FastAPI backend
    ↓
Keycloak

Mobile app
    ↓
Keycloak

CLI application
    ↓
Keycloak

Service A → Service B
    ↓
Keycloak
```

A client is **not necessarily a human user**.

For example:

```text
User
  ↓
React frontend
  ↓
Keycloak
```

Here the React application is a client.

And:

```text
FastAPI service
  ↓
Keycloak
```

The FastAPI service can also be a client.

---

# 2. Client authentication

Your screenshot:

```text
Client authentication     [ OFF ]
```

This determines whether the application must **authenticate itself to Keycloak**.

There are two fundamentally different types of OAuth clients:

### Public client

```text
client_id = my-react-app
client_secret = ❌
```

The application cannot safely keep a secret.

Typical examples:

* SPA
* mobile application
* desktop application

Why?

Because anything shipped to the user's browser/device can potentially be inspected.

---

### Confidential client

```text
client_id = my-fastapi
client_secret = ********
```

The application can safely keep credentials on a server.

Typical examples:

* FastAPI backend
* Django backend
* server-side web application
* backend service

So:

```text
Client authentication OFF
        ↓
Public client
```

and usually:

```text
Client authentication ON
        ↓
Confidential client
```

Keycloak's documentation describes client authentication as the capability that determines whether the client authenticates when communicating with Keycloak. ([Keycloak][1])

### For your FastAPI application

Usually:

```text
Client authentication: ON
```

For a browser SPA:

```text
Client authentication: OFF
```

---

# 3. Authorization

Your screenshot:

```text
Authorization     [ OFF ]
```

This is **not the same thing as authentication**.

Authentication answers:

> **Who are you?**

Authorization answers:

> **What are you allowed to do?**

Keycloak's Authorization Services provide fine-grained authorization such as RBAC, ABAC, user-based, context-based and other policy mechanisms. ([Keycloak][2])

---

### Without Authorization Services

Your FastAPI application might simply inspect:

```json
{
  "sub": "123",
  "preferred_username": "bhargav",
  "realm_access": {
    "roles": ["user"]
  }
}
```

and decide:

```python
if "admin" in roles:
    allow()
```

Keycloak is primarily issuing identities/tokens, while your application enforces the permissions.

---

### With Authorization Services

Keycloak itself can maintain things such as:

```text
Resources
    ↓
Scopes
    ↓
Policies
    ↓
Permissions
```

For example:

```text
Resource:
    /documents

Scopes:
    read
    write
    delete

Policies:
    admin
    document-owner
    manager

Permissions:
    admin → read/write/delete
```

This becomes useful for **fine-grained authorization**.

### For your learning project

Initially:

```text
Authorization: OFF
```

Learn ordinary OAuth/OIDC + roles first.

Then later turn it ON and learn Keycloak Authorization Services.

---

# 4. Authentication Flow

This section is the most important part of this screen.

You currently have:

```text
☑ Standard flow
☐ Direct access grants
☐ Implicit flow
☐ Service account roles
☐ Standard Token Exchange
☐ JWT Authorization Grant
☐ OAuth 2.0 Device Authorization Grant
☐ OIDC CIBA Grant
```

Each checkbox corresponds to a different OAuth/OIDC capability.

---

# 5. Standard flow

You currently have:

```text
☑ Standard flow
```

This means:

> Allow this client to use the **Authorization Code Flow**.

This is the normal modern browser login flow.

The simplified process is:

```text
Browser
   │
   │  Authorization request
   ▼
Keycloak
   │
   │ User logs in
   ▼
Authorization Code
   │
   ▼
Application
   │
   │ code + authentication
   ▼
Keycloak Token Endpoint
   │
   ▼
Access Token
Refresh Token
ID Token
```

For example:

```text
https://keycloak.example.com/realms/myrealm/
protocol/openid-connect/auth
```

The browser receives:

```text
?code=abc123
```

Then the application exchanges:

```text
code=abc123
```

for tokens.

Keycloak documents Authorization Code as its standard authorization-code flow and recommends it for web applications and native applications where a user agent can be used. ([Keycloak][3])

---

## Why Standard Flow is normally preferred

Because the sensitive access token isn't sent directly through the browser authorization response.

Instead:

```text
Browser
   ↓
authorization code
   ↓
Backend
   ↓
token endpoint
   ↓
tokens
```

With PKCE, the authorization-code flow becomes even safer for public clients.

For modern applications:

```text
Authorization Code + PKCE
```

is generally the configuration you should learn first.

### Your FastAPI application

Usually:

```text
Standard flow: ✅
```

---

# 6. Direct access grants

Your screenshot:

```text
☐ Direct access grants
```

This enables the **Resource Owner Password Credentials** flow.

You may see requests like:

```http
POST /realms/myrealm/protocol/openid-connect/token
```

with:

```text
grant_type=password
client_id=myclient
username=bhargav
password=******
```

The application directly receives the user's username/password and gives them to Keycloak.

Conceptually:

```text
User
 ↓
Application
 ↓ username/password
Keycloak
 ↓
Access Token
```

This is fundamentally different from the normal redirect-based login:

```text
User
 ↓
Application
 ↓
Keycloak login page
 ↓
Authentication
 ↓
Application
```

---

## Why this is generally a bad choice

The application gets the user's password.

That means:

```text
User password
      ↓
Your application
      ↓
Keycloak
```

instead of:

```text
User password
      ↓
Keycloak only
```

Current Keycloak documentation says Direct Grant / Resource Owner Password Credentials should not be used under current OAuth 2.0 security best practices, and recommends alternatives such as Authorization Code or Device Authorization Grant. ([Keycloak][4])

### For your FastAPI project

```text
Direct access grants: ❌
```

Keep it disabled unless you specifically need to experiment with the legacy flow.

---

# 7. Implicit flow

Your screenshot:

```text
☐ Implicit flow
```

This is the old **OAuth/OIDC Implicit Flow**.

Instead of:

```text
Authorization request
       ↓
Authorization Code
       ↓
Token endpoint
       ↓
Access Token
```

the token is returned directly from the authorization endpoint.

Conceptually:

```text
Browser
   ↓
Keycloak
   ↓
Access Token
```

There is no authorization-code exchange.

---

## Why it's generally discouraged

The access token can be exposed through browser-facing mechanisms such as the URL fragment, creating additional leakage/replay risks.

Keycloak's documentation notes that implicit flow is removed from the future OAuth 2.1 specification and describes security concerns around exposing tokens in the browser response. ([Keycloak][5])

Modern applications should normally use:

```text
Authorization Code + PKCE
```

instead.

### For your FastAPI project

```text
Implicit flow: ❌
```

---

# 8. Service account roles

Your screenshot:

```text
☐ Service account roles
```

This is extremely important for backend-to-backend authentication.

Enabling it allows the client to have a **service account**.

Think:

```text
FastAPI
   │
   │ "I am service X"
   ▼
Keycloak
   │
   ▼
Access Token
```

No human user is required.

For example:

```text
Client:
    payment-service

Service account:
    service-account-payment-service

Roles:
    payment.read
    payment.write
```

The application uses client credentials to obtain a token representing **the application/service itself**.

Keycloak explicitly describes this as enabling support for the OAuth 2.0 **Client Credentials Grant**. ([Keycloak][1])

---

## User token vs service account token

This distinction is fundamental.

### User authentication

```text
User
 ↓
Keycloak
 ↓
Access Token
 ↓
FastAPI
```

The token represents something like:

```text
User = Bhargav
```

---

### Service authentication

```text
FastAPI
 ↓
Keycloak
 ↓
Access Token
```

The token represents:

```text
Client = payment-service
```

There is no human user.

---

### When should you enable it?

For:

```text
FastAPI → another API
background worker → API
microservice → microservice
scheduled job → API
```

potentially yes.

For a normal user-login client:

```text
Service account roles: ❌
```

unless that same client genuinely needs service credentials.

---

# 9. Standard Token Exchange

Your screenshot:

```text
☐ Standard Token Exchange
```

Token Exchange allows an application to take one token and ask Keycloak for another token representing a different context/delegation.

Conceptually:

```text
Token A
   ↓
Keycloak
   ↓
Token B
```

For example, imagine:

```text
Frontend
   ↓
User Access Token
   ↓
API Gateway
   ↓
Service A
```

Service A may need to obtain a token appropriate for another service.

Token exchange supports these kinds of delegation/impersonation/token-substitution scenarios.

Keycloak's current documentation identifies Standard Token Exchange as a client capability that allows the client to use standard token exchange. ([Keycloak][1])

---

## Why you probably shouldn't enable it initially

It is an advanced capability.

First learn:

```text
Authorization Code
PKCE
Access Tokens
Refresh Tokens
Client Credentials
Roles
Scopes
```

Then learn token exchange.

---

# 10. JWT Authorization Grant

Your screenshot shows:

```text
☐ JWT Authorization Grant
```

This is a more advanced OAuth capability.

Instead of the client presenting a traditional username/password or simply another OAuth token, it can present a **signed JWT assertion** to Keycloak.

Conceptually:

```text
External Identity System
        ↓
   Signed JWT
        ↓
      Keycloak
        ↓
 Access Token
```

Example:

```text
External JWT
{
   "iss": "...",
   "sub": "...",
   "aud": "...",
   ...
}
        ↓
Keycloak validates it
        ↓
Keycloak issues access token
```

Current Keycloak versions support JWT Authorization Grant based on RFC 7523, including use cases involving externally signed JWT assertions requesting OAuth access tokens. ([Keycloak][6])

This is especially interesting in:

```text
multi-organization systems
federated systems
cross-domain authentication
service integrations
```

### For your current learning stage

```text
JWT Authorization Grant: ❌
```

Learn it later.

---

# 11. OAuth 2.0 Device Authorization Grant

Your screenshot:

```text
☐ OAuth 2.0 Device Authorization Grant
```

This is the **Device Code Flow**.

It is designed for devices where typing credentials or using a normal browser is inconvenient.

Examples:

```text
Smart TV
Game console
CLI
IoT device
```

Imagine a CLI application:

```bash
myapp login
```

It could display:

```text
Go to:
https://example.com/device

Enter code:
ABCD-EFGH
```

You open the URL on your phone/laptop:

```text
Phone
  ↓
Keycloak
  ↓
Login
  ↓
Approve
```

Meanwhile:

```text
CLI
 ↓
poll Keycloak
 ↓
authorization completed
 ↓
Access Token
```

Keycloak documents the Device Authorization Grant specifically for devices with limited input capability or no suitable browser. ([Keycloak][3])

---

# 12. OIDC CIBA Grant

Your screenshot:

```text
☐ OIDC CIBA Grant
```

CIBA means:

**Client Initiated Backchannel Authentication**

This is quite different from normal browser authentication.

Normal OIDC:

```text
Client
 ↓
Browser
 ↓
Keycloak
 ↓
User login
```

CIBA can work more like:

```text
Client
 ↓
Keycloak
 ↓
"Authenticate user somehow"
 ↓
User's authentication device
 ↓
User approves
 ↓
Keycloak
 ↓
Token delivered to client
```

The client does not necessarily need to redirect the user through a browser session.

This is useful for specialized high-assurance authentication scenarios, banking-style flows, decoupled devices, etc.

Keycloak documents CIBA as the **OpenID Connect Client Initiated Backchannel Authentication Grant**. ([Keycloak][1])

### For your FastAPI learning project

```text
OIDC CIBA: ❌
```

This is very advanced.

---

# 13. Require PKCE

Your screenshot:

```text
Require PKCE   ⚠️   [OFF]
```

This is one of the most important settings.

PKCE means:

**Proof Key for Code Exchange**

It protects the Authorization Code flow against authorization-code interception.

Without PKCE:

```text
Application → Keycloak
              ↓
         authorization code
              ↓
         Application
              ↓
          token request
```

With PKCE:

```text
Client generates:

code_verifier
     ↓
code_challenge = hash(code_verifier)

              ↓

Keycloak stores challenge

              ↓

Authorization Code

              ↓

Client sends:

authorization_code
+
code_verifier

              ↓

Keycloak verifies them

              ↓

Tokens
```

So stealing only the authorization code isn't enough.

Keycloak's documentation specifically describes PKCE as protection against an attacker stealing an authorization code and redeeming it for the legitimate client's tokens. ([Keycloak][1])

---

## Why is it currently OFF?

Because this screen is asking whether PKCE must be required.

There is an important distinction:

```text
Require PKCE = OFF
```

does **not necessarily mean PKCE cannot be used**.

It means the client isn't forced to use it.

A client may still send PKCE parameters.

Keycloak documents this behavior: when no PKCE method is required, Keycloak doesn't enforce PKCE unless the client sends the appropriate PKCE parameters. ([Keycloak][1])

---

## For public clients

For something like:

```text
React SPA
Mobile app
Desktop app
```

you generally want:

```text
Require PKCE: ✅
```

Usually:

```text
S256
```

rather than the weaker plain method.

---

## For your FastAPI backend

If your FastAPI app is a **confidential client**, PKCE isn't the primary protection because the backend can authenticate itself.

But using Authorization Code + PKCE can still be valuable, and modern security architectures frequently adopt PKCE broadly.

For your practical learning, I recommend learning:

```text
Standard Flow ✅
Require PKCE ✅
```

especially for public-client scenarios.

---

# 14. Require DPoP bound

Your screenshot:

```text
Require DPoP bound     [OFF]
```

DPoP means:

**Demonstrating Proof-of-Possession**

This protects against stolen access-token replay.

Normally OAuth access tokens are **Bearer tokens**:

```text
Authorization: Bearer eyJ...
```

That means:

> Whoever possesses the token can potentially use it.

So:

```text
Legitimate client
     ↓
Access Token
     ↓
Attacker steals token
     ↓
Attacker sends token
     ↓
API
```

The API may accept it.

---

## DPoP changes this

The token becomes bound to a cryptographic key.

Conceptually:

```text
Client
 ├── private key
 └── public key
```

Keycloak associates the token with that key.

Then the client must prove possession of the private key when making requests.

So:

```text
Attacker steals token
        ↓
Tries using it
        ↓
❌ Doesn't have private key
        ↓
Request rejected
```

Keycloak describes DPoP as a mechanism for making tokens sender-constrained and reducing the usefulness of stolen tokens. ([Keycloak][7])

---

## DPoP vs PKCE

These solve **different attacks**.

### PKCE protects the authorization-code exchange

```text
Authorization Code
       ↓
PKCE
       ↓
Prevents attacker from redeeming stolen code
```

### DPoP protects tokens from replay

```text
Access Token
       ↓
DPoP
       ↓
Makes stolen token harder to reuse
```

A useful mental model:

```text
PKCE
   ↓
"Don't let someone steal my authorization code and exchange it."

DPoP
   ↓
"Don't let someone who steals my access token use it."
```

Keycloak also notes that DPoP is not supported with implicit/hybrid front-channel token flows. ([Keycloak][7])

---

# 15. Why are some options greyed out?

This is something important to notice in your screenshot.

You have:

```text
Service account roles
Standard Token Exchange
JWT Authorization Grant
OIDC CIBA
```

shown greyed/disabled.

This generally means the current combination of client capabilities/client type doesn't allow those options in the current state.

For example, capabilities can depend on whether:

```text
Client authentication
```

is enabled.

This is intentional.

Keycloak doesn't present all possible OAuth capabilities as independently usable checkboxes in every client configuration.

---

# 16. Putting the entire screen together

Think of the screen as:

```text
                    KEYCLOAK CLIENT
                          │
          ┌───────────────┴───────────────┐
          │                               │
   Who can authenticate?          Which protocols/flows?
          │                               │
          ▼                               ▼
 Client authentication          Standard Flow
          │                       Direct Grant
          │                       Implicit
          │                       Device Grant
          │                       CIBA
          │                       Token Exchange
          │                       JWT Grant
          │
          ▼
 Public / Confidential
```

And then:

```text
Security enhancements
        │
        ├── Require PKCE
        │
        └── Require DPoP
```

---

# 17. What I recommend for your FastAPI learning project

Since you're learning this specifically with **FastAPI + Keycloak**, don't enable everything.

Start with a simple confidential OIDC client:

```text
Client authentication:        ON
Authorization:                OFF

Standard flow:                ON
Direct access grants:         OFF
Implicit flow:                OFF
Service account roles:        OFF
Standard Token Exchange:      OFF
JWT Authorization Grant:      OFF
Device Authorization Grant:  OFF
OIDC CIBA:                    OFF

Require PKCE:                 ON* 
Require DPoP bound:           OFF*
```

The `*` depends on which exact FastAPI architecture you're building.

For a **server-side FastAPI application performing the user login**, we'll configure the client differently from a **React SPA calling FastAPI**.

---

# 18. The most important distinction to memorize

Don't memorize these as a random list of Keycloak checkboxes.

Group them by purpose:

### User login

```text
Standard Flow
```

Usually:

```text
Authorization Code
        +
PKCE
```

---

### Legacy user/password login

```text
Direct Access Grants
```

Generally avoid.

---

### Old token-in-browser approach

```text
Implicit Flow
```

Generally avoid.

---

### Machine-to-machine

```text
Service Account Roles
```

which corresponds to:

```text
Client Credentials
```

---

### Device login

```text
Device Authorization Grant
```

For:

```text
CLI
TV
IoT
limited-input devices
```

---

### Advanced token/delegation mechanisms

```text
Standard Token Exchange
JWT Authorization Grant
OIDC CIBA
```

---

### Stronger protection

```text
PKCE
DPoP
```

---

# 19. One picture to tie it together

Imagine your AI SaaS:

```text
                    ┌───────────────┐
                    │    Keycloak   │
                    └───────┬───────┘
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
          React          FastAPI        Worker
          Client          Client         Client
             │              │              │
             │              │              │
       Standard Flow   Standard Flow   Service Account
             │              │              │
            PKCE           PKCE        Client Credentials
             │              │
             └──────┬───────┘
                    ▼
              Access Token
                    │
                    ▼
                 FastAPI
                    │
              ┌─────┴─────┐
              ▼           ▼
            User        Roles
           identity    permissions
```

Then later you can add:

```text
Device Flow
      ↓
CLI

Token Exchange
      ↓
Service delegation

JWT Authorization Grant
      ↓
External JWT → Keycloak

CIBA
      ↓
Backchannel authentication

DPoP
      ↓
Sender-constrained tokens
```

That is the mental model I'd use while going through your Keycloak practical tutorial. ([Keycloak][1])

For your next step, the most useful thing is to take **this exact screen** and build two clients together: **(1) a React/public client and (2) a FastAPI/confidential client**, then test every flow with actual HTTP requests so you can see exactly what each checkbox changes.

[1]: https://www.keycloak.org/docs/latest/server_admin/?utm_source=chatgpt.com "Server Administration Guide"
[2]: https://www.keycloak.org/docs/latest/authorization_services/?utm_source=chatgpt.com "Authorization Services Guide"
[3]: https://www.keycloak.org/docs/25.0.6/securing_apps/index.html?utm_source=chatgpt.com "Securing Applications and Services Guide"
[4]: https://www.keycloak.org/securing-apps/oidc-layers?utm_source=chatgpt.com "Securing applications and services with OpenID Connect - Keycloak"
[5]: https://www.keycloak.org/docs/24.0.5/securing_apps/?utm_source=chatgpt.com "Securing Applications and Services Guide"
[6]: https://www.keycloak.org/docs/latest/release_notes/?utm_source=chatgpt.com "Release Notes"
[7]: https://www.keycloak.org/securing-apps/dpop?utm_source=chatgpt.com "Securing applications with Demonstrating Proof-of-Possession (DPoP) - Keycloak"

