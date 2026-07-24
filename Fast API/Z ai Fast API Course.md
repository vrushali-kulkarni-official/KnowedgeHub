# 🚀 FastAPI: From Zero to Hero

I'll teach you FastAPI through 20 progressively harder levels. Each level introduces new concepts, building on the previous one. Save each example as a `.py` file and run with:

```bash
pip install fastapi uvicorn[standard]
uvicorn filename:app --reload
```

Then open `http://127.0.0.1:8000/docs` to see the auto-generated Swagger UI.

---

## 🟢 BEGINNER LEVEL

---

### **Level 1 — Hello World (The Basics)**

The smallest possible FastAPI app.

```python
# main.py
from fastapi import FastAPI

app = FastAPI()  # Creates the application instance


@app.get("/")  # Decorator: handles GET requests on "/"
def root():
    return {"message": "Hello, World!"}
```

**Concepts learned:**
- `FastAPI()` is the main app object
- `@app.get(path)` registers a path operation
- Functions can return dicts, lists, strings, numbers — FastAPI auto-converts to JSON
- Visit `/docs` for interactive API docs, `/redoc` for alternative docs

---

### **Level 2 — Path Parameters**

Variables in the URL path.

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/items/{item_id}")
def read_item(item_id: int):  # Type hint forces validation
    return {"item_id": item_id}


@app.get("/users/{username}")
def read_user(username: str):
    return {"user": username}
```

Try: `/items/5` ✅ | `/items/abc` ❌ (auto 422 error because `abc` is not int)

**Concepts learned:**
- Path parameters are extracted from `{}` in the route
- Type hints (`: int`, `: str`) enable automatic validation
- Invalid input returns a clean 422 error automatically

---

### **Level 3 — Query Parameters**

Parameters not in the path become query parameters.

```python
from fastapi import FastAPI

app = FastAPI()

items_db = ["apple", "banana", "cherry", "date", "elderberry"]


@app.get("/items/")
def list_items(skip: int = 0, limit: int = 10):
    # /items/?skip=1&limit=2
    return items_db[skip : skip + limit]


@app.get("/search/")
def search(q: str | None = None):
    # /search/?q=fastapi
    if q:
        return {"query": q}
    return {"query": "no query provided"}
```

**Concepts learned:**
- Parameters with default values → query params
- `str | None = None` makes it optional (Python 3.10+ syntax)
- `bool` is auto-converted (`true`, `True`, `1`, `yes` → True)

---

### **Level 4 — Combining Path & Query Parameters**

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/users/{user_id}/items/{item_id}")
def read_user_item(
    user_id: int, item_id: str, q: str | None = None, short: bool = False
):
    item = {"item_id": item_id, "owner_id": user_id}
    if q:
        item.update({"q": q})
    if not short:
        item.update({"description": "A long description..."})
    return item
```

Try: `/users/1/items/foo?q=hello&short=true`

**Concepts learned:**
- Path params and query params can mix freely
- Order matters: required path params, then optional query params
- FastAPI resolves them by name, not by position

---

### **Level 5 — Request Body (Pydantic Models)**

This is where FastAPI shines. Use Pydantic for structured data.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None


@app.post("/items/")
def create_item(item: Item):
    # FastAPI reads the JSON body and validates it against Item
    item_dict = item.model_dump()  # Convert Pydantic model to dict
    if item.tax:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict
```

Send POST with body:
```json
{ "name": "Laptop", "price": 999.99, "tax": 0.1 }
```

**Concepts learned:**
- `BaseModel` from Pydantic defines the shape of request data
- Type-annotated fields are validated automatically
- Default values make fields optional
- `model_dump()` converts a Pydantic model to a dict (Pydantic v2)

---

### **Level 6 — Path + Query + Body Together**

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item, q: str | None = None):
    result = {"item_id": item_id, **item.model_dump()}
    if q:
        result.update({"q": q})
    return result
```

**Concepts learned:**
- FastAPI auto-detects: path params (in path), Pydantic models (in body), primitives (as query)
- One endpoint can elegantly combine all three input sources

---

## 🟡 INTERMEDIATE LEVEL

---

### **Level 7 — Response Models**

Control what data is sent back to the client (hide secrets, etc.).

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class UserIn(BaseModel):
    username: str
    password: str  # sensitive!
    email: str


class UserOut(BaseModel):
    username: str
    email: str
    # No password!


@app.post("/users/", response_model=UserOut)
def create_user(user: UserIn):
    # We accept password but never return it
    return user  # FastAPI filters fields based on response_model


@app.get("/users/{id}", response_model=UserOut)
def get_user(id: int):
    # Even returning a dict works — FastAPI will filter
    return {"username": "alice", "email": "alice@example.com", "password": "secret"}
```

**Concepts learned:**
- `response_model` declares the output schema
- Sensitive fields are stripped automatically
- Works with dicts OR model instances as return values
- Shown in OpenAPI docs as the response schema

---

### **Level 8 — Parameter Validation**

Validate query/path parameters with constraints.

```python
from fastapi import FastAPI, Query, Path

app = FastAPI()


@app.get("/items/")
def read_items(
    q: str | None = Query(
        default=None,
        min_length=3,
        max_length=50,
        pattern="^fixedquery$",  # regex
        description="Search query string",
    ),
):
    return {"q": q}


@app.get("/items/{item_id}")
def read_item(
    item_id: int = Path(
        title="The ID of the item",
        ge=1,  # greater than or equal to 1
        le=1000,  # less than or equal to 1000
    ),
):
    return {"item_id": item_id}


@app.get("/numbers/")
def read_numbers(
    tags: list[str] = Query(default=[]),  # Multiple values: ?tags=a&tags=b
):
    return {"tags": tags}
```

**Concepts learned:**
- `Query()` and `Path()` add validation metadata
- `ge`, `le`, `gt`, `lt` for numeric constraints
- `min_length`, `max_length`, `pattern` for strings
- `list[str]` accepts repeated query params
- Title/description appear in API docs

---

### **Level 9 — Body Validation & Nested Models**

```python
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()


class Image(BaseModel):
    url: str
    name: str


class Item(BaseModel):
    name: str
    description: str | None = Field(default=None, title="Description", max_length=300)
    price: float = Field(gt=0, description="Price must be positive")
    tax: float | None = None
    tags: list[str] = []
    image: Image | None = None  # Nested model


@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    return {"item_id": item_id, "item": item}


# Body example using list of items
@app.post("/items/bulk")
def create_items(items: list[Item]):
    return {"created": len(items), "items": items}
```

Send:
```json
{
  "name": "Laptop",
  "price": 999.99,
  "tags": ["electronics", "premium"],
  "image": { "url": "http://x.com/img.png", "name": "laptop" }
}
```

**Concepts learned:**
- `Field()` validates Pydantic model fields
- Pydantic models can nest other models
- Body can be a `list[Model]` for bulk operations
- Deeply nested validation works out of the box

---

### **Level 10 — Form Data & File Uploads**

```python
from fastapi import FastAPI, Form, UploadFile, File

app = FastAPI()


@app.post("/login/")
def login(username: str = Form(), password: str = Form()):
    # Data sent as application/x-www-form-urlencoded, not JSON
    return {"username": username}


@app.post("/upload/")
async def upload_file(file: UploadFile = File()):
    # UploadFile is preferred over bytes — supports async, large files
    contents = await file.read()
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(contents),
    }


@app.post("/upload-multiple/")
async def upload_multiple(files: list[UploadFile]):
    return {"filenames": [f.filename for f in files]}
```

**Concepts learned:**
- `Form()` reads form-encoded fields (not JSON)
- `UploadFile` streams files efficiently (async)
- `await file.read()` reads bytes; for huge files use `await file.write()` to disk
- Multiple files via `list[UploadFile]`
- You cannot mix JSON body with form fields — pick one content type per endpoint

---

### **Level 11 — Error Handling**

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

items = {"apple": "A fruit", "banana": "Yellow and curved"}


@app.get("/items/{item_id}")
def read_item(item_id: str):
    if item_id not in items:
        raise HTTPException(
            status_code=404,
            detail="Item not found",
            headers={"X-Error": "Custom header"},
        )
    return {"item": items[item_id]}


# Custom exception with handler
class UnicornException(Exception):
    def __init__(self, name: str):
        self.name = name


@app.exception_handler(UnicornException)
async def unicorn_exception_handler(request, exc: UnicornException):
    return {"message": f"Oops, {exc.name} did a thing"}


@app.get("/unicorns/{name}")
def read_unicorn(name: str):
    if name == "yolo":
        raise UnicornException(name=name)
    return {"name": name}
```

**Concepts learned:**
- `HTTPException` is the standard way to return error responses
- Custom exception classes + `@app.exception_handler` for global handling
- `request` parameter gives access to the raw Request object
- You can attach custom headers to error responses

---

## 🟠 ADVANCED LEVEL

---

### **Level 12 — Dependency Injection Basics**

Reuse logic (auth, DB sessions, pagination) via dependencies.

```python
from fastapi import FastAPI, Depends, HTTPException

app = FastAPI()


# A dependency: a callable (function, class, etc.)
def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}


@app.get("/items/")
def read_items(commons: dict = Depends(common_parameters)):
    return {"message": "Hello items", "params": commons}


@app.get("/users/")
def read_users(commons: dict = Depends(common_parameters)):
    return {"message": "Hello users", "params": commons}
```

**Concepts learned:**
- `Depends()` injects a function's return value into your endpoint
- Dependencies themselves can have dependencies (recursive)
- Reduces boilerplate dramatically
- Dependencies can also raise exceptions (e.g., for auth checks)

---

### **Level 13 — Class Dependencies & Sub-dependencies**

```python
from fastapi import FastAPI, Depends, Cookie

app = FastAPI()


# Class-based dependency — reusable, can hold state
class CommonQueryParams:
    def __init__(self, q: str | None = None, skip: int = 0, limit: int = 100):
        self.q = q
        self.skip = skip
        self.limit = limit


@app.get("/items/")
def read_items(commons: CommonQueryParams = Depends(CommonQueryParams)):
    return {"q": commons.q, "skip": commons.skip, "limit": commons.limit}


# Sub-dependencies: dependencies using other dependencies
def query_extractor(q: str | None = None):
    return q


def query_validator(query: str = Depends(query_extractor)):
    if query == "admin":
        return "BLOCKED"
    return query


@app.get("/search/")
def search(validated: str = Depends(query_validator)):
    return {"query": validated}


# Using cookies as dependencies
def check_token(token: str | None = Cookie(default=None)):
    if token != "secret":
        raise Exception("Invalid token")
    return token
```

**Concepts learned:**
- Classes with `__init__` can be dependencies — parameters become the dependency's inputs
- Dependencies can depend on other dependencies
- `Cookie()`, `Header()` can be used inside dependencies
- Sub-dependency resolution is automatic and recursive

---

### **Level 14 — Dependencies with Yield (Resource Cleanup)**

Perfect for database sessions, file handles, transactions.

```python
from fastapi import FastAPI, Depends

app = FastAPI()


# Simulating a DB connection
def get_db():
    db = "DB Session Opened"
    try:
        print(f"[DB] {db}")
        yield db  # This value gets injected
    finally:
        print("[DB] Session Closed")  # Always runs after the request


@app.get("/items/")
def read_items(db=Depends(get_db)):
    return {"db_state": db}


@app.get("/users/")
def read_users(db=Depends(get_db)):
    return {"db_state": db}
```

**Concepts learned:**
- `yield` dependencies provide setup + teardown in one function
- The code before `yield` runs before the endpoint
- The code after `yield` (in `finally`) runs after, even on errors
- FastAPI handles exit stacks properly across nested dependencies

---

### **Level 15 — Middleware & CORS**

```python
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS — allow your frontend (React/Vue) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom middleware: log every request and add timing header
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)  # Run the actual route
    duration = time.time() - start
    response.headers["X-Process-Time"] = str(duration)
    print(f"{request.method} {request.url.path} → {duration:.4f}s")
    return response


@app.get("/")
def root():
    return {"hello": "world"}
```

**Concepts learned:**
- Middleware runs on every request before/after route handlers
- `@app.middleware("http")` registers a function with `(request, call_next)`
- `CORSMiddleware` is the standard solution for browser CORS issues
- You can modify both the request and response

---

### **Level 16 — Security: OAuth2 + JWT**

Production-grade authentication pattern.

```python
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

# pip install python-jose[cryptography] passlib[bcrypt]

app = FastAPI()

SECRET_KEY = "super-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Fake user DB
fake_users_db = {
    "alice": {
        "username": "alice",
        "hashed_password": pwd_context.hash("secret123"),
        "disabled": False,
    }
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str


def get_user(db, username: str):
    if username in db:
        return UserInDB(**db[username])


def authenticate_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user or not pwd_context.verify(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@app.post("/token", response_model=Token)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=User)
def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user
```

Test flow:
1. POST `/token` with form `username=alice&password=secret123` → get JWT
2. GET `/users/me` with header `Authorization: Bearer <token>`

**Concepts learned:**
- `OAuth2PasswordBearer` defines the auth scheme and token endpoint
- `OAuth2PasswordRequestForm` is a built-in form dependency for login
- `passlib` handles password hashing safely
- `python-jose` signs and verifies JWTs
- Security dependencies can be composed (`get_current_active_user` → `get_current_user`)
- `Annotated[T, Depends(...)]` is the modern (FastAPI 0.95+) syntax

---

### **Level 17 — Database Integration with SQLAlchemy**

```python
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session, Session as DBSession
from pydantic import BaseModel

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# SQLAlchemy ORM model
class UserORM(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)


Base.metadata.create_all(bind=engine)


# Pydantic schemas
class UserCreate(BaseModel):
    name: str
    email: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True  # Read from ORM objects


# DB dependency (yield-based)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()


@app.post("/users/", response_model=UserOut)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    existing = db.query(UserORM).filter(UserORM.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = UserORM(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users/", response_model=list[UserOut])
def list_users(db: Annotated[Session, Depends(get_db)]):
    return db.query(UserORM).all()


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = db.get(UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    user = db.get(UserORM, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"deleted": user_id}
```

**Concepts learned:**
- SQLAlchemy ORM maps Python classes to DB tables
- Pydantic schemas validate input/output; ORM models persist data — keep them separate
- `from_attributes = True` lets Pydantic read from ORM objects
- Yield-based `get_db` dependency ensures sessions are closed
- Full CRUD pattern with proper status codes

---

### **Level 18 — Bigger Apps: APIRouter & Project Structure**

Split code across multiple files.

```
project/
├── main.py
├── routers/
│   ├── __init__.py
│   ├── users.py
│   └── items.py
├── dependencies.py
```

```python
# dependencies.py
def pagination(skip: int = 0, limit: int = 10):
    return {"skip": skip, "limit": limit}
```

```python
# routers/users.py
from fastapi import APIRouter, Depends

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(lambda: True)],  # Apply to all routes here
    responses={404: {"description": "Not found"}},
)


@router.get("/")
def list_users():
    return [{"username": "alice"}, {"username": "bob"}]


@router.get("/{username}")
def get_user(username: str):
    return {"username": username}
```

```python
# routers/items.py
from fastapi import APIRouter

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/")
def list_items():
    return [{"name": "Apple"}, {"name": "Banana"}]
```

```python
# main.py
from fastapi import FastAPI
from routers import users, items

app = FastAPI()
app.include_router(users.router)
app.include_router(items.router)


@app.get("/")
def root():
    return {"message": "Welcome"}
```

**Concepts learned:**
- `APIRouter` is a mini-app: routes, tags, prefix, dependencies
- `include_router` mounts it under the main app
- `prefix` applies to all routes in the router
- `tags` group routes in the docs
- Project stays maintainable as it grows

---

### **Level 19 — Background Tasks**

Run things after the response is sent (emails, webhooks, logs).

```python
import time
from fastapi import FastAPI, BackgroundTasks

app = FastAPI()


def write_log(message: str):
    time.sleep(2)  # simulate slow IO
    with open("log.txt", "a") as f:
        f.write(f"{message}\n")


def send_email(email: str, message: str):
    print(f"Sending to {email}: {message}")


@app.post("/send-notification/{email}")
def send_notification(email: str, background_tasks: BackgroundTasks):
    # These run AFTER the response is returned
    background_tasks.add_task(write_log, f"Notified {email}")
    background_tasks.add_task(send_email, email, "Hello!")
    return {"message": "Notification queued"}
```

**Concepts learned:**
- `BackgroundTasks` runs functions after the response
- Multiple tasks can be queued; they run in order
- For heavy/long tasks, prefer Celery or RQ — BackgroundTasks is for lightweight work
- No external broker needed (unlike Celery)

---

### **Level 20 — Testing, Async, & WebSockets**

The final boss level.

```python
# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient
import asyncio

app = FastAPI()


# 1. Async endpoints
@app.get("/slow")
async def slow():
    await asyncio.sleep(1)  # Non-blocking!
    return {"message": "done"}


# 2. WebSocket endpoint
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: str):
        for ws in self.active:
            await ws.send_text(message)


manager = ConnectionManager()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(ws: WebSocket, client_id: int):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            await manager.broadcast(f"Client {client_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast(f"Client {client_id} left")


# 3. Tests
client = TestClient(app)  # Synchronous test client — no server needed!


def test_slow():
    response = client.get("/slow")
    assert response.status_code == 200
    assert response.json() == {"message": "done"}


def test_websocket():
    with client.websocket_connect("/ws/1") as ws:
        ws.send_text("Hello")
        data = ws.receive_text()
        assert "Hello" in data


if __name__ == "__main__":
    test_slow()
    test_websocket()
    print("All tests passed ✅")
```

Run with `python main.py` — it'll execute the tests directly.

**Concepts learned:**
- `async def` + `await` for non-blocking IO (DB drivers, HTTP clients, file IO)
- `WebSocket` enables real-time bidirectional communication
- `WebSocketDisconnect` handles client drops gracefully
- `TestClient` lets you test the app synchronously without spinning up a server
- WebSockets can also be tested via `client.websocket_connect()`

---

## 🎓 What's Next?

Now that you've completed all 20 levels, explore:

| Topic | Library / Approach |
|---|---|
| Async DB | `databases`, `SQLAlchemy 2.0 async`, `Tortoise ORM` |
| Task queues | `Celery`, `RQ`, `Dramatiq` |
| Caching | `fastapi-cache2`, Redis |
| Rate limiting | `slowapi` |
| OpenTelemetry | Distributed tracing |
| GraphQL | `strawberry-graphql` + FastAPI integration |
| Deployment | `gunicorn -k uvicorn.workers.UvicornWorker` behind Nginx |
| Docker | Multi-stage builds with `tiangolo/uvicorn-gunicorn-fastapi` |

### 🧠 Mental Model Summary

1. **Endpoints** = decorated functions (`@app.get`, `@app.post`, ...)
2. **Validation** = type hints + Pydantic models
3. **Reusability** = `Depends()` for shared logic
4. **Errors** = `HTTPException` + custom exception handlers
5. **Real-time** = `WebSocket` endpoints
6. **Async** = `async def` + `await` for IO-bound work
7. **Docs** = auto-generated at `/docs` from your type hints

Practice by building these projects in order:
- 📘 A **TODO API** (Levels 1–11)
- 🔐 An **auth system** (Levels 12–16)
- 🛒 A **mini e-commerce backend** (Levels 17–20)

Pick any level you want me to expand with more examples, edge cases, or real-world patterns — I'll go deeper!