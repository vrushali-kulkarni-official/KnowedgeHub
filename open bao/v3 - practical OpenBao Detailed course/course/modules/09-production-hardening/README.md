# Module 09 — Production Hardening

> **Where we are.** Modules 01 through 08 gave Meridian AI a working secret
> store: KV v2 for static secrets, policies, namespaces and entities, AppRole
> and OIDC logins, the Transit and PKI engines, and the AI harness reading
> its secrets at runtime. Everything so far ran on one node, over plain HTTP,
> with a hand-managed unseal key, a local audit file, and no backups.
>
> This module is the difference between "it works on my laptop" and "a
> security reviewer signs off." We add transport encryption, an audit
> architecture that survives the CVE that broke the old one, auto-unseal with
> recovery keys, a real high-availability topology, backups, container
> hardening, monitoring, CI/CD, and an incident runbook.

**Status:** the running lab is single-node, plain HTTP, `pebbledb` storage,
Shamir seal, one local file audit device. Every command output in this
module comes from that live OpenBao **v2.7.1** server. Where a claim needs
a real 3-node cluster, real TLS certificates, or a real KMS, this module
says so explicitly instead of inventing a transcript.

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| **TLS** | Encrypts the wire so secrets never travel in plaintext; TLS on every listener, always. |
| **mTLS** | Client certificates too, so only cluster members can join; required on the Raft cluster port. |
| **Pure-PQC TLS** | 2.7 adds `tls_key_exchange_preferences` so the key exchange itself is post-quantum. |
| **ML-DSA** | FIPS 204 post-quantum signatures, usable in PKI, Transit, and TLS. |
| **Declarative audit** | 2.7 removed API-driven audit devices; the `audit` stanza in the config file is now the only way — and it needs **two labels plus an `options` map**. |
| **`log_raw`** | `false` HMACs secret values in the audit log; `true` writes plaintext you must never ship. |
| **CVE-2025-54997** | The bug that forced declarative audit: API admins could write audit logs to arbitrary host files. |
| **Off-host shipping** | The audit log on the host is a copy the host owner could edit; the SIEM copy is the evidence. |
| **Transit auto-unseal** | OpenBao unseals itself using a key held in a second OpenBao; survives unattended restarts. |
| **Recovery keys** | Auto-unseal mode *gives you* recovery keys; Shamir mode gives you none — see Module 01. |
| **KMS seals** | 2.7 moved all KMS seals to external plugins (`awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`, `pkcs11`). |
| **Raft** | The integrated storage backend that replicates across nodes; 3 or 5 nodes, odd. |
| **Failure domain** | A group of nodes that can all fail together; never put two raft voters in one. |
| **Standby** | A hot standby node that takes over without the quorum noticing. |
| **PostgreSQL horizontal scale** | 2.7 lets OpenBao read from Postgres read replicas instead of one writer. |
| **Snapshot** | A byte-level copy of the storage backend; encrypted, useless without the unseal/recovery keys. |
| **Back up data AND keys, separately** | The single most-skipped rule in secret management. |
| **`mlock`** | Keeps secret material out of swap; needs the `IPC_LOCK` capability. |
| **`ulimit -c 0`** | No core dumps; a core dump is a plaintext copy of your key material on disk. |
| **Non-root container** | The OpenBao image runs as uid 100 / gid 1000, and the volume quirk is `/openbao/file`. |
| **`cap_drop: ALL`** | Drop every Linux capability, then add back only `IPC_LOCK` if you need `mlock`. |
| **Read-only rootfs** | The container cannot write to its own filesystem. |
| **Pinned digest** | `image@sha256:...` instead of `:2.7.1`; tags move, digests do not. |
| **`/v1/sys/metrics`** | Prometheus-format metrics; the source of every alert you will write. |
| **Seal-state alerting** | Alert on `vault.core.unsealed == 0`; a sealed cluster is a total outage. |
| **Audit-health alerting** | `vault_audit_log_request_failure` rising means your evidence pipeline is broken. |
| **`bao policy fmt`** | Client-side policy validation — **no server, no credentials**; perfect for CI. |
| **Policies as code** | Policies live in Git; CI validates and applies them; drift is a failed build. |
| **Break-glass** | `bao operator generate-root` mints a new root token — but it still needs a quorum of unseal shares. |
| **Threat model** | Asset → threat → control → mechanism; the table that makes this module auditable. |

---

## 1. Why this matters

Let me reframe the problem in Meridian AI's terms.

The previous engineer committed a `.env` to Git. That was the *incident*. But
it was not the cause. The cause was that Meridian AI had **no place to put a
secret** that was safer than Git. Everything else — the plaintext listener,
the manual unseal key, the audit file nobody shipped off the box, the
no-backup storage — is the *same* root cause wearing different clothes.

A security review of Meridian AI's platform will not ask "did they use
OpenBao?" It will ask five questions:

1. **If someone captures the network traffic, do they get the secrets?**
2. **If the host is stolen, do they get the keys?**
3. **If the disk dies tonight, do we lose the secrets forever?**
4. **If an admin token leaks, how fast do we notice and how fast can we cut it off?**
5. **If someone breaks into the OpenBao API, can they write audit logs to `/etc/passwd`?**

Every section in this module answers one of those questions with a specific
OpenBao mechanism. That is what "production hardening" means: not a checklist
you print, but a set of controls you can point at.

> **Production:** *Hardening is not a one-time project. It is a set of controls
> that must be continuously verified. A control that is not monitored is a
> control that has silently stopped working.*

---

## 2. The hardening model: eight layers

Before any command, the mental model. Think of a secret store as an onion.
Each layer assumes the layer above it might already be broken.

```
  ┌─────────────────────────────────────────────────────────┐
  │ 8. Operations    runbooks, alerts, rotation, backups     │  ← the layer that
  │ 7. Supply chain images, digests, CI, drift detection     │    actually keeps
  │ 6. Runtime       non-root, cap_drop, read-only, mlock     │    the others alive
  │ 5. Audit         immutable, off-host, monitored            │
  │ 4. Availability  HA, snapshots, restore drills           │
  │ 3. Keys          auto-unseal, recovery keys, offline      │
  │ 2. Transport     TLS everywhere, mTLS on the cluster port  │
  │ 1. Access        policies, identities, least privilege     │  ← Modules 03–05
  └─────────────────────────────────────────────────────────┘
```

Layers 1 is what you built in Modules 03–05. This module builds 2 through 8.

> **Trade-off:** *Each layer costs something — CPU, latency, operational
> complexity, or a dependency you now have to keep alive. A transit
> auto-unseal seal means your "canary" cluster can now seal and unseal
> itself, but it also means that cluster can no longer be recovered if the
> transit cluster is destroyed. Every control in this module is a trade. The
> job is to know which trade you are making.*

---

## 3. Transport security: TLS, mTLS, and post-quantum TLS

### 3.1 The concept

**TLS** is a protocol that turns an HTTP connection into an encrypted,
authenticated one. Three things happen in the handshake:

1. The server presents a **certificate** proving it is who it claims to be.
2. The client (or the server, in mTLS) proves the same thing with a
   certificate of its own.
3. Both sides derive a **session key**, which encrypts everything after the
> handshake.

**Why it exists:** your OpenBao API is a secret dispenser. A token in a
header, a password in a JSON body — all of it is plaintext over HTTP. On
any shared network (a VPC, a Kubernetes service mesh, a corporate LAN), a
passive observer gets every secret Meridian AI stores.

**What breaks if you skip it:**

- The Gemini API key, the Postgres password, the Redis password, and the
  Keycloak client secret all cross the network in cleartext on every single
  request.
- An attacker with a packet capture on one pod-to-pod hop gets all of them.
- You will fail PCI-DSS 4.0 requirement 4.2.1 ("strong cryptography in
  transit"), and most enterprise SOC 2 audits as well.

**Transport security is table stakes.** A secret store over plain HTTP in
production is a mistake on day one and an incident report by month three.

### 3.2 The real listener configuration

This is the production shape of a `listener` block. Every field here has a
job:

```hcl
ui            = true
api_addr      = "https://bao-1.meridian-ai.internal:8200"
cluster_addr  = "https://bao-1.meridian-ai.internal:8201"

listener "tcp" {
  address     = "0.0.0.0:8200"
  cluster_address = "bao-1.meridian-ai.internal:8201"
  tls_disable = false

  tls_cert_file      = "/openbao/tls/tls.crt"
  tls_key_file       = "/openbao/tls/tls.key"
  tls_client_ca_file = "/openbao/tls/ca.crt"

  tls_min_version = "tls12"
  tls_max_version = "tls13"
}

storage "raft" {
  path           = "/openbao/file"
  node_id        = "bao-1"
  cluster_address = "https://bao-1.meridian-ai.internal:8201"
  raft_instance_id = "raft_node_1"
  api_addr        = "https://bao-1.meridian-ai.internal:8200"
  redis_node_api_address = ""
}
```

| Field | What it does | Get it wrong and… |
|---|---|---|
| `api_addr` | The **public** URL clients use. | Load balancers health-check the wrong address and mark the node down. |
| `cluster_address` (listener) | The address raft peers use to talk to each other — **`host:port`, no scheme**. | `Error resolving cluster_address: address https://…: too many colons in address`, and the node never joins. |
| `cluster_addr` (top level) | The cluster's advertised URL. **Required with `raft` storage.** | `cluster address must be set when using raft storage` — the server starts and then immediately exits. |
| `tls_cert_file` / `tls_key_file` | Server identity. | Clients get a hostname mismatch and refuse to connect. |
| `tls_client_ca_file` | **mTLS**: the CA allowed to issue client certs. | Anyone with a cert from that CA can connect — including your own broken CI. |
| `tls_min_version` | Floor on the negotiated TLS version. | TLS 1.0/1.1 clients are accepted. Remove them. |
| `storage "raft"` | Clustered storage. | See section 6. |

Before this config ever reaches a server, validate it. OpenBao ships a
config validator that parses the file the same way the server does:

```bash
$ bao operator validate-config -config=lab/config/openbao.hcl
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
[ success ] Validate Config
exit=0
```

And here is it catching a real mistake — `disable_mlock` is a **CLI flag**,
not a config field, and putting it in HCL is a classic copy-paste error
from older tutorials:

```bash
$ cat bad-config.hcl
ui = true
disable_mlock = true
storage "pebbledb" { path = "./data" }

$ bao operator validate-config -config=bad-config.hcl
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
[ warning ] Validate Config: Unknown or unsupported field disable_mlock found in configuration at bad-config.hcl:2:1.
exit=2
```

> **Honest limitation, verified in this lab:** `validate-config` is a
> *configuration-schema* check, not a *file-existence* check. I pointed it at
> a listener referencing `./certs/nope.crt` and `./certs/nope.key` and it still
> reported `[ success ]` with exit code 0. It will also happily accept
> `api_addr = "127.0.0.1:8200"` (missing scheme), which the server rejects
> at boot with `Error parsing synthesized cluster address ... invalid URI`.
>
> **Production:** *Treat `validate-config` as the first gate in CI, not the
> only one. It catches schema errors in seconds; it does not catch a missing
> certificate or a wrong hostname. Add a container start-up probe and a
> `curl --resolve` TLS smoke test to the same pipeline.*

### 3.3 mTLS: mutual TLS on the cluster port

**What is mTLS?** Normal TLS is one-way: the *server* proves its identity to
the client. **Mutual** TLS adds the reverse — the client proves its
identity to the server, with a certificate.

**Why it exists for the cluster port:** the raft cluster port (8201 by
default) is where nodes exchange *everything*, including the encrypted
storage entries and the seal configuration. If that port is reachable from
the general network, a hostile node can attempt to join your cluster and
receive a full copy of your storage. mTLS turns "the network is trusted"
into "only nodes holding a certificate signed by our raft CA can join."

**What breaks if you skip it:** any workload that can reach port 8201 can
try to join the cluster. Combined with a misconfigured `cluster_address`
and a permissive security group, this is a cluster-takeover path.

The pattern is a **separate CA** for the cluster, distinct from the
client-facing CA:

```hcl
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = false
  tls_cert_file      = "/openbao/tls/tls.crt"
  tls_key_file       = "/openbao/tls/tls.key"
  tls_client_ca_file = "/openbao/tls/ca.crt"
}

listener "tcp" {
  address     = "0.0.0.0:8201"
  cluster_address = "https://bao-1.meridian-ai.internal:8201"
  tls_disable = false
  tls_cert_file      = "/openbao/tls/raft-tls.crt"
  tls_key_file       = "/openbao/tls/raft-tls.key"
  tls_client_ca_file = "/openbao/tls/raft-ca.crt"
  tls_require_and_verify_client_cert = true
}
```

> **Production:** *Rotate cluster certificates **before** they expire, or
> lose quorum. A raft cluster where two of three nodes cannot present a
> valid client certificate is a dead cluster, and the surviving node cannot
> reach quorum to even tell you why. Set up expiry alerting on the cluster
> CA (section 9) — it is the highest-consequence certificate in the system.*

### 3.4 The certificate lifecycle

Certificates expire. A secrets store whose TLS cert silently expires is a
secrets store your applications cannot reach, at the worst possible moment.

Three ways to source certificates, best first:

| Source | How | Rotation | Use when |
|---|---|---|---|
| **OpenBao's own PKI engine** | OpenBao issues and renews its own certs | Automatic, `renew` job | You want one system of record |
| **cert-manager / Vault PKI** | cert-manager asks OpenBao's PKI engine for certs | Automatic | You run cert-manager already |
| **Static certs on disk** | Files mounted from a secret manager | Manual, painful | Never, in production |

The self-issued pattern, using the PKI engine from
[Module 06 — Crypto Tooling](../06-crypto-tooling/README.md):

> ⚠️ **Vault-era endpoint names, gone in 2.7.** *Vault's `pki/root/root/sign-one`
> and `pki/intermediate/sign-one` **do not exist** in OpenBao 2.7.1 — both
> return `404 unsupported path`. The 2.7 PKI engine generates keys and CSRs
> with `root/generate/internal` and `intermediate/generate/internal`, and
> signs them with `root/sign-intermediate` and `intermediate/set-signed`
> (see [Module 08 — Other Engines](../08-other-engines/README.md) §4.3 for
> the full walkthrough).*

```bash
# 0. Give the mount room for a long-lived root (the default maxTTL is 768h)
bao secrets tune -max-lease-ttl=87600h -default-lease-ttl=72h ai/pki

# 1. Root CA — self-signed, generated inside the mount
bao write -format=json ai/pki/root/generate/internal \
  common_name="Meridian AI Internal Root CA" \
  issuer_name="meridian-ai-pki-root" \
  ttl=87600h key_type=ec key_bits=521 \
  | tee root-bundle.json

# 2. Intermediate CA — generate a key + CSR, sign it with the root, import it
bao write -format=json ai/pki/intermediate/generate/internal \
  common_name="Meridian AI Issuing CA" \
  ttl=43800h key_type=ec key_bits=521 \
  | jq -r '.data.csr' > intermediate.csr

bao write -format=json ai/pki/root/sign-intermediate \
  csr=@intermediate.csr \
  common_name="Meridian AI Issuing CA" \
  ttl=43800h format=pem_bundle \
  | jq -r '.data.certificate' > intermediate.crt

# set-signed imports the intermediate as a NEW issuer — and imports it UNNAMED.
# The output tells you which one:
bao write ai/pki/intermediate/set-signed certificate=@intermediate.crt
#   imported_issuers    [cffd1dff-9447-10ad-cab9-eb536c318714]
#   mapping             map[80833732-...:fb631557-... cffd1dff-...:0efad69b-...]

# 3. Name it — and check the name took.
bao write ai/pki/issuer/cffd1dff-9447-10ad-cab9-eb536c318714 \
  issuer_name=meridian-ai-pki-intermediate

$ bao read -field=issuer_name ai/pki/issuer/cffd1dff-9447-10ad-cab9-eb536c318714
meridian-ai-pki-intermediate

# 4. Create the role that signs the leaf, pinned to that issuer
bao write ai/pki/roles/meridian-ai-pki-int \
  allowed_domains="meridian-ai.internal" allow_subdomains=true \
  max_ttl=8760h ttl=720h \
  key_type=ec key_bits=521 \
  issuer_ref=meridian-ai-pki-intermediate

# 5. Issue the server certificate
bao write ai/pki/issue/meridian-ai-pki-int common_name=bao-1.meridian-ai.internal \
  alt_names=bao-1.meridian-ai.internal,bao-2.meridian-ai.internal,bao-3.meridian-ai.internal \
  ttl=720h format=pem_bundle
```

> ⚠️ **Two things in that chain will bite you if you skip them.**
>
> **1. `issuer_name` on `root/sign-intermediate` is silently ignored.**
> Pass it and nothing happens — no warning, no error, the import succeeds:
>
> ```console
> $ bao write -format=json ai/pki/root/sign-intermediate \
>     csr=@intermediate.csr common_name="Meridian AI Issuing CA" \
>     issuer_name="meridian-ai-pki-intermediate" ttl=43800h format=pem_bundle \
>     | jq -r '.data.certificate' > intermediate.crt
> $ bao write ai/pki/intermediate/set-signed certificate=@intermediate.crt
>   imported_issuers    [cffd1dff-9447-10ad-cab9-eb536c318714]
> $ bao read -field=issuer_name ai/pki/issuer/cffd1dff-9447-10ad-cab9-eb536c318714
> (empty)
> ```
>
> The issuer comes in with **no name**. That is not cosmetic: a role's
> `issuer_ref` can only point at a *named* issuer, so an unnamed
> intermediate leaves you with no way to say "sign with the intermediate".
> Name it explicitly with `ai/pki/issuer/<id>`, exactly as step 3 does.
> ([Module 08 — Other Engines](../08-other-engines/README.md) §4.4 covers
> the issuer model and the same trap.)
>
> **2. The role has to exist before you can issue.** `ai/pki/issue/<role>`
> does not create the role for you. Point it at a role you never wrote and
> the server answers:
>
> ```console
> Error writing data to ai/pki/issue/meridian-ai-pki-int: Error making API request.
> Code: 500. Errors:
> * 1 error occurred:
> 	* could not fetch the CA certificate (was one set?): unable to find PKI issuer for reference: meridian-ai-pki-intermediate
> ```
>
> That error names the *issuer*, not the role, which is what makes it
> confusing: the role is missing **and** the issuer it points at is
> unnamed. Both are fixed above.

> **CLI gotcha:** *`bao write` prints a key/value table, not JSON, unless
> you ask for it. The `| jq -r '.data.certificate'` in step 2 only works
> because the write carries `-format=json` — and the flag has to come
> **before** the path, exactly like the `bao write -format=json` rule from
> Module 02. Without it, `jq` chokes on the table and writes an empty
> file, and the next command fails with a confusing certificate error.*

Then the **renewal job** — this is the pattern that keeps a TLS cert from
expiring at 3 a.m. on a Saturday:

```hcl
# lab/config/renewal.hcl — a second config file, loaded by the same server
storage "raft" { path = "/openbao/file" }

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = false
  tls_cert_file      = "/openbao/tls/tls.crt"
  tls_key_file       = "/openbao/tls/tls.key"
  tls_client_ca_file = "/openbao/tls/ca.crt"
}
```

The 2.7 release notes include **`tls_auto_reload`** — when the certificate
files on disk are replaced, the server picks up the new certificate without
a restart. Combine that with a renewal job that writes to the same path and
your TLS lifecycle becomes self-maintaining.

> **Production:** *Issue server certs with a short TTL (24–72h) from an
> intermediate CA, and rotate the root CA on a schedule you actually
> rehearse. A root CA you have never rotated is a root CA you have never
> tested the rotation of.*

### 3.5 Post-quantum TLS and ML-DSA (new in 2.7)

**What is the problem?** Classical TLS key exchange (ECDHE) and classical
signatures (RSA, ECDSA) are broken by a sufficiently powerful quantum
computer — Shor's algorithm. "Harvest now, decrypt later" makes this urgent
*today*: an adversary who can store your traffic can decrypt it in ten
years.

**What did 2.7 add?**

- **Pure-PQC TLS** — a post-quantum *key exchange* mode, configured with
  `tls_key_exchange_preferences`. In hybrid mode (the default posture) the
  session key is derived from **both** a classical KEX and a post-quantum
  KEX, so it is safe if *either* one survives.
- **ML-DSA (FIPS 204)** — post-quantum *signatures*, usable in the PKI
  engine, in Transit, and in TLS.

I confirmed the 2.7.1 binary actually contains these features — the
`tls_key_exchange_preferences` config key and the `ML-DSA` signature
implementation are both compiled in:

```bash
$ strings bao | grep -E 'tls_key_exchange|TLSKeyExchange'
xml:"preference"
json:"ssl_key_exchange"
json:"preferences,omitzero"
TLSKeyExchangePreferences"hcl:"tls_key_exchange_preferences"
```

And the ML-DSA implementation, with the FIPS 204 parameter sets:

```bash
$ strings bao | grep -oE 'mldsa-[0-9]+' | sort -u
mldsa-44
mldsa-65
mldsa-87
```

The `-44`, `-65`, `-87` are the three ML-DSA parameter sets (matching
Dilithium's security levels): **44** ≈ NIST category 2, **65** ≈ category
3, **87** ≈ category 5.

The listener shape:

```hcl
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = false

  tls_cert_file      = "/openbao/tls/tls.crt"
  tls_key_file       = "/openbao/tls/tls.key"
  tls_client_ca_file = "/openbao/tls/ca.crt"

  tls_min_version = "tls13"
  tls_max_version = "tls13"

  # Post-quantum key exchange (2.7+)
  tls_key_exchange_preferences = ["X25519MLKEM768"]
}
```

And ML-DSA key usage in Transit / PKI:

> ⚠️ **The spelling is not the same in the two engines — and neither one
> takes `ml-dsa-65`.** *OpenBao 2.7.1 rejects the hyphenated form in
> both places:*
>
> ```console
> $ bao write ai/transit/keys/meridian-ai-pqc type=ml-dsa-65
> Error writing data to ai/transit/keys/meridian-ai-pqc: Error making API request.
>
> URL: PUT http://127.0.0.1:9234/v1/ai/transit/keys/meridian-ai-pqc
> Code: 400. Errors:
>
> * unknown key type ml-dsa-65
> ```
>
> *The PKI engine is the same: `key_type=ml-dsa-65` gives
> `unknown key type ml-dsa-65`. The correct spellings are:*
>
> | Engine | Parameter | Value |
> |---|---|---|
> | **Transit** | `type` | `mldsa-65` (you name the level) |
> | **PKI** | `key_type` | `mldsa` (OpenBao picks ML-DSA-44) |

```bash
# Transit, ML-DSA key
bao write ai/transit/keys/meridian-ai-pqc \
  type=mldsa-65 \
  exportable=false \
  auto_rotate_period=720h

# PKI, ML-DSA key type  (note: pki/roles, plural)
bao write ai/pki/roles/meridian-ai-tls \
  key_type=mldsa \
  max_ttl=72h
```

> **CLI gotcha:** *`pki/role/<name>` (singular) is not a path in 2.7.1 —
> it returns `404 unsupported path`. The write path is **`pki/roles/<name>`**,
> plural, exactly like the KV v2 trap in Module 02.*

> **Scope of this lab.** This single-node, plain-HTTP lab has no TLS
> listener and no client to negotiate against, so **no pure-PQC handshake
> was run and no ML-DSA certificate was issued here.** What *is* verified
> is that both features exist in the 2.7.1 binary — the config key and the
> FIPS 204 implementation are in the executable. The *runtime handshake
> behavior* comes from the 2.7 release notes, not from a session in this
> module. Run it yourself before you depend on it:
>
> ```bash
> # on the OpenBao side
> bao operator validate-config -config=lab/config/openbao-tls.hcl
> # on the client side
> openssl s_client -connect bao-1:8200 -tls1_3 -groups X25519MLKEM768
> ```
>
> **Trade-off:** *Pure-PQC TLS costs extra CPU and larger handshakes
> (ML-KEM public keys are ~1 KB), and today it will break against clients
> that do not implement it. Hybrid mode is the pragmatic default: it is
> safe if the classical half is broken and it still works with every
> existing client. Enable pure-PQC only for the clients you control.*

### 3.6 The GUI for this module

Open <http://127.0.0.1:8200/ui> → **Status** shows the seal type and
storage backend. The GUI does **not** expose listener configuration — TLS
settings are file-level and require a restart.

| GUI | CLI equivalent |
|---|---|
| **Status** → seal type, storage type, HA enabled | `bao status` |
| **Status** → seal progress (shares needed) | `bao operator key-status` |
| *(not available)* | `bao operator validate-config -config=…` |
| *(not available)* | `bao operator diagnose -config=…` |

> **Why the CLI is primary here:** almost everything in this module is
> *server-level* configuration — listeners, seals, storage, audit devices.
> Those live in the config file and are not exposed in the UI at all.

---

## 4. Audit architecture

### 4.1 The CVE that changed the design

**What happened.** Before OpenBao 2.7, audit devices were created through
the API:

```bash
$ bao audit enable file file_path=./evil.log
```

In OpenBao 2.7.1 that command **fails**, and this is the whole point of
this section:

```bash
$ bao audit enable file file_path=./evil.log
Error enabling audit device: Error making API request.

URL: PUT http://127.0.0.1:9234/v1/sys/audit/file
Code: 400. Errors:

* cannot enable audit device via API; use declarative, config-based audit
  device management instead
exit=2
```

> **Note the port in that transcript:** the capture came from this lab's
> instance, which listens on a non-default port. Yours will print `8200`.
> The 400 and the `cannot enable audit device via API` body are the parts
> that matter.

**Why it matters.** The underlying issue is **CVE-2025-54997**
(HCSEC-2025-14). An administrator at the *API* level — a role you might
have handed to a platform team — could create an audit device pointing at
an arbitrary path on the host. That breaks the privilege separation the
whole product depends on: the API-level admin can no longer be assumed to
be less privileged than the operator who holds the config file. The
attacker writes a fake audit log, or fills a disk, or targets a sensitive
file, all with a legitimate-looking token.

**The fix:** audit devices become **declarative** — defined in the operator's
config file, like storage and listeners. The API cannot create them. The
config file is the trust boundary.

> **If you find a tutorial saying X:** *any tutorial that tells you to run
> `bao audit enable file …` is describing pre-2.7 behavior. On OpenBao 2.7
> that command errors out. The config stanza is the only supported path.*

### 4.2 The declarative stanza — and the three ways to get it wrong

The working syntax has **two labels** — a type and a name — plus an
`options` map:

```hcl
audit "file" "local-file" {
  description = "Local JSON audit log"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"
  }
}
```

That is the **Docker** path. When you run the repo's lab directly on the
host, the same stanza uses a relative path — `./logs/audit.log` — because
the lab's config file is `lab/config/openbao.hcl` and it is loaded from
inside `lab/`. The path is the only thing that changes; the structure of
the stanza is identical.

**The stanza needs BOTH labels AND an `options` map.** There are exactly
**three** ways to get it wrong, and I tested all three on 2.7.1 — because
the failure modes are *different*, and you need to recognise each one.

**Wrong #1 — one label only** (type, no name):

```hcl
# WRONG
audit "file" {
  file_path = "/openbao/logs/audit.log"
}
```

This one fails **loudly, at config-parse time**. The server refuses to
start. Here is the validator's verdict:

```bash
$ bao operator validate-config -config=onelabel.hcl
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
[ failure ] Validate Config: Could not parse configuration: error loading configuration from onelabel.hcl: error parsing 'audit': audit.0: audit type must be specified: &ast.ObjectItem{Keys:[]*ast.ObjectKey{*ast.ObjectKey{Token:token.Token{Type:9, Pos:token.Pos{Filename:"", Offset:199, Line:10, Column:7}, Text:"\"file\"", JSON:false}}}, Assign:token.Pos{Filename:"", Offset:0, Line:0, Column:0}, Val:(*ast.ObjectType)(0x2d92932c9260), LeadComment:(*ast.CommentGroup)(nil), LineComment:(*ast.CommentGroup)(nil)}.
exit=1
```

And the server itself, started with that same config, exits with the same
complaint and never reaches "OpenBao server started!":

```bash
$ bao server -config=onelabel.hcl
error loading configuration from onelabel.hcl: error parsing 'audit': audit.0: audit type must be specified: &ast.ObjectItem{...}
exit=1
```

**Wrong #2 — two labels, but no `options` map:**

```hcl
# ALSO WRONG
audit "file" "local-file" {
  description = "Local JSON audit log"
}
```

This one is nastier, because it **passes config validation** and only
fails later, when the server tries to bring the device up:

```bash
$ bao operator validate-config -config=twolabel-noopts.hcl
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
[ success ] Validate Config
exit=0
```

But the server log shows what really happened at unseal time:

```
[INFO]  core: adding new audit device: path=local-file/
[ERROR] core: post-unseal setup failed during init: error="failed to create new audit device local-file/: file_path is required"
```

…which leaves the server **sealed and unusable**, because `init` cannot
complete:

```bash
$ bao read sys/audit
Error reading sys/audit: Error making API request.

URL: GET http://127.0.0.1:9240/v1/sys/audit
Code: 503. Errors:

* Vault is sealed
```

**Wrong #3 — two labels, but `file_path` inline instead of inside `options`:**

```hcl
# THE NASTIEST ONE
audit "file" "local-file" {
  description = "Local JSON audit log"
  file_path   = "/openbao/logs/audit.log"
}
```

This is the one that will actually cost you an afternoon. The server
**starts normally**. There is no error, no exit code, no failed
`validate-config`. All you get is one line in the startup log:

```
2026-10-21T18:32:50.122Z [WARN]  unknown or unsupported field file_path
found in configuration at openbao.hcl:6:3
```

…and the device registers — but `file_path` never reached it, so the log
goes somewhere you did not choose (or nowhere useful at all). The server
looks healthy. `bao status` says unsealed. The only symptom is that your
audit log is missing.

**So the triage order is:** a hard config error → check the startup log
for `unknown or unsupported field` → and if the audit log is simply
absent, that WARN line is the reason. `bao audit list` will show the
device; `bao read sys/audit` will show its *resolved* options, which is
where the wrong path shows up.

> ⚠️ **A correction to our own ground truth.** An earlier draft of
> `VERIFIED-FACTS.md` §3 stated that a one-label
> `audit "file" { file_path = ... }` stanza *"parses without error and
> registers nothing"* — a **silent no-op** you would only notice because
> `bao audit list` came back empty.
>
> **That is not what OpenBao 2.7.1 does.** I tested all three malformed
> forms on this lab: the one-label form is a hard config error
> (`audit type must be specified`, exit 1, server refuses to start); the
> *two-label-without-`options`* form slips past the validator and then dies
> at unseal time with `file_path is required`; and the nastiest one — two
> labels with `file_path` inline instead of inside `options` — starts the
> server cleanly, logs only `[WARN] unknown or unsupported field file_path`,
> and silently writes its audit log somewhere you did not choose.
>
> **Practical consequence for you:** the "silent no-op" story is wrong, and
> that is *good* news — 2.7.1 fails loudly in both cases. But it means the
> failure you will actually hit in production is **wrong #2** (the one the
> validator waves through), and it will present as *a server that will not
> unseal*, not as *a missing audit device*. Know both signatures.

The live server, with the correct two-label-plus-`options` stanza in its
config, reports:

```bash
$ bao audit list
Path           Type    Description
----           ----    -----------
local-file/    file    Local JSON audit log
```

```bash
$ bao read sys/audit
Key            Value
---            -----
local-file/    map[description:Local JSON audit log local:false options:map[file_path:./logs/audit.log log_raw:false] path:local-file/ type:file]
```

Every field you need is in that one line: the device path
(`local-file/`), its type (`file`), the `local` flag, and the resolved
`options` map — including the `file_path` the server will actually write
to and the `log_raw` setting in force.

> **CLI gotcha, verified live:** do **not** add `-format=json` to that
> command. The `sys/audit` endpoint does not accept the flag, and the
> server tells you so in a `warnings` block alongside the payload:
>
> ```bash
> $ bao read sys/audit -format=json
> ...
>   "warnings": [
>     "Endpoint ignored these unrecognized parameters: [-format]"
>   ]
> }
> ```
>
> The endpoint returns JSON already. The same class of mistake is the
> `-format=json` vs `-f=json` trap from Module 02: on writes, `-f` means
> `--force`, not `--format`.

> **Production:** *After any config change, assert that the audit device
> exists — `bao audit list` must show at least one row, and `bao read
> sys/audit` must show a `file_path` inside the `options` map. In 2.7.1 a
> misconfigured audit stanza fails loudly rather than silently, but a
> *health check* that asserts the device is present still catches the
> case where someone edits the config and never restarts the node.*

> **Note on the transcript above:** the `file_path` shown is the **lab**
> path (`./logs/audit.log`), because that is what the running lab instance
> was configured with. In the Docker deployment it is
> `/openbao/logs/audit.log`. Everything else on that line — the device
> path, the type, the `local` flag, the `options` map, and `log_raw:false`
> — is exactly what you should see in production.

### 4.3 `log_raw` — the setting that decides whether your audit log is a liability

**What is `log_raw`?** It controls whether the audit log stores secret
values **in plaintext** (`true`) or **HMAC-hashed** (`false`).

**Why it exists:** an audit log is a record of *what happened*, and the
most useful record includes the values. But an audit log is also a file on
disk that gets shipped to a log aggregator, backed up, and read by
on-call engineers. If it contains plaintext secrets, your audit trail is
now a second copy of your secret store with none of the protections.

With `log_raw = "false"`, the server HMACs every sensitive value with a
key that never leaves the server. The audit log stays useful — you can see
that `ai/platform/llm/gemini` was read — without becoming a secret store.

Here is the real audit log from the live server, with `log_raw = "false"`:

```json
{
  "time": "2026-10-21T18:01:49.479515865Z",
  "type": "request",
  "auth": {
    "client_token": "hmac-sha256:a505f5e7384279cd68ebe6b274705c0b044da9ed5d9259cc5b255245985ae632",
    "accessor": "hmac-sha256:3c02a7cc4e32bc050fad21ce81eaca46f07819ffdba3f200f3c7d210cabb71ed",
    "display_name": "root",
    "policies": [
      "root"
    ],
    "token_policies": [
      "root"
    ],
    "policy_results": {
      "allowed": true,
      "granting_policies": [
        {
          "name": "root",
          "namespace_id": "root",
          "type": "acl"
        }
      ]
    },
    "token_type": "service",
    "token_issue_time": "2026-10-21T18:01:26Z"
  },
  "request": {
    "id": "41c7ef88-3ae7-3cb3-fa81-a9852a8c5921",
    "client_id": "0DHqvq2D77kL2/JTPSZkTMJbkFVmUu0TzMi0jiXcFy8=",
    "operation": "read",
    "mount_point": "sys/",
    "mount_type": "system",
    "mount_running_version": "v2.7.1+builtin.bao",
    "mount_class": "secret",
    "client_token": "hmac-sha256:a505f5e7384279cd68ebe6b274705c0b044da9ed5d9259cc5b255245985ae632",
    "client_token_accessor": "hmac-sha256:3c02a7cc4e32bc050fad21ce81eaca46f07819ffdba3f200f3c7d210cabb71ed",
    "namespace": {
      "id": "root"
    },
    "path": "sys/metrics",
    "data": {
      "format": "hmac-sha256:3a22be975ab14357883eace8ce40c9d4e0a7c5f52d808ef77fc8a94c34b5fccc"
    },
    "remote_address": "127.0.0.1",
    "remote_port": 45624
  }
}
```

Read it carefully. What is HMAC'd:

- `client_token` — the token, hashed.
- `accessor` — hashed.
- The `data` payload — every key and value hashed.

What is **not** hashed — and this is important, because it is what makes
the log useful for detection:

- `path` — you can see *which* secret was accessed.
- `operation` — read, write, list, delete.
- `remote_address` and `remote_port` — who connected.
- `http_status_code` — whether it was allowed.
- `policy_results.allowed` — which policy granted it.
- `display_name` and `policies` — which identity.
- `time` — when.

**That is exactly the right split.** You can alert on "who read the
Postgres password, from where, and was it allowed" without the log ever
containing the Postgres password.

> **Production:** *`log_raw = "false"` everywhere, always. The only
> legitimate use of `log_raw = "true"` is a short-lived forensic session
> where you must see the exact value — and even then, the log must be
> destroyed immediately afterwards. A `log_raw = "true"` audit device
> shipping to a shared SIEM index is a secret store with a public API.*

### 4.4 Shipping the audit log off-host

**The problem with a local audit file.** The audit log lives in
`/openbao/logs/audit.log`, on the same host as the OpenBao process. Anyone
who can write to that host — root, a container escape, a compromised
sidecar — can **edit or truncate** the log. The log is written by the
process you are trying to audit. It is evidence, but it is not
*immutable* evidence.

**The fix: two devices, two destinations.**

```hcl
audit "file" "local-file" {
  description = "Local JSON audit log (last resort, for crash forensics)"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"
  }
}

audit "syslog" "siem" {
  description = "Ship to the Meridian AI SIEM over TLS syslog"
  options = {
    facility  = "AUTH"
    log_level = "INFO"
    tag       = "meridian-openbao"
    use_journal = "false"
    socket_type = "tcp"
    address    = "siem.meridian-ai.internal:6514"
  }
}
```

**Why both?** The syslog device is your *immutable* copy — it lands in a
log aggregator that the OpenBao host's root user cannot retroactively
edit. The local file is your *fast* copy for debugging when the SIEM is
down and for forensics right after a crash.

**What to configure on the syslog side:** TLS to the collector
(`tls_ca_file`, `tls_client_cert_file`, `tls_client_key_file` on the
syslog device), a real facility, and a tag that lets your log pipeline
route OpenBao events into their own index. A shared `AUTH` facility with
no tag means your audit events are interleaved with every other system on
the network, and during an incident nobody can find them.

> **Trade-off:** *A syslog device adds a network dependency to every
> audited request. If the SIEM is unreachable, OpenBao's behavior depends
> on the device's `blocking` setting — a blocking device stalls API calls
> when the SIEM is down (availability risk), a non-blocking one drops audit
> records (evidence risk). There is no free option. The industry norm is
> non-blocking with a *local file device always enabled as the second
> sink*, so a SIEM outage degrades evidence coverage rather than taking the
> cluster down.*

### 4.5 What to alert on

The audit log is only useful if something reads it. Meridian AI's alerting
set, in priority order:

| Alert | Audit signal | Why it matters |
|---|---|---|
| **Secret read by a human** | `auth.token_type == "service"` vs `batch` mismatch, `display_name` in a known human set, `operation == "read"` on a `data/` path | A person reading a machine's secret is either a bug or a compromise. |
| **Reads from a new IP** | `remote_address` not in the known egress set for that identity | Credential theft from an unfamiliar host. |
| **Denied operations** | `response.data.error` non-empty, `http_status_code == 403` | Someone is probing what they cannot reach — a policy that is too tight *or* an attacker. |
| **Root token used** | `auth.policies` contains `root` | Production should have **no** root token. Any use is an incident. |
| **Policy change** | `path` starts with `sys/policy/`, `operation == "write"` | Someone is editing access control. |
| **Audit device change attempt** | `path` starts with `sys/audit/` | Should be *impossible* in 2.7 (see 4.1) — if you see it, you are on a vulnerable version or a different product. |
| **Seal / unseal** | `core: marked as sealed` in `server.log` | Unattended sealing is either a misconfiguration or an attack. |
| **Audit device failure** | `vault_audit_log_request_failure` metric rising (section 9) | Your evidence pipeline is broken and you do not know it. |

> **Production:** *Ship the audit log to a system with **retention you
> control** and **immutability you can prove**. "We have an audit log" is
> not a control. "An attacker with root on the OpenBao host cannot alter
> the audit trail, and we can prove that to an auditor" is a control.*

### 4.6 The GUI for this module

**The 2.7.1 UI has no audit screen.** I pulled the shipped UI bundle
(`/ui/assets/vault.js`) and grepped it: the only occurrences of "audit" are
the mount-tuning field names `auditNonHmacRequestKeys` and
`auditNonHmacResponseKeys`, and the string `sys/audit` **does not appear at
all**. No 2.7.1 build exposes audit devices in the UI, and the UI never
calls the endpoint.

**The CLI is the only way.** That is not a gap in the course — it is a
fact about the product, and it is worth knowing before an auditor asks
where the screen is:

| GUI | CLI equivalent |
|---|---|
| *(no such screen in 2.7.1)* | `bao audit list` |
| *(no such screen in 2.7.1)* | `bao read sys/audit` (shows the *resolved* `options` — this is where a wrong `file_path` shows up) |
| *(not available — 2.7 removed it)* | `bao audit enable file …` (now errors) |

---

## 5. Auto-unseal: Transit, recovery keys, and KMS

### 5.1 The concept

**What is unsealing?** OpenBao's data at rest is encrypted with a *root
key* (the "barrier key"). The root key is itself split into **unseal
shares** using Shamir's Secret Sharing. A quorum of shares reconstructs the
root key and decrypts the storage. Until that happens, the server is
**sealed** and every API call returns "server is sealed."

**Why auto-unseal exists:** in Shamir mode, a *human* must present shares
after every restart. In a container platform, "after every restart" means
after every pod eviction, every node drain, every deploy. If a human is
required, the secrets are unavailable exactly when you need them — and
people get tempted to automate the unseal key into a script or a
Kubernetes Secret, which puts the root key back in Git-like storage.

Auto-unseal replaces the human with a **cryptographic process**: OpenBao
wraps its root key with a key held somewhere else, and asks that other
system to unwrap it on every boot.

### 5.2 How Transit auto-unseal works

**Transit** is OpenBao's built-in encryption-as-a-service engine
([Module 06](../06-crypto-tooling/README.md)). The auto-unseal design
uses *two* OpenBao instances:

```
   ┌──────────────────┐         ┌──────────────────┐
   │  bao-app         │         │  bao-transit     │
   │  (your secrets)  │◄──TLS───│  (holds the KEK) │
   │                  │  unseal │  transit key     │
   │  root key       │  request│  never leaves    │
   │  (wrapped)      │─────────►│  this instance   │
   └──────────────────┘         └──────────────────┘
```

1. The transit instance holds a **named transit key** (the KEK).
2. The app instance's root key is **wrapped** by that transit key, and the
   wrapped blob is stored in the app instance's storage.
3. On boot, the app instance asks transit to **decrypt** the wrapped blob.
4. Transit returns the root key; the app instance is unsealed.

**Critically:** the transit key never leaves the transit instance, and the
root key never leaves the app instance's memory.

```hcl
# lab/config/openbao-transit-seal.hcl
storage "raft" {
  path           = "/openbao/file"
  node_id        = "bao-app-1"
  cluster_address = "https://bao-transit.meridian-ai.internal:8201"
  raft_instance_id = "raft_node_1"
  api_addr        = "https://bao-app-1.meridian-ai.internal:8200"
}

seal "transit" {
  address            = "https://bao-transit.meridian-ai.internal:8200"
  disable_renewal    = "false"
  wrapped_token      = "<wrapped-token>"
  mount_path         = "transit/"
  key_name           = "meridian-ai-unseal"
  namespace          = "root/"
}
```

### 5.3 The difference that matters: recovery keys

Here is the single most important distinction in this module.

| | **Shamir seal** | **Auto-unseal (Transit / KMS)** |
|---|---|---|
| Who unseals? | A human with shares | The process, automatically |
| Survives unattended restart? | ❌ No | ✅ Yes |
| **Recovery keys** | ❌ **None exist** | ✅ **You get them** |
| Recovery mechanism | The unseal shares *are* the recovery mechanism | A separate, independent quorum of recovery shares |
| Losing 2 of 3 shares | Total data loss, by design | Use recovery keys instead |
| KMS/KMS outage | n/a | Cluster stays sealed |

**The trap.** Module 01 documented this and it is worth restating here,
because auto-unseal is where people get it wrong:

```bash
$ bao operator init -key-shares=3 -key-threshold=2 \
      -recovery-shares=5 -recovery-threshold=3 -format=json | jq .recovery_keys_b64
null
```

`-recovery-shares` and `-recovery-threshold` are **auto-unseal only**. The
CLI help says it verbatim:

> `-recovery-shares=<int>` … *This is only used in Auto Unseal mode. The default is 5.*

**In Shamir mode there are no recovery keys. The unseal keys ARE the
recovery mechanism.** If you lose too many unseal shares, the data is
cryptographically unrecoverable. Not "hard to recover" — *unrecoverable*.
This is by design: a design that let you recover from losing the shares
would be a design where a single attacker could always get in.

**In auto-unseal mode, the recovery key is a separate key** from the
sealing key. It is protected by Shamir (5 shares, threshold 3 by default)
and it is the *only* thing standing between you and total loss if the
transit cluster is destroyed. **Back up the recovery keys. Then back them
up somewhere else.**

> **Production:** *If you use auto-unseal, you now have **two** critical
> secret sets: the transit key (held by the transit cluster) and the
> recovery keys (held offline by you). The recovery keys are the ones that
> will save you, because the transit cluster is the thing most likely to be
> destroyed in a bad day. Store them the same way you store the unseal
> shares in Shamir mode: sealed, offline, split, and rehearsed.*

### 5.4 The KMS seals (external plugins in 2.7)

**What is a KMS seal?** Instead of a second OpenBao, the KEK lives in a
cloud KMS (AWS KMS, GCP Cloud KMS, Azure Key Vault, Alibaba Cloud KMS, OCI
KMS) or a PKCS#11 hardware token.

**The 2.7 change you must know:** the KMS seals are **no longer built in**.
They moved to the `openbao-plugins` repository and are installed as
**external plugins**. From the verified plugin inventory on the live 2.7.1
server, the seal plugins you get out of the box are `shamir` and `transit`
only. `awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`, and
`pkcs11` are all external.

**The config shape for an external KMS seal** (conceptual — the exact
plugin name and options depend on which plugin you install):

```hcl
seal "awskms" {
  region     = "eu-west-1"
  access_key = "AKIA..."     # prefer env vars / instance roles
  secret_key = "..."
  mount_path = "awskms/"
  key_name   = "meridian-ai-unseal"
}
```

**What to check before you choose a KMS seal:**

| Question | Why it matters |
|---|---|
| Can the KMS be in the same failure domain as OpenBao? | If yes, a single AZ failure takes both down. |
| What happens if the KMS API is unreachable at boot? | The cluster stays sealed. Your KMS becomes a hard dependency. |
| Does the KMS support key deletion? | Some clouds let you schedule key deletion. If the key is gone, the data is gone. |
| Is there a key-policy that lets an attacker use the key? | A KMS decrypt grant is effectively unseal permission. |
| Does the KMS support rotation? | Key rotation invalidates the wrapped root key unless you re-wrap. |

> **Trade-off:** *A cloud KMS seal removes the "second OpenBao to operate"
> problem, and it puts the unseal key in a system with real HSM backing
> and real audit. But it also puts your ability to start Meridian AI's
> secret store behind a network call to a third-party API, and cloud KMS
> key policies are a new attack surface. A Transit seal against a
> separately-operated, separately-backed-up cluster keeps the whole thing
> in one product you understand.*

### 5.5 Auto-unseal and the runbook

Auto-unseal changes the incident runbook in section 11 in one important
way: **"the cluster is sealed" is no longer automatically an incident.**
With auto-unseal, a sealed cluster means the auto-unseal path is broken —
which is still an incident, but a different one, with a different runbook
(see 11.3).

---

## 6. High availability

### 6.1 Raft, and why it is the only clustered option in 2.7

**What is Raft?** A consensus algorithm. Every node keeps a full copy of the
storage; a quorum of nodes agrees on the order of writes; the cluster keeps
working as long as a majority is alive.

**Why it exists:** a single OpenBao node is a single point of failure. If
that node's disk dies at 02:00, Meridian AI's entire secret estate is
gone until you restore it.

**The 2.7 storage landscape — verified:**

| Backend | Status in 2.7.1 | Multi-node? |
|---|---|---|
| `file` | ❌ **Removed in 2.7.0** | n/a |
| `pebbledb` | ✅ New in 2.7.0 | ❌ **Refuses to run multi-node** |
| `raft` | ✅ Integrated | ✅ This is the HA backend |

> **If you find a tutorial saying X:** *any tutorial with `storage "file" { path = ... }`
> is describing pre-2.7 OpenBao (or HashiCorp Vault). That backend was
> removed in 2.7.0.*

**`pebbledb` refusing to run multi-node is a feature, not a bug.** It is a
split-brain guard: a second instance against the same data dir fails
loudly instead of corrupting the database.

I reproduced this directly: I pointed a second server at the data
directory the running lab instance already had open.

```bash
$ cat second.hcl
ui = true
api_addr = "http://127.0.0.1:9242"
listener "tcp" {
  address     = "127.0.0.1:9242"
  tls_disable = true
}
storage "pebbledb" {
  path = "/openbao/file"
}

$ bao server -config=second.hcl
2026-10-21T18:28:52.211Z [INFO]  proxy environment: http_proxy="" https_proxy="" no_proxy=""
error initializing storage of type pebbledb: failed to open database: resource temporarily unavailable
```

The second process dies on startup. It does **not** start, join, or
corrupt anything. The same error and the same wording also come out of
`bao operator diagnose` when it tries to open the same locked directory
(see section 9.4).

### 6.2 The three-node configuration

```hcl
# node 1
storage "raft" {
  path             = "/openbao/file"
  node_id          = "bao-1"
  cluster_address  = "https://10.20.1.11:8201"
  raft_instance_id = "raft_node_1"
  api_addr         = "https://10.20.1.11:8200"
}

# node 2 — same, node_id "bao-2", cluster_address "https://10.20.1.12:8201"
# node 3 — same, node_id "bao-3", cluster_address "https://10.20.1.13:8201"
```

Joining them — **these are the real 2.7.1 subcommands, but the output
below is the documented shape, not a transcript I captured.** I have not
run a multi-node cluster in this lab, and I am not going to paste a
session I did not produce:

```bash
# On node 2 and node 3, with the node-1 config in place:
$ bao operator raft join https://10.20.1.11:8201
```

```bash
$ bao operator raft list-peers
```

Both exist in the live binary — the full subcommand list, straight from
the 2.7.1 CLI:

```
$ bao operator raft -help
Subcommands:
    autopilot
    demote         Demotes a voter to a permanent non-voter
    join           Joins a node to the Raft cluster
    list-peers     Returns the raft peer set
    promote        Promotes a permanent non-voter to a voter
    remove-peer    Removes a node from the Raft cluster
    snapshot       Restores and saves snapshots from the Raft cluster
```

> **Scope of this lab.** This lab runs a **single node** with `pebbledb`
> storage, which by design refuses to cluster. The Raft configuration and
> the join procedure above are the standard OpenBao 2.7 raft topology, and
> the commands are the real 2.7.1 CLI subcommands — the live server's
> `bao operator raft -help` output above is the captured proof. **No
> 3-node raft cluster was run in this module**, so no cluster transcript
> is reproduced here. Build it on three VMs or three containers on
> separate networks before you rely on it.

### 6.3 Node counts and failure domains

**Odd numbers, always.** Raft needs a majority to commit. With 3 nodes you
can lose 1. With 4 nodes you can still only lose 1 — and now you pay for
the 4th node's cost and disk. With 5 nodes you can lose 2.

| Nodes | Tolerated failures | Verdict |
|---|---|---|
| 1 | 0 | Development only |
| 2 | 0 | **Worse than 1** — a single failure loses quorum |
| 3 | 1 | The standard minimum |
| 4 | 1 | No better than 3, more cost |
| 5 | 2 | Good for larger deployments |
| 7 | 3 | Diminishing returns; raft gets slower |

**Failure domains.** A failure domain is a set of nodes that can all fail
together. If `bao-1` and `bao-2` are both in the same Kubernetes node, the
same availability zone, or the same cloud region, they are not two nodes —
they are one node with a duplicate bill.

```
   ┌──────────── Availability Zone A ────────────┐
   │  bao-1 (voter)     bao-2 (voter)             │  ← BAD: both die together
   └──────────────────────────────────────────────┘

   ┌─── AZ A ───┐ ┌─── AZ B ───┐ ┌─── AZ C ───┐
   │  bao-1     │ │  bao-2     │ │  bao-3     │  ← GOOD: one AZ can fail
   └────────────┘ └────────────┘ └────────────┘
```

**Rule of thumb:** each voter in its own availability zone, its own host,
and ideally its own power/network path.

**Standby nodes.** A standby is a non-voting node that keeps a warm copy
and can be promoted to voter without a full rejoin. In 2.7, performance
standbys can even serve read requests (with `disable_standby_reads = false`
in the config).

> **Production:** *Three voters across three zones is the shape you want.
> Add a standby in a fourth zone as a hot spare if your RTO budget is
> tight — it survives a lost quorum because it can be promoted to restore
> the majority without a full data copy.*

### 6.4 The 2.7 PostgreSQL horizontal scalability

**What is it?** 2.7 adds the ability to run OpenBao's storage layer on
**PostgreSQL** and to use **read replicas** — so reads are served by
replicas rather than piling onto a single writer.

**Why it matters at scale:** Meridian AI's AI harness reads secrets
constantly. In a single-node raft cluster, every read hits the leader.
Horizontal scalability lets you add read capacity without adding raft
voters.

**The trade-off is real, and you should read the 2.7 release notes before
committing:**

| | Raft | PostgreSQL |
|---|---|---|
| Operational complexity | Low — one thing to run | Higher — Postgres, its backups, its replicas, its failover |
| Consistency | Strong, single writer | Depends on replication mode |
| Storage independence | ✅ Raft IS the storage | ❌ You now depend on Postgres being up |
| Scaling | Vertical (bigger disks) | Horizontal (read replicas) |

> **Scope of this lab.** The PostgreSQL storage backend was **not**
> exercised here — this lab runs `pebbledb`, and the 2.7.1 server reports
> `Storage Type pebbledb` in `bao status`. The feature is documented in
> the 2.7.0 CHANGELOG; the operational shape (DSN, replica configuration,
> failover behavior) is **not** reproduced from a live session in this
> module. Treat it as a scaling option to evaluate in a dedicated lab,
> not a default.
>
> **Trade-off:** *Postgres horizontal scaling trades operational
> simplicity for read throughput. A secret store is not a high-read
> workload unless you have thousands of pods; most teams should run raft
> and spend their complexity budget on unseal key management and audit
> shipping instead.*

---

## 7. Backups and restore

### 7.1 What a snapshot is — and what it is not

**What it is:** a byte-level copy of the storage backend, taken by the
cluster, at a point in time. For raft, the cluster creates a snapshot
entry, ships it to a follower, and that follower writes the file.

**What it is not:**

| Not included | Why it matters |
|---|---|
| The unseal/recovery keys | **A snapshot without keys is an encrypted blob you cannot read.** |
| The audit logs | Audit lives on disk, not in the storage backend. Back it up separately. |
| The config file | Where the listener, seal, and audit stanzas live. Back it up separately. |
| The PKI private keys in `pki/` | Actually *in* the snapshot (they're in storage), but they are the crown jewels of that snapshot — protect the snapshot accordingly. |

**The consequence, stated plainly:** a snapshot is the data. The unseal
shares are the ability to use the data. **You need both, and they must not
be stored in the same place.** A snapshot next to its unseal keys is not a
backup; it is a single encrypted container that anyone who finds it can
open.

### 7.2 Taking a snapshot

```bash
$ bao operator raft snapshot save ./backups/meridian-openbao-2026-10-21.snap
```

And the peer-side version, which you run on a *follower* so the leader
does the work and the follower writes the bytes:

```bash
$ bao operator raft snapshot save -format=json ./backups/snapshot.json
```

**⚠️ A trap I hit in this lab.** This lab's storage is `pebbledb`, not
`raft`. The raft snapshot endpoint does not exist there:

```bash
$ bao operator raft snapshot save ./backups/meridian-openbao.snap
Error taking the snapshot: Error making API request.

URL: GET http://127.0.0.1:9234/v1/sys/storage/raft/snapshot
Code: 404. Errors:

* 1 error occurred:
	* unsupported path

exit=2
```

> **Note the port in that transcript:** the capture came from the lab's
> instance, which listens on a non-default port. Yours will print
> `8200`. The 404 and the `unsupported path` body are the parts that
> matter.
>
> **What this means:** *`operator raft snapshot` is **raft-only**. If you
> are on `pebbledb` (the 2.7 default in the container image) you need a
> different backup method — filesystem-level backup of the data directory
> with the server stopped, or a storage-backend-specific dump. Do not
> assume a raft command works because the command name sounds general.*

### 7.3 The restore drill

A backup you have never restored is a hope, not a backup.

```bash
# 1. Stop the target cluster. A restore is destructive — it replaces the cluster state.
$ bao operator seal              # or stop the process entirely

# 2. Install the snapshot
$ bao operator raft snapshot restore ./backups/meridian-openbao-2026-10-21.snap
```

The restore endpoint is **force-restore**: it does not merge, it replaces.
After the restore, the cluster comes back **sealed** and you unseal it with
your shares (or it auto-unseals).

**The drill, quarterly:**

1. Provision a scratch cluster.
2. Install the snapshot.
3. Unseal with the **practice** shares.
4. Read a known secret: `bao kv get ai/platform/llm/gemini`.
5. Confirm the audit log contains the read.
6. Destroy the scratch cluster.

If step 3 fails, you have found the real bug — and it is always one of:
wrong shares, wrong seal type, or a snapshot taken from a different
cluster.

> **Production:** *Run the restore drill on a schedule and **record the
> date and the outcome**. "We have backups" is unverifiable. "We restored
> the 2026-10-01 snapshot into a scratch cluster on 2026-10-04 and read
> `ai/platform/llm/gemini` successfully" is verifiable — and it is the only
> thing that survives a real incident.*

### 7.4 The rule: back up data AND keys, to different places

This is the rule people skip, and skipping it is how secret-management
projects end.

**What you have to back up, in Meridian AI's case:**

| # | Artifact | Where it lives | Where the backup goes | How it is protected |
|---|---|---|---|---|
| 1 | Storage snapshot | Raft/pebbledb data dir | Encrypted S3 bucket, different account | S3 SSE + bucket policy |
| 2 | Unseal shares (Shamir) | Offline, printed | Sealed envelope, split between 3 people | Offline custody |
| 3 | Recovery keys (auto-unseal) | Offline, printed | Sealed envelope, split between 3 people | Offline custody |
| 4 | Config file | Git, `lab/config/` | Git history + a tagged release | Git signed tags |
| 5 | Audit logs | `/openbao/logs/audit.log` | SIEM (immutable) | Append-only index |
| 6 | TLS/raft CA + client certs | PKI engine / secret store | Re-issueable from the CA | PKI engine, offline root |

**The separation rule:** no single artifact in that table should be able to
read the snapshot on its own. Different bucket, different account, different
custodian, different access path. If a single person can walk away with
both the snapshot and the shares, you have one encrypted file, not a
defense in depth.

**The custody rule:** Shamir shares and recovery keys are split between
*people*, with a threshold. Meridian AI's reasonable design for 3
unseal shares / threshold 2:

| Share | Custodian | Location |
|---|---|---|
| Share 1 | Head of Platform | Company safe, Meridian City |
| Share 2 | Lead SRE | Company safe, London |
| Share 3 | External auditor | Escrowed, sealed |

Two of three must physically meet to unseal. That is the whole point of
Shamir.

> **Production:** *Print the shares. Paper does not get phished, does not
> get exfiltrated by a compromised CI runner, and does not get included in
> a `grep -r` of your repo. Store the printed shares in separate physical
> locations. Then rehearse the meeting — twice a year, with a timer, and
> without the keys present in any digital system.*

---

## 8. Container and runtime hardening

### 8.1 `mlock` — keep secrets out of swap

**What is it?** `mlock` tells the OS to never page a memory region to
disk. OpenBao uses it to keep the root key and the unseal key material in
RAM only.

**Why it exists:** the root key lives in memory. If it is swapped to disk,
it lands in a swap file, a hibernation image, or a core dump on a disk you
did not think of as sensitive. An attacker with the disk then has the root
key, and the root key decrypts everything.

**What breaks if you skip it:** you get a secret store that leaks its
master key to swap. On a cloud VM, swap is usually on a disk you manage.
In a container with no `IPC_LOCK` capability, `mlock` fails and OpenBao
**refuses to start** unless you pass `disable_mlock` — which is exactly
the trade: no swap protection, but it runs.

> **Production:** *Give the container the `IPC_LOCK` capability and keep
> `mlock` enabled. If your platform cannot grant `IPC_LOCK`, you are
> choosing an explicit, documented risk: disable swap on the host and
> disable hibernation, and record that in your risk register.*

### 8.2 `ulimit -c 0` — no core dumps

**What is it?** A core dump is a file containing a process's memory image,
written when the process crashes. It contains every secret the process
held, in plaintext.

**Why it exists:** a crash is a normal event. A crash *with core dumps
enabled* writes your root key to a file in the working directory, with the
permissions of the user running the process.

**What breaks if you skip it:** the first time OpenBao OOMs or hits a nil
pointer, you have written the secret store's master key to disk in a place
nobody is monitoring, and it is still there months later.

```yaml
# In the Compose file
command: ["server", "-config=/openbao/config"]
ulimits:
  core:
    soft: 0
    hard: 0
```

> **Production:** *`ulimit -c 0` is one line and it is not optional. A core
> dump is the single most common way a hardened secret store leaks its
> master key in the wild.*

### 8.3 The non-root requirement — and the `/openbao/file` quirk

**The image facts (OpenBao 2.7.1, `openbao/openbao:2.7.1`):**

| Fact | Value |
|---|---|
| Base | Alpine |
| Runtime user | `openbao` = **uid 100, gid 1000** |
| Default `CMD` | `server -dev -dev-no-store-token` |
| Entrypoint | `bao server -config=/openbao/config` (loads every `.hcl`/`.json` there) |
| Chowned by the entrypoint | `/openbao/config`, `/openbao/logs`, `/openbao/file` |
| **NOT** chowned | `/openbao/data` |
| `vault` binary | symlinked to `bao` |

**The quirk, and it will bite you.** The image's entrypoint chowns three
directories — `config`, `logs`, and `file` — and **aborts if the chown
fails** (`set -e`). It does **not** chown `/openbao/data`.

So:

- If you mount your data volume at **`/openbao/data`**, the volume is
  created root-owned, the server cannot write to it, and it **will not
  start**.
- If you mount it at **`/openbao/file`**, it is one of the three
  directories the image creates and manages, so a named volume inherits
  **uid 100**.

**To run truly non-root**, set `SKIP_CHOWN=true` (so the entrypoint does
not try to chown and abort) and pre-own the host directories yourself:

```bash
# On the host, before starting the container
sudo mkdir -p /srv/openbao/{file,logs,config}
sudo chown -R 100:1000 /srv/openbao
sudo chmod 700 /srv/openbao/file
```

**And the default command is not production.** The image's default `CMD` is
`server -dev -dev-no-store-token` — the **development** server: in-memory
storage, always unsealed, a random root token printed to stdout. A
production container must override it:

```yaml
command: ["server", "-config=/openbao/config"]
```

> **If you find a tutorial saying X:** *"the OpenBao container's root token
> is `root`"* describes HashiCorp Vault's dev server, not OpenBao 2.7.1.
> OpenBao 2.7.1's dev server generates a **random** root token and prints
> it on stdout. In the image, because the default CMD includes
> `-dev-no-store-token`, that token exists **only in the container's
> stdout**:
>
> ```bash
> $ docker logs meridian-openbao | grep -i "root token"
> ```

### 8.4 The full hardening posture

| Control | Flag | Why |
|---|---|---|
| Non-root | `user: "100:1000"` | Root in a container is root on the host if the runtime is misconfigured. |
| No new privileges | `security_opt: ["no-new-privileges:true"]` | Stops setuid binaries from escalating. |
| Drop all capabilities | `cap_drop: ["ALL"]` | The default capability set is far larger than needed. |
| Add back only what is needed | `cap_add: ["IPC_LOCK"]` | That is the only one `mlock` requires. |
| Read-only rootfs | `read_only: true` | The container cannot rewrite its own binaries. |
| No core dumps | `ulimits.core: 0/0` | See 8.2. |
| Drop the Linux capabilities | `cap_drop` | Done above. |
| Writable tmpfs | `tmpfs: /tmp` | Read-only rootfs needs a writable `/tmp`. |
| Pinned image | `image@sha256:…` | Tags move; digests do not. |

**The hardened Compose service:**

```yaml
services:
  openbao:
    image: openbao/openbao@sha256:<pin-the-digest-here>
    command: ["server", "-config=/openbao/config"]
    user: "100:1000"
    environment:
      SKIP_CHOWN: "true"
      BAO_ADDR: "https://openbao.meridian-ai.internal:8200"
    cap_drop:
      - ALL
    cap_add:
      - IPC_LOCK
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:size=64m,mode=1777
    ulimits:
      core:
        soft: 0
        hard: 0
      nofile:
        soft: 1048576
        hard: 1048576
    volumes:
      - ./config:/openbao/config:ro
      - ./certs:/openbao/tls:ro
      - openbao-file:/openbao/file
      - openbao-logs:/openbao/logs
    healthcheck:
      test: ["CMD", "/openbao/bin/bao", "status", "-format=json"]
      interval: 30s
      timeout: 5s
      retries: 3
    ports:
      - "127.0.0.1:8200:8200"
```

> **Note the `nofile` limit.** OpenBao's own diagnostic checks it, and the
> live server reports a very high value — which is the right shape:
>
> ```
> [ success ] Check Operating System
>   [ success ] Check Open File Limits: Open file limits are set to 1048576.
> ```
>
> A default `ulimit -n` of 1024 is a real production problem for a server
> that holds thousands of open files under load. It fails as connection
> errors that look like network problems.

> **Trade-off:** *`read_only: true` plus `SKIP_CHOWN=true` plus a
> pre-owned volume is more friction than the default. It is worth it: the
> default gives the container a writable root filesystem owned by root,
> which is one `docker exec` away from a full compromise of the host's
> writable layer.*

### 8.5 Pinning by digest

```bash
# Get the digest for the tag you intend to run
$ docker inspect --format='{{index .RepoDigests 0}}' openbao/openbao:2.7.1
openbao/openbao@sha256:<the full digest>    # get it with: docker inspect --format='{{index .RepoDigests 0}}' openbao/openbao:2.7.1
```

A tag like `2.7.1` is mutable — someone can repoint it. A digest is
immutable. If your supply chain is a review question, the answer is
digests, plus a scheduled job that re-resolves the tag and opens a PR when
it moves.

> **Production:** *Pin the digest in the Compose file **and** record which
> tag the digest corresponds to in a comment, so a human can tell what
> they are running without a registry round-trip.*

---

## 9. Monitoring

### 9.1 The metrics endpoint

OpenBao exposes Prometheus-format metrics. The live server, asked for
Prometheus format:

```bash
$ curl -s -H "X-Vault-Token: $BAO_TOKEN" \
    "http://127.0.0.1:8200/v1/sys/metrics?format=prometheus" | head -12
# HELP go_gc_duration_seconds A summary of the wall-time pause (stop-the-world) duration in garbage collection cycles.
# TYPE go_gc_duration_seconds summary
go_gc_duration_seconds{quantile="0"} 1.5714e-05
go_gc_duration_seconds{quantile="0.25"} 2.6915e-05
go_gc_duration_seconds{quantile="0.5"} 4.8555e-05
go_gc_duration_seconds{quantile="0.75"} 5.212e-05
go_gc_duration_seconds{quantile="1"} 5.212e-05
go_gc_duration_seconds_sum 0.000143304
go_gc_duration_seconds_count 4
# HELP go_gc_gogc_percent Heap size target percentage configured by the user, otherwise 100. This value is set by the GOGC environment variable, and the runtime/debug.SetGCPercent function. Sourced from /gc/gogc:percent.
# TYPE go_gc_gogc_percent gauge
go_gc_gogc_percent 100
```

**The endpoint is authenticated.** Without a token:

```bash
$ curl -s http://127.0.0.1:8200/v1/sys/metrics
{"errors":["permission denied"]}
```

Give the scraper a **dedicated, read-only, low-privilege token** with a
policy like:

```hcl
path "sys/metrics" {
  capabilities = ["read", "list"]
}
```

**Metric families on the live 2.7.1 server** (the `vault_*` ones — the
`go_*` and `process_*` families are the Go runtime and are also useful):

```
vault_audit_log_request            vault_audit_log_request_failure
vault_audit_log_response           vault_audit_log_response_failure
vault_audit_local_file__log_request vault_audit_local_file__log_response
vault_barrier_estimated_encryptions vault_barrier_get / _put / _delete / _list
vault_cache_hit                    vault_cache_miss          vault_cache_write
vault_core_active                  vault_core_unsealed
vault_core_in_flight_requests      vault_core_locked_users
vault_core_mount_table_num_entries vault_core_mount_table_size
vault_core_pre_seal                vault_core_post_unseal
vault_expire_num_leases            vault_expire_num_irrevocable_leases
vault_policy_get_policy
vault_runtime_alloc_bytes          vault_runtime_num_goroutines
vault_runtime_sys_bytes            vault_runtime_total_gc_runs
vault_seal_decrypt                 vault_seal_shamir_decrypt
vault_token_create                 vault_token_lookup
```

> ⚠️ **Not every family is exported from the first scrape.** *Some
> families only appear once the thing they count has happened — a fresh
> server has no `vault_token_create` until a token is minted, and no
> `vault_seal_decrypt`, `vault_core_pre_seal` or `vault_core_post_unseal`
> until it has been through a seal/unseal cycle. Scrape once, diff
> against the list you expect, and remember that "missing" often means
> "has not happened yet", not "does not exist".*
>
> *Also note the one-way naming: the seal counters are **`_decrypt`**,
> not `_encrypt` — `vault_seal_encrypt` and `vault_seal_shamir_encrypt`
> do not exist on 2.7.1, and neither does `vault_policy_list_policies`
> (only `vault_policy_get_policy`). Alert on what the server actually
> exports, not on what the name "should" be.*

### 9.2 The alerts that matter

| Alert | Expression | Severity | Why |
|---|---|---|---|
| **Cluster sealed** | `vault_core_unsealed == 0` | **Critical** | Every secret read fails. Meridian AI's platform is down. |
| **No active node** | `vault_core_active == 0` | **Critical** | The cluster has no leader. |
| **Audit device failing** | `rate(vault_audit_log_request_failure[5m]) > 0` | **Critical** | You are losing the evidence trail. |
| **Audit device silent** | `rate(vault_audit_log_request[15m]) == 0` | High | No requests logged at all — either no traffic or a broken device. |
| **Lease count climbing** | `vault_expire_num_leases` trending up | Medium | Leaked dynamic credentials. |
| **Token creation spike** | `rate(vault_token_create[5m])` | Medium | Token churn or a token-minting loop. |
| **Mount count changed** | `vault_core_mount_table_num_entries` | High | Someone enabled or disabled a secret engine. |
| **Encryption count** | `vault_barrier_estimated_encryptions` | Info | See the warning below. |
| **Goroutines growing** | `vault_runtime_num_goroutines` | Medium | A leak. |

> ⚠️ **A false alarm to avoid — the encryption count does NOT move on
> seal/unseal.** Verified on the live 2.7.1 server, twice:
>
> ```bash
> $ bao operator key-status
> Key Term            1
> Install Time        21 Oct 26 18:01 UTC
> Encryption Count    28
>
> $ bao operator seal
> Success! Vault is sealed.
> $ bao operator unseal "<share-1>"
> $ bao operator unseal "<share-2>"
>
> $ bao operator key-status
> Key Term            1
> Install Time        21 Oct 26 18:01 UTC
> Encryption Count    28
> ```
>
> The absolute number depends on how much work the instance has done
> (it rises as the server encrypts new data), so **do not hard-code a
> threshold against it**. What matters is that it is *unchanged across a
> seal/unseal cycle*. The common advice *"if the encryption count climbs,
> something is sealing your vault on a schedule"* is a guaranteed false
> alarm, because the number does not track seal cycles.
>
> **Use `vault_core_unsealed` and the `core: marked as sealed` line in
> `server.log` instead.**

### 9.3 A Prometheus rules file

```yaml
groups:
  - name: openbao
    rules:
      - alert: OpenBaoSealed
        expr: vault_core_unsealed == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "OpenBao cluster is SEALED"
          runbook: "https://wiki.meridian-ai.internal/runbooks/openbao-sealed"

      - alert: OpenBaoNoActiveNode
        expr: vault_core_active == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "OpenBao has no active node"

      - alert: OpenBaoAuditDeviceFailing
        expr: rate(vault_audit_log_request_failure[5m]) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "OpenBao audit device is failing - evidence is being lost"

      - alert: OpenBaoAuditDeviceSilent
        expr: rate(vault_audit_log_request[15m]) == 0
        for: 15m
        labels:
          severity: high
        annotations:
          summary: "No audit records written in 15 minutes"

      - alert: OpenBaoLeaseCountHigh
        expr: vault_expire_num_leases > 5000
        for: 10m
        labels:
          severity: medium
        annotations:
          summary: "OpenBao lease count unusually high"
```

### 9.4 The diagnostic command

When something is wrong and metrics are not enough, OpenBao has a
built-in troubleshooter:

```bash
$ bao operator diagnose -config=lab/config/openbao.hcl
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z

Results:
[ failure ] Vault Diagnose
  [ success ] Check Operating System
    [ success ] Check Open File Limits: Open file limits are set to 1048576.
  [ success ] Parse Configuration
  [ failure ] Check Telemetry: incomplete Stackdriver telemetry configuration, missing stackdriver_project_id
  [ success ] Check KMS Plugin Catalog
  [ failure ] Check Storage: Diagnose could not initialize storage backend.
    [ failure ] Create Storage Backend: error initializing storage of type pebbledb: failed to open database: resource temporarily unavailable
```

**Read that output carefully — every line is a lesson:**

- `Check Open File Limits: 1048576` → the `nofile` limit is right.
- `Check Telemetry: incomplete Stackdriver telemetry configuration` → the
  default telemetry config is only relevant if you use Stackdriver; a
  harmless *failure* line that teaches you the diagnostic is not
  context-aware.
- `Check KMS Plugin Catalog` → **this is where a missing external KMS
  plugin would show up.** Relevant to section 5.4.
- `Check Storage: … resource temporarily unavailable` → the storage
  backend is **locked by another process**. In this lab, that was the
  running server holding the pebbledb lock, and `diagnose` had to open the
  same database to test it. This is the same error you get when you try
  to start a second instance against the same data directory.

> **Production:** *Run `bao operator diagnose -config=…` as part of your
> deployment pipeline and on every alert. It is read-only, it is fast, and
> it answers most "why won't it start" questions in one shot.*

---

## 10. CI/CD: policies as code

### 10.1 The finding that changes your CI design

Here is the discovery that reshapes how you do policies-as-code, verified
on this lab's OpenBao 2.7.1 binary.

**`bao policy fmt` validates policies entirely client-side.** It needs no
server, no network, and no credentials. I proved it by pointing the CLI at
an **unreachable** address:

```bash
$ export BAO_ADDR="http://127.0.0.1:1"     # nothing is listening here
$ export -n BAO_TOKEN
$ bao policy fmt bad-policy.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": path
"ai/platform/data/llm/gemini": invalid capability "reed"
exit=1
```

And the good one:

```bash
$ bao policy fmt good-policy.hcl
Success! Formatted policy: good-policy.hcl
exit=0
```

**It catches real classes of error, with the same messages the server
produces.** Unknown top-level keys in a `path` block:

```bash
$ bao policy fmt bad-key.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": 1 error occurred:
	* invalid key "bananas" on line 3

exit=1
```

> **Note the line number.** *`bao policy fmt` reports the line inside
> **the file you passed it** — so `line 3` is only true for the policy
> exactly as it is written here. Change the file and the number moves
> with it. The message text is the stable part; the line number is
> per-file.*

Invalid keys inside a `control_group` block (the 2.7 approval feature):

```bash
$ bao policy fmt bad-cg.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": error handling control_group: 1 error occurred:
	* invalid key "not_bananas" on line 4

exit=1
```

**Why this matters more than it looks.** The obvious way to do
policies-as-code is: CI spins up an OpenBao container, logs in, and runs
`bao policy write`. That works, but it means:

- CI needs credentials to a real cluster, or to a throwaway one.
- A throwaway cluster needs unsealing, which needs unseal keys in CI.
- Unseal keys in CI is the exact anti-pattern this course has been
  avoiding since Module 01.

`bao policy fmt` sidesteps all of it. **Policy linting needs no server and
no credentials.** Your CI job downloads the `bao` binary, runs
`bao policy fmt` over `policies/*.hcl`, and fails the build on a bad
policy. Zero secrets in CI.

Note also that `bao policy fmt` **rewrites the file** into canonical
formatting when it succeeds — so it doubles as a formatter, and running
it in CI also detects formatting drift.

### 10.2 The GitHub Actions job

Meridian AI already uses GitHub Actions. Here is the policy-validation job,
and it is the *first* thing you should add:

```yaml
# .github/workflows/openbao-policy-lint.yml
name: openbao-policy-lint

on:
  pull_request:
    paths:
      - 'policies/**'
      - '.github/workflows/openbao-policy-lint.yml'
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install OpenBao CLI
        run: |
          curl -sSL -o bao \
            https://github.com/openbao/openbao/releases/download/v2.7.1/bao_2.7.1_linux_amd64.zip
          unzip -o bao && chmod +x bao && sudo mv bao /usr/local/bin/bao
          bao version

      - name: Validate every policy (no server, no credentials)
        run: |
          set -euo pipefail
          for p in policies/*.hcl; do
            echo "::group::$p"
            bao policy fmt "$p"     # rewrites the file in canonical format
            echo "::endgroup::"
          done

      - name: Fail if formatting drifted
        run: |
          if ! git diff --quiet -- policies/; then
            echo "::error::Policies are not canonically formatted. Run 'bao policy fmt policies/*.hcl' and commit."
            git --no-pager diff -- policies/
            exit 1
          fi
```

**Notice what is absent: no `secrets.*`, no `BAO_TOKEN`, no server.** The
`BAO_ADDR` is not even set. That is the point.

### 10.3 Applying policies — the second job

Validation is not application. Now the job that actually pushes policies
to the cluster. This one *does* need a credential, and the credential
should be narrow:

```yaml
# .github/workflows/openbao-policy-apply.yml
name: openbao-policy-apply

on:
  push:
    branches: [main]
    paths:
      - 'policies/**'

permissions:
  contents: read
  id-token: write          # if you use OIDC federation from Actions

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production   # ← protected environment, requires approval
    concurrency:
      group: openbao-policies
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4

      - name: Install OpenBao CLI
        run: |
          curl -sSL -o bao.zip \
            https://github.com/openbao/openbao/releases/download/v2.7.1/bao_2.7.1_linux_amd64.zip
          unzip -o bao.zip && chmod +x bao && sudo mv bao /usr/local/bin/bao

      - name: Federate into OpenBao (OIDC, no long-lived token)
        run: |
          export BAO_ADDR="https://openbao.meridian-ai.internal:8200"
          bao login -method=oidc \
            -role=github-actions-policy-applier \
            -auth-path=auth/oidc/github

      - name: Apply policies
        run: |
          set -euo pipefail
          for p in policies/*.hcl; do
            name="$(basename "$p" .hcl)"
            bao policy write "$name" "$p"
          done

      - name: Verify the applied policy matches Git
        run: |
          set -euo pipefail
          for p in policies/*.hcl; do
            name="$(basename "$p" .hcl)"
            bao policy read "$name" > "$RUNNER_TEMP/live-$name.hcl"
            # fmt rewrites the file in place, so the live copy is now canonical
            bao policy fmt "$RUNNER_TEMP/live-$name.hcl"
            if ! diff -u "$RUNNER_TEMP/live-$name.hcl" "$p"; then
              echo "::error::Policy $name drifted from Git"
              exit 1
            fi
          done
```

> **CLI gotcha, verified on this lab's 2.7.1 binary:** `bao policy fmt`
> does **not** read from stdin. `bao policy fmt -` fails with
> `Error reading source file: open -: no such file or directory` and exit
> code 1. It always wants a **file path**, and it rewrites that file in
> place with canonical formatting. To normalise a policy that is coming
> from somewhere else (a live policy read, a generated file), write it to
> a file first and then format the file.

> **Production:** *The drift check is the part that matters. Validation
> proves your Git policies are well-formed; drift detection proves the
> **running cluster** still matches Git. Without the second check, a
> well-formed policy change made directly against the cluster lives
> forever, and your "policies as code" is just "policies in a repo".*

The **drift check** at the end is what turns "we use policies as code" into
a *control*. If somebody changes a policy in the UI or with a hand-typed
`bao policy write`, the next deploy fails and the drift is visible.

> **Production:** *Use OpenBao's **OIDC** auth method for CI
> ([Module 05](../05-auth-mfa-oidc/README.md)) instead of a static
> `BAO_TOKEN` in GitHub secrets. A static token in CI is a long-lived
> credential in a place you do not control the blast radius of; an OIDC
> federation token is short-lived, scoped to one role, and revocable by
> un-binding the Actions OIDC subject.*

### 10.4 The secret-rotation job

Meridian AI has a `secret-rotation-bot` service. The GitHub Actions job
below is the *scheduled* half of rotation: it rotates the Gemini API key
and the database credentials, then commits the new KV version.

```yaml
# .github/workflows/secret-rotation.yml
name: secret-rotation

on:
  schedule:
    - name: Rotate platform secrets every 30 days
      cron: "17 3 1 * *"
  workflow_dispatch: {}

permissions:
  contents: write
  id-token: write

concurrency:
  group: secret-rotation
  cancel-in-progress: false

jobs:
  rotate:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Install OpenBao CLI
        run: |
          curl -sSL -o bao.zip \
            https://github.com/openbao/openbao/releases/download/v2.7.1/bao_2.7.1_linux_amd64.zip
          unzip -o bao.zip && chmod +x bao && sudo mv bao /usr/local/bin/bao

      - name: Authenticate (OIDC, short-lived)
        run: |
          export BAO_ADDR="https://openbao.meridian-ai.internal:8200"
          bao login -method=oidc \
            -role=github-actions-secret-rotator \
            -auth-path=auth/oidc/github

      - name: Rotate the Gemini API key
        run: |
          set -euo pipefail
          NEW_KEY="$(python3 scripts/request_gemini_key.py)"   # calls the Gemini console API
          CAS="$(bao read -field=current_version ai/platform/metadata/llm/gemini)"
          bao kv put -cas="$CAS" ai/platform/llm/gemini \
            api_key="$NEW_KEY" \
            rotated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

      - name: Rotate the Postgres credential
        run: |
          set -euo pipefail
          NEW_PW="$(python3 scripts/rotate_postgres_password.py)"
          CAS="$(bao read -field=current_version ai/platform/metadata/db/postgres)"
          bao kv put -cas="$CAS" ai/platform/db/postgres \
            password="$NEW_PW" \
            rotated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

      - name: Record the rotation in the audit trail
        run: |
          # sys/audit-hash/<device> is a real endpoint: it hashes the string
          # with that audit device's HMAC key AND writes an audit record.
          # The device name must match your config stanza (local-file here).
          bao write sys/audit-hash/local-file \
            input="rotation_id=${{ github.run_id }} actor=github-actions/secret-rotation"
```

> ⚠️ **There is no `sys/audit-test-marker` endpoint.** *A lot of
> runbook-shaped examples online use one. OpenBao 2.7.1 answers*
>
> ```console
> $ bao write sys/audit-test-marker rotation_id=123 actor=ci
> Error writing data to sys/audit-test-marker: Error making API request.
>
> URL: PUT http://127.0.0.1:9234/v1/sys/audit-test-marker
> Code: 404. Errors:
>
> * 1 error occurred:
> 	* unsupported path
> ```
>
> *The two endpoints that really exist are `sys/audit-hash/{device}`
> (hash a string with an audit device's key, and log the request) and
> `sys/audit/{device}` (read one device's resolved options). Use
> `sys/audit-hash/local-file` for a marker — it is a genuine audited
> request, so it shows up in the log with the path, the identity, and the
> source IP.*

**The important detail is the CAS value.** With `cas_required=true` on the
`ai/platform` mount (Module 02), every write needs a check-and-set value
or the server rejects it with `400 check-and-set parameter required`.

**`-cas=0` means "this secret must not exist yet"** — it is the value for
*creating* a secret, not for replacing one. Use it on an existing secret
and the job fails on every run after the first:

```console
$ bao kv put -cas=0 ai/platform/db/postgres password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
Error writing data to ai/platform/data/db/postgres: Error making API request.

URL: PUT http://127.0.0.1:8200/v1/ai/platform/data/db/postgres
Code: 400. Errors:

* check-and-set parameter did not match the current version
```

A rotation job that fails this way **rotates nothing and still reports
success to the scheduler** — the classic silent-failure rotation. Read
the current version and use *that* as the CAS value:

```console
$ bao read -field=current_version ai/platform/metadata/db/postgres
2
$ bao kv put -cas=2 ai/platform/db/postgres password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
Success! Data written to: ai/platform/db/postgres
```

That is also the concurrency guard you want: if somebody else wrote the
secret between your read and your write, the CAS value is stale and the
server refuses the write instead of silently clobbering them.

> **Trade-off:** *A scheduled rotation job is a *mechanism*. It is not a
> *rotation policy*. The policy is "the Gemini key rotates every 30 days
> and the old one is revoked at the provider within 24 hours of the new
> one being issued." Write the policy down, and make the job enforce it.
> A job that rotates the value in OpenBao while the old value stays valid
> at Gemini has created the illusion of rotation.*

---

## 11. The incident runbook

Four scenarios. Each one: **how you know**, **what you do**, and **what
you do afterwards**.

### 11.1 A credential leaked

**You know because:** the audit log shows a read of
`ai/platform/db/postgres` from an unexpected `remote_address`, or a token
in a GitHub secret scanner, or a scanner found it in a log.

```bash
# 1. Find every read of the secret, with who and from where
$ jq -r 'select(.request.path|test("^ai/platform/(data/|metadata/)?db/postgres$"))
         | "\(.time) \(.type) \(.request.operation) \(.request.path) \(.auth.display_name) \(.request.remote_address)"' \
    audit.log
2026-10-21T18:47:20.79281923Z request read ai/platform/data/db/postgres token-platform-operator 127.0.0.1
2026-10-21T18:47:20.792999919Z response read ai/platform/data/db/postgres token-platform-operator 127.0.0.1
2026-10-21T18:47:21.104559Z request read ai/platform/metadata/db/postgres token-platform-operator 127.0.0.1
2026-10-21T18:47:21.104771Z response read ai/platform/metadata/db/postgres token-platform-operator 127.0.0.1
```

> ⚠️ **Two details in that output will surprise you, and both matter
> during an incident.**
>
> **1. A KV v2 secret is reachable at three different paths, and only one
> of them is the value.** This is the single most important thing to know
> before you go grepping an audit log for a leak:
>
> | Path | What it is | In the audit log as |
> |---|---|---|
> | `ai/platform/db/postgres` | The **pre-v2 path**. OpenBao rejects it: `data: null` plus the warning *"Invalid path for a versioned K/V secrets engine…"*. It carries no secret — but it **is** still audited as a `read`. | `read` on `ai/platform/db/postgres` |
> | `ai/platform/data/db/postgres` | The **secret value**. This is the read that leaks. Writes land here too. | `read` / `create` / `update` on `ai/platform/data/db/postgres` |
> | `ai/platform/metadata/db/postgres` | The **metadata**: version list, timestamps, custom metadata. No secret value. | `read` on `ai/platform/metadata/db/postgres` |
>
> The bare path is the one that surprises people: it looks like the
> secret's address, it returns nothing, and it is *still* in the log. A
> query that only matches the bare path finds a request that read
> **nothing**. A query that only matches `data/` misses the metadata
> read. **Match on the pattern, not on the exact path** — and make sure
> the pattern covers all three forms, exactly as in the command above.
>
> > ⚠️ **A plain `startswith("ai/platform/db/postgres")` is not enough:**
> > `ai/platform/data/db/postgres` and `ai/platform/metadata/db/postgres`
> > do not start with that string. Use the alternation.
>
> **2. `auth.display_name` is the token's display name, not the policy
> that granted it.** `token-platform-operator` above is the display name
> of a token created with `-display-name=platform-operator` — OpenBao
> prefixes token display names with `token-`. If you did not set a display
> name, the field is literally `token`, and every identity in the log
> looks identical. **Set `-display-name` on every token you issue**, or
> your audit trail tells you nothing about *who* did what.

```bash
# 2. Revoke every token that could read it
$ bao list auth/token/accessors
$ bao write auth/token/revoke-accessor accessor=...     # one by one
```

```bash
# 3. Rotate the credential at the source (Postgres), not in OpenBao
$ bao write ai/database/rotate-role/meridian_app   # <mount>/rotate-role/<role-name>
```

**Order matters:** revoke the *access* first, then rotate the *value*.
If you rotate first, the leaked value is still live and the attacker
still has a window; if you revoke first, the leaked value is useless
even though it is still technically valid at Postgres.

**Afterwards:**
- Add the `remote_address` to a denylist / the CIDR bound on the role.
- Review the policy: why could that identity read that path at all?
- Rotate **every** secret in the same blast radius, not just the one that
  leaked. Assume the attacker enumerated.

### 11.2 Unseal shares lost

**You know because:** someone needs to unseal and does not have a quorum.

**The decision tree, and the order matters:**

```
        Do you have 2 of 3 Shamir shares?
                    │
          ┌─────────┴─────────┐
          │ YES               │ NO
          ▼                   ▼
   Unseal normally     ┌────────────────────────────┐
   (Shamir mode)      │ Is this an AUTO-UNSEAL      │
                       │ cluster (Transit/KMS)?      │
                       └────────────┬───────────────┘
                                    │
                      ┌─────────────┴──────────────┐
                      │ YES                        │ NO  ← Shamir mode
                      ▼                            ▼
              Use the RECOVERY keys          ┌──────────────────────────┐
              (Shamir mode has none)         │ RECOVERY IS THE SHARES.  │
              to reconstruct the root key,    │ If you have lost too many │
              then unseal manually.           │ unseal shares, the data  │
              ```                              │ is UNRECOVERABLE.        │
              bao operator generate-root \    │ This is by design.        │
                -init -otp=...                │                          │
              ```                              │ → Declare the loss.      │
                                               │ → Restore from SNAPSHOT  │
                                               │ (if you have one)        │
                                               │ → Restore from a NEW     │
                                               │   cluster and re-issue   │
                                               │   every secret.          │
                                               └──────────────────────────┘
```

> **The hard truth, verified in Module 01:** in Shamir mode
> `bao operator init -recovery-shares=5 -recovery-threshold=3` produces
> `null` for the recovery keys. There are no recovery keys. The unseal
> shares *are* the recovery mechanism. If you have lost too many of them,
> no tool can help you, and you restore from backup instead.

**The command that turns a Shamir-mode share loss into a root token**
(`generate-root`, verified in Module 01) — note that it still requires a
quorum of unseal shares, so it does **not** help if you have lost those:

```bash
$ bao operator generate-root -generate-otp
8BL7xUkLdWlcoY9WmPJBkP9F0Z
```

**Afterwards:** this is the moment to switch to auto-unseal, which gives
you a *second, independent* set of recovery keys. Also: check whether the
shares were "lost" or "stolen". Lost shares are an availability incident.
Stolen shares are a security incident, and the response is different —
you need to **rotate** the root key (`bao operator rotate-keys`, which
invalidates every old share) and re-unseal.

### 11.3 The cluster is sealed

**You know because:** `bao_core_unsealed == 0` fires, or every API call
returns `server is sealed`.

```bash
$ bao operator seal
Success! Vault is sealed.

$ bao status
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/2
Unseal Nonce       n/a
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

And the JSON form, which is what your monitoring should be reading:

```bash
$ bao status -format=json
{
  "type": "shamir",
  "initialized": true,
  "sealed": true,
  "t": 2,
  "n": 3,
  "progress": 0,
  "nonce": "",
  "version": "2.7.1",
  "commit_date": "2026-10-01T15:32:54Z",
  "migration": false,
  "recovery_seal": false,
  "storage_type": "pebbledb",
  "build_date": "",
  "ha_enabled": false
}
```

Note what the sealed server does to a *health check* — this is why your
load balancer must be configured to expect a 503 from a sealed node
rather than treating it as a crash loop:

```bash
$ bao read sys/health
Error reading sys/health: Error making API request.

URL: GET http://127.0.0.1:9234/v1/sys/health
Code: 503. Errors:
```

And note `Unseal Progress` — it climbs as you submit shares:

```bash
$ bao operator unseal "<share-1>"
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    1/2
Unseal Nonce       f63918d9-5316-a344-7278-b4e7ac4e2c31
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

> **Note the port in the health-check transcript:** the capture came from
> this lab's instance, which listens on a non-default port. Yours will
> print `8200`. The `503` is the part that matters.

**Is this a Shamir cluster or an auto-unseal cluster?** That single
question changes the runbook completely.

| | Shamir | Auto-unseal |
|---|---|---|
| Expected cause | A human did not unseal after a restart | The transit/KMS dependency is broken |
| Who acts | A human with 2 of 3 shares | The operator of the transit cluster |
| Time to restore | Minutes, if someone is awake | Depends on the transit cluster |
| Escalation | Page the on-call | Page the on-call **and** the transit owner |

**Shamir path:**

```bash
$ bao operator unseal "<share-1>"
$ bao operator unseal "<share-2>"
$ bao status
Key             Value
---             -----
Seal Type       shamir
Sealed          false
```

**Auto-unseal path:** check the transit cluster first. The `status` JSON
tells you which seal you are in — the `type` field changes from
`"shamir"` to `"transit"`, and `recovery_seal` tells you whether the
recovery key path is what is holding the cluster closed:

```bash
$ bao status -format=json | jq '{type, sealed, recovery_seal, storage_type}'
{
  "type": "transit",
  "sealed": true,
  "recovery_seal": true,
  "storage_type": "raft"
}
```

> That JSON block is the **shape** you should expect from an auto-unseal
> cluster; the transcript above it is the real one from this lab, which is
> Shamir-sealed. The `jq` projection is included because it is the exact
> query your runbook script should run.

Then check the transit instance's own health, its own seal state, and
whether the app instance's `seal "transit"` block is still pointing at a
live address. A common cause is a **transit key that was rotated or
deleted** — the app can no longer unwrap its root key.

**Afterwards:** find out *why* it sealed. `core: marked as sealed` in
`server.log` (from `server.log`, not the audit log) gives the reason.
Repeated unattended sealing is a configuration bug, and shipping
`disable_renewal = "true"` on a transit seal makes it worse — the app
cannot renew its wrapped token and will eventually fail to unseal.

### 11.4 A compromised admin token

**You know because:** the audit log shows `auth.policies` containing
`root`, or an unexpected `display_name` on privileged operations, or an
unknown source IP.

**Order of operations:**

```bash
# 1. Revoke the token's ACCESSOR — this kills it everywhere, immediately
$ bao write auth/token/revoke-accessor accessor=hg7c1...     # or:
$ bao token revoke -accessor ...

# 2. Find every other live token and check for surprises
$ bao list auth/token/accessors
```

```bash
# 3. If the root token itself is compromised, generate a NEW one
$ bao operator generate-root -generate-otp
Vg5PZU8j7N6yiPFgwoxVebYhR7

$ bao operator generate-root -init -otp="Vg5PZU8j7N6yiPFgwoxVebYhR7"
Nonce         e7432f68-49fb-f365-7033-31dc0cf86a2b
Started       true
Progress      0/2
Complete      false
OTP Length    26

$ bao operator generate-root -nonce="e7432f68-49fb-f365-7033-31dc0cf86a2b" \
    -otp="Vg5PZU8j7N6yiPFgwoxVebYhR7" "<unseal-key-1>"
Nonce       e7432f68-49fb-f365-7033-31dc0cf86a2b
Started       true
Progress    1/2
Complete    false

$ bao operator generate-root -nonce="e7432f68-49fb-f365-7033-31dc0cf86a2b" \
    -otp="Vg5PZU8j7N6yiPFgwoxVebYhR7" "<unseal-key-2>"
Nonce            e7432f68-49fb-f365-7033-31dc0cf86a2b
Started          true
Progress         2/2
Complete         true
Encoded Token    JUl3IzYAVzlWIgApJmNzLRYeTToXJB4/PmI

$ bao operator generate-root -decode="JUl3IzYAVzlWIgApJmNzLRYeTToXJB4/PmI" \
    -otp="Vg5PZU8j7N6yiPFgwoxVebYhR7"
s.BslUoSal6PO35Jaq5lrFGWlU
```

(The OTP, the nonce, and the resulting token are different on every run.
The `Encoded Token` value decodes to an `s.`-prefixed root token, exactly
like the one in the `bao status` output above.)

> **Note the port in the `generate-root` transcripts below:** the capture
> came from this lab's instance, which listens on a non-default port. Yours
> will print `8200`.

**One more trap, verified live in this lab.** If you start an attempt and
walk away, the next attempt is refused:

```bash
$ bao operator generate-root -init -otp="$OTP"
Error initializing root generation: Error making API request.

URL: PUT http://127.0.0.1:9234/v1/sys/generate-root-token/attempt
Code: 400. Errors:

* root generation already in progress for this namespace
```

Cancel it and start over:

```bash
$ bao operator generate-root -cancel
Success! Root token generation canceled (if it was started)
```

**And a final warning about the OTP.** It is an XOR key. Decode with the
*wrong* OTP and you get binary garbage, not an error:

```bash
$ bao operator generate-root -decode="JUl3IzYAVzlWIgApJmNzLRYeTToXJB4/PmI" \
    -otp="AAAAAAAAAAAAAAAAAAAAAAAAAA"
d6bwAx"cAhg"2lW_{Ve_~
```

If your decode step prints garbage instead of an `s.`-prefixed token, the
OTP is wrong — it is not a corrupted token.

**⚠️ Two gotchas from Module 01 that will bite you at 3 a.m.:**

- The **nonce must be passed on every subsequent call.** Without it:
  `Missing nonce value: specify it via the -nonce flag`. The CLI does
  **not** carry it forward.
- The output field is **`Encoded Token`** (two words) →
  `awk '/^Encoded Token/{print $3}'`. `Encoded Root Token` matches nothing.

**A crucial limitation:** `generate-root` **requires the same quorum of
unseal shares** as unsealing. It is a way to mint a new root token when
you *have* the shares; it is **not** a way around losing them.

**Afterwards:**
- Rotate every credential the compromised token could read. Enumerate
  them from the audit log, not from memory.
- If the token was a `platform-admin` service token, find out where it
  was stored and why (a Kubernetes Secret? an env var in a deployment?).
- If the attacker had root, assume the audit log on the host was edited.
  This is exactly why section 4.4 ships audit logs off-host.

---

## 12. Threat model

| Asset | Threat | Control | OpenBao mechanism |
|---|---|---|---|
| Gemini API key | Leaked in Git / logs | Never stored in Git; HMAC'd audit; rotation | KV v2 at `ai/platform/llm/gemini` + rotation job |
| Postgres password | Read from a compromised pod | Least-privilege policy; short-lived dynamic creds | Database engine `ai/database` + policy scoping |
| Redis password | Leaked via a config map | Secrets injected at runtime from OpenBao | KV v2 `ai/platform/cache/redis` |
| Keycloak client secret | Leaked by a service account | Scoped identity; token TTL; no long-lived tokens | AppRole / OIDC + `auth/token/roles` TTLs |
| Root key | Extracted from a swapped-out process | `mlock`; no core dumps; encrypted at rest | `mlock`, `ulimit -c 0`, `disable_mlock=false` |
| Unseal shares | Stolen from a laptop | Split custody, sealed envelopes, offline | Shamir shares, 2-of-3, offline custody |
| Recovery keys | Lost with a transit cluster | Separate offline custody, 3-of-5 | Auto-unseal recovery keys |
| Transit key | Compromised in the transit cluster | Separate cluster, separate operators, mTLS | `seal "transit"` + TLS |
| Storage snapshot | Stolen from a backup bucket | Different account + different bucket; keys not in the bucket | Raft snapshot + split custody of shares |
| Audit log | Edited by a host root | Ship off-host to an immutable sink | `audit "syslog"` device → SIEM |
| Audit log | Contains plaintext secrets | HMAC sensitive values | `log_raw = "false"` |
| Audit device | Created by an API admin to write to arbitrary host files | **Fixed in 2.7** — declarative only | `audit` stanza in config; CVE-2025-54997 |
| TLS traffic | Eavesdropped on the pod network | TLS on every listener; mTLS on the cluster port | `tls_cert_file`, `tls_client_ca_file` |
| TLS key | Intercepted in the future by a quantum adversary | Post-quantum KEX and signatures | `tls_key_exchange_preferences`, ML-DSA (2.7) |
| Admin token | Leaked and used | Short TTL; accessors; revoke on compromise | `auth/token/revoke-accessor`, `generate-root` |
| Policy | Weakened by a well-meaning admin | Policies in Git; CI applies and verifies drift | `bao policy fmt` + `bao policy write` in CI |
| Container | Escape to the host | Non-root, `cap_drop`, read-only rootfs, no-new-privileges | Image uid 100 / gid 1000; Compose hardening |
| Container filesystem | Tampered with in transit | Pin the image by digest | `image@sha256:…` |
| Storage | Corruption or disk loss | Raft replication + snapshots + restore drills | `storage "raft"`, `operator raft snapshot` |
| Availability | Sealed cluster takes the platform down | Auto-unseal + `vault_core_unsealed` alert | `seal "transit"`, Prometheus rule |
| Availability | Quorum loss | 3 voters across 3 failure domains + standby | Raft, odd node counts, standbys |
| Supply chain | Malicious dependency | No long-lived CI credentials; OIDC federation | OIDC auth method for CI |
| Insider | Reads secrets via a human token | Audit shows every read, with IP | Audit log + alerting on human reads |

---

## 13. The complete production checklist

### Transport
- [ ] TLS enabled on **every** listener (`tls_disable = false`)
- [ ] `tls_min_version = "tls12"`, `tls_max_version = "tls13"`
- [ ] mTLS on the **cluster** port with a **separate** cluster CA
- [ ] Server certs issued by an intermediate CA, TTL ≤ 72h
- [ ] Certificate renewal automated, with expiry alerting
- [ ] `tls_key_exchange_preferences` set to hybrid (2.7+)
- [ ] `api_addr` and `cluster_address` are full URLs with a scheme

### Audit
- [ ] Audit device declared in the **config file** (never via the API in 2.7)
- [ ] Two labels + an `options` map — verify with `bao audit list`
- [ ] `log_raw = "false"` on every device
- [ ] A **syslog/socket** device shipping to an off-host SIEM
- [ ] The SIEM sink is append-only and not writable by the OpenBao host
- [ ] Alerts on: audit failures, audit silence, root-token use, denied ops
- [ ] Retention defined and enforced by the SIEM, not by the host

### Keys and sealing
- [ ] Auto-unseal (Transit or KMS) so the cluster survives unattended restarts
- [ ] **Recovery keys** generated, split, and stored offline in a *different* place
- [ ] Unseal/recovery share custody documented and rehearsed
- [ ] Root token not persisted; break-glass via `generate-root` documented
- [ ] `bao operator rotate-keys` rehearsed

### Availability
- [ ] 3 (or 5) Raft voters, **odd**, one per failure domain
- [ ] A standby node in a fourth domain
- [ ] Snapshots on a schedule, stored off-host
- [ ] **Restore drill** performed and recorded at least quarterly
- [ ] Snapshot and keys stored in **different** accounts/buckets/custodians
- [ ] Config file, audit logs, and PKI roots backed up too

### Runtime and container
- [ ] Non-root (`user: "100:1000"`), `SKIP_CHOWN=true`, pre-owned volumes
- [ ] Data volume mounted at **`/openbao/file`**, not `/openbao/data`
- [ ] `command: ["server", "-config=/openbao/config"]` — **not** the dev default
- [ ] `mlock` enabled (container has `IPC_LOCK`)
- [ ] `ulimit -c 0`
- [ ] `cap_drop: [ALL]`, `cap_add: [IPC_LOCK]` only
- [ ] `no-new-privileges:true`
- [ ] `read_only: true` with a `tmpfs` for `/tmp`
- [ ] Image pinned by **digest**, not tag
- [ ] `nofile` limit raised to ≥ 100000
- [ ] A liveness probe that checks `sealed`, not just that the port is open

### Monitoring
- [ ] `/v1/sys/metrics?format=prometheus` scraped by a **read-only** token
- [ ] Alert on `vault_core_unsealed == 0` (critical)
- [ ] Alert on `vault_core_active == 0` (critical)
- [ ] Alert on `vault_audit_log_request_failure` (critical)
- [ ] Alert on audit silence (high)
- [ ] Lease-count and token-creation anomaly alerts
- [ ] `bao operator diagnose` wired into the deploy pipeline and into alerts
- [ ] Do **not** alert on the encryption count — it does not track seal cycles

### CI/CD
- [ ] All policies in Git under `policies/`
- [ ] `bao policy fmt` in CI — **no server, no credentials**
- [ ] Formatting drift fails the build
- [ ] Policies applied by CI with a **short-lived OIDC** credential
- [ ] A drift check that fails when the live policy differs from Git
- [ ] A scheduled rotation job with a documented rotation policy
- [ ] No long-lived tokens in GitHub secrets
- [ ] The workflow's `environment:` is protected and requires approval

### Access
- [ ] `default` policy is minimal (deny-by-default)
- [ ] The `root` token is never used by an application
- [ ] AppRole `secret_id` TTL is short; `num_uses = 1`
- [ ] CIDR bounds on roles
- [ ] Every identity is a named entity with a group
- [ ] Wrapping tokens used for one-shot secret delivery

### Operations
- [ ] Runbooks exist and are rehearsed: sealed cluster, leaked credential, lost shares, compromised token
- [ ] The on-call can reach the unseal shares within the RTO
- [ ] The "who holds which share" roster is current and known to the whole team

---

## 14. What you learned

- [ ] TLS belongs on every listener, and mTLS belongs on the cluster port.
- [ ] `tls_key_exchange_preferences` and ML-DSA exist in OpenBao 2.7.1, and the binary proves it.
- [ ] Audit devices are **declarative only** in 2.7 because of **CVE-2025-54997**; `bao audit enable` now errors.
- [ ] The `audit` stanza has **two labels AND an `options` map** — a one-label stanza is a
      hard config error, and a two-label stanza without `options` passes `validate-config`
      but then fails at unseal with `file_path is required`
- [ ] `log_raw = "false"` HMACs secret values while leaving paths, IPs, and status codes readable.
- [ ] An audit log on the host is evidence the host owner could edit; ship it off-host.
- [ ] Auto-unseal gives you **recovery keys**. Shamir mode gives you **none** — the unseal shares *are* the recovery mechanism.
- [ ] KMS seals are **external plugins** in 2.7, not built in.
- [ ] Raft needs an **odd** number of voters, each in its own failure domain.
- [ ] `pebbledb` refuses to run multi-node, on purpose; `file` storage was **removed** in 2.7.0.
- [ ] `operator raft snapshot` is **raft-only** — on `pebbledb` it 404s with `unsupported path`.
- [ ] A snapshot without its unseal shares is unreadable. Back up data **and** keys, separately.
- [ ] `mlock` and `ulimit -c 0` are not optional; a core dump is a plaintext key on disk.
- [ ] The OpenBao image is uid 100 / gid 1000, and the data volume belongs at **`/openbao/file`**.
- [ ] The image's default `CMD` is the **dev** server. Override it.
- [ ] `/v1/sys/metrics?format=prometheus` is authenticated; give the scraper a read-only token.
- [ ] The encryption count does **not** move on seal/unseal — do not alert on it.
- [ ] `bao operator diagnose` answers most "why won't it start" questions in one shot.
- [ ] `bao policy fmt` validates policies **client-side** — no server, no credentials. This is the correct CI shape.
- [ ] `bao operator validate-config` catches schema errors (exit 2) but **not** missing files.
- [ ] The runbook order for a leaked credential is **revoke access first, rotate the value second**.
- [ ] `generate-root` still needs a quorum of unseal shares; it is not a way around losing them.

---

## 15. What's next

You have now built the whole platform: OpenBao running, secrets in KV v2,
policies and namespaces, AppRole and OIDC identities, the Transit and PKI
engines, the application integration — and now the production hardening
that makes it survive contact with reality.

The natural next step is **disaster recovery**: proving that the
hardening works by actually restoring a snapshot onto a clean cluster,
sealing the original, and watching the applications fail and recover.
That is where the checklist in section 13 stops being a document and
becomes a fact.

---

## 16. Homework

1. **Audit the audit.** Set `log_raw = "true"` on a *second* audit device
   in a **scratch** instance, read `ai/platform/llm/gemini`, and diff the
   two log lines. Write down exactly which fields are HMAC'd and which are
   not. Then set it back to `"false"` and confirm the value is hashed.

2. **Prove the CI claim.** Write a two-file pair (one good policy, one
   with a bad capability) and run `bao policy fmt` against them with
   `BAO_ADDR` pointed at a dead port. Record the exact exit codes and the
   exact error text. Then wire it into a GitHub Actions workflow that has
   **no secrets in it at all**.

3. **Do the restore drill.** Create a `raft` cluster with three nodes
   (three containers on separate networks, or three VMs), write a
   distinctive secret, take a snapshot, destroy one node, and restore.
   Write down how long it took and what broke.

4. **Audit the container.** Pull `openbao/openbao:2.7.1`, inspect it
   (`docker inspect`), and answer: what is the default `CMD`, what user
   does it run as, which directories does the entrypoint chown, and which
   one does it *not*? Then write the hardened Compose service from
   section 8.4 and prove it starts with `read_only: true`.

5. **Write the seal-state Prometheus rules yourself** — without copying
   section 9.3 — and add one alert that is *not* about seal state. Defend
   your choice of expression in three sentences.

6. **Design the custody roster.** For Meridian AI's 3 unseal shares and 5
   recovery shares, name the custodians, the locations, and the meeting
   procedure. Then write down the RTO you are committing to and the two
   ways you would fail to meet it.

---

## 17. Meridian AI — the complete secrets architecture

Nine modules, one system.

```
                            ┌───────────────────────────────────────────────┐
                            │          Meridian AI Platform                 │
                            │   FastAPI · LangChain · Gemini · Postgres ·    │
                            │   Redis · Keycloak                           │
                            └───────────────────────────────────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     ▼                       ▼                       ▼
            ┌────────────────┐      ┌────────────────┐      ┌────────────────┐
            │   ai-harness   │      │ data-pipeline  │      │ secret-rotation│
            │    (FastAPI)   │      │                │      │      -bot      │
            └───────┬────────┘      └───────┬────────┘      └───────┬────────┘
                    │                       │                       │
                    └───────────┬───────────┴───────────┬───────────┘
                                │                       │
              AppRole login     │                       │  OIDC (CI)
         (role_id + secret_id)  │                       │
                                ▼                       ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │                        OpenBao  —  3-node Raft cluster                │
    │                                                                       │
    │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
    │   │   bao-1     │    │   bao-2     │    │   bao-3     │   + standby  │
    │   │ AZ-A        │    │   AZ-B      │    │   AZ-C      │   (AZ-D)     │
    │   │  voter      │    │  voter      │    │  voter      │   hot spare  │
    │   │ TLS :8200  │◄─►│ TLS :8200  │◄─►│ TLS :8200  │              │
    │   │ mTLS :8201 │◄─►│ mTLS :8201 │◄─►│ mTLS :8201 │              │
    │   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘              │
    │          │                  │                  │                     │
    │          └──────────────────┴──────────────────┘                     │
    │                             raft consensus                            │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐     │
    │  │  IDENTITY   [M04] [M05]   identity/entity · groups · aliases │     │
    │  │             AppRole  ai-harness-service                       │     │
    │  │             OIDC     Keycloak realm  meridian-ai             │     │
    │  │             OIDC     GitHub Actions (CI, no static tokens)    │     │
    │  │             Control Groups (2.7)  second-party approval       │     │
    │  └──────────────────────────────────────────────────────────────┘     │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐     │
    │  │  ACCESS     [M03]   policies: ai-harness · data-pipeline      │     │
    │  │                    · secret-rotation-bot · platform-operator   │     │
    │  │                    deny-by-default `default` policy           │     │
    │  │                    namespaces: tenant-alpha (isolated)         │     │
    │  └──────────────────────────────────────────────────────────────┘     │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐     │
    │  │  SECRETS    [M02] [M08]                                      │     │
    │  │   ai/platform/        kv-v2  cas_required · max_versions 10   │     │
    │  │     ├── llm/gemini        AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1m… │     │
    │  │     ├── db/postgres      Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK │     │
    │  │     ├── cache/redis      Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU │     │
    │  │     └── oidc/keycloak    meridian-ai-harness-client-secret-…  │     │
    │  │   ai/database/     dynamic Postgres + Redis creds (auto-exp) │     │
    │  │   ai/ssh/          SSH certs for the pipeline hosts          │     │
    │  └──────────────────────────────────────────────────────────────┘     │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐     │
    │  │  CRYPTO     [M06]   ai/transit   encryption-as-a-service     │     │
    │  │                      ai/pki      certs · ML-DSA (FIPS 204)   │     │
    │  │                      external keys via KMS (never in OpenBao)│     │
    │  └──────────────────────────────────────────────────────────────┘     │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐     │
    │  │  APP INTEGRATION [M07]                                      │     │
    │  │   ai-harness reads secrets at startup, caches with TTL,      │     │
    │  │   renews via kubelet 2.0 native sidecar                       │     │
    │  │   never writes a secret to disk, never logs one               │     │
    │  └──────────────────────────────────────────────────────────────┘     │
    └───────────────────────────────────────────────────────────────────────┘
              │                     │                    │                │
   ┌──────────┴──────┐   ┌──────────┴──────┐   ┌────────┴───────┐  ┌────┴─────────┐
   │  TRANSIT SEAL   │   │  AUDIT (declar.) │   │   METRICS      │  │  BACKUPS     │
   │  [M09]          │   │  [M09]          │   │  [M09]        │  │  [M09]      │
   │                 │   │                 │   │               │  │             │
   │  bao-transit    │   │ audit "file"    │   │ /v1/sys/metrics│  │ raft        │
   │  (separate      │   │   → local copy  │   │  prometheus    │  │  snapshot   │
   │   cluster,      │   │ audit "syslog"  │   │               │  │      ↓      │
   │   separate ops) │   │   → SIEM (immut)│   │ unsealed==0    │  │  encrypted  │
   │        │        │   │                 │   │ audit_failure  │  │     S3 (acct │
   │        │ KEK    │   │  log_raw=false  │   │ lease count    │  │      B)     │
   │        ▼        │   │  (HMAC'd)       │   │ token creation │  │      ↑      │
   │  wraps root key │   │                 │   │               │  │  UNSEAL     │
   │                 │   │  CVE-2025-54997 │   └───────────────┘  │  SHARES     │
   │  RECOVERY KEYS  │   │  → config-only  │                      │  (acct C,    │
   │  3-of-5, OFFLINE │   └─────────────────┘                      │   sealed,    │
   │  in a different  │                                           │   3 people) │
   │  place entirely  │                                           └─────────────┘
   └─────────────────┘
              │
              │  2.7: pure-PQC / hybrid TLS · ML-DSA · external keys
              ▼
    ┌───────────────────────────────────────────────────────────────────────┐
    │  RUNTIME HARDENING [M09]                                              │
    │  non-root (uid 100 / gid 1000) · cap_drop ALL + IPC_LOCK ·           │
    │  read-only rootfs · no-new-privileges · ulimit -c 0 · mlock on ·    │
    │  volume at /openbao/file · image pinned by digest · nofile ≥ 100000  │
    └───────────────────────────────────────────────────────────────────────┘
              ▲
              │  CI/CD [M09]
    ┌─────────┴───────────────────────────────────────────────────────────┐
    │  GitHub Actions                                                      │
    │   lint  : bao policy fmt      → NO server, NO credentials           │
    │   apply : OIDC federation     → short-lived, scoped, revocable       │
    │   rotate: scheduled 30d       → KV CAS write + provider-side revoke │
    │   drift : live vs Git diff    → fails the build                      │
    └─────────────────────────────────────────────────────────────────────┘
```

**One last thing.** The diagram has a deliberate asymmetry: the *soft*
parts — the keys, the policies, the drift checks, the runbooks — are the
parts that decay. The *hard* parts — TLS, Raft, mlock, non-root — break
loudly and get fixed. A vault that is cryptographically perfect and
operationally abandoned is still lost data. Harden the operations as
carefully as the cryptography, and rehearse both.

---

**Course complete.** You now have a secret store you could put in front of
a security review.

---

[← Module 08 — Other Engines](../08-other-engines/README.md)
· [Back to the course index](../../README.md)
