# Module 07 — App Integration: The Secret Reaches the App

> **Where we are.** We have a secret in OpenBao and an app that needs it.
> This module closes the loop — and proves the `.env` file is gone.

**Status: outline — full lesson in a later session.** The working
implementation already exists in `lab/app/`.

---

## 1. The flow

```
container start
   │
   ├─ 1. AppRole login ─────────► OpenBao (role_id + secret_id)
   │                              returns a 15-minute token
   │
   ├─ 2. Read KV v2 ────────────► ai/platform/data/llm/gemini
   │                              returns { api_key, model, ... }
   │
   └─ 3. Keep in memory only. Never write to disk. Never log it.
```

**The token expires in 15 minutes.** The client re-authenticates at 80% of
TTL and refreshes transparently. Long-running processes work with no
restart and no manual intervention.

---

## 2. The code (working, in `lab/app/openbao_client.py`)

Key design decisions, each with a reason:

**Stdlib-only HTTP.** The secret-fetching path sits inside the trust
boundary. Every dependency there is supply-chain risk, so it uses
`urllib.request` and has **zero** third-party dependencies. FastAPI and
LangChain live outside that boundary and can use whatever they like.

**No `httpx`/`hvc`.** `hvc` is the popular Python client, and it's a
reasonable choice when you need HA retry/standby handling. For a simple
AppRole + KV read it's a large dependency tree for two HTTP calls.
(Module 09 revisits this for HA.)

**Fail fast, never fall back.** If OpenBao is unreachable, the app raises.
It does *not* fall back to an env var or an empty key. A silent fallback
means your app starts "healthy" and then fails confusingly in production.

**The KV v2 path layout.** The API path is `<mount>/data/<key>`. Getting it
backwards (`<mount>/<key>/data`) produces a confusing **403 permission
denied** — because your policy grants `<mount>/data/<key>` and you asked
for a path that doesn't exist. This bit us during the build; it's a
classic.

---

## 3. Docker integration

`lab/docker-compose.yml`:

```yaml
ai-harness:
  build: ./app
  environment:
    BAO_ADDR: "http://openbao:8200"
    BAO_ROLE_ID: "${BAO_ROLE_ID}"      # not secret
    BAO_SECRET_ID: "${BAO_SECRET_ID}"  # secret, delivered at deploy time
  depends_on:
    openbao:
      condition: service_healthy
```

**`role_id` is not a secret.** It's an identifier. Bake it into the image.
**`secret_id` IS a secret** — it authenticates the workload, and it should
be delivered at deploy time (CI/CD secret injection, a mounted file, or a
short-lived bootstrap), never committed.

### The Dockerfile's discipline
- `USER meridian` — non-root
- No `ENV` with a secret
- No `ARG` with a secret (build args leak into image history)
- No `COPY .env`
- Healthcheck that doesn't log the key

---

## 4. The verification

```bash
# Inside the container:
$ docker exec -it meridian-ai-harness python -c "
from openbao_client import OpenBaoClient, get_gemini_credentials
c = OpenBaoClient(addr='http://openbao:8200')
c.login()
creds = get_gemini_credentials(c)
print('model   :', creds['model'])
print('project :', creds['project_id'])
print('api_key :', creds['api_key'][:10] + '...')
"
```

**Already verified working in the lab.** The full path — AppRole login →
KV v2 read → in-memory credential — executes correctly with no secret
material on disk.

---

## 5. Proving the secret is gone from the old places

```bash
# The old way
docker exec meridian-ai-harness env | grep -i gemini
# → nothing

docker exec meridian-ai-harness cat /proc/1/environ | tr '\0' '\n' | grep -i key
# → nothing

docker exec meridian-ai-harness ls -la /app
# → no .env file
```

**Note the honest caveat:** the key *is* in the container's memory, and
`/proc/<pid>/mem` of the right user could read it. That's why Module 09
covers `mlock`, disabling core dumps (`ulimit -c 0`), and why the
`read` capability should be scoped as narrowly as possible. No design
puts a secret in RAM and claims it can't be read.

---

## 6. Rotation without a restart

Because the client re-reads from OpenBao on every secret fetch:

```bash
# Rotate in OpenBao
bao kv put -cas=8 ai/platform/llm/gemini api_key="AIzaSyNEW..." ...
```

The next request picks up the new version. No restart, no redeploy, no
config push. **That is the entire point of the exercise.**

---

**Next:** [Module 08 — Other Engines](08-other-engines/)
