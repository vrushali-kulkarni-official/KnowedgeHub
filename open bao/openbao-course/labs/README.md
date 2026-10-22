# Labs

Three runnable Docker Compose labs that mirror the course chapters.

| Lab | What it is | Chapter |
|---|---|---|
| `lab01-dev-stack/` | One OpenBao node + Postgres + Redis. TLS, audit, KV v2, AppRole. | Level 2 |
| `lab02-ha-raft/` | 5-node Raft HA cluster, snapshot/restore, DR drill script. | Level 6 |
| `lab03-full-reference/` | OpenBao + Keycloak + Postgres + Redis + FastAPI + `bao agent` sidecar. | Level 7 |
| `lab04-ci-oidc/` | **Secrets-free CI.** GitHub Actions OIDC → OpenBao, with a local stand-in IdP so you can rehearse the whole flow offline. | Level 11 |

---

## Before you start

```bash
# 1. Get the CLI (a single static binary, no dependencies)
# Linux
wget -qO- https://github.com/openbao/openbao/releases/download/v2.7.1/openbao_2.7.1_linux_amd64.zip \
  | funzip > /usr/local/bin/bao && chmod +x /usr/local/bin/bao

# Windows (PowerShell)
winget install OpenBao.OpenBao

# macOS
brew install openbao/tap/openbao

bao version
# → OpenBao v2.7.1 (...)

# 2. You also need: jq, openssl, docker + docker compose
```

---

## Lab 01 — learning lab

```bash
cd labs/lab01-dev-stack

cp .env.example .env          # edit the passwords
./gen-certs.sh                # local CA + server cert
docker compose up -d
docker compose logs -f openbao
```

In another terminal:

```bash
export BAO_ADDR=https://127.0.0.1:8200
export BAO_CACERT=./certs/ca.crt

bao operator init -key-shares=3 -key-threshold=2
# copy the unseal keys and the root token, then:
bao operator unseal '<key1>'
bao operator unseal '<key2>'

./bootstrap.sh
```

Then explore:

```bash
bao status
bao secrets list
bao kv get secret/myapp
bao policy read app-readonly
bao audit list -detailed
tail -f logs/audit.log | jq .
```

**Break it on purpose:**

```bash
TOKEN=$(bao token create -policy=app-readonly -ttl=10m -field=token)
BAO_TOKEN=$TOKEN bao kv put secret/myapp hacked=yes     # 403
BAO_TOKEN=$TOKEN bao secrets list                        # 403
BAO_TOKEN=$TOKEN bao kv get secret/myapp                 # 200
```

Tear down:

```bash
docker compose down -v && rm -rf data/*
```

---

## Lab 02 — 5-node HA cluster

```bash
cd labs/lab02-ha-raft

./gen-certs.sh
docker compose up -d
./bootstrap-cluster.sh
```

Verify:

```bash
bao operator raft list-peers
bao operator raft autopilot state
bao status
```

**Failover test:**

```bash
# Kill the active node and watch a new leader appear
docker compose stop openbao-1
sleep 15
bao operator raft autopilot state    # new leader elected
docker compose start openbao-1
```

**Snapshot + DR drill:**

```bash
bao operator raft snapshot save ./backup-$(date +%F).snap
./dr-drill.sh ./backup-$(date +%F).snap
```

> ⚠️ The DR drill is **destructive** to the lab cluster. That is the point.

**Simpler alternative to the interactive DR drill** (non-interactive):

```bash
docker compose down
for v in $(docker volume ls -q | grep -E 'data[0-9]+$'); do docker volume rm "$v"; done
docker compose up -d openbao-1
bao operator raft snapshot restore ./backup-2026-10-20.snap
# unseal openbao-1 (3 keys)
docker compose up -d
for n in 2 3 4 5; do
  BAO_ADDR=https://openbao-$n:8200 bao operator raft join https://openbao-1:8200
done
```

---

## Lab 03 — full reference stack

```bash
cd labs/lab03-full-reference

cp .env.example .env      # fill in every password
./gen-certs.sh
docker compose up -d

export BAO_ADDR=https://127.0.0.1:8200
export BAO_CACERT=./certs/ca.crt
bao operator init -key-shares=3 -key-threshold=2
bao operator unseal '<key1>'; bao operator unseal '<key2>'

export KEYCLOAK_CLIENT_SECRET=<from .env>
export PG_ADMIN_PASSWORD=<from .env>
./bootstrap.sh
```

### Option A — app authenticates itself (AppRole)

```bash
export APPROLE_ROLE_ID=<from bootstrap output>
export APPROLE_SECRET_ID=<from bootstrap output>
docker compose up -d app
curl -s localhost:8000/config-check | jq
```

### Option B — `bao agent` sidecar

```bash
# put the role_id / secret_id into config/agent.hcl
docker compose up -d bao-agent app
curl -s localhost:8000/config-check | jq
```

### Human login via Keycloak

```bash
bao login -method=oidc -path=oidc -role=human
# → opens a browser → http://localhost:8080 → alice / alice-dev-password
bao token lookup | jq '.data.policies, .data.entity_id'
```

> ⚠️ The Keycloak realm's `sslRequired` is `none` for the lab. Set it to
> `external` (or `all`) in production.

---

## Lab 04 — secrets-free CI (the Level 11 lab)

```bash
cd labs/lab04-ci-oidc
docker compose up -d
./setup.sh          # init, unseal, configure the jwt mount + role
./simulate-ci.sh    # run the CI flow, show the audit trail, run a negative test
```

It runs the *same* step scripts the GitHub Action uses
(`ci/steps/01…04`), against a stand-in IdP that mints GitHub-shaped OIDC
tokens. The OpenBao side is **identical** to production — only the token
source differs.

**What you'll see at the end:**

```
  "policies": [ "ci-deploy", "default" ],
  "metadata": {
    "actor": "octocat",
    "environment": "production",
    "ref": "refs/heads/main",
    "repository": "your-org/your-repo",
    "role": "github",
    "run_id": "1792485478",
    "workflow": "deploy.yml"
  }

▸ Negative test — a token from the wrong repo must be refused
  ✅ correctly refused:
     error validating claims: claim "repository" does not match any
     associated bound claim values
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `permission denied` writing to `./data` | The 2.7.0 image runs as the `openbao` user (uid 100). `sudo chown -R 100:1000 data logs` |
| `mlock` warning in the logs | `memlock` ulimit too low, or `CAP_IPC_LOCK` missing |
| `connection refused` on 8200 | Container not started, or `api_addr`/`cluster_addr` mismatch |
| OIDC login loops | Redirect URI must match **exactly** on both sides |
| Keycloak groups missing from the token | The `groups` mapper must be on the client (see `keycloak/realm.json`) |
| `docker compose` version errors | Use Compose v2 (`docker compose`, not `docker-compose`) |
| `Upgrading from non-versioned to versioned data` on first `kv put` | A one-time format upgrade — retry after a couple of seconds (the lab scripts already do) |
| A script says "still SEALED" on a healthy server | jq's `//` treats `false` as empty. Use `jq -r 'if has("sealed") then (.sealed\|tostring) else "true" end'` |
| `bao status` in a `set -e` script aborts the script | `bao status` exits 2 when sealed/uninitialised — capture the JSON first, then parse it |

---

## A note on honesty

These labs were written against the **OpenBao 2.7.1 documentation and source
tree**, and the Compose files, HCL configs and shell scripts are syntactically
validated. They were **not** executed end-to-end in the authoring environment
(no Docker available there), so treat the first run as part of the exercise:
read the error messages, fix them, and learn something.

Every "expected output" in the course chapters is taken from the official
documentation or the `v2.7.1` changelog — not from my own runs.
