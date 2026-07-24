Great question. `request` and `call_next` are the two most important things to understand in FastAPI middleware.

Let's build the concept slowly.

---

# First, what is Middleware?

A middleware is simply **a function that runs before and after every request**.

Think of it like a security gate.

```
Client
   │
   ▼
──────────────
 Middleware
──────────────
   │
   ▼
 API Endpoint
   │
   ▼
──────────────
 Middleware
──────────────
   │
   ▼
Client
```

Every request passes through the middleware.

---

# Sample Middleware

```python
from fastapi import FastAPI, Request

app = FastAPI()


@app.middleware("http")
async def my_middleware(request: Request, call_next):
    print("Before endpoint")

    response = await call_next(request)

    print("After endpoint")

    return response
```

This middleware receives two arguments:

```
request
call_next
```

Let's understand each.

---

# What is `request`?

`request` is the **HTTP request object** that came from the client.

Suppose your browser sends

```
GET /users/10 HTTP/1.1

Host: localhost:8000

User-Agent: Chrome

Accept: application/json
```

FastAPI converts this raw HTTP request into a Python object.

That object is

```python
request
```

So

```
Raw HTTP Request
        │
        ▼
Request Object
```

---

Imagine someone orders pizza.

Instead of giving the chef a paper receipt, the waiter gives a proper order sheet.

The order sheet contains

* customer name
* pizza size
* toppings
* address

That order sheet is like the `Request` object.

---

# What information does `request` contain?

Lots.

Example:

```python
request.method
```

Output

```
GET
```

---

```python
request.url
```

Output

```
http://127.0.0.1:8000/users/10
```

---

```python
request.headers
```

Output

```
{
    "host": "127.0.0.1:8000",
    "user-agent": "Chrome",
    ...
}
```

---

```python
request.client
```

Output

```
127.0.0.1
```

---

```python
request.query_params
```

If request is

```
GET /items?id=20
```

Then

```python
request.query_params
```

returns

```
id=20
```

---

If the client sends JSON

```json
{
    "name":"John",
    "age":20
}
```

you can read it using

```python
body = await request.json()
```

---

So the Request object contains almost everything about the incoming request.

---

# Why does middleware receive the request?

Because middleware often needs information about the request.

Examples

Log every request

```python
print(request.url)
```

---

Allow only certain IPs

```python
print(request.client.host)
```

---

Check authentication

```python
print(request.headers["Authorization"])
```

---

Measure request size

```python
body = await request.body()
```

---

# Now what is `call_next`?

This is the part that confuses almost everyone initially.

Imagine this API.

```python
@app.get("/")
def home():
    return {"message": "Hello"}
```

Now middleware runs first.

```
Request
    │
    ▼
Middleware
    │
    ▼
Home Endpoint
```

How does middleware tell FastAPI

> "Okay, now continue to the endpoint."

That is exactly what `call_next()` does.

---

It literally means

> **Call the next thing in the request-processing chain.**

Usually the "next thing" is your endpoint (or another middleware if one exists).

---

# Visual

```
Request
   │
   ▼
Middleware
   │
   │ call_next()
   ▼
Endpoint
   │
   ▼
Response
   │
   ▼
Middleware
   │
   ▼
Client
```

---

# Example

```python
@app.middleware("http")
async def my_middleware(request: Request, call_next):

    print("Request received")

    response = await call_next(request)

    print("Response generated")

    return response
```

Client calls

```
GET /
```

Console

```
Request received
Response generated
```

because

```
Request
↓

Middleware
↓

call_next()

↓

Endpoint executes

↓

Endpoint returns response

↓

Middleware continues

↓

Returns response
```

---

# Why do we write

```python
await call_next(request)
```

instead of

```python
call_next(request)
```

Because `call_next()` is an **asynchronous function**.

It may need to wait for:

* database queries
* file reading
* network requests
* other async work

So middleware pauses until the endpoint finishes.

```
response = await call_next(request)
```

means

> "Wait until the endpoint finishes and gives me a response."

---

# What does `call_next()` return?

It returns the endpoint's **response**.

Example

Endpoint

```python
@app.get("/")
def home():
    return {"message": "Hello"}
```

Middleware

```python
response = await call_next(request)
```

Now

```
response
```

contains the HTTP response produced by the endpoint.

You can inspect or modify it before sending it to the client.

Example

```python
response.headers["X-Time"] = "10 ms"
```

Client receives

```
HTTP/1.1 200 OK

X-Time: 10 ms
```

---

# Can middleware stop the request?

Yes.

Instead of

```python
response = await call_next(request)
```

you can directly return a response.

Example

```python
from fastapi.responses import JSONResponse


@app.middleware("http")
async def block_everything(request: Request, call_next):

    return JSONResponse(content={"message": "Blocked"}, status_code=403)
```

Flow

```
Request

↓

Middleware

↓

Returns 403

↓

Endpoint never executes
```

So `call_next()` is optional if your middleware decides to end the request early.

---

# Real-life analogy

Imagine visiting a company office.

```
Visitor
   │
   ▼
Reception (Middleware)
```

The receptionist checks:

* your ID
* your appointment
* the time

Then says

```
Please go inside.
```

That is like

```python
await call_next(request)
```

You meet the employee (the endpoint).

The employee gives you a document (the response).

You return to reception.

The receptionist stamps the document.

Then gives it back to you.

```
Visitor
↓

Reception (before)

↓

Employee

↓

Reception (after)

↓

Visitor
```

---

# Summary

| Thing                      | What it is                                        | Purpose                                                                                                                                  |
| -------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `request`                  | The incoming HTTP request object                  | Lets middleware inspect details like method, URL, headers, cookies, body, query parameters, and client IP.                               |
| `call_next`                | A function provided by FastAPI                    | Passes the request to the next step (usually the endpoint) and returns the resulting response.                                           |
| `await call_next(request)` | Executes the rest of the request-processing chain | Waits for the endpoint to finish and gives the middleware the response so it can inspect or modify it before returning it to the client. |

A simple way to remember them is:

* **`request`** = "Here is everything the client sent."
* **`call_next(request)`** = "Continue processing this request and give me the response when you're done."
