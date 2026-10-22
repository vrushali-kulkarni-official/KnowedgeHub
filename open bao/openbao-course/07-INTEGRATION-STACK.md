# Level 7 — Integration With Your Stack

> **Goal:** OpenBao is now *part of* your system, not a thing next to it.
> Keycloak for humans, AppRole/JWT for machines, GitHub Actions for CI,
> FastAPI and LangChain consuming secrets safely, PostgreSQL with dynamic
> credentials.

---

## 7.0 The integration map

```
                    ┌──────────────┐
   Human ──────────▶│  Keycloak    │  OIDC IdP (you already have this)
                    │  (OIDC IdP)  │
                    └──────┬───────┘
                           │ ID token
                           ▼
                    ┌──────────────┐      ┌──────────────────────┐
                    │  OpenBao     │◀────▶│  Audit log → SIEM    │
                    │  auth/oidc   │      └──────────────────────┘
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┬────────────────────┐
        │                  │                  │                    │
   ┌────▼─────┐      ┌─────▼──────┐    ┌──────▼─────┐      ┌───────▼──────┐
   │ FastAPI  │      │ LangChain  │    │ GitHub    │      │  PostgreSQL  │
   │ (AppRole)│      │ (AppRole)  │    │ Actions   │      │ (dynamic DB  │
   │          │      │            │    │ (OIDC JWT)│      │  creds)      │
   └──────────┘      └────────────┘    └───────────┘      └──────────────┘
```

**The one rule that makes this work:** every consumer authenticates with its
**own identity**, and gets a **scoped token**. No shared credentials, ever.

---

## 7.1 Keycloak → OpenBao (OIDC)

### 7.1.1 The Keycloak side

In Keycloak, create a **client** for OpenBao:

| Setting | Value |
|---|---|
| Client type | `OpenID Connect` |
| Client ID | `openbao` |
| Access type | `confidential` |
| Standard flow | **enabled** |
| Direct access grants | disabled |
| Valid redirect URIs | `http://localhost:8250/oidc/callback` and `https://openbao.corp.internal:8200/ui/vault/auth/oidc/oidc/callback` |
| Web origins | `https://openbao.corp.internal:8200` |
| Client secret | copy it (it's needed for `oidc/client_secret`) |
| **Scope** | add the `groups` client scope (see below) |

> 🔍 **Keycloak groups claim — the gotcha everyone hits.** Keycloak does **not**
> put groups in the ID token by default. You must add a **group membership
> mapper** to the client's scope:
>
> 1. Create a client scope (e.g. `openbao-groups`) with a **Hardcoded claim**
>    mapper or, better, a **Group membership** mapper with:
>    * "Full group path" → **off** (otherwise you get `/platform/sre`)
>    * "Claim" → `groups`
> 2. Assign the scope to the client (Client → Client scopes → Add).
>
> Without this, OpenBao sees no groups and every user lands in the default
> policy.

Also create a **group** in Keycloak, e.g. `openbao-sre`, and add a client
scope mapper for it. And note Keycloak's **groups overage**: a user in a very
large number of groups will have the claim omitted entirely rather than
truncated. Design for that (use a dedicated mapper on a specific group, not
"all groups").

### 7.1.2 The OpenBao side

```bash
# 1. Enable the OIDC auth method
bao auth enable -path=oidc oidc

# 2. Point it at Keycloak's discovery endpoint
bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/enterprise" \
    oidc_client_id="openbao" \
    oidc_client_secret="<from-keycloak>" \
    default_role="human"
```

> 🚨 **Two corrections that catch everyone:**
>
> 1. **The config path is `auth/<mount>/config`** — not `auth/oidc/oidc`
>    (that path returns *"unsupported path"*).
> 2. **`oidc_discovery_url` is the BASE URL.** OpenBao appends
>    `/.well-known/openid-configuration` itself, and **rejects** the full URL:
>    *"'oidc_discovery_url' contains '.well-known' component"*.
> 3. The keys are **`oidc_client_id` / `oidc_client_secret`** — plain
>    `client_id` / `client_secret` are silently ignored.
>
> Check the result:
> ```bash
> bao read -format=json auth/oidc/config | jq -r .data.status
> # → "valid"   ← discovery fetched and verified
> ```
>
> The `issuer` in Keycloak's discovery document must match the URL OpenBao
> uses to reach Keycloak. If OpenBao reaches it at `http://keycloak:8080`
> (Docker DNS) but the token says `https://keycloak.corp.internal`,
> validation fails. **Make them match**, and set Keycloak's frontend URL to
> match too.

### 7.1.3 The role — this is where identity mapping happens

```bash
bao write auth/oidc/role/human \
    user_claim="preferred_username" \
    oidc_scopes="openid profile email groups" \
    role_type="oidc" \
    allowed_redirect_uris="http://localhost:8250/oidc/callback,https://openbao.corp.internal:8200/ui/vault/auth/oidc/oidc/callback" \
    token_ttl="1h" \
    token_max_ttl="8h" \
    token_policies="human-default"
```

For group-based mapping, use a **JSON write** (map values can't be set via
individual CLI flags):

```bash
bao write auth/oidc/role/human - <<'EOF'
{
  "user_claim": "preferred_username",
  "oidc_scopes": "openid profile email groups",
  "role_type": "oidc",
  "allowed_redirect_uris": "http://localhost:8250/oidc/callback",
  "token_ttl": "1h",
  "token_max_ttl": "8h",
  "bound_claims": {
    "groups": ["openbao-sre", "openbao-platform"]
  }
}
EOF
```

### 7.1.4 Test the login

```bash
bao login -method=oidc -path=oidc -role=human
# → opens your browser → Keycloak login → back to OpenBao
```

```bash
bao token lookup | jq '.data.policies, .data.entity_id'
```

### 7.1.5 Debugging OIDC (the docs' own advice)

> *"Start simple. The only claim configuration a role requires is `user_claim`."*

1. Start with just `user_claim` and `oidc_scopes`. Get it working.
2. Then add `bound_claims`.
3. **Check OpenBao's logs** — validation failures are logged there.
4. **Redirect URIs must match exactly**: http vs https, `127.0.0.1` vs
   `localhost`, port numbers, trailing slashes.
5. Decode the token yourself to see the claims:
   ```bash
   cat jwt.json | jq -r .access_token | cut -d. -f2 | base64 -d | jq
   ```
6. `log_oidc_info = true` on the role logs the received token — **debug only**,
   it writes claims to the server log verbatim.

> ⚠️ **2.7.0 improvement:** `auth/oidc` now returns `oidc_discovery_url`
> validation errors (like a bad issuer) from the underlying library, instead of
> a generic failure. If your setup suddenly starts failing loudly, read the
> message.

### 7.1.6 Keycloak → OpenBao with the `jwt` auth method (alternative)

Use `jwt` instead of `oidc` when you want to validate tokens Keycloak issued
*without* the browser redirect (e.g. service-to-service, or a token your
frontend already holds).

```bash
bao auth enable -path=keycloak-jwt jwt

bao write keycloak-jwt/jwt/keycloak \
    jwks_url="http://keycloak:8080/realms/enterprise/protocol/openid-connect/certs" \
    bound_issuer="http://keycloak:8080/realms/enterprise" \
    bound_audiences="openbao" \
    user_claim="preferred_username" \
    roles_claim="/realm_access/roles" \
    token_policies="human-default" \
    token_ttl="1h" \
    token_max_ttl="8h"
```

Login with a token:

```bash
bao write auth/keycloak-jwt/login role=keycloak jwt="$KEYCLOAK_ACCESS_TOKEN"
```

> 💡 **When to use `oidc` vs `jwt`:**
> * `oidc` = interactive browser login. **This is what you want for humans.**
> * `jwt` = you already have a signed JWT and want OpenBao to trust it.
> * `oidc` supports PKCE and the device flow; `jwt` is simpler but there's no
>   browser flow.

---

## 7.2 Machines: AppRole in Docker Compose

### The pattern

```
  role_id     → baked into the image/config (NOT a secret)
  secret_id   → injected at deploy time by a trusted party (secret)
```

### Option A — entrypoint script (simplest, most common)

`docker-compose.yml`:

```yaml
services:
  app:
    build: ./app
    environment:
      BAO_ADDR: https://openbao:8200
      BAO_CACERT: /certs/ca.crt
      APPROLE_ROLE_ID: ${APPROLE_ROLE_ID}
      APPROLE_SECRET_ID: ${APPROLE_SECRET_ID}   # injected by CI, never committed
    volumes:
      - ./certs:/certs:ro
    depends_on:
      openbao:
        condition: service_healthy
```

`app/entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "authenticating to OpenBao..."
export BAO_TOKEN=$(bao write -format=json auth/approle/login \
    role_id="${APPROLE_ROLE_ID}" \
    secret_id="${APPROLE_SECRET_ID}" | jq -r .auth.client_token)

# Optional: background token renewal
(
  while true; do
    sleep 240
    export BAO_TOKEN=$(bao write -format=json auth/token/renew-self \
        token="$BAO_TOKEN" increment="20m" | jq -r .auth.client_token) || {
      echo "renewal failed, re-authenticating" >&2
      export BAO_TOKEN=$(bao write -format=json auth/approle/login \
          role_id="${APPROLE_ROLE_ID}" \
          secret_id="${APPROLE_SECRET_ID}" | jq -r .auth.client_token)
    }
  done
) &

exec "$@"
```

> ⚠️ **The `_FILE` convention is better.** Most apps (including many Docker
> images) support reading a secret from a file. Combine it with a Docker secret
> or a mounted file so the secret never appears in `docker inspect` output or
> the process environment of *other* processes:
>
> ```yaml
> environment:
>   APPROLE_SECRET_ID_FILE: /run/secrets/approle_secret_id
> secrets:
>   - approle_secret_id
> ```

### Option B — `bao agent` sidecar (the professional answer)

`bao agent` handles authentication, renewal, and secret rendering for you. The
app never sees a token at all.

`agent.hcl`:

```hcl
pid_file = "/tmp/bao-agent.pid"

vault {
  address      = "https://openbao:8200"
  ca_cert      = "/openbao/certs/ca.crt"
  retry {
    num_retries = 5
  }
}

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id   = "..."
      secret_id = "..."
    }
  }

  # Write the token to a file the app can read (mode 0640, owned by the app user)
  sink "file" {
    config = {
      path = "/secrets/openbao-token"
      mode = 0640
    }
  }
}

template {
  source            = "/secrets/openbao-token"
  destination       = "/secrets/openbao-token"
  error_on_missing_key = true
  wait { min_duration = "5s" }
}
```

`docker-compose.yml`:

```yaml
services:
  bao-agent:
    image: openbao/openbao:2.7.1
    container_name: bao-agent
    command: agent -config=/agent/config/agent.hcl
    volumes:
      - ./config:/agent/config:ro
      - agent-secrets:/secrets
    depends_on:
      openbao:
        condition: service_healthy
    restart: unless-stopped

  app:
    build: ./app
    volumes:
      - agent-secrets:/secrets:ro
    environment:
      BAO_ADDR: https://openbao:8200
      BAO_CACERT: /certs/ca.crt
      BAO_TOKEN_FILE: /secrets/openbao-token
    depends_on: [bao-agent]

volumes:
  agent-secrets:
```

> 💡 **`bao agent` templates secrets to files** — including arbitrary
> transformations. Your app reads `/secrets/db_password` and never handles a
> token. This is the **best pattern for containers**: it means a compromised
> app process can't escalate to "read everything in OpenBao", and the agent
> handles re-auth transparently.

### Option C — `bao proxy` (for apps that speak the OpenBao API)

`bao proxy` sits in front of OpenBao, caches responses, and handles
authentication. Your app points at `http://127.0.0.1:8100` instead of OpenBao.

```hcl
pid_file = "/tmp/bao-proxy.pid"

vault {
  address = "https://openbao:8200"
}

api_addr = "127.0.0.1:8100"

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = { role_id = "...", secret_id = "..." }
  }
}

cache {
  use_static_token = true
  persist = "memory"
}

listener "tcp" {
  address = "127.0.0.1:8100"
  tls_disable = true      # it's a loopback sidecar listener
}
```

> 💡 **Proxy is great for the "many small reads" pattern** — it caches KV
> reads so you're not hammering OpenBao. But **cached secrets have a TTL you
> must choose**, and a proxy that caches a *dynamic* credential is dangerous
> (the lease keeps ticking while the cache serves it). Cache static KV, not
> dynamic creds.

---

## 7.3 FastAPI — the production integration

### The complete, correct pattern

```python
"""
app/secrets.py — the only place in your codebase that talks to OpenBao.

Design rules encoded here:
  1. One long-lived OpenBao client, created at startup.
  2. Auth via AppRole; the token is renewed in a background task.
  3. Secrets are cached with a TTL and refreshed in the background.
  4. NOTHING is logged. No secret is ever in an exception message.
  5. Fail closed: if OpenBao is unreachable at boot, the app does not start.
  6. Dynamic credentials are fetched on demand and renewed, never cached long.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

import hvac

log = logging.getLogger(__name__)

BAO_ADDR = os.environ.get("BAO_ADDR", "https://openbao:8200")
BAO_CACERT = os.environ.get("BAO_CACERT")
ROLE_ID = os.environ.get("APPROLE_ROLE_ID")
SECRET_ID = os.environ.get("APPROLE_SECRET_ID")
SECRET_PATH = os.environ.get("SECRET_PATH", "myapp")
MOUNT = os.environ.get("SECRET_MOUNT", "secret")


class SecretManager:
    """Owns the OpenBao client, the token, and the secret cache."""

    def __init__(self) -> None:
        self.client = hvac.Client(url=BAO_ADDR, verify=BAO_CACERT, timeout=30)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ttl = float(os.environ.get("SECRET_CACHE_TTL", "300"))

    # ── auth ──────────────────────────────────────────────────────────
    def login(self) -> None:
        resp = self.client.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
        self.client.token = resp["auth"]["client_token"]
        log.info("authenticated to OpenBao")

    def _renew(self) -> None:
        try:
            resp = self.client.auth.token.renew_self(
                token=self.client.token, increment="20m"
            )
            self.client.token = resp["auth"]["client_token"]
        except Exception:
            log.warning("token renewal failed; re-authenticating")
            self.login()

    async def keepalive(self) -> None:
        """Background task: renew the token and refresh the cache."""
        while True:
            await asyncio.sleep(240)
            try:
                await asyncio.to_thread(self._renew)
            except Exception as exc:
                # Never log the exception's payload; it can contain a token.
                log.error("openbao keepalive error: %s", type(exc).__name__)

    # ── secret access ────────────────────────────────────────────────
    def _read(self, path: str) -> dict[str, Any]:
        resp = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=MOUNT
        )
        return resp["data"]["data"]

    def get(self, path: str) -> dict[str, Any]:
        """Read a KV v2 secret with a short in-process cache."""
        now = time.monotonic()
        hit = self._cache.get(path)
        if hit and hit[0] > now:
            return hit[1]
        data = self._read(path)
        self._cache[path] = (now + self._ttl, data)
        return data

    def get_db_credentials(self) -> dict[str, str]:
        """Fetch DYNAMIC database credentials.

        These are deliberately NOT cached beyond their lease: the whole point
        is that the credential dies. We track the lease so we can renew it.
        """
        resp = self.client.secrets.database.read_creds(
            name=os.environ.get("DB_ROLE", "app"), mount_point="db"
        )
        return {
            "username": resp["data"]["username"],
            "password": resp["data"]["password"],
            "lease_id": resp["data"]["lease_id"],
            "lease_duration": resp["data"]["lease_duration"],
        }

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.client.revoke(self.client.token)


secrets = SecretManager()
```

`app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .secrets import secrets


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed: if we cannot authenticate, do not serve traffic.
    try:
        secrets.login()
    except Exception as exc:
        raise RuntimeError(
            f"could not authenticate to OpenBao: {type(exc).__name__}"
        ) from exc

    task = asyncio.create_task(secrets.keepalive())
    try:
        yield
    finally:
        task.cancel()
        secrets.close()


app = FastAPI(title="AI Harness", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config-check")
def config_check() -> dict[str, object]:
    """Prove the app can read its config — without leaking it."""
    s = secrets.get("myapp")
    return {
        "db_host": s.get("db_host"),
        "llm_key_present": bool(s.get("llm_api_key")),
        "redis_host": s.get("redis_host"),
    }
```

### Testing OpenBao-dependent code

Use a **fake** in tests. Never point your test suite at production OpenBao.

```python
# tests/conftest.py
import pytest
from app import secrets as secrets_module


@pytest.fixture
def fake_secrets(monkeypatch):
    monkeypatch.setattr(
        secrets_module.secrets,
        "get",
        lambda path: {"db_host": "localhost", "llm_api_key": "sk-test"},
    )
    monkeypatch.setattr(
        secrets_module.secrets,
        "get_db_credentials",
        lambda: {"username": "u", "password": "p"},
    )
```

---

## 7.4 LangChain — sourcing API keys safely

### The reality

LangChain reads configuration from **environment variables** (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `LANGCHAIN_API_KEY`, `TAVILY_API_KEY`, …). It does not
know about OpenBao. So the integration is:

```
OpenBao KV v2  →  (at process start)  →  os.environ  →  LangChain
```

### The pattern

```python
# app/bootstrap.py
"""Populate os.environ from OpenBao, before anything imports LangChain.

Order matters: this MUST run before `from langchain...` imports in your app,
because many LangChain integrations read env vars at import time.
"""
import os

from .secrets import secrets


def load_environment() -> None:
    cfg = secrets.get("myapp/llm")

    mapping = {
        "OPENAI_API_KEY": cfg.get("openai_api_key"),
        "ANTHROPIC_API_KEY": cfg.get("anthropic_api_key"),
        "LANGCHAIN_API_KEY": cfg.get("langsmith_api_key"),
        "LANGCHAIN_TRACING_V2": "true" if cfg.get("langsmith_enabled") else "false",
        "LANGCHAIN_PROJECT": cfg.get("langsmith_project", "ai-harness"),
        "TAVILY_API_KEY": cfg.get("tavily_api_key"),
    }
    for k, v in mapping.items():
        if v:
            os.environ[k] = v
```

```python
# app/main.py
import uvicorn

from .bootstrap import load_environment

load_environment()          # ← BEFORE any langchain import

from .api import app         # noqa: E402  (deliberate late import)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

> ⚠️ **The import-order trap is real.** If any module does
> `from langchain_openai import ChatOpenAI` at module scope, and that module is
> imported before `load_environment()`, the key may be `None` or cached
> incorrectly. Use `load_environment()` in the container's entrypoint script
> instead — that's even more robust.

### The container entrypoint (most robust)

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Authenticate
export BAO_TOKEN=$(bao write -format=json auth/approle/login \
    role_id="$APPROLE_ROLE_ID" secret_id="$APPROLE_SECRET_ID" | jq -r .auth.client_token)

# 2. Export secrets as env vars for LangChain
export OPENAI_API_KEY=$(bao kv get -mount=secret -field=openai_api_key myapp/llm)
export ANTHROPIC_API_KEY=$(bao kv get -mount=secret -field=anthropic_api_key myapp/llm)
export LANGCHAIN_API_KEY=$(bao kv get -mount=secret -field=langsmith_api_key myapp/llm)

# 3. Start
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### A `SecretProvider` for LangChain callbacks

For things you *do* want to look up at runtime (RAG corpora, model configs):

```python
from typing import Any
from langchain_core.callbacks import BaseCallbackHandler


class OpenBaoSecretHandler(BaseCallbackHandler):
    """Resolve secrets lazily, from OpenBao, inside a LangChain callback."""

    def __init__(self, path: str = "myapp/llm") -> None:
        self._path = path

    def get(self, key: str, default: Any = None) -> Any:
        return secrets.get(self._path).get(key, default)


handler = OpenBaoSecretHandler()
handler.get("openai_api_key")
```

### What NOT to do

```python
# ❌ Never
os.environ["OPENAI_API_KEY"] = "sk-hardcoded"
# ❌ Never
langchain_api_key=os.environ.get("OPENAI_API_KEY")  # in a module-level constant
# ❌ Never
client = ChatOpenAI(openai_api_key=secrets["openai_api_key"])  # in a module-level global
```

Module-level globals capture the value at import time, which makes rotation
impossible and makes the secret immortal in the process.

---

## 7.5 PostgreSQL — dynamic credentials end to end

### 7.5.1 One-time Postgres setup

```sql
-- As a superuser, ONCE
CREATE ROLE openbao_admin WITH LOGIN PASSWORD 'strong-password' CREATEROLE;
GRANT CONNECT ON DATABASE appdb TO openbao_admin;
```

### 7.5.2 OpenBao config

```bash
bao secrets enable -path=db database

bao write db/config/postgres \
    plugin_name=postgresql-database-plugin \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/appdb?sslmode=require" \
    username="openbao_admin" \
    password="strong-password" \
    verify_connection=true \
    allowed_roles="app,readonly,migrate"

bao write db/roles/app \
    db_name=postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT CONNECT ON DATABASE appdb TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\"; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
    revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="4h" \
    renew_statements="ALTER ROLE \"{{name}}\" VALID UNTIL '{{expiration}}';" \
    username_template="v-token-{{identity.entity.id}}-{{random 6}}-{{timestamp}}"

bao write db/roles/migrate \
    db_name=postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL ON DATABASE appdb TO \"{{name}}\";" \
    revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl="15m" \
    max_ttl="30m"
```

### 7.5.3 Policy — the app can only read its own creds

```bash
bao policy write app-db - <<'EOF'
path "database/creds/app" {
  capabilities = ["read"]
}
EOF
```

### 7.5.4 Use it from FastAPI

```python
import psycopg2
from psycopg2.pool import ThreadedConnectionPool


class RotatingPool:
    """A connection pool that recycles when the dynamic credential expires."""

    def __init__(self) -> None:
        self._pool: ThreadedConnectionPool | None = None
        self._expires_at = 0.0

    def get_pool(self) -> ThreadedConnectionPool:
        now = time.monotonic()
        if self._pool is None or now >= self._expires_at:
            creds = secrets.get_db_credentials()
            self._pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                host=os.environ.get("DB_HOST", "postgres"),
                port=int(os.environ.get("DB_PORT", "5432")),
                dbname="appdb",
                user=creds["username"],
                password=creds["password"],
            )
            # Recycle a bit before the lease actually dies
            self._expires_at = now + max(30, creds["lease_duration"] * 0.7)
        return self._pool
```

> 💡 **The subtle part:** the Postgres role has `VALID UNTIL` = lease expiry.
> Your connection pool might hold connections created *before* expiry; those
> stay alive (Postgres doesn't kill established sessions), but **new**
> connections will fail after expiry. So the pool must be recycled on a
> schedule tied to the lease. The 0.7 factor above is deliberate.

### 7.5.5 Verify revocation works

```sql
-- In Postgres
SELECT rolname, rolvaliduntil FROM pg_roles WHERE rolname LIKE 'v-token-%';
```

Revoke from OpenBao and watch the role disappear:

```bash
bao lease revoke database/creds/app/...
```

---

## 7.6 Redis — the honest version

As established in §4.9: **there is no Redis dynamic-credentials plugin in
OpenBao 2.7.1.** Here is what to actually do.

### Approach A — static credential in KV v2 (recommended for most cases)

```bash
bao kv put -mount=secret myapp/redis \
    host=redis \
    port=6379 \
    username=app \
    password='redis-app-password' \
    tls=true \
    db=0
```

```bash
bao policy write redis-reader - <<'EOF'
path "secret/data/myapp/redis" {
  capabilities = ["read"]
}
EOF
```

### Approach B — Redis ACL users with scripted rotation (better)

Redis 6+ has **ACL users**. You can create one per service with narrow
permissions and rotate the password on a schedule.

```bash
#!/usr/bin/env bash
# rotate-redis-acl.sh — run from a controlled environment (CI or a cron sidecar)
set -euo pipefail

SERVICE="${1:?service name}"
KEYS="${2:?key pattern, e.g. app:*}"

# Admin password comes from OpenBao
ADMIN_PW=$(bao kv get -mount=secret -field=password myapp/redis/admin)
NEW_PW=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)

redis-cli -u "redis://:${ADMIN_PW}@redis:6379" --no-auth-warning ACL SETUSER "$SERVICE" \
  on ">$KEYS" "+@read" "+@write" "+ping" "+get" "+set" ">${NEW_PW}" "+@all" -@all

# Store the new password for the service to pick up
bao kv put -mount=secret "myapp/redis/${SERVICE}" \
    host=redis port=6379 username="$SERVICE" password="$NEW_PW" tls=true

# Reload the ACL file so it survives a Redis restart
redis-cli -u "redis://:${ADMIN_PW}@redis:6379" --no-auth-warning ACL SAVE
```

> ⚠️ **Be careful with the ACL command above** — the ordering of `+@all -@all`
> matters. The safe sequence is: reset the user, then grant only what you
> need. Test it in a lab.

### Approach C — the Valkey plugin (if you can switch)

OpenBao ships `valkey-database-plugin`. If you can run **Valkey** (the Linux
Foundation's Redis fork, drop-in compatible), you get real dynamic credentials:

```bash
bao write db/config/valkey \
    plugin_name=valkey-database-plugin \
    connection_url="redis://{{username}}:{{password}}@valkey:6379" \
    username="openbao_admin" \
    password="..." \
    allowed_roles="app"
```

### Recommendation for your stack

```
Postgres  → real dynamic credentials (postgresql-database-plugin)     ✅
Redis     → static KV v2 + ACL-user rotation script                   ⚠️
```

Redis is usually network-isolated and lower-value than a database credential.
Don't over-engineer it. But **do** give each service its own Redis ACL user
with scoped key patterns, so a compromised service can't read another's keys.

---

## 7.7 GitHub Actions → OpenBao (OIDC, no stored secrets)

This is the single biggest win available to your CI: **zero long-lived secrets
in GitHub**.

### 7.7.1 The flow

```
  GitHub Actions (OIDC identity token)
        │  JWT signed by GitHub, aud="openbao"
        ▼
  OpenBao `jwt` auth method
        │  validates signature via GitHub's JWKS
        │  checks bound_audiences + bound_claims
        ▼
  OpenBao token with CI policies
```

### 7.7.2 Configure the OpenBao side

```bash
bao auth enable -path=github-actions jwt

bao write auth/github-actions/config - <<'EOF'
{
  "oidc_discovery_url": "https://token.actions.githubusercontent.com",
  "bound_issuer": "https://token.actions.githubusercontent.com",
  "default_role": "github"
}
EOF

bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "ref": "refs/heads/main"
  },
  "token_policies": ["ci-deploy"],
  "token_ttl": "15m",
  "token_max_ttl": "30m"
}
EOF
```

> 🚨 **Three corrections:**
> 1. The mount config is at **`auth/<mount>/config`**; the role is at
>    **`auth/<mount>/role/<name>`**. There is no `auth/<mount>/jwt/<name>`.
> 2. `oidc_discovery_url` is the **base URL** — no `.well-known` suffix
>    (OpenBao appends it). The literal `/.well-known/jwks` form only applies
>    to `jwks_url`.
> 3. `bound_claims` is a **map**, so it needs a JSON write (or
>    `-` heredoc) — you cannot set it with repeated `key=value` flags.
>
> The `oidc_discovery_url` form pulls the JWKS automatically. You can also
> set `jwks_url="https://token.actions.githubusercontent.com/.well-known/jwks"`
> explicitly (they are mutually exclusive).

**Tightening `bound_claims`:**

```bash
# Restrict to a specific repo AND branch AND workflow
bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "ref": "refs/heads/main",
    "workflow": "deploy.yml",
    "repository_owner": "your-org"
  }
}
EOF
```

> 💡 `bound_claims` is a **map**, so it needs a JSON write (or a `-` heredoc).
> You cannot set it with repeated `key=value` flags.

> 🔒 **`bound_audiences` must match the `aud` you request from GitHub.** If they
> don't, the token is rejected. This is the #1 cause of "401 unauthorized" in
> this setup.

### 7.7.3 The CI policy

```bash
bao policy write ci-deploy - <<'EOF'
# CI can read the config it needs to deploy
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/data/myapp/config" {
  capabilities = ["read"]
}
# CI can write the versioned app config it owns
path "secret/data/myapp/deploy" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp/deploy" {
  capabilities = ["read", "list"]
}
# CI needs to see what it's deploying
path "sys/health" {
  capabilities = ["read"]
}
EOF
```

> ⚠️ **Do NOT give CI `list` on `secret/data/*` or `secret/metadata/*`.** The
> whole point of CI having a token is that it can read *specific* things.
> `list` on a KV mount reveals every secret path in it.

### 7.7.4 The GitHub Actions workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write        # ← REQUIRED to get an OIDC token

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production   # ← set "Require approval" in GitHub settings

    steps:
      - name: Get OpenBao token from OIDC
        id: bao
        env:
          BAO_ADDR: https://openbao.corp.internal:8200
          BAO_CACERT: ${{ secrets.BAO_CACERT }}
        run: |
          # Request the GitHub OIDC token
          OIDC_TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_URL" \
                             "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=openbao" | jq -r .value)

          # Exchange it for an OpenBao token
          BAO_TOKEN=$(curl -sS --cacert "$BAO_CACERT" \
            -H "X-Vault-Request: true" \
            -H "Content-Type: application/json" \
            -d "{\"role\":\"github\",\"jwt\":\"$OIDC_TOKEN\"}" \
            "$BAO_ADDR/v1/auth/github-actions/login" | jq -r .auth.client_token)

          echo "::add-mask::$BAO_TOKEN"
          echo "token=$BAO_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Read app config from OpenBao
        env:
          BAO_TOKEN: ${{ steps.bao.outputs.token }}
        run: |
          # Write to a file, not an env var in the job log
          curl -sS --cacert "$BAO_CACERT" \
            -H "X-Vault-Token: $BAO_TOKEN" \
            "$BAO_ADDR/v1/secret/data/myapp" > app-config.json
          echo "Config fetched (values not printed)"

      - name: Deploy
        run: ./deploy.sh
```

> 🔑 **The `aud` must match `bound_audiences`.** In the workflow above,
> `audience=openbao`; in OpenBao, `bound_audiences="openbao"`. Change one,
> change both.

> 💡 **`environment: production`** with "required reviewers" gives you a
> human approval gate on the deploy — a poor-man's but effective control
> group, and it also means the OIDC token's `environment` claim is set.

### 7.7.3b Using `bao` CLI in CI

```yaml
      - name: Install bao CLI
        run: |
          wget -qO- https://github.com/openbao/openbao/releases/download/v2.7.1/openbao_2.7.1_linux_amd64.zip \
            | funzip > /usr/local/bin/bao
          chmod +x /usr/local/bin/bao

      - name: Fetch secrets
        env:
          BAO_ADDR: https://openbao.corp.internal:8200
          BAO_CACERT: ${{ secrets.BAO_CACERT }}
          OIDC_TOKEN: ${{ steps.oidc.outputs.token }}
        run: |
          export BAO_TOKEN=$(curl -sS --cacert "$BAO_CACERT" \
            -H "Content-Type: application/json" \
            -d "{\"role\":\"github\",\"jwt\":\"$OIDC_TOKEN\"}" \
            "$BAO_ADDR/v1/auth/github-actions/login" | jq -r .auth.client_token)
          echo "::add-mask::$BAO_TOKEN"
          bao kv get -mount=secret -field=api_key myapp/deploy > /tmp/deploy-key
```

> 💡 `BAO_CACERT` is a GitHub secret, but it's a **public CA certificate** —
> not a credential. It's fine (and correct) to store it as a secret so you can
> rotate it, but it provides no security. The *only* thing protecting your
> secrets here is the OIDC token's short lifetime and its bound claims.

### 7.7.4 The alternative — OpenBao as the OIDC *provider*

You can flip it: make OpenBao the IdP and have GitHub Actions log in to it.

```bash
bao write sys/oidc/providers/default \
    client_type="public" \
    allowed_redirect_uris="https://github.com/org/repo" \
    allowed_scopes="openid profile email" \
    default_scopes="openid profile email" \
    issuer="https://openbao.corp.internal:8200"
```

Then create a client for GitHub and configure the **OIDC** auth method in
OpenBao to trust OpenBao's own provider.

> ⚠️ **2.6.0 added a Client Credentials flow to the OIDC Provider** — so
> OpenBao can now issue tokens for machine-to-machine flows directly. And
> 2.7.0 removed `prompt=none` redirection support in the OIDC provider
> (GHSA-2cjw-94fw-wqjx) — a security fix. Don't build flows that rely on it.

**Which direction should you use?**

| | GitHub → OpenBao (`jwt` auth) | OpenBao → GitHub (OIDC provider) |
|---|---|---|
| Simplicity | ✅ Simple, well-documented | More moving parts |
| GitHub native | ✅ Uses the built-in `id-token: write` | Needs custom setup |
| Revocation | GitHub's OIDC tokens are short-lived | OpenBao's session model |
| Use when | CI needs OpenBao secrets | You want one IdP for everything |

**Recommendation: GitHub → OpenBao.** It's simpler, and GitHub's OIDC tokens
are already short-lived and audience-scoped.

---

## 7.8 The complete stack in one Compose file

```yaml
services:
  # ─────────── OpenBao ───────────
  openbao:
    image: openbao/openbao:2.7.1
    container_name: openbao
    command: server -config=/openbao/config/openbao.hcl
    ports: ["127.0.0.1:8200:8200"]
    volumes:
      - ./config:/openbao/config:ro
      - ./certs:/openbao/certs:ro
      - openbao-data:/openbao/data
      - ./logs:/openbao/logs
    memswap_limit: 0
    security_opt: ["no-new-privileges:true"]
    healthcheck:
      test: ["CMD-SHELL", "BAO_CACERT=/openbao/certs/ca.crt bao status >/dev/null 2>&1"]
      interval: 10s
      timeout: 5s
      retries: 12
    networks: [backend]
    restart: unless-stopped

  # ─────────── Keycloak ───────────
  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    container_name: keycloak
    command: ["start-dev", "--import-realm"]
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_ADMIN:-admin}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD:?set KC_ADMIN_PASSWORD}
      KC_HEALTH_ENABLED: "true"
    volumes:
      - ./keycloak/realm.json:/opt/keycloak/data/import/realm.json:ro
    ports: ["127.0.0.1:8080:8080"]
    healthcheck:
      test: ["CMD-SHELL", "exec 3<>/dev/tcp/127.0.0.1/8080 && echo -e 'GET /health/ready HTTP/1.1\\r\\nhost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && cat <&3 | grep -q '\"status\": \"UP\"'"]
      interval: 10s
      timeout: 5s
      retries: 20
    networks: [backend]

  # ─────────── Postgres ───────────
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
      POSTGRES_DB: appdb
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]

  # ─────────── Redis ───────────
  redis:
    image: redis:7-alpine
    container_name: redis
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:?set REDIS_PASSWORD}", "--appendonly", "yes"]
    volumes: [redisdata:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [backend]

  # ─────────── The app ───────────
  app:
    build: ./app
    container_name: harness-app
    environment:
      BAO_ADDR: https://openbao:8200
      BAO_CACERT: /certs/ca.crt
      APPROLE_ROLE_ID: ${APPROLE_ROLE_ID}
      APPROLE_SECRET_ID: ${APPROLE_SECRET_ID}
      SECRET_PATH: myapp
      DB_HOST: postgres
      REDIS_HOST: redis
    volumes:
      - ./certs:/certs:ro
    depends_on:
      openbao:   { condition: service_healthy }
      postgres:  { condition: service_healthy }
      redis:     { condition: service_healthy }
      keycloak:  { condition: service_healthy }
    networks: [backend]

networks:
  backend:
    driver: bridge

volumes:
  openbao-data:
  pgdata:
  redisdata:
```

### The bootstrap script (runs once after the stack is up)

```bash
#!/usr/bin/env bash
# bootstrap.sh — idempotent initial configuration
set -euo pipefail

export BAO_ADDR=https://127.0.0.1:8200
export BAO_CACERT=./certs/ca.crt

# ── audit first ──
# NOTE: 2.7.1 — audit devices are declared in the server config:
#   audit "file" "file" {
#     description = "Local audit log (declarative)."
#     options { file_path = "/openbao/logs/audit.log" mode = "0600" log_raw = "false" }
#   }
bao audit list -detailed

# ── secret engines ──
bao secrets enable -path=secret kv-v2 2>/dev/null || true
bao secrets enable -path=db database 2>/dev/null || true
bao secrets enable -path=transit transit 2>/dev/null || true

# ── auth methods ──
bao auth enable -path=oidc oidc 2>/dev/null || true
bao auth enable -path=approle approle 2>/dev/null || true

# ── policies ──
bao policy write app-readonly - <<'EOF'
path "secret/data/myapp"        { capabilities = ["read"] }
path "secret/metadata/myapp"    { capabilities = ["read", "list"] }
path "database/creds/app"       { capabilities = ["read"] }
path "transit/encrypt/myapp"     { capabilities = ["update"] }
path "transit/decrypt/myapp"     { capabilities = ["update"] }
EOF

# ── approle for the app ──
bao write auth/approle/role/myapp \
    secret_id_ttl=10m secret_id_num_uses=1 \
    token_ttl=20m token_max_ttl=1h 2>/dev/null || true

# ── oidc for humans ──
#    NOTE: config path is auth/<mount>/config; oidc_discovery_url is the
#    BASE url (no .well-known); the client keys are oidc_client_id/_secret.
bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/enterprise" \
    oidc_client_id="openbao" \
    oidc_client_secret="$KEYCLOAK_CLIENT_SECRET" \
    default_role="human" 2>/dev/null || true

echo "bootstrap complete"
```

---

## 7.9 The anti-patterns

| ❌ Anti-pattern | Why it's bad | ✅ Do this |
|---|---|---|
| One shared "app" credential for all services | Can't attribute, can't revoke one | One role per service |
| `path "secret/*" { capabilities = ["*"] }` | Any app can read any secret | Per-service paths |
| Storing secrets in `.env` in git | Permanent exposure | OpenBao + AppRole |
| Root token in CI | Full compromise on CI breach | GitHub OIDC |
| `verify=False` in the TLS client | MITM | `BAO_CACERT` |
| Long TTL dynamic credentials (24h+) | Defeats the whole point | 1h default, 4h max |
| Logging the whole config at startup | Leaks into log aggregators | Log *keys present*, not values |
| One long-lived OpenBao token for the app | Can't rotate without downtime | Short TTL + renewal loop |
| `bao login` in a shared CI runner | Token cached on disk | Per-job OIDC login |
| Catching and printing OpenBao exceptions | Exceptions can contain tokens | Log the exception *type* only |

---

## 7.10 Level 7 checkpoint

1. What must match between Keycloak's issuer and OpenBao's `oidc_discovery_url`?
2. Why does Keycloak need a groups mapper configured on the client?
3. `role_id` vs `secret_id` in AppRole: which goes in the image, which goes in
   the deploy pipeline? Why?
4. Why is `bao agent` better than an entrypoint script for containers?
5. Why must `load_environment()` run before LangChain imports?
6. What is the danger of caching a *dynamic* credential in `bao proxy`?
7. Your Postgres pool holds connections past the lease expiry. What breaks and
   how do you fix it?
8. Is there a Redis dynamic-credentials plugin in 2.7.1? What do you do?
9. In the GitHub Actions flow, what must match between `audience=` and OpenBao's
   `bound_audiences`?
10. What should a CI policy *not* be able to do, and why?

**Next → [Level 8: EXPERT.md](08-EXPERT.md)** — namespaces, the plugin system,
workflows, External Keys, post-quantum crypto, CEL roles and control groups.

---

## 7.11 Scratchpad

```
Keycloak discovery:  http://keycloak:8080/realms/<realm>              (BASE url!)
Keycloak JWKS:       http://keycloak:8080/realms/<realm>/protocol/openid-connect/certs
OpenBao OIDC config: bao write auth/oidc/config oidc_discovery_url=... oidc_client_id=... oidc_client_secret=...
OIDC role:           bao write auth/oidc/role/human user_claim=preferred_username groups_claim=groups
GitHub Actions:      bao write auth/github-actions/config oidc_discovery_url=https://token.actions.githubusercontent.com
                     bao write auth/github-actions/role/github bound_audiences=["openbao"] bound_claims={...}
DB creds:            bao read db/creds/app
Transit:             bao write transit/encrypt/myapp plaintext=<base64>
LangChain env:       OPENAI_API_KEY / ANTHROPIC_API_KEY / LANGCHAIN_API_KEY
```
