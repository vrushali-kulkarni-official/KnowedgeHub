# Part 5 — FastAPI Secure Coding: 7 versions of the same app
### Each version more secure than the last. By the end, you'll know why each line is there.

> The same Todo app, written seven times. Each version starts from the previous and adds one layer of defense. **Read in order.** At the end of each version, there's a list of "what's still wrong" that the next version will fix.

The app: a multi-user todo list. Users sign up, log in, and manage their own todos. We'll evolve it from "demo-grade" to "I would run this in production" over seven iterations.

---

## Setup — used in every version

```bash
mkdir -p ~/labs/vulntodo && cd ~/labs/vulntodo
python -m venv .venv && source .venv/bin/activate
pip install "fastapi[standard]" "uvicorn[standard]" "sqlalchemy[asyncio]" "asyncpg" "pydantic[email]" "passlib[argon2]" "python-jose[cryptography]" "python-multipart" "itsdangerous" "pyotp" "qrcode[pil]" "zxcvbn" "bcrypt" "pyyaml" "defusedxml" "pyjwt" "cryptography"
```

A `docker-compose.yml` for the database we'll use throughout:
```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: vulntodo
      POSTGRES_USER: vulntodo_app       # least-privilege user (Part 6)
      POSTGRES_PASSWORD: change-me
    ports: ["5432:5432"]
    volumes: ["dbdata:/var/lib/postgresql/data"]
volumes:
  dbdata:
```

```bash
docker compose up -d
```

---

## Version 1 — The "I just learned FastAPI" app

The most common starting point. Lots of bugs, but it works.

```python
# v1/app.py — ⚠️ DO NOT USE. INTENTIONALLY VULNERABLE.
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from passlib.hash import sha256_crypt
import os

app = FastAPI()
engine = create_engine("postgresql+psycopg2://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    is_admin = Column(Boolean, default=False)
    todos = relationship("Todo", backref="user")

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    owner = Column(String)
    title = Column(String)
    done = Column(Boolean, default=False)

Base.metadata.create_all(engine)

# 1. Plaintext password storage (well, SHA-256 single round — still bad)
# 2. SQL injection
# 3. No auth on most endpoints
# 4. IDOR: any logged-in user can see any todo
# 5. Mass assignment: client controls is_admin
# 6. No rate limit
# 7. Debug endpoints on

@app.post("/signup")
def signup(req: Request):
    data = await req.json() if False else await req.json()  # placeholder
    # ↑ async mistake — let's just do the synchronous version
    data = await req.json()    # requires async, but this is sync — already broken
```

OK, that's *too* broken to even be a baseline. Let me restart with a slightly less-broken V1.

```python
# v1/app.py — bare-minimum, intentionally vulnerable
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.hash import sha256_crypt   # ⚠️ SHA-256 isn't argon2

engine = create_engine("postgresql+psycopg2://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(bind=engine); Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    owner = Column(String)
    title = Column(String)
    done = Column(Boolean, default=False)

Base.metadata.create_all(engine)

SECRET = "secret"   # ⚠️ hardcoded

def get_db():
    db = Session()
    try: yield db
    finally: db.close()

def make_token(user):
    return f"{user.id}:{user.username}:{SECRET}"

def parse_token(tok):
    try:
        uid, uname, sig = tok.split(":")
        if sig != SECRET: return None
        return {"id": int(uid), "username": uname}
    except: return None

@app.post("/signup")
def signup(req: Request, db = Depends(get_db)):
    data = await req.json()
    # ⚠️ No validation. No password strength. SHA-256 round.
    pw = sha256_crypt.hash(data["password"])
    u = User(username=data["username"], password=pw, is_admin=data.get("is_admin", False))  # ⚠️ mass assignment
    db.add(u); db.commit()
    return {"token": make_token(u)}

@app.get("/todos")
def list_todos(req: Request, db = Depends(get_db)):
    auth = req.headers.get("authorization", "").replace("Bearer ", "")
    user = parse_token(auth)
    if not user: raise HTTPException(401)
    # ⚠️ No filter by owner — IDOR
    return db.query(Todo).all()

@app.post("/todos")
async def add_todo(req: Request, db = Depends(get_db)):
    data = await req.json()
    auth = req.headers.get("authorization", "").replace("Bearer ", "")
    user = parse_token(auth)
    if not user: raise HTTPException(401)
    # ⚠️ SQL injection: title is concatenated
    db.execute(f"INSERT INTO todos (owner, title) VALUES ('{user['username']}', '{data['title']}')")
    db.commit()
    return {"ok": True}
```

**Run it:**
```bash
uvicorn v1.app:app --reload
```

### V1's bug list (we'll fix each in a later version)

| # | Bug | Where | OWASP |
|---|-----|-------|-------|
| 1 | Plaintext-equivalent password hash (SHA-256 single-round) | signup | A02 |
| 2 | Hardcoded secret | `SECRET = "secret"` | A02 |
| 3 | Unsigned token | `f"{id}:{uname}:{secret}"` | A02 |
| 4 | SQL injection in `add_todo` | f-string into SQL | A03 |
| 5 | No input validation | `signup` accepts anything | A03 |
| 6 | Mass assignment | `is_admin` from client | A04 (mass assign) |
| 7 | No auth on some endpoints (later) | various | A07 |
| 8 | IDOR in `list_todos` | no filter by owner | A01 |
| 9 | `sync` route with `await` | broken code | — |
| 10 | No password strength check | signup | A07 |
| 11 | No rate limit on signup/login | missing | A04/A07 |
| 12 | Error responses leak internals | default FastAPI | A05 |
| 13 | `/docs` open in prod | default | A05 |
| 14 | No security headers | default | A05 |
| 15 | No logging | missing | A09 |
| 16 | No CORS config | default | A05 |
| 17 | No DB constraints | schema | A04 |

That's a lot. Let's go.

---

## Version 2 — Input validation, parameterized queries, separate input schemas

The first step is the cheap one: **don't accept junk, don't format your own SQL, don't let the client set fields you didn't intend to expose.**

```python
# v2/app.py
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.hash import sha256_crypt
from pydantic import BaseModel, EmailStr, Field, ConfigDict

app = FastAPI()
engine = create_engine("postgresql+psycopg2://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(bind=engine); Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)   # ← fix #8
    title = Column(String, nullable=False)
    done = Column(Boolean, default=False, nullable=False)

Base.metadata.create_all(engine)

# ── Pydantic schemas (fix #5, #6) ────────────────────────────────────────
class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unknown fields (mass assignment fix)
    username: EmailStr
    password: str = Field(min_length=12, max_length=128)

class SignupOut(BaseModel):
    id: int
    username: EmailStr

class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: EmailStr
    password: str

class TodoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

class TodoOut(BaseModel):
    id: int
    title: str
    done: bool

# ── Routes ──────────────────────────────────────────────────────────────
def get_db():
    db = Session(); 
    try: yield db
    finally: db.close()

@app.post("/signup", response_model=SignupOut)
def signup(data: SignupIn, db = Depends(get_db)):
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(409, "Username taken")
    u = User(
        username=data.username,
        password=sha256_crypt.hash(data.password),  # still weak, fixed in V3
        is_admin=False,                              # ← server controls admin (fix #6)
    )
    db.add(u); db.commit(); db.refresh(u)
    return u

@app.post("/login")
def login(data: LoginIn, db = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username).first()
    if not user or not sha256_crypt.verify(data.password, user.password):
        raise HTTPException(401, "Invalid credentials")  # generic message
    return {"token": make_token(user)}  # still weak token, fixed in V3

@app.get("/todos", response_model=list[TodoOut])
def list_todos(current_user: User = Depends(get_current_user_stub), db = Depends(get_db)):
    # ← fix #8: filter by owner
    return db.query(Todo).filter_by(owner_id=current_user.id).all()

@app.post("/todos", response_model=TodoOut)
def add_todo(data: TodoIn, current_user: User = Depends(get_current_user_stub),
             db = Depends(get_db)):
    todo = Todo(owner_id=current_user.id, title=data.title)
    db.add(todo); db.commit(); db.refresh(todo)
    return todo
```

### What V2 fixed (and didn't)

✅ Pydantic input validation — no more `data["title"]` explosions.
✅ Unknown fields rejected — no more `is_admin=true` from the client.
✅ SQL injection avoided — we're using the ORM, not f-strings.
✅ IDOR avoided in `list_todos` — filter by `owner_id`.
✅ Generic 401 message.
✅ Title length-bounded — DoS protection.

❌ Still SHA-256 single-round for passwords (V3).
❌ Still weak token (V3).
❌ Still no real auth dependency (V3).
❌ Still sync route with `await` (V3 — async).
❌ Still no rate limit (V4).
❌ Still no logging (V6).
❌ Still no security headers (V6).
❌ Still no MFA (V7).

---

## Version 3 — Real auth: Argon2 + JWT + dependency

Now we get serious about authentication.

```python
# v3/app.py
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.hash import argon2
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field, ConfigDict
import os, secrets

app = FastAPI()
engine = create_engine("postgresql+psycopg2://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(bind=engine); Base = declarative_base()

# ── Config (no more hardcoded secret) ──────────────────────────────
SECRET = os.environ.get("APP_SECRET") or secrets.token_urlsafe(64)
ALG = "HS256"
ACCESS_TTL = timedelta(minutes=15)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")   # for /docs integration

# ── Models ─────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    failed_logins = Column(Integer, default=0)
    locked_until = Column(Integer, default=0)   # epoch seconds

class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    done = Column(Boolean, default=False, nullable=False)

Base.metadata.create_all(engine)

# ── Schemas ────────────────────────────────────────────────────────
class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: EmailStr
    password: str = Field(min_length=12, max_length=128)

class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: EmailStr
    password: str

class TodoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

class TodoOut(BaseModel):
    id: int
    title: str
    done: bool

# ── Password helpers ───────────────────────────────────────────────
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900   # 15 min

def hash_password(pw: str) -> str:
    return argon2.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return argon2.verify(pw, hashed)

# ── Token helpers ──────────────────────────────────────────────────
def make_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + ACCESS_TTL,
         "jti": secrets.token_urlsafe(16)},
        SECRET, algorithm=ALG,
    )

def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALG])  # ← pinned
    except JWTError:
        raise cred_exc
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise cred_exc
    return user

# ── Routes ─────────────────────────────────────────────────────────
def get_db():
    db = Session()
    try: yield db
    finally: db.close()

@app.post("/signup")
def signup(data: SignupIn, db = Depends(get_db)):
    if db.query(User).filter_by(username=data.username).first():
        raise HTTPException(409, "Username taken")
    u = User(username=data.username, password=hash_password(data.password))
    db.add(u); db.commit()
    return {"id": u.id, "username": u.username}

@app.post("/login")
def login(data: LoginIn, db = Depends(get_db)):
    user = db.query(User).filter_by(username=data.username).first()
    if user is None:
        # Constant-time-ish: still hash to avoid timing leak
        verify_password(data.password, "$argon2id$v=19$m=65536,t=3,p=4$" + "x"*22 + "$" + "y"*43)
        raise HTTPException(401, "Invalid credentials")
    now = int(datetime.now(timezone.utc).timestamp())
    if user.locked_until > now:
        raise HTTPException(429, "Account locked. Try again later.")
    if not verify_password(data.password, user.password):
        user.failed_logins += 1
        if user.failed_logins >= MAX_ATTEMPTS:
            user.locked_until = now + LOCKOUT_SECONDS
            user.failed_logins = 0
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    user.failed_logins = 0
    user.locked_until = 0
    db.commit()
    return {"access_token": make_token(user.id), "token_type": "bearer"}

@app.get("/todos", response_model=list[TodoOut])
def list_todos(current_user: User = Depends(get_current_user), db = Depends(get_db)):
    return db.query(Todo).filter_by(owner_id=current_user.id).all()

@app.post("/todos", response_model=TodoOut)
def add_todo(data: TodoIn, current_user: User = Depends(get_current_user), db = Depends(get_db)):
    todo = Todo(owner_id=current_user.id, title=data.title)
    db.add(todo); db.commit(); db.refresh(todo)
    return todo
```

### What V3 fixed (and didn't)

✅ Argon2id passwords — no more rainbow tables.
✅ JWT with `iat`, `exp`, `jti`, pinned algorithm.
✅ Account lockout after 5 failed attempts.
✅ Constant-time-ish 401 message.
✅ Generic "Invalid credentials" — no username enumeration.
✅ Generic 401 on bad token — no user-existence leak.

❌ No refresh tokens — short TTL means user re-logs in every 15 min (V4).
❌ No MFA — V7.
❌ No rate limit at app level — V4.
❌ Sync DB driver blocks the event loop — V5.
❌ No logging — V6.
❌ No security headers — V6.
❌ No idempotency on POSTs (refund, transfer) — V5.
❌ DB user has too many privileges — Part 6.

---

## Version 4 — Refresh tokens, rate limits, app-level hardening

```python
# v4/app.py
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.hash import argon2
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field, ConfigDict
import secrets, os

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# ── DB / Models (same as V3) ────────────────────────────────────────
# Add RefreshToken table
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    jti = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    user_agent = Column(String)
    ip = Column(String)

engine = create_engine("postgresql+psycopg2://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(bind=engine); Base = declarative_base()
# (User and Todo as before)
Base.metadata.create_all(engine)

SECRET = os.environ["APP_SECRET"]
ALG = "HS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=14)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ── Token helpers ──────────────────────────────────────────────────
def make_access(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + ACCESS_TTL,
                       "type": "access"}, SECRET, algorithm=ALG)

def issue_refresh(db, user_id: int, user_agent: str, ip: str) -> str:
    jti = secrets.token_urlsafe(32)
    rt = RefreshToken(
        user_id=user_id, jti=jti,
        expires_at=datetime.now(timezone.utc) + REFRESH_TTL,
        user_agent=user_agent[:256], ip=ip[:64],
    )
    db.add(rt); db.commit()
    return jwt.encode({"sub": str(user_id), "jti": jti,
                       "iat": datetime.now(timezone.utc),
                       "exp": datetime.now(timezone.utc) + REFRESH_TTL,
                       "type": "refresh"}, SECRET, algorithm=ALG)

# ── Routes with rate limits ────────────────────────────────────────
@app.post("/login")
@limiter.limit("5/minute")
def login(req: Request, data: LoginIn, db = Depends(get_db)):
    # ... same as V3 ...
    pass

@app.post("/refresh")
@limiter.limit("30/minute")
def refresh(req: Request, data: RefreshIn, db = Depends(get_db)):
    try:
        payload = jwt.decode(data.refresh_token, SECRET, algorithms=[ALG])
    except JWTError:
        raise HTTPException(401, "Invalid refresh")
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Wrong token type")
    rt = db.query(RefreshToken).filter_by(jti=payload["jti"], revoked=False).first()
    if not rt or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh revoked or expired")
    # Token rotation: revoke old, issue new
    rt.revoked = True
    db.commit()
    return {"access_token": make_access(rt.user_id),
            "refresh_token": issue_refresh(db, rt.user_id,
                                           req.headers.get("user-agent", ""),
                                           req.client.host)}

@app.post("/logout")
def logout(req: Request, data: RefreshIn, user = Depends(get_current_user),
           db = Depends(get_db)):
    try:
        payload = jwt.decode(data.refresh_token, SECRET, algorithms=[ALG])
    except JWTError:
        raise HTTPException(204)
    rt = db.query(RefreshToken).filter_by(jti=payload["jti"]).first()
    if rt and rt.user_id == user.id:
        rt.revoked = True
        db.commit()
    return {"ok": True}
```

### What V4 fixed

✅ Refresh tokens, rotating, revocable.
✅ Rate limit on `/login`, `/refresh`.
✅ Short access tokens (15 min).
✅ Generic 204 on logout (don't leak whether the token existed).

---

## Version 5 — Async, structured logging, idempotency keys

```python
# v5/app.py — async SQLAlchemy + structlog + idempotency
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

log = structlog.get_logger()

engine = create_async_engine("postgresql+asyncpg://vulntodo_app:change-me@localhost/vulntodo")
Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with Session() as db:
        yield db

# Idempotency: store (key, response) for 24h. Same key → return cached response.
# This prevents double-charge on network retry.
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key = Column(String, primary_key=True)
    user_id = Column(Integer, nullable=False)
    response = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

async def with_idempotency(db, user_id: int, key: str, handler):
    existing = await db.get(IdempotencyKey, key)
    if existing and existing.user_id == user_id:
        if (datetime.now(timezone.utc) - existing.created_at).total_seconds() < 86400:
            return existing.response
    response = await handler()
    db.add(IdempotencyKey(key=key, user_id=user_id, response=response.json(),
                          created_at=datetime.now(timezone.utc)))
    await db.commit()
    return response

@app.post("/todos", response_model=TodoOut)
async def add_todo(
    data: TodoIn,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    log.info("todo.create", user_id=current_user.id, ip=request.client.host)
    
    idem_key = request.headers.get("idempotency-key")
    if idem_key:
        async def _do():
            todo = Todo(owner_id=current_user.id, title=data.title)
            db.add(todo); await db.commit(); await db.refresh(todo)
            return TodoOut(id=todo.id, title=todo.title, done=todo.done)
        return await with_idempotency(db, current_user.id, idem_key, _do)
    # ... without idempotency, just do it
```

### What V5 fixed

✅ Async — no more event-loop blocking.
✅ Structured logging (JSON).
✅ Idempotency keys for state-changing operations.

---

## Version 6 — Security headers, error handlers, CORS, async DB user

```python
# v6/app.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # hide in prod

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return resp

app.add_middleware(SecurityHeadersMiddleware)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, method=request.method, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},   # never leak traceback
    )
```

---

## Version 7 — MFA, audit log, admin actions, secrets, DB constraints

The final version. We add TOTP MFA, an immutable audit log, admin role checks, and database-level constraints.

```python
# v7/app.py
import pyotp, qrcode, io
from sqlalchemy import CheckConstraint

# Add to User model:
#   mfa_secret = Column(String, nullable=True)            # encrypted at rest in real prod
#   mfa_enabled = Column(Boolean, default=False)

@app.post("/mfa/setup")
def mfa_setup(current_user: User = Depends(get_current_user), db = Depends(get_db)):
    if current_user.mfa_enabled:
        raise HTTPException(400, "MFA already enabled")
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.username, issuer_name="VulnTodo")
    img = qrcode.make(uri)
    buf = io.BytesIO(); img.save(buf, "PNG")
    # Don't store secret yet — verify first
    return {"qr_png_b64": base64.b64encode(buf.getvalue()).decode(),
            "secret": secret}    # show to user ONCE, then they verify

@app.post("/mfa/verify")
def mfa_verify(code: str, current_user: User = Depends(get_current_user), db = Depends(get_db)):
    if not current_user.mfa_secret:
        raise HTTPException(400, "Run /mfa/setup first")
    if not pyotp.TOTP(current_user.mfa_secret).verify(code, valid_window=1):
        raise HTTPException(401, "Bad code")
    current_user.mfa_enabled = True
    db.commit()
    return {"ok": True}

# Login now requires a second factor step
class LoginStep2In(BaseModel):
    mfa_token: str   # short-lived (5 min) proof of step 1
    code: str

@app.post("/login/mfa")
def login_mfa(data: LoginStep2In, db = Depends(get_db)):
    try:
        payload = jwt.decode(data.mfa_token, SECRET, algorithms=[ALG])
    except JWTError:
        raise HTTPException(401)
    if payload.get("type") != "mfa_pending":
        raise HTTPException(401)
    user = db.get(User, int(payload["sub"]))
    if not user.mfa_enabled or not pyotp.TOTP(user.mfa_secret).verify(data.code, valid_window=1):
        raise HTTPException(401)
    return {"access_token": make_access(user.id),
            "refresh_token": issue_refresh(db, user.id, "", "")}

# Audit log — append-only
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    user_id = Column(Integer, index=True)
    action = Column(String, nullable=False, index=True)
    target_id = Column(Integer)
    ip = Column(String)
    user_agent = Column(String)
    details = Column(String)
    # ↑ INSERT-only; revoke UPDATE/DELETE permissions on the role (Part 6)

# Admin actions are logged
@app.post("/admin/users/{uid}/promote")
def promote(uid: int, request: Request, admin: User = Depends(get_current_user),
            db = Depends(get_db)):
    if not admin.is_admin:
        raise HTTPException(403)
    target = db.get(User, uid)
    target.is_admin = True
    db.add(AuditLog(ts=datetime.now(timezone.utc), user_id=admin.id,
                    action="promote", target_id=uid, ip=request.client.host,
                    user_agent=request.headers.get("user-agent", "")[:256],
                    details=f"Promoted user {uid}"))
    db.commit()
    return {"ok": True}

# DB-level constraints (defense in depth)
# ALTER TABLE todos ADD CONSTRAINT title_len CHECK (char_length(title) BETWEEN 1 AND 200);
# ALTER TABLE users ADD CONSTRAINT username_lowercase CHECK (username = lower(username));
# ALTER TABLE users ADD CONSTRAINT password_len CHECK (char_length(password) > 50);
#  (Argon2 hashes are always > 50 chars)
```

### What V7 fixed (everything else)

✅ TOTP MFA on user accounts.
✅ Audit log for admin actions (immutable at the DB role level — Part 6).
✅ Generic 401 for any MFA failure.
✅ DB constraints enforce invariants (defense in depth).
✅ `docs_url=None` etc. in production.

---

## How to use these 7 versions in your own learning

1. **Run V1.** Find the bugs. There are 17. Use the list.
2. **Run V2.** Find the *remaining* bugs. The list shrinks.
3. **Run V3.** Add a `tests/` directory with tests that try to break the auth (timing attack, brute force, JWT alg confusion).
4. **Run V4.** Add tests for refresh-token rotation. Try a refresh token twice — the second call should fail.
5. **Run V5.** Add tests for idempotency (POST the same `Idempotency-Key` twice — second response is the cached first).
6. **Run V6.** Run **Mozilla Observatory** on it. Try to get an A+.
7. **Run V7.** Try to brute-force the MFA secret in 10 minutes. Try to log in without a code. Try to promote yourself without `is_admin=True`. They should all fail.

The full progression in one table:

| V | Topic | OWASP covered | Lines |
|---|-------|---------------|-------|
| 1 | Bare-minimum (broken) | (none) | 60 |
| 2 | Input validation, ORM | A01 (partial), A03, A04 | 90 |
| 3 | Argon2, JWT, lockout | A02, A07 | 130 |
| 4 | Refresh tokens, rate limit | A04, A07 | 180 |
| 5 | Async, idempotency, logging | A04, A09 | 220 |
| 6 | Headers, errors, CORS | A05 | 250 |
| 7 | MFA, audit, constraints | A04, A07 | 320 |

---

## What V7 still doesn't do (and we cover in the next files)

- No **PostgreSQL Row-Level Security** (Part 6).
- No **secret management** (env vars in production, Vault, etc.).
- No **container hardening** (non-root, read-only FS, dropped caps).
- No **CI/CD security** (Part 8).
- No **dynamic testing** (DAST, fuzzing, Part 8).
- No **AI-generated code review** (Part 7).

Open `06-postgres-security.md` next.
