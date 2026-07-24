These three concepts are related, but they solve different problems in web applications.

Think of a website like a hotel.

* **Session Variable** = Information stored at the hotel reception desk.
* **Cookie** = A card given to the guest and carried by the guest.
* **Auth Token** = A special ID card proving the guest is authenticated.

---

# 1. Cookie

A cookie is a small piece of data stored in the user's browser.

### Example

You visit Amazon.

Server sends:

```http
Set-Cookie: theme=dark
```

Browser stores:

```text
theme=dark
```

Later, every request automatically includes:

```http
Cookie: theme=dark
```

Server can read it.

---

## What cookies are used for

### Remember user preferences

```text
theme=dark
language=en
```

### Remember login sessions

```text
session_id=abc123
```

### Shopping carts

```text
cart_id=xyz789
```

---

## Where is it stored?

Client side (browser).

```text
User Browser
 └── Cookies
      ├── theme=dark
      └── session_id=abc123
```

---

# 2. Session Variables

Session variables are data stored on the server.

The browser usually stores only a session identifier.

---

## Example

User logs in.

Server creates:

```python
sessions = {"abc123": {"user_id": 42, "username": "bhargav", "role": "admin"}}
```

Server sends cookie:

```http
Set-Cookie: session_id=abc123
```

Browser stores:

```text
session_id=abc123
```

---

Next request:

```http
Cookie: session_id=abc123
```

Server does:

```python
user = sessions["abc123"]
```

Result:

```python
{"user_id": 42, "username": "bhargav", "role": "admin"}
```

These values are session variables.

---

## Where are session variables stored?

Server side.

Could be in:

* Memory
* Redis
* Database
* File system

Example:

```text
Browser
   |
   | session_id=abc123
   v
Server
   |
   └── Session Store
           |
           ├── user_id=42
           ├── role=admin
           └── cart_items=[...]
```

---

# Cookie vs Session Variable

| Cookie                  | Session Variable   |
| ----------------------- | ------------------ |
| Stored in browser       | Stored on server   |
| User can see it         | User cannot see it |
| Limited size (~4 KB)    | Can be large       |
| Sent with every request | Not sent directly  |
| Less secure             | More secure        |

---

# 3. Auth Token

An auth token is proof that the user has successfully authenticated.

Instead of storing user data in a server-side session, the server issues a token.

---

## Example Login

User sends:

```json
{
  "username": "bhargav",
  "password": "secret"
}
```

Server verifies credentials and creates:

```text
eyJhbGciOiJIUzI1Ni...
```

This is a token (often JWT).

Server returns:

```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni..."
}
```

---

## Subsequent Requests

Client sends:

```http
Authorization: Bearer eyJhbGciOiJIUzI1Ni...
```

Server validates token.

If valid:

```python
user_id = 42
```

and processes the request.

---

# JWT Token Example

JWT contains 3 parts:

```text
header.payload.signature
```

Example:

```text
eyJhbGciOiJIUzI1Ni
.
eyJ1c2VyX2lkIjo0Miwicm9sZSI6ImFkbWluIn0
.
abcxyz123
```

Payload may contain:

```json
{
  "user_id": 42,
  "role": "admin",
  "exp": 1710000000
}
```

---

# Session-Based Authentication

Traditional approach.

### Login

```text
User Login
    |
    v
Server validates
    |
    v
Creates session
    |
    v
session_id=abc123
```

### Requests

```text
Browser
   |
   | session_id=abc123
   v
Server
   |
   └── lookup session store
```

---

# Token-Based Authentication

Modern API approach.

### Login

```text
User Login
   |
   v
Server validates
   |
   v
Creates JWT
```

### Requests

```text
Browser
   |
   | Bearer Token
   v
Server
   |
   └── validates JWT
```

No session lookup needed.

---

# FastAPI Example

## Login Endpoint

```python
@app.post("/login")
def login():
    token = create_jwt_token()

    return {"access_token": token}
```

---

## Protected Endpoint

```python
@app.get("/profile")
def profile(token: str = Depends(oauth2_scheme)):
    return {"message": "authenticated"}
```

FastAPI extracts:

```http
Authorization: Bearer <token>
```

and validates it.

---

# Real-World Flow

When you log into ChatGPT, Gmail, GitHub, etc.:

### Session-based

```text
Browser
    |
    └── Cookie(session_id)
            |
            v
         Server Session
```

### Token-based

```text
Browser
    |
    └── JWT Token
            |
            v
       Server validates
```

---

# Why Modern APIs Prefer Tokens

Imagine you have:

```text
10 API servers
```

With sessions:

```text
All servers must share session storage
(Redis usually)
```

With JWT:

```text
No shared session storage required
```

Any server can validate the token using the signing key.

This makes JWTs very popular in:

* FastAPI
* Spring Boot
* Node.js
* Microservices
* Mobile apps
* React frontends

---

## One-line Summary

* **Cookie** → Small data stored in the browser.
* **Session Variable** → User-specific data stored on the server and identified by a session ID.
* **Auth Token** → Proof of authentication (often a JWT) sent with requests to access protected resources.
