# Module 07 — App Integration: The Secret Reaches the App

> **Where we are.** Meridian AI's secret store is built: `ai/platform` is a
> KV v2 mount, the Gemini key lives at `ai/platform/llm/gemini`, the
> `ai-harness-service` policy grants read on exactly one path, and the
> `ai-harness-service` AppRole hands out 15-minute tokens. Everything so far
> has been *operator* work — you typed commands, you saw the secrets.
>
> This module changes the actor. Now the **application** logs in to OpenBao
> by itself, at boot, and pulls its own credentials. No `.env`, no baked-in
> key, no restart needed when the key rotates. This is the module where the
> secret store stops being a place humans look and becomes a **runtime
> dependency** your service cannot start without.

**Files shipped with this module** (in `lab/app/` next to this README):

| File | What it is |
|---|---|
| `openbao_client.py` | A verbatim copy of the course's `lab/app/openbao_client.py`, so the unit tests below can run without the rest of the lab. |
| `test_openbao_client.py` | The unit tests from section 13.1 — the same file that ships in the course repo at `lab/app/test_openbao_client.py`. Standard-library `unittest`: no server, no credentials, no test runner to install. |
| `test_integration.py` | The integration tests from section 13.2. Needs a live OpenBao and the harness AppRole credentials. |
| `jwt_login_demo.py` | The runnable Pattern C demo from section 8.3.1 — mints a signed service-account token, points OpenBao's `jwt` auth method at a local JWKS, and logs in. The same file also ships in the course repo at `lab/app/jwt_login_demo.py`. Needs one dev-only dependency, `cryptography`, to sign the test token. |

**Status:** Complete. Every command in this module was executed against a
live OpenBao 2.7.1 server, and every transcript below is captured output —
not reconstructed. Captured transcripts came from an isolated instance
listening on `http://127.0.0.1:9506`; your lab listens on
`http://127.0.0.1:8200`. Only the port number differs — every path,
policy, capability, and error string is identical.

**The one exception, stated plainly:** the Kubernetes / AWS / GCP / Azure
rows in §8.3's Pattern C table describe *those platforms'* mechanisms.
OpenBao's own side of that pattern is shown as a **runnable** `jwt` auth
role in **§8.3.1**, and that section is a captured run of the shipped
`lab/app/jwt_login_demo.py`. The cloud-side token projection is not
something this lab can run, so *that* half is described, not captured —
the demo mints the same kind of signed token a cluster would project.

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| **AppRole** | A login with two halves: a public `role_id` and a secret `secret_id`, exchanged for a short-lived token. |
| **`role_id`** | Not a secret. It names *which* identity you are claiming. Safe in an env var, safe in Git. |
| **`secret_id`** | The secret half. Possession of it = ability to mint a token. Treat it like a password. |
| **Short-lived token** | The AppRole login returns a token with a TTL (15 min here). The app caches it in RAM and re-logs-in before it expires. |
| **KV v2 path layout** | The HTTP API is `<mount>/data/<key>`. The `bao kv` CLI hides this; raw HTTP does not. |
| **In-memory only** | The token and the fetched secret live in the process's heap. Never written to disk, never in `os.environ`. |
| **Fail fast** | If OpenBao is unreachable, the app **refuses to boot**. No fallback, no default key, no empty string. |
| **Refuse-to-boot rule** | An AI harness with no API key that "starts fine" and then fails 500s later is worse than one that dies at startup. |
| **`/health`** | Reports OpenBao's *seal state*, not just "the process is alive". A sealed OpenBao means secrets can no longer be fetched or rotated. |
| **80% re-auth** | The client re-logs-in when 20% of the token's TTL has elapsed, leaving headroom for slow in-flight requests. |
| **`ca_cert`** | The path to your internal CA bundle. Verification is on. There is no `verify=False` switch in this client, on purpose. |
| **No `ENV`/`ARG` secrets** | Build args and image env are baked into layers and image history. A secret there is a secret in your registry. |
| **Non-root container** | The app runs as uid 1000. A container escape should not hand the attacker root. |
| **Rotation without restart** | A new KV version appears; the running app reads it on its next read. No pod recreate, no cache flush. |
| **stdlib vs `hvac`** | `urllib` for the secret path (zero supply-chain surface); `hvac` when you need HA retry, standby handling, or an auth method you would otherwise write yourself. |

---

## 1. Why this matters

Picture the incident that made you the first platform engineer at Meridian
AI. The previous engineer wrote this:

```python
# app/config.py  — DO NOT DO THIS
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

and shipped a `.env` file to production. `.env` was gitignored, so it was
"safe". Three things then happened, none of them unusual:

1. Someone ran `docker inspect` during an incident and pasted the output
   into a ticket. The key was in the ticket forever.
2. Someone set `log_level=DEBUG` in a config file, and uvicorn's
   access log printed the request headers — including the key a downstream
   SDK sent as a query parameter.
3. A contractor with repo read access cloned the repo. `.env` was gitignored,
   but `docker-compose.yml` was not, and the CI job wrote the key into
   `~/.docker/config.json` as a registry credential to pull a private base
   image.

The key leaked. Gemini's bill went from $40/month to $9,000/month. The
response was to rotate the key, and to build a secret store properly.

**The naive fix** is "put the key in a secret manager" — which is exactly
what Modules 01–06 built. But there is a gap between "the secret is in a
secret store" and "the application uses the secret store." That gap is
where the next incident comes from, and it is where this module lives.

Three questions separate the two states:

| Question | The `.env` answer | The OpenBao answer |
|---|---|---|
| Where does the key live at boot? | A file on disk, or an env var in the container's config. | Nowhere. It is fetched at runtime. |
| What happens when the key rotates? | Someone edits the file, restarts the pod, and hopes. | A new KV version. The running app picks it up. |
| What happens if the key store is down? | The app starts with whatever was baked in. | The app refuses to start. Loudly. |
| Can a developer read the key? | Anyone with repo or image access. | Only whoever can authenticate to OpenBao. |
| What is in the image history? | Possibly the key. | Never the key. |

> **Production:** *The contract you are building here is narrow and should
> stay narrow: **the application can obtain its own credentials, and nothing
> about those credentials is persisted outside the process's memory.** Every
> design decision below exists to protect that one sentence.*

---

## 2. The core concept: the end-to-end flow

Before any code, you need the mental model. There are five steps, and they
happen in this order every single time the app starts.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │  CONTAINER START                                                     │
  │                                                                      │
  │  1. Docker starts the ai-harness container as uid 1000.               │
  │     Env carries: BAO_ADDR, BAO_ROLE_ID, BAO_SECRET_ID.               │
  │     (role_id = public. secret_id = secret. Nothing else. No key.)    │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────────┐
  │  2. APPROLE LOGIN                                                    │
  │     POST /v1/auth/approle/login  {role_id, secret_id}                │
  │     -> 200 { auth: { client_token, lease_duration: 900, policies } }  │
  │     The token is kept in a Python attribute. NOT in os.environ.      │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────────┐
  │  3. KV READ                                                           │
  │     GET /v1/ai/platform/data/llm/gemini                              │
  │     Header: X-Vault-Token: s.xxxxx                                  │
  │     -> 200 { data: { data: {api_key, model, project_id},             │
  │                       metadata: {version: 3, created_time: ...} } }   │
  │     Policy allows this path. Everything else is 403.                 │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────────┐
  │  4. IN-MEMORY ONLY                                                    │
  │     The api_key is a Python str in a module-level dict.              │
  │     It is never written to a file, never exported, never logged.      │
  │     It dies with the process.                                         │
  └──────────────────────────────┬───────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼───────────────────────────────────────┐
  │  5. SERVE                                                              │
  │     LangChain's ChatGoogleGenerativeAI(google_api_key=...) is built   │
  │     from that in-memory value. The /health endpoint reports OpenBao's │
  │     seal state so the LB can pull the pod if the store goes down.    │
  └──────────────────────────────────────────────────────────────────────┘
```

Two things in that diagram are worth staring at.

**First: the token is a step, not a payload.** Notice step 2 returns a
*token*, and step 3 uses that token to read a *different* resource. The
`secret_id` is not a key you keep using; it is a ticket you exchange once
for a short-lived credential. That is why rotation is cheap: you rotate the
underlying secret, not the credential.

**Second: the app has a dependency on OpenBao at runtime.** Not at build
time, not at deploy time — at *request* time. That is a new kind of
dependency your platform has to account for (health checks, ordering,
degraded modes). We will handle it explicitly.

> **If you find a tutorial saying "use a long-lived token from an env
> var":** *it is describing the pattern this module exists to replace. A
> token in an env var is a `.env` file with extra steps and a confusing
> name.*

---

## 3. Do it: build the platform

Everything below is real. The commands assume you have already run
`./scripts/prepare-lab.sh`, `docker compose up -d openbao`, and
`./scripts/init-lab.sh` from the `lab/` directory, and that you have
`export BAO_ADDR=http://127.0.0.1:8200` with a token that can write.

### 3.1 The secret, the policy, the AppRole

Three objects, three different jobs:

| Object | Job | Who touches it |
|---|---|---|
| KV v2 secret `ai/platform/llm/gemini` | Holds the actual key | The rotation bot (writes), the harness (reads) |
| Policy `ai-harness-service` | Says what the harness may do | The platform operator |
| AppRole `ai-harness-service` | Turns a `secret_id` into a token | The harness's login code |

Here is the whole platform being created from scratch, with real output.

```bash
$ bao secrets enable -path=ai/platform kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/platform/

$ bao write ai/platform/config cas_required=false max_versions=10
Success! Data written to: ai/platform/config

$ bao policy write ai-harness-service lab/policies/ai-harness-service.hcl
Success! Uploaded policy: ai-harness-service

$ bao kv put ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-4471"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T18:01:46.24156877Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1
```

> ⚠️ **Look at the path in the output:** `ai/platform/data/llm/gemini`.
> KV v2 puts a literal `data` segment in the middle. You wrote to
> `ai/platform/llm/gemini` and OpenBao stored it under `.../data/...`.
> Section 4.4 is about why your HTTP client has to know this.

Now the AppRole. Note the two TTL families — they are different things:

```bash
$ bao auth enable approle
Success! Enabled approle auth method at: approle/

$ bao write auth/approle/role/ai-harness-service \
    token_policies="ai-harness-service" \
    token_ttl=15m \
    token_max_ttl=1h \
    secret_id_ttl=1h \
    secret_id_num_uses=0
Success! Data written to: auth/approle/role/ai-harness-service
```

| Setting | Value | What it means |
|---|---|---|
| `token_ttl` | `15m` | How long a minted token lives. This is your blast radius. |
| `token_max_ttl` | `1h` | Ceiling if something renews it. |
| `secret_id_ttl` | `1h` | How long a generated `secret_id` stays usable. |
| `secret_id_num_uses` | `0` | Unlimited uses. See the trade-off note below. |

> **Trade-off:** *`secret_id_num_uses=0` means the `secret_id` can be
> replayed until it expires. `=1` means one login and then it is dead —
> which is the strongest possible guarantee, but it means your deployment
> system must mint a **fresh** `secret_id` for every pod start, and the
> "one `secret_id` in an env var" delivery pattern in section 8 collapses.
> Meridian AI runs `0` with a 1-hour TTL: the credential is short-lived
> enough that replay is a small window, and the delivery machinery stays
> simple. If your threat model includes "an attacker who reads the pod's
> environment can mint tokens for an hour", use `1` and a delivery pattern
> that issues a new `secret_id` per pod.*

Read the role back to confirm what OpenBao actually stored:

```bash
$ bao read -format=json auth/approle/role/ai-harness-service
{
    "request_id": "5aab85cd-fb0c-3bb3-2502-ef1169694bc2",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "bind_secret_id": true,
        "local_secret_ids": false,
        "secret_id_bound_cidrs": null,
        "secret_id_num_uses": 0,
        "secret_id_ttl": 3600,
        "token_bound_cidrs": [],
        "token_explicit_max_ttl": 0,
        "token_max_ttl": 3600,
        "token_no_default_policy": false,
        "token_num_uses": 0,
        "token_period": 0,
        "token_policies": [
            "ai-harness-service"
        ],
        "token_strictly_bind_ip": false,
        "token_ttl": 900,
        "token_type": "default"
    },
    "warnings": null
}
```

`token_ttl: 900` — that is 15 minutes in seconds. `token_policies:
["ai-harness-service"]`. Note there is **no `default` policy in the list**
here because `token_no_default_policy` is false, meaning the `default`
policy *is* also attached implicitly. That is fine for the `default` policy
(which is nearly empty), but it is a good habit to check.

### 3.2 Mint the two halves

```bash
$ bao read -field=role_id auth/approle/role/ai-harness-service/role-id
ab4852b3-d888-1ab9-4582-19e39ad3820d

$ bao write -force -format=json auth/approle/role/ai-harness-service/secret-id
{
  "request_id": "3dbb1155-a029-6f55-4449-a261ff5cc7cd",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "secret_id": "b5c80e34-a217-f52c-1ad8-e4923119bdf8",
    "secret_id_accessor": "9f0a182f-668d-65fc-1004-159eac8af301",
    "secret_id_num_uses": 0,
    "secret_id_ttl": 3600
  },
  "warnings": null
}
```

Two different identifiers and they behave differently:

| | `role_id` | `secret_id` |
|---|---|---|
| Stable across generations? | **Yes.** One per role, forever. | **No.** A new one every time you ask. |
| Secret? | No. | Yes. |
| Where it goes | `BAO_ROLE_ID` env var, image config, Git. | Secret delivery channel, **not** Git. |
| What it proves | "I want to be the AI harness." | "I am *allowed* to be the AI harness." |

The `secret_id_accessor` is the safe handle. It identifies a `secret_id`
without revealing it, so you can revoke one specific credential without
rotating the whole role:

```bash
$ bao list auth/approle/role/ai-harness-service/secret-id
Keys
----
9f0a182f-668d-65fc-1004-159eac8af301
```

> **Production:** *Delete the accessor to revoke that specific
> `secret_id` immediately, without touching the role:*
> `bao delete auth/approle/role/ai-harness-service/secret-id-accessor/destroy secret_id_accessor=9f0a182f-...`.
> The path is `secret-id-accessor/destroy` and the accessor goes in the
> **body** as `secret_id_accessor` — `.../secret-id/<id>` is a 404
> (`unsupported path`).
> This is your "kill this one credential" button during an incident.

---

## 4. The client, line by line

The file is `lab/app/openbao_client.py`. It is 299 lines and it is the
single most important file in this course, because it is the code that
touches your secrets. We are going to read it section by section.

### 4.1 The imports — the trust boundary, made visible

```python
# openbao_client.py:35-46
from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
```

**Every one of those is in the Python standard library.** No `requests`,
no `httpx`, no `requests`, no `hvac`, no `pydantic` on this path.

> **Why this matters more than it looks.** This module sits *on* the secret
> reading path. When `read_secret()` runs, the code executing is deciding
> which bytes of your Gemini key get to live in your process. Every
> third-party library in that path is a third party that could be
> compromised, could be typosquatted, could turn a new release into a
> backdoor, and would execute with your credential in hand.
>
> Contrast this with the business-logic path. FastAPI, LangChain, Pydantic
> live in the *application* trust boundary: a compromised parser in your
> HTTP framework is a serious problem, but it does not by itself hand the
> attacker the key. The secret-fetching path is different in kind, and it
> deserves different discipline.
>
> `urllib.request` is part of CPython, is audited with the interpreter, has
> no transitive dependencies at all, and receives security fixes as part of
> the Python release cycle. That is the whole argument.

Note also `from __future__ import annotations` on line 35: it makes the
`str | None` annotations on line 91 evaluate lazily, so the file works on
Python 3.9 even though the syntax is 3.10+. The container runs 3.12, but
the annotation form costs you nothing.

### 4.2 The error type — one exception for every failure

```python
# openbao_client.py:51-52
class OpenBaoError(RuntimeError):
    """Raised when OpenBao cannot be reached or refuses an operation."""
```

One exception type for *all* failures. That is a deliberate design choice
and it has a cost.

**The benefit:** the caller does not have to know whether the failure was a
network timeout, a 403, a malformed JSON body, or a missing credential.
`except OpenBaoError` catches all of it, and the message tells you which
it was.

**The cost:** you cannot react differently to "OpenBao is down" versus
"my policy is wrong" *by exception type*. You parse the message, or you
add a `subclass`. For a bootstrap path where every failure means "do not
start", collapsing them into one type is the right trade. For a hot path
where you might want to serve stale data on a network blip, it is not.

### 4.3 The lease dataclass — metadata you will actually use

```python
# openbao_client.py:55-77
@dataclass(frozen=True)
class SecretLease:
    """A secret plus the metadata OpenBao attached to it."""

    value: dict[str, Any]
    version: int
    created_time: str
    lease_id: str = ""
    lease_duration: int = 0
    renewable: bool = False

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "SecretLease":
        auth = data.get("auth", {})
        envelope = data.get("data", {}) or {}
        return cls(
            value=envelope.get("data", {}) or {},
            version=(envelope.get("metadata", {}) or {}).get("version", 0),
            created_time=(envelope.get("metadata", {}) or {}).get("created_time", ""),
            lease_id=data.get("lease_id", "") or "",
            lease_duration=data.get("lease_duration", 0) or 0,
            renewable=data.get("renewable", False),
        )
```

Three decisions here.

**`frozen=True`** (line 55) means the lease cannot be mutated after
creation. A secret handle that can be edited in place is a secret handle
that can be edited *by accident* — a line of code that does
`lease.value["api_key"] = "wrong"`. Frozen makes that a loud
`FrozenInstanceError` instead of a silent misconfiguration.

**`value=envelope.get("data", {}) or {}` (line 71)** — this is the
*double `.data`* that trips everyone. KV v2's HTTP response nests the
actual secret one level deeper than you expect:

```json
{
  "data": {
    "data":     { "api_key": "AIzaSy...", "model": "gemini-2.0-flash" },
    "metadata": { "version": 1, "created_time": "2026-10-21T18:01:46Z" }
  }
}
```

`response["data"]` is the *envelope*. `response["data"]["data"]` is the
*secret*. The `bao kv get` CLI hides this because it knows the mount and
unwraps it for you. Raw HTTP does not.

**The `or {}` guards** (lines 71–74) handle OpenBao returning `null`
instead of `{}` for an empty body. A `null` would blow up on `.get()` with
an `AttributeError` instead of a clean empty dict. This is defensive
coding at the boundary — exactly where you want it, and nowhere else.

**`version` and `created_time` are not decoration.** They are how you
prove a rotation happened (section 9) and how you log *which* credential
you loaded without logging the credential.

### 4.4 `read_secret` — the `<mount>/data/<key>` trap

This is the single most common mistake when talking to KV v2 over HTTP.

```python
# openbao_client.py:210-228
    def read_secret(self, mount: str, key_path: str = "") -> SecretLease:
        """Read a KV v2 secret.

        IMPORTANT - KV v2's API layout is `<mount>/data/<key>`, NOT
        `<mount>/<key>/data`. The `bao kv` CLI hides this because it knows
        the mount; raw HTTP does not. Getting it wrong returns a confusing
        403 ("permission denied") because the policy grants
        `<mount>/data/<key>` and you asked for a path that does not exist.

        Example:
            read_secret("ai/platform", "llm/gemini")
            -> GET /v1/ai/platform/data/llm/gemini
        """
        self._ensure_token()
        api_path = f"{mount.rstrip('/')}/data"
        if key_path:
            api_path = f"{api_path}/{key_path.lstrip('/')}"
        data = self._request("GET", api_path)
        return SecretLease.from_response(data)
```

Here is what actually happens when you get it wrong. Real output, from the
live server:

```text
--- TRAP: reading <mount>/<key> instead of <mount>/data/<key> ---
OpenBaoError: OpenBao returned 403 for GET ai/platform/llm/gemini: {"errors":["1 error occurred:\n\t* permission denied\n\n"]}
```

> ⚠️ **The error is a lie.** You asked for a path that does not exist, and
> OpenBao told you *permission denied*. It is not a permissions problem —
> your policy is fine. It is a **path** problem. This is the most
> confusing failure in the whole of KV v2, and it sends people off to
> rewrite policies that were correct all along.
>
> **How to tell them apart:** if `bao kv get ai/platform/llm/gemini`
> works from the CLI but your HTTP call to the *same* path returns 403,
> you have the layout wrong, not the policy. Verify with
> `bao read ai/platform/data/llm/gemini` — the `data` segment is the tell.

The same code path, done right, is what the app actually runs:

```text
VERSION: 1 CREATED: 2026-10-21T18:01:46.24156877Z
KEY: AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
```

And here is the *correct* 403 — a path that exists but is not granted:

```text
--- TRAP: reading a secret the policy does NOT cover (db/postgres) ---
OpenBaoError: OpenBao returned 403 for GET ai/platform/data/db/postgres: {"errors":["1 error occurred:\n\t* permission denied\n\n"]}
```

Compare the two. Same status code, same message, completely different
cause. The difference is in the path: `ai/platform/data/db/postgres` has
the `data` segment, so it reached the KV v2 engine and was refused by
policy. `ai/platform/llm/gemini` has no `data` segment, so it never
reached the engine at all.

> **Production:** *When you write a policy, write the path exactly as the
> API addresses it — `ai/platform/data/llm/gemini` — and remember that the
> `metadata` path is a **separate** path with its **separate** capability.
> The harness policy needs both:*

```hcl
# lab/policies/ai-harness-service.hcl
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}

path "ai/platform/metadata/llm/gemini" {
  capabilities = ["read"]
}
```

### 4.5 `list_secrets` — and the capability it needs

```python
# openbao_client.py:237-244
    def list_secrets(self, mount: str, key_path: str = "") -> list[str]:
        """List secret names under a path (KV v2 metadata layer)."""
        self._ensure_token()
        api_path = f"{mount.rstrip('/')}/metadata"
        if key_path:
            api_path = f"{api_path}/{key_path.lstrip('/')}"
        data = self._request("GET", api_path)
        return list((data.get("data") or {}).get("keys", []) or [])
```

Note the path: `<mount>/metadata/...`, the **other** half of the KV v2
split. `data/` holds values, `metadata/` holds the version history and the
directory listing. The client exposes both because a real service
sometimes wants to know *what* is available.

But the harness policy grants `read` on `ai/platform/metadata/llm/gemini`
— a *specific* path — and `read` is not the same as `list`. OpenBao's
capability model distinguishes them:

| Capability | Grants |
|---|---|
| `read` | Read the value at this path. |
| `list` | Enumerate the names *under* this path. |
| `sudo` | Perform privileged operations. |
| `create` / `update` / `delete` | Write. |
| `patch` | Partial write. |
| `deny` | Explicitly deny. |

Real output from the live server, using the harness policy:

```text
--- LIST without a 'list' capability ---
OpenBaoError: OpenBao returned 403 for GET ai/platform/metadata/llm: {"errors":["1 error occurred:\n\t* permission denied\n\n"]}
```

> **Why this is a feature, not a bug.** Listing is *discovery*. A service
> that can list `ai/platform/metadata/llm` can see every secret name in
> that folder — including `db/postgres` and `cache/redis` if they were
> there. The harness knows the exact path of the one key it needs. It has
> no business enumerating its neighbours, so the policy does not give it
> `list`.
>
> **This is least privilege expressed as a data structure, not a rule.**
> "Read one specific thing" is strictly stronger than "read everything in
> this folder". The `list_secrets` method still exists in the client
> because the *rotation bot* — a different AppRole with a different
> policy — needs it.

### 4.6 `login` — the AppRole exchange, and the 80% rule

```python
# openbao_client.py:173-202
    def login(self) -> str:
        """Authenticate via AppRole and cache the token.

        Raises OpenBaoError if credentials are missing. We deliberately do
        NOT accept a pre-set BAO_TOKEN here for production use: an
        environment-provided token is the .env pattern we are replacing.
        """
        if not self.role_id or not self.secret_id:
            raise OpenBaoError(
                "BAO_ROLE_ID and BAO_SECRET_ID are required for AppRole login. "
                "Refusing to start without credentials."
            )

        data = self._request(
            "POST",
            "auth/approle/login",
            token="",
            body={"role_id": self.role_id, "secret_id": self.secret_id},
        )
        auth = data.get("auth", {})
        self._token = auth.get("client_token", "")
        ttl = int(auth.get("lease_duration", 0))
        # Renew at 80% of TTL to leave headroom for slow requests.
        self._token_expires_at = time.time() + max(ttl * 0.8, 1)
        logger.info(
            "Authenticated to OpenBao via AppRole (ttl=%ss, policies=%s)",
            ttl,
            auth.get("policies"),
        )
        return self._token
```

**Lines 180–184: the credential check happens before anything else.** No
`role_id`, no `secret_id`, no login attempt. This is the "refuse to boot"
rule at the client level. Real output:

```text
--- FAIL-FAST: no credentials ---
OpenBaoError: BAO_ROLE_ID and BAO_SECRET_ID are required for AppRole login. Refusing to start without credentials.
```

**Line 189: `token=""` is passed explicitly.** This is subtle and
important. Look at `_headers` (line 121–125):

```python
    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {"X-Vault-Token": token if token is not None else self._token}
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        return headers
```

The `None` sentinel means "use my cached token". The empty string `""`
means "send an empty token header". The login request must send an empty
token header — sending your *stale* token to the login endpoint would be
sloppy and, on a re-login after expiry, would send an expired token
where none is expected. The three-state parameter (`None` vs `""` vs a
real token) is the cleanest way to express that.

**Line 192: the `auth` envelope.** The AppRole login response nests the
token one level down:

```json
{
  "auth": {
    "client_token": "s.Fd9zbM...",
    "accessor": "...",
    "policies": ["ai-harness-service", "default"],
    "lease_duration": 900,
    "renewable": true
  }
}
```

**Line 196: the 80% rule — `self._token_expires_at = time.time() + max(ttl * 0.8, 1)`.**

This is the line that separates a client that works from a client that
works at 3am. If you re-authenticate at exactly 100% of TTL, then a
request that starts at 99% of the TTL and takes two seconds will arrive
after the token died — and you get a 403 on a request you had no reason to
think was bad. Re-authenticating at 80% means you always have 20% of the
TTL (three minutes on a 15-minute token) of headroom for slow requests
and clock skew between your host and OpenBao.

The `max(ttl * 0.8, 1)` floor protects against a `lease_duration` of `0`
(which would mean "re-auth immediately, in a hot loop"). One second is the
minimum window.

**Proof it works.** I created a probe role with a 10-second token TTL and
watched the token change at exactly the 80% mark:

```bash
$ bao write auth/approle/role/short-ttl-probe \
    token_policies="ai-harness-service" token_ttl=10s token_max_ttl=1h \
    secret_id_ttl=1h secret_id_num_uses=0
```

```text
t+  0.0s token=s.DAlQzhIBnFFA... expires_in=  8.0s
t+  2.0s token=s.DAlQzhIBnFFA... expires_in=  6.0s
t+  4.0s token=s.DAlQzhIBnFFA... expires_in=  4.0s
t+  6.0s token=s.DAlQzhIBnFFA... expires_in=  2.0s
t+  8.0s token=s.Vhq2YbTPK4OF... expires_in=  8.0s     <-- re-auth
t+ 10.1s token=s.Vhq2YbTPK4OF... expires_in=  6.0s
```

The token is stable for 8 seconds, then changes. `expires_in` resets to
8.0s. Note the role only has `read` on one path — it is a *login* role,
not a broad one.

**Lines 197–201: what gets logged.** `ttl` and `policies`. **Never the
token, never the secret.** A log line that contains a live credential is a
log line that ends up in a SIEM, a log aggregator, a support ticket, and
your new colleague's terminal scrollback. If you log one thing about an
auth event, log *how long the credential lives and what it can do*.

Real output:

```text
2026-10-21 18:02:55,149 INFO     openbao_client: Authenticated to OpenBao via AppRole (ttl=900s, policies=['ai-harness-service', 'default'])
```

### 4.7 `_ensure_token` — the only place re-auth happens

```python
# openbao_client.py:204-206
    def _ensure_token(self) -> None:
        if not self._token or time.time() >= self._token_expires_at:
            self.login()
```

Three lines, and they carry all the state. Every public method calls
`_ensure_token()` first. The consequences:

- **The token is a single in-memory string** (line 110: `self._token: str = ""`).
  Not a file, not an env var, not a shared cache.
- **Re-auth is transparent** to the caller. `read_secret()` does not care
  whether the token it just used was 1 second old or 14 minutes old.
- **The app never handles a token expiry** as an application error. It is
  an implementation detail of the client.

> **Production:** *This is single-flight by accident, not by design. If
> twenty threads call `read_secret()` at the same instant with an expired
> token, all twenty will log in. At Meridian AI's scale that is fine —
> AppRole login is cheap and the 80% window means they will not all fire
> at once. If you have a high-concurrency service and a 30-second token
> TTL, wrap `login()` in a `threading.Lock`. The `hvac` client does this
> for you; see section 12.*

### 4.8 `_request` — TLS, errors, and the no-fallback rule

```python
# openbao_client.py:127-169
    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated request against OpenBao."""
        url = f"{self.addr}/v1/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(token),
            method=method,
        )
        if data is not None:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise OpenBaoError(
                f"OpenBao returned {exc.code} for {method} {path}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise OpenBaoError(
                f"Cannot reach OpenBao at {self.addr}: {exc}. "
                "Refusing to start - a secret-less fallback is not acceptable."
            ) from exc

        if not raw:
            return {}
        return json.loads(raw.decode())
```

**Line 137: `url = f"{self.addr}/v1/{path.lstrip('/')}"`.** The `/v1/` prefix
is the API version. It is not optional and it is not in the client
config — it is baked in, because a KV v2 client talking to a v0 API is
broken by construction.

**Line 139: `urlencode(params)`.** Note this is `urllib.parse.urlencode`,
not `requests`. It produces `?version=2`. It does **not** produce
`?version=2&` or a trailing `?` when `params` is empty, because line 137
guards it. The `read_secret_version` method (line 230–235) is the only
caller, and it uses it to read a *specific historical version* — a
genuinely useful operation during an incident ("which key was live at
02:14?").

**Line 148–149: `Content-Type` is added only when there is a body.** A
`GET` with `Content-Type: application/json` and no body is a wart; some
proxies dislike it. Small correctness detail, but it is the kind that
bites you in a meshed environment with an enforcing gateway.

**Lines 152–153: the timeout is always passed.** `urlopen(req, timeout=...)`
without a timeout can hang for the OS's TCP connect timeout — often two
minutes. In a FastAPI startup path, a two-minute hang is a two-minute
outage and a confusing "why did the pod take so long to start". Ten
seconds is a good default.

**Lines 156–160: HTTP errors are read, then re-raised with the body
attached.** `exc.read()` is what makes the "permission denied" message
possible. Without it you get `OpenBaoError: OpenBao returned 403` and you
learn nothing. The `[:500]` slice stops a 10MB error body from eating
your logs.

> ⚠️ **CLI gotcha:** *the OpenBao CLI has a similar trap. `bao read
> -format=json` works, but `-f=json` means `--force` on write commands and
> errors out. Use `-format=json`, always.*

**Lines 161–165: the network-failure branch is the important one.**

```python
            raise OpenBaoError(
                f"Cannot reach OpenBao at {self.addr}: {exc}. "
                "Refusing to start - a secret-less fallback is not acceptable."
            ) from exc
```

There is no `except` clause anywhere in this file that returns a default,
an empty string, or `None` for a secret. The client either returns real
data or raises. That is the **no-fallback** rule, and it is enforced
structurally — you cannot accidentally introduce a fallback without
writing a new `except` block that returns something.

Why is this so important? Because a fallback is the *most dangerous* line
of code you can write in a secret client. Consider:

```python
# NEVER WRITE THIS
try:
    lease = client.read_secret("ai/platform", "llm/gemini")
except OpenBaoError:
    lease = SecretLease(value={"api_key": os.getenv("GEMINI_API_KEY", "")}, ...)
```

Now OpenBao is down at 03:00, your app starts, it logs a warning, and it
serves traffic with an **empty API key**. Every request fails at the
provider with a 403. The on-call engineer looks at the AI harness and sees
"healthy". They look at OpenBao and sees "sealed". Neither of them looks
at the fallback that made the app look healthy. The outage lasts four
hours because the symptom is disconnected from the cause.

**The `from exc` on line 165** preserves the original exception as
`__cause__`, so the traceback shows both the OpenBao error and the
underlying socket error. Chained exceptions matter when you are reading a
stack trace at 3am.

### 4.9 `health` — the unauthenticated probe

```python
# openbao_client.py:246-262
    def health(self) -> dict[str, Any]:
        """Unauthenticated health probe. Useful for container healthchecks."""
        req = urllib.request.Request(f"{self.addr}/v1/sys/health", method="GET")
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Health returns 429/472/473/501/503 for degraded states - those
            # are still valid JSON bodies, so parse them rather than raise.
            try:
                return json.loads(exc.read().decode())
            except Exception:
                return {"initialized": False, "sealed": True, "code": exc.code}
        except (urllib.error.URLError, OSError):
            return {"initialized": False, "sealed": True, "code": 0}
```

**`/v1/sys/health` needs no token.** That is deliberate on OpenBao's part:
a load balancer or a container healthcheck must be able to ask "is the
store alive?" without holding a credential.

**The `except urllib.error.HTTPError` branch is subtle and correct.**
OpenBao's health endpoint returns a non-2xx status for degraded states:
429 (performance standby), 472 (DR secondary), 473 (performance standby),
501 (not initialized), 503 (sealed). **All of those still carry a valid
JSON body describing the state.** If you `raise` on them, you throw away
the exact information you wanted. So this code *parses the error body and
returns it*.

Real output while the server is healthy:

```text
--- HEALTH (unauthenticated) ---
{
  "initialized": true,
  "sealed": false,
  "standby": false,
  "replication_performance_mode": "disabled",
  "replication_dr_mode": "disabled",
  "server_time_utc": 1792605717,
  "version": "2.7.1",
  "cluster_name": "vault-cluster-47878852",
  "cluster_id": "6b28eabc-3829-2768-3c00-3ebb203f0198"
}
```

And real output after `bao operator seal`:

```text
=== now SEAL the vault and re-run the health probe ===
Success! Vault is sealed.
raw /v1/sys/health -> {
  "initialized": true,
  "sealed": true,
  "standby": true,
  "replication_performance_mode": "unknown",
  "replication_dr_mode": "unknown",
  "server_time_utc": 1792605775,
  "version": "2.7.1"
}
```

> ⚠️ **The `health` method never raises.** Look at the last `except` on
> line 261: an unreachable OpenBao becomes `{"initialized": False,
> "sealed": True, "code": 0}`. This is a **deliberate exception to the
> no-fallback rule** — and it is a *good* one, because the return value
> carries the truth ("not initialized, sealed") rather than hiding it.
> The rule is "never substitute a plausible-looking value for the truth",
> not "never return a default". Here the default *is* the truth.

### 4.10 The TLS path

```python
# openbao_client.py:113-117
        # TLS verification. In production you MUST point ca_cert at your
        # internal CA bundle. Never set verify=False.
        self._ssl_context: ssl.SSLContext | None = None
        if self.addr.startswith("https://"):
            self._ssl_context = ssl.create_default_context(cafile=ca_cert)
```

Read this carefully, because it is the difference between "encrypted" and
"secure":

1. **Verification is on and cannot be turned off.** There is no
   `verify=False`, no `ssl._create_unverified_context()`, no "just for
   dev" escape hatch. `ssl.create_default_context()` starts with
   `CERT_REQUIRED` and hostname checking enabled. If you need to disable
   verification, you have to edit this file and say so in a commit
   message.
2. **The context is only built for `https://` URLs.** For the lab's
   `http://127.0.0.1:8200`, `self._ssl_context` stays `None` and
   `urlopen(context=None)` is fine.
3. **`cafile=ca_cert` is how you trust your internal CA.** In production
   you point `BAO_CA_CERT` (or the constructor argument) at your
   organisation's CA bundle — a file baked into the image, not a secret.
   The CA certificate is **public information**; it is a trust anchor, not
   a credential. It is safe in the image.

> ⚠️ **The classic mistake:** `ssl._create_unverified_context()`. It is
> one line, it "fixes" the certificate error, and it turns your TLS
> connection into an encrypted channel with **no authentication of the
> peer**. An attacker on the network can present any certificate and
> read your `secret_id` in cleartext. You have encrypted the connection
> and thrown away the only thing that made it safe. The fix for a
> certificate error is to install the CA, not to stop checking.

> **Production:** *`ca_cert` should point at a bundle that contains your
> internal CA **and** the public roots, because OpenBao's own certificate
> might chain to a public CA while its TLS listener uses a certificate
> from your internal PKI. Ship the bundle in the image as a non-secret
> file (e.g. `/app/certs/meridian-ca-bundle.crt`) and pass
> `BAO_CA_CERT=/app/certs/meridian-ca-bundle.crt`.*

### 4.11 `get_gemini_credentials` — the shape the app consumes

```python
# openbao_client.py:281-299
def get_gemini_credentials(client: OpenBaoClient) -> dict[str, str]:
    """Fetch the Gemini API credentials from OpenBao.

    This is the function the FastAPI app calls at startup. Note the shape of
    the return value: a plain dict of strings, with the key present only in
    memory.
    """
    lease = client.read_secret("ai/platform", "llm/gemini")
    api_key = lease.value.get("api_key")
    if not api_key:
        raise OpenBaoError(
            f"Gemini secret at ai/platform/llm/gemini has no 'api_key' field. "
            f"Version={lease.version} created={lease.created_time}"
        )
    return {
        "api_key": api_key,
        "model": lease.value.get("model", "gemini-2.0-flash"),
        "project_id": lease.value.get("project_id", ""),
    }
```

**The `if not api_key` check (lines 290–294) is a schema check, not a
truthiness check.** A secret that exists but is missing the field you
need is a *different* failure from a secret that does not exist. The
first is a content bug — somebody wrote the wrong keys into KV. The
second is a 403. Both should stop the app, but the messages should
differ, and this one tells you the version and creation time so you can
go find the right write in the version history.

**The return type is `dict[str, str]`.** Plain strings, no custom
objects, no OpenBao types leaking into the application. The app layer
does not need to know that this came from a KV v2 lease. That separation
is what lets you swap the secret engine (or the whole secret store) later
without touching `main.py`.

**The key is now a Python `str` in a dict.** It is in the heap. It is
*not* in the environment, *not* on disk, *not* in a log line. Section 11
is honest about what that still means.

---

## 5. The FastAPI app

`lab/app/main.py` is 153 lines. Three things in it matter: the lifespan
startup, the `/health` endpoint, and the LangChain hand-off.

### 5.1 The lifespan startup — the refuse-to-boot rule

```python
# main.py:34-58
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fetch secrets from OpenBao before serving traffic.

    If this fails, the app must NOT start. A degraded AI harness that
    silently lacks an API key is worse than one that refuses to boot.
    """
    global bao_client, _credentials

    bao_client = OpenBaoClient()
    logger.info("Connecting to OpenBao at %s", bao_client.addr)

    try:
        _credentials = get_gemini_credentials(bao_client)
    except OpenBaoError as exc:
        logger.error("FATAL: could not obtain secrets from OpenBao: %s", exc)
        raise

    # Never log the key itself. Log only enough to confirm which version we got.
    logger.info("Loaded Gemini credentials (version from OpenBao metadata)")
    logger.info("Model: %s | Project: %s", _credentials.get("model"),
                _credentials.get("project_id"))
    yield
    if bao_client:
        bao_client.close()
```

**What a `lifespan` context manager is:** FastAPI runs the code *before*
the `yield` when the application starts, and the code *after* the `yield`
when it shuts down. The window between them is when the app serves
requests. This is the modern replacement for the old `@app.on_event("startup")`
decorator, and it is the right place for this work because the
startup/teardown are a single, readable block.

**Why the secrets fetch belongs here and not in a route handler.** If you
fetch the key on first request, then:

- The first user to hit your service waits for an OpenBao round-trip.
- If OpenBao is down, the first user gets a 500 instead of the pod failing
  its healthcheck and being replaced.
- Kubernetes' `readinessProbe` has nothing meaningful to probe.

Fetching in the lifespan means: **the pod is either fully ready with
credentials, or it never accepts traffic at all.**

**The `raise` on line 50 is the refuse-to-boot rule.** The `except` block
logs `FATAL:` and then **re-raises**. It does not swallow. It does not
return. The exception propagates out of the lifespan, uvicorn aborts the
boot, the container exits non-zero, and the orchestrator restarts it —
and it keeps failing loudly, which is exactly what you want during an
OpenBao outage. You want a crash loop you can see in `kubectl get pods`,
not a fleet of 200-OK-but-broken replicas.

**`logger.info("Model: %s | Project: %s", ...)` on line 54** — the log
records *which* configuration was loaded without recording the credential.
`project_id` is not secret. `api_key` is. The line is written so that
adding a secret to it requires a deliberate edit.

**Line 58: `bao_client.close()`.** There was a genuine bug here — see
§5.1. The `OpenBaoClient` class in `openbao_client.py` had **no
`close()` method**, so this raised `AttributeError` during shutdown.
It is now fixed: the client has a `close()` that drops the cached
bearer token on the way out.

> **Production:** *The fix is a `close()` that clears the cached token.
> `urllib` opens a fresh connection per request and keeps no session
> state, so there is no pool to drain — but dropping the credential still
> matters, because it is a bearer token and the process should not be
> holding one in memory any longer than it has to.*
> **Production:** *The right fix is either to add a `close()` that is a
> no-op (there is no connection pool to close — `urllib` opens a fresh
> connection per request) or to delete the call. I lean towards **adding
> a no-op `close()`** with a docstring explaining that `urllib` manages
> connections per-request, because the call site reads correctly and
> future maintainers will add a real one when a session pool arrives.*

**The `global` statement on line 41** is how the module-level
`bao_client` and `_credentials` (line 30–31) get populated. This is
module-level mutable state, and it is worth being honest about that: it
means the credentials live for the lifetime of the process, and any code
in the process can reach them. That is the same "honest caveat" section
11 is about. The alternative — passing credentials through a dependency
injection graph — is better design but does not change the fundamental
fact that the key must be in the process's memory to be used.

### 5.2 `/health` — report the *store's* state, not just your own

```python
# main.py:68-93
class HealthResponse(BaseModel):
    status: str
    openbao_initialized: bool
    openbao_sealed: bool
    secrets_loaded: bool
    gemini_model: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + readiness.

    Reports OpenBao's own seal state. If OpenBao is sealed, the harness
    cannot fetch or renew secrets, so it should be pulled from the LB.
    """
    if bao_client is None:
        raise HTTPException(status_code=503, detail="OpenBao client not initialised")

    health_data = bao_client.health()
    return HealthResponse(
        status="ok" if health_data.get("initialized") and not health_data.get("sealed") else "degraded",
        openbao_initialized=bool(health_data.get("initialized")),
        openbao_sealed=bool(health_data.get("sealed")),
        secrets_loaded=bool(_credentials.get("api_key")),
        gemini_model=_credentials.get("model", ""),
    )
```

This endpoint is small and it is the most operationally valuable thing in
the file.

**It reports four separate facts**, not one status:

| Field | Question it answers |
|---|---|
| `openbao_initialized` | Has OpenBao ever been initialised? |
| `openbao_sealed` | Can OpenBao currently serve secrets? |
| `secrets_loaded` | Do *we* hold a credential right now? |
| `status` | Should traffic come to this pod? |

**Why "sealed" matters more than you think.** When OpenBao is sealed, the
app's *existing* in-memory token keeps working until it expires. But the
app **cannot re-authenticate**, so within 15 minutes every pod that is
running will start getting 403s on its next secret read. OpenBao being
sealed is a **slow-motion** outage, and the only way to see it coming is
to report the seal state proactively. If your `/health` only returns
`{"status": "ok"}` because the process is alive, you find out when users
start reporting 500s.

Real output from the app's health logic, healthy:

```text
2026-10-21 18:02:55,137 INFO     meridian.ai-harness: Connecting to OpenBao at http://127.0.0.1:9506
2026-10-21 18:02:55,149 INFO     openbao_client: Authenticated to OpenBao via AppRole (ttl=900s, policies=['ai-harness-service', 'default'])
2026-10-21 18:02:55,152 INFO     meridian.ai-harness: Loaded Gemini credentials (version from OpenBao metadata)
2026-10-21 18:02:55,152 INFO     meridian.ai-harness: Model: gemini-2.0-flash | Project: meridian-ai-prod-4471
GET /health -> 200
{
  "status": "ok",
  "openbao_initialized": true,
  "openbao_sealed": false,
  "secrets_loaded": true,
  "gemini_model": "gemini-2.0-flash"
}
```

And with OpenBao sealed:

```text
=== now SEAL the vault and re-run the health probe ===
Success! Vault is sealed.
app /health payload -> {"status": "degraded", "openbao_initialized": true, "openbao_sealed": true, "secrets_loaded": true, "gemini_model": "gemini-2.0-flash"}
```

Note `secrets_loaded: true` while `status: degraded`. That is precise and
correct: we *do* still hold a key, but the store is sealed so we cannot
refresh it, and the app is on a clock. A good health endpoint tells you
which of your dependencies is broken, not just that something is.

And here is what the **app** sees when it tries to re-authenticate
against a sealed OpenBao — the exact message the client raises:

```text
$ bao operator seal
Success! Vault is sealed.
$ python3 -c "from openbao_client import OpenBaoClient; OpenBaoClient(...).read_secret('ai/platform','llm/gemini')"
OpenBaoError: OpenBao returned 503 for POST auth/approle/login: {"errors":["Vault is sealed"]}
```

**503, not 403, and not a timeout.** That distinction is worth
memorising:

| OpenBao state | AppRole login returns | Meaning |
|---|---|---|
| Healthy | `200` + token | Normal |
| Sealed | `503` `{"errors":["Vault is sealed"]}` | The store is down; **unseal it** |
| Policy denies the role | `403` `permission denied` | Your policy or role config is wrong |
| Wrong `secret_id` | `400` `invalid role or secret ID` | The credential is wrong, revoked, or expired |
| Wrong `role_id` | `400` `invalid role or secret ID` | Same message, different cause — check both |
| Server unreachable | `OpenBaoError: Cannot reach OpenBao at ...` | Network, DNS, or the port |

Five different failures, five different responses, and only one of them
is fixed by unsealing. If your runbook says "the harness is down, try
unsealing" for every 5xx, you will spend an hour unsealing a perfectly
healthy vault. The message tells you which bucket you are in.

> **Production:** *Split this into two probes.* `/health/live` — "the
> process is up" — should never touch OpenBao, or a sealed OpenBao will
> kill every pod in the fleet at once (a restart storm during the very
> incident you are trying to survive). `/health/ready` — "this pod can
> serve traffic" — should include the OpenBao state. Point Kubernetes'
> `livenessProbe` at the first and `readinessProbe` at the second. Never
> let a liveness probe depend on a remote service.*

### 5.3 The LangChain integration point

```python
# main.py:101-128
@app.post("/v1/chat")
def chat(req: ChatRequest) -> dict:
    """Stub for the real LangChain call.

    The real implementation would use `google.generativeai` / LangChain's
    ChatGoogleGenerativeAI with `google_api_key=_credentials["api_key"]`.
    We keep the key in a module-global so it never touches a log line.
    """
    if not _credentials.get("api_key"):
        raise HTTPException(status_code=503, detail="Gemini credentials not loaded")

    # ---- The actual LangChain integration would look like: ----
    #
    # from langchain_google_genai import ChatGoogleGenerativeAI
    # llm = ChatGoogleGenerativeAI(
    #     model=req.model or _credentials["model"],
    #     google_api_key=_credentials["api_key"],   # <- from OpenBao
    # )
    # return {"answer": llm.invoke(req.prompt).content}

    return {
        "model": req.model or _credentials.get("model"),
        "answer": (
            "The Gemini key was retrieved from OpenBao and is present in memory. "
            "The real LangChain call is intentionally stubbed in the lab."
        ),
        "key_prefix": _credentials["api_key"][:6] + "...",
    }
```

The integration point is one line:

```python
llm = ChatGoogleGenerativeAI(
    model=req.model or _credentials["model"],
    google_api_key=_credentials["api_key"],   # <- from OpenBao
)
```

**Why an explicit `google_api_key=` and not the ambient environment.**
LangChain's `ChatGoogleGenerativeAI` will happily pick up
`GOOGLE_API_KEY` from `os.environ` if you do not pass the parameter. That
is the trap: you would build the LLM object without a key, LangChain would
find the old `GOOGLE_API_KEY` in the environment, and the app would appear
to work — while actually using the credential you were trying to retire.
**Always pass the key explicitly.** Passing it explicitly means the only
source of truth is the variable you assigned from OpenBao.

**Where to build the `ChatGoogleGenerativeAI` object.** Not inside the
request handler. The handler builds a *new* LLM client on every request,
which means new HTTP connection pools, new token handling, and new
objects to garbage-collect, on every single call. Build it once — in the
lifespan, right after the credentials are fetched — and reuse it.

```python
# in lifespan(), after get_gemini_credentials() succeeds
llm = ChatGoogleGenerativeAI(
    model=_credentials["model"],
    google_api_key=_credentials["api_key"],
)
```

**Why the model name comes from OpenBao too.** `_credentials["model"]` is
`"gemini-2.0-flash"`, stored in KV. That means you can move the fleet
from `gemini-2.0-flash` to `gemini-2.5-pro` by writing a new KV version
and restarting the pods — no code change, no image rebuild, no deploy
pipeline. Configuration that changes often belongs in the secret store
next to the credential, not in the code.

**`key_prefix` on line 127.** The response includes the first six
characters of the key and three dots. This is the *only* way the key
appears in an HTTP response, and it is a deliberate leak of exactly six
characters — enough to confirm which key is loaded, not enough to use it.
Do not copy this pattern for anything more sensitive than a
confirmation prefix.

> **Trade-off:** *The lab stubs the LangChain call so the course runs
> without spending Gemini quota. In production this handler is where
> your token accounting, rate limiting, and prompt logging live. Be aware
> that LangChain and the underlying SDK can log request payloads, and
> prompts may contain PII. That is a separate audit from secret
> management, and Module 09 covers it.*

---

## 6. The Dockerfile

```dockerfile
# lab/app/Dockerfile
FROM python:3.12-slim AS base

# --- Non-root user ----------------------------------------------------------
# Running as root inside a container is a needless privilege escalation.
RUN groupadd --gid 1000 meridian \
 && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin meridian

WORKDIR /app

# --- Dependencies ------------------------------------------------------------
# Copy the manifest first so the layer caches independently of source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application -------------------------------------------------------------
COPY openbao_client.py main.py ./

# --- Security posture --------------------------------------------------------
# 1. No build tools in the final image.
# 2. Run as non-root.
# 3. No secrets in build args, layers, or environment.
USER meridian

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
```

### 6.1 Non-root

`USER meridian` on line 28. The process runs as uid 1000, not uid 0.

**Why it matters here specifically.** A container escape — a malicious
dependency, a deserialisation bug, anything that gets you code execution
inside the container — should not hand you root. With `USER meridian`, the
attacker gets an unprivileged user. It also means the app's own process
**cannot read** the OpenBao data directory or any other root-owned
resource, so a compromise cannot pivot to the secret store's storage.

**The `/usr/sbin/nologin` shell** means the user cannot log in
interactively. It is not a security boundary on its own, but it removes an
accidental path.

### 6.2 Layer caching: `COPY requirements.txt .` comes first

`requirements.txt` is copied and installed in its own layer, **before**
the application source. Because Docker caches layers, editing `main.py`
rebuilds only the last layer. Editing `requirements.txt` rebuilds the
dependency layer. This is a build-hygiene point, not a security point,
but it is in the file for a reason and beginners routinely get it wrong
by copying the whole app first.

### 6.3 `--no-cache-dir`

`pip install --no-cache-dir` stops pip writing a wheel cache into the
image layer. Without it, the image carries a duplicate copy of every
dependency (bigger images, more CVEs to scan, and occasionally cached
metadata you did not intend to publish). It also avoids a subtle problem:
pip's HTTP cache can contain URLs and headers from a private index.

### 6.4 Pinned dependencies

```text
# lab/app/requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
httpx==0.28.1
```

**Exact pins, no `>=`.** `fastapi>=0.100` means your build today and your
build next quarter are *different code*. A dependency release that
introduces a breaking change or a CVE becomes an emergency at 02:00
because nobody controlled when it landed. With `==`, the upgrade is a
deliberate commit that a human reviews.

**Note what is NOT in that file:** `requests`, `httpx` (except for
TestClient), `hvac`, `boto3`. The comment in the file says it:

> NOTE: the OpenBao client (openbao_client.py) deliberately depends on
> NOTHING from this file - it is stdlib-only.

> **Production:** *Generate the pins with `pip-compile` (or `uv pip
> compile`) from a `requirements.in`, and commit **both** files. The `.in`
> file is the human intent; the compiled file is the exact, hashed
> dependency set. Add `--generate-hashes` so a compromised PyPI upload of
> the same version cannot slip in.*

### 6.5 No `ENV` and no `ARG` — and why `ARG` is *worse* than `ENV`

This is the section to read twice.

**`ARG` is a build-time variable. `ENV` is a runtime variable. Both are
baked into the image.** Neither is safe for a secret.

| | `ARG` | `ENV` |
|---|---|---|
| Visible in `docker history`? | **Yes** | Yes |
| Visible in `docker inspect` (the image)? | **Yes** | Yes |
| Visible to anyone who can pull the image? | **Yes** | Yes |
| Available at runtime in the container? | No | Yes |
| Available at *build* time? | Yes | Yes |

`ARG` is strictly worse, for two reasons:

1. **`ARG` values are recorded in the image's layer metadata and are
   visible in `docker history` output** — the same place build commands
   are visible. Anyone with read access to the image can see
   `ARG GEMINI_API_KEY=AIzaSy...` in the build log.

2. **`ARG` values persist in the layer.** If you use `ARG` in a `RUN`
   command, the value can be baked into that layer's filesystem. Even if
   you `unset` it later, the *earlier* layer still contains it. Docker
   layers are append-only; a later `RUN` cannot erase an earlier layer's
   bytes.

**The same is true of `ENV`**, and this is the point people miss. A
secret in `ENV` is:

- in `docker inspect` output — which lands in support tickets;
- in `docker history` if the `ENV` instruction is visible;
- in the exported environment of the process — visible in
  `/proc/<pid>/environ` for **every user who can read that file**, and
  readable by the container's own processes;
- in your CI system's build logs if the build prints `docker inspect`.

**The fix is not a better Dockerfile instruction. The fix is that the
secret never enters the build at all.** The app gets its credential at
runtime, from OpenBao, using a `role_id` (not secret) and a `secret_id`
(delivered by the mechanism in section 8).

> **Production:** *If you genuinely must pass something sensitive to a
> build, use BuildKit's `--mount=type=secret` — it mounts the value into
> one `RUN` command as a file and it never enters a layer:*
> ```dockerfile
> RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
>     npm ci --userconfig /root/.npmrc
> ```
> ```bash
> $ docker build --secret id=npmrc,src=$HOME/.npmrc .
> ```
> *Even then, prefer not to need it.*

### 6.6 No `.env` file copied in

**There is no `COPY .env .` in this Dockerfile.** Not because `.env` was
forgotten — because copying it in would be the *original sin* rebuilt.

A `.env` in the image is worse than a `.env` on a developer's laptop,
because the image is:

- pushed to a registry, where it may be pulled by anyone with read access;
- cached in every CI node and every build cache;
- present in every running replica, so one compromised replica leaks it;
- often still there long after the `.env` was "removed from Git".

And `.dockerignore` is the second line of defence:

```dockerignore
.env
.env.*
secrets/
*.pem
*.key
```

> ⚠️ **A missing `.dockerignore` is a silent secret leak.** If you have a
> `.env` in the build context and no `.dockerignore`, then even a
> Dockerfile that never mentions it may still ship it — `COPY . .` or
> `COPY .` patterns will include it. Always write a `.dockerignore` in
> the same commit that adds the first `.env`.

### 6.7 The healthcheck

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"
```

It uses Python's stdlib `urllib` rather than `curl` — no extra package
to install, no extra binary to keep patched, and it is guaranteed to be
present because the app itself needs Python.

**`--start-period=15s`** is the grace period during which a failing
healthcheck does not count. It covers the lifespan startup: the app must
log in to OpenBao and fetch the key before it can answer `/health`. Without
a start period, a slow OpenBao would cause every pod to be marked
unhealthy and restarted in a loop.

**`--retries=3`** at 30-second intervals means the container is declared
dead after roughly 90 seconds of failures. That is the right order of
magnitude: long enough to ride out an OpenBao hiccup, short enough that a
genuinely broken pod is replaced.

> **Production:** *Because `/health` reports `status: "degraded"` when
> OpenBao is sealed, a sealed OpenBao will make **every** harness container
> fail its healthcheck and be replaced in a storm — replacing a pod that
> cannot possibly boot, against a store that is sealed. Split the probes
> (section 5.2) and point the Docker `HEALTHCHECK` at the liveness
> endpoint, not the readiness one.*

---

## 7. Docker Compose: wiring it together

```yaml
# lab/docker-compose.yml (ai-harness service)
  ai-harness:
    build:
      context: ./app
      dockerfile: Dockerfile
    container_name: meridian-ai-harness
    environment:
      # NOTE: these are NOT set here on purpose. The app fetches the Gemini
      # key from OpenBao at startup using AppRole. See modules/07.
      BAO_ADDR: "http://openbao:8200"
      BAO_ROLE_ID: "${BAO_ROLE_ID:-}"
      BAO_SECRET_ID: "${BAO_SECRET_ID:-}"
      APP_LOG_LEVEL: "INFO"
    depends_on:
      openbao:
        condition: service_healthy
    networks:
      - meridian-net
```

### 7.1 `depends_on: service_healthy`

```yaml
    depends_on:
      openbao:
        condition: service_healthy
```

**Plain `depends_on` only waits for the container to start, not for it to
be usable.** OpenBao's container starts, then initialises, then waits for
unseal. A harness that starts in that window gets a connection refusal,
fails its lifespan, and crash-loops.

`condition: service_healthy` makes Compose wait for OpenBao's own
healthcheck to pass, which is this:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8200/v1/sys/health | grep -q '\"initialized\":true' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 10s
```

Note that this healthcheck checks `initialized`, not `sealed` — because a
sealed-but-initialised OpenBao will accept the login and give a real
permission error, which is a *better* failure than a connection refusal.

> ⚠️ **`depends_on` does not do health checking in older Compose
> versions.** The `condition: service_healthy` form requires Compose
> v2 (the `docker compose` subcommand). If you are on the legacy
> `docker-compose` v1, `depends_on` is a plain start-order list and you
> need a wait-for-it loop in your entrypoint instead. Check with
> `docker compose version`.

> **Production:** *In Kubernetes this becomes an `initContainer` that
> waits for OpenBao, or a `startupProbe` with a generous
> `failureThreshold`. Do not use `depends_on` as your only ordering
> mechanism — it is a start-order hint, not a readiness gate.*

### 7.2 `BAO_ROLE_ID` vs `BAO_SECRET_ID`

```yaml
      BAO_ROLE_ID: "${BAO_ROLE_ID:-}"
      BAO_SECRET_ID: "${BAO_SECRET_ID:-}"
```

Both are interpolated from the **host's** environment (or a `.env` file
next to the compose file) at `docker compose up` time. This is where the
delivery problem lives, and section 8 is entirely about it.

The important asymmetry:

| Variable | Secret? | In `docker inspect`? | Where it may live |
|---|---|---|---|
| `BAO_ROLE_ID` | **No** | Yes, harmlessly | Env var, Git, compose file |
| `BAO_SECRET_ID` | **Yes** | **Yes, and that is the problem** | A delivery channel, not a file |

`BAO_ROLE_ID` is a UUID naming a role. Putting it in the compose file
outright is fine:

```yaml
      BAO_ROLE_ID: "ab4852b3-d888-1ab9-4582-19e39ad3820d"
```

`BAO_SECRET_ID` cannot be. It has to come from somewhere, and everywhere
you put it, it lands in `docker inspect`.

> **Production:** *The `ai-harness` container's `docker inspect` output
> contains its full environment. That means a `secret_id` in an env var
> is a `secret_id` in your container metadata, which means it is a
> `secret_id` in your orchestrator's state store (etcd, Kubernetes
> Secrets, ECS task metadata), which means it is a `secret_id` in your
> cluster's backup. **This is the reason the "OpenBao app pattern" uses a
> push model instead of a pull model.** See section 8.*

---

## 8. Delivering the `secret_id`: three patterns

This is the hard part, and there is no free lunch. You must get a secret
into a container without it ending up in the container's metadata. Three
patterns are realistic, and each has a real cost.

### 8.1 Pattern A — the host `.env` file (the one that dies)

```bash
# lab/.env   <-- gitignored, 0600
BAO_ROLE_ID=ab4852b3-d888-1ab9-4582-19e39ad3820d
BAO_SECRET_ID=b5c80e34-a217-f52c-1ad8-e4923119bdf8
```

```yaml
# lab/docker-compose.yml
  ai-harness:
    environment:
      BAO_ADDR: "http://openbao:8200"
      BAO_ROLE_ID: "${BAO_ROLE_ID:-}"
      BAO_SECRET_ID: "${BAO_SECRET_ID:-}"
```

```bash
$ chmod 600 lab/.env
$ grep -qxF 'lab/.env' .gitignore || echo 'lab/.env' >> .gitignore
$ docker compose up -d ai-harness
```

**Why this pattern dies.** Not because of the `.gitignore` — because of
where the value ends up:

1. `docker compose` reads the `.env` file and injects the value into the
   container's environment. `docker inspect meridian-ai-harness` now
   contains `BAO_SECRET_ID=b5c80e34-...` in plain text, permanently, in
   the container's metadata.
2. The same value is in the container's `/proc/<pid>/environ`.
3. The same value is in the Docker daemon's state on disk.
4. Every `docker compose config` run prints it, in cleartext, to your
   terminal — and CI runs that command and logs the output.
5. If you later move to Kubernetes, the natural translation is a
   `Secret` object, which is base64, **not encrypted**, and is readable by
   anyone with `get secrets` in the namespace.

**The `.env` pattern is not *worse* than a hardcoded key in the repo —
it is the same pattern with extra steps.** It replaces one leak surface
with three.

> **Verdict:** *Acceptable for a **local lab**. Not acceptable in
> production, and not acceptable for anything you would have to explain to
> an auditor. The value of the pattern is that it teaches you the shape of
> the problem, not that it solves it.*

> **Production:** *If you use a `.env` locally, at minimum: `chmod 600`,
> gitignore it, and never run `docker compose config` in a CI job that
> logs its output.*

### 8.2 Pattern B — the push model: OpenBao delivers the credential

The idea: the container never receives a `secret_id` at all. Instead, the
deployment system asks OpenBao to create a **one-time credential** and
injects it directly into the container's environment at creation time, in
memory, in the orchestrator's control plane.

**The OpenBao side** — a "wrapping token" that carries the `secret_id`
in an encrypted, single-use envelope:

```bash
$ bao write -format=json -wrap-ttl=60s sys/wrapping/wrap \
    role_id="ab4852b3-d888-1ab9-4582-19e39ad3820d"
{
  "request_id": "",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": null,
  "warnings": null,
  "wrap_info": {
    "token": "s.7Kd2mQxR4nVbT9pLzYcHwA1sF3jG6uXe0NiOpQrStUv",
    "accessor": "v3Kq9XpL2mNbR7tYcWzA4sD6fH0jG1kL8iO5pQ",
    "ttl": 60,
    "creation_time": "2026-10-21T18:47:20.792819230Z",
    "creation_path": "sys/wrapping/wrap",
    "wrapped_accessor": ""
  }
}
```

> ⚠️ **Two CLI gotchas here, and both bite.**
>
> **1. There is no `-token` flag and no `-ttl` flag.** `bao write` has
> exactly one wrapping-related flag: **`-wrap-ttl`**, and it takes a
> duration. Anything else you invent silently becomes a *data key*:
>
> ```console
> $ bao write -format=json sys/wrapping/wrap -token="x" role_id="y" -ttl=60
> ...
> # the wrapping token's payload contains your flags as data:
> ["-token", "-ttl", "role_id"]
> ```
>
> That is not a harmless typo. The secret you meant to put in the
> envelope is now a payload field, and the TTL you asked for is 300
> seconds, not 60 — the server's default, because your `-ttl=60` never
> reached it.
>
> **2. `token=` IS a data field — but on a different command.** For
> `sys/wrapping/unwrap` you pass the token as data:
> `bao write sys/wrapping/unwrap token="s.xxx"`. For `sys/wrapping/wrap`
> the thing you are wrapping is whatever data fields you need — usually
> `role_id`. And for wrapping raw text it is `text=`, **not** `-text=`:
> the latter creates a payload key literally named `"-text"`.

The wrapping token is a single-use, 60-second-TTL, encrypted blob. Only
the process that unwraps it can read the `secret_id` inside.

**The container side** — an entrypoint that unwraps and then **erases**:

```bash
#!/bin/sh
set -eu

# The wrapping token arrives as a file, not an env var, so it never shows
# up in `docker inspect`'s Env array.
WRAP_TOKEN="$(cat /run/secrets/bao-wrap-token)"

# Unwrap -> the AppRole secret_id, single use, 60s TTL.
SECRET_ID="$(
  curl -s --header "X-Vault-Token: ${WRAP_TOKEN}" \
       --data '{"role_id":"ab4852b3-d888-1ab9-4582-19e39ad3820d"}' \
       http://openbao:8200/v1/auth/approle/secret-id \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["secret_id"])'
)"

# Overwrite the wrapping token file. It is single-use anyway, but the
# ciphertext on disk is worth one more second of life.
: > /run/secrets/bao-wrap-token
rm -f /run/secrets/bao-wrap-token

export BAO_ROLE_ID="ab4852b3-d888-1ab9-4582-19e39ad3820d"
export BAO_SECRET_ID="${SECRET_ID}"

exec uvicorn main:app --host 0.0.0.0 --port 8000
```

**Why this is better.** The `secret_id` never appears in the image, in
Git, in a `.env` file, or in a long-lived secret store. It exists as
plaintext for a few seconds inside one process's memory, and OpenBao
guarantees it can be used only once.

**Why it is still not perfect.** The `export` puts it in the
`/proc/<pid>/environ` of the uvicorn process, and it is in the Docker
daemon's metadata for the container's lifetime, because Docker stores the
container's env. You have moved the problem; you have not solved it.

> **Production:** *The push model is the right one for **short-lived
> workloads** — Kubernetes Jobs, CI runners, batch containers — where the
> container is destroyed within minutes. For long-running services,
> pattern C is better.*

### 8.3 Pattern C — the "let the app fetch it" model

The idea: **do not deliver the secret at all.** Deliver a *capability to
obtain* the secret.

The cleanest version of this is a **token with a short TTL, delivered by
the orchestrator's own secret mechanism**, combined with the app's
ability to re-authenticate. The cloud-native implementations of this are:

| Platform | Mechanism |
|---|---|
| Kubernetes | The **TokenRequest API**: a `serviceAccountToken` projected into the pod with a 1-hour audience-bound expiry. The app exchanges it for a cloud IAM role. |
| AWS | **IAM Roles for Service Accounts (IRSA)**: the pod's projected token is exchanged for temporary AWS credentials. |
| GCP | **Workload Identity Federation**: same shape, Google's implementation. |
| Azure | **Workload Identity**: same shape again. |
| OpenBao itself | **AppRole with `bind_secret_id=true` and a CIDR-bound `secret_id`**, or a JWT auth method (OIDC) that validates the orchestrator's projected token. |

The shape is always the same:

```
orchestrator projects a signed, short-lived, audience-bound token
        -> the app presents it to OpenBao
        -> OpenBao validates it (signature, audience, expiry)
        -> OpenBao returns a Vault token scoped to the app's policy
        -> the app reads the secret
```

**The `secret_id` is gone entirely.** There is no secret to deliver,
therefore no secret to leak. The only thing that exists is a *public
claim* ("I am the ai-harness pod in namespace meridian") plus a
*cryptographic proof* that the orchestrator vouched for that claim.

**This is where OpenBao's `jwt` or `oidc` auth method earns its keep.**
`bao plugin list` shows both are built in:

```bash
$ bao plugin list
Name                            Type        Version
----                            ----        -------
approle                         auth        v2.7.1+builtin.bao
cert                            auth        v2.7.1+builtin.bao
jwt                             auth        v2.7.1+builtin.bao
kubernetes                      auth        v2.7.1+builtin.bao
oidc                            auth        v2.7.1+builtin.bao
userpass                        auth        v2.7.1+builtin.bao
cassandra-database-plugin       database    v2.7.1+builtin.bao
influxdb-database-plugin        database    v2.7.1+builtin.bao
mysql-aurora-database-plugin    database    v2.7.1+builtin.bao
mysql-database-plugin           database    v2.7.1+builtin.bao
mysql-legacy-database-plugin    database    v2.7.1+builtin.bao
mysql-rds-database-plugin       database    v2.7.1+builtin.bao
postgresql-database-plugin      database    v2.7.1+builtin.bao
redis-database-plugin           database    v2.7.1+builtin.bao
valkey-database-plugin          database    v2.7.1+builtin.bao
kubernetes                      secret      v2.7.1+builtin.bao
kv                              secret      v2.7.1+builtin.bao
pki                             secret      v2.7.1+builtin.bao
rabbitmq                        secret      v2.7.1+builtin.bao
ssh                             secret      v2.7.1+builtin.bao
totp                            secret      v2.7.1+builtin.bao
transit                         secret      v2.7.1+builtin.bao
```

The `jwt` auth method validates a JWT **using a JWKS endpoint that
OpenBao fetches itself** — which is exactly the shape of a Kubernetes
ServiceAccount token (`iss`, `aud`, `exp`, `sub` all present). The
`kubernetes` auth method goes further and validates the token against
**the cluster's own TokenReview API**, so OpenBao does not need to be
configured with an issuer URL at all.

**The trade-offs are real:**

| | Pattern A (`.env`) | Pattern B (push/wrapping) | Pattern C (federated identity) |
|---|---|---|---|
| Secret in the image | No | No | No |
| Secret in `docker inspect` | **Yes** | Yes (in env) | **No** |
| Secret on disk | Yes (`.env`) | Briefly | **No** |
| Works offline / air-gapped | Yes | Yes | **No** — needs the orchestrator |
| Setup complexity | Trivial | Medium | **High** |
| Vendor/infra coupling | None | Low | **High** — ties you to one orchestrator |
| Works on a laptop | Yes | Yes | Awkward |
| Survives a credential leak | No | No | **Yes** — the token expires by itself |

> **Recommendation for Meridian AI:** *Pattern C for the production
> Kubernetes platform, using OpenBao's `jwt` auth method pointed at the
> cluster's OIDC issuer, with the `aud` claim bound to the harness. The
> `role_id` maps to the JWT's `sub` claim via `bound_claims`. This means
> there is no `secret_id` anywhere in the system — not in the pod, not in
> GitHub, not in a vault-of-vaults.*
>
> *Pattern A for the course lab, because a laptop has no service account
> token to project, and the point of the lab is to show the mechanics
> without a Kubernetes cluster in the picture.*
>
> *Pattern B for CI jobs, where the container is short-lived and the
> wrapping token's single-use property is a genuine benefit.*

### 8.3.1 The OpenBao side of Pattern C, runnable

The rows in the table above describe what *Kubernetes*, *AWS*, *GCP* and
*Azure* do. This section is the OpenBao half, and it runs on a laptop.

The idea: the orchestrator projects a **signed, short-lived token** into
the pod. The pod presents that token to OpenBao. OpenBao validates the
signature against a **JWKS endpoint it fetches itself**, checks the
claims against the role's `bound_claims`, and issues a normal scoped
OpenBao token. No `secret_id`, no `role_id` secret, nothing to leak.

The script below ships with this module at `lab/app/jwt_login_demo.py`.
It mints the same kind of RS256 token a cluster would project, serves
the public half as a JWKS document on localhost, and logs in. It needs
exactly one dev-only dependency, `cryptography`, because the standard
library cannot sign an RSA token — in production the *orchestrator*
signs it and your app never needs a signing key at all.

This is a captured run of that file against a live OpenBao 2.7.1:

```bash
$ export BAO_ADDR=http://127.0.0.1:8200
$ export BAO_TOKEN=s.xxxxxxxxxxxxxxxxxxxxxxxx   # a token that can write auth/
$ cd lab/app && python3 jwt_login_demo.py
$ bao auth disable jwt
Success! Disabled the auth method (if it existed) at: jwt/

$ bao auth enable jwt
Success! Enabled jwt auth method at: jwt/

$ bao write auth/jwt/config jwks_url=http://127.0.0.1:8099/.well-known/jwks.json jwt_supported_algs=RS256 role_type=jwt
Success! Data written to: auth/jwt/config

$ bao read -format=json auth/jwt/config
{
  "jwks_url": "http://127.0.0.1:8099/.well-known/jwks.json",
  "jwt_supported_algs": [
    "RS256"
  ],
  "status": "valid"
}

$ bao write auth/jwt/role/ai-harness-jwt role=ai-harness-service \
      user_claim=sub bound_claims='{"iss":"...","sub":"ai-harness"}' \
      bound_audiences=["openbao"] token_ttl=15m token_max_ttl=1h
Success! Data written to: auth/jwt/role/ai-harness-jwt

{
  "user_claim": "sub",
  "role_type": "jwt",
  "bound_claims": {
    "iss": "https://meridian-ai.svc.cluster.local",
    "sub": "ai-harness"
  },
  "bound_audiences": [
    "openbao"
  ],
  "token_ttl": 900,
  "token_max_ttl": 3600
}

### present the projected service-account token to OpenBao
client_token   = s.ppNjVuOpfDlVWb9JAC7BYYOD
lease_duration = 900
policies       = ['ai-harness-service', 'default']
metadata       = {"role": "ai-harness-jwt"}

### the token works, and it is scoped exactly like the AppRole token
GET /v1/ai/platform/data/llm/gemini -> 200
GET /v1/ai/platform/data/db/postgres -> 403

### the same token with a WRONG subject is refused
    refused, as it should be
```

Read the last three blocks as the whole point of the pattern:

* **The issued token is scoped exactly like the AppRole one.**
  `policies: ['ai-harness-service', 'default']`, the same 900-second
  TTL, the same read on `ai/platform/data/llm/gemini` (200) and the same
  refusal on `ai/platform/data/db/postgres` (403). Swapping the login
  method changes *how the app proves who it is*; it does not change
  *what the app is allowed to do*.
* **A token for the wrong subject is refused.** The `sub` claim is
  checked against the role's `bound_claims`, so a token minted for
  another workload cannot be replayed here. The server says
  `error validating claims: claim "sub" does not match any associated
  bound claim values`.
* **The `aud` claim is bound separately.** `bound_audiences` is a list
  in its own right — an `aud` claim in the token with no
  `bound_audiences` on the role is rejected with `audience claim found
  in JWT but no audiences bound to the role`. Binding the audience to
  OpenBao is what stops a token minted for *some other* service from
  being accepted here.

> **Production:** *point `jwks_url` at your cluster's OIDC issuer, set
> `jwt_supported_algs` to the algorithms that issuer actually uses, and
> bind `iss`, `sub` and `aud` to the one workload. Then the pod carries
> a token that the orchestrator already rotates for you, and there is
> nothing left for your deployment pipeline to keep secret.*

---

## 9. Rotation without a restart

Now the payoff. Here is a real rotation, observed live.

The app process reads the secret every few seconds. In the middle of the
loop, the secret is rewritten in OpenBao. The process never restarts.

```text
[t+00s] version=1 key=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr token=s.wLGRyFVM...
[t+03s] version=1 key=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr token=s.wLGRyFVM...
### ROTATING IN OPENBAO NOW ###
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T18:02:07.417730531Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            2
server version: 2
[t+06s] version=2 key=AIzaSyR4mZ8pL1qT6wN3vX9kD2bF7hJ5sC0eY token=s.wLGRyFVM...
[t+09s] version=2 key=AIzaSyR4mZ8pL1qT6wN3vX9kD2bF7hJ5sC0eY token=s.wLGRyFVM...
```

Read that output carefully. Three things happened and none of them
required a restart:

1. **The version changed from 1 to 2.** The app is reading a *new* KV
   version.
2. **The key value changed.** The new credential is in use.
3. **The token did NOT change** (`s.wLGRyFVM...` throughout). The app
   reused its cached token; it did not re-authenticate, because the token
   was still valid. Re-authentication and re-reading are independent
   concerns.

**The mechanism** is that the client does not cache the *secret*, only
the *token*. Every call to `read_secret()` is a fresh HTTP GET to
OpenBao. There is no local cache to invalidate, no config-map hash
annotation to update, no sidecar to restart.

### 9.1 What this buys you

| Without rotation-without-restart | With it |
|---|---|
| Rotate the key → edit a Secret/ConfigMap → rolling restart of every replica | Rotate the key → the next read picks it up |
| A 15-minute window where some pods have the old key and some have the new | One version, one key, everywhere |
| Deploy required, so rotation is coupled to release windows | Rotation is a routine, unattended operation |
| The old key is valid until every pod has restarted | The old key dies the moment OpenBao serves version 2 |

### 9.2 The KV version history is your rollback

```bash
$ bao kv metadata get ai/platform/llm/gemini
======== Metadata Path ========
ai/platform/metadata/llm/gemini

============ Metadata ============
Key                         Value
---                         -----
cas_required                false
created_time                2026-10-21T18:01:46.24156877Z
current_metadata_version    0
current_version             2
custom_metadata             <nil>
delete_version_after        0s
max_versions                0
metadata_cas_required       false
oldest_version              0
updated_time                2026-10-21T18:02:07.417730531Z

====== Version 1 ======
Key              Value
---              -----
created_time     2026-10-21T18:01:46.24156877Z
deletion_time    n/a
destroyed        false

====== Version 2 ======
Key              Value
---              -----
created_time     2026-10-21T18:02:07.417730531Z
deletion_time    n/a
destroyed        false
```

Both versions are readable. The client can even ask for a specific one:

```python
lease = client.read_secret_version("ai/platform", "llm/gemini", version=1)
```

which is what you reach for at 02:00 when a rotation broke something and
you need to know which key was live at 01:55.

> ⚠️ **KV v2 rollback creates a NEW version.** `bao kv rollback -version=1
> ai/platform/llm/gemini` does not make version 1 current again — it
> writes version 1's *content* as version 3. The audit trail stays honest:
> the rollback is itself recorded as a write. Do not expect
> `current_version` to go backwards.

> **Production:** *For the rotation bot, use CAS.* With
> `cas_required=true` on the mount, every write must present the version
> it expects to replace. Without CAS, two rotation bots racing each other
> can clobber one another's write, and you lose the audit trail of who
> changed what. Module 02 covers this in depth.*

---

## 10. Proving the secret is gone

Claims are cheap. Let us look.

Here is a real process that logged in to OpenBao, read the key, and then
sat there holding it in memory. Let us go and look for it.

```text
SECRET IN MEMORY: AIzaSyR4mZ8pL1qT6wN3vX9kD2bF7hJ5sC0eY
PID: 503
```

### 10.1 The environment

```bash
$ tr '\0' '\n' < /proc/503/environ | grep -c "AIzaSy"
0
```

Zero. The secret is not in the process's environment. Let us see what
*is* there:

```text
BAO_ROLE_ID=ab4852b3-d88...
BAO_ADDR=http://127.0.0...
BAO_SECRET_ID=b5c80e34-a21...
```

> **Read that output honestly.** `BAO_TOKEN` and `BAO_BIN` may appear in
> a transcript like this one because the *operator*'s shell had a root
> token exported so they could run `bao` commands — the demo process
> inherited them. A real `ai-harness` container has exactly three
> variables: `BAO_ADDR`, `BAO_ROLE_ID`, `BAO_SECRET_ID` — and **not one
> of them contains the Gemini key**. That is the whole point. The key
> appears nowhere on that list.
>
> Also note: `BAO_SECRET_ID` *is* in the environment. That is pattern A's
> weakness, and section 8 explains the two patterns that fix it.

### 10.2 The command line

```bash
$ tr '\0' ' ' < /proc/503/cmdline
python3 bao_rotation_demo.py
```

No key. This matters because command lines show up in `ps aux`, in
`top`, in process-monitoring dashboards, and — in a crash dump — in
`/var/log/` files. A key on the command line is a key in the world.

### 10.3 The file descriptors

```bash
$ ls -l /proc/503/fd
total 0
lr-x------ 1 root root 64 Oct 21 18:02 0 -> /dev/null
lrwx------ 1 root root 64 Oct 21 18:02 1 -> socket:[76733]
lrwx------ 1 root root 64 Oct 21 18:02 2 -> socket:[76735]
```

Three descriptors: stdin from `/dev/null`, stdout and stderr to sockets
(the harness capture pipes). **No regular files.** The secret was never
written anywhere, so there is no file descriptor pointing at it. If the
client had cached the secret to a file under the app's working
directory, you would see a fourth line here with a real path.

### 10.4 The filesystem

```bash
$ grep -rl "AIzaSyR4mZ8pL1qT6wN3vX9kD2bF7hJ5sC0eY" /tmp /etc /root /home
(no output)
```

Nothing. Not in `/tmp`, not in `/etc`, not in the home directory, not in
a config file. Compare that with a `.env`-based app, where the same grep
finds:

```bash
$ grep -rl "AIzaSyR4mZ8pL1qT6wN3vX9kD2bF7hJ5sC0eY" /app
/app/.env
```

### 10.5 The OpenBao side — what the audit log records

Here is the audit entry for the AppRole login, with `log_raw = "false"`
(so values are HMAC'd):

```text
"path": "auth/approle/login",
"data": {
    "role_id": "hmac-sha256:e6e99696b551f461499cbbf23b2dae6075cca02c4f7cba6fa7690c7b41ca0b56",
    "secret_id": "hmac-sha256:f2b077b8031c9be3c14d251a04b2ea6180bbc813fce9ac3e05b8b18c10d9f5c8"
}
```

The `role_id` and `secret_id` are HMAC'd, so an attacker with the audit
log cannot recover the real `secret_id` — but they *can* correlate
requests by their HMAC. That is the intended property: the log tells you
**that** a login happened and **which** credential was used, without
becoming a secret store itself.

> **Production:** *The audit log is the evidence trail for the whole
> system. It should be shipped somewhere the app's own credentials cannot
> write to, and it should be on a retention policy. Module 09 covers the
> audit device configuration in production form.*

---

## 11. The honest caveat: the key IS in memory

Everything above is true, and it is worth being precise about what it
does and does not buy you.

**The key is in the process's heap.** `lease.value["api_key"]` is a Python
`str` object. `_credentials["api_key"]` is another. So the key exists,
in RAM, in the app's address space, for as long as the app runs.

**What that means concretely:**

- Anyone with read access to the container's memory (a debugger, a
  core dump, `/proc/<pid>/mem` as root, a `gdb` attach) can read the key.
- A heap-dump crash handler uploaded to a bug tracker can leak it.
- A core dump written to disk by an OOM kill contains it.
- A memory-scraping attacker who achieves code execution gets it without
  ever touching the OpenBao API — which means they bypass the audit log.

**What it does NOT mean:**

- It does not mean the key is in the image, the repo, the compose file,
  the container environment, the orchestrator's etcd, or your CI logs.
- It does not mean a stolen `.env` gives an attacker the key.
- It does not mean a leaked registry pull gives an attacker the key.
- It does not mean the attacker's access to the container is undetected —
  OpenBao's audit log still records every read.

**So the honest framing is this:**

> Moving a secret from a file on disk to process memory moves it out of
> reach of every *passive* and *at-rest* attacker, and into reach of only
> an *active* attacker who already has code execution in the process. That
> is a genuine improvement — the set of attackers who can read a file is
> much larger than the set who can execute code in your process — but it
> is not the elimination of risk. It is the reduction of it.

**How to narrow the window further, if you need to:**

| Technique | Effect | Cost |
|---|---|---|
| Keep the key only as long as needed | Don't hold it in a module global; fetch per request | A round-trip per request |
| Use OpenBao's **dynamic secrets** (`database` engine) | The credential is a short-lived DB role, not a static password | A database plugin; the credential is still in memory while in use |
| Use **response wrapping** | The secret travels encrypted, single-use, with a short TTL | Extra steps in the client |
| Disable core dumps (`ulimit -c 0`) | A crash cannot write the heap to disk | None, essentially |
| `mlock` the pages | The key is not written to swap | Needs `CAP_IPC_LOCK` or a `ulimit -l` allowance |
| Zero the buffer after use | Reduces the window where a stale copy sits in freed memory | Language-specific, and only partially effective in Python |

> **Production:** *For Meridian AI, the recommendation is: keep the key in
> memory (unavoidable — the SDK needs it), set `ulimit -c 0` in the
> container so core dumps cannot capture it, and move the *database*
> credentials to OpenBao's `database` secret engine so the most valuable
> credential is short-lived and revocable. Module 08 covers the
> `database` engine.*

---

## 12. The Python client question: `hvc`, `hvac`, or stdlib?

### 12.0 First, the name trap

**The name you will hear most is `hvac` — and it is not an OpenBao
client either.** It is HashiCorp's client for *Vault*, and it works
against OpenBao because the HTTP API is compatible. But there is no
OpenBao-branded Python client, and the near-miss names on PyPI are worse
than "does not exist" — some of them install something entirely
unrelated.

This is not a hypothetical. Here is the docstring in the course's own
`lab/app/openbao_client.py` — the file this module has been reading
line by line since section 4:

```python
class OpenBaoClient:
    """Minimal, dependency-free OpenBao client for the Meridian AI harness.

    Deliberately built on urllib.request rather than hvac:
      - hvac pulls in a large dependency tree for what we need here.
      - Module 09 discusses when hvac's abstractions (HA retry, standby
        handling) are worth the dependency.
    """
```

`hvac` is the right name in that comment — and section 12.1 explains
exactly what it is, what it costs, and when it is the right call. But
before you run `pip install hvac`, read this next bit.

**`pip install hvc` does not install an OpenBao client.** Here is the
actual package that name resolves to on PyPI:

```text
$ curl -s https://pypi.org/pypi/hvc/json | python3 -c "import sys,json; d=json.load(sys.stdin)['info']; print(d['name'], d['version']); print(d['summary']); print(d['home_page']); print(d['requires_dist'])"
hvc 0.1.0
HVC is a Python library for Hyperdimensional Vector Computing
https://github.com/people-art/hvc
['torch (>=1.9.0)', 'scipy', 'pandas', 'numpy', 'requests', 'tqdm', 'openpyxl']
```

That is a **machine-learning library for hyperdimensional vector
computing**, published by `people-art`, with one release ever, which
pulls in PyTorch. It has nothing to do with OpenBao. If you followed a
tutorial that said `pip install hvc` and then `import hvc`, you would
either get an `ImportError` or, worse, a working import of the wrong
library and a very confusing afternoon.

> **Production:** *Pin the exact package you import. `pip install hvc`
> followed by `import hvac` is a bug that only shows up on someone
> else's machine.*

### 12.1 So what IS installable?

Here is the verified state of the Python-client landscape, checked
against PyPI and the OpenBao project itself.

| Artifact | Installable? | Verified how | What it actually is |
|---|---|---|---|
| `hvc` (PyPI) | **Yes — and it is the wrong thing** | `pypi.org/pypi/hvc/json` → 200 | "Hyperdimensional Vector Computing" (ML library, pulls torch) |
| `hvac` (PyPI) | **Yes** | `pypi.org/pypi/hvac/json` → 200, v2.4.0 | HashiCorp's Vault API client, `github.com/hvac/hvac`. **This is the real installable Python client.** |
| `openbao`, `openbao-client`, `openbao-python`, `openbao_client`, `pyopenbao`, `openbao-py`, `bao-client`, `openbao-hvc` | **No** | all `pypi.org/pypi/<name>/json` → **404**; `pypi.org/simple/openbao/` is **empty** | — |
| An official OpenBao Python client | **Does not exist** | `openbao.org/docs/2.6.x/api/libraries/` — "Official" lists **only Go** (`go get github.com/openbao/openbao/api/v2`); community list has only Swift | — |

That last row is the one to internalise. Here is the OpenBao project's
own Client Libraries page, reduced to its substantive text:

> The programming libraries listed on this page can be used to consume the
> API more conveniently. Some are officially maintained while others are
> provided by the community.
>
> **warning** Note: OpenBao intends to remain API compatible with
> HashiCorp Vault. This means that most of the existing libraries for
> Vault should also work with OpenBao.
>
> **Official** — These libraries are officially maintained by OpenBao.
> **Go** — OpenBao Go Client: `go get github.com/openbao/openbao/api/v2`
>
> **Community** — These libraries are maintained by the community.
> **Swift** — VaultCourier

**One official client library: Go.** No Python. And the guidance for
Python is in that warning box — use the Vault library, because OpenBao
is API-compatible with Vault.

> **If you find a tutorial saying "install the OpenBao Python client":**
> *it is describing a client that, as of OpenBao 2.7.1, is not published
> on PyPI. The honest options are `hvac` (installable, community/HashiCorp
> maintained, works against OpenBao) or your own stdlib client. This
> module uses the second.*

So the honest framing of this section is: **there is no OpenBao-branded
Python client** — not on PyPI under any name, and not in the OpenBao
GitHub organisation (25 public repositories, none of them a Python
client; `github.com/openbao/openbao-python` returns 404). The
OpenBao-maintained client is **not installable from PyPI under this
name**; the `hvc` name on PyPI belongs to an unrelated machine-learning
library. The real, installable Python artifact is `hvac` — HashiCorp's
client, which OpenBao's own documentation points Vault users at, because
the HTTP API is compatible.

### 12.2 What `hvac` gives you

`pip install hvac` (v2.4.0, `requires_python >=3.8,<4.0`) pulls in
exactly one runtime dependency:

```text
$ curl -s https://pypi.org/pypi/hvac/json | python3 -c "import sys,json; d=json.load(sys.stdin)['info']; print(d['requires_dist'])"
['pyhcl<0.5.0,>=0.4.4; extra == "parser"', 'requests<3.0.0,>=2.27.1']
```

So: `requests` (which brings `urllib3`, `certifi`, `idna`,
`charset-normalizer`). Plus optional `pyhcl` if you want HCL parsing.

Its documented feature set, from the `hvac` docs and source:

| Feature | What it does | When you need it |
|---|---|---|
| **Auth methods** | LDAP, AWS, Azure, GCP, JWT/OIDC, Kubernetes, AppRole, cert, token, userpass, and more | You use one of them |
| **Secret engines** | KV v1/v2, database, AWS/Azure/GCP, PKI, transit, and the rest | You read more than KV |
| **`is_authenticated()`** | Tells you whether the current token is still valid | Health checks |
| **TLS via `VAULT_CACERT` / `VAULT_CAPATH`** | Internal-CA support, verification on by default | Production with a private CA |
| **Pluggable `requests.Session`** | You can pass your own session with a tuned pool | High RPS |
| **HA / standby awareness** | Understands standby nodes, retries against the active one | OpenBao in HA mode |

### 12.3 What it costs — and the two defaults you must override

These are not opinions. They are lines in the `hvac` source, and they are
the reason a drop-in `hvac` client is not a drop-in for this module's
client without thought.

**First: it reads your token from the environment, and from a file on
disk.**

```python
# hvac/v1/__init__.py:113
token = token if token is not None else utils.get_token_from_env()
```

```python
# hvac/utils.py:359-368
"""Get the token from env var, VAULT_TOKEN. If not set, attempt to get the token from, ~/.vault-token
"""
    token_file_path = os.path.expanduser("~/.vault-token")
    if os.path.exists(token_file_path):
        with open(token_file_path) as f_in:
```

Two consequences, both of which hit this module's core property:

1. **`VAULT_TOKEN` in the environment is silently picked up.** That is
   the `.env` pattern this module exists to replace — and a client that
   reads it automatically makes it very easy to ship the old pattern by
   accident, because the code "works" either way. You would have to
   *actively* defeat it.
2. **If `VAULT_TOKEN` is unset, it reads `~/.vault-token` from disk.**
   A token written to a file on disk is exactly the "secret on disk"
   property this module says the app must not have. `hvac` does this by
   default because its primary user is a *human at a terminal* — which
   is a legitimate design for a CLI, and the wrong default for a
   containerised service.

**Second: it is a `VAULT_` client, not a `BAO_` client.**

```python
# hvac/v1/__init__.py:114
url = url if url else os.getenv("VAULT_ADDR", DEFAULT_URL)
```

```python
# hvac/v1/__init__.py:126-135
if verify is None:
    if VAULT_CAPATH:
        verify = VAULT_CAPATH
    if VAULT_CACERT:
        verify = VAULT_CACERT
    if not verify:
        # default to verifying certificates if the above aren't defined
        verify = True
```

`VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_CACERT`, `VAULT_CAPATH`,
`VAULT_NAMESPACE`, and the `X-Vault-Token` request header
(`hvac/adapters.py:346-347`). OpenBao accepts all of these — that is
the API compatibility guarantee quoted in §12.1 — and OpenBao *also*
accepts the `BAO_`-prefixed equivalents. So `hvac` works, but every
default it carries is the Vault-era spelling. In a container full of
`BAO_ADDR` variables, `hvac` will quietly look for `VAULT_ADDR` and not
find it, unless you pass `url=` explicitly.

> **Trade-off:** *`hvac` is a mature, well-tested client with a huge
> feature surface, and the correct choice the moment you need an auth
> method it implements, HA support, or a secret engine it wraps. The
> price is a `requests` dependency, `VAULT_`-era defaults, and two
> behaviours (env-var token discovery, `~/.vault-token` fallback) that
> you must actively disable in a production container.*

### 12.4 The decision

> | Your situation | Use |
> |---|---|
> | Single-node OpenBao, a handful of secrets, a service you control | **stdlib** — as in this module |
> | You need an auth method you would otherwise implement yourself (LDAP, AWS, GCP, OIDC) | **`hvac`** — writing a signing/identity flow is a bad idea |
> | OpenBao in **HA mode** (raft, multi-node) | **`hvac`** — standby handling and retry are the whole point |
> | You need connection pooling at high RPS | **`hvac`** — it takes a `requests.Session` |
> | You are writing a CLI for humans | **`hvac`** — its `~/.vault-token` behaviour is exactly right there |
> | You want a container with a tiny attack surface | **stdlib** |
>
> **Meridian AI's decision:** the harness talks to a **single** OpenBao
> node, reads **one** secret, at **startup and on rotation**. None of
> `hvac`'s advantages apply. The stdlib client is ~150 lines, has zero
> dependencies, and every line of it is readable by the one person on
> the team who has to audit it. When the platform moves to HA, or adds
> OIDC-federated identity, `hvac` becomes the right tool behind the same
> four methods — `login`, `read_secret`, `list_secrets`, `health` — and
> `OpenBaoClient` becomes an interface.

That last sentence is the real lesson: **the important decision was not
stdlib-vs-`hvac`, it was the shape of the interface between your app and
the secret store.** Keep that interface narrow and the question becomes
an implementation detail. If you are writing a *new* service today and
you know you will need OIDC or HA within a year, start with `hvac` — but
pass `token=None` explicitly, set `VAULT_TOKEN` to nothing, and make sure
`~/.vault-token` does not exist in your image.

> **Production:** *If you do use `hvac` in a container, add exactly two
> things to your Dockerfile or entrypoint:*
> ```dockerfile
> RUN rm -f /home/<user>/.vault-token
> ```
> ```bash
> # and make sure the service account's HOME is not a shared, writable volume
> ENV VAULT_TOKEN=""   # belt and braces: no ambient token
> ```
> *Better: use `hvac.Client(url=..., token=...)` with an explicit
> `token` argument so neither the env var nor the file is consulted.*

## 13. Testing

### 13.1 Unit-test the client with a mock

The point of the stdlib design is that the client is easy to test. There
is no session object to patch and no connection pool to fake — just one
method, `urllib.request.urlopen`.

The full test file ships alongside the client at
`lab/app/test_openbao_client.py` (a copy is in this module's `lab/app/`
directory too). It is standard-library `unittest`, so it needs no test
runner installed:

```bash
$ cd lab/app
$ python -m unittest test_openbao_client -v
test_403_is_wrapped_with_the_server_body (test_openbao_client.TestFailFast.test_403_is_wrapped_with_the_server_body)
The body is what tells the on-call engineer it is a POLICY ... ok
test_login_without_credentials_refuses (test_openbao_client.TestFailFast.test_login_without_credentials_refuses)
The client must refuse to run without a role_id and secret_id ... ok
test_missing_api_key_is_a_schema_error_not_a_403 (test_openbao_client.TestFailFast.test_missing_api_key_is_a_schema_error_not_a_403)
A secret that exists but has no api_key is a different fault from ... ok
test_network_failure_never_falls_back (test_openbao_client.TestFailFast.test_network_failure_never_falls_back)
There is no code path that returns a default secret. A silent ... ok
test_reading_a_secret_creates_no_files (test_openbao_client.TestNoDiskWrites.test_reading_a_secret_creates_no_files) ... ok
test_list_uses_the_metadata_path (test_openbao_client.TestPathConstruction.test_list_uses_the_metadata_path)
Listing reads the metadata layer, not the data layer. ... ok
test_read_secret_builds_the_kv_v2_data_path (test_openbao_client.TestPathConstruction.test_read_secret_builds_the_kv_v2_data_path)
The single most important assertion in this file. ... ok
test_read_secret_version_passes_version_as_a_query_param (test_openbao_client.TestPathConstruction.test_read_secret_version_passes_version_as_a_query_param)
A historical read is the same path plus ?version=N. ... ok
test_login_sends_an_empty_token_header (test_openbao_client.TestTokenLifecycle.test_login_sends_an_empty_token_header)
The login request must NOT carry a stale token. `_headers` uses ... ok
test_reauth_happens_at_eighty_percent_of_the_ttl (test_openbao_client.TestTokenLifecycle.test_reauth_happens_at_eighty_percent_of_the_ttl)
A 100-second token must be refreshed at 80 seconds, not 100. ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.010s

OK
```

Ten tests, no server, no credentials, ten milliseconds. Here is the one
that matters most:

```python
    def test_read_secret_builds_the_kv_v2_data_path(self):
        """The single most important assertion in this file.

        KV v2's HTTP API is <mount>/data/<key>. If this ever regresses to
        <mount>/<key>, every read returns 403 'permission denied' and the
        on-call engineer debugs the policy instead of the code.
        """
        client = OpenBaoClient(role_id="r", secret_id="s")
        body = {
            "data": {
                "data": {"api_key": GEMINI_KEY},
                "metadata": {"version": 3, "created_time": "2026-10-21T18:01:46Z"},
            }
        }
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            lease = client.read_secret("ai/platform", "llm/gemini")

        self.assertEqual(lease.version, 3)
        self.assertEqual(lease.value["api_key"], GEMINI_KEY)
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8200/v1/ai/platform/data/llm/gemini",
        )
```

It asserts the **exact URL**, including the `/data/` segment. A test that
only checked "it returns a dict" would have caught nothing; this one
would have caught the layout trap from section 4.4 the first time
somebody refactored `read_secret`.

Two more worth calling out:

```python
    def test_login_sends_an_empty_token_header(self):
        """The login request must NOT carry a stale token. `_headers` uses
        None for 'use my cached token' and '' for 'send an empty header'."""
        ...
        self.assertEqual(request.get_header("X-vault-token"), "")
```

This pins down the three-state `token` parameter (`None` vs `""` vs a
real token). It is the kind of detail that looks like a typo until you
re-authenticate after an expiry and send a dead token to the login
endpoint.

```python
    def test_reading_a_secret_creates_no_files(self):
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.fake"
        body = {
            "data": {
                "data": {"api_key": GEMINI_KEY},
                "metadata": {"version": 1},
            }
        }
        before = set(os.listdir(tempfile.gettempdir()))
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            client.read_secret("ai/platform", "llm/gemini")
        after = set(os.listdir(tempfile.gettempdir()))

        self.assertEqual(before, after)
```

The in-memory-only property, asserted rather than asserted-in-prose.
A "cache" is a natural thing for somebody to add to a client for
performance, and a cache file is a secret on disk. The test snapshots
the temp directory before and after a read and requires the two to be
identical.

### 13.2 The real integration test

A unit test proves the client builds the right request. It cannot prove
OpenBao accepts it. For that you need a live server — and this is where
`docker compose` earns its keep.

```bash
$ docker compose -f lab/docker-compose.yml up -d openbao
$ export BAO_ADDR=http://127.0.0.1:8200
$ export BAO_TOKEN=$(cat lab/secrets/root-token)
$ ./scripts/init-lab.sh
$ export BAO_ROLE_ID=$(cat lab/secrets/ai-harness-role-id)
$ export BAO_SECRET_ID=$(cat lab/secrets/ai-harness-secret-id)
```

The full integration test ships at `lab/app/test_integration.py`. It is
standard-library `unittest`, same as the unit test file — a learner should
not have to install a test runner to check the course works, and
`assertRaises` covers the *expected failure* case just as well as
`pytest.raises` does:

```python
class TestIntegration(unittest.TestCase):

    def test_the_harness_cannot_read_the_database_password(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client.read_secret("ai/platform", "db/postgres")
        self.assertIn("403", str(ctx.exception))

    def test_the_harness_cannot_list_the_llm_folder(self):
        """The policy grants `read` on one specific path, not `list` on the
        folder. Listing would let the service enumerate its neighbours."""
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client.list_secrets("ai/platform", "llm")
        self.assertIn("403", str(ctx.exception))

    def test_rotation_is_visible_without_a_restart(self):
        """Read the secret, rotate it out-of-band, read again. Same process,
        new value. This is the property that makes rotation cheap."""
        client = _client()
        first = client.read_secret("ai/platform", "llm/gemini")
        second = client.read_secret("ai/platform", "llm/gemini")
        self.assertGreaterEqual(first.version, 1)
        self.assertGreaterEqual(second.version, first.version)
        self.assertTrue(second.value["api_key"])

    def test_the_harness_cannot_write(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client._request("POST", "ai/platform/data/llm/gemini",
                            body={"api_key": "attacker-supplied"})
        self.assertIn("403", str(ctx.exception))
```

Run against the live server, this is the real output:

```bash
$ cd lab/app
$ export BAO_ADDR=http://127.0.0.1:8200
$ export BAO_ROLE_ID=$(cat ../secrets/ai-harness-role-id)
$ export BAO_SECRET_ID=$(cat ../secrets/ai-harness-secret-id)
$ python -m unittest test_integration -v
test_health_reports_seal_state (test_integration.TestIntegration.test_health_reports_seal_state) ... ok
test_reads_the_real_gemini_secret (test_integration.TestIntegration.test_reads_the_real_gemini_secret) ... ok
test_rotation_is_visible_without_a_restart (test_integration.TestIntegration.test_rotation_is_visible_without_a_restart)
Read the secret, rotate it out-of-band, read again. Same process, ... ok
test_the_harness_cannot_list_the_llm_folder (test_integration.TestIntegration.test_the_harness_cannot_list_the_llm_folder)
The policy grants `read` on one specific path, not `list` on the ... ok
test_the_harness_cannot_read_the_database_password (test_integration.TestIntegration.test_the_harness_cannot_read_the_database_password) ... ok
test_the_harness_cannot_write (test_integration.TestIntegration.test_the_harness_cannot_write) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.052s

OK
```

**Those last four are security regression tests, and they are written
backwards on purpose.** They assert that a *denial* still happens. If
someone "helpfully" widens the policy to make a debugging session
easier, these tests fail and the PR is blocked. If you only test the
happy path, a widened policy is invisible.

> **Production:** *Run the integration tests in CI against a throwaway
> OpenBao container, not against production. Use the
> `openbao/openbao:2.7.1` image with `-dev` for speed, or a real init
> cycle if you want the audit path exercised too. The point is that CI
> proves the app can still reach the store after every change to the
> policy, the role, and the client.*

### 13.3 What to test and what not to

| Test | Value |
|---|---|
| The exact URL the client builds | **High** — catches the `/data/` trap and path regressions |
| The error messages for missing credentials and 403 | **High** — these are what on-call reads at 3am |
| The 80% re-auth timing | **High** — a bug here is an outage, and it is easy to break |
| That the policy still denies `db/postgres` | **High** — a security regression test |
| That the client never writes a file | Medium — hard to assert, but a `tmp_path` check works |
| That the FastAPI app boots with no OpenBao | **High** — the refuse-to-boot rule |
| The exact wording of a log line | **Low** — brittle, low value |

---

## 14. The GUI for this module

Open <http://127.0.0.1:8200/ui> and sign in with your root token.

The top-level navigation in OpenBao 2.7.1 is **Secrets engines**, **Access**,
**Policies** and **Tools**. Inside **Access** the sub-navigation reads
**Authentication methods**, **Multi-factor authentication** and
**OIDC provider**; inside **Policies** it reads **ACL Policies**.

| What you want | GUI path | CLI equivalent |
|---|---|---|
| See the secret | **Secrets engines → KV (ai/platform) → llm → gemini** | `bao kv get ai/platform/llm/gemini` |
| See the version history | **Secrets engines → KV (ai/platform) → llm → gemini → *View version history*** | `bao kv metadata get ai/platform/llm/gemini` |
| See the AppRole auth method | **Access → Authentication methods → AppRole** | `bao read auth/approle/role/ai-harness-service` |
| See the role_id | **Not in the GUI — use the CLI** | `bao read -field=role_id auth/approle/role/ai-harness-service/role-id` |
| Generate a secret_id | **Not in the GUI — use the CLI** | `bao write -force auth/approle/role/ai-harness-service/secret-id` |
| See the policy | **Policies → ACL Policies → ai-harness-service** | `bao policy read ai-harness-service` |
| See the tokens issued | **Access → Authentication methods → AppRole → …** | `bao list auth/token/accessors` |
| See the health | **The seal-status indicator in the top bar** | `bao status` |

> **Two of those rows say "not in the GUI", and that is a finding, not a
> gap in my checking.** The OpenBao 2.7.1 UI bundle that the server
> actually serves contains **no AppRole role page at all**. There is no
> string `Role ID`, no `Generate Secret ID`, no `Secret ID`, no
> `role_id` and no `secret_id` anywhere in it — the AppRole support in
> the UI stops at the auth-method list entry and the "enable AppRole"
> wizard. If you are looking for a button that mints a `secret_id`, it
> is not there; `bao write -force auth/approle/role/<role>/secret-id`
> is the only way to get one, and that is fine — a `secret_id` is a
> credential, and a credential belongs in a tool that can print it to a
> pipe rather than a page that renders it into a DOM.

**How those labels were confirmed.** They were read out of the shipped
JavaScript bundle, not guessed:

```bash
$ curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
assets/chunk.475.0d3d12c9247a2b3e141f.js
assets/chunk.524.db8024bf66127c1bac18.js
assets/engine-vendor.js
assets/engine.js
assets/vendor.js
assets/vault.js
```

Download them and grep. The nav labels are literal strings in
`vault.js`; the version-history button is the literal string
**"View version history"** (not "Show version history" — that is the
wording in older Vault screenshots). The `AppRole` display name comes
from the UI's own method table: `{displayName: "AppRole", value:
"approle", …}`. I did not drive the GUI in this lab, because the lab is
a headless container with no browser, so the *labels* are quoted from
the bundle and the *page layout* is inferred from it.

**What the GUI does not expose, and why the CLI is primary here:**

- **The `role_id` and `secret_id`.** As above: there is no AppRole role
  page in the 2.7.1 UI. The `secret_id_accessor` list — your "revoke one
  credential" handle — is CLI-only for the same reason.
- **The exact API path** the client will request. The GUI shows you
  `ai/platform/llm/gemini`; the API wants `ai/platform/data/llm/gemini`.
  The GUI would never teach you the trap from section 4.4.
- **The raw JSON envelope.** The GUI pretty-prints away the double
  `.data` nesting that `SecretLease.from_response` has to unpack.
- **Whether the client would actually work.** The GUI authenticates as
  *you* (a root token). The harness authenticates as *the AppRole*. A
  secret you can see in the GUI is a secret your policy might not let
  the app read.

> **The last point is the real lesson about the GUI.** The GUI shows you
> what OpenBao *has*. The CLI shows you what OpenBao *allows*. Your
> application lives in the second world.

---

## 15. CLI gotchas from this module

Collected, because they will cost you an afternoon each if you meet them
cold.

| Gotcha | Wrong | Right |
|---|---|---|
| KV v2 path layout | `GET /v1/ai/platform/llm/gemini` | `GET /v1/ai/platform/data/llm/gemini` |
| JSON output flag | `-f=json` | `-format=json` |
| `token` on write | `bao write -token=... path` (flag not defined) | `bao write path token="..."` (data field) |
| Wrapping raw text | `-text="..."` | `text="..."` |
| Flags before positionals | `bao secrets tune ai/platform -default-lease-ttl=1h` | `bao secrets tune -default-lease-ttl=1h ai/platform` |
| Engine type is positional | `bao secrets enable kv-v2 -path=ai/platform` | `bao secrets enable -path=ai/platform kv-v2` |
| KV v1 vs v2 | `bao secrets enable -path=ai/x kv` (v1!) | `bao secrets enable -path=ai/x kv-v2` |
| KV v2 config | `bao write sys/mounts/ai/platform/tune cas_required=true` (silently does nothing) | `bao write ai/platform/config cas_required=true` |
| Version flags | `bao kv destroy -version=1` | `bao kv destroy -versions=1` (plural) |
| Read a specific version | `bao kv get -versions=1` | `bao kv get -version=1` (singular) |
| Policy linting | Needs a server | `bao policy fmt file.hcl` works with no server at all |

---

## 16. What you learned

- [ ] The five-step runtime flow: container start → AppRole login → KV read → in-memory only → serve.
- [ ] The difference between `role_id` (public, stable) and `secret_id` (secret, rotating), and the `secret_id_accessor` as a revocation handle.
- [ ] Why the client is **stdlib-only**: the secret-reading path is a trust boundary, and every dependency in it is supply-chain risk.
- [ ] The KV v2 API layout `<mount>/data/<key>`, and how a wrong path gives a **403 that lies** and sends you to debug the wrong thing.
- [ ] The double `.data` nesting in the KV v2 response envelope.
- [ ] Why `read` and `list` are different capabilities, and why the harness policy grants only `read` on one specific path.
- [ ] The 80%-of-TTL re-auth rule, and the headroom it buys.
- [ ] The no-fallback rule: a secret client either returns real data or raises, and the one exception (health) still returns the truth.
- [ ] The refuse-to-boot rule in the FastAPI lifespan, and why a crash loop beats a 200-OK-but-broken service.
- [ ] Why `/health` must report OpenBao's **seal state**, and why liveness and readiness must be separate endpoints.
- [ ] Why `google_api_key=` must be passed explicitly to `ChatGoogleGenerativeAI` instead of relying on the ambient environment.
- [ ] Why `ARG` is worse than `ENV` for secrets, and why neither is acceptable.
- [ ] The three `secret_id` delivery patterns and their real trade-offs — and why the `.env` pattern dies.
- [ ] The federated pattern (Pattern C): the orchestrator projects a signed token, OpenBao validates it against a JWKS endpoint, and the `sub`/`aud` claims are bound to one workload.
- [ ] How rotation works without a restart, and how KV's version history is your rollback.
- [ ] How to prove the secret is absent from the environment, the command line, the file descriptors, and the filesystem.
- [ ] The honest caveat: the key **is** in memory, and what that does and does not buy you.
- [ ] That `pip install hvc` installs an unrelated ML library, that `hvac` is the real installable Python client, and that OpenBao publishes **no** official Python client at all.

---

## 17. What's next

Module 08 opens the secret engines up: the `database` engine (short-lived
Postgres and Redis credentials that never sit in a file), the `transit`
engine (encryption as a service, so your application never holds a
decryption key), and `PKI` (issuing certificates from OpenBao instead of
your own CA). It is the natural next step because it takes the ideas here
— short-lived credentials, fetched at runtime, revocable — and applies
them to credentials you did not even know were passwords.

---

## 18. Homework

1. **Break the client on purpose and watch it fail correctly.**
   Set `BAO_SECRET_ID` to a wrong UUID and run the startup sequence.
   Capture the exact OpenBao error. Then set `BAO_ADDR` to a port with
   nothing on it and capture that error. Write down the two messages and
   the line in `openbao_client.py` that produced each. *Bonus:* add a
   `read_secret` for a path that does not exist and explain why the
   answer is a 403 and not a 404.

2. **Prove the `/data/` trap to a colleague who does not believe it.**
   With the harness's own token, issue both requests by hand:
   `GET /v1/ai/platform/llm/gemini` and `GET /v1/ai/platform/data/llm/gemini`.
   Issue them **twice** — once with the harness's AppRole token and once
   with the root token — because the four answers are *not* the same:

   ```console
   harness-token  ai/platform/llm/gemini         -> 403
   harness-token  ai/platform/data/llm/gemini    -> 200
   root-token     ai/platform/llm/gemini         -> 404
   root-token     ai/platform/data/llm/gemini    -> 200
   ```

   Explain all four, using `bao policy read ai-harness-service`. The two
   that surprise people are the **403 vs 404** split on the *same* path:
   the harness is *denied* (403, the path exists but the policy does not
   grant it) while root is *not found* (404, that path genuinely does not
   exist — KV v2 stores it under `data/`). A 403 means "wrong identity";
   a 404 means "wrong path". Then show `bao kv get ai/platform/llm/gemini`
   working from the CLI and explain why the CLI gets it right when the
   hand-rolled URL does not.

3. **Add a `list` capability, on purpose, and then take it back.**
   Add `list` to `ai/platform/metadata/llm` in the policy, confirm
   `client.list_secrets("ai/platform", "llm")` now returns `["gemini"]`,
   then remove it and confirm the 403 comes back. Write down why the
   *default* (no `list`) is the correct answer for a service that already
   knows the exact path it wants.

4. **Measure the real blast radius of a leaked `secret_id`.**
   Mint a `secret_id`, use it to log in, then read
   `auth/approle/role/ai-harness-service` and work out how long the
   resulting token lives and what it can do. Then check
   `bao list auth/token/accessors` and revoke the accessor. Repeat the
   login with the *same* `secret_id` and explain the result.

5. **Ship the app for real and inspect it.**
   Put the `secret_id` in a gitignored `lab/.env`, run
   `docker compose up -d ai-harness`, and then run
   `docker inspect meridian-ai-harness | grep -A2 BAO_SECRET_ID` and
   `docker exec meridian-ai-harness cat /proc/1/environ`. Decide, with
   evidence, whether pattern A is acceptable for production — and write
   the one-paragraph argument you would make to your manager.

6. **Design the CI/CD delivery.** Your CI system must give the build a
   `secret_id` that expires in 60 minutes, that never lands in the build
   log, and that is not stored in your CI provider's secret store as
   plain text. Choose between pattern B (push) and pattern C
   (federated identity), write the concrete configuration for your
   platform, and list the three things that could still leak it.

---

**[← Module 06 — Crypto Tooling](../06-crypto-tooling/README.md)**
· **[Module 08 — Other Secret Engines →](../08-other-engines/README.md)**
