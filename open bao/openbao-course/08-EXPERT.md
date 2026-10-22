# Level 8 — Expert: The Advanced Surface

> **Goal:** the features that separate a competent OpenBao operator from an
> expert. Namespaces at scale, the plugin system, workflows, External Keys,
> post-quantum crypto, CEL validation programs, control groups, and the
> password-policy subsystem.

---

## 8.1 Namespaces at scale

### What a namespace really is

A namespace is a **mini-OpenBao** living inside one instance:

```
root/                          ← the cluster's control plane
├── auth/oidc/                 ← IdP config
├── identity/                  ← entities, groups
├── secret/                    ← shared platform secrets
├── policy/                    ← shared policies
│
├── ns-platform/               ← a tenant
│   ├── secret/                ← its own KV
│   ├── auth/approle/          ← its own auth methods
│   ├── identity/              ← its own entities
│   └── policy/                ← its own policies
│
└── ns-payments/               ← another tenant
    ├── secret/
    └── ...
```

Each namespace has its **own login paths**. A user logging into
`ns-platform/auth/oidc` is entirely separate from `ns-payments/auth/oidc`.

### Creating and working with namespaces

```bash
# Create
bao namespace create platform-team
bao namespace list

# Work inside one
export BAO_NAMESPACE=platform-team
bao secrets enable kv-v2
bao policy write my-policy - <<'EOF'
path "secret/data/*" { capabilities = ["read"] }
EOF

# Or per-command
bao secrets list -namespace=platform-team
bao -namespace=platform-team kv get secret/myapp
```

### The critical difference from Vault: namespaces are free

In HashiCorp Vault, namespaces are an **Enterprise** feature with client-count
metering. In OpenBao, they're **free** — and that removes the usual objection to
multi-tenancy (the "client count" fear doesn't apply).

### The delegation model

```bash
# Create a namespace as the platform team
bao namespace create team-a

# Give them an admin policy *inside* their namespace
bao policy write ns-admin - <<'EOF'
path "sys/mounts/*"    { capabilities = ["create", "read", "update", "delete", "list"] }
path "sys/auth/*"      { capabilities = ["create", "read", "update", "delete", "list"] }
path "sys/policies/acl/*" { capabilities = ["create", "read", "update", "delete", "list"] }
path "identity/*"      { capabilities = ["create", "read", "update", "delete", "list"] }
path "secret/*"        { capabilities = ["create", "read", "update", "delete", "list", "scan"] }
EOF

# Assign it to a group in the parent namespace
bao write identity/group name=team-a-admins policies=ns-admin
```

Now the team admins can manage their own namespace without being root-namespace
admins.

### Child namespaces and inheritance

```
ns-platform/
└── ns-platform/subsidiary/
```

A child namespace **inherits** policies and identities from its parent. You can
also let a parent "assert" policies on identities in a child.

### Namespace sealing (2.6.0)

```bash
# Create a namespace with its own Shamir seal
bao namespace create -seal-shares=5 -seal-threshold=3 team-sensitive
```

This gives the namespace **its own barrier keyring**. A tenant can then seal
their own namespace, revoking the operator's access to their data **without
touching any other tenant**. Seal status is synchronised globally, so it's
visible from any node.

```bash
bao namespace seal-status team-sensitive
bao namespace seal team-sensitive
```

> 💡 This is a genuinely differentiated feature vs Vault Community, and it's
> the kind of thing that matters if you're offering OpenBao as an internal
> service to other teams.

### Cross-namespace identity — leave it off

```hcl
unsafe_cross_namespace_identity = false     # ← the default, keep it
```

The docs are explicit: it "gives compatibility with Vault Enterprise's
cross-namespace group membership and **should not be enabled**" because "there
are no mitigating controls on what identities or groups another namespace can
reference and allows for unconfined permission sharing."

### Namespace quotas

```bash
bao namespace quota \
    rate_limit=200 \
    path="" \
    namespace="team-a"
```

---

## 8.2 The plugin system

### Architecture

```
┌──────────────────────────────────────────────────┐
│  OpenBao core (Go binary)                        │
│  ├── Router, policy engine, barrier, audit       │
│  └── Plugin interface (gRPC over a local socket) │
└───────────┬──────────────────────────────────────┘
            │  hashicorp/go-plugin + gRPC
   ┌────────┴─────────┬──────────────┬──────────────┐
   ▼                  ▼              ▼              ▼
┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────┐
│ secrets  │   │ auth      │   │ audit    │   │ kms      │
│ plugin   │   │ plugin    │   │ plugin   │   │ plugin   │
└──────────┘   └───────────┘   └──────────┘   └──────────┘
```

Plugin types: `secrets`, `auth`, `audit`, `kms`, `database`.

### What became a plugin (and why it matters to you)

| Plugin | Was | Now | Why you care |
|---|---|---|---|
| `kms-pkcs11` | Built-in `pkcs11` seal | Plugin (2.7.0) | HSM auto-unseal without the HSM distribution |
| `kms-aws` | Built-in `awskms` seal | Plugin (2.7.0) | Same |
| `kms-gcp`, `kms-azure`, `kms-alicloud`, `kms-oci` | Built-in | Plugin (2.7.0) | Same |
| `kms-ovhcloud`, `kms-tcloudpublic`, `kms-securosys` | Built-in | Plugin (2.7.0) | Same |
| `auth-ldap`, `auth-kerberos`, `auth-radius` | Built-in | Plugin (2.7.0) | Legacy enterprises |
| `auth-github`, `auth-aws` | — | Plugin | Cloud / GitHub |
| `secrets-ldap` | Built-in | Plugin (2.7.0) | Legacy enterprises |
| `secrets-aws`, `secrets-gcp`, `secrets-consul`, `secrets-nomad` | — | Plugin | Cloud / legacy |
| `database-mongodb` | Built-in in Vault (SSPL) | Plugin | MongoDB dynamic creds |
| `secrets-oauthapp` | — | Separate repo | OAuth 2.0 grant types |

### The verified plugin registry (as of October 2026)

First-party plugins are published as **GitHub releases** in
`https://github.com/openbao/openbao-plugins` and as **OCI images** on
`ghcr.io/openbao/`. The image name is
`ghcr.io/openbao/openbao-plugin-<name>:<tag>`, and the tag matches the release
tag. Verified live:

| OCI image | Available tags |
|---|---|
| `ghcr.io/openbao/openbao-plugin-kms-pkcs11` | `v0.1.0`, `v0.2.0`, **`v0.2.1`** |
| `ghcr.io/openbao/openbao-plugin-kms-aws` | `v0.1.0` |
| `ghcr.io/openbao/openbao-plugin-kms-azure` | `v0.1.0` |
| `ghcr.io/openbao/openbao-plugin-secrets-aws` | `v0.0.1` … **`v0.3.1`** |
| `ghcr.io/openbao/openbao-plugin-secrets-gcp` | … `v0.22.0`, `v0.23.0`, **`v0.23.1`** |
| `ghcr.io/openbao/openbao-plugin-auth-ldap` | `v0.1.0` |
| `ghcr.io/openbao/openbao-plugin-auth-github` | `v0.0.1` |

> 💡 There are also two separate plugin repos outside `openbao-plugins`:
> `openbao/openbao-plugin-auth-jwt` and
> `openbao/openbao-plugin-secrets-oauthapp`.

**Pin by digest**, not by tag:

```bash
# Get the digest for a tag
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:openbao/openbao-plugin-kms-pkcs11:pull&service=ghcr.io" | jq -r .token)
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/openbao/openbao-plugin-kms-pkcs11/manifests/v0.2.1" \
  | jq -r '.manifests[0].digest'
```

> 🔒 **The upgrade trap:** if your config references a plugin that is no longer
> built in, **install and register the plugin BEFORE upgrading the binary**.
> Otherwise the new node starts and cannot unseal.

### Installing plugins

**Option 1 — declarative, from an OCI registry (2.5.0+):**

```hcl
plugin_directory = "/openbao/plugins"

plugin_auto_download     = true
plugin_auto_register     = true
plugin_download_behavior = "fail"

plugin "kms" "pkcs11" {
  # Pin by digest (2.7.0) — never by a moving tag
  image = "ghcr.io/openbao/openbao-plugin-kms-pkcs11@sha256:abc123..."
}

plugin "secrets" "aws" {
  image = "ghcr.io/openbao/openbao-plugin-secrets-aws:v0.3.1"
  # binary_name auto-detected from ENTRYPOINT/CMD in 2.7.0
}
```

**Option 2 — manual:**

```bash
bao plugin init <sha256> <command> [args...]
bao plugin list
bao plugin info <name>
bao plugin reload <name>
bao plugin prune          # 2.7.0: remove unused OCI downloads
bao plugin deregister <name>
```

### 2.7.0's plugin security fixes — read these

| GHSA | Fix |
|---|---|
| `GHSA-j6wc-jpvg-xfxq` | Plugin command name is now resolved **relative to `plugin_directory`** before execution |
| `GHSA-cg72-x35g-xfp8` | Writes to `sys/plugins/catalog/*` are restricted to the **root namespace** |
| — | `plugin_auto_register` now defaults to `true` |
| — | `sha256sum` no longer required for manually installed plugin binaries |
| — | OCI plugins can be pinned **by manifest digest** |

### Using a plugin

```bash
# Secrets plugin
bao secrets enable -path=aws aws
bao write aws/config/root access_key=... secret_key=...
bao write aws/roles/my-role credential_type=iam_user

# Auth plugin
bao auth enable -path=aws aws
bao write auth/aws/role/my-role credential_type=iam_user

# KMS plugin as a seal
seal "pkcs11" {
  # ... PKCS#11 specific options
}
```

### Plugin upgrade without downtime (2.7.0)

> *"core/plugins: Reload KMS plugin configuration stanzas on `SIGHUP` and
> respawn plugin clients as needed, enabling plugin upgrades at runtime."*

```bash
# Replace the plugin binary
cp new-openbao-plugin-kms-pkcs11 /openbao/plugins/

# Reload
kill -HUP $(pgrep bao)
# or
bao plugin reload pkcs11
```

---

## 8.3 Workflows (2.6.0)

### What they are

Workflows let operators define a **named, multi-request sequence** that users
execute in one call. They provide "a simplified or managed interface over
OpenBao's standard API" and "a basic (workflow-defined) form of cross-plugin
communication".

Think: a **macro** for API calls.

```bash
# Manage (privileged)
bao list sys/workflows/manage
bao read sys/workflows/manage/create-namespace
```

### Where they're defined

Workflows are configured **in the server config file** (like self-initialization),
not via the API. The API only *manages* and *executes* them.

```hcl
# (server config)
workflow "create-namespace" {
  description = "Create a namespace and its initial policy"

  step "create" {
    operation = "update"
    path      = "sys/namespaces/team-{{identity.entity.name}}"
    data = {
      description = "team namespace"
    }
  }

  step "policy" {
    operation = "update"
    path      = "sys/policies/acl/team-default"
    data = {
      policy = <<-EOT
path "secret/data/*" { capabilities = ["read"] }
EOT
    }
  }
}
```

### Executing

```bash
bao write sys/workflows/execute/create-namespace
```

Or via the API: `POST /v1/sys/workflows/execute/:path`

### The `allow_unauthenticated_workflows` flag

```hcl
allow_unauthenticated_workflows = true
```

This lets the workflow be **dispatched** without authentication — but the
*requests inside* it still require authentication, which can be supplied as a
request parameter. Use this for a public "request a certificate" style flow.

> ⚠️ **Manage workflows is a privileged operation.** The docs are clear:
> *"a workflow cannot do anything more than the token it is executed as can
> do... but workflows can result in high server load depending on the endpoints
> called."* Keep workflow definitions in git and review them like code.

### When to use workflows

| Use case | Workflow? |
|---|---|
| "Create a namespace + a policy + a mount" | ✅ Perfect |
| "Issue a cert + write the private key to KV" | ✅ Great |
| "Rotate a secret across 3 systems" | ✅ Useful |
| A single API call | ❌ Just call the API |

---

## 8.4 External Keys (2.7.0) — keys in an HSM, not in OpenBao

### The problem it solves

In a normal PKI setup, the **intermediate CA's private key lives inside
OpenBao**. It's encrypted at rest, but it *is* in OpenBao. If OpenBao is
compromised, the CA key is compromised — and a compromised intermediate CA
means you must distrust every cert it ever issued.

**External Keys** lets the PKI and Transit engines use a key held in an
**external KMS or HSM**. The private key never enters OpenBao at all.

> 📌 External Keys are OpenBao's equivalent of Vault Enterprise's *Managed
> Keys*, redesigned for flexibility. **Not API-compatible** with Managed Keys.

### Supported engines

| Engine | What it externalises |
|---|---|
| **PKI** | Certificate signing via root and intermediate paths, using external private keys |
| **Transit** | Sign, verify, encrypt, decrypt with external key material |

### The API

```
/sys/external-keys/...
```

```bash
# List configured external keys
bao list sys/external-keys

# Map a mount to an external key
bao write sys/external-keys/pki_int \
    keys="my-hsm-key" \
    backend="kms" \
    # ... backend-specific configuration
```

Then grant access to the mounts that use them (external keys are **per
namespace** — a secrets engine in a namespace can only use external keys
configured in that same namespace).

### Backends

| Backend | Source |
|---|---|
| **Transit** | Built-in. Similar in concept to the built-in Transit seal — a transit engine in the same or another cluster holds the key |
| **PKCS#11** | `kms-pkcs11` plugin from `openbao-plugins` |

```hcl
# PKCS#11-backed external key
plugin "kms" "pkcs11" {
  command = "openbao-plugin-kms-pkcs11"
}

seal "pkcs11" {
  # ...
}
```

### The architecture

```
   ┌────────────┐   sign request    ┌──────────────┐
   │  OpenBao   │──────────────────▶│  HSM / KMS   │
   │  PKI       │◀──────────────────│  (holds key) │
   │  (no key!) │   signature       └──────────────┘
   └────────────┘
```

Compare with a normal (non-external) PKI:

```
   ┌────────────┐   sign request    ┌──────────────┐
   │  OpenBao   │──────────────────▶│  OpenBao     │  ← the key is HERE
   │  PKI       │◀──────────────────│  barrier+KV  │
   └────────────┘   signature       └──────────────┘
```

### When to use it

| Situation | External Keys? |
|---|---|
| Compliance requires the CA key in an HSM | ✅ **Yes** |
| You want a stolen OpenBao to not mean a stolen CA | ✅ **Yes** |
| You're on a cloud KMS and want one key story | ✅ Yes |
| You're a small team, cost matters | ❌ Overkill — the built-in PKI is fine |
| You want Transit to encrypt with an HSM key | ✅ Yes |

---

## 8.5 Post-quantum cryptography (2.7.0)

OpenBao 2.7.0 is one of the first secrets managers to ship **pure post-quantum
** protections at the TLS layer.

### ML-DSA (NIST FIPS 204) in PKI and Transit

```bash
# PKI role using ML-DSA
bao write pki_int/roles/pqc-app \
    key_type="mldsa-44" \
    signature_bits=0 \
    max_ttl="24h"

# Transit ML-DSA keys
bao write transit/keys/pqc-key \
    type="mldsa-44"          # or mldsa-65, mldsa-87

bao write transit/sign/pqc-key \
    input=$(echo -n "data" | base64)

bao write transit/verify/pqc-key \
    input=$(echo -n "data" | base64) \
    signature="vault:v1:..."
```

| Parameter | Meaning |
|---|---|
| `mldsa-44` | NIST security category 2 |
| `mldsa-65` | NIST security category 3 |
| `mldsa-87` | NIST security category 5 |

> ⚠️ **The OCSP caveat, straight from the release notes:** *"Go's OCSP
> implementation does not support ML-DSA so will be unusable with ML-DSA typed
> issuers."* If your revocation strategy depends on OCSP, ML-DSA roles won't
> work with it.

### Pure-PQC TLS (2.7.0)

```hcl
listener "tcp" {
  address        = "0.0.0.0:8200"
  tls_cert_file  = "/openbao/certs/openbao.crt"
  tls_key_file   = "/openbao/certs/openbao.key"

  # Force post-quantum key exchange
  tls_key_exchange_preferences = ["X25519MLKEM768", "SecP256r1MLKEM768"]
}
```

| Algorithm | Notes |
|---|---|
| `X25519MLKEM768` | X25519 + ML-KEM-768. The modern default choice. |
| `SecP256r1MLKEM768` | NIST P-256 + ML-KEM-768 |
| `SecP384r1MLKEM1024` | NIST P-384 + ML-KEM-1024. Strongest. |
| `MLKEM1024` | Pure ML-KEM (no classical component) |

You can also serve **ML-DSA certificates** from the listener, and OpenBao's
**outbound** TLS (to a transit seal cluster, to Postgres, to an OIDC provider)
can now connect to servers presenting these algorithms.

### Why this matters

The "**harvest now, decrypt later**" threat: an adversary records encrypted
traffic today and decrypts it in 10 years when quantum computers can break
classical RSA/ECDHE. For a secrets manager whose traffic carries tokens and
secrets, that's a real concern for long-lived data.

**Practical advice:** you don't need PQC everywhere today. But if your
organisation has a PQC migration plan, OpenBao 2.7 gives you the *server* side
of it, which is the hard part.

---

## 8.6 CEL validation programs

### What CEL is

**Common Expression Language** — a small, fast, sandboxed expression language.
OpenBao uses it in **PKI** and **JWT/OIDC** for declarative validation rules and
policies.

### The structure

```
CelProgram
├── Expression    ← the main expression: accept or reject
└── CelVariable[] ← named sub-expressions, evaluated in order
```

### The main expression

It must return the engine's success object, or a `string`/`bool` error:

```go
require_cn ? 'request should have a common_name' : (validate_ttl ? 'request has invalid TTL' : "Request Rejected")
```

Use a **ternary** so a value is always produced:

```go
cond ? SuccessObject : error string/bool
```

### The warning you must internalise

> ⚠️ *"CEL is an advanced topic for operators. All validation is taken on by the
> CEL program created by the operator; limited to no validation is performed by
> OpenBao above and beyond what the CEL program contains. **It is up to the
> operator to craft CEL programs which adequately perform validation.**"*

**CEL programs replace OpenBao's built-in checks. If your program is wrong,
OpenBao will do the wrong thing.** Test extensively. Start by *adding* to the
defaults, not replacing them.

### Where it's used

**PKI** — a `validation` block on a role:

```bash
bao write pki_int/roles/strict \
    validation_cel_program='
      variable "require_cn" {
        expression = "has(request.common_name) && request.common_name != \"\""
      }
      variable "validate_ttl" {
        expression = "request.ttl <= 86400"
      }
      expression = "require_cn && validate_ttl ? ValidationOutput : \"Request Rejected: invalid common_name or ttl\""
    '
```

**JWT/OIDC** — a `validation_cel_program` on the role, controlling which claims
are required and how they're interpreted.

### Practical guidance

```
□ Start with the simplest possible program
□ Add one condition at a time
□ Test with both valid and invalid inputs
□ Keep the built-in checks AND your CEL program until you're confident
□ Review CEL programs like code (they're in git, they're reviewed)
```

---

## 8.7 Control groups (2.7.0) — the two-person rule

### The concept

> *"In some deployments, it may be desirable to require a 'second set of eyes'
> to approve access to a secret or to generate a certificate. Control groups
> implement second-party authorization by means of policy 'factors' applied to
> a path."*

When a request hits a path with a control-group factor, OpenBao **does not
execute it**. It returns a **wrapped response** containing a token and an
accessor. A member of the approving group authorizes it. Then the requester
unwraps it, and *that* is when the original request executes.

### The workflow

```
1. Policy declares a control_group for a path
2. Requester calls the path
3. OpenBao returns a wrapped response (token + accessor), NOT the secret
4. Requester forwards the accessor to an approver
5. Approver reviews it, authorizes it
6. Requester unwraps → the original request executes → secret released
```

> ⚠️ **OpenBao sends no notification to approvers.** You have to build the
> notification (a webhook, a queue, a Slack bot) or nobody will ever approve
> anything.

### The policy

```hcl
path "pki/issue/*" {
  capabilities = ["read", "update"]

  control_group = {
    factor "pki-approvers" {
      controlled_capabilities = ["update"]

      identity {
        # Who can approve
        group_names = ["pki-approvers", "security-team"]
        approvals   = 1        # how many must approve

        # How long an authorization stays valid
        ttl = "5d"

        # Allow self-authorization?
        allow_self_authorization = false
      }
    }
  }
}
```

### The operations

Via `sys/wrapping` and `sys/control-group`:

| Operation | Path | What it does |
|---|---|---|
| **Authorize** | `sys/control-group/authorize` | Approve the request using the accessor |
| **Review** | `sys/control-group/request` | View the original request (entity, path, payload) using the accessor |
| **Unwrap** | `sys/wrapping/unwrap` | Execute the original request (only works once approved) |

```bash
# 1. Requester
bao write pki/issue/myapp common_name="prod.example.com"
# → { "wrap_info": { "token": "hvs...", "accessor": "6f1c..." } }

# 2. Requester sends the accessor to an approver (out of band)

# 3. Approver reviews
bao write sys/control-group/request accessor=6f1c...

# 4. Approver authorizes
bao write sys/control-group/authorize accessor=6f1c...

# 5. Requester unwraps → the cert is issued
bao unwrap hvs...
```

### Why this is the strongest anti-insider control in OpenBao

Even a **fully compromised OpenBao admin token** can't unilaterally read a
protected path. They need a *second* identity with a *separate* group
membership. That's a genuine separation of duties, enforced cryptographically
by the approval flow.

**This is the answer to "what if an admin account is popped?"**

---

## 8.8 Password policies (advanced)

Password policies control **how OpenBao generates passwords** for dynamic and
static users in certain engines.

```bash
bao write sys/policies/password/my-policy \
    length=24 \
    lower=true \
    upper=true \
    digit=true \
    special="!@#$%^&*" \
    policy_name="my-policy"
```

| Rule | Meaning |
|---|---|
| `length` | Minimum length |
| `lower` / `upper` / `digit` | Require each class |
| `special` | The special-character set |
| `excludes` | Characters to exclude (ambiguous ones like `O`/`0`) |

> ⚠️ **The docs mark this as advanced and dangerous:**
> *"This generates credentials for external systems (databases, LDAP, etc.) and
> should be used with caution."* A password policy that's too strict produces
> credentials that break target systems' password rules.

Reference it from a database role:

```bash
bao write db/roles/app \
    db_name=postgres \
    creation_statements="..." \
    password_policy="my-policy"
```

> 💡 **Password policies are unrelated to OpenBao's own `default` policy** —
> they just share a similar name. Don't confuse them.

---

## 8.9 Other expert features worth knowing

### The `sudo` capability (and why it's scary)

```hcl
path "sys/raw" { capabilities = ["sudo", "read"] }
```

`sudo` on `sys/raw` lets a token read and **write raw encrypted storage** —
effectively root. If `raw_storage_endpoint = true` is set in the server config,
this path exists.

```hcl
# Default: the endpoint doesn't exist
raw_storage_endpoint = false
```

### The OpenAPI spec endpoint

```bash
bao read sys/internal/specs/openapi > openapi.json
```

Generate client code, or hand it to your team so they can build against the
real API.

### The resultant ACL endpoint

```bash
bao read sys/internal/ui/resultant-acl
```

Shows the **effective** policy for a token — invaluable for debugging
"why can they do that?".

### `sys/monitor` — streaming request logs

```bash
bao monitor -log-level=info
```

Streams every request as it happens. Great for live debugging, dangerous in
production (it can log secrets if `log_raw` is on).

### `sys/leases/lookup` and lease metadata

```bash
bao write sys/leases/lookup lease_id=database/creds/app/...
```

Since 2.6.0, lease lookup responses include `path`, `namespace_path` and
`revoke_error` — much easier to debug.

### Server-side consistent tokens (SSCTs)

2.7.0 improved SSCTs to support storage-indicated index values (previously
always `0`). SSCTs are encrypted tokens that carry their own authorisation —
useful for delegated access without a server-side token record.

```bash
bao write sys/consistent-tokens/<name> \
    type=service \
    expiration_ttl=1h \
    orphan=true \
    path="secret/data/myapp"
```

### `sys/tools/*` — small utilities

```bash
bao write sys/tools/hash sha256        # hash input
bao write sys/tools/random bytes=32     # crypto-random bytes
bao write sys/tools/lookup path=secret/data/myapp
```

### `sys/config/state/sanitized` — what is the server actually running?

```bash
bao read sys/config/state/sanitized | jq
```

> ⚠️ 2.7.1 fixed **GHSA-3237-j65r-m5rp** — a disclosure of
> `tls_acme_eab_mac_key` through this endpoint. Another reason to run 2.7.1
> rather than 2.7.0.

### `sys/host-info` and `sys/ha-status`

```bash
bao read sys/host-info | jq
bao read sys/ha-status | jq
```

---

## 8.10 Kubernetes (brief, but you should know it exists)

```bash
helm repo add openbao https://openbao.github.io/openbao-helm
helm repo update
helm install openbao openbao/openbao \
  --namespace openbao --create-namespace \
  --set 'server.auditStorage.enabled=true' \
  --set 'server.dataStorage.size=10Gi' \
  --set 'injector.enabled=true' \
  --set 'global.image.tag=2.7.1'
```

The Helm chart is at `openbao/openbao-helm` (chart version `0.30.x` as of
October 2026).

Key components:
* **Server StatefulSet** with a `Raft` or `PostgreSQL` storage backend
* **Injector** — mutates pods to inject a `bao agent` sidecar that
  authenticates and renders secrets
* **Audit** — a sidecar that ships the audit log off-box

The injector pattern is the Kubernetes equivalent of the `bao agent` sidecar
pattern from §7.2 — same idea, automated.

> ⚠️ For Kubernetes, **auto-unseal is effectively mandatory** — you cannot have
> 3 humans unseal pods. Use the transit seal or a cloud KMS plugin.

---

## 8.11 Level 8 checkpoint

1. Why is namespace sealing (2.6.0) genuinely useful for a multi-tenant
   internal service?
2. Why must `unsafe_cross_namespace_identity` stay off?
3. What must you do *before* upgrading to 2.7.0 if you use the `pkcs11` seal?
4. Why pin OCI plugins by digest rather than tag?
5. What is a workflow, and when is it better than just calling the API?
6. What problem do External Keys solve that the built-in PKI doesn't?
7. What is the OCSP limitation of ML-DSA issuers?
8. What does a CEL program *replace*, and what is the risk?
9. Walk through the control-group flow from request to secret.
10. What breaks if you enable `sudo` on `sys/raw`?

**Next → [Level 9: REFERENCE.md](09-REFERENCE.md)** — the cheatsheet and
runbook.

---

## 8.12 Scratchpad

```
Namespaces:      bao namespace create <name>   BAO_NAMESPACE=<name>
Namespace seal:  bao namespace seal <name>     (2.6.0, own barrier keyring)
Plugins:         plugin "kms" "<name>" { image = "...@sha256:..." }
                 plugin_auto_download=true  plugin_auto_register=true
                 plugin_download_behavior="fail"
Workflows:       sys/workflows/manage  +  sys/workflows/execute/<name>
External keys:   sys/external-keys/<mount>  (PKI + Transit, per-namespace)
PQC:             key_type="mldsa-44|65|87"   tls_key_exchange_preferences
CEL:             validation_cel_program (PKI roles, JWT/OIDC roles)
Control groups:  control_group { factor "x" { identity { group_names, approvals } } }
                 sys/control-group/{authorize,request}  +  sys/wrapping/unwrap
Password policy: sys/policies/password/<name>
SSCT:            sys/consistent-tokens/<name>
```
