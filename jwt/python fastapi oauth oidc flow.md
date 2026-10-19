# OAuth 2.0 and OpenID Connect, explained from scratch

We'll use your exact stack throughout the explanation:

Frontend — Streamlit

Login button, user interface, browser interaction

Backend — Python FastAPI

Protects APIs, validates tokens or sessions, enforces permissions

Postgres

Users, tenant memberships, permissions, audit records, optionally durable sessions

Redis

Short-lived sessions, caches, temporary authentication state, revocation checks

Identity provider options: Google directly, Keycloak, or AD FS (Active Directory Federation Services).

The central idea is that logging someone in, giving them permission to use your API, and remembering that they are logged in are three different jobs. OAuth, OpenID Connect, and your application’s own session management help accomplish different parts of these jobs.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+2



## 1. First, understand the main characters

Imagine your application is an office building.

| Technical term          | Office-building analogy                                              | In your system                                   |
| ----------------------- | -------------------------------------------------------------------- | ------------------------------------------------ |
| User                    | Employee                                                             | Person using the Streamlit app                   |
| Client                  | Receptionist requesting identity information                         | Streamlit/backend login integration              |
| Identity Provider (IdP) | Organization that confirms an employee's identity                    | Google, Keycloak, or AD FS                       |
| Authorization Server    | Authority that issues access credentials                             | Google, Keycloak, or AD FS                       |
| Resource Server         | Locked department that protects its own resources                    | Your FastAPI API                                 |
| Access token            | Temporary access badge for a specific area                           | Credential presented to FastAPI                  |
| ID token                | A signed statement identifying the employee                          | Used by the OIDC client to verify who logged in  |
| Refresh token           | Credential used to obtain a new access badge                         | Sent to the token endpoint, not to your API      |
| Session cookie          | A secure claim ticket that lets the receptionist remember your visit | Browser-to-application session                   |
| Postgres                | Official employee and application records                            | User profiles, memberships, roles, business data |
| Redis                   | A fast desk for temporary records                                    | Session cache or short-lived state               |

One important nuance: the client and resource server can be separate components of the same application, and Google, Keycloak, or AD FS can act as both the identity provider and authorization server. These are roles, not necessarily separate physical machines.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://openid.net\&sz=32)

OpenID Foundation

+2



## 2. OAuth 2.0 versus OpenID Connect

These are related, but they solve different problems.

## OAuth 2.0

The permission question: “Is this application allowed to access this protected resource?”

For example, can a client call your FastAPI endpoint to read a specific customer's documents?

## OpenID Connect (OIDC)

The identity question: “Who signed in?”

For example, Google issues an ID token identifying the signed-in Google account to your registered application.

OAuth 2.0 is an authorization framework. OpenID Connect adds an identity layer, including the ID token, on top of OAuth 2.0. When you select “Sign in with Google,” the intended login protocol is OIDC, even though the underlying flow also uses OAuth 2.0 mechanisms.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



That distinction matters because a valid ID token is not automatically a suitable credential for calling your FastAPI API. Your API should validate an access token intended for that API, or validate your own application's session cookie.

## 3. The four credentials you must never confuse

Before walking through the full process, learn these four objects. Most OAuth confusion disappears once you can distinguish them.

1\. ID token

Purpose: establish the user's identity.

Example claims: `sub`, `email`, `iss`, `aud`, `exp`.

Think: “Google says this person is account 123.”

2\. Access token

Purpose: authorize requests to a particular resource server.

Example claims: `iss`, `aud`, `exp`, `scope`, or roles.

Think: “This credential allows the holder to call these API endpoints.”

3\. Refresh token

Purpose: obtain new tokens from the identity provider's token endpoint.

Usually a long, opaque credential, though implementations differ.

Think: “I can ask the token issuer for a new access badge without making the user sign in again.”

4\. Application session cookie

Purpose: let your own application remember the signed-in user.

It can contain an opaque session identifier or, in some designs, signed session data.

Think: “This application already knows me.”

An authorization code is a fifth object, but it is temporary: it is exchanged for tokens during login and should not be reused.

An ID token and an access token may both look like JWTs, with three dot-separated parts:

```
xxxxx.yyyyy.zzzzz
```

That appearance does not make them interchangeable. The recipient and intended purpose matter more than their format. Access tokens can also be opaque rather than JWTs.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://openid.net\&sz=32)

OpenID Foundation

+2



### A small but important example

Imagine Google issues these example claims to your Streamlit login client:

```
{
  "iss": "https://accounts.google.com",
  "sub": "google-user-123",
  "aud": "streamlit-client-id",
  "email": "alex@example.com",
  "exp": 1900000000
}
```

This is an illustrative ID token payload, not a real credential.

- `iss` identifies who issued it.
- `sub` is the stable identifier Google assigned to this account.
- `aud` says which application the token is intended for.
- `exp` says when it expires.

Notice `aud` is `streamlit-client-id`, not your FastAPI API. This is why a Google ID token should not automatically become your API's access token.

Google specifically recommends using `sub`, rather than email, as the stable unique identifier for a Google account. Email addresses can change.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



## 4. Who does what in your stack?

Let's assign the roles precisely.

| Component          | Responsibility                                                                     |
| ------------------ | ---------------------------------------------------------------------------------- |
| Streamlit          | OIDC client / relying party for login; renders the UI                              |
| Google             | Identity provider and token issuer for the Google login flow                       |
| FastAPI            | Resource server for your protected business APIs                                   |
| Postgres           | Your application's durable records and authorization data                          |
| Redis              | Optional fast storage for temporary state, session data, and caches                |
| Browser            | Holds browser cookies and follows authentication redirects                         |
| OAuth/OIDC library | Handles protocol operations such as redirects, code exchange, and token validation |

Your FastAPI middleware or authentication dependency acts as the gatekeeper for requests. It does not magically create authentication by existing. It needs a defined credential to inspect, a validation strategy, and a policy for deciding whether to allow each operation.

Also, if FastAPI calls Google Drive or another Google API on a user's behalf, that Google API is another resource server. In your own application, FastAPI is the resource server for your own endpoints.

# Part I — Sign in with Google directly

## 5. The recommended way to start with Streamlit

For the Google-login use case, distinguish two possible requirements:

Requirement A: “I only need to know which user signed in.”

Streamlit already has built-in OIDC authentication through `st.login()`, `st.user`, and `st.logout()`. It redirects the user to the identity provider, maintains its own identity cookie, and exposes the user's identity to your Streamlit code. It is an authentication feature, not a complete token-management solution for a separate API.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.streamlit.io\&sz=32)

Streamlit Docs

+1



Requirement B: “I need a separately secured FastAPI API that receives per-user access tokens.”

You must additionally design how API calls will be authenticated. That might use an application-issued API token, or an access token issued by an identity provider and specifically intended for FastAPI.

For your exact stack, a good starting architecture is:

1\. Browser

Streamlit UI and its login cookie

2\. Streamlit Python server

Knows the authenticated user; calls FastAPI server-to-server

3\. FastAPI

Validates trusted API credentials and checks the user's permissions

The arrows represent separate authenticated interactions. A user profile is not, by itself, an API credential.

Here, the browser normally interacts with the Streamlit server, and Python code running on that server makes the HTTP request to FastAPI. The browser does not automatically forward its Streamlit authentication identity cookie to every HTTP service that Streamlit calls.

That distinction is especially important with Streamlit because its Python code executes on the server rather than directly in the browser like the code of a typical JavaScript single-page application.

## 6. Step 1: Register your application with Google

Open the Google Cloud Console and create or select a project.

Create an OAuth client appropriate for a server-side web application. Configure your redirect URI, for example:

```
https://app.example.com/oauth2callback
```

For local development, it could be:

```
http://localhost:8501/oauth2callback
```

Use HTTPS in production. The redirect URI must match the value registered with Google.

You will receive:

```
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
```

The client ID identifies your application. It is not a password and is generally safe to disclose. The client secret is confidential and must remain on the server.

Configure the OpenID Connect metadata URL:

```
https://accounts.google.com/.well-known/openid-configuration
```

That discovery document identifies Google's authorization endpoint, token endpoint, public signing keys, and other protocol metadata. Your implementation should use a maintained OIDC library instead of hard-coding all the protocol mechanics yourself.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



A minimal Streamlit configuration for login looks like this:

```
# .streamlit/secrets.toml

[auth]
redirect_uri = "https://app.example.com/oauth2callback"
cookie_secret = "REPLACE_WITH_A_STRONG_RANDOM_SECRET"
client_id = "YOUR_GOOGLE_CLIENT_ID"
client_secret = "YOUR_GOOGLE_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Treat `cookie_secret` as a separate application secret. It is not your Google client secret and not a user token.

In production, provide these values through your secrets manager or secure runtime configuration. Do not commit a real `secrets.toml` to Git.

## 7. Step 2: The user clicks “Sign in with Google”

Your Streamlit application can offer a button that initiates login:

```
import streamlit as stif not st.user.is_logged_in:    if st.button("Sign in with Google"):        st.login()else:    st.write(f"Welcome, {st.user.name}")
```

This is a simplified usage example, not a complete application security implementation.

Conceptually, the browser is redirected from your application to Google's authorization endpoint.

The OIDC client creates the authorization request with information such as:

```
client_id=YOUR_CLIENT_ID
response_type=code
scope=openid email profile
redirect_uri=https://app.example.com/oauth2callback
state=RANDOM_TRANSACTION_VALUE
nonce=RANDOM_LOGIN_VALUE
```

For an authorization-code flow using PKCE, the request also contains a code challenge.

Each value has a purpose:

- `client_id`: identifies the application.
- `response_type=code`: requests an authorization code.
- `scope=openid`: indicates that this is an OIDC login request.
- `email profile`: requests permitted user information.
- `redirect_uri`: identifies the registered callback.
- `state`: protects the authorization transaction against request-forgery attacks.
- `nonce`: binds an ID token to the login transaction and helps prevent replay.

A maintained library generates and checks the appropriate transaction values.

## 8. Step 3: Google authenticates the person

The user now sees Google's sign-in page, or Google may recognize an existing Google session.

Google handles the password, passkey, MFA, and other applicable authentication steps. Your application should never collect the user's Google password.

After successful authentication and any required consent, Google redirects the browser to the registered callback, with a one-time authorization code and the original state value.

Conceptually:

```
GET /oauth2callback?code=ONE_TIME_CODE&state=...
```

The application compares the returned `state` with the original value. An unexpected value means the login transaction must be rejected.

The code is not the access token, and it is not the ID token. It is a short-lived, one-time credential for the next step.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



## 9. Step 4: Exchange the authorization code for tokens

The server-side OIDC client sends an HTTPS request directly to Google's token endpoint.

Conceptually, the request contains:

```
grant_type=authorization_code
code=ONE_TIME_CODE
client_id=YOUR_CLIENT_ID
client_secret=YOUR_CLIENT_SECRET
redirect_uri=https://app.example.com/oauth2callback
```

If PKCE was used, it also supplies the original `code_verifier`.

Google validates the request and may return an ID token and an access token. A refresh token is optional and depends on the flow and requested access.

For a typical server-side login with Google, this is a back-channel exchange: the application server calls Google rather than asking the user to send the client secret or refresh token. The authorization code initially travels through the browser, but the token exchange takes place over HTTPS between servers.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



## 10. Step 5: What happens to the returned tokens?

There are two different needs.

### Need A: Sign-in only

Your application validates the ID token and establishes the user's logged-in application session.

Using Streamlit's built-in authentication, Streamlit manages its identity cookie and exposes verified user information through `st.user`. It is not necessary for your application to retain Google's access and refresh tokens just to display the user's name or recognize their login. Streamlit documents this cookie lifecycle separately from token lifetimes.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://docs.streamlit.io\&sz=32)

Streamlit Docs

+1



### Need B: Access Google APIs

Suppose later your application also needs to read a user's Google Drive files. Now you need the appropriate Google API scopes and a Google API access token.

To request offline API access, Google's OAuth flow uses `access_type=offline`. Google documents that refresh-token issuance is conditional and that refresh tokens must be stored safely; a refresh token is not guaranteed to accompany every code exchange.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+1



Do not assume that the Google access token from a login flow is your FastAPI access token. It is normally intended for the Google resources that the requested scopes authorize.

## 11. How to secure FastAPI in the Google-direct design

This is the part that requires an explicit architectural decision.

### Recommended basic design: use application authentication for your own API

When the user is logged in and performs an action in Streamlit, the Streamlit Python server makes an authenticated request to FastAPI.

For example:

```
Streamlit server  ── HTTPS request ──►  FastAPI
```

For FastAPI to trust the request, establish one of these approaches:

- Use a trusted internal service identity, such as mTLS, together with securely established user context.
- Issue a short-lived, signed application token containing the authenticated user's stable identity and the intended API audience.
- Use a shared server-side session store with an authenticated session reference, if the services are designed around that model.

For a signed internal token, claims could conceptually resemble:

```
{
  "iss": "your-application-auth-service",
  "sub": "internal-user-123",
  "aud": "fastapi-api",
  "exp": 1900000300
}
```

This is an illustrative application-issued token, not a Google token.

The trusted server-side component signs it after the user's identity has been established. FastAPI verifies the signature and claims, then loads the user's actual roles and permissions from the application's trusted records.

Do not simply send `X-User-Email: alex@example.com` from a client and trust it. A caller could change that value. User identity must come from a verified authentication context, not from arbitrary request data.

### What does the first FastAPI request look like?

Suppose the user clicks a button in Streamlit to retrieve a report.

1. Streamlit executes the Python code associated with the action.
2. It obtains the authenticated user context from its established login session.
3. The trusted server-side component prepares the API credential or session reference.
4. Streamlit's server calls the FastAPI endpoint over an authenticated connection.
5. FastAPI validates the credential.
6. FastAPI checks whether the user can access that particular report.
7. If permitted, FastAPI retrieves the data from Postgres or another trusted service and returns the result.

The flow is:

```
User
  │ clicks a Streamlit button
  ▼
Streamlit Python server
  │ attaches trusted API credentials
  ▼
FastAPI authentication
  │ verifies issuer/signature/expiry/audience
  ▼
FastAPI authorization
  │ checks user + permissions
  ▼
Postgres / business service
```

Authentication answers, “Who is making the request?” Authorization answers, “Can that user perform this action?”

### What about every future request?

The same process occurs for each protected request. FastAPI does not have to revisit Google just because another request arrives.

If the application uses a signed, short-lived API token, FastAPI can usually verify its signature locally and check its claims. If it uses a server-side session identifier, FastAPI or a trusted session service may look up the corresponding session in Redis.

With this recommended Google-login architecture, Google's login tokens and your internal API credentials remain separate. You create or validate the internal credential for your own API; you do not treat every Google login token as a generic enterprise API credential.

# Part II — Token validation, PKCE, signing keys, and storage

## 12. How does FastAPI verify a token?

Imagine someone presents a badge to the security desk. The guard does not merely check that the badge looks like a badge. The guard checks whether it was issued by a trusted authority, whether it is still valid, and whether it permits access to this particular area.

API token validation follows the same idea.

### When the access token is a signed JWT

A correctly implemented JWT validation process typically checks:

| Check               | What it proves                                                                 |
| ------------------- | ------------------------------------------------------------------------------ |
| Signature           | The token was signed by a trusted issuer and has not been altered              |
| `iss`               | The issuer is the expected identity provider or application                    |
| `aud`               | The token is intended for this API                                             |
| `exp`               | The token has not expired                                                      |
| `nbf`, when present | The token is not being used before its valid-from time                         |
| Scope/roles         | The token provides the relevant permission claims                              |
| Additional policy   | The user, tenant, account status, or resource permissions permit the operation |

FastAPI should reject requests with missing, malformed, invalid, or expired credentials. It should also reject valid tokens whose audience or privileges do not match the endpoint.

Decoding a JWT is not validating it. Anyone can base64url-decode a JWT payload and read its claims. Signature verification and claim checks are what establish trust.

### Does FastAPI have to ask Google whether every token is valid?

Usually, no—not for a signed JWT that your API is configured to validate locally.

The identity provider publishes public signing keys. FastAPI obtains and caches these keys, then verifies the token's signature and claims on each request. It generally does not contact the identity provider on every API call.

This is possible because a valid digital signature lets the API check token authenticity without possessing the issuer's private signing key.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developers.google.com\&sz=32)

Google for Developers

+2



There are two qualifications:

- Some access tokens are opaque rather than JWTs. Their validity may need to be checked through the issuer's token-introspection endpoint, possibly with suitable caching.
- Local JWT validation does not automatically detect every revocation immediately. A token may remain cryptographically valid until expiry unless the architecture adds revocation or session-state checks.

## 13. How public and private keys work

This is one of the most important security concepts.

Imagine Google, Keycloak, or AD FS wants to issue a tamper-resistant token.

Identity provider — private key

The issuer signs the token using its private signing key. That key must remain secret.

Publishes the matching public key through JWKS

FastAPI — public key

FastAPI uses the public key to verify the signature. It does not need the issuer's private key.

JWKS means JSON Web Key Set. It is a document containing public keys and identifiers that help a verifier select the appropriate key.

In a JWT signed using an asymmetric algorithm such as RS256:

1. The issuer constructs the token.
2. The issuer signs it using its private key.
3. The token is sent to the application.
4. FastAPI obtains the appropriate trusted public key.
5. FastAPI verifies the signature.
6. FastAPI checks `iss`, `aud`, expiration and required permissions.

An attacker who edits the payload and keeps the original signature will not be able to produce a valid signature for the edited token.

For Keycloak, for example, the realm's public keys are available through an endpoint such as:

```
/realms/your-realm/protocol/openid-connect/certs
```

Google publishes signing-key information through its OIDC discovery metadata. AD FS also publishes metadata and signing certificates/keys.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.keycloak.org\&sz=32)

Keycloak

+2



### There are two different key pairs to understand

Do not confuse the token-signing keys with the credentials your application uses to authenticate to the token endpoint.

| Mechanism                                                      | What it is used for                                                    |
| -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Issuer's private/public signing key                            | Signs tokens and lets APIs verify them                                 |
| OAuth client secret                                            | Authenticates a confidential application to the token endpoint         |
| Client private key, when using key-based client authentication | Can let the client prove its identity by signing a client assertion    |
| TLS certificate and private key                                | Secure the HTTPS connection and authenticate the relevant TLS endpoint |

These mechanisms can coexist, but they do different jobs. An API generally does not use your Google client secret to verify Google's RS256 token signature.

## 14. How PKCE and the code verifier work

PKCE stands for Proof Key for Code Exchange. It protects the authorization-code exchange from an attacker who manages to steal or intercept the authorization code.

Think of the authorization code as a numbered ticket. PKCE ensures that merely stealing the ticket is not enough to exchange it for tokens.

### The steps

Step 1 — The client creates a secret verifier.

For every login transaction, the client creates a fresh, high-entropy random string:

```
code_verifier = RANDOM_SECRET_FOR_THIS_LOGIN
```

This should not be a hard-coded constant.

Step 2 — The client derives a challenge.

With the recommended S256 method, it effectively computes:

```
code_challenge =
    BASE64URL(SHA256(code_verifier))
```

The client saves the original verifier in its protected, short-lived login transaction state.

Step 3 — The client sends only the challenge initially.

The authorization request includes:

```
code_challenge=...
code_challenge_method=S256
```

The identity provider remembers the challenge alongside that authorization transaction.

Step 4 — The user authenticates and receives a code.

The code comes back through the registered redirect URI. An attacker might manage to obtain that code.

Step 5 — The legitimate client exchanges the code.

At the token endpoint, the client supplies the original `code_verifier`.

The identity provider hashes it and compares the result to the stored challenge. If the values match, it can establish that the token request possesses the verifier associated with the original authorization request.

If the attacker stole only the authorization code, they would not know the verifier and could not successfully complete the exchange.

PKCE is not a replacement for HTTPS, exact redirect URI matching, `state`, or secure token storage. It adds protection against authorization-code interception. Current OAuth security guidance recommends PKCE for confidential clients as well as requiring it for public clients.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.rfc-editor.org\&sz=32)

RFC Editor

+1



## 15. What `state` and `nonce` do—and how they differ from PKCE

These three values protect different parts of the login transaction.

| Value         | Purpose                                                              | What is compared?                                     |
| ------------- | -------------------------------------------------------------------- | ----------------------------------------------------- |
| `state`       | Protects the authorization flow against request forgery              | Returned state against the original transaction state |
| `nonce`       | Binds the ID token to the login transaction and helps prevent replay | ID token's nonce claim against the original nonce     |
| PKCE verifier | Protects authorization-code redemption                               | Hash of the verifier against the original challenge   |

These values are all associated with the specific login transaction. They should not be static values reused for every user or every login.

## 16. What happens when an access token expires?

Suppose an access token expires at 12:05.

At 12:06, your application sends a protected API request with that old token.

```
Streamlit → FastAPI
            expired access token
                 │
                 ▼
            Token rejected
                 │
                 ▼
          Client refreshes token
                 │
                 ▼
        Identity provider token endpoint
                 │
                 ▼
         New access token returned
                 │
                 ▼
       Retry request as appropriate
```

The API should reject the expired token. The trusted token-handling component can then use its refresh token at the identity provider's token endpoint to request a fresh access token.

For example, the request uses the `refresh_token` grant type:

```
grant_type=refresh_token
refresh_token=SERVER_STORED_REFRESH_TOKEN
```

A confidential client also authenticates itself to the issuer as required.

The provider may issue a new access token and may also issue a replacement refresh token. When the provider rotates refresh tokens, the client must replace the old token safely and handle concurrent refresh operations correctly.

The refresh token is not sent to the FastAPI business endpoint. It is used only with the token issuer's token endpoint.

### Does the user have to sign in again?

Usually not, as long as the refresh token is still valid and permitted for use.

If the refresh token is expired, revoked, invalid, or no longer permitted, refresh fails. Your application then needs to initiate a new login flow.

### Does every request go back to Google?

No. There are three separate operations:

| Operation                                                      | Must contact Google each time?                 |
| -------------------------------------------------------------- | ---------------------------------------------- |
| Verify a cached-signing-key JWT locally                        | Usually no                                     |
| Validate a session using your own Redis/Postgres session store | No Google call is required                     |
| Exchange or refresh tokens                                     | Yes, contact the token issuer's token endpoint |

A refresh request happens when needed, not on every business API request. If the API accepts opaque access tokens and introspects each one, it might contact the issuer or an intermediary more often.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.rfc-editor.org\&sz=32)

RFC Editor

+2



## 17. Where are details, secrets, and tokens stored?

This is not one database. Different information belongs in different places.

Browser

Normally stores an application session cookie. It should not need a Google refresh token or your client secret.

Postgres

Durable user records, internal user IDs, issuer/subject mappings, tenant memberships, roles, permissions and audit records. Encrypted provider refresh tokens can be stored here if genuinely required.

Redis

Short-lived login state, pending PKCE verifiers, temporary session records, cached access tokens and token-validation metadata. Apply explicit TTLs to temporary entries.

Secret manager / KMS

OAuth client secrets, cookie-signing secrets, your application's private signing keys, and encryption keys used to protect other secrets.

Identity provider

Owns user authentication and the provider-side grant/token lifecycle, including refresh-token validity and revocation state.

A sound policy for your application would be:

- Keep a stable internal user record in Postgres, linked to the identity provider with `(issuer, subject)`.
- Keep only an application session identifier in the browser cookie wherever practical. Set `Secure`, `HttpOnly`, and an appropriate `SameSite` policy when you control the cookie.
- Keep short-lived credentials in server-side storage with an expiry and access control.
- If you need long-lived refresh tokens for Google APIs or another provider, store them server-side, encrypted at rest, and restrict access to the smallest set of services.
- Do not store secrets in source code, Docker images, logs, or Git. Inject secrets at runtime and protect them with your secret-management system.

One important detail: the user's roles and permissions are your application's authorization data. They do not automatically belong to Google. Your application must decide which users are allowed to access its data.

For an enterprise service, do not use a role claim in an old, still-valid token as the only source of truth for highly sensitive permissions that can be revoked at any time. Token claims can remain unchanged until the token expires; current permission checks may also need to query your trusted application data.

# Part III — Using Keycloak instead of Google directly

## 18. First, what is Keycloak?

Keycloak is an identity and access management server. It supports OAuth 2.0 and OpenID Connect, manages application clients and users, issues tokens, and exposes endpoints for authentication, token renewal, token validation, and revocation.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.keycloak.org\&sz=32)

Keycloak

+1



Think of Keycloak as your own organization's authentication authority.

Instead of having every application manage Google-specific authentication logic, you can configure applications to trust Keycloak.

Your application may then trust tokens issued by your Keycloak instance, while Keycloak decides how users authenticate.

A typical setup looks like this:

Streamlit

OIDC client

Keycloak

Identity provider and token issuer

Authentication, token issuance, roles, sessions

FastAPI

Validates Keycloak access tokens and applies API authorization

Keycloak does not replace your FastAPI application or your Postgres business database. It centralizes identity and token issuance.

## 19. What changes when you introduce Keycloak?

The central change is the issuer your application trusts.

With direct Google login:

```
Google → Streamlit
```

With Keycloak:

```
Keycloak → Streamlit
       │
       └── issues access tokens intended for FastAPI
```

You can configure an OAuth/OIDC client in Keycloak for your frontend authentication and configure your API's audience, scopes, and roles.

There is a crucial configuration detail: do not assume that a Keycloak access token automatically has the right audience for FastAPI. Configure the appropriate audience and permissions for the resource server, then verify those claims in the token.

## 20. The Keycloak login flow, step by step

### Step 1 — Configure a realm

A realm is an administrative and identity boundary in Keycloak.

For example:

```
https://identity.example.com/realms/vbcreators
```

The realm has OIDC discovery metadata at a URL following this pattern:

```
https://identity.example.com/realms/vbcreators/.well-known/openid-configuration
```

The discovery document tells the OIDC client where to find the authorization, token, and other relevant endpoints.

### Step 2 — Register the application client

Create a Keycloak client for your application. Configure the allowed redirect URI, client type, and authentication settings.

For a server-side application, use an appropriately configured confidential client if the application needs to authenticate itself with a client secret.

Store its secret in your runtime secret manager, not in frontend code.

### Step 3 — Configure FastAPI as a protected resource

Decide which audience identifies your API, for example:

```
fastapi-api
```

Configure the Keycloak client scopes, audience mapper, and relevant roles or permissions so the access token contains the information your API expects.

Then configure FastAPI to trust the exact Keycloak realm issuer and validate access tokens intended for `fastapi-api`.

### Step 4 — The user clicks the login button

The browser is redirected to Keycloak with a request containing information such as:

```
response_type=code
client_id=streamlit-client
scope=openid profile email
redirect_uri=https://app.example.com/oauth2callback
state=...
nonce=...
```

Where PKCE is used, the request includes a code challenge.

### Step 5 — Keycloak authenticates the user

Keycloak may show a login page, MFA challenge, or another configured authentication method.

After the user is authenticated, Keycloak returns a one-time authorization code to the application callback.

### Step 6 — Exchange the code

The server-side OIDC client exchanges the code at Keycloak's token endpoint. It presents its client authentication, the registered redirect URI, and the PKCE verifier when applicable.

Keycloak can return:

- An ID token identifying the user to the client.
- An access token for the protected resource, if configured and issued for that request.
- A refresh token, if the request and client configuration permit it.

The Keycloak token endpoint handles code exchange and is also used for token refresh.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.keycloak.org\&sz=32)

Keycloak

+1



### Step 7 — Validate the user's identity

The OIDC client validates the ID token. It checks the signature and claims, including issuer, audience, expiry, and applicable nonce.

The application can then establish its signed-in session and map the identity to an internal user record.

### Step 8 — Make the first FastAPI request

In a token-based API design, Streamlit's server-side client sends the Keycloak access token, not the ID token:

```
GET /api/reports
Authorization: Bearer ACCESS_TOKEN
```

This is a conceptual HTTP example.

FastAPI verifies that the token:

1. Has a valid signature from the trusted Keycloak realm.
2. Has the expected issuer.
3. Has an audience that identifies the FastAPI API.
4. Has not expired.
5. Carries sufficient scopes or roles for the request.

FastAPI then checks the user's current application permissions where necessary and executes the operation.

### Step 9 — Send all subsequent requests

Until the access token expires, the application can normally reuse it.

FastAPI validates the token locally using trusted, cached public signing keys. It does not need to redirect the user to Keycloak or ask for their password again.

If the user tries to access a protected resource beyond their permissions, FastAPI rejects the operation even if the token is otherwise valid.

### Step 10 — Refresh the token

When a token needs refreshing, the trusted server-side component sends the refresh token to Keycloak's token endpoint.

Keycloak returns a new access token if the refresh is permitted. If the configuration rotates refresh tokens, the application must safely replace the previous refresh token.

If the refresh fails because the session or grant has expired or been revoked, the application needs to start a new authentication flow.

### Where should the Keycloak tokens be stored?

In the server-side session/token-management layer, when you need to retain them:

| Information                                | Suggested location                                  |
| ------------------------------------------ | --------------------------------------------------- |
| Keycloak client ID                         | Application configuration                           |
| Keycloak client secret                     | Secret manager                                      |
| Access token                               | Server-side short-lived session/cache, where needed |
| Refresh token                              | Protected server-side storage, only if needed       |
| Public signing keys                        | Key/JWKS cache                                      |
| Internal application roles and memberships | Postgres                                            |
| Temporary login state and PKCE verifier    | Protected temporary session storage                 |

The browser should not need to hold your Keycloak client secret or a long-lived refresh token.

Also, if your application uses `st.login()` alone, do not assume it exposes the raw access and refresh tokens required by an API-bearer-token design. Configure an OIDC integration that provides those tokens securely when that capability is needed, or use a separate server-side API credential design.

# Part IV — Using Keycloak together with Windows AD / AD FS

There are two architectures that sound similar but behave differently. First we need to separate Active Directory, which stores organizational identities, from AD FS, which provides federation and SSO.

## 21. Active Directory versus AD FS

- Active Directory Domain Services (AD DS) is the directory: it stores organizational user accounts, password-related authentication data, group memberships, and other attributes.
- AD FS is the federation service: it authenticates users against configured identity sources and issues federation/security tokens to applications.
- Keycloak can provide a centralized identity/token service for your applications. It can use directory federation or act as a broker to another identity provider.

Microsoft documents AD FS as a service for federated identity and single sign-on. It can use AD DS attributes and group membership information in its issued claims.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://learn.microsoft.com\&sz=32)

Microsoft Learn

+1



## 22. Option A: Keycloak connects directly to Active Directory

If your purpose is to use corporate AD accounts without making AD FS your application's identity provider, Keycloak can be configured for user federation against an LDAP-compatible directory.

The simplified flow is:

```
Streamlit
    │ OIDC
    ▼
Keycloak
    │ directory authentication / user federation
    ▼
Active Directory / LDAP
```

In this arrangement, Keycloak handles the application's OIDC flows and issues the tokens that your application trusts.

This can be appropriate when you want centralized application authentication and token issuance but do not specifically need an existing AD FS federation service to be the upstream authentication authority.

The exact integration setup depends on whether you need password validation against AD, synchronized user information, or Windows integrated SSO. Those are not interchangeable requirements.

## 23. Option B: Keycloak brokers authentication to AD FS

This is the architecture to use when an organization already has AD FS and wants its authentication experience to be used by applications whose direct identity provider is Keycloak.

Configure AD FS as an external OIDC identity provider in Keycloak, then configure the Keycloak client used by Streamlit.

Here is the flow:

Streamlit

Application

Keycloak

Broker and issuer trusted by the application

AD FS

Authenticates the user and provides an upstream identity assertion

Active Directory

Corporate user accounts, credentials and group information

The steps are:

1. The user selects login in Streamlit.
2. Streamlit redirects the browser to Keycloak.
3. Keycloak recognizes that this authentication request should use AD FS and redirects the browser there.
4. AD FS authenticates the user using its configured authentication mechanisms, potentially including Windows integrated authentication, a sign-in form, or MFA.
5. AD FS returns an identity response to Keycloak through the configured federation protocol.
6. Keycloak validates the upstream response and maps the external identity into its own user model and configured claims.
7. Keycloak issues the tokens for the application.
8. Streamlit establishes the user's application session.
9. For API requests, FastAPI validates Keycloak-issued access tokens, assuming you configured and obtained tokens intended for FastAPI.

The most important detail is step 7: in this architecture, Keycloak is the issuer your application trusts, not AD FS. AD FS authenticates the user upstream, but the application receives Keycloak-issued tokens. FastAPI therefore normally trusts Keycloak's issuer and signing keys.

This arrangement separates corporate authentication from the token contract that your application APIs consume.

### What changes in the token flow?

Without Keycloak:

```
Streamlit → AD FS → Streamlit
                    ↓
                  FastAPI
```

With Keycloak brokering AD FS:

```
Streamlit → Keycloak → AD FS
     ▲          ▲
     │          │
     └──────────┘
       Keycloak issues
       application tokens
```

The second diagram is simplified, but it captures the critical point: the browser redirects across the identity providers, and Keycloak completes the upstream identity-brokering flow before returning its own authorization response to the application.

Keycloak's documented OIDC endpoints, including its token and public-key endpoints, support this separation between its own issuance of application tokens and the upstream authentication mechanism.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.keycloak.org\&sz=32)

Keycloak

+1



# Part V — Using AD FS directly, without Keycloak

## 24. What changes when AD FS is the only identity provider?

In this design, you do not operate Keycloak as an intermediary. Streamlit's OIDC integration trusts AD FS directly, and AD FS issues the tokens for the configured application and API resources.

Streamlit

OIDC client / application UI

AD FS

Authenticates users, issues tokens, exposes federation metadata

FastAPI

Validates access tokens issued for this API

AD FS authenticates against Active Directory or another configured identity source.

AD FS has supported OAuth authorization flows and OpenID Connect since AD FS 2016. Microsoft's current documentation describes authorization-code flows, token issuance, refresh behavior, and PKCE support; PKCE support for OAuth authorization-code flows was introduced in AD FS 2019.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://learn.microsoft.com\&sz=32)

Microsoft Learn

+2



## 25. The direct AD FS flow, step by step

### Step 1 — Register the client and API

In AD FS, configure the appropriate application group, web client, API/resource identifiers, callback URI, permissions, and claims.

You need a clear client identifier for the application and a resource/audience identifier for the FastAPI API. Configure claims or scopes so the API gets the information it needs.

For example:

```
Client: streamlit-client
Resource: fastapi-api
```

These are illustrative identifiers. Their actual values depend on your AD FS configuration.

### Step 2 — Streamlit starts the OIDC login

The user clicks the sign-in button. The OIDC client redirects the browser to AD FS's authorization endpoint, following the AD FS metadata and registered client configuration.

A typical AD FS authorization endpoint has this form:

```
https://adfs.example.com/adfs/oauth2/authorize
```

The request includes the client ID, the redirect URI, the requested scopes, `response_type=code`, and transaction-protection values. PKCE parameters are included when PKCE is used.

### Step 3 — AD FS authenticates the user

AD FS determines how to authenticate the user. Depending on its configuration and the user's environment, it may use an existing Windows authentication context, a sign-in page, MFA, or other authentication policies.

AD FS uses Active Directory's identity information where configured to do so. Your Streamlit application does not need to ask the user to submit their Windows password to FastAPI.

### Step 4 — AD FS returns an authorization code

After successful authentication, the browser is redirected to the registered callback with an authorization code.

The application verifies the returned state and then exchanges the code with AD FS's token endpoint.

A typical token endpoint has this form:

```
https://adfs.example.com/adfs/oauth2/token
```

The exchange includes the authorization code, client ID, grant type, redirect URI, and the client authentication method required by the registration. A confidential client commonly uses its configured client secret, while a client configured for key-based authentication may use that method instead. A PKCE verifier must be supplied when the authorization request used PKCE.

### Step 5 — AD FS issues tokens

Depending on the request and configuration, AD FS can issue:

- An ID token for the application to identify the signed-in user.
- An access token for the configured resource/API.
- A refresh token when the relevant flow and policies permit it.

AD FS documents `id_token`, `access_token`, and `refresh_token` as distinct token types. The access token's audience must correspond to the intended resource, while the ID token is intended for the client.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://learn.microsoft.com\&sz=32)

Microsoft Learn

+1



### Step 6 — FastAPI validates the request

For a bearer-token API, the Streamlit server calls FastAPI with the access token intended for that API:

```
GET /api/reports
Authorization: Bearer ACCESS_TOKEN
```

FastAPI verifies the access token using the configured AD FS issuer, trusted signing keys, audience, lifetime, and required authorization claims.

If the API uses a JWT with known signing keys, these checks can generally be performed locally. If the token format or deployment requires introspection, validation instead follows the corresponding AD FS or token-validation mechanism.

### Step 7 — Future requests and refreshing

The application reuses an unexpired access token for subsequent protected requests.

When necessary, its trusted server-side token client sends the refresh token to AD FS's token endpoint to request a new access token. AD FS applies its configured refresh-token and SSO policies. The user normally does not have to sign in again while refresh remains valid.

If refreshing fails, the application needs to start a new sign-in flow.

AD FS refresh-token lifetimes and replacement behavior depend on configuration and factors such as persistent SSO or device registration. Do not assume that every AD FS deployment issues the same refresh-token lifetime or rotates tokens identically.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://learn.microsoft.com\&sz=32)

Microsoft Learn

+2



### Step 8 — Store your application data separately

Use Postgres for application-owned information, such as internal user records, memberships, roles, and permissions. Use Redis for temporary sessions or caches where suitable. Keep the AD FS client secret and any application signing keys in protected server-side secret storage.

AD FS's identity and token issuance do not replace your application's own authorization policy or data model.

# Part VI — Compare all three architectures

## 26. What changes, and what stays the same?

| Topic                                              | Google directly                                                                                  | Keycloak                                           | AD FS directly                                  |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------- | ----------------------------------------------- |
| Identity provider trusted by application           | Google                                                                                           | Keycloak                                           | AD FS                                           |
| Who authenticates the user?                        | Google                                                                                           | Keycloak or its upstream identity provider         | AD FS and its configured identity source        |
| Who issues the application's OIDC tokens?          | Google                                                                                           | Keycloak                                           | AD FS                                           |
| API access token issuer                            | Usually your application for a custom Google-login design, or a separately configured API issuer | Keycloak, with correct API audience                | AD FS, with correct API/resource configuration  |
| Who validates FastAPI access credentials?          | FastAPI                                                                                          | FastAPI                                            | FastAPI                                         |
| Where do user roles and business permissions live? | Your application, typically Postgres                                                             | Your application and/or configured Keycloak claims | Your application and/or configured AD FS claims |
| Is Redis required?                                 | No, but useful                                                                                   | No, but useful                                     | No, but useful                                  |
| Is Postgres required?                              | For your application's own durable data, yes in your proposed design                             | Same                                               | Same                                            |

The OAuth/OIDC concepts—authorization codes, PKCE, ID tokens, access tokens, refresh tokens, issuers, audiences, and expiration—remain substantially the same. What changes is the issuer, the authentication configuration, the claims and audiences it issues, and the validation configuration trusted by FastAPI.

## 27. What should you choose for your application?

For your Streamlit + FastAPI application, I would choose based on your actual requirements rather than introducing an identity server merely because it is possible.

## Choice A — Start with Google

Best when you need straightforward Google sign-in.

Use Streamlit's built-in OIDC login, map the authenticated Google identity to an internal user in Postgres, and establish a secure application session. Authenticate Streamlit-to-FastAPI calls separately.

This avoids managing Google refresh tokens when your application only needs sign-in.

## Choice B — Adopt Keycloak as the identity layer

Best when you expect enterprise customers to use different identity providers, want a central issuer, and need explicit API access tokens, scopes, and roles.

Configure Keycloak for your applications and FastAPI API resource, and use access tokens with the correct audience. Later, Keycloak can broker Google or AD FS authentication without requiring every application to change its trusted issuer.

## Choice C — Use existing AD FS directly

Best when an organization already operates AD FS and needs applications to integrate with that existing federation service.

Configure the AD FS client and API resource, then have FastAPI trust AD FS-issued access tokens for that resource. You avoid operating another identity server, but you also do not gain Keycloak's centralized identity-brokering layer.

One current planning consideration: Microsoft's AD FS documentation recommends considering Microsoft Entra ID rather than deploying or upgrading AD FS for new deployments.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://learn.microsoft.com\&sz=32)

Microsoft Learn

+1



## 28. My recommended production design for an enterprise SaaS

For the product direction you have described, I would keep these responsibilities separate:

```
                    IDENTITY LAYER
               Google / Corporate AD FS
                         │
                         ▼
                      Keycloak
                  Token issuer for apps
                         │
                         │ Access token
                         ▼
STREAMLIT ───────────► FASTAPI
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
            Postgres      Redis     Other APIs
```

This is the token-oriented design. Streamlit's server-side OIDC integration must actually acquire and manage the API access token if you choose this route; `st.login()` alone is not a promise that the token will be available to your API-calling code.

You could instead use a server-side application-session pattern and have Streamlit make authenticated internal calls to FastAPI. Both are legitimate designs. The key is to choose one consistently and not mix up a Google ID token, an API access token, an internal application token, and a browser session cookie.

For either design, have these security boundaries:

- Authentication: the identity provider establishes who signed in.
- Token or session validation: FastAPI verifies the credential presented for its own endpoints.
- Authorization: your API checks the user's tenant, membership, permissions, and the requested resource.
- Persistence: Postgres owns durable application information; Redis supports appropriate temporary state and caching.
- Secrets: OAuth client secrets, application signing keys, and refresh tokens remain under server-side protection.

One FastAPI-specific point: `OAuth2PasswordBearer` extracts a bearer token from the authorization header and describes the OAuth security scheme. It does not, by itself, verify the token's signature, audience, expiration, or permissions. Your authentication code must perform those checks. Then FastAPI dependencies or middleware can make the authenticated identity available to endpoint handlers.

## 29. Final mental model

Remember these five rules, and the flows become much easier to reason about:

1. Google, Keycloak, or AD FS authenticates the user. The application should not handle the user's identity-provider password directly.
2. The ID token is about login; the access token is about access to a resource. A token's audience and purpose determine where it can be used.
3. The refresh token goes to the token issuer, not the business API. It is used only when needed to obtain fresh tokens.
4. FastAPI does not have to call the identity provider for every JWT request. It can validate a signed token locally with cached trusted public keys, although revocation and opaque-token strategies may require additional checks.
5. Your application still owns its access policy. A successfully authenticated user is not automatically allowed to access every tenant, document, customer, or administrative endpoint.

Once these are clear, moving from Google to Keycloak or AD FS changes the identity-provider configuration and trusted token issuer far more than it changes the basic request-validation concepts.
