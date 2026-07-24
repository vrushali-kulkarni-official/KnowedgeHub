In **FastAPI**, data is usually sent in the **request body** for `POST`, `PUT`, and `PATCH` requests.

## 1. Define a Pydantic Model

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class User(BaseModel):
    name: str
    age: int


@app.post("/users")
def create_user(user: User):
    return {"message": "User created", "user": user}
```

---

## 2. Send Request Body

### Using Postman

* Method: `POST`
* URL: `http://127.0.0.1:8000/users`
* Body → Raw → JSON

```json
{
    "name": "Bhargav",
    "age": 30
}
```

Response:

```json
{
    "message": "User created",
    "user": {
        "name": "Bhargav",
        "age": 30
    }
}
```

---

## 3. Using curl

```bash
curl -X POST "http://127.0.0.1:8000/users" \
-H "Content-Type: application/json" \
-d '{"name":"Bhargav","age":30}'
```

---

## 4. Using Python requests

```python
import requests

data = {"name": "Bhargav", "age": 30}

response = requests.post("http://127.0.0.1:8000/users", json=data)

print(response.json())
```

---

## 5. Without a Pydantic Model

You can also accept a raw dictionary:

```python
from fastapi import FastAPI

app = FastAPI()


@app.post("/users")
def create_user(user: dict):
    return user
```

Request:

```json
{
    "name": "Bhargav",
    "age": 30
}
```

However, this is **not recommended** because you lose:

* Validation
* Type checking
* Auto-generated documentation
* Better error messages

---

## 6. Multiple Fields Directly in Body

```python
from fastapi import Body


@app.post("/users")
def create_user(name: str = Body(), age: int = Body()):
    return {"name": name, "age": age}
```

Request:

```json
{
    "name": "Bhargav",
    "age": 30
}
```

---

## 7. Testing in Swagger UI

After starting FastAPI:

```bash
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

FastAPI automatically generates a form where you can enter the JSON body and test the API.

---

### Real-world pattern

Most FastAPI applications use a Pydantic model:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str


@app.post("/users")
def create_user(request: CreateUserRequest):
    return {"username": request.username, "email": request.email}
```

This is the standard approach you'll see in production FastAPI applications.
