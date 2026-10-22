# Level 6 — High Availability & Production Architecture

> **Goal:** you can design, deploy, upgrade, back up, restore and monitor a
> production OpenBao cluster — and you know the failure modes before they happen.

---

## 6.1 The HA mental model

```
        ┌──────────────────────────────────────────────────────────┐
        │                    CLIENTS                               │
        │        (apps, CI, operators) — hit the LB / DNS           │
        └───────────────────────┬──────────────────────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │  LB / DNS / VIP     │
                     └──────────┬──────────┘
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
      ┌────────────┐    ┌────────────┐    ┌────────────┐
      │  NODE 1    │    │  NODE 2    │    │  NODE 3    │
      │   ACTIVE   │    │  standby   │    │  standby   │
      │  (leader)  │    │ (readable) │    │ (readable) │
      └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
            │                  │                  │
            └──────────────────┼──────────────────┘
                               │
                 ┌─────────────▼─────────────┐
                 │   Raft (integrated storage)│
                 │   or PostgreSQL            │
                 └─────────────────────────────┘
```

### The rules of HA in OpenBao

| Rule | Detail |
|---|---|
| **One active node** | Only the leader performs writes. All writes go through Raft consensus on disk. |
| **Standbys serve reads** | Since **2.5.0** (Raft) and **2.7.0** (PostgreSQL), standbys answer storage-read requests locally. Writes are forwarded to the active node. |
| **Reads are eventually consistent** | A write on the leader may not be visible on a standby for a moment. 2.7.0 added `X-Vault-Index` / `X-Vault-Inconsistent` headers to fix this on demand. |
| **Unsealed standbys only** | A sealed node cannot be a standby. |
| **Quorum is king** | Lose 2 of 3 voters and the cluster is down. |
| **Sealing is per-node** | With Shamir, each node needs its own threshold of shares. |
| **Failover is automatic** | If the active node dies, a standby is elected. Typically seconds. |

### Sizing

| Cluster size | Fault tolerance | Use when |
|---|---|---|
| 1 node | 0 (single point of failure) | Dev, or a non-critical internal tool |
| 3 nodes | 1 node | **The minimum for production.** |
| 5 nodes | 2 nodes | Serious production, larger blast radius tolerance |
| 7 nodes | 3 nodes | Rarely worth it — more IO, slower consensus |

> 💡 **Start with 3.** 5 nodes gives you one more failure tolerance but costs
> more IO and slower Raft commits. If you can only afford one production-grade
> cluster, 3 well-run nodes beat 5 poorly-tuned ones.

### Voter vs non-voter

Raft nodes are either **voters** (part of quorum) or **non-voters** (standby,
replicate but don't vote). You can add extra non-voters for read capacity
without affecting quorum.

```bash
bao operator raft autopilot state
```

```
Healthy:                      true
Failure Tolerance:            1
Leader:                       raft1
Voters:
   raft1
   raft2
   raft3
Non-Voters:
   raft4
```

---

## 6.2 The reference architecture: 5-node Raft in Docker Compose

This is a complete, runnable production-shaped cluster.

### Directory

```
openbao-ha/
├── docker-compose.yml
├── config/
│   ├── node1.hcl ... node5.hcl
├── certs/
├── init.sh
└── scripts/
```

### `config/node1.hcl` (nodes 2–5 differ only in `node_id` and `api_addr`)

```hcl
ui           = true
cluster_name = "openbao-prod"

api_addr     = "https://openbao-1:8200"
cluster_addr = "https://openbao-1:8201"

storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-1"

  # Production tuning
  performance_multiplier = 1     # highest performance; needs good network
  snapshot_threshold     = 8192
  snapshot_interval      = 120
  trailing_logs          = 10000

  # Auto-join: lets nodes find the leader without manual `raft join`
  retry_join {
    retry_join_initial_interval = "1s"
    retry_join_max_interval     = "30s"
    retry_join_max_attempts     = -1
  }
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
  # The cluster listener inherits this listener's TLS config, so enforce
  # node-to-node access to 8201 at the NETWORK layer (firewall), not with
  # client certs here — client certs would also apply to the API port.
  tls_disable_client_certs = false
}

# ⚠️ No `disable_mlock` in OpenBao 2.x (removed in 2.0.0). Harden swap
#    instead — see Level 5, §5.2.

telemetry {
  prometheus_retention_time = "30s"
  disable_hostname = false
  usage_gauge_period = "1m"
}

default_lease_ttl = "24h"
max_lease_ttl     = "168h"
```

> 💡 **2.6.0 added `auto_join` via DNS SRV records** (and 2.7.0 fixed
> `auto_join` breaking on providers that include ports in discovered
> addresses, GH-4113). With `retry_join` stanzas you can pre-declare all peers
> and let them join automatically.

### `docker-compose.yml`

```yaml
x-openbao-base: &openbao-base
  image: openbao/openbao:2.7.1
  command: server -config=/openbao/config/openbao.hcl
  volumes:
    - ./certs:/openbao/certs:ro
    - ./logs:/openbao/logs
  memswap_limit: 0
  security_opt:
    - no-new-privileges:true
  healthcheck:
    test: ["CMD-SHELL", "BAO_CACERT=/openbao/certs/ca.crt bao status >/dev/null 2>&1"]
    interval: 10s
    timeout: 5s
    retries: 12
  restart: unless-stopped
  networks: [openbao]

services:
  openbao-1:
    <<: *openbao-base
    container_name: openbao-1
    volumes:
      - ./certs:/openbao/certs:ro
      - ./logs:/openbao/logs
      - openbao-data-1:/openbao/data
    environment:
      BAO_RAFT_NODE_ID: openbao-1
      BAO_ADDR: https://openbao-1:8200
    depends_on: [openbao-2, openbao-3, openbao-4, openbao-5]

  openbao-2:
    <<: *openbao-base
    container_name: openbao-2
    volumes:
      - ./certs:/openbao/certs:ro
      - ./logs:/openbao/logs
      - openbao-data-2:/openbao/data
    environment:
      BAO_RAFT_NODE_ID: openbao-2
      BAO_ADDR: https://openbao-2:8200

  openbao-3:
    <<: *openbao-base
    container_name: openbao-3
    volumes:
      - ./certs:/openbao/certs:ro
      - ./logs:/openbao/logs
      - openbao-data-3:/openbao/data
    environment:
      BAO_RAFT_NODE_ID: openbao-3
      BAO_ADDR: https://openbao-3:8200

  openbao-4:
    <<: *openbao-base
    container_name: openbao-4
    volumes:
      - ./certs:/openbao/certs:ro
      - ./logs:/openbao/logs
      - openbao-data-4:/openbao/data
    environment:
      BAO_RAFT_NODE_ID: openbao-4
      BAO_ADDR: https://openbao-4:8200

  openbao-5:
    <<: *openbao-base
    container_name: openbao-5
    volumes:
      - ./certs:/openbao/certs:ro
      - ./logs:/openbao/logs
      - openbao-data-5:/openbao/data
    environment:
      BAO_RAFT_NODE_ID: openbao-5
      BAO_ADDR: https://openbao-5:8200

networks:
  openbao:
    driver: bridge

volumes:
  openbao-data-1:
  openbao-data-2:
  openbao-data-3:
  openbao-data-4:
  openbao-data-5:
```

### Bootstrap sequence

```bash
# 1. Start the cluster (all nodes come up sealed & uninitialized)
docker compose up -d

# 2. Init ONE node — the storage backend is shared, so one init is enough
export BAO_ADDR=https://openbao-1:8200
export BAO_CACERT=./certs/ca.crt

bao operator init -key-shares=5 -key-threshold=3

# 3. Unseal node 1
bao operator unseal '<key1>'; bao operator unseal '<key2>'; bao operator unseal '<key3>'

# 4. Join the other nodes to the Raft cluster
for n in 2 3 4 5; do
  BAO_ADDR=https://openbao-$n:8200 bao operator raft join https://openbao-1:8200
done

# 5. Unseal each remaining node (each needs its own threshold!)
for n in 2 3 4 5; do
  for k in 1 2 3; do
    BAO_ADDR=https://openbao-$n:8200 bao operator unseal '<key>'
  done
done

# 6. Verify
bao operator raft list-peers
bao operator raft autopilot state
bao status
```

> ⚠️ **Raft membership is security-critical.** Anyone who can reach the cluster
> port and has a valid TLS client cert could try to join. That's why
> `tls_require_and_verify_client_cert = true` on the cluster listener matters
> — and why `cluster_addr` must be firewalled to node-to-node only.

### Verify

```bash
bao operator raft list-peers
```

```
Node              ID                 Address         State     Voter
openbao-1         openbao-1          openbao-1:8201  leader    true
openbao-2         openbao-2          openbao-2:8201  follower  true
openbao-3         openbao-3          openbao-3:8201  follower  true
```

```bash
bao status
```

```json
{
  "sealed": false,
  "initialized": true,
  "storage_type": "raft",
  "cluster_name": "openbao-prod",
  "cluster_id": "..."
}
```

### Removing a node

```bash
bao operator raft remove-peer openbao-5
```

Then stop the container and delete its data volume. **Always remove the peer
before destroying the node**, otherwise Raft keeps trying to contact a dead
member and wastes time on elections.

---

## 6.3 The PostgreSQL storage backend (the alternative)

### When to choose it

| Choose Raft when | Choose PostgreSQL when |
|---|---|
| You want a self-contained system | You already have a battle-tested Postgres with HA + backups |
| You want snapshot/restore built in | You want all your data in one backup/DR story |
| Fewer operational dependencies | You have Postgres expertise and monitoring |
| You don't want a distributed database | You want SQL-level inspection of the data |

### Config

```hcl
storage "postgresql" {
  connection_url = "postgres://openbao:CHANGE_ME@postgres-primary:5432/openbao?sslmode=verify-full"

  # HA mode
  ha_enabled = "true"
  ha_table   = "openbao_ha_locks"

  # 2.7.0: read scalability — REQUIRES physical replication
  # (cluster_addr must be reachable from standbys to the primary)

  table                 = "openbao_kv_store"
  skip_create_table     = "false"
  max_parallel          = "128"
  max_idle_connections  = 10
  max_connect_retries   = 5
}

cluster_addr = "https://openbao-1:8201"
api_addr     = "https://openbao-1:8200"
```

### Critical 2.7.0 caveat: physical replication only

> *"Only works with PostgreSQL physical replication; will not work with logical
> replication."*

That means:
* ✅ Streaming replication (native Postgres)
* ✅ Patroni / HAProxy / pgbouncer in front of a streaming-replica pair
* ❌ Logical replication (pglogical, postgres_fdw, logical decoding)
* ❌ Some managed "read replica" services that use logical replication

Verify before you design around it:

```sql
SELECT * FROM pg_stat_replication;
-- `replication_state = 'streaming'` on the replica = physical. Good.
```

### TLS to Postgres

```hcl
connection_url = "postgres://openbao:CHANGE_ME@postgres:5432/openbao?sslmode=verify-full&sslrootcert=/openbao/certs/pg-ca.crt"
```

> ⚠️ The plugin **attempts SSL by default**. If your Postgres doesn't have SSL
> enabled, you must explicitly set `sslmode=disable` — or better, turn on SSL
> and use `verify-full`.

### Manual table creation (for a least-privilege DB user)

```sql
CREATE TABLE openbao_kv_store (
  parent_path TEXT COLLATE "C" NOT NULL,
  key         TEXT COLLATE "C" NOT NULL,
  hashed_path TEXT COLLATE "C" NOT NULL,
  hashed_key  TEXT COLLATE "C" NOT NULL,
  value       BYTEA NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (parent_path, key)
);
CREATE INDEX openbao_kv_store_hashed_path ON openbao_kv_store (hashed_path);
CREATE INDEX openbao_kv_store_hashed_key  ON openbao_kv_store (hashed_key);

CREATE TABLE openbao_ha_locks (
  id           INTEGER NOT NULL PRIMARY KEY,
  network_addr TEXT,
  ha_enabled   BOOLEAN
);
```

Then set `skip_create_table = "true"` so the OpenBao DB user never needs DDL
rights.

---

## 6.4 Consistency — the 2.7.0 headers

### The problem

With standby reads enabled (default since 2.5.0), you can write to node A and
read from node B and **not** see your write. That's eventual consistency.

### The 2.7.0 solution

```bash
# 1. Write — the response includes X-Vault-Index
curl -sD- -X POST \
  -H "X-Vault-Token: $TOKEN" \
  -d '{"data":{"value":"x"}}' \
  https://openbao:8200/v1/secret/data/myapp | grep -i x-vault-index
# X-Vault-Index: 3f9a2c...

# 2. Read, demanding consistency
curl -s -X GET \
  -H "X-Vault-Token: $TOKEN" \
  -H "X-Vault-Index: 3f9a2c..." \
  -H "X-Vault-Inconsistent: forward-active-node" \
  https://openbao:8200/v1/secret/data/myapp
```

`X-Vault-Inconsistent` values:

| Value | Behaviour |
|---|---|
| `fail` | Respond **429 Too Many Requests** with `Retry-After` |
| `forward-active-node` | Forward the request to the active node |
| `await-state` | Hold the request locally until it catches up (optionally falling back to the above) |

### Listener defaults (2.7.0)

```hcl
listener "tcp" {
  # ...
  consistency_fallback_behavior      = "forward-active-node"
  consistency_missing_header_forward = false
  consistency_max_index_wait         = "30s"
}
```

> 💡 **When do you actually need this?** Read-after-write matters when a
> pipeline writes a secret and the app immediately reads it. For a
> write-once-at-deploy, read-many-later pattern, you don't need it. Use
> `await-state` sparingly — it holds connections and adds latency.

### Disabling standby reads

```hcl
disable_standby_reads = true
```

Every request then goes to the active node → **strong consistency, no read
scaling**. The right choice when correctness trumps throughput (rare), and the
**safe first setting** while you're still learning.

---

## 6.5 Snapshots, backup and restore

### Raft snapshots

```bash
# Save
bao operator raft snapshot save /backup/openbao-$(date +%F-%H%M).snap

# Inspect
bao operator raft snapshot inspect /backup/openbao-2026-10-20-1200.snap

# Restore (destroys current data!)
bao operator raft snapshot restore /backup/openbao-2026-10-20-1200.snap
```

> ⚠️ **Restore replaces the entire cluster state.** The cluster must be
> stopped/managed carefully, and this is a **destructive** operation. Practise
> it in a lab first.

### The restore runbook (the one you'll actually need)

```bash
# ═══ DISASTER RECOVERY: full cluster restore from snapshot ═══

# 1. STOP EVERYTHING. All nodes. No exceptions.
docker compose down

# 2. Preserve the evidence (if this is an incident)
cp -a openbao-data-1/ /incident-evidence/node1-$(date +%s)/

# 3. Wipe all data volumes
docker volume rm openbao-ha_openbao-data-{1,2,3,4,5}

# 4. Start ONE node only
docker compose up -d openbao-1

# 5. Restore the snapshot into that node
export BAO_ADDR=https://openbao-1:8200
export BAO_CACERT=./certs/ca.crt
bao operator raft snapshot restore /backup/openbao-2026-10-20-1200.snap

# 6. Unseal it
bao operator unseal '<key1>'; bao operator unseal '<key2>'; bao operator unseal '<key3>'

# 7. Bring up the rest and re-join them
docker compose up -d
for n in 2 3 4 5; do
  BAO_ADDR=https://openbao-$n:8200 bao operator raft join https://openbao-1:8200
done
for n in 2 3 4 5; do
  for k in 1 2 3; do BAO_ADDR=https://openbao-$n:8200 bao operator unseal '<key>'; done
done

# 8. VERIFY
bao operator raft list-peers
bao operator raft autopilot state
bao status
bao secrets list
bao policy list
```

> 🔴 **The unseal keys are the same across the cluster.** If you lost the
> unseal shares, a snapshot does **not** help — you need the recovery keys
> (auto-unseal) or the original unseal shares. And if you lost the KMS key
> that unseals the cluster, **the snapshot is useless**: the data is encrypted
> with a key that only the KMS-held root key can derive. This is the single
> most important sentence in this chapter.

### Backup strategy

```
Every hour:   Raft snapshot → /backup (local, then off-box)
Daily:         Snapshot → object storage (encrypted, versioned, immutable)
Quarterly:     FULL RESTORE DRILL into a scratch cluster  ← the important one
```

```bash
#!/usr/bin/env bash
# snapshot-backup.sh — run from cron
set -euo pipefail

STAMP=$(date -u +%Y%m%d-%H%M%S)
FILE="/backup/openbao-${STAMP}.snap"

export BAO_ADDR=https://openbao-1:8200
export BAO_CACERT=/openbao/certs/ca.crt

bao operator raft snapshot save "$FILE"
sha256sum "$FILE" > "$FILE.sha256"

# Ship off-box
aws s3 cp "$FILE" "s3://openbao-backups/raft/" --sse aws:kms \
  --sse-kms-key-id "$BACKUP_KMS_KEY" || \
rclone copy "$FILE" "remote:openbao-backups/raft/"

# Retention: keep 24 hourly, 14 daily, 12 monthly
find /backup -name 'openbao-*.snap' -mtime +14 -delete

echo "snapshot ok: $FILE"
```

> 💡 **A backup you have never restored is a hope, not a backup.** The quarterly
> drill is the single highest-value item on this page.

### Postgres backend backup

If you're on PostgreSQL, you back up Postgres — but you also need the **seal
material** and the **unseal/recovery keys** to make the data usable.

```bash
pg_dump -Fc -d openbao > openbao-$(date +%F).dump
```

Plus: snapshots of the *same* logical state, because `pg_dump` is
point-in-time-consistent but you still need a matching seal.

---

## 6.6 Upgrades

### The rolling upgrade procedure

```bash
# 1. Check the current state
bao status
bao operator raft autopilot state
bao operator raft snapshot save /backup/pre-upgrade-$(date +%F).snap

# 2. Read the release notes for EVERY version you're skipping.
#    2.5 → 2.6 → 2.7 each have changes.
#    https://openbao.org/community/release-notes/

# 3. Upgrade the STANDBY nodes first, one at a time.
#    (Never upgrade the active node first.)

# 4. For each standby: stop → change image tag → start → unseal → verify
docker compose stop openbao-2
# edit docker-compose.yml: openbao/openbao:2.7.0
docker compose up -d openbao-2
# unseal it, verify it's a healthy follower:
bao operator raft autopilot state

# 5. Step down the active node so the last-upgraded node becomes leader
bao operator step-down

# 6. Now upgrade the (new) active node
docker compose stop openbao-1
docker compose up -d openbao-1
# unseal

# 7. Verify the whole cluster
bao status
bao operator raft autopilot state
bao secrets list
bao policy list
```

### Cross-version compatibility

> ⚠️ 2.7.0 fixed a bug in **cross-version request forwarding during rolling
> upgrades to v2.6.x** (GH-3900). This is exactly the kind of thing that
> breaks a rolling upgrade.

**Rules:**
1. **Read every intermediate release note.** 2.5→2.6→2.7 is not one upgrade.
2. **Upgrade one minor version at a time.** Don't jump 2.4 → 2.7.
3. **Always snapshot first.**
4. **One node at a time.** Keep quorum.
5. **Unseal every node after restart.**
6. **Don't upgrade the leader first.**
7. **Have the previous image tag ready** for a fast rollback.

### Notable upgrade gotchas in 2.5 → 2.7

| Change | What you must do |
|---|---|
| `file` storage backend removed (2.7.0) | Migrate to `raft` or `postgresql` **before** upgrading |
| `pkcs11`/cloud seals removed from binary (2.7.0) | Install the KMS plugins **before** upgrading, or you're sealed out |
| Kerberos/LDAP/RADIUS auth removed (2.7.0) | Install the plugins **before** upgrading |
| `openbao-hsm` image discontinued (2.7.0) | Switch to the standard image + `kms-pkcs11` plugin |
| `sys/generate-root/attempt` deprecated (2.6.0) | `bao operator generate-root` already uses the new endpoint |
| `stored_shares` removed from `sys/init` (2.6.0) | Stop sending it |
| `build_date` → `commit_date` (2.6.0) | Update any scripts reading that field |
| `sys/health` lost `performance_standby`/`last_wal` (2.6.0) | Update monitoring checks |
| Container image labels changed (2.6.0) | Use OpenContainers labels, not the old ones |
| Container runs as `openbao` user (2.6.0) | Fix volume ownership |

> 💡 **Plugin-first upgrade rule:** if your config references a plugin that is
> no longer built in, install and register the plugin **before** you upgrade the
> binary. Otherwise the new node comes up and can't unseal.

---

## 6.7 Observability

### Metrics

```hcl
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname  = false
  usage_gauge_period = "1m"
}
```

```bash
curl -s --cacert certs/ca.crt https://openbao:8200/v1/sys/metrics | grep -E '^(vault|openbao)_' | head -40
```

Key metrics to alert on:

| Metric | Alert when |
|---|---|
| `vault.core.unsealed` | `== 0` on any node → **critical** |
| `vault.core.active` | `== 0` cluster-wide → no leader |
| `vault.raft.leader.lastContact` | rising → leader problems |
| `vault.expire.lease` | lease expiry rate spikes |
| `vault.core.fsm.pending` | rising → storage lag |
| `vault.raft.commit.lag` | rising → replication lag |
| `vault.token.count` | rising fast → token leak |
| `vault.secret.kv.*` (per mount) | unexpected growth |
| `vault.quota.*` | rate limit hits (an app is misbehaving) |

> 📌 2.7.0 added a dedicated metrics loop that reports `vault.core.unsealed=0`
> when OpenBao is sealed, so you get an accurate signal instead of a stale one.

### Health endpoint

```bash
curl -s --cacert certs/ca.crt https://openbao:8200/v1/sys/health | jq
```

```json
{
  "initialized": true,
  "sealed": false,
  "standby": false,
  "replication_performance_mode": "disabled",
  "replication_dr_mode": "disabled",
  "server_time_utc": 1792483433,
  "version": "2.7.1",
  "cluster_name": "vault-cluster-b075f70e",
  "cluster_id": "13c7cf87-0830-03ae-5aa0-5393b55b80bf"
}
```

> ⚠️ **Do not script against `performance_standby`, `last_wal` or `enterprise`**
> — those fields were **removed in 2.6.0**. The 2.7.1 response has
> `replication_performance_mode` and `replication_dr_mode` instead, and there
> is no `enterprise` field at all (OpenBao has no enterprise tier).

HTTP status codes: `200` = initialized, unsealed, active. `429` = standby.
`472` = DR secondary. `473` = performance standby. `501` = not initialized.
`503` = sealed.

### Audit log monitoring

```bash
# Denied requests in the last hour
jq 'select(.error != "" and (.time > (now-3600)|todate))' audit.log | \
  jq -r '.request.path' | sort | uniq -c | sort -rn

# Distinct source IPs reading secrets
jq -r 'select(.request.path | startswith("secret/data/")) | .request.remote_address' audit.log | sort -u

# Token creation rate
jq -r 'select(.request.operation=="update" and (.request.path|startswith("auth/token/create"))) | .time' audit.log | tail
```

### Logs

```bash
docker compose logs -f openbao-1
docker compose logs -f openbao-1 | grep -i "seal\|unseal\|election\|raft"
```

Set `BAO_LOG_LEVEL=info` (default). Use `debug` temporarily, `trace` only for
a specific incident (it prints request/response pairs — **including secrets**).

> ⚠️ **`TRACE` logs contain sensitive information.** The self-initialization
> docs say so explicitly. Never leave trace on.

---

## 6.8 Disaster recovery scenarios

| Scenario | Impact | Recovery |
|---|---|---|
| One node dies | None (if ≥3 voters) | Automatic failover. Restart the node, re-unseal, re-join. |
| Active node dies | Brief write pause | Automatic election (seconds). |
| Two of three voters lost | **Cluster down** | Restore from snapshot. |
| Disk corruption on one node | None | Replace the node's data volume, re-join. |
| All nodes lost | **Total outage** | Restore snapshot + unseal keys. |
| KMS key deleted | **Unrecoverable** | Even backups are useless. Prevent with IAM controls. |
| Unseal shares lost | **Unrecoverable** (Shamir) | Recovery keys (if auto-unseal) or restore + new init (data loss) |
| Audit disk full | **Cluster stops serving** | Free space immediately; add capacity. |
| Bad policy pushed | Some access broken | `bao policy write` the previous version (policies are versioned) |
| Malicious token minted | Blast radius | Revoke the token/ancestor, `lease revoke -prefix`, rotate |

### The "bad deploy" runbook

```bash
# 1. What changed?
bao audit list -detailed
git log --oneline -10        # your config repo

# 2. Roll back the policy
bao policy read app-readonly > /tmp/old-policy.hcl
git revert <commit> && bao policy write app-readonly - < /tmp/old-policy.hcl

# 3. Revoke the offending token
bao token revoke -accessor <accessor>
bao lease revoke -prefix secret/

# 4. Verify
bao token capabilities <token> secret/data/myapp
```

> 💡 **Policies are versioned.** `bao policy read` shows a `version` field, and
> each write increments it. Keep your policies in **git** and treat the repo as
> the source of truth — then rollback is a `git revert`.

---

## 6.9 Infrastructure as Code

### Declarative self-initialization (2.4.0+)

This closes the dangerous window between "initialized" and "configured" where a
root token exists and **nothing is audited**.

```hcl
# The audit device is declared with the `audit` stanza (see below) —
# in 2.7.1 you CANNOT create it via the API.
audit "file" "file" {
  description = "Local audit log (declarative)."
  options {
    file_path = "/openbao/logs/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}

# Self-initialization stanzas (2.4.0+) run on first start.
initialize "auth" {
  request "enable-oidc" {
    operation = "update"
    path      = "sys/auth/oidc"
    data = { type = "oidc", description = "Keycloak OIDC" }
  }

  request "enable-approle" {
    operation = "update"
    path      = "sys/auth/approle"
    data = { type = "approle", description = "Machine auth" }
  }
}

initialize "secrets" {
  request "enable-kv" {
    operation = "update"
    path      = "sys/mounts/secret"
    data = { type = "kv", options = { version = "2" } }
  }
}
```

> ⚠️ **In 2.7.1, do NOT create the audit device through self-initialization
> either** — the underlying API call is disabled by default, so the request
> would fail at runtime. Use the declarative `audit "file" "file" { ... }`
> stanza (shown above) for the audit device, and reserve `initialize` for auth
> methods, secret engines and policies.
>
> 📌 2.6.0 added **CEL support**, **`text/template` support**, a **`when`**
> conditional, custom **headers**, and self-init stanzas in **dev mode**.
> 2.6.0 also made self-initialization **error on unknown keys** instead of
> silently ignoring typos.

> ⚠️ **Self-initialization requires an auto-unseal mechanism** — it does not
> generate recovery keys, and the root token is **revoked after use** (it's
> never returned to you). Use the authenticated `/sys/rotate/recovery` endpoints
> to generate recovery keys afterwards.

> 💡 **Sensible split (from the OpenBao team's own advice):** keep
> self-initialization *minimal* — enable audit, enable one human OIDC path,
> one machine path, create one admin policy. Everything else belongs in
> OpenTofu/Terraform or a reviewed Git repo.

### The OpenTofu/Terraform approach (the right way at scale)

```hcl
# main.tf
resource "openbao_mount" "kv" {
  path = "secret/"
  type = "kv"
  options = { version = "2" }
}

resource "openbao_policy" "app_readonly" {
  name   = "app-readonly"
  policy = <<-EOT
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}
EOT
}

resource "openbao_approle_role" "myapp" {
  role_id        = "myapp"
  token_policies = ["app-readonly"]
  token_ttl      = 1200
  token_max_ttl  = 3600
}
```

Run it from CI with a **short-lived, least-privilege** token, not a root token.
Configure the provider with `BAO_TOKEN` from a **GitHub Actions OIDC** login
(Level 7).

---

## 6.10 Level 6 checkpoint

1. How many nodes do you need to tolerate 1 failure? 2 failures?
2. What happens to a write followed immediately by a read on a different node
   with standby reads enabled? How do you fix it in 2.7.0?
3. Why must `cluster_addr` be set when using the Raft backend?
4. What is the correct order for a full cluster restore from a snapshot?
5. Why is a snapshot useless if the KMS key is gone?
6. In a rolling upgrade, why do you upgrade standbys before the active node?
7. Which 2.7.0 removals would leave you unable to unseal if you didn't prepare?
8. What happens to the cluster if the audit log disk fills up?
9. Why does Postgres HA read-scaling require *physical* replication?
10. What does `bao operator raft remove-peer` prevent you from having to do by
    hand?

**Next → [Level 7: INTEGRATION-STACK.md](07-INTEGRATION-STACK.md)** — wiring
OpenBao into your actual stack: Keycloak, FastAPI, LangChain, PostgreSQL, Redis,
GitHub Actions.

---

## 6.11 Scratchpad

```
Raft:       storage "raft" { path, node_id, performance_multiplier=1 }
Join:       bao operator raft join https://openbao-1:8200
Peers:      bao operator raft list-peers
Autopilot:  bao operator raft autopilot state
Snapshot:   bao operator raft snapshot save|inspect|restore <file>
Step down:  bao operator step-down
Members:    bao operator members
Consistency: X-Vault-Index + X-Vault-Inconsistent: forward-active-node|await-state|fail
Postgres:   storage "postgresql" { connection_url, ha_enabled, ha_table }
```
