# Redis Sessions & Token Management

Let’s build this from the ground up.

---

## 1. The Core Concepts

### Authentication vs Authorization

- **Authentication** answers: “Who are you?”
- **Authorization** answers: “What are you allowed to do?”

Examples:

- Login with email/password → authentication.
- Checking whether that user can edit a post → authorization.

Redis is commonly used for the authentication/session part.

---

## 2. What Is a Session?

A **session** is a record on the server representing a logged-in user.

When someone logs in:

1. The server creates a session.
2. The server stores session data somewhere.
3. The browser receives a small **session ID** cookie.
4. On future requests, the browser automatically sends that cookie.
5. The server looks up the session ID and knows who is making the request.

Example session data might include:

```json
{
  "userId": "123",
  "email": "user@example.com",
  "roles": ["user"],
  "createdAt": "2026-09-09T10:00:00Z",
  "lastSeenAt": "2026-09-09T10:15:00Z"
}
```

The cookie usually contains only:

```text
sessionId=8f3bfa8e-7d12-4c5a-a67b-9bd20de4f182
```

The sensitive user information stays on the server.

---

## 3. Why Redis Is Useful for Sessions

A web application may have multiple servers. If you store sessions in one application server’s memory, another server will not recognize the user.

Redis solves this because all application servers can share the same Redis session store.

Redis is useful because it is:

- **Fast:** usually an in-memory lookup.
- **Shareable:** many backend servers can use the same Redis instance.
- **Expirable:** keys can automatically disappear after a TTL.
- **Simple:** supports strings, hashes, sets, sorted sets, and expiration.

Example:

```bash
SET session:8f3bfa8e '{"userId":"123"}' EX 1800
```

This stores the session for 1800 seconds, or 30 minutes. Redis automatically deletes it after that.

---

## 4. Opaque Tokens vs JWTs

There are two major token styles.

### Opaque token

An opaque token is random data that has no readable meaning.

Example:

```text
s%2F5K8f3Xy9vPzQm...
```

The server must look it up in Redis or a database.

**Advantages:**

- Simple to revoke.
- Token contents are not readable by the client.
- Server can store session state.

**Disadvantage:**

- Every authenticated request requires a Redis lookup.

---

### JWT

JWT means **JSON Web Token**.

A JWT usually looks like this:

```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.
eyJ1c2VySWQiOiIxMjMiLCJyb2xlIjoidXNlciJ9.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c
```

It has three parts:

```text
HEADER.PAYLOAD.SIGNATURE
```

The payload contains claims such as:

```json
{
  "sub": "123",
  "email": "user@example.com",
  "iat": 1767225600,
  "exp": 1767227400
}
```

Common claims:

- `sub`: user ID
- `iat`: issued at
- `exp`: expiration time
- `iss`: issuer
- `aud`: audience
- `jti`: token ID

Important: a JWT is usually **signed, not encrypted**.

That means:

- The server can verify the token was not changed.
- The client can usually read the payload.
- Do not put passwords or sensitive information inside a JWT.

---

## 5. The Most Common Redis Session Pattern

This is the classic pattern:

1. User logs in.
2. Generate a random session ID.
3. Store session details in Redis.
4. Send the session ID to the browser as an `HttpOnly` cookie.
5. On every request, read the cookie.
6. Load session data from Redis.
7. Attach the user information to the request.

### Redis key design

Example:

```bash
HSET session:8f3bfa8e \
  userId "123" \
  roles "user,editor" \
  createdAt "2026-09-09T10:00:00Z" \
  lastSeenAt "2026-09-09T10:15:00Z"

EXPIRE session:8f3bfa8e 1800
```

Or store one JSON string:

```bash
SET session:8f3bfa8e \
'{"userId":"123","roles":["user"],"createdAt":"..."}' \
EX 1800
```

Hashes are often better when you need to update individual fields.

Example sliding expiration:

```bash
EXPIRE session:8f3bfa8e 1800
```

You normally update `lastSeenAt` and reset the TTL when the user performs an action.

---

## 6. Login Flow With Redis Sessions

A typical login looks like this:

1. User submits email and password.
2. Server verifies the credentials.
3. Server creates a random session ID.
4. Server writes session data to Redis:

```bash
SET session:abc123 \
'{"userId":"123","roles":["user"]}' \
EX 1800
```

5. Server sends a cookie:

```http
Set-Cookie: session_id=abc123; HttpOnly; Secure; SameSite=Lax; Path=/
```

6. Browser includes the cookie on future requests:

```http
Cookie: session_id=abc123
```

7. Server reads `session_id=abc123`, loads Redis, and recognizes the user.

---

## 7. Logout in a Redis Session System

Logout should do server-side work.

Do not only clear the browser cookie. Clearing the cookie hides the session from that browser, but if someone copied the session ID earlier, the session may still be active.

Correct logout:

```bash
DEL session:abc123
```

Then remove the browser cookie.

If you support “log out everywhere,” maintain an index of sessions per user.

For example:

```bash
SADD user:123:sessions session:abc123 session:def456
```

Then delete all session IDs in that set.

---

## 8. Access Tokens and Refresh Tokens

In token-based authentication, there are usually two kinds of tokens.

### Access token

The access token is sent with API requests to prove the user is authenticated.

It should be short-lived, for example:

- 5 minutes
- 10 minutes
- 15 minutes

A short lifetime limits the damage if the token is stolen.

### Refresh token

The refresh token is used only to obtain a new access token.

It should be long-lived, for example:

- 7 days
- 30 days
- 90 days

Because it is powerful, it must be protected carefully.

### Why use both?

If the access token lasts 30 days, a stolen token is useful for 30 days.

Instead:

- Access token lasts 10 minutes.
- Refresh token lasts 30 days.
- When the access token expires, the client quietly gets another one.
- If the refresh token is stolen or reused suspiciously, you can revoke it.

---

## 9. Recommended Hybrid JWT + Redis Design

A common secure design is:

### Access token

Use a JWT.

Keep it in:

- frontend memory, or
- an `HttpOnly` cookie if appropriate.

Claims:

```json
{
  "sub": "123",
  "roles": ["user"],
  "sessionId": "sess_abc",
  "jti": "token_123",
  "iat": 1767225600,
  "exp": 1767226200
}
```

It is short-lived.

### Refresh token

Use a long random opaque token, not necessarily a JWT.

Store only a hash of it in Redis:

```bash
SET refresh:sha256_of_token \
'{"userId":"123","sessionId":"sess_abc","familyId":"fam_789"}' \
EX 2592000
```

That is a 30-day TTL.

The browser stores the refresh token in an `HttpOnly`, `Secure`, `SameSite` cookie.

This hybrid gives you:

- Fast access-token validation without Redis on every request.
- Centralized control of refresh tokens.
- Easy logout and revocation.
- Refresh-token rotation.

---

## 10. JWT + Redis: Refresh Token Rotation

Refresh token rotation means:

> Every time a refresh token is used, it is invalidated and replaced by a new refresh token.

### Why rotate refresh tokens?

If an attacker steals a refresh token, it will eventually be used.

When the real user later uses a newer refresh token, or when the old stolen token is used again, your system can detect suspicious reuse and revoke the entire token family.

### Token family

A token family groups all refresh tokens created from one login.

Example:

- Login creates refresh token A.
- Token A rotates into token B.
- Token B rotates into token C.
- A, B, and C belong to family F1.

If an old token is reused, revoke F1.

---

## 11. Refresh Rotation Flow

### First login

Server generates:

- access token
- refresh token R1
- family ID F1

Store:

```bash
SET refresh:hash(R1) \
'{"userId":"123","familyId":"F1","sessionId":"sess_1"}' \
EX 2592000
```

Send R1 to the browser in a secure cookie.

---

### Access token expires

The frontend calls:

```http
POST /auth/refresh
Cookie: refresh_token=R1
```

The server:

1. Reads R1.
2. Hashes it.
3. Looks up Redis:

```bash
GET refresh:hash(R1)
```

4. If found, it generates R2.
5. Deletes R1:

```bash
DEL refresh:hash(R1)
```

6. Stores R2:

```bash
SET refresh:hash(R2) \
'{"userId":"123","familyId":"F1","sessionId":"sess_1"}' \
EX 2592000
```

7. Returns a new access token.
8. Replaces the refresh cookie with R2.

---

### Why detect reuse?

Suppose an attacker steals R1.

The legitimate user later refreshes R1, so R1 is deleted and R2 is issued.

Now the attacker tries to use R1 again.

The server sees that R1 was already rotated. That may mean:

- the network request retried, or
- someone stole the old token.

For stronger security, revoke the whole token family F1.

This forces the user to log in again.

---

## 12. Simple Redis Refresh Example in JavaScript

This example uses Node.js and `ioredis`.

```javascript
import Redis from "ioredis";
import crypto from "crypto";

const redis = new Redis();

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function generateToken() {
  return crypto.randomBytes(32).toString("base64url");
}
```

### Login

```javascript
app.post("/login", async (req, res) => {
  const { email, password } = req.body;

  // Verify email/password using your normal user system.
  const user = await verifyUser(email, password);
  if (!user) {
    return res.status(401).json({ message: "Invalid credentials" });
  }

  const accessToken = createJwt({
    sub: user.id,
    roles: user.roles,
    sessionId: user.sessionId,
    expiresIn: "10m"
  });

  const refreshToken = generateToken();
  const refreshHash = sha256(refreshToken);
  const familyId = generateToken();

  await redis.set(
    `refresh:${refreshHash}`,
    JSON.stringify({
      userId: user.id,
      sessionId: user.sessionId,
      familyId
    }),
    "EX",
    60 * 60 * 24 * 30
  );

  res.cookie("refresh_token", refreshToken, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/auth",
    maxAge: 1000 * 60 * 60 * 24 * 30
  });

  res.json({ accessToken });
});
```

### Refresh

```javascript
app.post("/auth/refresh", async (req, res) => {
  const oldRefreshToken = req.cookies.refresh_token;

  if (!oldRefreshToken) {
    return res.sendStatus(401);
  }

  const oldHash = sha256(oldRefreshToken);

  // GETDEL is atomic: read and delete in one operation.
  const stored = await redis.getdel(`refresh:${oldHash}`);

  if (!stored) {
    // In production, inspect whether this token was previously used.
    return res.sendStatus(401);
  }

  const oldData = JSON.parse(stored);

  const accessToken = createJwt({
    sub: oldData.userId,
    sessionId: oldData.sessionId,
    expiresIn: "10m"
  });

  const newRefreshToken = generateToken();
  const newHash = sha256(newRefreshToken);

  await redis.set(
    `refresh:${newHash}`,
    JSON.stringify({
      userId: oldData.userId,
      sessionId: oldData.sessionId,
      familyId: oldData.familyId
    }),
    "EX",
    60 * 60 * 24 * 30
  );

  res.cookie("refresh_token", newRefreshToken, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/auth",
    maxAge: 1000 * 60 * 60 * 24 * 30
  });

  res.json({ accessToken });
});
```

This is intentionally simple. A production system also needs:

- refresh-token reuse detection
- rate limiting
- refresh-token tombstones
- CSRF protection
- structured session records
- monitoring and audit logs

---

## 13. Handling Refresh Retries

There is one tricky problem.

Suppose the browser refreshes a token and the response is lost because of a network error. The server may already have deleted the old token and issued a new one.

If the browser retries the old token, the server sees it as “reuse” and logs the user out.

There are two common approaches.

### Strict rotation

- One refresh token works exactly once.
- Any retry with the old token is rejected.
- Simpler, but users may occasionally get logged out during network failures.

### Short overlap/grace period

- The old refresh token remains valid for a few seconds.
- This helps with retries.
- But it increases attack complexity and must be implemented carefully.

A common compromise is a very short grace period, such as 5–15 seconds.

For a beginner implementation, strict rotation is easier to understand.

---

## 14. JWT Blacklist for Logout

A JWT remains valid until its `exp` time unless you add a revocation mechanism.

That creates a problem:

- Access token expires in 15 minutes.
- User clicks logout.
- You delete the refresh token.
- But the access token may still work for up to 15 minutes.

### Solution: blacklist

When the user logs out, store the token’s `jti` in Redis:

```bash
SET blacklist:token_123 "1" EX 900
```

Use a TTL equal to the remaining access-token lifetime.

Then authentication middleware does this:

1. Verify the JWT signature.
2. Check `exp`.
3. Check whether the `jti` is blacklisted.
4. If blacklisted, reject it.

Example:

```javascript
const isBlacklisted = await redis.exists(`blacklist:${jwt.jti}`);

if (isBlacklisted) {
  return res.sendStatus(401);
}
```

### Important

Do not blacklist tokens forever. That would make Redis grow unnecessarily.

Store only until:

```text
token expiration time - current time
```

Example in JavaScript:

```javascript
const ttlSeconds = Math.max(0, jwt.exp - Math.floor(Date.now() / 1000));

await redis.set(`blacklist:${jwt.jti}`, "1", "EX", ttlSeconds);
```

---

## 15. When You Need a Blacklist

Use a blacklist when you need to invalidate an access token before it naturally expires.

Examples:

- user logout
- password change
- account suspension
- administrator ban
- suspected token theft
- permission or session version changes

### Example: password change

When a user changes their password:

1. Delete refresh tokens for the user.
2. Blacklist current access tokens or increase a session version.
3. Force active sessions to re-authenticate.

---

## 16. Alternative to Blacklisting Every Token

If every request checks Redis, your JWT becomes stateful.

That is not necessarily bad, but it reduces one benefit of JWTs: stateless verification.

Other approaches include:

### Session version

Add a version to the session:

```json
{
  "sub": "123",
  "sessionId": "sess_1",
  "version": 4
}
```

Redis stores the current version:

```bash
HSET session:sess_1 userId "123" version "4"
```

On each request, compare the JWT version with Redis. If they differ, reject.

This is useful for logout-all or password changes.

### User token version

Store a version per user:

```bash
SET user:123:token_version 4
```

The JWT contains:

```json
{
  "sub": "123",
  "version": 4
}
```

If the user’s version changes to 5, all old JWTs become invalid.

### Opaque session tokens

Instead of JWT access tokens, use random session IDs and check Redis every time.

This is simpler and often perfectly fine.

Choose based on your system’s needs.

---

## 17. Best Redis Key Structures

Here are common patterns.

### Single session

```text
session:{sessionId}
```

Value:

```json
{
  "userId": "123",
  "roles": ["user"],
  "createdAt": "...",
  "lastSeenAt": "...",
  "version": 1
}
```

---

### Refresh token

```text
refresh:{sha256(token)}
```

Value:

```json
{
  "userId": "123",
  "sessionId": "sess_1",
  "familyId": "fam_1"
}
```

---

### JWT blacklist

```text
blacklist:{jti}
```

---

### User sessions index

```text
user:{userId}:sessions
```

Redis type: set

```text
session:sess_1
session:sess_2
```

This helps you implement “log out from all devices.”

---

### Used refresh token tombstone

```text
used_refresh:{sha256(token)}
```

Value: family ID

This helps detect refresh-token reuse.

---

## 18. TTL Strategy

Every security token should have an expiration.

### Access token TTL

Common choices:

- 5 minutes
- 10 minutes
- 15 minutes

Shorter is safer, but too short means frequent refreshes.

### Refresh token TTL

Common choices:

- 7 days
- 30 days
- 90 days

Longer is convenient, but riskier.

### Session TTL

Choose between:

#### Fixed expiration

The session expires after a fixed amount of time, regardless of activity.

```text
Login at 10:00 → expires at 10:30
```

#### Sliding expiration

The session TTL resets whenever the user is active.

```text
Login at 10:00
Request at 10:20 → expire at 10:50
Request at 10:45 → expire at 11:15
```

Sliding expiration is common for ordinary web sessions.

You may also add an **absolute expiration** so a session cannot remain active forever.

Example:

- sliding expiration: 30 minutes
- absolute expiration: 12 hours

---

## 19. Cookie Security

Cookies are the usual way browsers carry session and refresh tokens.

A secure session cookie should usually have:

```http
HttpOnly; Secure; SameSite=Lax; Path=/
```

### `HttpOnly`

JavaScript cannot read the cookie.

This helps against some XSS attacks.

```http
Set-Cookie: session_id=abc; HttpOnly
```

Important: `HttpOnly` does not stop XSS completely. Malicious JavaScript can still make requests through the browser; it just cannot directly read the cookie value.

---

### `Secure`

The cookie is sent only over HTTPS.

```http
Set-Cookie: session_id=abc; Secure
```

Never use session cookies over plain HTTP in production.

---

### `SameSite`

Controls when browsers send cookies cross-site.

Common options:

- `Strict`
- `Lax`
- `None`

#### `SameSite=Strict`

The cookie is not sent for cross-site requests at all.

Best security, but can be annoying if users arrive from external links.

#### `SameSite=Lax`

The cookie is sent for normal top-level navigation but generally not for cross-site POST requests.

Usually a good default.

#### `SameSite=None`

Required for some cross-site cookie scenarios.

If you use this, the cookie must also be `Secure`.

---

### `Path`

Limits the URL paths that receive the cookie.

Example:

```http
Path=/auth
```

For refresh cookies, this is useful because the refresh endpoint needs the cookie, but the rest of the app does not.

---

### `Domain`

Avoid setting `Domain` unless necessary.

If you set:

```http
Domain=example.com
```

the cookie may also be sent to subdomains.

That increases exposure.

Use `__Host-` cookie names if you want browser-enforced restrictions.

Example:

```http
Set-Cookie: __Host-refresh=token; Secure; Path=/; HttpOnly; SameSite=Lax
```

`__Host-` requires:

- `Secure`
- `Path=/`
- no `Domain`

---

## 20. CSRF and Cookies

CSRF means **Cross-Site Request Forgery**.

It happens when another website tricks a user’s browser into making a request to your site. Since browsers automatically attach cookies, the request may look authenticated.

Example:

```html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="to" value="attacker">
</form>
```

If the user is logged in, the browser may include the session cookie.

### Protection

Use a combination of:

- `SameSite=Lax` or `Strict`
- proper CORS policy
- CSRF tokens for cookie-based state-changing requests
- require custom headers for sensitive requests
- never allow unsafe GET requests to change data

For APIs using the `Authorization` header, CSRF risk is lower because the browser does not automatically attach `Authorization` headers.

For cookie-based APIs, CSRF protection is very important.

---

## 21. XSS and Token Storage

XSS means **Cross-Site Scripting**.

If an attacker injects malicious JavaScript into your page, that script can read anything JavaScript can access.

This is why storing access tokens in `localStorage` is risky:

```javascript
localStorage.setItem("access_token", token);
```

If XSS happens, the attacker can read the token.

Better options:

### Put refresh token in an `HttpOnly` cookie

JavaScript cannot read it.

### Keep access token in frontend memory

This is safer than `localStorage`, but it disappears when the page reloads.

After reload, the frontend calls the refresh endpoint.

This pattern is common:

1. Access token is stored in memory.
2. Refresh token is stored in an `HttpOnly` cookie.
3. On page reload, frontend silently refreshes the access token.

---

## 22. Recommended Production Architecture

For a typical web application:

### Login

1. Verify credentials.
2. Create session record in Redis.
3. Issue short-lived JWT access token.
4. Issue long-lived random refresh token.
5. Store refresh-token hash in Redis.
6. Put refresh token in `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
7. Return access token to frontend memory.

### API request

1. Read access token from `Authorization: Bearer ...`.
2. Verify JWT signature and expiration.
3. Check blacklist/session version only when needed.
4. Perform authorization checks.
5. Return data.

### Token refresh

1. Call `POST /auth/refresh`.
2. Read refresh cookie.
3. Verify hashed token in Redis.
4. Rotate refresh token.
5. Return new access token.
6. Set new refresh cookie.

### Logout

1. Delete refresh token from Redis.
2. Blacklist current access token or invalidate session version.
3. Clear refresh cookie.
4. Optionally remove the user’s session index entry.

---

## 23. Common Security Mistakes

### 1. Storing passwords in Redis sessions

Do not do this.

Bad:

```json
{
  "userId": "123",
  "password": "..."
}
```

### 2. Putting sensitive data in JWT payloads

JWT payloads are readable. Do not include passwords, secrets, or private personal data.

### 3. Never expiring tokens

Always set expiration.

### 4. Using weak random tokens

Use a cryptographically secure random generator.

Do not use:

```javascript
Math.random()
```

Use:

```javascript
crypto.randomBytes(32)
```

### 5. Storing raw refresh tokens in Redis

Store a hash of the refresh token instead.

If Redis is exposed, raw refresh tokens are not immediately usable.

### 6. Trusting the client’s user ID

Never accept this from the client:

```json
{
  "userId": "123"
}
```

The authenticated identity must come from:

- verified session data, or
- a verified and trusted token.

### 7. Forgetting CSRF protection

Cookies alone do not prevent CSRF.

### 8. Thinking JWT signature means the token is still authorized

A JWT can be correctly signed but should no longer be accepted because the user logged out or was banned.

### 9. Leaving Redis publicly accessible

Redis should not be directly exposed to the internet. Use:

- private networking
- authentication
- ACLs
- TLS where appropriate
- firewall rules

### 10. Logging tokens

Do not write tokens into ordinary application logs.

---

## 24. Operational Redis Considerations

### Expiration

Always set TTLs on:

- sessions
- refresh tokens
- blacklist entries
- temporary verification tokens

### Persistence

Redis is usually memory-first. Depending on your setup, sessions may disappear if Redis restarts.

Use Redis persistence carefully:

- RDB snapshots
- AOF persistence
- replication

If losing sessions only logs users out, that may be acceptable.

If losing sessions is serious, configure persistence and failover.

### Eviction

Do not configure Redis to evict important session keys casually just because memory is full.

Use an appropriate memory policy and monitor usage.

### Clustering

If you use Redis Cluster, design keys carefully because some multi-key operations require keys in the same hash slot.

For a beginner, start with a managed Redis service or a single Redis instance.

---

## 25. Redis Commands You Should Know

### Create a session

```bash
SET session:abc '{"userId":"123"}' EX 1800
```

### Read a session

```bash
GET session:abc
```

### Delete a session

```bash
DEL session:abc
```

### Refresh the TTL

```bash
EXPIRE session:abc 1800
```

### Create a hash-based session

```bash
HSET session:abc userId "123" roles "user" version "1"
EXPIRE session:abc 1800
```

### Read one session field

```bash
HGET session:abc userId
```

### Blacklist a token

```bash
SET blacklist:jti123 "1" EX 900
```

### Check blacklist

```bash
EXISTS blacklist:jti123
```

### Track all sessions for one user

```bash
SADD user:123:sessions "session:abc" "session:def"
```

### Delete one session from the index

```bash
SREM user:123:sessions "session:abc"
```

---

## 26. Practical Cheat Sheet

| Item | Recommendation |
|---|---|
| Session ID | Random, opaque, high entropy |
| Session storage | Redis with TTL |
| Access token | Short-lived JWT, often 5–15 minutes |
| Refresh token | Long-lived random opaque token |
| Refresh token in Redis | Store SHA-256 hash, not raw token |
| Refresh rotation | Rotate on every refresh |
| Reuse detection | Revoke token family on suspicious reuse |
| Logout | Delete refresh token and invalidate active access token |
| JWT logout | Blacklist `jti` until original `exp` |
| Cookie flags | `HttpOnly`, `Secure`, `SameSite=Lax`, correct `Path` |
| CSRF protection | SameSite plus CSRF/header defenses |
| XSS protection | Avoid sensitive tokens in `localStorage` |
| Redis security | Private network, authentication, TLS where appropriate |
| Rate limiting | Protect login and refresh endpoints |
| Token logging | Do not log full tokens |

---

## 27. The Big Picture

The safest beginner-friendly model is:

1. **Use Redis for sessions and refresh tokens.**
2. **Use short-lived JWT access tokens.**
3. **Use random refresh tokens.**
4. **Store only refresh-token hashes in Redis.**
5. **Rotate refresh tokens after every use.**
6. **Revoke the token family when reuse is detected.**
7. **Use cookies with `HttpOnly`, `Secure`, and `SameSite`.**
8. **Add CSRF protection for cookie-authenticated requests.**
9. **Blacklist JWTs for immediate logout.**
10. **Use TTLs everywhere.**

A simple mental model is:

- **Access token:** a temporary badge.
- **Refresh token:** a card that can issue a new badge.
- **Redis:** the secure office database that knows which cards and sessions are valid.
- **Rotation:** every time the card is used, the old card is destroyed and replaced.
- **Blacklist:** a “do not accept this badge anymore” list.

Once you understand those five ideas, Redis session and token management becomes much easier to reason about.
