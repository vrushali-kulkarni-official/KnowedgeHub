Let's build this from **zero knowledge** and gradually reach the code.

---

# Part 1: What problem does CORS solve?

Imagine you have:

### Frontend

```text
http://localhost:3000
```

React application running in browser.

### Backend

```text
http://localhost:8000
```

FastAPI application.

Now your React app tries to call:

```javascript
fetch("http://localhost:8000/")
```

You might think:

> "Why wouldn't this work? Both are on my computer."

The answer is:

**The browser blocks it.**

Not FastAPI.
Not React.

The **browser** blocks it for security reasons.

---

# Part 2: Understanding Origins

An **Origin** is:

```text
Protocol + Domain + Port
```

Examples:

### Origin 1

```text
http://localhost:3000
```

Protocol:

```text
http
```

Domain:

```text
localhost
```

Port:

```text
3000
```

---

### Origin 2

```text
http://localhost:8000
```

Protocol:

```text
http
```

Domain:

```text
localhost
```

Port:

```text
8000
```

Different port.

Therefore:

```text
Different Origin
```

---

### Another example

```text
https://google.com
```

and

```text
http://google.com
```

Different protocol.

Therefore:

```text
Different Origin
```

---

# Part 3: Why browsers care

Imagine you're logged into:

```text
https://mybank.com
```

and have valid session cookies.

Now you visit:

```text
https://evil.com
```

Without protection, evil.com could run:

```javascript
fetch("https://mybank.com/transfer-money")
```

using your cookies.

That would be a disaster.

So browsers enforce:

```text
Same-Origin Policy
```

Meaning:

```text
A website cannot freely call APIs from another origin.
```

---

# Part 4: Enter CORS

CORS means:

```text
Cross-Origin Resource Sharing
```

It is a way for the backend to tell the browser:

> "Yes, I trust requests coming from this origin."

---

# Example

Frontend:

```text
http://localhost:3000
```

Backend:

```text
http://localhost:8000
```

Browser asks:

```text
Can localhost:3000 access localhost:8000?
```

FastAPI replies:

```text
Yes, I allow localhost:3000
```

Then browser allows the request.

This permission system is called:

```text
CORS
```

---

# Part 5: Without CORS

Suppose your React app does:

```javascript
fetch("http://localhost:8000/")
```

Request reaches FastAPI.

FastAPI returns:

```json
{
  "hello": "world"
}
```

But browser sees:

```text
No CORS permission.
```

and blocks the response.

Console error:

```text
Access-Control-Allow-Origin missing
```

---

# Part 6: What FastAPI does

Your code:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

adds a special middleware.

This middleware automatically adds headers to responses.

---

# What is a Header?

HTTP messages contain:

```text
Headers
Body
```

Example:

```http
GET / HTTP/1.1
Host: localhost:8000
```

Headers are metadata.

---

# Part 7: How CORS works internally

Browser sends:

```http
GET /
Origin: http://localhost:3000
```

Notice:

```http
Origin: http://localhost:3000
```

Browser tells backend:

> "I am coming from localhost:3000"

---

FastAPI responds:

```http
Access-Control-Allow-Origin: http://localhost:3000
```

Browser checks:

```text
Origin == Allowed Origin
```

If yes:

```text
Allow response
```

Otherwise:

```text
Block response
```

---

# Part 8: Understanding each option

## allow_origins

```python
allow_origins = ["http://localhost:3000"]
```

Meaning:

```text
Only localhost:3000 may call this API.
```

---

You can allow multiple:

```python
allow_origins = ["http://localhost:3000", "http://localhost:5173"]
```

---

Allow everything:

```python
allow_origins = ["*"]
```

Meaning:

```text
Everyone can call this API.
```

Usually okay for public APIs.

Not ideal for authenticated apps.

---

# allow_credentials

```python
allow_credentials = True
```

Credentials include:

* Cookies
* Session IDs
* Authorization headers

Example:

```javascript
fetch(url, {
  credentials: "include"
})
```

If credentials are used:

```python
allow_credentials = True
```

must be enabled.

---

# allow_methods

```python
allow_methods = ["*"]
```

Means:

```text
GET
POST
PUT
DELETE
PATCH
...
```

all allowed.

---

Restrict:

```python
allow_methods = ["GET", "POST"]
```

---

# allow_headers

```python
allow_headers = ["*"]
```

Allows custom headers.

Example:

```http
Authorization: Bearer abc123
```

or

```http
X-API-KEY: xyz
```

Without permission browser may block them.

---

# Part 9: What is Middleware?

Now let's move to middleware.

Think of middleware as a checkpoint.

---

Normal request flow:

```text
Client
   ↓
Route
   ↓
Response
```

With middleware:

```text
Client
   ↓
Middleware
   ↓
Route
   ↓
Middleware
   ↓
Response
```

Middleware runs:

```text
Before route
After route
```

---

# Real-life analogy

Airport:

```text
Passenger
   ↓
Security Check
   ↓
Gate
   ↓
Flight
```

Security check is middleware.

---

# Your Middleware

```python
@app.middleware("http")
async def add_process_time_header(request, call_next):
```

This function runs for every request.

---

# Step 1

Request arrives:

```http
GET /
```

Middleware executes.

---

# Step 2

```python
start = time.time()
```

Stores current time.

Example:

```python
1750845000.123
```

---

# Step 3

```python
response = await call_next(request)
```

This is the most important line.

It means:

```text
Continue to the next step.
```

In this case:

```python
@app.get("/")
def root():
    return {"hello": "world"}
```

gets executed.

---

Without:

```python
call_next(request)
```

the route never runs.

---

# Step 4

Route returns:

```python
{"hello": "world"}
```

FastAPI converts it to a response.

Execution returns back to middleware.

---

# Step 5

```python
duration = time.time() - start
```

Example:

```python
0.0023
```

seconds.

---

# Step 6

```python
response.headers["X-Process-Time"] = str(duration)
```

Adds a custom response header.

Response becomes:

```http
HTTP/1.1 200 OK

X-Process-Time: 0.0023
```

---

# Step 7

```python
return response
```

Response sent to browser.

---

# Complete Flow

```text
Browser
   ↓
Middleware starts timer
   ↓
call_next()
   ↓
Route executes
   ↓
Route returns response
   ↓
Middleware calculates duration
   ↓
Adds X-Process-Time header
   ↓
Browser receives response
```

---

# Why middleware is useful

Common uses:

### Logging

```python
print(request.url)
```

---

### Authentication

```python
Check JWT token
```

---

### Timing

```python
Measure response time
```

---

### Rate Limiting

```python
100 requests per minute
```

---

### Adding headers

```python
X - Request - ID
X - Process - Time
```

---

# In your code, what happens when GET / is called?

1. Browser sends request.
2. CORS middleware checks whether origin is allowed.
3. Your custom middleware starts timer.
4. Route executes.
5. Route returns `{"hello":"world"}`.
6. Custom middleware calculates duration.
7. Adds `X-Process-Time` header.
8. Response goes back.
9. Browser accepts response only if CORS rules allow that origin.

So **CORS middleware is mainly about security and cross-origin permissions**, while **your custom middleware is mainly about intercepting every request/response to perform common tasks like logging, timing, authentication, etc.**
