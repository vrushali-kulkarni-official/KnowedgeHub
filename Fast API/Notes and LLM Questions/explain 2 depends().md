Great question. `Depends()` is one of the most important concepts in FastAPI, and it can feel confusing at first because it introduces **Dependency Injection**.

Let's build the understanding step by step.

---

# Step 1: What problem are we trying to solve?

Imagine you have 100 APIs.

```python
@app.get("/items")
def get_items():
    db = connect_to_db()
    ...
    close_db()


@app.get("/users")
def get_users():
    db = connect_to_db()
    ...
    close_db()


@app.get("/orders")
def get_orders():
    db = connect_to_db()
    ...
    close_db()
```

Notice the repetition:

* Open DB connection
* Use DB
* Close DB

Every API repeats the same code.

This is bad.

---

# Step 2: Move common code into a function

```python
def get_db():
    db = "DB Session Opened"
    return db
```

Now every endpoint can call it.

```python
@app.get("/items")
def get_items():
    db = get_db()
    return {"db": db}
```

Works.

But FastAPI gives us a cleaner way.

---

# Step 3: Enter Depends()

Instead of calling:

```python
db = get_db()
```

you tell FastAPI:

```python
db = Depends(get_db)
```

Example:

```python
@app.get("/items")
def get_items(db=Depends(get_db)):
    return {"db": db}
```

This means:

> "Hey FastAPI, before running this endpoint, call `get_db()` and give me its result inside the variable `db`."

You don't call `get_db()` yourself.

FastAPI does it for you.

---

# Step 4: What actually happens?

You write:

```python
@app.get("/items")
def read_items(db=Depends(get_db)):
    return {"db_state": db}
```

User calls:

```text
GET /items
```

FastAPI internally does something like:

```python
db = get_db()

response = read_items(db)

return response
```

So your function effectively becomes:

```python
def read_items(db="DB Session Opened"):
    return {"db_state": db}
```

---

# Step 5: Understanding your code

Your dependency:

```python
def get_db():
    db = "DB Session Opened"

    try:
        print(f"[DB] {db}")
        yield db

    finally:
        print("[DB] Session Closed")
```

Your endpoint:

```python
@app.get("/items/")
def read_items(db=Depends(get_db)):
    return {"db_state": db}
```

---

When request arrives:

```text
GET /items
```

FastAPI:

### 1. Calls get_db()

```python
db = "DB Session Opened"
```

---

### 2. Executes before yield

```python
print("[DB] DB Session Opened")
```

Output:

```text
[DB] DB Session Opened
```

---

### 3. Reaches yield

```python
yield db
```

Value yielded:

```python
"DB Session Opened"
```

FastAPI injects it into:

```python
db = Depends(get_db)
```

So endpoint receives:

```python
db = "DB Session Opened"
```

---

### 4. Endpoint runs

```python
return {"db_state": "DB Session Opened"}
```

Response:

```json
{
  "db_state": "DB Session Opened"
}
```

---

### 5. Endpoint finishes

After response is generated, FastAPI goes back to the dependency.

Execution resumes after `yield`.

```python
finally:
    print("[DB] Session Closed")
```

Output:

```text
[DB] Session Closed
```

---

# Step 6: Why use yield instead of return?

If you write:

```python
def get_db():
    db = "DB Session Opened"
    return db
```

FastAPI gets the value.

But there's no cleanup.

---

With:

```python
yield db
```

FastAPI can:

1. Open resource
2. Give it to endpoint
3. Automatically clean it up later

This is perfect for:

* Database sessions
* File handles
* Network connections
* Transactions

---

# Step 7: Visual flow

```text
Request arrives
       |
       V
   get_db()
       |
       V
Open DB
       |
       V
yield db
       |
       V
read_items(db)
       |
       V
Response generated
       |
       V
Resume get_db()
       |
       V
Close DB
```

---

# Step 8: Why is it called Dependency?

Because your endpoint depends on something.

This endpoint:

```python
def read_items(db=Depends(get_db)):
```

depends on:

```python
get_db()
```

Without a database object, it cannot work.

So `get_db` is called a **dependency**.

---

# Step 9: Multiple endpoints using same dependency

```python
@app.get("/items/")
def read_items(db=Depends(get_db)):
    return {"db_state": db}


@app.get("/users/")
def read_users(db=Depends(get_db)):
    return {"db_state": db}
```

Now both endpoints reuse the same logic.

Request:

```text
GET /items
```

Output:

```text
[DB] DB Session Opened
[DB] Session Closed
```

---

Request:

```text
GET /users
```

Output:

```text
[DB] DB Session Opened
[DB] Session Closed
```

Each request gets its own dependency execution.

---

# Real-world example

A real database session dependency often looks like:

```python
from sqlalchemy.orm import Session


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
```

Endpoint:

```python
@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

FastAPI automatically:

```text
Open session
    ↓
Inject session
    ↓
Run endpoint
    ↓
Close session
```

This is one of the biggest reasons FastAPI code stays clean and scalable.

**Rule to remember:**

```python
db = Depends(get_db)
```

means:

> "FastAPI, execute `get_db()`, take whatever it yields/returns, and pass it into the `db` parameter before running this endpoint."
