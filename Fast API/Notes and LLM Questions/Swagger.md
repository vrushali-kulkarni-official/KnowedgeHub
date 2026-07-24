In FastAPI, **Swagger groups endpoints using `tags`**.

When you open:

* `/docs` → Swagger UI
* `/redoc` → ReDoc documentation

you'll notice that endpoints are organized into collapsible sections. These sections are created from the **`tags`** you assign to each path operation.

---

# Without Tags

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/users")
def get_users():
    return []


@app.post("/users")
def create_user():
    return {}
```

Swagger displays something like:

```
Default

GET   /users
POST  /users
```

Everything goes into a default section because no tags were provided.

---

# With Tags

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/users", tags=["Users"])
def get_users():
    return []


@app.post("/users", tags=["Users"])
def create_user():
    return {}
```

Swagger now displays:

```
Users
------
GET   /users
POST  /users
```

Both endpoints appear inside the **Users** section.

---

# Multiple Tags

An endpoint can belong to more than one group.

```python
@app.get("/profile", tags=["Users", "Authentication"])
def profile():
    return {}
```

Swagger shows this endpoint in **both** groups.

```
Users
------
GET /profile

Authentication
--------------
GET /profile
```

---

# Using APIRouter

Most real-world FastAPI applications use `APIRouter`.

Instead of adding tags to every endpoint, you assign them once when creating the router.

```python
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["Users"])
```

Now every endpoint inside the router automatically gets the `Users` tag.

```python
@router.get("/")
def get_users(): ...


@router.post("/")
def create_user(): ...
```

Swagger:

```
Users
------
GET  /users/
POST /users/
```

---

# Multiple Routers

A typical project structure looks like this:

```
app/
│
├── main.py
├── routers/
│   ├── users.py
│   ├── products.py
│   └── auth.py
```

### users.py

```python
router = APIRouter(prefix="/users", tags=["Users"])
```

### products.py

```python
router = APIRouter(prefix="/products", tags=["Products"])
```

### auth.py

```python
router = APIRouter(prefix="/auth", tags=["Authentication"])
```

Swagger displays:

```
Authentication
--------------
POST /auth/login
POST /auth/register

Users
------
GET /users
POST /users

Products
---------
GET /products
POST /products
```

Each router becomes its own logical section.

---

# Tag Metadata (Descriptions)

You can make the documentation more professional by defining metadata for each tag.

```python
from fastapi import FastAPI

tags_metadata = [
    {"name": "Users", "description": "Operations related to user accounts."},
    {"name": "Products", "description": "Manage product catalog."},
    {"name": "Authentication", "description": "Login, logout and JWT operations."},
]

app = FastAPI(openapi_tags=tags_metadata)
```

Swagger now shows:

```
Users
Operations related to user accounts.

GET /users
POST /users
```

---

# Order of Groups

The order of the sections is determined by the order in `openapi_tags`, **not** alphabetically.

```python
tags_metadata = [
    {"name": "Authentication"},
    {"name": "Users"},
    {"name": "Products"},
]
```

Swagger displays:

```
Authentication

Users

Products
```

---

# Best Practice for Large Projects

A common organization is:

```
app/
│
├── routers/
│   ├── auth.py
│   │
│   │ router = APIRouter(
│   │     prefix="/auth",
│   │     tags=["Authentication"]
│   │ )
│   │
│   ├── users.py
│   │
│   │ router = APIRouter(
│   │     prefix="/users",
│   │     tags=["Users"]
│   │ )
│   │
│   └── products.py
│       router = APIRouter(
│           prefix="/products",
│           tags=["Products"]
│       )
│
└── main.py
```

Then in `main.py`:

```python
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
```

This keeps your code modular, and Swagger automatically groups endpoints into **Authentication**, **Users**, and **Products** sections.

---

## Key Takeaways

* **`tags`** are what Swagger UI uses to group endpoints.
* Without tags, endpoints appear under a default group.
* You can assign tags per endpoint or once per `APIRouter`.
* An endpoint can have multiple tags and appear in multiple groups.
* `openapi_tags` lets you add descriptions and control the display order of the groups.
* In production applications, it's common to assign one tag per router (for example, `"Users"`, `"Products"`, `"Authentication"`), making the API documentation organized and easy to navigate.
