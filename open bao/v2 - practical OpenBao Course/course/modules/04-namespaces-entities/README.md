# Module 04 — Namespaces, Entities, Groups & Leases

> **Where we are.** Policies decide *what* a token can do. Namespaces decide
> *where* it can do it. Entities and groups decide *who* it is. Leases decide
> *how long* it lives. This module completes the mental model.

**Status: outline — full lesson in a later session.** Covers:

---

## 1. Namespaces — the multi-tenancy layer

A namespace is an isolated subtree of the whole OpenBao tree. Different
namespaces have **separate** mounts, policies, and auth methods.

```
/                       root namespace — Meridian AI platform team
/tenant-alpha/          a customer tenant
/tenant-beta/           another customer tenant
```

### Verified in the lab

```bash
$ bao namespace create tenant-alpha
$ bao namespace list
Keys
----
team-alpha/
tenant-alpha/

$ bao secrets list -namespace=tenant-alpha
Path          Type            Accessor              Description
----          ----            --------              -----------
cubbyhole/    ns_cubbyhole    cubbyhole_8516168c    per-token private secret storage
identity/     ns_identity     identity_380e86ce     identity store
sys/          ns_system       system_3e961018       system endpoints used for control, policy and debugging

$ bao secrets enable -namespace=tenant-alpha -path=ai/tenant kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/tenant/

$ bao secrets list | grep tenant
   (nothing — correctly isolated from the root namespace)
```

### Key points
- Each namespace has its **own** `sys/` — its own policies, its own tokens.
- A root-namespace token cannot see into a child namespace unless the
  policy explicitly grants it.
- 2.6 added **per-namespace sealing** — a tenant can revoke the operator's
  access to their own namespace without affecting others.
- 2.7 added **Control Groups** — second-party approval on sensitive paths.

**When to use namespaces:** true multi-tenancy (each customer isolated), or
hard compliance boundaries (PCI scope, per-legal-entity separation).

**When NOT to:** ordinary team separation. Use **paths + policies** for
that. Namespaces are heavier and you can't easily undo one.

---

## 2. Entities — a stable identity for a human

An **entity** is the canonical identity record. It survives token
expiry, device changes, and service restarts. Auth methods create
**aliases** pointing at the entity.

```bash
$ bao write identity/entity name=ai-harness-service
{
  "data": {
    "aliases": null,
    "id": "f64762f9-f70b-8446-aa23-7d14f893cccb",
    "name": "ai-harness-service",
    ...
  }
}

$ bao list identity/entity/name
Keys
----
ai-harness-service
entity_a72925d7.root
```

**Why this matters:** if `aisha.rahman` logs in via OIDC today and
userpass tomorrow, she is the **same entity** with two aliases. Her
group memberships and her audit trail stay continuous. Without entities,
every auth method creates an unrelated identity.

⚠️ Note the path: `identity/entity`, **not** `auth/token/identities/entity`
(which returns 404 in 2.7).

---

## 3. Groups — the unit of authorization

A group is a named set of entities. Policies attach to groups, not people.
When someone joins or leaves the team, you change one membership, not
twelve policies.

**Meridian AI's model:**
- `platform-team` → `platform-operator` role
- `security-team` → `platform-admin` role
- `ai-service` → machine identity for the harness

---

## 4. Leases — the lifecycle of a credential

A **lease** is OpenBao's record of a time-bound credential. Every token
and every dynamic secret is a lease.

### The lease lifecycle
```
created ──► active ──► renew (TTL extends) ──► active
               │
               └──────► expired (auto-revoked) or revoked (manual)
```

### Verified in the lab
```bash
$ bao token create -policy=ai-harness-service -ttl=30m -format=json
{
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "auth": {
    "client_token": "s.meXfjPDEJZaxXXq07DN8erxl",
    "lease_duration": 1800,
    ...
  }
}
```

Note: in 2.7 the **token's own TTL** lives in `auth.lease_duration`, while
the top-level `lease_id`/`lease_duration` fields are reserved for
*dynamic* secrets (database creds, PKI certs).

### ⚠️ Lease endpoint changes in 2.7 (breaking)

The legacy endpoints were **removed** for cross-namespace lease-revocation
safety (CVE-2026-45808):

| Endpoint | 2.7 status |
|---|---|
| `sys/renew` | ❌ **404 — removed** |
| `sys/revoke` | ❌ **404 — removed** |
| `sys/revoke-prefix` | ❌ **404 — removed** |
| `sys/revoke-force` | ❌ **404 — removed** |
| `sys/leases/renew` | ✅ use this |
| `sys/leases/revoke` | ✅ use this |
| `sys/leases/lookup` | ✅ use this |
| `sys/leases/revoke-prefix` | ✅ use this |
| `sys/leases/count` | ✅ use this |

**Use `bao token revoke`, `bao token renew`, and `bao write sys/leases/...`
— the CLI already targets the new endpoints.**

---

## 5. Why leases matter operationally

- **Automatic expiry** — a leaked token dies on its own.
- **Renewal with a cap** — `token_max_ttl` prevents indefinite extension.
- **Revocation by prefix** — kill every token for one service at once:
  ```bash
  bao write sys/leases/revoke-prefix prefix=ai/platform
  ```
- **Counting** — `bao write sys/leases/count` tells you how many live
  credentials exist. A sudden spike is an incident signal.

---

**Next:** [Module 05 — Auth Methods, MFA & OIDC](05-auth-mfa-oidc/)
