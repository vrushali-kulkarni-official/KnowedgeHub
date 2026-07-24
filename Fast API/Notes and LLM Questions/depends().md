Let's start from **zero assumptions** and build up slowly.

# Step 1: What is a Cookie?

A cookie is a small piece of data stored by the browser.

For example, after you log in to a website, the server may tell the browser:

```http
Set-Cookie: token=abc123
```

The browser stores:

```text
token = abc123
```

locally.

---

# Step 2: Why do cookies exist?

HTTP is stateless.

Imagine:

### Request 1

```http
POST /login
username=bhargav
password=123
```

Server verifies credentials and responds:

```http
Set-Cookie: token=abc123
```

Browser stores:

```text
token = abc123
```

---

### Request 2

Later the browser calls:

```http
GET /profile
```

How does the server know this is Bhargav?

The browser automatically sends:

```http
GET /profile
Cookie: token=abc123
```

The server reads the cookie and identifies the user.

---

# Step 3: What does the browser actually send?

Suppose the browser has stored:

```text
token=abc123
theme=dark
language=en
```

Every request to that site may include:

```http
Cookie: token=abc123; theme=dark; language=en
```

Notice:

```text
Cookie:
```

contains multiple name-value pairs.

---

# Step 4: Which cookie is FastAPI reading?

Look at your code:

```python
def check_token(
    token: str | None = Cookie(default=None)
):
```

The variable name is:

```python
token
```

FastAPI assumes:

> "I need a cookie named `token`."

So if the request contains:

```http
Cookie: token=abc123
```

FastAPI extracts:

```python
token = "abc123"
```

and passes it to the function.

---

# Step 5: How does FastAPI know which cookie to use?

It uses the parameter name.

Example:

```python
def my_func(
    token: str = Cookie()
):
```

Looks for:

```http
Cookie: token=...
```

---

Example:

```python
def my_func(
    session_id: str = Cookie()
):
```

Looks for:

```http
Cookie: session_id=...
```

---

Example:

```python
def my_func(
    language: str = Cookie()
):
```

Looks for:

```http
Cookie: language=...
```

---

The parameter name determines the cookie name.

---

# Step 6: Let's simulate a request

Suppose browser sends:

```http
GET /items

Cookie: token=secret
```

FastAPI sees:

```python
token: str | None = Cookie(default=None)
```

It searches cookies for:

```text
token
```

Finds:

```text
token=secret
```

Then executes:

```python
check_token(token="secret")
```

---

# Step 7: What if browser sends another value?

Browser:

```http
Cookie: token=abc123
```

FastAPI executes:

```python
check_token(token="abc123")
```

Inside function:

```python
if token != "secret":
```

becomes:

```python
if "abc123" != "secret":
```

which is True.

Exception raised.

---

# Step 8: What if cookie doesn't exist?

Browser sends:

```http
GET /items
```

No cookies.

FastAPI cannot find:

```text
token
```

Because:

```python
Cookie(default=None)
```

says:

> If missing, use None.

So FastAPI executes:

```python
check_token(token=None)
```

Then:

```python
if None != "secret":
```

Exception raised.

---

# Step 9: Where did "secret" come from?

This is what confuses many beginners.

Look carefully:

```python
if token != "secret":
```

The string:

```python
"secret"
```

is NOT a cookie.

It is just a hardcoded value written by the programmer.

The programmer is saying:

```python
Only allow requests whose cookie value equals "secret"
```

---

Example:

Browser sends:

```http
Cookie: token=secret
```

Allowed.

---

Browser sends:

```http
Cookie: token=hello
```

Rejected.

---

Browser sends:

```http
Cookie: token=xyz
```

Rejected.

---

# Step 10: Real-world authentication

In production you would not do:

```python
if token != "secret":
```

Instead:

```python
def check_token(token: str | None = Cookie(default=None)):
    
    if token is None:
        raise HTTPException(401)

    user = verify_jwt_token(token)

    if not user:
        raise HTTPException(401)

    return user
```

Now the cookie might contain:

```text
eyJhbGciOi...
```

which is a JWT token.

---

# Step 11: Why put this inside a dependency?

Suppose you have:

```python
GET / profile
GET / orders
GET / cart
GET / wishlist
```

All require authentication.

Without dependency:

```python
@app.get("/profile")
def profile(token: str = Cookie()):
    validate(token)
```

```python
@app.get("/orders")
def orders(token: str = Cookie()):
    validate(token)
```

```python
@app.get("/cart")
def cart(token: str = Cookie()):
    validate(token)
```

Same code repeated.

---

Instead:

```python
def check_token(token: str = Cookie()):
    validate(token)
    return token
```

Then:

```python
@app.get("/profile")
def profile(token=Depends(check_token)): ...
```

```python
@app.get("/orders")
def orders(token=Depends(check_token)): ...
```

```python
@app.get("/cart")
def cart(token=Depends(check_token)): ...
```

FastAPI automatically:

1. Reads cookie.
2. Calls `check_token()`.
3. Validates token.
4. Gives result to endpoint.

---

### Visual Flow

Request:

```http
GET /profile

Cookie: token=secret
```

FastAPI:

```text
Request arrives
      ↓
Find cookie named "token"
      ↓
token="secret"
      ↓
Call check_token(token)
      ↓
Validation succeeds
      ↓
Return "secret"
      ↓
Inject into profile()
      ↓
Execute profile()
```

The key idea is:

```python
token: str | None = Cookie(default=None)
```

does **not create a cookie**.

It tells FastAPI:

> "Look inside the incoming request's Cookie header and fetch the cookie named `token`."
