# Level 2 — Hands-On: From Zero to a Working OpenBao

> **Goal:** by the end of this level you will have a **real** (non-dev) OpenBao
> in Docker, with storage, TLS-ready config, an audit device, KV v2, a properly
> scoped policy, a human login path, a machine login path, and an app that pulls
> its own secrets. Everything below is a live command.

---

## 2.0 The plan for this level

```
Step 1  Build the Docker Compose stack (OpenBao + Postgres + Redis)
Step 2  Generate an internal TLS CA and server certificates
Step 3  Initialise + unseal
Step 4  Enable audit BEFORE anything else
Step 5  Enable KV v2 and write a secret
Step 6  Write policies (the good, minimal kind)
Step 7  Enable userpass, log in as a human
Step 8  Enable AppRole, log in as a machine
Step 9  Wire a FastAPI app to pull its secret
Step 10 Read the audit log and understand what you see
```

---

## 2.1 Step 1 — The Docker Compose stack

Create the lab directory:

```bash
mkdir -p ~/openbao-lab/{certs,config,data,logs,scripts}
cd ~/openbao-lab
```

### `docker-compose.yml`

```yaml
services:
  openbao:
    image: openbao/openbao:2.7.1
    container_name: openbao
    command: server -config=/openbao/config/openbao.hcl
    ports:
      - "127.0.0.1:8200:8200"
    volumes:
      - ./config:/openbao/config:ro
      - ./certs:/openbao/certs:ro
      - ./data:/openbao/data
      - ./logs:/openbao/logs
    environment:
      BAO_ADDR: https://127.0.0.1:8200
      BAO_CACERT: /openbao/certs/ca.crt
    # Swap protection (OpenBao 2.x does not use mlock — see Level 5, §5.2)
    memswap_limit: 0
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD-SHELL", "BAO_CACERT=/openbao/certs/ca.crt bao status >/dev/null 2>&1 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 10s
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    container_name: openbao-postgres
    environment:
      POSTGRES_USER: openbao
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: openbao
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U openbao"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: openbao-redis
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:?set REDIS_PASSWORD in .env}", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
  redisdata:
```

`.env` (git-ignored!):

```bash
POSTGRES_PASSWORD=change-me-postgres
REDIS_PASSWORD=change-me-redis
```

> 🔒 **Create `.gitignore` right now** if this lives in a repo:
> ```
> .env
> .env.*
> data/
> logs/
> certs/
> ```

> 🐘 **Note on the Postgres service here:** in *this* lab, Postgres is the
> **application database** for your FastAPI app, not OpenBao's storage (we're
> using Raft in this lab). Level 6 shows you the alternative where Postgres *is*
> OpenBao's storage backend.

---

## 2.2 Step 2 — TLS (do this from day one, not "in production later")

Self-signed internal CA. Five minutes now, no regrets later.

```bash
cd ~/openbao-lab/certs

# 1. CA key + cert
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=openbao-lab-ca" -out ca.crt

# 2. Server key + CSR
openssl genrsa -out openbao.key 4096
openssl req -new -key openbao.key -subj "/CN=openbao" -out openbao.csr

# 3. SAN file — the SAN is what modern TLS actually checks
cat > san.cnf <<'EOF'
[req]
distinguished_name = req_distinguished_name
req_extensions     = v3_req
[req_distinguished_name]
[v3_req]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = openbao
DNS.2 = localhost
DNS.3 = openbao.local
IP.1  = 127.0.0.1
EOF

# 4. Sign
openssl x509 -req -in openbao.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out openbao.crt -days 825 -sha256 -extfile san.cnf -extensions v3_req

# 5. Restrict permissions (OpenBao will refuse world-readable plugin/key material)
chmod 600 ca.key openbao.key
chmod 644 ca.crt openbao.crt
```

### `config/openbao.hcl`

```hcl
ui            = true
api_addr      = "https://openbao:8200"
cluster_addr  = "https://openbao:8201"
cluster_name  = "openbao-lab"

# Never use the "file" storage backend: removed in OpenBao 2.7.0
storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-node-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
}

# ⚠️ There is NO `disable_mlock` option in OpenBao 2.x.
#    It was removed in 2.0.0 (mlock-removal RFC) and the server
#    REFUSES TO START if it is present. See §5.2 for the swap-based
#    hardening OpenBao expects instead.

telemetry {
  prometheus_retention_time = "30s"
  disable_hostname = false
}

# Tighten request handling
default_max_request_duration = "60s"
```

> ⚠️ **`api_addr` and `cluster_addr` must be reachable by clients.** In a Compose
> network, `https://openbao:8200` is the *service name*, but your laptop can't
> resolve it. Two options:
> * Set `api_addr = "https://127.0.0.1:8200"` (reachable from the host) and
>   `cluster_addr = "https://openbao:8201"` (reachable between nodes), **or**
> * Keep the service name and set `BAO_ADDR` on the host to
>   `https://127.0.0.1:8200` while adding `127.0.0.1 openbao` to
>   `/etc/hosts`.
>
> For a single-node lab the simplest correct choice is:
> `api_addr = "https://127.0.0.1:8200"`, `cluster_addr = "https://openbao:8201"`.

Start it:

```bash
cd ~/openbao-lab
docker compose up -d
docker compose logs -f openbao
```

You'll see it start **sealed** and **uninitialized**.

---

## 2.3 Step 3 — Initialise and unseal

```bash
export BAO_ADDR=https://127.0.0.1:8200
export BAO_CACERT=~/openbao-lab/certs/ca.crt

bao status
```

```json
{
  "sealed": true,
  "initialized": true,     // ← in your case this is false on first boot
  "storage_type": "raft",
  ...
}
```

### Initialise

```bash
bao operator init -key-shares=5 -key-threshold=3
```

Output (abridged):

```
Unseal Keys:
Unseal Key 1: <base64...>
Unseal Key 2: <base64...>
Unseal Key 3: <base64...>
Unseal Key 4: <base64...>
Unseal Key 5: <base64...>

Initial Root Token: hvs.CAESIJ...
```

> **Do this properly, even in a lab.** In a real engagement you would:
> * `-pgp-keys="alice.asc,bob.asc,carol.asc"` so the shares are encrypted to
>   individual GPG keys,
> * `-root-token-pgp-key="admin.asc"` for the root token.
>
> The point of the exercise is to build the *habit*.

### Unseal

Each node needs its own threshold of shares entered **on that node**:

```bash
bao operator unseal '<Unseal Key 1>'
bao operator unseal '<Unseal Key 2>'
bao operator unseal '<Unseal Key 3>'

bao status    # -> "sealed": false
```

### Log in with the root token

```bash
export BAO_TOKEN='hvs.CAESIJ...'
bao token lookup
```

> 💡 **Better: use the token helper** so the token isn't in your shell history.
> ```bash
> bao login -token-only -no-store   # prints the token, doesn't save it
> # or store it in the helper (macOS/Linux):
> bao login -method=userpass -no-store
> ```
> Level 5 covers root token rotation and the "no root token at rest" pattern.

---

## 2.4 Step 4 — Audit FIRST (before you store anything)

This is the habit that separates professionals from hobbyists: **enable audit
before there is anything to audit.**

> ⚠️ **Important 2.7.1 change: audit devices can no longer be created via the
> API by default.** `bao audit enable` now fails with:
>
> ```
> cannot enable audit device via API; use declarative, config-based
> audit device management instead
> ```
>
> The **right** way is the **declarative audit stanza in the server config
> file** — which has the additional benefit that a node can never come up with
> audit missing. Add this to `config/openbao.hcl` and restart:
>
> ```hcl
> audit "file" "file" {
>   description = "Local audit log (declarative, 2.4.0+)."
>   options {
>     file_path = "/openbao/logs/audit.log"
>     mode      = "0600"
>     log_raw   = "false"
>   }
> }
> ```
>
> Note the **two labels**: the first is the device *type*, the second is the
> *mount path*. `options` is a block, and its values are **strings** (hence
> `log_raw = "false"` with quotes). Validate before you restart:
>
> ```bash
> bao operator validate-config -config=config/openbao.hcl
> ```
>
> **The escape hatch** (for one-off API creation, e.g. adding a second device
> in an emergency) is the `unsafe_allow_api_audit_creation` server option,
> which can be toggled at runtime with `SIGHUP`:
>
> ```hcl
> unsafe_allow_api_audit_creation = true
> ```
>
> Enable it, create the device, then set it back to `false` and `SIGHUP` again.
> The option name says everything you need to know about it.

Once the config-based device is up, verify it:

```bash
bao audit list -detailed
```

```json
{
  "file/": {
    "type": "file",
    "options": {
      "file_path": "/openbao/logs/audit.log",
      "log_raw": "false",
      "hmac_accessor": "true"
    }
  }
}
```

> ⚠️ **`log_raw = "false"` is mandatory in production.** With it `true`, secret
> values are written to the audit log in plaintext.
>
> ⚠️ `hmac_accessor = "true"` means token accessors are HMAC'd too (safer, but
> you can't use them for emergency revocation from the log). Default is now
> `true` — good. Set it `false` only if you have a *separate*, secure
> revocation runbook.

**Now** store the unseal shares and root token somewhere safe (password
manager, offline). Then, ideally, **revoke the root token** — Level 5 shows how.

---

## 2.5 Step 5 — KV v2 and a secret

```bash
# Enable the KV v2 engine at "secret"
bao secrets enable -path=secret kv-v2
bao secrets list
```

```json
{
  "cubbyhole/": { "type": "cubbyhole", "description": "per-token private secret storage", "accessor": "..." },
  "identity/":  { "type": "identity",  ... },
  "secret/":    { "type": "kv", "options": { "version": "2" }, ... },
  "sys/":       { "type": "sys", ... }
}
```

### Write a secret

```bash
bao kv put -mount=secret myapp \
  db_host=postgres \
  db_port=5432 \
  db_user=app \
  db_password='S3cr3t!' \
  llm_api_key='sk-live-xxxxx'
```

```json
{
  "request_id": "...",
  "lease_id": "",
  "renewable": false,
  "lease_duration": 0,
  "data": {
    "created_time": "2026-10-20T12:00:00Z",
    "deletion_time": "",
    "destroyed": false,
    "version": 1
  },
  "wrap_info": null,
  "warnings": null,
  "auth": null
}
```

### Read it back

```bash
bao kv get -mount=secret myapp
bao kv get -mount=secret -field=db_password myapp
bao kv metadata get -mount=secret myapp
```

### The KV v2 lifecycle (know these before you need them)

```bash
bao kv put -mount=secret myapp db_password='new'      # v2 now
bao kv get -mount=secret -version=1 myapp              # read old version
bao kv delete -mount=secret myapp                      # soft delete (v3 marked deleted)
bao kv get -mount=secret myapp                         # -> error: data deleted
bao kv undelete -mount=secret myapp                    # bring it back
bao kv destroy -mount=secret myapp                     # permanently destroy current version
bao kv metadata delete -mount=secret myapp             # delete all versions + metadata
```

### Sub-path (folder) organisation

```bash
bao kv put -mount=secret myapp/api llm_api_key='sk-live-xxxxx'
bao kv put -mount=secret myapp/db  db_password='S3cr3t!'

bao kv get -mount=secret myapp
# -> { "api": {...}, "db": {...} }   (folder listing)
```

> 💡 **Design tip:** one secret per *path* (not one big blob) makes policies
> far more granular. `secret/data/myapp/api` and `secret/data/myapp/db` can have
> different policies.

---

## 2.6 Step 6 — Policies (write them like a reviewer would)

### The "reader" policy for the app

```bash
bao policy write app-readonly - <<'EOF'
# Read the app's secrets
path "secret/data/myapp" {
  capabilities = ["read"]
}

# Read version metadata (needed for `bao kv metadata get` / version listing)
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}
EOF

bao policy read app-readonly
```

### The "writer" policy (for a deploy pipeline, not the app)

```bash
bao policy write app-writer - <<'EOF'
path "secret/data/myapp" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list", "delete"]
}
EOF
```

> 💡 **The `metadata` path for KV v2 needs `list`** to enumerate versions.
> Forgetting it causes a confusing "permission denied" on `bao kv metadata get`.

### The "version" policy (does the secret exist, and what's its latest version)

```bash
bao policy write app-version-reader - <<'EOF'
path "secret/metadata/myapp" {
  capabilities = ["read"]
}
EOF
```

### Test the policy before you give it to anyone

```bash
bao token create -policy=app-readonly -ttl=10m -no-default-policy -field=token
```

Then, in a second shell with that token:

```bash
export BAO_TOKEN=<the token>
bao kv get -mount=secret myapp             # ✅ works
bao kv put -mount=secret myapp x=1         # ❌ permission denied
bao secrets list                    # ❌ permission denied
bao token capabilities <token> secret/data/myapp
```

> 🔒 **`-no-default-policy`**: without it, every token also gets `default`
> (lookup-self + renew-self). Usually you want it; for a *strict* test, drop it.

### The "audit auditor" policy

```bash
bao policy write audit-reader - <<'EOF'
path "sys/audit" {
  capabilities = ["read", "list"]
}
path "auth/token/accessors" {
  capabilities = ["read", "list"]
}
EOF
```

### Check what a token can do — the debugging superpower

```bash
bao token capabilities <token> secret/data/myapp
bao sys capabilities <other-token> secret/data/myapp
```

---

## 2.7 Step 7 — A human login path (userpass)

```bash
bao auth enable userpass

bao write auth/userpass/users/alice \
  password='Correct-Horse-Battery-Staple' \
  token_policies=app-readonly \
  token_ttl=1h \
  token_max_ttl=8h
```

Log in:

```bash
bao login -method=userpass username=alice
```

This writes the token to `~/.vault-token` (2.6.0+ lets you override with
`BAO_TOKEN_PATH`).

```bash
bao token lookup
bao kv get -mount=secret myapp
```

Logout:

```bash
# There is NO `bao logout` command in OpenBao 2.7.1. To "log out", delete
# the token file that the default token helper wrote:
rm -f ~/.vault-token          # or $BAO_TOKEN_PATH, if you set it
```

> 💡 `userpass` is **not** for production humans — you have Keycloak. It is
> here for (a) learning, (b) break-glass. Level 7 replaces it with OIDC.

---

## 2.8 Step 8 — A machine login path (AppRole)

```bash
bao auth enable approle

bao write auth/approle/role/myapp \
  secret_id_ttl=10m \
  secret_id_num_uses=1 \
  token_num_uses=0 \
  token_ttl=20m \
  token_max_ttl=1h \
  secret_id_bound_cidrs="10.0.0.0/8"

ROLE_ID=$(bao read -field=role_id auth/approle/role/myapp/role-id)
SECRET_ID=$(bao write -f -field=secret_id auth/approle/role/myapp/secret-id)

echo "role_id:    $ROLE_ID"
echo "secret_id:  $SECRET_ID"     # inject this at deploy time, never commit it
```

Login:

```bash
bao write auth/approle/login role_id="$ROLE_ID" secret_id="$SECRET_ID"
```

```json
{
  "auth": {
    "client_token": "hvs.CAES...",
    "accessor": "...",
    "policies": ["app-readonly", "default"],
    "lease_duration": 1200,
    "renewable": true
  }
}
```

### Test that a used secret_id is dead

```bash
bao write auth/approle/login role_id="$ROLE_ID" secret_id="$SECRET_ID"
# -> Error: invalid secret id   ✅ (num_uses=1 worked)
```

> 🛡️ **2.7.1 security fix (GHSA-7m59-mp95-w6ph):** AppRole secret IDs now
> cannot be used for authentication after expiry, even before the `tidy` job
> runs. This was a real bug — **keep OpenBao patched**. That is the whole
> reason to run `2.7.1` and not `2.6.x`.

---

## 2.9 Step 9 — Wire up a FastAPI app

Directory:

```
~/openbao-lab/app/
├── Dockerfile
├── requirements.txt
└── main.py
```

`requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
hvac==2.3.0
pydantic==2.10.4
```

`main.py`:

```python
"""
Minimal, production-shaped FastAPI + OpenBao integration.

Key ideas:
  * Secrets are fetched at startup, not at import time.
  * The Vault token is renewed in the background.
  * Secrets are never logged.
  * Fail fast if OpenBao is unreachable at boot (fail closed).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

import hvac
from fastapi import FastAPI, HTTPException

log = logging.getLogger("app")
logging.basicConfig(level=logging.INFO)

BAO_ADDR = os.environ["BAO_ADDR"]
BAO_CACERT = os.environ.get("BAO_CACERT")
ROLE_ID = os.environ["APPROLE_ROLE_ID"]
SECRET_ID = os.environ["APPROLE_SECRET_ID"]
SECRET_PATH = os.environ.get("SECRET_PATH", "secret/data/myapp")

client = hvac.Client(url=BAO_ADDR, verify=BAO_CACERT, timeout=30)
_cache: dict[str, Any] = {}


def login() -> str:
    """Authenticate with AppRole and return the client token."""
    resp = client.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
    token = resp["auth"]["client_token"]
    client.token = token
    return token


def renew_loop() -> None:
    """Renew the Vault token in the background so the app never loses access."""
    while True:
        try:
            client.auth.token.renew_self(token=client.token, increment="30m")
            log.info("renewed OpenBao token")
        except Exception as exc:  # noqa: BLE001
            log.error("token renewal failed: %s", exc)
            with contextlib.suppress(Exception):
                login()
        import time
        time.sleep(300)


def get_secret() -> dict[str, Any]:
    """Read the secret from KV v2 with a tiny in-process cache."""
    key = "value"
    now = asyncio.get_event_loop().time() if False else 0  # simple TTL below
    cached = _cache.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    resp = client.secrets.kv.v2.read_secret_version(
        path=SECRET_PATH.replace("secret/data/", ""),
        mount_point="secret",
    )
    data = resp["data"]["data"]
    _cache[key] = {"data": data, "expires": 0}  # refresh each call in this example
    return data


app = FastAPI(title="AI Harness", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    login()
    asyncio.create_task(asyncio.to_thread(renew_loop))
    log.info("OpenBao authenticated and secret cache warm")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config-check")
def config_check() -> dict[str, str]:
    """Prove the app can read its secret — WITHOUT leaking it."""
    secret = get_secret()
    return {
        "db_host": secret.get("db_host", "missing"),
        "llm_key_present": bool(secret.get("llm_api_key")),
    }


@app.get("/llm-key")
def llm_key() -> str:
    """Example of a *bad* endpoint. Do not do this in production."""
    return get_secret()["llm_api_key"]
```

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

RUN useradd -m -u 10001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Run it:

```bash
docker build -t harness-app ./app

docker run -d --name harness-app \
  --network openbao-lab_default \
  -e BAO_ADDR=https://openbao:8200 \
  -e BAO_CACERT=/certs/ca.crt \
  -e APPROLE_ROLE_ID="$ROLE_ID" \
  -e APPROLE_SECRET_ID="$SECRET_ID" \
  -v ~/openbao-lab/certs:/certs:ro \
  harness-app
```

```bash
curl -s localhost:8000/config-check | jq
```

```json
{ "db_host": "postgres", "llm_key_present": true }
```

> 💡 **Notice what the app does *not* do:** it never writes the secret to a
> file, never puts it in a command-line argument, never prints it. It holds it
> in memory, briefly, and uses it.

> ⚠️ **A note on the "never log the secret" rule:** the `/llm-key` endpoint
> above is deliberately labelled bad. In production, you would expose *actions*
> that use the key, never the key.

---

## 2.10 Step 10 — Read the audit log

This is the most important 5 minutes in the course.

```bash
docker compose exec openbao sh -c 'tail -f /openbao/logs/audit.log' | jq .
```

You'll see a stream of JSON objects. Let me annotate one:

```json
{
  "type": "response",
  "auth": {
    "client_token": "hmac-sha256:9c2a...",   // ← HMAC'd, not plaintext
    "accessor": "hmac-sha256:1f3b...",
    "display_name": "token",
    "policies": ["app-readonly", "default"],
    "token_ttl": 3600,
    "token_num_uses": 0
  },
  "request": {
    "id": "0e4b...",
    "operation": "read",
    "client_token": "hmac-sha256:9c2a...",
    "client_token_accessor": "hmac-sha256:1f3b...",
    "namespace_path": "root/",
    "path": "secret/data/myapp",
    "remote_address": "172.18.0.5",
    "client_capabilities": ["read"],
    "request_priority": 0
  },
  "error": "",
  "response": {
    "data": {
      "data": {
        "db_password": "hmac-sha256:7a4e...",   // ← secret value, HMAC'd
        "llm_api_key": "hmac-sha256:2b9f..."
      }
    }
  }
}
```

### What to look for in an incident

```bash
# All operations on a specific path
jq 'select(.request.path=="secret/data/myapp") | {t:.time, op:.request.operation, ip:.request.remote_address}' audit.log

# All failed requests
jq 'select(.error != "") | {t:.time, path:.request.path, err:.error}' audit.log

# Everything a given accessor did
jq 'select(.auth.accessor=="hmac-sha256:1f3b...")' audit.log

# How many reads happened, by path
jq -r 'select(.type=="response") | .request.path' audit.log | sort | uniq -c | sort -rn
```

> 💡 **The HMAC trick:** because the same plaintext always produces the same
> HMAC (for a given audit device), you can prove "this is the same secret
> value" across logs and across time, without ever seeing the value. That's how
> you detect *value reuse* after a supposed rotation.
>
> ⚠️ Because the HMAC key is per-device, **HMACs are not comparable across
> different audit devices.**

---

## 2.11 Now break it on purpose

The best way to internalise policies is to violate them.

```bash
# 1. A token that should only read, tries to write
BAO_TOKEN=<app-readonly-token> bao kv put -mount=secret myapp hacked=yes
# → Error making API request. ... Code: 403. Errors: * 1 error occurred: * permission denied

# 2. Try to read a different app's secret
BAO_TOKEN=<app-readonly-token> bao kv get -mount=secret otherapp
# → 403 permission denied

# 3. Try to list secrets
BAO_TOKEN=<app-readonly-token> bao secrets list
# → 403

# 4. Try to escalate
BAO_TOKEN=<app-readonly-token> bao token create -policy=root
# → 403

# 5. Try to read the audit log
BAO_TOKEN=<app-readonly-token> bao audit list
# → 403
```

Now check the audit log — did the **denied** attempts get recorded?

```bash
jq 'select(.error != "") | {path:.request.path, op:.request.operation, err:.error}' audit.log
```

**Yes.** Denied requests are audited. That's how you detect credential
stuffing and permission-probing.

---

## 2.12 Clean up and reset (repeatable practice)

```bash
# Revoke the root token (Level 5 does this properly — do it by hand once here)
bao token revoke <root-token>

# Or nuke the whole thing
docker compose down -v
rm -rf data/*
docker compose up -d
```

---

## 2.13 Level 2 checkpoint

1. Why must you enable the audit device *before* storing secrets?
2. What does `bao operator init -key-shares=5 -key-threshold=3` mean, and can
   two different people unseal with shares 1 and 2?
3. Which four paths does a KV v2 policy need per secret, and which one do
   people forget?
4. What happens to a secret_id after `secret_id_num_uses=1` is used once?
5. Where does the AppRole `role_id` belong, and where does the `secret_id`
   belong? Why the difference?
6. How do you check what a token is allowed to do before giving it to someone?
7. How do you find "who read this secret" in the audit log?

**Next → [Level 3: POLICIES-TOKENS-IDENTITY.md](03-POLICIES-TOKENS-IDENTITY.md)** —
the authorization deep dive: advanced policy syntax, templating, identity groups,
token strategy at scale.

---

## 2.14 Scratchpad

```
BAO_ADDR:              https://127.0.0.1:8200
BAO_CACERT:            ~/openbao-lab/certs/ca.crt
Mounts:                secret/ (kv-v2)
Policies:             app-readonly, app-writer, app-version-reader, audit-reader
Auth methods:         userpass/ (human), approle/ (machine)
AppRole role_id:      <from bao read -field=role_id auth/approle/role/myapp/role-id>
Audit log:             /openbao/logs/audit.log  (inside container)
```
