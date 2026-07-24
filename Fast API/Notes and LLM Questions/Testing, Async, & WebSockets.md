This is one of the last major concepts you need to understand to become comfortable with FastAPI.

These three topics are related, but each solves a completely different problem:

| Topic          | Purpose                                                       |
| -------------- | ------------------------------------------------------------- |
| **Async**      | Handle many requests efficiently without blocking the server  |
| **WebSockets** | Keep a permanent two-way connection between client and server |
| **Testing**    | Verify your API works correctly automatically                 |

We'll go through them in the order they're normally learned.

---

# Part 1 — Async in FastAPI

Before understanding FastAPI, you need to understand one question:

> **What happens when one request takes a long time?**

Imagine your endpoint:

```python
@app.get("/slow")
def slow():
    time.sleep(5)
    return {"message": "done"}
```

Now suppose three users call this endpoint simultaneously.

```
User 1 -----> waiting 5 sec
User 2 -----> waiting...
User 3 -----> waiting...
```

If your server handles only one request at a time, everyone waits.

This is called **blocking**.

---

## Blocking Example

Imagine a restaurant.

There is only one chef.

```
Customer 1 orders pizza
Chef starts making it (10 min)

Customer 2 arrives
Must wait.

Customer 3 arrives
Must wait.
```

Everyone waits because the chef cannot do anything else.

That's synchronous execution.

---

# What is Async?

Async allows the server to do something else while waiting.

Imagine the chef.

Instead of standing and watching the pizza bake...

```
Put pizza in oven

↓

Go prepare another order

↓

Come back when pizza is ready
```

Nobody wastes time.

The oven works.

The chef works.

Everyone is happier.

---

## In Python

Normal function

```python
def hello():
    return "Hello"
```

Async function

```python
async def hello():
    return "Hello"
```

The keyword

```
async
```

means

> This function may pause while waiting.

---

# await

Inside async functions we use

```python
await
```

Example

```python
await asyncio.sleep(1)
```

This means

> Pause THIS function until the operation finishes,
>
> but allow the server to work on other requests.

This is the most important idea.

---

## Difference

Blocking sleep

```python
time.sleep(5)
```

Server freezes.

Nothing else happens.

---

Async sleep

```python
await asyncio.sleep(5)
```

Current request pauses.

Other requests continue running.

Huge difference.

---

# Your code

```python
@app.get("/slow")
async def slow():
    await asyncio.sleep(1)
    return {"message": "done"}
```

Flow:

```
Client
   │
   ▼
GET /slow

Server enters function

↓

await asyncio.sleep(1)

↓

Current request pauses

↓

Server handles other requests

↓

1 second later

↓

Continue execution

↓

Return response
```

No thread is blocked.

---

# Why FastAPI loves async

FastAPI is built on

```
ASGI
```

instead of WSGI.

ASGI was designed specifically for asynchronous applications.

This is why FastAPI performs extremely well.

---

# When should you use async?

Use async whenever you're waiting for something.

Examples:

✔ Database

```python
await db.fetch(...)
```

---

✔ HTTP request

```python
await client.get(...)
```

---

✔ Redis

```python
await redis.get(...)
```

---

✔ File upload

```python
await file.read()
```

---

Don't use async for CPU-heavy work.

Example

```python
for i in range(1_000_000_000):
    ...
```

Async won't make calculations faster.

---

# Part 2 — WebSockets

Now let's learn something much cooler.

Normally HTTP works like this:

```
Browser

↓

Request

↓

Server

↓

Response

↓

Connection closes
```

Every request creates a new connection.

---

Suppose you're building

* WhatsApp
* Discord
* Multiplayer game
* Live stock market
* Live cricket scores

Should the browser ask every second

```
Any message?

Any message?

Any message?

Any message?
```

That's inefficient.

---

Instead we keep one connection alive.

```
Browser
      ⇅
Server
```

Both sides can send messages anytime.

This is called

> WebSocket

---

## HTTP

```
Request

↓

Response

↓

Done
```

---

## WebSocket

```
Connect

↓

Stay connected

↓

Client sends

↓

Server sends

↓

Client sends

↓

Server sends

↓

Repeat forever
```

---

# Your endpoint

```python
@app.websocket("/ws/{client_id}")
```

Notice

Not

```python
@app.get()
```

Instead

```python
@app.websocket()
```

because this endpoint speaks the WebSocket protocol.

---

# Step 1

```python
await manager.connect(ws)
```

Let's see connect()

```python
async def connect(self, ws):
    await ws.accept()
    self.active.append(ws)
```

The first thing is

```python
await ws.accept()
```

The server accepts the WebSocket handshake.

Before this,

```
Client:
Can we upgrade to WebSocket?

Server:
Yes.
```

After

```
accept()
```

the permanent connection exists.

---

Then

```python
self.active.append(ws)
```

stores the connected client.

Suppose three clients connect.

```
active = [

Client1,

Client2,

Client3

]
```

Now the server knows everybody.

---

# Infinite loop

```python
while True:
```

Why infinite?

Because WebSockets don't finish after one message.

Instead

```
Hello

↓

How are you?

↓

Good

↓

Bye
```

Many messages.

---

Receiving

```python
data = await ws.receive_text()
```

Wait until the client sends something.

```
Client

↓

Hello
```

Server receives

```
Hello
```

---

Broadcast

```python
await manager.broadcast(...)
```

Broadcast means

Send to everyone.

---

Inside

```python
for ws in self.active:
    await ws.send_text(message)
```

Imagine

```
Client A
Client B
Client C
```

Client A says

```
Hello
```

Server sends

```
Hello
```

to

```
A

B

C
```

Everyone receives it.

That's exactly how chat applications work.

---

# Disconnect

Suppose someone closes the browser.

```
WebSocketDisconnect
```

is raised.

Your code

```python
except WebSocketDisconnect:
```

runs.

Then

```python
manager.disconnect(ws)
```

removes them from

```
active
```

Then broadcasts

```
Client left
```

to everyone.

---

# Overall WebSocket Flow

```
Client connects

↓

accept()

↓

Store connection

↓

Loop forever

↓

Receive message

↓

Broadcast

↓

Receive message

↓

Broadcast

↓

Disconnect

↓

Remove connection

↓

Notify everyone
```

---

# Part 3 — Testing

Testing is one of the biggest reasons FastAPI is loved in production.

Instead of manually opening

```
localhost:8000/docs
```

and clicking every endpoint...

we write automated tests.

---

# TestClient

```python
client = TestClient(app)
```

This creates a fake client.

It behaves like a browser.

No server is needed.

```
Your code

↓

Fake HTTP request

↓

FastAPI app

↓

Response
```

Everything happens in memory.

Very fast.

---

# Testing /slow

```python
response = client.get("/slow")
```

Equivalent to

```
GET

http://localhost:8000/slow
```

except no network is involved.

---

Check status

```python
assert response.status_code == 200
```

Meaning

```
Did the endpoint succeed?
```

---

Check body

```python
assert response.json() == {"message": "done"}
```

If the endpoint accidentally returns

```python
{"hello": "world"}
```

The test fails immediately.

---

# Testing WebSockets

```python
with client.websocket_connect("/ws/1") as ws:
```

Creates a fake WebSocket connection.

Exactly like a browser.

---

Send message

```python
ws.send_text("Hello")
```

Server receives

```
Hello
```

---

Receive

```python
data = ws.receive_text()
```

Server broadcasts

```
Client 1: Hello
```

Test receives it.

---

Verify

```python
assert "Hello" in data
```

If not,

the test fails.

---

# Why Tests Matter

Imagine you have

```
100 endpoints

15 developers

200 users
```

Someone changes one endpoint.

Suddenly login breaks.

Without tests:

```
Users discover the bug.
```

With tests:

```
CI/CD runs tests

↓

Failure detected

↓

Deployment blocked
```

That's why production projects have hundreds or thousands of tests.

---

# Visual Summary

```
                   FastAPI

                      │
     ┌────────────────┼────────────────┐
     │                │                │
     ▼                ▼                ▼

   Async         WebSockets        Testing

async def      Persistent        TestClient

await          Two-way           Fake browser

Non-blocking   Live updates      Assertions

Many users     Chat apps         Prevent bugs

Database       Games             CI/CD

HTTP calls     Notifications     Regression testing
```

---

# How These Concepts Work Together

Imagine you're building a real-time chat application:

1. A user opens the chat page, and the browser establishes a **WebSocket** connection to `/ws/{client_id}`. The server accepts the connection and keeps it open.

2. When the user sends a message, the server uses **`await ws.receive_text()`** to wait for incoming messages without blocking other clients. While one client is idle, the server can continue handling HTTP requests and messages from other WebSocket connections thanks to **async**.

3. The server broadcasts the message to all connected clients using `await manager.broadcast(...)`, so everyone sees the new message instantly.

4. To ensure everything works correctly, you write **tests** with `TestClient`:

   * Verify that `/slow` returns the expected JSON.
   * Verify that a WebSocket client can connect, send a message, receive the broadcast, and handle disconnects correctly.

This combination—**async for scalability**, **WebSockets for real-time communication**, and **automated testing for reliability**—is a common pattern in production FastAPI applications such as chat systems, live dashboards, multiplayer games, collaborative editors, and notification services.
