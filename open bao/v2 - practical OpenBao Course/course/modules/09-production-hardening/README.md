# Module 09 — Production Hardening

> **Where we are.** The lab works. Now we make it something you'd be
> comfortable running Meridian AI's production secrets on.

**Status: outline — full lesson in a later session.**

---

## 1. TLS — non-negotiable

The lab uses `tls_disable = true` for learner sanity. Production:

```hcl
listener "tcp" {
  address            = "0.0.0.0:8200"
  tls_cert_file      = "/openbao/tls/tls.crt"
  tls_key_file       = "/openbao/tls/tls.key"
  tls_client_ca_file = "/openbao/tls/ca.crt"
  tls_min_version    = "tls12"
  tls_max_version    = "tls13"
}
```

2.7 adds **pure post-quantum TLS** (`tls_key_exchange_preferences`) and
**ML-DSA certificates**.

---

## 2. Audit devices — declarative only in 2.7

```hcl
audit "file" "local-file" {
  description = "Local JSON audit log"
  options = {
    file_path = "/openbao/logs/audit.log"
    log_raw   = "false"    # HMAC sensitive values
  }
}
```

⚠️ `bao audit enable` **no longer works** in 2.7:
```
* cannot enable audit device via API; use declarative, config-based
  audit device management instead
```

This was a deliberate security change (CVE-2025-54997). API-driven audit
creation let an API-level admin write to arbitrary host files. The fix
moves the audit lifecycle into the operator-controlled config file.

**Verified in the lab** — secrets are HMAC'd, not plaintext:
```json
"api_key": "hmac-sha256:99573bf8d5f6f359999ebb2e953a1b1994fdc3dc6d9..."
```

**Production:** ship audit logs off-host (syslog / socket to a SIEM), keep
them append-only, and alert on the seal state.

---

## 3. Auto-unseal — surviving restarts unattended

The lab uses Shamir. Production wants **Transit auto-unseal**, which also
gives you **recovery keys** (Shamir mode has none — Module 01).

```hcl
seal "transit" {
  address       = "https://bao-transit.internal:8200"
  disable_renewal = "false"
  wrapped_token = "<wrapped>"
}
```

Then `bao operator init` returns recovery keys instead of unseal keys.

**Also 2.7:** KMS seals are now **external plugins**, and there's a
`kms` plugin type in the config for auto-unseal.

---

## 4. High availability

```hcl
storage "raft" {
  path = "/openbao/data"
  node_id = "bao-1"
  cluster_address = "https://10.0.1.11:8201"
  raft_instance_id = "raft_node_1"
  api_addr = "https://10.0.1.11:8200"
}
```

- 3 or 5 nodes, **odd**, spread across failure domains.
- 2.7 adds **PostgreSQL horizontal scalability** (read replicas).
- `pebbledb` deliberately refuses to run multi-node — a safety feature.

---

## 5. Storage backups

```bash
bao operator raft snapshot save -format=json /backup/openbao-snapshot.json
```

⚠️ A snapshot contains **encrypted** data, but you still need the unseal
keys to read it. Back up **both**, to **different places**.

---

## 6. Container & process hardening

- `mlock` (needs `IPC_LOCK`) — keep secrets out of swap
- `ulimit -c 0` — no core dumps
- Non-root user (`USER meridian`)
- `cap_drop: ALL` + only `IPC_LOCK`
- `no-new-privileges:true`
- `read_only: true` filesystem where possible
- Pin image digests, not tags

---

## 7. CI/CD — policies as code

Store policies in Git, apply them in CI. `lab/policies/*.hcl` is the
starting point. A pipeline that fails when a policy drifts from Git is
worth more than any documentation.

---

## 8. The production checklist

- [ ] TLS on all listeners, mTLS on the cluster port
- [ ] Auto-unseal with Transit + recovery keys stored offline
- [ ] 3+ node Raft cluster across failure domains
- [ ] Audit device declared in config, shipping off-host
- [ ] `default` policy kept minimal
- [ ] No long-lived root token; break-glass via `generate-root`
- [ ] AppRole `secret_id` short TTL, bound CIDRs, `num_uses=1`
- [ ] All policies in Git, applied by CI
- [ ] Snapshots scheduled + restore tested
- [ ] Monitoring on seal state, audit health, lease counts
- [ ] `bao status` alerting on `sealed=true`

---

**Course complete.** 🎉
