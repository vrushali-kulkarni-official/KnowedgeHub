# Module 06 — Crypto Tooling: wrap, random, hash, Transit

> **Where we are.** OpenBao can hold a secret. But sometimes you need to
> *move* a secret without storing it, *generate* one without a source, or
> *encrypt* data that must never touch the store at all.

**Status: outline — full lesson in a later session.** All commands below
are already verified against the live lab.

---

## 1. `sys/wrapping/wrap` — hand a secret over safely

Wrapping encrypts a value into a **single-use token** that can be
transported through a channel you don't trust (email, a ticket, a chat
message) and unwrapped exactly once.

```bash
$ bao write -format=json sys/wrapping/wrap text="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
{
  "wrap_info": {
    "token": "s.9Twytr34RvC7ivj6RZ2hyIrh",
    "accessor": "n0UjEvt4c3xM7eYUIcwMVQaP",
    "ttl": 300,
    "creation_path": "sys/wrapping/wrap"
  }
}

$ bao write -format=json sys/wrapping/unwrap token="s.9Twytr34RvC7ivj6RZ2hyIrh"
{
  "data": { "text": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" }
}
```

Reusing the token fails:
```
* wrapping token is not valid or does not exist
```

⚠️ **Gotcha:** use `text=` not `-text=`. With `-text=` the unwrapped
payload's key is literally `"-text"`. And `token=` is a **data field**, not
a flag — `-token=` gives `flag provided but not defined`.

**Meridian AI use case:** onboarding a new engineer — wrap the first-boot
credentials and put them in the onboarding ticket.

---

## 2. `sys/tools/random` — generate secrets

```bash
$ bao write sys/tools/random/32 bytes=32
random_bytes    w/i32BA7JEpEPdXs3nPj3DbUhHCq0BzfUF2NfcTnUSw=
```

Use it for: session IDs, CSRF tokens, initial DB passwords, API keys for
new services. The output is base64 of cryptographically random bytes.

---

## 3. `sys/tools/hash` — one-way hashing

```bash
$ echo -n "meridian-ai-prod" | base64
$ bao write sys/tools/hash/sha2-256 input="bWVyaWRpYW4tYWktcHJvZA=="
sum    272fc0365ed45a481eaa1b487f341303909ebbe394a113550223a455748f5953
```

**Use case:** storing a webhook HMAC secret so the service can *verify* an
incoming signature without being able to reproduce it.

⚠️ The input must be **base64-encoded**. The output is hex.

---

## 4. Transit — encrypt data that never enters the store

This is the most powerful engine in the course. Transit gives you
**encryption as a service** for data that lives somewhere else entirely
— a database column, a Kafka topic, a S3 object.

```bash
$ bao write -format=json ai/transit/encrypt/llm-payload-key \
    plaintext=$(echo -n "customer-email@example.com" | base64)
{
  "data": {
    "ciphertext": "vault:v1:QEgDg0gyMP4fIK/lpl3JTpzQLUMKWpf..."
  }
}

$ bao write -format=json ai/transit/decrypt/llm-payload-key \
    ciphertext="vault:v1:QEgDg0gyMP4fIK/lpl3JTpzQLUMKWpf..."
{
  "data": { "plaintext": "Y3VzdG9tZXItZW1haWxAZXhhbXBsZS5jb20=" }
}
```

**Why this is better than putting the ciphertext in OpenBao:**
- The encrypted data can live in Postgres, and OpenBao holds only the key.
- OpenBao never sees the plaintext at rest.
- The data's own storage compromise doesn't yield plaintext.

**Transit features to cover in the full lesson:** batch encryption,
datakey generation (`exportable` / `non-exportable`), key rotation, HMAC
signing, and **External Keys** (2.7) where the key material stays in an
HSM/KMS and never enters OpenBao at all.

**Meridian AI use case:** encrypting PII (customer emails) in the Postgres
`users` table, with the Transit key held in OpenBao.

---

## 5. The mental model

| Tool | Reversible? | Key in OpenBao? | Use when |
|---|---|---|---|
| `wrap`/`unwrap` | Yes (once) | No | Transporting a secret |
| `random` | n/a | No | Generating a secret |
| `hash` | **No** | No | Verifying a secret |
| `transit` | Yes | **Yes** (or external) | Encrypting data elsewhere |

---

**Next:** [Module 07 — App Integration](07-app-integration/)
