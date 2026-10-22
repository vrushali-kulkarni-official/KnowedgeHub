# Module 03 — Policies & ACLs: Least Privilege

> **Where we are.** Right now the root token can read everything, and every
> token we mint can read everything. That's a store where a single leaked
> credential = full compromise. This module makes Meridian AI's OpenBao
> actually safe to share.

**Status: outline — full lesson in the next session.** This module covers:

---

## 1. How OpenBao authorization actually works

Three inputs, evaluated in order:

1. **The path** being accessed (e.g. `ai/platform/data/llm/gemini`)
2. **The token** making the request (which carries a set of policies)
3. **The policies** attached to that token (each with path→capability rules)

The request is allowed if **any** policy grants the required capability.
There is no "deny" rule — **absence of a grant is the deny.** This is a
critical mental model: you write allow-rules, and everything else is
implicitly forbidden.

### The capability verbs

| Capability | Meaning | KV v2 example |
|---|---|---|
| `read` | Read the value | Read `ai/platform/data/llm/gemini` |
| `list` | List child paths | List `ai/platform/metadata/llm` |
| `create` | Create a new key | First write of a secret |
| `update` | Modify an existing key | Rotate a secret |
| `delete` | Soft-delete (KV v2) | `bao kv delete` |
| `sudo` | Privileged operations | Unseal, `generate-root`, policy authoring |
| `deny` | Explicitly block | `capabilities = ["deny"]` |
| `root` | Everything | Only the `root` policy |

---

## 2. The three policies that always exist

### `default`
Attached to every token by default. In OpenBao 2.7 it is **minimal**:

```hcl
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/renew-self" { capabilities = ["update"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
path "identity/entity/id"    { capabilities = ["read"] }
```

**Production recommendation:** keep it minimal. Many teams disable it
entirely for machine tokens with `-no-default-policy` so that a policy
mistake fails loudly rather than silently granting a standard path.

### `root`
Unrestricted. **Never attach it to a long-lived token.** It exists for
bootstrap and break-glass.

### Your own policies
Everything else. This is where all the real work is.

---

## 3. Writing Meridian AI's policies

Already applied in `lab/policies/`. The five roles:

| Policy | For | Can read | Can write |
|---|---|---|---|
| `ai-harness-service` | The FastAPI app | Gemini key only | ❌ |
| `data-pipeline-service` | ETL job | Postgres + Redis | ❌ |
| `secret-rotation-bot` | Rotation cron | LLM + DB paths | ✅ (not destroy) |
| `platform-operator` | Humans via OIDC | Everything (read+list) | ❌ |
| `platform-admin` | Humans, admin | Everything | ✅ (no `sudo`) |

**The separation of read from write is the single most important pattern
here.** It means:

- A compromised *reader* (the AI harness) can exfiltrate secrets but cannot
  corrupt them.
- The *writer* (rotation bot) is a scheduled job, tightly scoped, and
  auditable.
- A human admin can fix things but cannot silently rotate the Gemini key.

---

## 4. The `sudo` capability — your break-glass switch

`sudo` is what separates "can administer" from "can administrate the vault
itself". Operations that require `sudo`:

- `sys/seal`, `sys/unseal`
- `sys/generate-root-token`, `sys/rotate/*`
- `sys/policy` (writing policies)
- `sys/audit` (enabling audit devices)
- `sys/mounts` (mounting engines)

`platform-admin` deliberately **omits** `sudo`. So:

```bash
# As a platform-admin token:
bao operator seal
# → Error: 403 permission denied

# As root:
bao operator seal
# → Success
```

This is how you get a security property most secret stores don't have:
**no human session can unilaterally lock the company out of its own secrets.**

The 2.7 `control_group` feature extends this — it lets a policy require a
**second person to approve** a sensitive operation. We'll cover it here.

---

## 5. Path patterns and wildcards

```hcl
# Exact path
path "ai/platform/data/llm/gemini" { capabilities = ["read"] }

# Wildcard
path "ai/platform/data/llm/*" { capabilities = ["read"] }

# Glob
path "ai/platform/data/llm/gemini*" { capabilities = ["read"] }
```

⚠️ **Wildcards are a silent privilege-escalation vector.** A policy with
`ai/platform/data/llm/*` grants read on `llm/gemini` — and on
`llm/gemini-backup-2024` if someone creates one. Prefer exact paths; use
wildcards only where the set is genuinely enumerable.

**Also:** in KV v2, remember the `data/` and `metadata/` segments. A policy
that grants `ai/platform/data/llm/gemini` does **not** grant
`ai/platform/metadata/llm/gemini`. You need both if you want version info.

---

## 6. `deny` — and why you almost never need it

```hcl
path "ai/platform/data/llm/*" {
  capabilities = ["read", "deny"]
}
```

`deny` overrides everything else. Use it for:
- A path that must never be read, even by a broad policy.
- Emergency containment ("disable access to the prod key right now").

But prefer **not granting** in the first place. A `deny` is a patch over an
over-broad grant.

---

## 7. Testing policies before you ship them

```bash
# What can this token do at this path?
bao token capabilities ai/platform/data/llm/gemini
```

```
path          capabilities
----          ------------
ai/platform/data/llm/gemini    [read]
```

This is the single most useful command in the module. Use it on **every**
policy you write, from the token's perspective.

```bash
# With a specific token:
BAO_TOKEN=$TOKEN bao token capabilities ai/platform/data/db/postgres
```

---

## 8. The enforcement lab (already verified)

From the live lab — this is the real proof:

```
[PASS] ai-harness-service   ai/platform/llm/gemini     expected=ALLOW actual=ALLOW
[PASS] ai-harness-service   ai/platform/db/postgres    expected=DENY  actual=DENY
[PASS] ai-harness-service   ai/platform/cache/redis     expected=DENY  actual=DENY
[PASS] ai-harness-service   write                      expected=DENY  actual=DENY
[PASS] ai-harness-service   list                       expected=DENY  actual=DENY
```

The AI harness can read the Gemini key and **nothing else**. Not the
database password. Not even the *names* of other secrets.

---

## 9. Production policy checklist

- [ ] No long-lived token carries `root`
- [ ] Human tokens are OIDC-backed and short-lived
- [ ] Machine tokens use AppRole with tight TTLs
- [ ] `sudo` is granted to as few identities as possible
- [ ] No policy grants `list` on a broad path
- [ ] Write access exists on exactly one path per domain
- [ ] `destroy` (irreversible) requires human authority
- [ ] Every policy is tested with `bao token capabilities`
- [ ] Policies are version-controlled in Git and applied by CI
- [ ] `deny` rules are exceptional, not routine

---

**Next:** [Module 04 — Namespaces, Entities & Leases](04-namespaces-entities/)
