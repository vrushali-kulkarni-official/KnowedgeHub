# OpenBao — The Complete Beginner's Guide

> A from-scratch walkthrough: what it is, why you need it, how it fits with
> Docker Compose / FastAPI / PostgreSQL / Redis / Keycloak, with baby-step
> code for every piece.

---

## 0. TL;DR

OpenBao is a **password manager for your applications**. It holds all your
API keys, database passwords, TLS certs, and OAuth client secrets in **one
encrypted place** and gives them out to your apps only when they're allowed
to have them.

It's the open-source community fork of HashiCorp Vault (because HashiCorp
moved Vault to a non-open BSL license in late 2023). Same API, same UI,
same clients. You can swap between the two with almost zero code change.

---

## 1. The problem — and why you shouldn't put secrets in `.env`

Before we touch OpenBao, let's feel the pain.

Today your stack probably looks like this:

```
your-fastapi-app/
├── .env
│   ├── DATABASE_URL=postgresql://user:s3cr3t@db:5432/myapp
│   ├── REDIS_URL=redis://:r3d1sP4ss@redis:6379
│   ├── KEYCLOAK_CLIENT_SECRET=kc-supersecret
│   ├── JWT_SECRET=please-dont-leak-me
│   └── OPENAI_API_KEY=sk-...
├── main.py
└── ...
```

The pain:

| #   | What goes wrong                                                     | How bad            |
| --- | ------------------------------------------------------------------- | ------------------ |
| 1   | `.env` gets `git push`ed by accident                                | ☠️ Total compromise |
| 2   | You rotate the DB password → you have to restart every service      | 😐 Annoying        |
| 3   | Every dev sees prod passwords in their local `.env`                 | ☠️ Insider risk     |
| 4   | Three copies of the same secret in three `.env` files, one is stale | 🐛 Heisenbugs      |
| 5   | "What secrets do we actually have, and who can see them?"           | 🤷 Nobody knows    |

OpenBao fixes all five.

---

## 2. What is OpenBao? (one sentence at a time)

- OpenBao is a **secrets manager**: a single, encrypted, auditable place to
  store every secret your system uses.
- It was **forked from HashiCorp Vault 1.14 in late 2023** after HashiCorp
  switched Vault to the Business Source License. The community didn't want
  to lose an open-source Vault, so they forked it.
- It now lives under the **Linux Foundation / OpenSSF** with open
  governance. License is **MPL 2.0** (truly open source, weak copyleft).
- It's **API-compatible with Vault** — every `vault` CLI command, every
  `hvac` library call, every `VAULT_*` env var works in OpenBao. The
  binary is just called `bao` instead of `vault`.
- It's a **single Go binary** with a web UI, an HTTP API, and a CLI. You
  run it as a Docker container (or bare metal) and your apps talk to it
  over HTTP.

So when you see `bao`, just think "Vault but open source".

### Why this fits your preferences (from your user profile)

| Your rule                            | OpenBao's answer                                                     |
| ------------------------------------ | -------------------------------------------------------------------- |
| Free and open source                 | ✅ MPL 2.0, Linux Foundation                                          |
| Industry-standard / production-grade | ✅ Same API as HashiCorp Vault, used by GitLab, Akamai, Siemens, etc. |
| Avoid vendor lock-in                 | ✅ Vault-compatible, so you can move to either freely                 |
| Self-hostable, free tier             | ✅ It's literally one Docker image, you own everything                |
| API-first / abstraction-friendly     | ✅ LangChain, hvac, openbao-mcp all available                         |

---

## 3. The 6 concepts you have to internalize

Don't skip this. Every other guide assumes you already know these.

```
┌──────────────────────────────────────────────────────────────┐
│  1. TOKEN          "I am logged in"                          │
│  2. AUTH METHOD    "How I proved who I am"                   │
│  3. POLICY         "What I'm allowed to do"                  │
│  4. SECRETS ENGINE "Where the secret actually lives"         │
│  5. PATH           "The address of a secret"                 │
│  6. LEASE          "When my access expires"                  │
└──────────────────────────────────────────────────────────────┘
```

### 3.1 Token — "your session ID"

You login → OpenBao gives you a long string (the token). You send that
token in every future request via the `X-Vault-Token` header. Tokens
**expire** (default 32 days, max 32 days), can be **renewed**, and can be
**revoked** instantly. Treat it like a JWT for OpenBao itself.

### 3.2 Auth method — "how I prove I'm me"

A *plugin* that knows how to verify identity. OpenBao has many:

| Auth method             | Used by                                  | Mental model               |
| ----------------------- | ---------------------------------------- | -------------------------- |
| `userpass`              | humans via UI                            | username + password        |
| `token`                 | bootstrap / scripts                      | paste a root token         |
| **`approle`**           | **machines / apps**                      | RoleID + SecretID → token  |
| `kubernetes`            | pods in k8s                              | ServiceAccount JWT → token |
| **`oidc` / `jwt`**      | **SSO users (Keycloak, Auth0, Google…)** | browser login → token      |
| `ldap`, `github`, `aws` | enterprise                               | federated login            |

You'll use **AppRole** for FastAPI and **OIDC** for humans via Keycloak.
Mark those.

### 3.3 Policy — "what I'm allowed to do"

A policy is a tiny HCL or JSON file. Example:

```hcl
# policy: myapp-policy.hcl
path "secret/data/myapp/*" {
  capabilities = ["read"]
}
```

That says: any token with this policy can **read** anything under
`secret/data/myapp/`, but cannot write or delete.

You can attach multiple policies to one token. If a request hits a path
the token's policies don't allow → **403**.

### 3.4 Secrets engine — "the storage backend for a kind of secret"

A *plugin* that knows how to store / generate a type of secret. You
**enable** one (or many) and they become available at a path.

| Engine     | What it does                               | Example path                    |
| ---------- | ------------------------------------------ | ------------------------------- |
| `kv-v2`    | key-value with versioning                  | `secret/data/myapp/db`          |
| `database` | **dynamic** Postgres / MySQL / Redis creds | `database/creds/myapp-readonly` |
| `transit`  | encrypt/decrypt without storing data       | `transit/encrypt/myapp`         |
| `pki`      | issue TLS certs                            | `pki/issue/internal`            |
| `ssh`      | SSH cert authority                         | `ssh/sign/...`                  |

You will use **`kv-v2`** (static secrets) and **`database`** (dynamic
Postgres + Redis creds) in your stack. Mark those.

### 3.5 Path — "the address"

Every secret lives at a path. You `read`, `write`, `list`, `delete` paths.

```
secret/data/myapp/db          # a kv-v2 secret named "db"
database/creds/app-readonly   # a dynamic DB credential
auth/approle/login            # an auth endpoint
sys/health                    # a system endpoint
```

### 3.6 Lease — "when this expires"

Almost everything in OpenBao has a **TTL**. Database creds you got at
3:00pm with a 1-hour lease will be auto-revoked at 4:00pm. Tokens have
TTLs. Even secret reads can be logged with an expiry. The app is
**forced** to renew or re-fetch.

This is the magic that makes "rotate keys" actually happen instead of
being a quarterly panic.

---

## 4. The full mental model

```
                  ┌─────────────────────────────────────┐
                  │              OpenBao                │
                  │                                     │
  Human ──OIDC──▶ │  ┌─────────────┐  ┌──────────────┐  │   ┌────────┐
  (browser)       │  │ jwt/oidc    │  │ approle      │  │   │ Tokens │
                  │  │ auth method │  │ auth method  │  │   │ + Pols │
                  │  └──────┬──────┘  └──────┬───────┘  │   └────────┘
                  │         │                │          │
                  │         ▼                ▼          │
                  │  ┌────────────────────────────────┐ │
                  │  │   Policies  (who can do what)  │ │
                  │  └────────────────────────────────┘ │
                  │         │                │          │
                  │         ▼                ▼          │
                  │  ┌──────────┐  ┌──────────┐ ┌──────┐│
                  │  │ kv-v2    │  │ database │ │transit││
                  │  │ (static) │  │ (dynamic)│ │(crypt)││
                  │  └────┬─────┘  └────┬─────┘ └───────┘│
                  │       │             │                │
                  └───────┼─────────────┼────────────────┘
                          │             │
                          ▼             ▼
                       Secrets    Postgres / Redis
                       (read)     (generated creds)
```

Your FastAPI app holds a token, asks OpenBao for the secret it needs,
and OpenBao says yes/no based on the policy attached to that token.

---

## 5. Install OpenBao (baby steps)

### 5.1 The one-file docker-compose

```yaml
# docker-compose.yml
services:
  openbao:
    image: openbao/openbao:2.4
    container_name: openbao
    restart: unless-stopped
    ports:
      - "8200:8200"   # API + UI
      - "8201:8201"   # Raft cluster traffic
    environment:
      BAO_ADDR: "http://0.0.0.0:8200"
      BAO_API_ADDR: "http://0.0.0.0:8200"
      BAO_CLUSTER_ADDR: "http://0.0.0.0:8201"
    cap_add:
      - IPC_LOCK      # needed so OpenBao can lock memory
    volumes:
      - ./bao/config:/openbao/config:ro
      - bao-data:/openbao/file
      - bao-logs:/openbao/logs
    command: ["server", "-config=/openbao/config/openbao.hcl"]

volumes:
  bao-data:
  bao-logs:
```

### 5.2 The config file

`bao/config/openbao.hcl`:

```hcl
ui            = true
disable_mlock = true        # fine for dev; turn off in prod
storage "raft" {
  path = "/openbao/file"
  node_id = "bao-1"
}
listener "tcp" {
  address         = "0.0.0.0:8200"
  tls_disable     = true     # dev only — use TLS in prod
  cluster_address = "0.0.0.0:8201"
}
api_addr     = "http://0.0.0.0:8200"
cluster_addr = "http://0.0.0.0:8201"
log_level    = "info"
```

### 5.3 Run it

```bash
docker compose up -d openbao
docker compose logs -f openbao
# wait for: "OpenBao server started!"
```

---

## 6. Initialize & unseal (only the first time)

OpenBao boots **sealed**. Sealed = "I have encrypted data on disk but
I don't have the key in memory to read it yet." This is so that if
someone steals the disk, they can't read the secrets.

```bash
docker exec -it openbao bao operator init
```

You'll get back:

```
Unseal Key 1: AbCdEf...
Unseal Key 2: GhIjKl...
Unseal Key 3: MnOpQr...
Unseal Key 4: StUvWx...
Unseal Key 5: YzAbCd...

Initial Root Token: hvs.SuperLongString...
```

> **Save these in your password manager.** The 5 unseal keys split the
> master key using Shamir's Secret Sharing — by default you need any 3
> of 5 to unseal. Lose them and you lose everything.

```bash
# unseal (run 3 times with 3 different keys)
docker exec -it openbao bao operator unseal
# paste key 1
docker exec -it openbao bao operator unseal
# paste key 2
docker exec -it openbao bao operator unseal
# paste key 3
```

Now it's unsealed. Check:

```bash
docker exec -it openbao bao status
# Sealed: false
# Initialized: true
```

In real production you'd use **auto-unseal** (with AWS KMS, GCP KMS,
Azure Key Vault, or transit) so the server unseals itself on boot.
For local dev the manual flow is fine.

---

## 7. Log in & set up the world

Set the root token as an env var (we'll throw this away after creating
proper logins):

```bash
export BAO_ADDR=http://localhost:8200
export BAO_TOKEN=hvs.SuperLongString...
```

### 7.1 Enable the engines we need

```bash
# static key-value (with versioning)
bao secrets enable -path=secret kv-v2

# dynamic database creds
bao secrets enable -path=database database

# encryption-as-a-service
bao secrets enable -path=transit transit
```

### 7.2 Enable the auth methods we need

```bash
# machines / apps
bao auth enable -path=approle approle

# humans via Keycloak SSO
bao auth enable -path=oidc jwt
# (jwt with config = OIDC — same plugin, two modes)
```

### 7.3 Make a policy for your app

`policies/myapp.hcl`:

```hcl
# read static secrets
path "secret/data/myapp/*" {
  capabilities = ["read"]
}
# generate dynamic DB creds
path "database/creds/app-readonly" {
  capabilities = ["read"]
}
# encrypt with transit (optional)
path "transit/encrypt/myapp" {
  capabilities = ["update"]
}
path "transit/decrypt/myapp" {
  capabilities = ["update"]
}
```

Load it:

```bash
bao policy write myapp-policy policies/myapp.hcl
```

### 7.4 Make an AppRole for FastAPI

```bash
# create the role
bao write auth/approle/role/myapp \
    token_policies="myapp-policy" \
    token_ttl=15m \
    token_max_ttl=2h \
    secret_id_ttl=24h \
    secret_id_num_uses=0   # 0 = unlimited uses
```

This says: "any caller that proves they have the myapp RoleID+SecretID
gets a 15-min token with myapp-policy attached."

```bash
# grab the RoleID (NOT secret)
bao read -field=role_id auth/approle/role/myapp/role-id
# → a1b2c3d4-...

# grab a SecretID
bao write -f -field=secret_id auth/approle/role/myapp/secret-id
# → e5f6g7h8-...
```

> **Never** put the root token in your app. AppRole gives your app
> a *least-privilege* token instead.

### 7.5 Store your first real secret

```bash
bao kv put secret/myapp/db \
    host=postgres \
    port=5432 \
    name=myapp \
    user=myapp \
    password=initial-password-from-DB-init
```

> **The point:** now this secret isn't in your `.env` file. It's in
> OpenBao. The app asks for it at startup.

---

## 8. Wire up dynamic Postgres creds (the killer feature)

This is where OpenBao really earns its keep.

### 8.1 Tell OpenBao about Postgres

```bash
# OpenBao will log in as a "root" user and create new roles on demand
bao write database/config/myapp-postgres \
    plugin_name=postgresql-database-plugin \
    allowed_roles="app-readonly,app-readwrite" \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/myapp?sslmode=disable" \
    username="vault-root" \
    password="vault-root-password" \
    password_authentication="scram-sha-256"
```

### 8.2 Define the role it can mint

```bash
bao write database/roles/app-readonly \
    db_name=myapp-postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"
```

### 8.3 What happens at runtime

Your app says "give me a readonly user":

```bash
bao read database/creds/app-readonly
```

OpenBao instantly:

```
Key                Value
---                -----
lease_id           database/creds/app-readonly/abc123
username           v-myapp-postgre-app-reado-xyz123
password           A1B2C3D4E5...
```

It just **created a brand-new Postgres user**, valid for 1 hour, with
only `SELECT` permission. When the hour's up, OpenBao **drops the
user**. Your app never reuses a password, and a leaked password is
dead in an hour.

> Same plugin works for Redis, MySQL, MongoDB, MSSQL, Cassandra,
> ClickHouse, Snowflake, etc.

---

## 9. Wire up Keycloak SSO (humans)

When a human admin opens the OpenBao UI, we want them to log in with
their Keycloak account, not with a token we paste.

### 9.1 In Keycloak

1. Create a new realm (e.g. `mycompany`).
2. Create a new client `openbao`:
   - Access Type: **confidential**
   - Standard Flow Enabled: ON
   - Valid Redirect URIs:
     - `http://localhost:8200/ui/vault/auth/oidc/oidc/callback`
     - `http://localhost:8250/oidc/callback`
3. Copy the client secret.

### 9.2 In OpenBao

```bash
bao write auth/oidc/config \
    oidc_client_id="openbao" \
    oidc_client_secret="<paste-from-keycloak>" \
    default_role="user" \
    oidc_discovery_url="http://keycloak:8080/realms/mycompany"
```

Make a policy + role for humans:

```bash
bao policy write user - <<EOF
path "secret/data/myapp/*" { capabilities = ["read"] }
EOF

bao write auth/oidc/role/user \
    role_type="oidc" \
    user_claim="sub" \
    policies="user" \
    allowed_redirect_uris="http://localhost:8200/ui/vault/auth/oidc/oidc/callback,http://localhost:8250/oidc/callback"
```

Now a human can click "OIDC" on the login page → redirected to
Keycloak → SSO sign-in → back to OpenBao with a user-token.

> The same flow works for **CI/CD** (GitHub Actions JWT, GitLab
> JWT, K8s ServiceAccount JWT…) and for **other apps** that
> already have a JWT (you can verify a token without OIDC dance).

---

## 10. The full stack (docker-compose with everything)

```yaml
# docker-compose.yml
services:

  # ─── secrets manager ─────────────────────────────────
  openbao:
    image: openbao/openbao:2.4
    container_name: openbao
    ports: ["8200:8200"]
    environment:
      BAO_ADDR: "http://0.0.0.0:8200"
      VAULT_ADDR: "http://0.0.0.0:8200"   # hvac still reads VAULT_*
    cap_add: [IPC_LOCK]
    volumes:
      - ./bao/config:/openbao/config:ro
      - bao-data:/openbao/file
      - bao-logs:/openbao/logs
    command: ["server", "-config=/openbao/config/openbao.hcl"]
    healthcheck:
      test: ["CMD", "bao", "status"]
      interval: 10s
      retries: 5
    networks: [internal]

  # ─── your app ────────────────────────────────────────
  api:
    build: ./api
    container_name: api
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
      openbao:  { condition: service_started }
    environment:
      BAO_ADDR: "http://openbao:8200"
      BAO_ROLE_ID: "a1b2c3d4-..."         # injected from host env
      BAO_SECRET_ID: "e5f6g7h8-..."       # injected from host env
    ports: ["8000:8000"]
    networks: [internal, edge]

  # ─── database ────────────────────────────────────────
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: myapp
    volumes:
      - pg-data:/var/lib/postgresql/data
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s

  # ─── cache ───────────────────────────────────────────
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--requirepass", "changeme"]
    networks: [internal]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  # ─── identity for humans ─────────────────────────────
  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    command: ["start-dev"]
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
    ports: ["8080:8080"]
    networks: [internal]

networks:
  internal: { driver: bridge }
  edge: { driver: bridge }

volumes:
  bao-data:
  bao-logs:
  pg-data:
```

Notice:

- `postgres` and `redis` are on the **internal** network only —
  the outside world can't reach them.
- `openbao` and `keycloak` are also on the **internal** network
  (you can also expose OpenBao's UI on `edge` for the dashboard).
- `api` is on **both** — it needs to talk to the internal services
  *and* be reached by clients.

---

## 11. The FastAPI side — `hvac` client (baby steps)

`hvac` is the official Python client. Works with both Vault and OpenBao.

```bash
pip install hvac
```

### 11.1 A minimal helper

`app/secrets.py`:

```python
import os
import hvac
from functools import lru_cache

@lru_cache(maxsize=1)
def get_bao() -> hvac.Client:
    """Authenticate once, cache the client."""
    return hvac.Client(
        url=os.environ["BAO_ADDR"],
        namespace=None,                 # OpenBao optional
    )

def login_with_approle(role_id: str, secret_id: str) -> str:
    """Trade AppRole creds for a short-lived token."""
    client = get_bao()
    resp = client.auth.approle.login(role_id=role_id, secret_id=secret_id)
    client.token = resp["auth"]["client_token"]   # cache it
    return client.token

def get_kv_secret(path: str) -> dict:
    """Read a kv-v2 secret at secret/<path>."""
    client = get_bao()
    # mount_point='secret', path=<path without 'secret/'>
    return client.secrets.kv.v2.read_secret_version(
        mount_point="secret", path=path, raise_on_deleted_version=True
    )["data"]["data"]

def get_dynamic_db_creds(role: str = "app-readonly") -> dict:
    """Get a fresh, time-limited DB user."""
    client = get_bao()
    return client.secrets.database.generate_credentials(
        name=role, mount_point="database"
    )["data"]
```

### 11.2 Wire it into FastAPI startup

`app/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.secrets import (
    get_bao, login_with_approle,
    get_kv_secret, get_dynamic_db_creds,
)
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. App boots → authenticate to OpenBao
    login_with_approle(
        role_id=os.environ["BAO_ROLE_ID"],
        secret_id=os.environ["BAO_SECRET_ID"],
    )
    print("✓ Authenticated to OpenBao")
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "bao_authed": get_bao().is_authenticated()}

@app.get("/config")
def show_config():
    db = get_kv_secret("myapp/db")        # static config
    creds = get_dynamic_db_creds("app-readonly")  # dynamic, 1h TTL
    return {
        "static":   {k: "***" for k in db},         # never leak!
        "dynamic": {
            "user":     creds["username"],
            "password": creds["password"],
            "expires":  "in ~1h, will be auto-rotated",
        },
    }
```

Run it:

```bash
docker compose up -d
curl localhost:8000/health
# {"status":"ok","bao_authed":true}

curl localhost:8000/config
# {"static": {"host":"***","port":"***",...},
#  "dynamic": {"user":"v-myapp-postgre-...","password":"...","expires":"..."}}
```

> The static `db` is what you stored once (host, port, name). The
> dynamic `creds` is a *brand new Postgres user* minted just for
> this request, expiring in 1h.

### 11.3 Use the dynamic creds to actually talk to Postgres

```python
from sqlalchemy import create_engine
from app.secrets import get_dynamic_db_creds

def make_engine():
    cfg = get_kv_secret("myapp/db")           # host, port, dbname
    creds = get_dynamic_db_creds("app-readonly")
    url = (
        f"postgresql+psycopg://{creds['username']}:{creds['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['name']}"
    )
    return create_engine(url, pool_pre_ping=True)
```

Now even your SQLAlchemy connection string is **never written down**.

---

## 12. Where Redis fits in

Two ways:

### 12.1 Just store the Redis password in OpenBao (static)

```bash
bao kv put secret/myapp/redis host=redis port=6379 password=r3d1sP4ss
```

App reads it the same way it reads the DB config. Done.

### 12.2 OR — use the Redis database plugin for *dynamic* creds

```bash
bao write database/config/myapp-redis \
    plugin_name=redis-database-plugin \
    allowed_roles="app-cache" \
    host=redis \
    port=6379 \
    username="default" \
    password="r3d1sP4ss"

bao write database/roles/app-cache \
    db_name=myapp-redis \
    creation_statements="['~*', '+@read', '+@write']" \
    default_ttl="1h" max_ttl="24h"
```

Now your app gets a **per-request Redis ACL user** with read+write that
dies in an hour. Same idea as Postgres.

---

## 13. Where Keycloak fits in

Keycloak does **identity for humans** (and for services that have a
browser flow). OpenBao does **authorization for everything in your
infra**. They are *complementary*, not competing.

```
User  ──login──▶  Keycloak  ──issues JWT──▶  Browser hits FastAPI
                                                  │
                                                  ▼
                                       FastAPI verifies JWT via
                                       Keycloak's JWKS endpoint
                                                  │
                                                  ▼
                                       FastAPI calls OpenBao
                                       with its own AppRole token
                                       to get a DB password
```

In other words:

| Tool     | Question it answers                                                           | Stored where              |
| -------- | ----------------------------------------------------------------------------- | ------------------------- |
| Keycloak | "Who is this human, and what groups are they in?"                             | Keycloak's own DB         |
| OpenBao  | "What secrets is this app allowed to fetch, and when does its access expire?" | OpenBao's encrypted store |

You can also **cross-link** them — have OpenBao trust Keycloak's
JWT (OIDC auth method) so human operators log into OpenBao using
their Keycloak account, as we set up in section 9.

---

## 14. The full picture (one diagram)

```
┌────────────────────────────────────────────────────────────────────────┐
│                              YOUR STACK                                │
│                                                                        │
│   ┌────────┐     OIDC     ┌────────────┐      AppRole       ┌───────┐  │
│   │  User  │ ───────────▶ │  Keycloak  │                    │FastAPI│  │
│   └────────┘   (browser)  └────────────┘                    │ app   │  │
│       │                       │ JWKS                        └───┬───┘  │
│       │                       │                                 │      │
│       │ OIDC                  │ verify                          │      │
│       ▼                       ▼                                 │      │
│   ┌────────┐  short JWT   ┌──────────┐  hvac + role/secret      │      │
│   │OpenBao │ ◀─────────── │  Browser │                          │      │
│   │ (UI)   │              └──────────┘                          │      │
│   └────┬───┘                                                    │      │
│        │ audit logs                                             │      │
│        ▼                                                        │      │
│   ┌────────────────┐   KV v2     ┌──────────────────────────┐   │      │
│   │  Secrets store │ ──────────▶ │  static config           │   │      │
│   │  (Raft, encr.) │   dynamic   │  + dynamic DB creds      │   │◀─────┘
│   └────────────────┘ ──────────▶ │  + dynamic Redis creds   │
│                                  └──────────────────────────┘
│                                            │            │
│                                            ▼            ▼
│                                       ┌─────────┐  ┌────────┐
│                                       │Postgres │  │ Redis  │
│                                       └─────────┘  └────────┘
└────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Step-by-step: a real request walkthrough

Imagine a request comes in: `GET /users/42`. Here's every secret-touching
event in order:

1. **App boot** (one-time):

   - FastAPI starts → reads `BAO_ROLE_ID` + `BAO_SECRET_ID` from env.
   - Calls `hvac.auth.approle.login(...)` → gets a 15-min token.
   - That token has `myapp-policy` attached.

2. **First DB call**:

   - SQLAlchemy wants to connect.
   - `make_engine()` calls `get_dynamic_db_creds("app-readonly")`.
   - OpenBao creates a new Postgres user `v-app-readonly-x9k2`, password
     `Bh3...`, valid 1h, returns it.
   - SQLAlchemy connects with that user. **Password never existed in
     code or in `.env`.**

3. **Some time later** (1h):

   - Postgres user `v-app-readonly-x9k2` is auto-dropped by OpenBao.
   - App's connection pool notices, calls `make_engine()` again.
   - A *new* user is minted. Old password is dead.

4. **Admin opens OpenBao UI**:

   - Clicks "OIDC" → redirected to Keycloak.
   - Logs in with username/password (or Google, or whatever Keycloak has).
   - Keycloak issues JWT, redirects back.
   - OpenBao verifies signature with Keycloak's JWKS, mints a user-token.
   - Admin can now manage secrets; every action is **audit-logged**.

5. **Something goes wrong** (a leaked token):

   - `bao token revoke <leaked-token>` — instant kill.
   - Or wait 15 minutes for natural expiry.
   - Rotate the actual DB password → `bao write -force database/rotate-root/myapp-postgres`.

---

## 16. Beginner pitfalls (don't learn these the hard way)

| #   | Pitfall                                        | Fix                                                                     |
| --- | ---------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | Leaving the root token in `docker-compose.yml` | Throw it away after creating scoped AppRole + OIDC                      |
| 2   | `disable_mlock = true` in prod                 | Set to false and grant `IPC_LOCK` cap                                   |
| 3   | `tls_disable = true` in prod                   | Generate a real cert (or use a reverse proxy)                           |
| 4   | Long-lived tokens                              | Use 15m–2h AppRole TTLs; let OpenBao rotate                             |
| 5   | One policy per app with `path "*"`             | Write *least-privilege* policies per service                            |
| 6   | Forgetting to unseal after a restart           | Add a sidecar that runs `bao operator unseal` with a key from a KMS     |
| 7   | Hardcoding the unseal key in a script          | Use auto-unseal (AWS/GCP/Azure KMS) or Shamir keys split between humans |
| 8   | Pasting secrets in `print()`                   | Always mask: `print({k: '***' for k in secret})`                        |

---

## 17. Quick-reference commands

```bash
# status
bao status

# login (root, dev only)
bao login <root-token>

# login (AppRole)
bao write auth/approle/login role_id=... secret_id=...

# write a kv-v2 secret
bao kv put secret/myapp/db host=postgres user=myapp password=...

# read a kv-v2 secret
bao kv get -mount=secret myapp/db
bao kv get -mount=secret -field=password myapp/db

# list secrets under a path
bao kv list secret/myapp/

# delete a secret (kv-v2 = soft delete)
bao kv delete secret/myapp/db

# generate dynamic DB creds
bao read database/creds/app-readonly

# encrypt with transit
bao write transit/encrypt/myapp plaintext=$(echo -n 'hi' | base64)

# see who I am
bao token lookup
```

---

## 18. Where to go from here

1. **Auto-unseal** with AWS/GCP/Azure KMS or Transit — so you don't
   have to manually unseal after every restart.
2. **Audit logs** — point OpenBao at a file or syslog so you have a
   record of every secret access.
3. **Namespaces** — split OpenBao into per-team or per-env partitions
   (`ns/staging/`, `ns/prod/`).
4. **HA cluster** — run 3 or 5 OpenBao nodes with Raft so one node
   dying doesn't take secrets down.
5. **PKI engine** — issue short-lived TLS certs for your internal
   services instead of buying certs.
6. **External Secrets Operator** — if you ever deploy to k8s, this
   syncs OpenBao secrets into k8s Secrets automatically.
7. **The GitLab story** — GitLab ships OpenBao as their native
   secrets manager; their docs are a great reference deployment.

---

## TL;DR once more

- **OpenBao = open-source HashiCorp Vault.** One binary, one API.
- Three jobs: **store** secrets, **mint** dynamic secrets, **audit**
  who used what.
- For your stack: FastAPI uses **AppRole**, humans use **OIDC/Keycloak**,
  PostgreSQL & Redis get **dynamic creds**, all behind **policies**.
- A single `bao kv put` removes a secret from your `.env` forever.

Welcome to "no more secrets in the repo" 🌱
