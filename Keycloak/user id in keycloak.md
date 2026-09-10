**Use Keycloak’s `sub` claim as your application’s unique user ID.** Do **not** create a separate application-generated userid unless you have a very specific reason (legacy system, multi-IdP federation that forces it, etc.).

### 1. What is the unique user ID in a Keycloak JWT?

Keycloak (following the OpenID Connect / JWT standards) puts the user’s permanent unique identifier in the **`sub`** (subject) claim.

Example of a typical Keycloak access token payload (simplified):

```json
{
  "exp": 1725...,
  "iat": 1725...,
  "jti": "some-token-id",
  "iss": "https://your-keycloak/realms/your-realm",
  "aud": "your-client-id",
  "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",   ← THIS is the user ID
  "typ": "Bearer",
  "azp": "your-client-id",
  "session_state": "...",
  "realm_access": { "roles": ["user", "offline_access"] },
  "scope": "openid email profile",
  "email_verified": true,
  "name": "John Doe",
  "preferred_username": "johndoe",
  "given_name": "John",
  "family_name": "Doe",
  "email": "john@example.com"
}
```

- **`sub`** = Keycloak’s internal user ID (almost always a UUID).  
  It is stable, never reassigned, and unique within the realm (and with the `iss` claim it is globally unique).
- **`preferred_username`** = the username the user types (can change).
- **`email`** = can change or be missing.
- Other claims (`name`, roles, etc.) are useful but **not** for unique identification.

You can (and should) rely on `sub`. It is the standard, recommended way.

### 2. Should you create your own application userid or reuse Keycloak’s?

**Best practice for almost every FastAPI + Keycloak project:**

- Use Keycloak’s `sub` value directly as the primary key (or as a unique indexed column) in your application database.
- Store it in every table that records user activity (orders, logs, posts, audit trails, etc.).

**Why this is better:**

| Approach | Pros | Cons |
|----------|------|------|
| Use Keycloak `sub` | Single source of truth, no sync headaches, works with future Keycloak features, simple | Slightly longer UUID strings |
| Generate your own userid + map to `sub` | Familiar integer IDs | Extra table/mapping, risk of desync, more code, harder multi-IdP later |

Only create your own ID if:
- You already have a large legacy database with integer user IDs.
- You must support multiple identity providers and need a unified internal ID.
- Business rules force sequential IDs.

Even then, still store the Keycloak `sub` as a unique column and use it for lookups.

### 3. Where to store the userid in the JWT?

You don’t put anything extra in the JWT yourself.  
Keycloak already puts the correct value in **`sub`**.  
Your FastAPI code just **reads** it.

You *can* add custom claims via Keycloak Protocol Mappers if you want (e.g. an internal `app_user_id`), but it is unnecessary and adds complexity.

### 4. Complete user identification + activity/log cycle (beginner walkthrough)

Here is the full lifecycle:

#### A. User registers / is created
1. User is created in Keycloak (Admin Console, registration form, or Admin API).
2. Keycloak assigns a permanent UUID → this becomes the `sub` value forever.

#### B. User logs in
1. Frontend (or your app) redirects the user to Keycloak (Authorization Code + PKCE flow is recommended).
2. User authenticates.
3. Keycloak returns an **access token** (JWT) + optionally a refresh token and ID token.
4. Frontend stores the access token (usually in memory or secure storage) and sends it on every API request:
   ```
   Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

#### C. FastAPI receives a request
1. You have a dependency that:
   - Extracts the Bearer token.
   - Fetches Keycloak’s public keys (JWKS endpoint) once and caches them.
   - Validates the signature, expiration (`exp`), issuer (`iss`), audience (`aud`), etc.
   - Decodes the payload.

2. From the decoded payload you take:
   ```python
   user_id = payload["sub"]          # the only ID you need
   username = payload.get("preferred_username")
   email = payload.get("email")
   roles = payload.get("realm_access", {}).get("roles", [])
   ```

3. (Optional but common) “Just-in-time” user provisioning:
   ```python
   # Pseudo-code
   user = db.query(User).filter(User.keycloak_id == user_id).first()
   if not user:
       user = User(keycloak_id=user_id, email=email, username=username)
       db.add(user)
       db.commit()
   ```

#### D. Recording activity / logs
Whenever the user does something (create post, place order, view page, etc.):

```python
# Example
activity = Activity(
    user_id=user_id,          # the Keycloak sub
    action="created_post",
    resource_id=post.id,
    timestamp=datetime.utcnow(),
    ip=request.client.host,
    # any other metadata
)
db.add(activity)
db.commit()
```

All your tables that need “who did this?” simply store the same `sub` value.

#### E. Later queries
```python
# Get all activities of the current user
activities = db.query(Activity).filter(Activity.user_id == current_user.sub).all()

# Or join with your local User table if you keep extra profile data
```

### 5. Recommended FastAPI pattern (high-level)

```python
from fastapi import Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt   # or PyJWT + PyJWKClient
# ... JWKS validation logic ...

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    payload = validate_and_decode(credentials.credentials)  # your validation function
    return payload   # contains "sub", "preferred_username", etc.

@app.post("/posts")
async def create_post(
    data: PostCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = user["sub"]          # ← use this everywhere
    # create post and store user_id
    ...
```

You can also create a small Pydantic model:

```python
class CurrentUser(BaseModel):
    id: str          # = sub
    username: str | None
    email: str | None
    roles: list[str]
```

### Summary – what you should do

1. Treat Keycloak’s **`sub`** as your application’s canonical user ID.
2. Store that exact string in every database table that records user activity.
3. Read it from the JWT with `payload["sub"]`.
4. Optionally keep a local `users` table keyed by `keycloak_id = sub` if you need extra application-specific profile data, preferences, etc.
5. Never invent a second independent userid unless you really have to.

This keeps identity management (Keycloak) and your business data cleanly separated while still giving you a reliable, permanent user identifier for logs, audit trails, ownership, etc.

If you show me your current token validation code or database models, I can give you concrete FastAPI + SQLAlchemy examples next.
