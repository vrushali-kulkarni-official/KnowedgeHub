# Level 5 — Production Security Standards

> **Goal:** this is the chapter that separates "a secrets manager running in
> production" from "a secrets manager that will get you fired". Every item here
> is a **top-level production grade security standard**, expressed as a decision
> with a reason and a command.

---

## 5.0 The baseline, at a glance

| # | Control | Why | Where |
|---|---|---|---|
| 5.1 | TLS everywhere | Credentials in plaintext on the wire | §5.1 |
| 5.2 | No/encrypted swap, no core dumps | Master key must not hit disk | §5.2 |
| 5.3 | Auto-unseal design | Removes humans from the boot path | §5.3 |
| 5.4 | Root token hygiene | Root can read everything | §5.4 |
| 5.5 | Audit strategy | You must prove what happened | §5.5 |
| 5.6 | Network exposure | Attack surface | §5.6 |
| 5.7 | Quotas + lockout | Blast radius of a runaway app | §5.7 |
| 5.8 | Policy hygiene | Least privilege | §5.8 |
| 5.9 | Secret lifecycle | Rotation, not eternal secrets | §5.9 |
| 5.10 | Supply chain | Plugins are code you run | §5.10 |
| 5.11 | Patch cadence | Real CVEs ship often | §5.11 |
| 5.12 | The checklist | Print it | §5.12 |

---

## 5.1 TLS everywhere — no exceptions

### Why

Every request carries `X-Vault-Token`. Over plaintext HTTP, that token is
readable by **anything on the network path**: a compromised switch, a rogue
container on the same bridge network, a passive tap. TLS is not optional.

### Server config

```hcl
listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  tls_cert_file = "/openbao/certs/openbao.crt"
  tls_key_file  = "/openbao/certs/openbao.key"

  tls_min_version = "tls12"
  # tls_max_version = "tls13"   # optional

  # 2.7.0: reload TLS material automatically when the files change
  # (no SIGHUP needed)
  tls_auto_reload = true
}
```

| Option | Notes |
|---|---|
| `tls_disable` | **Never** in production. Only for a loopback dev box. |
| `tls_min_version` | `"tls12"` minimum. `"tls13"` if all clients support it. |
| `tls_cert_file` / `tls_key_file` | PEM cert + key. |
| `tls_client_ca_file` + `tls_require_and_verify_client_cert` | mTLS for the *cluster* listener — strong. |
| `tls_auto_reload` | **2.7.0** — hot-reloads cert files on change. Great for Let's Encrypt / cert-manager. |
| `tls_key_exchange_preferences` | **2.7.0** — enforce post-quantum key exchange (`SecP256r1MLKEM768`, `SecP384r1MLKEM1024`, `X25519MLKEM768`, `MLKEM1024`). |

> 💡 **2.7.0 pure-PQC TLS.** You can now require post-quantum key exchange and
> even serve ML-DSA certificates. For a "harvest now, decrypt later" threat
> model, this matters. Note the `tls_key_exchange_preferences` option works on
> server, agent and proxy listeners.

### Client config

```bash
export BAO_ADDR=https://openbao.corp.internal:8200
export BAO_CACERT=/etc/ssl/certs/corp-internal-ca.crt
```

Or per-request: `curl --cacert /path/ca.crt https://openbao:8200/v1/sys/health`

### Python client

```python
client = hvac.Client(
    url="https://openbao.corp.internal:8200",
    verify="/etc/ssl/certs/corp-internal-ca.crt",   # CA bundle, NOT verify=False
    timeout=30,
)
```

> 🚫 **`verify=False` in production is a TLS-without-authentication failure
> mode.** It disables the check that the server is who it claims. In a lab, fine.
> In production, it means anyone who can redirect your traffic can read your
> tokens.

### Separate the public API from the cluster API

```hcl
listener "tcp" {
  address         = "0.0.0.0:8200"     # client API
  cluster_address = "0.0.0.0:8201"     # node-to-node cluster traffic

  tls_cert_file   = "/openbao/certs/openbao.crt"
  tls_key_file    = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
  tls_auto_reload  = true
}
```

> ⚠️ **The cluster listener inherits its parent listener's TLS settings.**
> There is no way to give `cluster_address` a *different* TLS configuration
> inside the same `listener` block, and declaring a second `listener "tcp"`
> block bound to the same cluster port collides on the bind.
>
> **Practical consequence:** you cannot have plain TLS on 8200 and mTLS on
> 8201 from a single listener block. Two ways to protect the cluster port:
>
> 1. **Network isolation (recommended):** firewall 8201 so only the other
>    OpenBao nodes can reach it. Combined with `cluster_addr` pointing at a
>    private interface, this is what actually stops a rogue container from
>    joining your Raft cluster.
> 2. **mTLS everywhere on that listener:** set
>    `tls_require_and_verify_client_cert = true` — but that then applies to
>    the API port on the same listener too, so every client needs a cert.
>    If you want both, terminate mTLS for 8201 with a proxy in front of it.
>
> Note: `tls_disable_client_certs` and `tls_require_and_verify_client_cert`
> are **mutually exclusive** — don't set both.

---

## 5.2 Swap, core dumps, and memory protection

### The problem

OpenBao holds the master key in memory. If it gets written to swap or a core
dump, a disk image of that machine = your entire secret store.

### ⚠️ OpenBao 2.x does NOT use mlock

`disable_mlock` was **removed in OpenBao 2.0.0** (the "mlock removal" RFC,
GH-363). The 2.7.1 server **refuses to start** if the option is present:

```
OpenBao has dropped support for mlock. Please remove the line "disable_mlock" = false
from your config and disable or encrypt swap instead.
```

So there is no `mlock()` call, no `CAP_IPC_LOCK`, and no `memlock` ulimit to
worry about. The hardening OpenBao asks for instead is **swap**.

### The controls

| Control | What it does | How |
|---|---|---|
| **No swap for the OpenBao process** | The master key can never be paged out | systemd `MemorySwapMax=0`, or cgroup v2 `memory.swap.max=0` |
| **Encrypted swap** (alternative) | A swap dump is unreadable | LUKS / `zswap` / `dmsetup` crypt |
| `kernel.core_pattern` | No core dumps | `kernel.core_pattern = \|/bin/false` |
| `NoNewPrivs` | Prevent privilege escalation | Docker `security_opt` |
| `read_only` rootfs | Prevent tampering | Docker `read_only: true` |
| `vm.swappiness=0` | Reduce swap pressure generally | sysctl |

### Linux (systemd)

The OpenBao systemd unit ships with swap already disabled for the process.
Verify:

```bash
systemctl cat openbao | grep MemorySwapMax
# MemorySwapMax=0        ← this is what you want
```

If you are not using systemd, set the cgroup v2 value instead:

```bash
# cgroup v2
echo "memory.swap.max=0" | sudo tee /etc/systemd/system/openbao.service.d/swap.conf
```

### Linux (host-wide, less precise)

```bash
# Disable swap entirely
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab
```

> ⚠️ The OpenBao docs note that disabling swap for the *whole OS* "is not
> recommended". Prefer the per-process approach.

### Docker

The OpenBao docs are explicit: **"When running the Docker image, include the
flag `--memory-swappiness=0`."**

```yaml
services:
  openbao:
    image: openbao/openbao:2.7.1
    # Equivalent of --memory-swappiness=0
    memswap_limit: 0
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
```

### BSD / macOS / Windows

```bash
# BSD: confirm swap is encrypted
# (FreeBSD, NetBSD, OpenBSD have guides linked in the OpenBao docs)

# macOS: swap is always encrypted — nothing to do

# Windows (PowerShell) — you said Windows 11
fsutil behavior query encryptpagingfile
# 0 = DISABLED  →  enable it:
fsutil behavior set encryptpagingfile 1
# then reboot
```

### Core dumps

```bash
echo "kernel.core_pattern=|/bin/false" | sudo tee /etc/sysctl.d/99-openbao.conf
sudo sysctl --system
```

### Container privileges (2.7.0 change)

> ⚠️ **2.7.0 container change:** the image now runs as the `openbao` user and
> **drops privileges automatically** before starting. If you rely on running as
> root, specify `user: root` explicitly. Also **all `VOLUME` instructions were
> removed** — you must declare your own volumes, and they must be writable by
> the `openbao` user (uid `100` / gid `1000` in the standard image).

---

## 5.3 Auto-unseal — designing the seal story

This is the single most consequential architectural decision you make.

### Option A — Shamir seal (default, no external dependency)

```
5 shares, threshold 3. 3 different humans must be present to boot the cluster.
```

| Pros | Cons |
|---|---|
| No external dependency at boot | Humans in the boot path |
| Nothing to keep alive besides OpenBao | Awkward for automated deployments |
| Strongest isolation from the platform | Slow disaster recovery (need 3 people) |

**The secret_id problem in CI/CD:** if you must automate unsealing, you're
storing unseal keys in a secret store — which is what you're trying to avoid.
OpenBao's own docs flag this as "the discouraged pattern of automating Shamir's
manual unseal" and point to **static key auto-unseal** instead.

### Option B — Transit seal (OpenBao unseals itself using another OpenBao)

```hcl
seal "transit" {
  address            = "https://bao-unseal.corp.internal:8200"
  disable_local_ca   = false
  ca_cert            = "/openbao/certs/unseal-ca.crt"
  tls_skip_verify    = false
  # The transit engine name that holds the key
  mount_path         = "transit"
  key_name           = "auto-unseal-key"
  # Recovery key configuration
  recovery_key_shares    = 5
  recovery_key_threshold = 3
}
```

The second cluster ("unseal cluster") holds the key that unseals the first.
It's a **deliberate, documented trust boundary**: whoever controls the unseal
cluster controls your main cluster.

| Pros | Cons |
|---|---|
| Fully automated unseal | Extra cluster to run and secure |
| No human in the boot path | Two-cluster failure mode |
| Transit can be backed by a KMS/HSM | More moving parts |

### Option C — Cloud KMS seal (2.7.0: **now a plugin**)

> ⚠️ **2.7.0 removed the built-in `awskms`, `gcpckms`, `azurekeyvault`,
> `alicloudkms`, `ocikms` and `pkcs11` seals from the binary.** They are now
> KMS plugins from `https://github.com/openbao/openbao-plugins`.

```hcl
# 1. Register the plugin
plugin "kms" "awskms" {
  # pulled from OCI, or installed locally
  # image = "ghcr.io/openbao/openbao-plugin-kms-awskms:<version>"
  # or:
  command = "openbao-plugin-kms-awskms"
}

# 2. Use it as a seal
seal "awskms" {
  region     = "eu-west-1"
  mount_path = "awskms/"
  key_name   = "my-openbao-unseal-key"
  # ... provider-specific options
}
```

**The AWS example in full** (from the 2.6+ model):

```hcl
plugin "kms" "awskms" {
  command = "openbao-plugin-kms-awskms"
}

seal "awskms" {
  region                      = "eu-west-1"
  mount_path                  = "awskms/"
  key_name                    = "prod-openbao-unseal"
  credential_type             = "iam"
  iam_role_arn                = "arn:aws:iam::123456789012:role/openbao-unseal"
  iam_endpoint                = "https://iam.eu-west-1.amazonaws.com"
  sts_endpoint                = "https://sts.eu-west-1.amazonaws.com"
  sts_region                  = "eu-west-1"
  rotation_period             = "720h"
  recovery_key_shares         = 5
  recovery_key_threshold      = 3
  recovery_key_pgp_keys       = "alice.asc,bob.asc,carol.asc,dave.asc,erin.asc"
  disable_automated_rotation  = false
  min_encryption_key_version  = 0
}
```

### Option D — Static key seal (for fully automated environments)

```hcl
seal "static" {
  secret_path = "/openbao/seals/unseal.key"   # 0600, on encrypted storage
  recovery_key_shares    = 5
  recovery_key_threshold = 3
}
```

> 🔴 The static key is a **single file whose loss = total loss**, and whose
> theft = total compromise. The docs explicitly say to use this only when you
> have "an automated alternative to Shamir's stored in Kubernetes secrets,
> OpenStack Barbican, or similar static secret stores". Use it as a
> **last resort**, protect it with disk encryption + strict permissions, and
> understand you have re-created the problem you're solving.

### Decision matrix

| Scenario | Recommended seal |
|---|---|
| Small team, manual ops, air-gapped-ish | **Shamir** (5/3) |
| Production K8s / Docker with automation | **Transit seal** (2-cluster) or **cloud KMS plugin** |
| Cloud-native, IAM already nailed down | **Cloud KMS plugin** (AWS/GCP/Azure) |
| HSM / compliance requirement | **PKCS#11 KMS plugin** (from `openbao-plugins`) |
| Fully automated, no external deps | **Static** (with heavy caveats) |

### The non-negotiable rules

1. **Never lose the KMS key.** The docs are blunt: *"If the seal mechanism or
   its keys are permanently deleted, then the OpenBao cluster cannot be
   recovered, **even from backups**."*
2. **Guard the KMS key with IAM/SCP-style controls** so a compromised OpenBao
   node can't delete the key that unseals it.
3. **Always generate recovery keys** and store them offline.
4. **Rehearse** the recovery path. An unrehearsed break-glass is a failed
   break-glass.
5. **Monitor seal health.** 2.6.0 added a periodic seal health check:

```hcl
seal "awskms" {
  # ...
  health_check_enabled        = true
  health_check_timeout        = "1m"
  health_check_interval       = "10m"
  health_check_interval_unhealthy = "1m"
}
```

> When the health check fails, OpenBao logs warnings — so you find out **before**
> you need to unseal.

### Seal migration

Migrating between seal types requires **downtime** and both mechanisms available
simultaneously. The procedure (from the docs):

1. Snapshot first.
2. Take a standby down, add the new `seal` block (or `disabled = "true"` on the
   old one), bring it back up, unseal with `-migrate`.
3. Repeat for each standby, one at a time (keeps quorum).
4. `bao operator step-down` the active node.
5. The new active node performs the migration — watch the logs.
6. Take down the old active node, update its config, bring it up.
7. Clean up the config files to have only the new seal block.

> ⚠️ **Known limitation:** migrating **from AWSKMS to AWSKMS** is currently not
> supported. All other same-type migrations are.

---

## 5.4 Root token hygiene

> *"In fact the OpenBao team recommends that root tokens are only used for just
> enough initial setup... and are revoked immediately after they are no longer
> needed."*

### The lifecycle of a root token

```
  1.  Init produces a root token         ← use ONCE
  2.  Use it to create: a real admin path (OIDC + break-glass policy)
  3.  Revoke the root token immediately  ← DO THIS
  4.  If you ever need root again:
      bao operator generate-root -init    ← requires a quorum of recovery keys
      ... use it, then revoke it again
```

```bash
# 3. Revoke it
bao token revoke <root-token>
bao token lookup | jq    # → confirms it's gone
```

### Creating a proper admin path instead

```bash
# A break-glass role with real (but non-root) power
bao policy write breakglass-admin - <<'EOF'
path "secret/data/*" {
  capabilities = ["create", "read", "update", "patch", "delete", "list", "scan"]
}
path "secret/metadata/*" {
  capabilities = ["read", "list"]
}
path "sys/mounts"  { capabilities = ["read", "list"] }
path "sys/auth"    { capabilities = ["read", "list"] }
path "sys/audit"   { capabilities = ["read", "list"] }
path "sys/policies/acl" { capabilities = ["list"] }
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/renew-self"  { capabilities = ["update"] }
EOF

# Bind it to an identity group reachable only via a protected path
bao write identity/group name=breakglass policies=breakglass-admin
```

> ⚠️ Note what `breakglass-admin` **cannot** do: create tokens, write policies,
> mount engines, use `sys/raw`. It manages *secrets*, not *the system*. That's a
> deliberate design choice: break-glass should not be a path to full compromise.

### Two-person rule with control groups (2.7.0)

Level 8 covers control groups in depth. The concept: even a break-glass secret
read requires a second approver. This is the strongest anti-insider control
OpenBao offers.

### Emergency root generation

```bash
# Requires a quorum of recovery keys
bao operator generate-root -init
# → asks for recovery key 1 of 5, 2 of 5, 3 of 5
# → prints a new root token

# Use it, then revoke it
bao token revoke <new-root-token>
```

> ✅ Since 2.6.0 this uses the **authenticated** `/sys/generate-root-token`
> endpoints. The old unauthenticated `/sys/generate-root/attempt` is deprecated
> and disabled by default.

### Never store root tokens

| ❌ Never | ✅ Instead |
|---|---|
| `export BAO_TOKEN=hvs.root...` in a long-lived shell | `bao login` + token helper |
| Root token in `.env` | `bao login` in the deploy pipeline, or AppRole |
| Root token in CI secrets | OIDC/JWT auth for CI (Level 7) |
| Root token in a shared vault | A break-glass policy + `generate-root` |

---

## 5.5 Audit strategy

### ⚠️ In 2.7.1, audit devices are created from the CONFIG, not the API

`bao audit enable` now fails by default:

```
cannot enable audit device via API; use declarative, config-based
audit device management instead
```

This is a **deliberate hardening change**: an operator (or a compromised admin
token) can no longer add or remove an audit device at runtime, so an attacker
cannot quietly disable your audit trail. The config file is the source of
truth, and the config is reviewed in git.

### The declarative audit device (2.4.0+)

The `audit` stanza takes **two labels** — the device *type* and the *mount
path* — and `options` is a **block** of **string** values:

```hcl
audit "file" "file" {
  description = "Local audit log (declarative)."
  options {
    file_path = "/openbao/logs/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}

audit "socket" "remote" {
  description = "Ship audit logs to the SIEM collector."
  options {
    address      = "tcp://audit-sink.internal:9023"
    socket_type  = "tcp"
    write_timeout = "2s"
  }
}
```

> ⚠️ `log_raw` is a **string** (`"false"`), not a boolean. `options` is a
> block, not an `=` map. Getting either wrong makes the server refuse to
> start with a cryptic parse error.

**Always validate before restarting:**

```bash
bao operator validate-config -config=/openbao/config/openbao.hcl
```

Audit devices defined this way are enabled on the active node at startup and
on `SIGHUP`. Removing the stanza removes the device — so **keep the
configuration identical across all nodes**.

### The escape hatch: `unsafe_allow_api_audit_creation`

If you genuinely need to add a device at runtime (an emergency second sink, a
test), set this server option — it can be toggled with `SIGHUP` without a
restart:

```hcl
unsafe_allow_api_audit_creation = true
```

```bash
bao audit enable -path=file file file_path=/var/log/openbao/audit.log mode=0600
# ...then set the option back to false and SIGHUP
```

The name is a warning. **Enable it, do the thing, turn it back off.**

A sibling option, `allow_audit_log_prefixing`, allows devices that use the
audit-log prefixing mode. Same discipline: temporary only.

### Why at least two devices

OpenBao considers a request successful if it can log to **at least one**
device. If all devices fail, **OpenBao refuses to serve requests**. That's
fail-closed and correct — but it means a single failed device is a single
point of failure, and a full disk on the audit sink takes the cluster down.
Two devices = redundancy + tamper-evidence (compare HMACs between two logs to
detect tampering).

### The rules

| Rule | Why |
|---|---|
| Define devices in the config | The API path is disabled by default in 2.7.1 |
| `log_raw = "false"` **always** | Otherwise secrets land in the audit log in plaintext |
| `mode = "0600"` | The audit log is a security artefact |
| Same config on every node | Otherwise devices drift between nodes |
| Ship off-box | An attacker with root on the box can edit the local log |
| Ship to immutable storage | Same reason — use WORM/SIEM |
| Monitor disk space | A full audit disk = a down cluster |
| Alert on audit failure | Detect the fail-closed condition before users do |
| Never enable `log_raw` "temporarily" | There is no temporary |

### Log shipping

```
openbao ──▶ local file (0600)     [declared in config]
        └──▶ socket ──▶ rsyslog/fluentbit ──▶ SIEM (Splunk/Elastic/Sentinel)
                                          └──▶ immutable/WORM bucket
```

### What to alert on

```
- denied requests (403) spiking        → credential stuffing or probing
- reads of secret/data/* by a new IP   → possible exfiltration
- login failures by user               → brute force
- token creation rate spike            → token minting abuse
- audit device failure                 → fail-closed imminent
- seal health check failure            → auto-unseal about to break
```

---

## 5.6 Network exposure

**The default posture should be: OpenBao is reachable from your application
networks and from nowhere else.**

| Port | Purpose | Expose to |
|---|---|---|
| 8200 | Client API | Application networks only |
| 8201 | Cluster API (Raft) | Only other OpenBao nodes |

### Controls

1. **Network policies / security groups** — 8201 open only to other nodes.
2. **mTLS on the cluster listener** — `tls_require_and_verify_client_cert`
   (note: it inherits the parent listener's TLS config, so it applies to the
   API port of that listener too — otherwise firewall 8201 to node-to-node).
3. **No public ingress.** Not even for the UI. Put the UI behind SSO + VPN.
4. **A reverse proxy / load balancer** in front for TLS termination only if
   you *also* keep TLS to the node (don't downgrade to plaintext behind the LB).
5. **Firewall the unauthenticated endpoints** if your platform can't do
   path-based filtering — a proxy that only allows `/v1/sys/health` and
   `/v1/auth/*` from the internet.

> ⚠️ `sys/health`, `sys/seal-status`, `sys/leader`, `sys/metrics` and
> `sys/pprof/*` may be reachable unauthenticated depending on listener config.
> `sys/metrics` leaks a lot of operational detail. `sys/pprof` is a
> profiling endpoint — **never** expose it publicly.

### Disable pprof explicitly

```hcl
# There is no explicit "disable"; it is off unless enabled.
# Just make sure the listener isn't exposed and consider:
# (no pprof_options stanza = disabled)
```

Actually — pprof in OpenBao is enabled via the `pprof` listener option in some
versions. In 2.7.1, confirm with:

```bash
bao sys/config/state/sanitized | jq '.data.listeners'
```

and never put a public listener in front of it.

---

## 5.7 Quotas, rate limits and lockout

### Rate limit quotas

```bash
# Global rate limit: 50 requests/second per client IP
bao write sys/quotas/rate-limit/global \
    rate=50 \
    path="" \
    block_interval=60

# Per-mount
bao write sys/quotas/rate-limit/kv \
    rate=200 \
    path="secret/" \
    block_interval=30

# Per-role login limit (most specific wins)
bao write sys/quotas/rate-limit/oidc-login \
    rate=5 \
    path="auth/oidc/login" \
    role="human-login"
```

> 💡 **Precedence:** the most specific rule wins — path > mount > namespace >
> global; a rule with a `role` beats all of them. Quotas are **per-node, per
> client IP**, and are *not* replicated across the cluster.

### Lease count quotas

```bash
# Limit the number of leases in a mount (prevents a crashloop from
# creating thousands of database users)
bao write sys/quotas/lease-count/db \
    max_leases=1000 \
    path="db/"
```

> 🚨 This is a real, observed failure mode: *"a deployment that requests
> credentials in a tight loop, a crashlooping pod, or a job that never revokes
> will pile up leases until revocation lags and the database fills with
> users."* Set lease-count quotas on your database mounts.

### User lockout

Enabled by default:

| Setting | Default |
|---|---|
| Lockout threshold | 5 failed attempts |
| Lockout duration | 15 minutes |
| Counter reset | 15 minutes after last attempt |

Configurable:

```hcl
user_lockout "all" {
  lockout_threshold = 5
  lockout_duration  = "15m"
  lockout_counter_reset = "15m"
}

user_lockout "userpass" {
  disable_lockout = false
}
```

Or per-mount:

```bash
bao write auth/userpass/tune disable_lockout=false
```

> ⚠️ **Only `userpass`, `ldap` and `approle` support lockout.** Not OIDC/JWT
> (the IdP handles that) and not `kubernetes`.

### Lease TTL discipline

```bash
# Never let a mount hand out long-lived dynamic creds
bao secrets tune -default-lease-ttl=1h -max-lease-ttl=4h db
```

---

## 5.8 Policy hygiene

### The five rules

1. **Deny by default.** Start from nothing, add what you need.
2. **Never `path "*" { capabilities = ["*"] }`.** If you must have a broad
   grant, enumerate capabilities and carve out `deny` paths.
3. **Never `sudo` on `sys/raw`.** That is root.
4. **Scope by path AND by capability.** `read` on `secret/data/app` ≠ `list` on
   `secret/metadata/app`.
5. **Separate humans from machines.** Different auth methods, different
   policies, different groups.

### The policy review checklist (repeat from Level 3)

```
□ Narrowest possible path?
□ Minimum capabilities?
□ Does it need list/scan (leaks data shape)?
□ Does it need sudo (almost never)?
□ Shared write path? (someone can overwrite you)
□ deny carve-outs for sensitive sub-paths?
□ Survives "app fully compromised"?
□ Scoped to one namespace?
```

### Namespace isolation as a security boundary

```bash
bao namespace create team-a
bao namespace create team-b
```

Each namespace has its own mounts, policies, auth methods, tokens. Root
namespace admins are **not** automatically admins inside a namespace. Use
namespaces to make "team A cannot read team B's secrets" a *structural*
property rather than a policy promise.

> 🔒 Cross-namespace identity references are off by default.
> `unsafe_cross_namespace_identity` should stay **off** — the docs say it
> "allows for unconfined permission sharing".

---

## 5.9 Secret lifecycle — rotation without downtime

### The rotation matrix

| Secret type | How it rotates | Automation |
|---|---|---|
| **Dynamic DB creds** | Lease expiry + revocation | Built in ✅ |
| **PKI leaf certs** | TTL expiry + client renewal | Built in ✅ |
| **KV v2 static values** | You write a new version | Script / CI |
| **Transit keys** | `transit/keys/<n>/rotate` | Script / CI |
| **Cloud IAM creds** | Cloud plugin lease | Plugin ✅ |
| **Passwords in an external IdP** | IdP's job | Keycloak ✅ |

### Automated KV rotation with a controlled window

```bash
#!/usr/bin/env bash
# rotate-secret.sh — rotates a KV v2 value and keeps the old one valid briefly
set -euo pipefail

MOUNT="${1:?mount}"; KEY="${2:?key}"; NEW_VALUE="${3:?new value}"
TTL="${4:-24h}"

# 1. Write the new value
bao kv put -mount="$MOUNT" "$KEY" password="$NEW_VALUE"

# 2. Keep the previous version readable for the overlap window
#    (KV v2 keeps N versions by default — verify max_versions is high enough)

# 3. Audit
echo "rotated $MOUNT/$KEY at $(date -Is)" >&2
```

Wire it into GitHub Actions with an OIDC login (Level 7) — **never** with a
stored root token.

### Rotation policy for a real org

```
  LLM provider API key   → every 90 days, or immediately on suspicion
  Database password      → dynamic creds, no static password at all
  TLS leaf certs         → every 24h (automatic)
  Transit keys           → every 6 months, or per NIST 800-38D guidance
  Service-to-service     → dynamic creds
  Human passwords        → Keycloak's job
```

---

## 5.10 Supply chain — plugins are code you execute

> **2.7.0 moved a LOT of functionality into plugins.** That makes plugin
> management a first-class supply-chain concern.

### What moved to plugins in 2.7.0

| Moved | Where it lives now |
|---|---|
| `awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`, `pkcs11` seals | `openbao/openbao-plugins` |
| `kerberos` auth | `openbao/openbao-plugins` |
| `ldap` auth | `openbao/openbao-plugins` |
| `radius` auth | `openbao/openbao-plugins` |
| `ldap` secrets | `openbao/openbao-plugins` |

### Declarative plugin distribution (2.5.0+, hardened in 2.7.0)

```hcl
plugin_directory = "/openbao/plugins"

plugin_auto_download   = true
plugin_auto_register   = true    # ← default true since 2.7.0
plugin_download_behavior = "fail"  # fail loudly rather than silently skip

plugin "kms" "pkcs11" {
  # Pin by digest — 2.7.0 feature
  image = "ghcr.io/openbao/openbao-plugin-kms-pkcs11@sha256:<digest>"
  # 2.7.0: binary_name is auto-detected from ENTRYPOINT/CMD if unset
  # binary_name = "openbao-plugin-kms-pkcs11"
}

plugin "secrets" "aws" {
  image = "ghcr.io/openbao/openbao-plugin-secrets-aws:2.7.1"
}
```

> 🔒 **Supply-chain rules:**
> 1. **Pin by digest**, never by tag. Tags move.
> 2. `plugin_auto_download = true` means OpenBao **pulls and executes code at
>    boot**. Only do that from a registry you control, over TLS, with digests
>    pinned. If you don't want auto-download, set it to `false` and install
>    plugins as a build step.
> 3. `plugin_download_behavior = "fail"` — don't let a failed download silently
>    degrade to "no plugin".
> 4. 2.5.5 added `plugin_download_max_size` (default 512 MB) to limit the size
>    of downloaded plugin binaries. Keep it.
> 5. `plugin_auto_register = true` (2.7.0 default) means a downloaded plugin is
>    registered automatically. Understand that before enabling it.
> 6. 2.7.0 fixed a security issue where the plugin command name was not
>    resolved relative to `plugin_directory` (GHSA-j6wc-jpvg-xfxq) and another
>    restricting catalog writes to the root namespace (GHSA-cg72-x35g-xfp8).
>    **Run 2.7.1.**

### Manual plugin management

```bash
bao plugin init <sha256> <command> [args...]   # register a local binary
bao plugin list
bao plugin info <name>
bao plugin register <sha256> <command>
bao plugin reload <name>                        # 2.7.0: KMS plugin configs reload on SIGHUP
bao plugin prune                                # 2.7.0: remove unused OCI downloads
bao plugin deregister <name>
```

> 💡 **2.7.0 improvement:** KMS plugin configuration stanzas now reload on
> `SIGHUP` and respawn plugin clients — so you can upgrade a KMS plugin
> **without restarting the whole cluster**.

---

## 5.11 Patch cadence

OpenBao ships security fixes frequently. Look at 2.7.1 alone:

| GHSA | What it fixed |
|---|---|
| `GHSA-3237-j65r-m5rp` | `tls_acme_eab_mac_key` disclosure via `sys/config/state/sanitized` |
| `GHSA-q74w-hv5x-6hxf` | Unauthenticated root-gen/rekey endpoints returned a response even when audit logging failed |
| `GHSA-7m59-mp95-w6ph` | **AppRole secret_id usable after expiry** (before `tidy` ran) |
| `GHSA-5v22-543h-wg96` | AppRole form-data login JSON-decode path |
| `GHSA-gf3j-hm38-jhh5` | **Kubernetes SA JWT not validated on renewal** — a revoked token could keep renewing |

That is **five security fixes in a patch release**. The Kubernetes one is the
scariest: a revoked service account token could keep renewing.

### The policy

```
  Security patch releases (2.7.1, 2.6.3, 2.5.5)   → within 7 days
  Minor releases (2.7.0, 2.6.0)                   → within 30 days, after testing
  Major/minor upgrades                            → planned window, never "just deploy it"
```

Automate it:

```yaml
# .github/workflows/openbao-patch-watch.yml
name: OpenBao patch watch
on:
  schedule:
    - cron: "0 9 * * 1"     # Mondays 09:00 UTC
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check latest release
        id: rel
        run: |
          LATEST=$(curl -s https://api.github.com/repos/openbao/openbao/releases/latest \
                   | jq -r .tag_name)
          echo "latest=$LATEST" >> $GITHUB_OUTPUT
      - name: Compare with deployed version
        run: |
          if [ "${{ steps.rel.outputs.latest }}" != "v2.7.1" ]; then
            echo "::warning::OpenBao ${{ steps.rel.outputs.latest }} is available (deployed: v2.7.1)"
          fi
```

> 📌 Also: **2.7.0 removed the `file` storage backend** and
> **deprecated it for `operator migrate`** (removal in 2.8.0). If you use
> `pebbledb`, note the deprecation is scoped to `bao operator migrate`.

---

## 5.12 The complete hardening checklist

Print this. Tick it. Do it in this order.

### Before first production traffic

```
□ TLS enabled on every listener, tls_min_version >= tls12
□ BAO_CACERT configured on every client; no verify=False anywhere
□ Swap disabled (or encrypted) for the OpenBao process; core dumps disabled
□ Audit device(s) enabled — at least two, log_raw=false, mode=0600
□ Audit log shipped off-box to immutable storage
□ Root token revoked
□ Break-glass admin path created and TESTED
□ Recovery keys generated, stored offline, and the procedure rehearsed
□ Seal health check enabled and alerting
□ All policies reviewed: no "*" capabilities, no sudo, no sys/raw
□ Unused auth methods disabled
□ Unused secret engines disabled
□ Quotas configured (rate limit + lease count on dynamic mounts)
□ Namespaces created for team isolation (if multi-team)
□ Network policies: 8201 only between nodes; no public ingress
□ Cluster port protected (mTLS on the listener, or firewall to node-to-node)
□ Snapshot taken and a RESTORE tested in a lab
□ Monitoring + alerting live (health, audit failures, seal health, lease counts)
```

### Ongoing

```
□ Patch cadence enforced
□ Secret rotation schedule defined and automated
□ Access reviews (quarterly): tokens, policies, entities, groups
□ Lease/credential leak check: DB role count vs active lease count
□ Restore drill performed at least twice a year
□ Unseal-key/unseal-cluster access reviewed
□ Plugin versions pinned and tracked
```

---

## 5.13 Level 5 checkpoint

1. Why is `verify=False` in a Python client a security failure, not a convenience?
2. Why does OpenBao 2.x have no `disable_mlock` option, and what does it
   ask you to do instead?
3. Which auto-unseal mechanisms are **no longer built in** to 2.7.1?
4. What happens to your cluster if the KMS key that unseals it is deleted?
5. What happens to OpenBao if all audit devices fail? Is that good or bad?
6. Why is `log_raw` never acceptable in production?
7. What's the difference between a rate-limit quota and a lease-count quota, and
   which one stops the "crashloop creates 10,000 DB users" problem?
8. Why should `unsafe_cross_namespace_identity` stay off?
9. Name three things you should pin about a plugin.
10. Which GHSA from 2.7.1 would have let a revoked Kubernetes token keep working?

**Next → [Level 6: HA-PRODUCTION.md](06-HA-PRODUCTION.md)** — the reference
production architecture: 5-node Raft, PostgreSQL backend, snapshots, upgrades,
observability, disaster recovery.

---

## 5.14 Scratchpad

```
TLS:                 tls_min_version="tls12"  tls_auto_reload=true  (2.7.0)
Swap:                no disable_mlock in 2.x! disable/encrypt swap (mem_swap.max=0)
Seal (2.7.0):        plugin "kms" "name" {...} + seal "name" {...}
Audit:               ≥2 devices, log_raw=false, mode=0600, ship off-box
Root token:          init → use → revoke → generate-root when needed
Quotas:              sys/quotas/rate-limit, sys/quotas/lease-count
Lockout:             userpass/ldap/approle only; 5 tries / 15 min default
Plugins:             pin by sha256 digest, plugin_download_behavior="fail"
Patches:             2.7.1 fixes: GHSA-3237, q74w, 7m59, 5v22, gf3j
```
