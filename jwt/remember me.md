**"Remember Me" keeps a user logged in across browser sessions** (closing the tab/browser, restarting the computer, etc.) by making the authentication credential longer-lived and usually more persistent on the client.

Here’s what happens internally for the three common mechanisms, what the tokens look like, and what an attacker can do if they steal them.

### 1. Classic Session Cookie Mechanism

**Normal login (Remember Me unchecked)**
- Server creates a short-lived server-side session (e.g. 15–30 minutes of inactivity, or until browser close).
- Sets a **session cookie** (usually `HttpOnly`, `Secure`, `SameSite=Lax/Strict`).
- Cookie has **no `Expires` / `Max-Age`** → it is a *session cookie* and is deleted when the browser is closed.
- Server stores the session data (user ID, roles, etc.) in Redis/memory/DB keyed by the session ID.

**Remember Me checked**
- Server creates a longer-lived session (days/weeks/months) **or** issues a separate long-lived “remember-me” token/cookie.
- The cookie gets an explicit `Expires` / `Max-Age` (e.g. 30 days).
- Often the remember-me cookie is a random high-entropy token stored in a separate table (or a signed value) that can later re-create a full session.

**If attacker copies the cookie**
- Yes — they can replay the cookie on their machine and get the user’s session (until it expires or is invalidated).
- With Remember Me the window is much larger (days/weeks instead of minutes/hours).
- Mitigation: `HttpOnly` + `Secure` + `SameSite`, IP/device binding, short absolute lifetime + rotation, server-side revocation list.

### 2. JWT Mechanism (stateless)

**Normal login (Remember Me unchecked)**
- Server issues a short-lived **access token** (JWT) — typically 5–15 minutes.
- Often also issues a short-lived **refresh token** (or none at all).
- Tokens are usually stored in memory or in a non-persistent cookie / `sessionStorage`.
- When the browser is closed, the tokens disappear → user must log in again.

**Remember Me checked**
- Access token still short-lived (good practice).
- Refresh token becomes long-lived (days/weeks) and is stored in a **persistent** cookie (`localStorage` is worse) or in a long-lived `HttpOnly` cookie.
- Client uses the refresh token to silently obtain new access tokens when the old one expires.
- Some systems put a longer expiry directly on the access token when Remember Me is checked (less ideal).

**Token lifetime summary**
| Token          | Remember Me off          | Remember Me on              |
|----------------|--------------------------|-----------------------------|
| Access JWT     | 5–15 min                 | still 5–15 min (preferred)  |
| Refresh token  | short / none             | days–weeks                  |

**If attacker copies the tokens**
- Access token → immediate access until it expires (minutes).
- Refresh token → can mint new access tokens for the entire lifetime of the refresh token → full account takeover for days/weeks.
- Because JWTs are usually self-contained, the server cannot easily revoke them unless it keeps a blocklist or uses short lifetimes + rotation.

### 3. Keycloak / OIDC / OAuth 2.0

This is the most common modern pattern (Authorization Code + PKCE + refresh tokens).

**Normal flow (Remember Me unchecked)**
- User authenticates at the IdP (Keycloak).
- Client receives:
  - Short-lived **access token** (JWT, ~5 min)
  - Short-lived **ID token**
  - Optionally a short-lived **refresh token**
- Tokens are kept in memory or non-persistent storage.
- Browser close → tokens gone → next visit requires interactive login again.

**Remember Me checked**
- Keycloak (or the IdP) issues a **long-lived refresh token** (or a long-lived session at the IdP).
- The refresh token is stored persistently (usually in an `HttpOnly` secure cookie or in the browser’s credential store).
- On subsequent visits the client silently uses the refresh token (or the SSO session cookie of the IdP) to obtain new access/ID tokens without showing a login form.
- Keycloak also has its own “Remember Me” checkbox that controls the SSO session lifetime at the IdP level.

**What happens to the tokens**
- Access token → always short-lived (even with Remember Me).
- Refresh token → becomes long-lived when Remember Me is selected.
- Keycloak can also keep a long-lived SSO session cookie on its own domain; that cookie is what actually provides the seamless experience across applications.

**If attacker copies the tokens**
- Access token → limited window (minutes).
- Refresh token → attacker can keep obtaining fresh access tokens until the refresh token expires or is revoked.
- If the attacker also steals the Keycloak SSO session cookie, they can get new tokens even more easily.
- Keycloak supports refresh-token rotation + reuse detection and server-side session revocation, which helps mitigate stolen tokens.

### Summary – Attacker Steals a Token

| Mechanism          | Stolen item              | Impact if Remember Me **off**      | Impact if Remember Me **on**              |
|--------------------|--------------------------|------------------------------------|-------------------------------------------|
| Session cookie     | Session ID cookie        | Short window (minutes–hours)       | Long window (days–weeks)                  |
| JWT                | Access token             | Minutes                            | Minutes                                   |
| JWT                | Refresh token            | Short / none                       | Days–weeks of full access                 |
| Keycloak/OIDC      | Access token             | Minutes                            | Minutes                                   |
| Keycloak/OIDC      | Refresh token / SSO cookie | Short / none                     | Days–weeks + possible silent re-auth      |

**Key practical takeaways**
- Remember Me almost always means “make the refresh token / session cookie long-lived and persistent”.
- Access tokens should stay short-lived regardless of Remember Me.
- Stealing a long-lived refresh token or remember-me cookie is almost as bad as stealing the password (until the token is revoked or expires).
- Best defenses: `HttpOnly` + `Secure` + `SameSite` cookies, short access-token lifetime, refresh-token rotation + reuse detection, server-side revocation, device/IP binding where possible, and never store long-lived tokens in `localStorage`.
