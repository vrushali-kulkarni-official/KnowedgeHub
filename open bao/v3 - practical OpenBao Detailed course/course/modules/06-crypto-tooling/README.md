# Module 06 — Crypto Tooling: wrap, random, hash, Transit

> **Where we are.** You now have Meridian AI's secrets inside OpenBao: the
> Gemini key and the Postgres password live in `ai/platform/`, the
> `ai-harness` service can read exactly one of them, and the rotation bot can
> write but not read. That solves *storage*. It does not yet solve four other
> problems a production platform runs into in the first month: handing a
> secret to a human who has no OpenBao account, generating a secret from
> nothing, checking a secret without keeping it, and encrypting data that
> lives in Postgres while the key lives in OpenBao. This module gives you all
> four tools, plus the two that live inside the `sys/` namespace and the one
> that lives inside every token.

**Status:** complete and verified against OpenBao 2.7.1. The transcripts
below were captured on an isolated instance listening on
`http://127.0.0.1:9274`; your lab listens on `http://127.0.0.1:8200`. Only
the port number differs — every path, status code, and error string is
identical.

**Files shipped with this module** (in `lab/app/` next to this README):

| File | What it is |
|---|---|
| `pii_demo.py` | The runnable end-to-end demo from Section 7.12 — stdlib only (`urllib` + `sqlite3`), no dependencies to install. Every transcript in this module that shows a script run comes from this file. |

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| `sys/tools/random` | Ask OpenBao for cryptographically random bytes. |
| `sys/tools/hash` | One-way SHA-2/SHA-3 digest of a base64 input; output is hex. |
| `sys/wrapping/wrap` | Encrypt any payload into a single-use, short-lived token. |
| `sys/wrapping/unwrap` | Consume a wrapping token exactly once and get the payload. |
| `sys/wrapping/lookup` | Inspect a wrapping token *without* consuming it. |
| `sys/wrapping/rewrap` | Mint a fresh wrapping token; **the original is destroyed**. |
| `X-Vault-Wrap-TTL` | The header that actually sets a wrapping token's lifetime. |
| `cubbyhole/` | Private storage bound to one token. Invisible to every other token. |
| `transit` | Encryption as a service: the key never leaves OpenBao. |
| `transit/keys/<name>` | A named key with a version history. |
| `transit/encrypt` / `decrypt` | Turn plaintext into `vault:v1:…` ciphertext and back. |
| `transit/datakey` | Mint a one-off data key, optionally wrapped by a master key. |
| `transit/hmac` | Keyed MAC so a service can verify a signature it cannot compute. |
| `transit/rotate` | Create a new key version. Old ciphertext still decrypts. |
| `min_decryption_version` | The floor below which ciphertext is refused. |
| `transit/rewrap` | Re-encrypt old ciphertext under the newest key version. |
| `sys/external-keys` | 2.7: back Transit/PKI keys with KMS/HSM key material. |
| `vault:v1:` prefix | The ciphertext tells you which key version made it. |

---

## 1. Why this matters: four problems KV does not solve

Modules 02–05 gave you a place to *put* secrets and a way to control *who
reads them*. That is most of the job. But four things are left over, and each
one has bitten a real platform team.

**Problem 1 — you must move a secret to someone who has no OpenBao access.**
A new engineer needs the staging database password. A contractor needs a
short-lived API token. If you put the secret in a ticket, a Slack message, or
an email, you have rebuilt the `.env` file with extra steps. You need a way
to hand over a secret that is *encrypted for the recipient*, expires on its
own, and cannot be replayed. That is **wrapping**.

**Problem 2 — you need a secret and there is no upstream to give you one.**
A new service needs its own API key, its own session-signing key, its own
CSRF secret. If the app generates it, you now have a randomness question
everywhere in your codebase: which PRNG, how many bytes, what encoding, is it
stored, is it rotated. If OpenBao generates it, there is exactly one answer
and it is auditable. That is **`sys/tools/random`**.

**Problem 3 — you need to *compare* a secret without keeping the secret.**
A webhook provider gives you a shared secret. You want to reject anything
that does not match, but you would rather not store the secret in a form
that a compromised store can replay. If all you need is equality, a one-way
digest is enough. That is **`sys/tools/hash`** — with a large, important
caveat about passwords that this module will spell out.

**Problem 4 — you have data in Postgres and you want it encrypted, but the
key must not be in the app.** The obvious approach is to generate an AES key
in the FastAPI service, encrypt columns with it, and stash the key in the
service's config. You are now back to a secret in a file, plus you have
re-implemented authenticated encryption badly. The alternative is to ask a
secret store to do the encryption for you, over a network call, with a key it
refuses to reveal. That is **Transit**.

> **Production:** *These four tools are the difference between "we have a
> secret store" and "we have a platform". A security review will ask about
> all four: how do you bootstrap a human, how do you generate secrets, how
> do you verify inbound signatures, and how do you protect PII at rest in
> the database. You need a real answer to each.*

---

## 2. The mental model

| Tool | Reversible? | Key material inside OpenBao? | Use it when |
|---|---|---|---|
| `sys/tools/random` | n/a | No key involved | You need a fresh secret and want one auditable source of entropy |
| `sys/tools/hash` | **No** | No key involved (unkeyed digest) | You need to *compare* a value, not reproduce it |
| `sys/wrapping/wrap` | Yes, exactly **once** | The payload is stored encrypted | You are transporting a secret to a specific recipient |
| `cubbyhole/` | Yes | Stored, but only that token can read it | One token needs a private scratch pad |
| `transit/encrypt` | Yes | **Yes** — the key never leaves | You are encrypting data that lives outside OpenBao |
| `transit/datakey` | Yes | Yes (the master key) | You want a one-off key for a bulk-encryption tool |
| `transit/hmac` | No (one-way, keyed) | Yes | A service must *verify* a signature it may not compute |

Two questions separate the whole table:

1. **Is the key inside OpenBao?** If no, OpenBao is doing *cryptography*
   (hash, random) or *transport* (wrap). If yes, OpenBao is doing *key
   management* (transit) and now owns rotation, revocation, and audit for
   that key.
2. **Does the plaintext ever exist anywhere but in RAM?** Transit is the only
   one of these that lets you say "the plaintext is never at rest anywhere",
   because the data being protected never lives in OpenBao at all.

```
                  what you hold                  what OpenBao holds
                ┌────────────────┐             ┌──────────────────────┐
  random ─────►│ 32 random bytes│             │ nothing              │
                └────────────────┘             └──────────────────────┘

  hash ────────►│ digest (hex)   │             │ nothing (unkeyed)    │
                └────────────────┘             └──────────────────────┘

  wrap ────────►│ s.xxxxxxxx     │──unwrap───►│ encrypted payload    │
                │ (bearer, 1 use)│             │ TTL + single use     │
                └────────────────┘             └──────────────────────┘

  transit ─────►│ vault:v1:xxx   │◄─decrypt──►│ master key (never    │
                │ (self-describing)             │ exported) + versions │
                └────────────────┘             └──────────────────────┘
```

---

## 3. `sys/tools/random` — generating secrets properly

### 3.1 The concept, before the command

**What is it?** An endpoint that returns N bytes of cryptographically secure
randomness, base64-encoded by default.

**Why does it exist?** Every secret your platform invents needs entropy, and
entropy has to come from somewhere you can audit. `random.random()` in
Python is a Mersenne Twister — fine for shuffling, catastrophic for keys.
`uuid4()` is fine, but it is 122 bits and formatted for you. `openssl rand`
is fine, but then every container, CI job, and laptop generates its own
secrets and nobody can answer "where did this value come from?".

**What breaks if you don't use it?** You end up with `secrets.token_hex(16)`
in one service, `uuid.uuid4()` in another, and a hand-typed string in a
third. Different lengths, different encodings, and no record of when or by
whom they were made. When one of them leaks, you cannot tell whether it was
a weak PRNG, a copy-paste, or a real compromise.

**The command:**

```bash
$ bao write sys/tools/random/32 bytes=32
Key             Value
---             -----
random_bytes    08ljVhCX4Q2I9B2phA2kOdNlvO5+oFfSkQubCWkCsyE=
```

The path segment `32` and the body `bytes=32` both appear, and they are not
interchangeable — see the gotcha in 3.2.

### 3.2 Gotcha: the URL segment wins over the body

The route is `tools/random/<source>/<bytes>`. If the first segment is a
number, OpenBao treats it as the byte count and **ignores `bytes=` in the
body**:

```bash
$ bao write sys/tools/random/32 bytes=64     # -> 32 bytes
$ bao write sys/tools/random/64 bytes=32     # -> 64 bytes
$ bao write sys/tools/random/platform/48 bytes=32   # -> 48 bytes
$ bao write sys/tools/random/all/16 bytes=32         # -> 16 bytes
$ bao write sys/tools/random bytes=32                # -> 32 bytes (no URL segment, body wins)
```

The `<source>` segment selects the entropy pool and must be `platform`,
`seal`, or `all`:

```bash
$ bao write sys/tools/random/seal/24 bytes=32
WARNING! The following warnings were returned from OpenBao:

  * no seal/entropy augmentation available, using platform entropy source

Key             Value
---             -----
random_bytes    QcZTmkC15VQQRdL5H5Xd2UFCCM3iJ6Q2
```

Read that warning before you build anything on top of `seal`. On a
Shamir-sealed cluster there is no separate seal entropy pool to draw
from, so OpenBao tells you it fell back to the platform CSPRNG. The
`seal` source only becomes a *different* entropy pool when the cluster
is sealed by a KMS or HSM that exposes entropy augmentation — the same
KMS plugins that are not built into OpenBao 2.7.1 (see Section 8). On
a stock lab cluster, `seal` and `platform` are the same bytes.

Anything else fails loudly, which is what you want:

```bash
$ bao write sys/tools/random/nope/24 bytes=32
Error writing data to sys/tools/random/nope/24: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/tools/random/nope/24
Code: 400. Errors:

* unsupported entropy source "nope"; must be "platform" or "seal", or "all"
```

```bash
$ bao write sys/tools/random/abc bytes=32
Error writing data to sys/tools/random/abc: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/tools/random/abc
Code: 400. Errors:

* error parsing url-set byte count: strconv.Atoi: parsing "abc": invalid syntax
```

> **Trade-off:** *`seal` draws from the same entropy source that protects the
> barrier key, which in a KMS-sealed cluster means the cloud KMS. `platform`
> draws from the host's CSPRNG. `all` mixes them. For everyday application
> secrets `platform` is the right answer: it is fast, it does not burn your
> KMS API quota, and it is not on the critical path of the seal operation.
> Use `seal` when you are bootstrapping something whose compromise is
> equivalent to losing the cluster.*

### 3.3 The body, the encoding, and the size

`bao write` refuses to send an empty request body, so even the
"no URL segment" form needs one — or `-force`, which sends `{}`:

```bash
$ bao write sys/tools/random/32
Must supply data or use -force

$ bao write -force sys/tools/random/32
Key             Value
---             -----
random_bytes    ilebDFM3n9ZJ3Dwqiiq6xVCrQT6Wz39Qu/44mWcpVpg=
```

Output is base64 by default, hex on request:

```bash
$ bao write sys/tools/random/32 bytes=32 format=hex
Key             Value
---             -----
random_bytes    b38e4679f2dda04f06672901f592276780f3c6f468686a62bcf6ded75879f340
```

Use hex when the value is going into a filename, a token that must be
URL-safe without encoding, or a system that treats `+` and `/` as syntax.

| Bytes | Bits | Good for |
|---|---|---|
| 16 | 128 | Session IDs, CSRF tokens, short-lived nonces |
| 32 | 256 | API keys, signing keys, encryption keys — the default choice |
| 64 | 512 | Key-encryption keys, high-value long-lived secrets |

> **Production:** *256 bits of randomness is the floor for anything that
> authenticates. The output is base64 of the raw bytes, so 32 bytes becomes
> 44 characters — remember that when you set a column width in Postgres.*

### 3.4 Why not `openssl rand` in your app?

Because then the secret's provenance is your application, not your secret
store. Concretely:

- **No audit trail.** OpenBao logs who asked for the secret, when, from where.
  `openssl rand` in a container logs nothing.
- **No policy.** With OpenBao you can grant `sys/tools/random` to the
  `platform-operator` role and nobody else. In the app, every process that
  can run `openssl` can mint a secret.
- **No central revocation story.** When you rotate, you need to know *every*
  consumer of that secret. A generated-in-the-app secret has consumers
  scattered across deployment manifests you forgot existed.
- **One more place to look during an incident.** The `.env` file was one
  place. `openssl rand` in twelve services is twelve places.

> **Trade-off:** *Calling OpenBao over the network to generate a secret adds
> a dependency and a round trip. For a service that generates a secret once
> at boot, that is free. For a service that generates one per request, you
> want a local CSPRNG and a single OpenBao-fetched master secret to seed it
> — but then you own the key derivation, and you are back to writing crypto.*

---

## 4. `sys/tools/hash` — one-way hashing

### 4.1 The concept, before the command

**What is it?** A digest of your input. Same input, same digest, always.
Different input, different digest, with overwhelming probability. There is
no way back.

**Why does it exist?** Because sometimes you need to check "is this the same
secret?" without being able to turn the stored value back into the secret.
If a thief reads your secret store, a digest is useless to them. If they
read a digest, they cannot log in.

**What breaks if you use it for the wrong thing?** If you use an *unkeyed*
fast hash to protect a password, the attacker takes the digest offline and
cracks it at billions of guesses per second on a GPU. More on that in 4.5.

**The command.** The input must be **base64**, and the output is **hex**:

```bash
$ echo -n "meridian-ai-prod" | base64
bWVyaWRpYW4tYWktcHJvZA==

$ bao write sys/tools/hash/sha2-256 input="bWVyaWRpYW4tYWktcHJvZA=="
Key    Value
---    -----
sum    272fc0365ed45a481eaa1b487f341303909ebbe394a113550223a455748f5953
```

That is the ordinary SHA-256 of that string, which you can confirm without
OpenBao at all:

```bash
$ printf '%s' "meridian-ai-prod" | sha256sum
272fc0365ed45a481eaa1b487f341303909ebbe394a113550223a455748f5953  -
```

> ⚠️ **Gotcha:** *The base64 input is not a convenience, it is the API
> contract. Passing raw text produces a real, specific error:*
>
> ```bash
> $ bao write sys/tools/hash/sha2-256 input="meridian-ai-prod"
> Error writing data to sys/tools/hash/sha2-256: Error making API request.
>
> URL: PUT http://127.0.0.1:9274/v1/sys/tools/hash/sha2-256
> Code: 400. Errors:
>
> * unable to decode input as base64: illegal base64 data at input byte 8
> ```
>
> *Base64 exists so that binary input — a file, a PDF, a JPEG — can travel
> through a JSON body without escaping. A password is text, but the API does
> not know that.*

### 4.2 Which algorithms, and which output encoding

The built-in help lists SHA-2 only, but SHA-3 is accepted too — the
algorithm in the URL path wins:

```bash
$ bao write sys/tools/hash/sha3-256 input="YQ=="
Key    Value
---    -----
sum    80084bf2fba02475726feb2cab2d8215eab14bc6bdd8bfb2c8151257032ecd8b

$ printf '%s' "a" | openssl dgst -sha3-256
SHA3-256(stdin)= 80084bf2fba02475726feb2cab2d8215eab14bc6bdd8bfb2c8151257032ecd8b
```

Anything that is not a supported digest is refused:

```bash
$ bao write sys/tools/hash/md5 input="YQ=="
Error writing data to sys/tools/hash/md5: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/tools/hash/md5
Code: 400. Errors:

* unsupported algorithm md5
```

MD5 is refused for a good reason: it is broken for collision resistance.

Output is hex by default, base64 on request:

```bash
$ bao write sys/tools/hash/sha2-256 input="bWVyaWRpYW4tYWktcHJvZA==" format=base64
Key    Value
---    -----
sum    Jy/ANl7UWkgeqhtIfzQTA5Ceu+OUoRNVAiOkVXSPWVM=
```

### 4.3 The webhook verification use case

A payment provider, `invoice.paid` webhook, shared secret. Two flavours, and
they are genuinely different tools.

**Flavour A — the provider sends you a MAC, you need the key to check it.**
The provider computes `HMAC-SHA256(body, shared_secret)`. To verify, you
must run the same HMAC with the same key. You cannot do that with a digest:
a digest has no key. This is where **Transit HMAC** earns its place
(Section 7.5) — OpenBao holds the key, your service asks OpenBao to
compute the MAC, and the shared secret never touches the service.

**Flavour B — the provider sends you the shared secret itself (a "simple
shared token"), and you only need to check equality.** Here a digest is
exactly right, because you never need to reproduce the secret — only
compare.

The Meridian AI webhook gateway (`data-pipeline`) receives partner
callbacks. Store the fingerprint, not the secret:

```bash
$ bao write sys/tools/hash/sha2-256 input="$(printf '%s' 'the-provider-shared-secret' | base64)"
Key    Value
---    -----
sum    5d9cd51929e0990dffa5e827255b3fec03048cf0736121b5f7e2c5d24c9b90e0
```

At verification time the service hashes whatever the provider sent and
compares:

```python
import hashlib, hmac, os

# the stored fingerprint - not the secret
EXPECTED = os.environ["WEBHOOK_SECRET_SHA256"]

def verify(candidate: str) -> bool:
    digest = hashlib.sha256(candidate.encode()).hexdigest()
    return hmac.compare_digest(digest, EXPECTED)
```

`hmac.compare_digest` is constant-time. A plain `==` on hex digests leaks
timing information; it is a small leak, but it is free to close.

> **Trade-off:** *Flavour B means a single leaked digest *is* a replay
> credential if your provider's scheme allows the secret to be presented
> directly — the attacker sends the same bytes and your comparison passes.
> The digest protects the secret at rest; it does not make the exchange
> safe. Prefer HMAC (Flavour A) wherever the provider supports it, and use
> a digest only as a defence in depth on top of a real signature.*

### 4.4 Why hashing a password is not enough

SHA-256 is a *fast* hash. Fast is exactly what you do not want for
passwords: a single modern GPU computes billions of SHA-256 candidates per
second, so an offline attacker with one stolen digest table recovers most
real passwords in minutes.

Password hashing needs three things SHA-2 does not give you:

1. **A salt** — so two users with the same password get different digests
   and one cracked hash does not unlock the rest.
2. **A work factor** — the hash must be deliberately slow, and tunable so
   you can raise it later.
3. **A memory-hard function** — Argon2id, scrypt, or bcrypt. They make
   GPU/ASIC attacks expensive by requiring RAM.

OpenBao's hash tool gives you none of these. Its only algorithms are SHA-2
and SHA-3, and it is **unkeyed** — no salt parameter, no work factor, no
memory parameter. That is a deliberate scope boundary, not an oversight: it
is a *fingerprint* tool, not a password KDF.

> **Production:** *Never store a password as `sha256(password)` — not in
> OpenBao, not in Postgres, not anywhere. Use `argon2-cffi` (Argon2id) in
> the service that owns authentication, with a per-user random salt. If you
> must centralise it, put the *parameters and the hash* in OpenBao and the
> verification logic in the app.*

---

## 5. Wrapping — moving a secret without storing it

### 5.1 The concept, before the command

**What is a wrapping token?** A short-lived, single-use token whose entire
payload is the encrypted secret. Whoever holds the token string can unwrap
it exactly once, and only if they also hold a credential that is allowed to
unwrap.

**Why does it exist?** Secrets have to travel. A new engineer needs a
credential. A CI job needs a service token. A customer needs a one-time
setup key. If you transmit the secret in the clear, you have created a
second copy of it in a place you do not control — the ticket system, the
chat history, the email archive. Wrapping turns "here is the secret" into
"here is a key-shaped object that yields the secret once, then evaporates".

**What breaks if you don't use it?** The ticket gets forwarded, the Slack
message is in a search index, the email is in a backup — and you now have
three unmanaged copies of a production credential. You cannot rotate them
because you do not know where they are.

**The command:**

```bash
$ bao write -format=json sys/wrapping/wrap text="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
{
  "request_id": "",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": null,
  "warnings": null,
  "wrap_info": {
    "token": "s.mjWPbZA0aRsTA9tWYSUarinz",
    "accessor": "eBoEee3QMrTvaGlvz6yLgNVY",
    "ttl": 300,
    "creation_time": "2026-10-21T16:41:34.094400671Z",
    "creation_path": "sys/wrapping/wrap",
    "wrapped_accessor": ""
  }
}
```

Read that carefully. There is **no secret in the response**. The `data` is
`null`. What you get is `wrap_info.token` — a handle. The secret is now
stored server-side, encrypted, under a lease.

That JSON envelope is the shape every `-format=json` response has:
`request_id`, `lease_id`, `lease_duration`, `renewable`, `data`, `warnings`,
and then the engine-specific part. For the rest of this module I show the
compact form — the same output piped through `jq -c '.data'` — so the
payload stays visible. The full envelope only appears once per endpoint.

### 5.2 Unwrapping — the first and only use

```bash
$ bao write -format=json sys/wrapping/unwrap token="s.mjWPbZA0aRsTA9tWYSUarinz"
{
  "request_id": "5e1e4cad-0aee-8e73-797f-a5cc4d12d367",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "text": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
  },
  "warnings": null
}
```

### 5.3 Reuse fails — and this is the whole point

```bash
$ bao write -format=json sys/wrapping/unwrap token="s.mjWPbZA0aRsTA9tWYSUarinz"
Error writing data to sys/wrapping/unwrap: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/wrapping/unwrap
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

The token is destroyed the instant it is unwrapped. A ticket that gets
forwarded is a ticket that yields nothing on the second attempt. This is why
wrapping is a *transport* mechanism and not a *storage* mechanism: for
storage you have KV, where the value is readable as many times as you like
under a policy.

### 5.4 The `-text=` gotcha, concretely

The payload key is whatever you typed. `text=` produces `text`:

```bash
$ bao write -format=json sys/wrapping/wrap text="meridian-ai-harness-client-secret-rotate-me"
{
  ...
  "wrap_info": { "token": "s.uj0rke1t2y1gWWA1iYSMJjxC", ... }
}

$ bao write -format=json sys/wrapping/unwrap token="s.uj0rke1t2y1gWWA1iYSMJjxC"
{
  ...
  "data": {
    "text": "meridian-ai-harness-client-secret-rotate-me"
  },
  ...
}
```

`-text=` produces a payload key literally named `"-text"`, dash included:

```bash
$ bao write -format=json sys/wrapping/wrap -text="meridian-ai-harness-client-secret-rotate-me"
{
  ...
  "wrap_info": { "token": "s.4mXvbKQ0tqNf2pLzC7yR1Wd", ... }
}

$ bao write -format=json sys/wrapping/unwrap token="s.4mXvbKQ0tqNf2pLzC7yR1Wd"
{
  ...
  "data": {
    "-text": "meridian-ai-harness-client-secret-rotate-me"
  },
  ...
}
```

The value is identical; the *key* is different. Your receiving code does
`payload["text"]` and gets a `KeyError`. The secret is fine; your parser is
wrong. This is why the style of this course writes `text=` and not `-text=`.

### 5.5 `token` is a data field, not a flag

`token=` is part of the JSON body. It is not a CLI flag. And the CLI's
argument parser treats an unknown flag differently depending on where it
appears, which is why the same typo produces two different errors:

```bash
$ bao write -format=json -token="s.mjWPbZA0aRsTA9tWYSUarinz" sys/wrapping/unwrap
flag provided but not defined: -token
```

```bash
$ bao write -format=json sys/wrapping/unwrap -token="s.mjWPbZA0aRsTA9tWYSUarinz"
Error writing data to sys/wrapping/unwrap: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/wrapping/unwrap
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

Before the path, the flag parser rejects it outright. After the path, the
parser has already moved on to positional arguments, so `-token=…` is
swallowed as a stray value and the request goes out with an **empty body** —
which the server reports as an invalid wrapping token. Same mistake, two
different symptoms, neither of which says "you used a dash".

> **Rule that saves you every time:** *flags before positionals, data
> fields without a leading dash. `bao write -format=json PATH key=value`.*

### 5.6 `lookup` — inspect without consuming

```bash
$ bao write -format=json sys/wrapping/lookup token="s.04uRsXVeKtOuIPsiO7MItoZY"
{
  "request_id": "46bc7881-65fd-1592-8efb-a434b88be640",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "creation_path": "sys/wrapping/wrap",
    "creation_time": "2026-10-21T16:34:25.232033114Z",
    "creation_ttl": 300
  },
  "warnings": null
}
```

`lookup` tells you *when* the token was made, *how long* it will live, and
*where* it came from — and it does **not** consume it. That makes it the
tool for an operator console: "is the onboarding token for Aisha still
valid, and when does it die?"

Note `creation_path`. For a token made by `sys/wrapping/wrap` it is
`sys/wrapping/wrap`. For a token made by response-wrapping a read it is the
path you read:

```bash
$ bao read -wrap-ttl=60s -format=json ai/platform/llm/gemini
{
  ...
  "wrap_info": {
    "token": "s.899tjwGjLmfZ1vZJnGjlCe5j",
    "accessor": "DE5kweVvAuTb4ruHNfwOEGz7",
    "ttl": 60,
    "creation_time": "2026-10-21T16:34:54.242414363Z",
    "creation_path": "ai/platform/llm/gemini",
    "wrapped_accessor": ""
  }
}
```

That is a genuinely useful audit signal: *this token was minted by reading
this specific secret path*.

### 5.7 `rewrap` — and the surprise

`rewrap` mints a **new** wrapping token carrying the same payload, without
exposing the payload. The obvious use is extending a token's life without
re-sending the secret: the recipient's ticket expires, so you rewrap the
original and post a fresh token.

Here is the surprise, and it is the kind of thing that bites people:

```bash
$ bao write -format=json sys/wrapping/rewrap token="s.04uRsXVeKtOuIPsiO7MItoZY"
{
  ...
  "wrap_info": {
    "token": "s.35DTFnIdyAF9DhaZLNDaDJ56",
    "accessor": "moezEZmt63htGdVWjc9cs9w4",
    "ttl": 300,
    "creation_time": "2026-10-21T16:34:25.575205636Z",
    "creation_path": "sys/wrapping/wrap",
    "wrapped_accessor": ""
  }
}
```

The rewrapped token carries the payload:

```bash
$ bao write -format=json sys/wrapping/unwrap token="s.35DTFnIdyAF9DhaZLNDaDJ56"
{
  ...
  "data": {
    "text": "meridian-ai-harness-client-secret-rotate-me"
  },
  ...
}
```

**But the original token is gone.** `lookup` on it now fails:

```bash
$ bao write -format=json sys/wrapping/lookup token="s.04uRsXVeKtOuIPsiO7MItoZY"
Error writing data to sys/wrapping/lookup: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/wrapping/lookup
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

`rewrap` is a **move, not a copy**. The old token is consumed in the
transaction that mints the new one. This matters operationally: you cannot
rewrap the same token twice. If your runbook says "rewrap to extend the
deadline", it must be written as "rewrap once, keep the new token, and
re-rewrap the *new* token next time".

### 5.8 TTL — the part everyone gets wrong

The default lifetime of a wrapping token is **300 seconds**.

Setting `ttl=` in the request body does **not** change it. The body is the
payload, so `ttl` becomes part of what you are transporting:

```bash
$ bao write -format=json sys/wrapping/wrap ttl=60 text="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
{
  ...
  "wrap_info": {
    "token": "s.pFkeSXSHcQVg2wTOUmxz0HEN",
    "ttl": 300,
    ...
  }
}
```

The token still says 300. And look at what the payload became:

```bash
$ bao write -format=json sys/wrapping/unwrap token="s.pFkeSXSHcQVg2wTOUmxz0HEN"
{
  ...
  "data": {
    "text": "Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK",
    "ttl": "60"
  },
  ...
}
```

The `ttl` rode along inside the payload. You shipped a Postgres password
with a stray `ttl` field attached to it.

The lifetime is set by the **`X-Vault-Wrap-TTL` request header**:

```bash
$ curl -s --header "X-Vault-Token: $BAO_TOKEN" \
       --header "X-Vault-Wrap-TTL: 60" \
       -X POST -d '{"text":"Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"}' \
       $BAO_ADDR/v1/sys/wrapping/wrap
{
    "request_id": "",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": null,
    "wrap_info": {
        "token": "s.OSqza2jK7KD1s6Z91I01dCFL",
        "accessor": "xs2IlENQmdAxwecF1bo3hjeX",
        "ttl": 60,
        "creation_time": "2026-10-21T16:34:00.582623914Z",
        "creation_path": "sys/wrapping/wrap"
    },
    "warnings": null,
    "auth": null
}
```

Now `ttl: 60`. Durations are Go-style, so `1h` works too, and bad values
are caught immediately:

```bash
$ curl -s --header "X-Vault-Token: $BAO_TOKEN" \
       --header "X-Vault-Wrap-TTL: 1h" -X POST -d '{"text":"x"}' \
       $BAO_ADDR/v1/sys/wrapping/wrap | jq -r '.wrap_info.ttl'
3600

$ curl -s --header "X-Vault-Token: $BAO_TOKEN" \
       --header "X-Vault-Wrap-TTL: notaduration" -X POST -d '{"text":"x"}' \
       $BAO_ADDR/v1/sys/wrapping/wrap
{"errors":["error parsing X-Vault-Wrap-TTL header: time: invalid duration \"notaduration\""]}
```

`ttl: 0` is refused as well — it disables response wrapping entirely:

```bash
$ curl -s --header "X-Vault-Token: $BAO_TOKEN" \
       --header "X-Vault-Wrap-TTL: 0" -X POST -d '{"text":"x"}' \
       $BAO_ADDR/v1/sys/wrapping/wrap
{"errors":["endpoint requires response wrapping to be used"]}
```

The `sys` mount itself cannot be tuned to change this default:

```bash
$ bao secrets tune -default-lease-ttl=600s -max-lease-ttl=1800s sys
Error tuning secrets engine sys/: Error making API request.

URL: POST http://127.0.0.1:9274/v1/sys/mounts/sys/tune
Code: 400. Errors:

* cannot tune parameter default_lease_ttl of sys/
```

**The message names whichever parameter the server rejected first, and
that order is not stable.** Run the same command a few times and you
will see all three of these:

```text
* cannot tune parameter default_lease_ttl of sys/
* cannot tune parameter max_lease_ttl of sys/
* cannot tune parameter options of sys/
```

(`options` is the bucket that holds the non-TTL tunables, so tuning
`-listing-visibility` produces that one.) The status code is always 400
and the shape is always `cannot tune parameter <name> of sys/`. If you
are scripting around this, match on the prefix, not on the exact
parameter name.

**Expiry is real.** A token with a five-second TTL dies on schedule:

```bash
$ curl -s --header "X-Vault-Token: $BAO_TOKEN" \
       --header "X-Vault-Wrap-TTL: 5" -X POST -d '{"text":"Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"}' \
       $BAO_ADDR/v1/sys/wrapping/wrap
{
    ...
    "wrap_info": {
        "token": "s.GGTlLRy8DrGqUpdhEMzHV66B",
        "ttl": 5,
        ...
    }
}

$ sleep 8
$ bao write -format=json sys/wrapping/unwrap token="s.GGTlLRy8DrGqUpdhEMzHV66B"
Error writing data to sys/wrapping/unwrap: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/wrapping/unwrap
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

Note the CLI's own `-wrap-ttl` flag, which does *not* set the lifetime of a
`sys/wrapping/wrap` token. It sets the lifetime of the *response* to
whatever command you ran:

```bash
$ bao write -wrap-ttl=60s -format=json ai/platform/db/postgres db_password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
{
  ...
  "wrap_info": {
    "token": "s.cclg0kjhVY1qCU0TTfjBDtrQ",
    "accessor": "oftmxyG6ZpazZSon8Vki8h2p",
    "ttl": 60,
    "creation_time": "2026-10-21T16:34:54.367863117Z",
    "creation_path": "ai/platform/db/postgres",
    "wrapped_accessor": ""
  }
}
```

Two different things, two different mechanisms. Remember which is which.

### 5.9 The two unwrap flows, and the one that matters

There are two ways to unwrap, and they have *different authorization
models*. Getting this wrong is the difference between "the new engineer can
claim their credential" and "the new engineer cannot".

**Flow 1 — the server-side flow.** The caller authenticates with a normal
token and passes the wrapping token in the body. The caller's token needs
the `sys/wrapping/unwrap` capability.

⚠️ **Before you test the denial, read this.** The `default` policy that
every token gets already grants `sys/wrapping/unwrap` (and
`sys/wrapping/wrap`, `sys/wrapping/lookup`, `cubbyhole/*` and
`sys/tools/hash/*` — Section 10 shows the whole list). So an ordinary
token *can* unwrap:

```bash
$ bao token capabilities "$DATA_PIPELINE_TOKEN" sys/wrapping/unwrap
update
```

To see the 403 you have to mint a token with `-no-default-policy`:

```bash
$ bao token create -policy=data-pipeline -no-default-policy -format=json
$ bao token capabilities "$N" sys/wrapping/unwrap
deny
```

Now unwrap a **valid** wrapping token with it, and you get the denial:

```bash
$ BAO_TOKEN=$N bao write -format=json sys/wrapping/unwrap token="$W"
Error writing data to sys/wrapping/unwrap: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/wrapping/unwrap
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

> ⚠️ **Order of checks.** Use a *valid* wrapping token for that test. With
> a made-up one you never reach the ACL check and the server answers
> `400 wrapping token is not valid or does not exist` instead — the same
> 400 you get from reusing a spent token. Two different failures, one
> error message; the 403 is the one that tells you about permissions.

Give the token the capability and it works, even for a wrapping token that
somebody else created:

```bash
$ bao token capabilities "$DP2" sys/wrapping/unwrap
create, update

$ BAO_TOKEN=$DP2 bao write -format=json sys/wrapping/unwrap token="$W"
{
  ...
  "data": {
    "text": "Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
  },
  ...
}
```

**Flow 2 — the recipient flow, and the one you want for onboarding.** The
CLI's dedicated `unwrap` command makes the *wrapping token itself* the
credential. No OpenBao login, no token, no account:

```bash
$ env -u BAO_TOKEN bao unwrap s.mjWPbZA0aRsTA9tWYSUarinz
Key     Value
---     -----
text    AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
```

That works with **no authentication at all**. Here is the audit record
proving what the server did — note `policies: ["response-wrapping"]`, that
the token is a `service` token, and that `remaining_uses` is 1:

```json
{
  "type": "response",
  "auth": {
    "client_token": "hmac-sha256:66008961ded4888434df8868c9e34707649aab92c9e5c0001aa7ec65422ec757",
    "display_name": "root",
    "policies": ["response-wrapping"],
    "token_policies": ["response-wrapping"],
    "remaining_uses": 1,
    "token_type": "service",
    "token_ttl": 300
  },
  "request": {
    "operation": "update",
    "mount_point": "sys/",
    "path": "sys/wrapping/unwrap",
    "remote_address": "127.0.0.1"
  },
  "response": {
    "data": { "text": "hmac-sha256:be44d9f66fad26e6c46caa49a578c0e6f3724b0a35c11143dbf3c2838055472a" }
  }
}
```

Two details of the 2.7.1 audit format are worth knowing, because they
catch people out when they grep the log. The `path` and `operation` live
inside the nested `request` object, not at the top level, and every entry
has a `type` of either `request` or `response`. The `auth` block is where
the *acting identity* is recorded — for this call, the wrapping token
itself, not the operator who created it.

Under the hood, `bao unwrap <token>` puts the wrapping token in the
`X-Vault-Token` header and calls `sys/wrapping/unwrap` with no body token.
You can reproduce it exactly:

```bash
$ curl -s --header "X-Vault-Token: $WRAPPING_TOKEN" \
       --header "Content-Type: application/json" -X PUT -d '{}' \
       $BAO_ADDR/v1/sys/wrapping/unwrap
{"request_id":"d50fea6e-feb6-1361-2046-58a382d3cf54","lease_id":"","renewable":false,"lease_duration":0,"data":{"text":"Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"},"wrap_info":null,"warnings":null,"auth":null}
```

And a completely raw request with *no* header at all is refused — the
endpoint still needs an identity, and the only acceptable one is the
wrapping token itself:

```bash
$ curl -s --header "Content-Type: application/json" -X PUT -d "{\"token\":\"$W\"}" \
       $BAO_ADDR/v1/sys/wrapping/unwrap
{"errors":["permission denied"]}
```

> **Security note:** *the wrapping token is a bearer secret. Anyone who
> copies it out of the ticket can claim the payload. That is the point, and
> it is also the risk. Ship it over a channel that expires and is not
> archived if you can, and set a tight `X-Vault-Wrap-TTL`.*

### 5.10 The Meridian AI onboarding flow, end to end

Aisha Rahman starts. She has no OpenBao account, no policy, no token.

**Step 1 — the platform operator wraps her first-boot credential.** The
operator holds a token with `sys/wrapping/wrap` capability:

```bash
$ bao write -format=json sys/wrapping/wrap text="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
```

**Step 2 — the operator puts `s.mjWPbZA0aRsTA9tWYSUarinz` in the onboarding
ticket.** Not the password. The token.

**Step 3 — Aisha claims it, with no OpenBao credentials at all:**

```bash
$ bao unwrap s.mjWPbZA0aRsTA9tWYSUarinz
Key     Value
---     -----
text    Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK
```

**Step 4 — the ticket is closed.** The token is spent. If the ticket is
forwarded to the whole onboarding channel, the second person gets:

```
* wrapping token is not valid or does not exist
```

**Step 5 — Aisha exchanges the password for a real scoped token.** She logs
in with AppRole or OIDC and receives a token bound to her identity and
policy. The password she received is now a *bootstrap* credential, and you
rotate it the moment she has exchanged it.

> **Production:** *never put a long-lived production password in a ticket
> even wrapped. Wrap a one-time bootstrap credential that is exchanged for a
> scoped token within minutes, and set `X-Vault-Wrap-TTL` to the shortest
> window that still works — fifteen minutes, not five.*

---

## 6. Cubbyhole — per-token private storage

### 6.1 The concept, before the command

**What is a cubbyhole?** A tiny private storage area, one per token. When you
read `cubbyhole/whatever`, the server resolves it against *the token you
authenticated with*. There is no global cubbyhole.

**Why does it exist?** Some values need to be reachable by exactly one
identity and by nobody else — not even the root token. A token's own
cubbyhole is the natural place for a token's own working state.

**What breaks if you use the wrong storage?** If you put a token's working
state in KV, every token with read access to that path can read it, and the
state outlives the token that created it. A revoked token's scratch data
keeps sitting in your KV until somebody remembers to delete it.

**The command.** With the root token:

```bash
$ bao write -format=json cubbyhole/meridian/root-note note="root cubbyhole: break-glass operator stash"

$ bao list cubbyhole/meridian
Keys
----
root-note

$ bao read cubbyhole/meridian/root-note
Key     Value
---     -----
note    root cubbyhole: break-glass operator stash
```

### 6.2 Isolation, demonstrated

Create a scoped token for the `ai-harness` service. It has the
`cubbyhole/*` capability and nothing else. It writes to *its* cubbyhole:

```bash
$ BAO_TOKEN=$AI_HARNESS_TOKEN bao write -format=json cubbyhole/meridian/harness-note \
    note="ai-harness private scratch: sqlite cache key"

$ BAO_TOKEN=$AI_HARNESS_TOKEN bao list cubbyhole/meridian
Keys
----
harness-note
```

The root token cannot see it, even though the root token can see everything
else:

```bash
$ bao read cubbyhole/meridian/harness-note
No value found at cubbyhole/meridian/harness-note
```

And the scoped token cannot see the root's:

```bash
$ BAO_TOKEN=$AI_HARNESS_TOKEN bao read cubbyhole/meridian/root-note
No value found at cubbyhole/meridian/root-note
```

Note the error: **"No value found"**, not "permission denied". The path
`cubbyhole/meridian/harness-note` is not denied — it simply does not exist
*in your cubbyhole*. The cubbyhole is namespaced by token, so a path you
cannot see and a path that is not there look identical. That is a feature:
it does not leak the existence of other tokens' data.

### 6.3 The policy requirement

A token with no `cubbyhole/*` grant gets a flat 403:

```bash
$ BAO_TOKEN=$NO_CUBBY_TOKEN bao write -format=json cubbyhole/meridian/nope note="should fail"
Error writing data to cubbyhole/meridian/nope: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/cubbyhole/meridian/nope
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

⚠️ **You have to earn that 403.** The `default` policy grants
`cubbyhole/*` to every token, so a token created the ordinary way can
always write to its own cubbyhole. The 403 above is what a token minted
with `-no-default-policy` sees:

```bash
$ bao token create -policy=ai-harness-service -no-default-policy -format=json
$ bao token capabilities "$NO_CUBBY_TOKEN" cubbyhole/meridian/nope
deny
```

This is the same trap that catches people on the wrapping endpoints in
Section 5.9, and it is worth internalising once: **in OpenBao 2.7.1 the
`default` policy is not empty.** Section 10 prints it in full.

The grant looks like this:

```hcl
path "cubbyhole/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
```

### 6.4 What cubbyhole is not

- **It is not a secrets store.** It dies with the token. When the token
  expires or is revoked, its cubbyhole goes with it. If you need a secret to
  outlive a token, it belongs in KV.
- **It is not shared.** There is no "team cubbyhole". If two people need
  the same value, it is a KV path with a policy.
- **It is not free of audit.** Every read is audited, but the audit shows
  the *path*, and every cubbyhole path looks the same in the log. You get
  "someone read cubbyhole/x", not "the ai-harness token read it" — the
  accessor is in the log, but the path is not unique per token.

> **Production:** *use cubbyhole for transient per-token state: a
> "here is the value I just wrapped" pointer, a short-lived correlation id, a
> one-shot nonce. Do not use it for anything you need to find again.*

---

## 7. Transit, in depth

Transit is the most powerful engine in this course. It is also the one with
the most surface area, so this section is the longest.

### 7.1 The concept, before the command

**What is Transit?** Encryption as a service. You send plaintext to
OpenBao, OpenBao encrypts it with a key that never leaves OpenBao, and you
get back a ciphertext string. Later you send the ciphertext back and get the
plaintext. The key is never exposed, never copied, never backed up by you.

**Why does it exist?** Because a lot of data should be encrypted but cannot
live in a secret store. A customer's email address in Postgres. A prompt in
a log. A payload in a queue. That data must be readable by the application
at runtime, so it cannot be a KV secret — but it should not be plaintext at
rest either.

**What breaks if you "just encrypt it in the app"?** Your app holds the key.
Which means the key is in the app's environment, in the app's image, in the
app's crash dumps, in the app's heap dump. You have rebuilt the `.env`
problem with extra steps. And rotating the key means redeploying every
app, plus re-encrypting every row.

**The command:**

```bash
$ bao secrets enable -path=ai/transit transit
Success! Enabled the transit secrets engine at: ai/transit/

$ bao write -format=json ai/transit/keys/pii-column-encryption type="aes256-gcm96"
{
  "request_id": "",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "allow_plaintext_backup": false,
    "auto_rotate_period": 0,
    "deletion_allowed": false,
    "derived": false,
    "exportable": false,
    "imported_key": false,
    "keys": {
      "1": 1792600901
    },
    "latest_version": 1,
    "min_available_version": 0,
    "min_decryption_version": 1,
    "min_encryption_version": 0,
    "name": "pii-column-encryption",
    "soft_deleted": false,
    "supports_decryption": true,
    "supports_derivation": true,
    "supports_encryption": true,
    "supports_signing": false,
    "type": "aes256-gcm96"
  },
  "warnings": null
}
```

Read that key metadata carefully — it is the control panel for everything
that follows:

| Field | What it means |
|---|---|
| `type` | The cipher. `aes256-gcm96` is AES-256-GCM with a 96-bit nonce: authenticated encryption, so tampering is detected. |
| `keys` | The version map. `{"1": <unix ts>}` means version 1 exists, created at that time. |
| `latest_version` | The version new encryptions use. |
| `min_decryption_version` | The floor. Ciphertext made with a lower version is refused. |
| `min_encryption_version` | The floor for *encryption*. |
| `min_available_version` | The oldest version whose material is still present. |
| `exportable` | Whether the raw key material can be read back out. |
| `allow_plaintext_backup` | Whether the key may appear in a plaintext backup blob. |
| `derived` | Whether the key is a KDF root, deriving per-context subkeys. |
| `deletion_allowed` | Whether the key can be deleted at all. |
| `auto_rotate_period` | Seconds between automatic rotations. `0` = never. |
| `soft_deleted` | The key is parked and unusable. |

### 7.2 Encrypt and decrypt

The plaintext is **base64**, because Transit is a JSON API and the payload
may be binary:

```bash
$ echo -n "aisha.rahman@meridian-ai.com" | base64
YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ==

$ bao write -format=json ai/transit/encrypt/pii-column-encryption \
    plaintext="YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ=="
{
  "request_id": "ff5898cd-a983-b889-064e-d37ed5944878",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "ciphertext": "vault:v1:otgxyczpFGwNiblmR49V4FxGumv7BzLY2KuvRHEZcjmop8eIUzNdpfuB6EIwKhR8GLSKX6XaihM=",
    "key_version": 1
  },
  "warnings": null
}
```

There it is: a real `vault:v1:…` ciphertext. Two things to notice.

**The `vault:v1:` prefix is the key version.** The `v1` is *not* the format
version and *not* the engine version — it is the version of the key that
produced this ciphertext. That single design decision buys you enormous
operational freedom: the ciphertext tells you what it needs, so you can
decrypt it without storing a separate "which key version" column, and you
can roll the key forward while old data stays readable.

**The ciphertext is not base64 of the plaintext.** It is base64 of
`nonce ‖ ciphertext ‖ tag`, and it is different every time you encrypt the
same value, because the nonce is random. That is correct for GCM.

Decrypting:

```bash
$ bao write -format=json ai/transit/decrypt/pii-column-encryption \
    ciphertext="vault:v1:otgxyczpFGwNiblmR49V4FxGumv7BzLY2KuvRHEZcjmop8eIUzNdpfuB6EIwKhR8GLSKX6XaihM="
{
  ...
  "data": {
    "plaintext": "YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ=="
  },
  ...
}
```

In a shell you will usually pipe it through `base64 -d`:

```bash
$ bao write -format=json ai/transit/decrypt/pii-column-encryption \
    ciphertext="vault:v1:otgxyczpFGwNiblmR49V4FxGumv7BzLY2KuvRHEZcjmop8eIUzNdpfuB6EIwKhR8GLSKX6XaihM=" \
  | jq -r '.data.plaintext' | base64 -d
aisha.rahman@meridian-ai.com
```

**Tampering is caught**, because GCM is authenticated:

```bash
$ bao write -format=json ai/transit/decrypt/pii-column-encryption ciphertext="vault:v1:deadbeefdeadbeefdeadbeef"
Error writing data to ai/transit/decrypt/pii-column-encryption: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/decrypt/pii-column-encryption
Code: 400. Errors:

* cipher: message authentication failed
```

That is the same error you get for the wrong key, the wrong context, or a
one-bit change. The library refuses to hand back plaintext it cannot
authenticate.

### 7.3 Datakeys — the exportable/non-exportable question

A **datakey** is a one-off symmetric key that OpenBao generates and wraps
under a master key, in a single call.

This section works on a **second** transit key, `pii-field-encryption`,
because a datakey is the one operation you would never run against your
main column-encryption key. Create it first:

```bash
$ bao write -format=json ai/transit/keys/pii-field-encryption type="aes256-gcm96"
{
  ...
  "data": {
    "allow_plaintext_backup": false,
    "auto_rotate_period": 0,
    "deletion_allowed": false,
    "derived": false,
    "exportable": false,
    "imported_key": false,
    "keys": {
      "1": 1792609224
    },
    "latest_version": 1,
    "min_available_version": 0,
    "min_decryption_version": 1,
    "min_encryption_version": 0,
    "name": "pii-field-encryption",
    "soft_deleted": false,
    "supports_decryption": true,
    "supports_derivation": true,
    "supports_encryption": true,
    "supports_signing": false,
    "type": "aes256-gcm96"
  },
  ...
}
```

Note `exportable: false` — that is the default, and it is the setting
that makes the next few commands behave the way they do.

```bash
$ bao write -format=json ai/transit/datakey/plaintext/pii-field-encryption bits=256
{
  ...
  "data": {
    "ciphertext": "vault:v1:kb646cWte7lqOBUpR96Dq3lt+6mf3k1yB7+M/XT9r+1OnfRs7pxo6TPE4j1qbVgrYuAdV+bjhWO+lckK",
    "key_version": 1,
    "plaintext": "rvRcanYfqIer/x4CuZZvec5RLf2Rp+t7kXdGpJGglao="
  },
  ...
}
```

You get **both** halves: the data key in the clear (`plaintext`) and the same
data key encrypted under your master key (`ciphertext`). The `wrapped` variant
returns only the ciphertext:

```bash
$ bao write -format=json ai/transit/datakey/wrapped/pii-field-encryption bits=256
{
  ...
  "data": {
    "ciphertext": "vault:v1:GA86S6kAdm81gJsvN2MHYKMUBcYWMVweVM+SvXvEuzqoFad07vuaghCdvhdowbVUZOYFZbphi3qFz2AB",
    "key_version": 1
  },
  ...
}
```

Round-tripping the wrapped datakey back through Transit gives you the same
bytes:

```bash
$ bao write -format=json ai/transit/decrypt/pii-field-encryption \
    ciphertext="vault:v1:kb646cWte7lqOBUpR96Dq3lt+6mf3k1yB7+M/XT9r+1OnfRs7pxo6TPE4j1qbVgrYuAdV+bjhWO+lckK" \
  | jq -r '.data.plaintext' | base64 -d | od -A x -t x1z | head -4
000000 ae f4 5c 6a 76 1f a8 87 ab ff 1e 02 b9 96 6f 79  >..\jv.........oy<
000010 ce 51 2d fd 91 a7 eb 7b 91 77 46 a4 91 a0 95 aa  >.Q-....{.wF.....<
000020
```

Which matches the `plaintext` field of the original call.

**Now the important distinction.** "Exportable" and "non-exportable" are
properties of the **named key**, not of the datakey.

- A **non-exportable** key (the default) means *the master key material
  cannot be read out of OpenBao*. You can only ask OpenBao to use it. The
  datakey itself still comes back to you in the clear, because you asked for
  it and you are the caller.
- An **exportable** key means the master key material can be read back out.

Reading the raw material out of a non-exportable key is refused:

```bash
$ bao read -format=json ai/transit/export/encryption-key/pii-field-encryption
Error reading ai/transit/export/encryption-key/pii-field-encryption: Error making API request.

URL: GET http://127.0.0.1:9274/v1/ai/transit/export/encryption-key/pii-field-encryption
Code: 400. Errors:

* private key material is not exportable
```

For an exportable key it comes straight out:

```bash
$ bao write -format=json ai/transit/keys/gemini-bring-your-own-key type="aes256-gcm96" \
    exportable=true allow_plaintext_backup=true

$ bao read -format=json ai/transit/export/encryption-key/gemini-bring-your-own-key
{
  ...
  "data": {
    "keys": {
      "1": "YatyT0NDM0eldMauCjSzAVJlOUfkTiMxdspIVyoEuSE="
    },
    "name": "gemini-bring-your-own-key",
    "type": "aes256-gcm96"
  },
  ...
}
```

The export path is type-specific: `export/encryption-key/<name>` refuses an
HMAC key with `encryption not supported for the key`, and
`export/hmac-key/<name>` refuses an AES key with `message encryption not
supported for key type hmac`-style errors on the encrypt side.

There is also a **backup** blob, which is the whole key policy including
archived versions, base64-encoded. Decoded, it contains the key material
plus the policy:

```json
{
  "policy": {
    "name": "gemini-bring-your-own-key",
    "type": 0,
    "exportable": true,
    "allow_plaintext_backup": true,
    "min_decryption_version": 1,
    "min_encryption_version": 0,
    "latest_version": 1,
    "...": "...",
    "keys": {
      "1": {
        "key": "YatyT0NDM0eldMauCjSzAVJlOUfkTiMxdspIVyoEuSE=",
        "hmac_key": "UvnAItnTgAhrwnsQ3h/PB9WVKcm8p92woGWZ5O/k7Io=",
        "time": "2026-10-21T16:35:53.369381992Z",
        "external_key_ref": ""
      }
    }
  },
  "archived_keys": {
    "keys": [
      { "key": null, "hmac_key": null, "time": "0001-01-01T00:00:00Z" },
      { "key": "YatyT0NDM0eldMauCjSzAVJlOUfkTiMxdspIVyoEuSE=",
        "hmac_key": "UvnAItnTgAhrwnsQ3h/PB9WVKcm8p92woGWZ5O/k7Io=",
        "time": "2026-10-21T16:35:53.369381992Z",
        "external_key_ref": "" }
    ]
  }
}
```

Two details in there are worth naming. The `type` field inside the backup
blob is a **numeric enum**, not the string `aes256-gcm96` you get from
the API — `0` is `aes256-gcm96`, `1` is `chacha20-poly1305`, and so on.
And the live key material lives under `policy.keys["<version>"]`, not at
the top of `policy`. `archived_keys` is the same list again, including
the empty slot for version 0.

Backing up a **non**-exportable key is refused — and note the error is a
500, not a 400:

```bash
$ bao read -format=json ai/transit/backup/pii-field-encryption
Error reading ai/transit/backup/pii-field-encryption: Error making API request.

URL: GET http://127.0.0.1:9274/v1/ai/transit/backup/pii-field-encryption
Code: 500. Errors:

* 1 error occurred:
	* exporting is disallowed on the policy
```

> ⚠️ **Note on `exportable`:** *I verified that in OpenBao 2.7.1, setting
> `exportable=true` is sufficient to read the key material out via
> `export/encryption-key/<name>`, and that `allow_plaintext_backup=false`
> did **not** block that read. Do not treat `allow_plaintext_backup` as a
> second lock on key material — treat `exportable` as the single decision.
> A key that is exportable is a key that can be stolen, full stop.*

**The datakey use case.** Datakeys exist for bulk encryption: you encrypt a
million rows with a datakey you hold locally, and you store only the
wrapped datakey alongside the data. To read the data you unwrap the datakey
(OpenBao does that) and decrypt locally. The per-row work happens in your
process, not over the network. For a 10-row table, that is overkill — just
call `transit/encrypt` per row. For a 10-million-row table, it is the only
sane option.

> **Trade-off:** *`datakey/plaintext` hands the raw key to the caller, so
> that key is now in your process's memory and in your logs if you are
> careless. `datakey/wrapped` keeps it sealed, but then you have to ask
> OpenBao to unwrap it anyway — so the only thing you gain is that the
> *wrapped* form is what crosses the network. For a small dataset, use
> `transit/encrypt`. Use datakeys when the volume makes a network round
> trip per row untenable.*

### 7.4 Batch encryption

Transit can encrypt many values in one call. The batch input must be a
**JSON array**:

```bash
$ curl -s --header "X-Vault-Token: $BAO_TOKEN" -X POST \
       -d '{"batch_input":[{"plaintext":"YQ=="},{"plaintext":"Yg=="},{"plaintext":"Yw=="}]}' \
       $BAO_ADDR/v1/ai/transit/encrypt/pii-column-encryption
{
    "request_id": "82bb8ef9-b9f6-0dd4-2bfb-a833ddb8ea59",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "batch_results": [
            {
                "ciphertext": "vault:v1:igk/VsX+Qu6MZFniWqBbXQt+3THXTOj4MRXskhY=",
                "key_version": 1,
                "reference": ""
            },
            {
                "ciphertext": "vault:v1:AZNAhRbmgCcqAvpI5gErc4DYTpBP0xdda/uyxT4=",
                "key_version": 1,
                "reference": ""
            },
            {
                "ciphertext": "vault:v1:/i6cY2IXCk/HB00v/w4nZWNJFnR7BA+crI9dOwE=",
                "key_version": 1,
                "reference": ""
            }
        ]
    },
    "wrap_info": null,
    "warnings": null,
    "auth": null
}
```

The results come back **in order**, one per input, each with its own
`ciphertext` and `key_version`. The `reference` field is your echo slot for
correlating a result with the row it came from.

> ⚠️ **Gotcha, and it will cost you an afternoon:** *the `bao write` CLI
> cannot send a batch. `batch_input=[{...}]` on the command line sends a
> **string**, and OpenBao 2.7.1 refuses strings:*
>
> ```bash
> $ bao write -format=json ai/transit/encrypt/pii-field-encryption \
>     batch_input='[{"plaintext":"YQ=="},{"plaintext":"Yg=="}]'
> Error writing data to ai/transit/encrypt/pii-field-encryption: Error making API request.
>
> URL: PUT http://127.0.0.1:9274/v1/ai/transit/encrypt/pii-field-encryption
> Code: 500. Errors:
>
> * 1 error occurred:
> 	* failed to parse batch input: source data must be an array or slice, got string
> ```
>
> *The `@file` form does not help either — `batch_input=@batch.json` still
> sends a string. Batch operations go through the HTTP API (or a small
> Python function) with a real JSON array. Section 7.12 shows the Python
> shape.*

Batch **decryption** takes the same shape, with `ciphertext` in each item.

### 7.5 HMAC signing

An HMAC key is a different key *type* — it can only sign, never encrypt:

```bash
$ bao write -format=json ai/transit/keys/webhook-signing type="hmac" key_size=32
```

`key_size` is mandatory for HMAC keys and is measured in **bytes**, between
32 and 512:

```bash
$ bao write -format=json ai/transit/keys/webhook-signing type="hmac"
Error writing data to ai/transit/keys/webhook-signing: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/webhook-signing
Code: 500. Errors:

* 1 error occurred:
	* invalid key size for HMAC key, must be between 32 and 512 bytes
```

Signing:

```bash
$ bao write -format=json ai/transit/hmac/webhook-signing \
    input="YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ=="
{
  "request_id": "ba0f010c-c8bb-a151-0000-a75a21abfde0",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "hmac": "vault:v1:7mqv6GgLT83/gXsGrbMTs3mOnBvEQtnwLNkChx04hWg="
  },
  "warnings": null
}
```

The MAC is **deterministic** — the same input always produces the same
value, which is what makes it usable as a signature:

```bash
$ bao write -format=json ai/transit/hmac/webhook-signing \
    input="YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ==" | jq -r '.data.hmac'
vault:v1:7mqv6GgLT83/gXsGrbMTs3mOnBvEQtnwLNkChx04hWg=
```

A different input gives a different MAC:

```bash
$ bao write -format=json ai/transit/hmac/webhook-signing \
    input="$(echo -n 'dev.kapoor@meridian-ai.com' | base64)" | jq -r '.data.hmac'
vault:v1:3L9qlRM+SgrKcK9Sy9aiC7xZgh2x6w64t1ob70YDzvg=
```

And an HMAC key cannot encrypt:

```bash
$ bao write -format=json ai/transit/encrypt/webhook-signing plaintext="eA=="
Error writing data to ai/transit/encrypt/webhook-signing: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/encrypt/webhook-signing
Code: 400. Errors:

* message encryption not supported for key type hmac
```

**The point of Transit HMAC.** Your service must verify a signature
computed with a key it must not have. It sends the payload to OpenBao,
OpenBao computes the MAC with the key it holds, and the service compares the
result to what the sender provided. The key never enters the service. That
is impossible with a local library — a local library needs the key.

The `algorithm` parameter accepts `sha2-224/256/384/512` and
`sha3-224/256/384/512`, defaulting to `sha2-256`. The output is always
base64 after the `vault:v1:` prefix.

> **Trade-off:** *every verification is a network round trip to OpenBao. For
> a webhook firehose — thousands per second — that is a latency and
> throughput problem. Batch HMAC is supported (`batch_input`), which is the
> answer, but at some volume you want a dedicated signing service rather
> than a transit mount.*

### 7.6 Key rotation

Rotation creates a **new version** of the key. It does not touch the old
one, and it does not re-encrypt anything.

```bash
$ bao write -force -format=json ai/transit/keys/pii-column-encryption/rotate
{
  ...
  "data": {
    "latest_version": 2,
    "min_decryption_version": 1,
    "min_encryption_version": 0,
    "keys": {
      "1": 1792600901,
      "2": 1792600902
    }
  },
  ...
}
```

The second key from Section 7.3 rotates the same way, and Section 7.7
uses *it* for the version-floor demonstration:

```bash
$ bao write -force -format=json ai/transit/keys/pii-field-encryption/rotate
{
  ...
  "data": {
    "latest_version": 2,
    "min_decryption_version": 1,
    "min_encryption_version": 0,
    "keys": {
      "1": 1792609224,
      "2": 1792611586
    }
  },
  ...
}
```

(The `-force` is needed because `rotate` takes no data fields and `bao
write` refuses to send an empty body. `bao write -force` sends `{}`.)

Old ciphertext still decrypts — the whole point of keeping old versions:

```bash
$ bao write -format=json ai/transit/decrypt/pii-column-encryption \
    ciphertext="vault:v1:otgxyczpFGwNiblmR49V4FxGumv7BzLY2KuvRHEZcjmop8eIUzNdpfuB6EIwKhR8GLSKX6XaihM=" \
  | jq -c '.data'
{"plaintext":"YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ=="}
```

New encryptions use the new version, and you can see it in the prefix:

```bash
$ bao write -format=json ai/transit/encrypt/pii-column-encryption \
    plaintext="YWlzaGEucmFobWFuQG1lcmlkaWFuLWFpLmNvbQ==" | jq -c '.data'
{"ciphertext":"vault:v2:yWLsCuI4ifcblTvK5A4dlENMm1kG39ontTw8vxqqIfnp46mpFBgcF435J7zqQldkn7LfoPde1Lw=","key_version":2}
```

`vault:v1:` → `vault:v2:`. That is the entire rotation story for a reader
of the ciphertext.

**This is the payoff of Transit over app-side encryption.** Rotating an
app-side key means: re-encrypt every row, deploy the new key, hope you did
not miss a row, keep the old key around forever in case you did. Rotating
a Transit key means: one API call. New writes use the new version, old data
keeps working, and the old version can be retired later once the data is
rewrapped.

You can also rotate automatically, per key:

```bash
$ bao write -format=json ai/transit/keys/pii-field-encryption/config auto_rotate_period="24h"
{
  ...
  "data": {
    "auto_rotate_period": 86400,
    ...
  }
}
```

### 7.7 `min_decryption_version` — retiring an old key version

Rotation alone never retires anything. To stop a version from being usable
you raise the floor:

```bash
$ bao write -format=json ai/transit/keys/pii-field-encryption/config \
    min_decryption_version=2 min_encryption_version=2
{
  ...
  "data": {
    "latest_version": 2,
    "min_decryption_version": 2,
    "min_encryption_version": 2
  },
  ...
}
```

Now the old ciphertext is refused:

```bash
$ bao write -format=json ai/transit/decrypt/pii-field-encryption \
    ciphertext="vault:v1:4a6u+UImBFbvuTREw8CLTO80NaRWMTonO7SarNVRwGfzGPJGnV7oPerCsWK8WnDahj0jRL6n"
Error writing data to ai/transit/decrypt/pii-field-encryption: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/decrypt/pii-field-encryption
Code: 400. Errors:

* ciphertext or signature version is disallowed by policy (too old)
```

And so is rewrapping it:

```bash
$ bao write -format=json ai/transit/rewrap/pii-field-encryption \
    ciphertext="vault:v1:4a6u+UImBFbvuTREw8CLTO80NaRWMTonO7SarNVRwGfzGPJGnV7oPerCsWK8WnDahj0jRL6n"
Error writing data to ai/transit/rewrap/pii-field-encryption: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/rewrap/pii-field-encryption
Code: 400. Errors:

* ciphertext or signature version is disallowed by policy (too old)
```

And you cannot ask to encrypt with the old version either:

```bash
$ bao write -format=json ai/transit/encrypt/pii-field-encryption key_version=1 plaintext="YQ=="
Error writing data to ai/transit/encrypt/pii-field-encryption: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/encrypt/pii-field-encryption
Code: 400. Errors:

* requested version for encryption is less than the minimum encryption key version
```

**Order of operations matters.** Raise `min_decryption_version` *only after*
you have rewrapped every row that still uses the old version. Otherwise you
have turned a rotation into a data-loss incident. The safe sequence is:

1. Rotate.
2. Rewrap all old ciphertext in the background.
3. Verify no `vault:v1:` rows remain.
4. Raise `min_decryption_version`.
5. `trim` to destroy the old key material.

**Trim** is the point of no return — it deletes the key material of the
versions below the floor:

```bash
$ bao write -force -format=json ai/transit/keys/pii-field-encryption/trim min_available_version=2
{
  ...
  "data": {
    "latest_version": 2,
    "min_decryption_version": 2,
    "min_encryption_version": 2,
    "keys": {
      "2": 1792600617
    }
  },
  ...
}
```

Version 1 is gone from the key map. And the floors are now coupled — you
cannot set `min_encryption_version` below what is still available:

```bash
$ bao write -format=json ai/transit/keys/pii-field-encryption/config min_decryption_version=1 min_encryption_version=0
Error writing data to ai/transit/keys/pii-field-encryption/config: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/pii-field-encryption/config
Code: 400. Errors:

* min encryption version should not be less than min available version
```

### 7.8 Rewrap — re-encrypting old ciphertext

`transit/rewrap` decrypts with whatever version the ciphertext names and
re-encrypts with the latest version, in one server-side operation. The
plaintext never crosses the wire.

```bash
$ bao write -format=json ai/transit/rewrap/pii-column-encryption \
    ciphertext="vault:v1:otgxyczpFGwNiblmR49V4FxGumv7BzLY2KuvRHEZcjmop8eIUzNdpfuB6EIwKhR8GLSKX6XaihM=" \
  | jq -c '.data'
{"ciphertext":"vault:v2:r8Kq4d6oBYtnb1IsFhViFysKyZ4DmL7GdoJ/bFZIFm3CJsgTzGerQF3KMgBZjbBi0vYI208Cibg=","key_version":2}
```

If the ciphertext is already on the latest version, rewrap is a no-op — it
returns the same value.

This is the background job that makes rotation cheap: a nightly task that
walks the `users` table, rewrites every `vault:v1:` row as `vault:v2:`, and
reports how many it changed.

### 7.9 Deleting a key

Keys are not deletable by default. `deletion_allowed` must be turned on
explicitly, and it is turned on at the **config** endpoint, not at creation
time:

```bash
$ bao write -format=json ai/transit/keys/throwaway-key type="aes256-gcm96" deletion_allowed=true
{
  ...
  "data": {
    "deletion_allowed": false,
    ...
  }
}
```

The `deletion_allowed=true` in the *creation* call is ignored. Set it
afterwards:

```bash
$ bao write -format=json ai/transit/keys/throwaway-key/config deletion_allowed=true
{
  ...
  "data": {
    "deletion_allowed": true,
    "latest_version": 1
  },
  ...
}
```

Now the key can be deleted:

```bash
$ bao delete -format=json ai/transit/keys/throwaway-key

$ bao read -format=json ai/transit/keys/throwaway-key
No value found at ai/transit/keys/throwaway-key
```

And a key that has not opted in refuses:

```bash
$ bao delete -format=json ai/transit/keys/gemini-bring-your-own-key
Error deleting ai/transit/keys/gemini-bring-your-own-key: Error making API request.

URL: DELETE http://127.0.0.1:9274/v1/ai/transit/keys/gemini-bring-your-own-key
Code: 400. Errors:

* error deleting policy gemini-bring-your-own-key: deletion is not allowed for this key
```

There is also a soft-delete / soft-delete-restore pair for parking a key
without destroying it.

> **Production:** *deleting a transit key does not delete the data it
> encrypted. It makes that data permanently unreadable. Treat
> `transit/keys/*` deletion as a destructive database operation: require
> the `platform-admin` role, require `sudo`, and run it from a reviewed
> runbook, not from a script.*

### 7.10 Derived and convergent keys (and a 2.7 finding you should know about)

A **derived** key is a KDF root. Each request supplies a `context`, and
OpenBao derives a per-context subkey with HKDF. Two different contexts never
share key material.

```bash
$ bao write -format=json ai/transit/keys/pii-lookup derived=true convergent_encryption=true type="aes256-gcm96"
{
  ...
  "data": {
    "convergent_encryption": true,
    "derived": true,
    "kdf": "hkdf_sha256",
    ...
  }
}
```

A derived key **requires** a context:

```bash
$ bao write -format=json ai/transit/encrypt/pii-lookup plaintext="eA=="
Error writing data to ai/transit/encrypt/pii-lookup: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/encrypt/pii-lookup
Code: 400. Errors:

* missing 'context' for key derivation; the key was created using a derived key, which means additional, per-request information must be included in order to perform operations with the key
```

**Convergent** encryption means the same (context, plaintext) always produces
the same ciphertext. That is what lets you `WHERE email_ciphertext = …` in
Postgres.

```bash
$ CTX=$(echo -n "meridian_ai.users.email" | base64)
$ bao write -format=json ai/transit/encrypt/pii-lookup context="$CTX" \
    plaintext="$(echo -n 'aisha.rahman@meridian-ai.com' | base64)" | jq -r '.data.ciphertext'
vault:v1:+KX6q0r7jjTXOcyS1s98CRp7MfTCjD+A1UmFxxk3Ft0A5CRQJqI+e10mPfIN2DGKH6dP+gV4q7s=
```

Run it again — identical output. Different plaintext, same context — different
output. Same plaintext, different context — different output. All verified.

Decrypting with the wrong context fails like a tampered ciphertext:

```bash
$ bao write -format=json ai/transit/decrypt/pii-lookup \
    context="$(echo -n 'other.table.col' | base64)" ciphertext="$C"
Error writing data to ai/transit/decrypt/pii-lookup: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/decrypt/pii-lookup
Code: 400. Errors:

* cipher: message authentication failed
```

> ⚠️ **Changed in 2.7 / differs from Vault-era tutorials:** *Vault's
> `transit/encrypt` documents a `nonce` parameter used to make convergent
> encryption safe (one fresh nonce per record). In OpenBao 2.7.1 there is
> **no `nonce` parameter on `transit/encrypt`**. The endpoint's own help
> proves it — the parameter list is `associated_data`, `batch_input`,
> `context`, `convergent_encryption`, `key_version`, `name`,
> `partial_failure_response_code`, `plaintext`, `type`, and nothing else.
> The only place the word "nonce" appears in that help is inside the
> description of `convergent_encryption`, which is the interesting part:
>
> ```text
>     convergent_encryption (bool)
>
>         ... will require all requests to carry both a context
>         and 96-bit (12-byte) nonce. The given nonce will be used in place
>         of a randomly generated nonce. ...
> ```
>
> *So the help tells you convergent encryption requires a nonce, and then
> offers you no way to supply one. I verified that passing a valid 12-byte
> `nonce` has **no effect**: the ciphertext was byte-identical with a
> random nonce, a different random nonce, and no nonce at all. In 2.7.1 a
> convergent key always uses the same effective nonce for a given context.
> Treat convergent encryption as "equality is visible" and nothing more.*

**The security cost of convergence, stated plainly.** Deterministic
encryption leaks equality. If two rows have the same ciphertext, they have
the same plaintext. An attacker with read access to your `users` table can
count how many customers share an email domain, how many share a name, and
can build a frequency table for common values — all without breaking any
crypto. For a field like `email`, that is often acceptable and is the price
of being able to look a user up. For a field like `medical_condition`, it
is not. Use a **blind index** (a separate HMAC of the value under a
separate key) when you need lookup without leaking equality of the
ciphertext column itself.

### 7.11 Transit configuration

The mount-level cache is configured separately:

```bash
$ bao read -format=json ai/transit/cache-config
{
  ...
  "data": {
    "size": 0
  },
  ...
}

$ bao write -format=json ai/transit/cache-config size=100
```

`size: 0` means no cache: every decrypt is a key lookup plus a decrypt
operation. A cache keeps decrypted key material in memory so repeated
decrypts are faster. **Do not enable it casually** — cached key material in
the OpenBao process's memory is a larger blast radius than you may want.
Note there is **no** `ai/transit/config` endpoint in 2.7.1:

```bash
$ bao write -format=json ai/transit/config cache_size=0
Error writing data to ai/transit/config: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/config
Code: 404. Errors:

* 1 error occurred:
	* unsupported path
```

### 7.12 The Meridian AI PII-in-Postgres use case, end to end

**The problem.** `meridian_ai.users` holds customer email addresses. The
`data-pipeline` service writes rows; the `ai-harness` service reads them to
build prompts. A dump of that table must not reveal customer email
addresses. The key must live in OpenBao, not in the app.

**The schema.** In a real deployment:

```sql
-- meridian_ai
CREATE TABLE users (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         UUID        NOT NULL,
    email_ciphertext  TEXT        NOT NULL,   -- vault:v2:... from OpenBao Transit
    email_blind_index BYTEA       NOT NULL,   -- HMAC-SHA256 for lookups, no equality leak
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX users_email_blind_index_idx ON users (email_blind_index);
```

The `email_ciphertext` column holds the Transit ciphertext. The
`email_blind_index` column holds an HMAC of the email under a *separate*
Transit HMAC key — that is how you look a user up by email without
convergent encryption and without leaking equality in the ciphertext column.

**The policy.** The application gets three transit paths and one KV path,
and nothing else:

```hcl
# meridian-ai / data-pipeline
path "ai/transit/encrypt/pii-column-encryption" {
  capabilities = ["create", "update"]
}

path "ai/transit/decrypt/pii-column-encryption" {
  capabilities = ["create", "update"]
}

path "ai/transit/hmac/user-lookup-index" {
  capabilities = ["create", "update"]
}

path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}
```

The capabilities, checked rather than assumed:

```bash
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/transit/encrypt/pii-column-encryption
create, update
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/transit/decrypt/pii-column-encryption
create, update
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/transit/keys/pii-column-encryption
deny
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/transit/datakey/plaintext/pii-column-encryption
deny
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/transit/export/encryption-key/pii-column-encryption
deny
$ bao token capabilities "$DATA_PIPELINE_TOKEN" ai/platform/data/db/postgres
read
```

`deny` on the key itself, on datakey, and on export. The application can
*use* the key and cannot *steal* it. That is the whole security property
of Transit, expressed as a policy.

**The application code.** Stdlib only — `urllib` for HTTP, because a
third-party SDK inside your trust boundary is a third-party supply chain.
This is the shipped `lab/app/pii_demo.py`; the excerpt below is the whole
of its crypto path:

```python
import base64
import json
import os
import urllib.error
import urllib.request

BAO_ADDR = os.environ["BAO_ADDR"].rstrip("/")
BAO_TOKEN = os.environ["BAO_TOKEN"]
TRANSIT_MOUNT = "ai/transit"
TRANSIT_KEY = "pii-column-encryption"


def bao(method, path, payload=None):
    """One HTTP call to OpenBao. Returns the parsed JSON body."""
    url = f"{BAO_ADDR}/v1/{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Vault-Token", BAO_TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"OpenBao {method} {path} -> HTTP {exc.code}: {exc.read().decode()}")
    return json.loads(body) if body else {}


def b64(text):
    return base64.b64encode(text.encode()).decode()


def unb64(text):
    return base64.b64decode(text).decode()


def transit_encrypt(plaintext):
    resp = bao("POST", f"{TRANSIT_MOUNT}/encrypt/{TRANSIT_KEY}", {"plaintext": b64(plaintext)})
    return resp["data"]["ciphertext"]


def transit_decrypt(ciphertext):
    resp = bao("POST", f"{TRANSIT_MOUNT}/decrypt/{TRANSIT_KEY}", {"ciphertext": ciphertext})
    return unb64(resp["data"]["plaintext"])
```

**The end-to-end run.** The lab for this course has no Postgres server, so
the run below uses SQLite as the storage layer; the crypto path is
byte-for-byte the same because Transit knows nothing about databases. The
Postgres DDL above is what you would actually deploy.

The script ships with this module at `lab/app/pii_demo.py`, and this
transcript is a **real run of that file** against a live OpenBao 2.7.1 —
not a reconstruction. Run it yourself with a token that carries the
`data-pipeline` policy:

```bash
$ export BAO_ADDR=http://127.0.0.1:8200
$ export BAO_TOKEN=s.GDBOCtv9VTncsFrYYjTrWtr5
$ cd lab/app && python3 pii_demo.py
[1] pulled DB creds from OpenBao KV: db=meridian_ai user=meridian_app
[2] transit_encrypt -> vault:v2:xLsCbZPRG5Z//crSqBGCVuX...
[3] inserted row with ciphertext only
[4] read row -> transit_decrypt -> aisha.rahman@meridian-ai.com
    round trip OK
[5] raw DB file contains plaintext email? False
    raw DB file contains the ciphertext? True
[6] reading the transit key from the app's token -> OpenBao GET ai/transit/keys/pii-column-encryption -> HTTP 403: {"errors":["1 error occurred:\n\t* permission denied\n\n"]}
```

Two things about that transcript are worth stating plainly. The
`vault:v2:` prefix in line **[2]** is the key *version*, and the
ciphertext itself is different on every run — the GCM nonce is random.
And the token in the `export` line above is a throwaway minted for the
demo; a real deployment would have the deployment system inject it.

Read those six lines as the acceptance criteria for the design:

- **(1)** The app's only secret from OpenBao is the *database password*. The
  transit key is not a secret to the app — the key *name* is configuration,
  and the policy decides what the app may do with it.
- **(2)** The app sends plaintext to OpenBao. It never holds a key.
- **(3)** Only ciphertext is written.
- **(4)** The round trip works, because the app can decrypt.
- **(5)** The raw storage file does not contain the email. That is the
  property you were buying.
- **(6)** The app cannot read the key. It can use it; it cannot steal it.

**The rotation runbook**, now that the design exists:

```bash
# 1. rotate the key (new writes use v3, old data still reads)
bao write -force ai/transit/keys/pii-column-encryption/rotate

# 2. background job: rewrap every old row
#    for each row where email_ciphertext LIKE 'vault:v1:%' or 'vault:v2:%':
#      new = transit_rewrap(row.email_ciphertext)
#      UPDATE users SET email_ciphertext = new WHERE id = row.id

# 3. verify nothing old is left
#    SELECT count(*) FROM users WHERE email_ciphertext NOT LIKE 'vault:v3:%';

# 4. only then, retire the old version
bao write ai/transit/keys/pii-column-encryption/config min_decryption_version=3
bao write -force ai/transit/keys/pii-column-encryption/trim min_available_version=3
```

Step 4 is the point of no return. Never run it before step 3 returns zero.

### 7.13 Why Transit beats "encrypt it yourself"

| | App-side encryption | Transit |
|---|---|---|
| Where the key lives | The app's env, image, heap dumps | OpenBao, never exported |
| Rotation | Re-deploy the app, re-encrypt every row | One `rotate` call; old data keeps working |
| Compromising the app | Yields the key **and** all the data | Yields the key *name*; policy still applies |
| Audit | Wherever you wrote it | Every encrypt/decrypt in the OpenBao audit log |
| Crypto correctness | Your problem | AES-256-GCM, authenticated, reviewed, versioned |
| Moving to an HSM later | Rewrite the app | Point the key at an external key (Section 8) |
| Latency | Microseconds | A network round trip |
| Availability | Degrades with the app | Degrades with OpenBao |

The last two rows are the honest trade-off. Transit is a network
dependency in your hot path. If OpenBao is down, your service cannot encrypt
or decrypt. For a control plane that is acceptable; for a request path that
encrypts on every request, you need to think about it.

> **Trade-off:** *the usual hybrid is a **datakey**: ask Transit once at
> startup for a data key, keep it in process memory, and use a local
> library (libsodium, `cryptography`) for the per-row work. You get local
> speed with a key that OpenBao still controls the lifecycle of. The cost:
> the data key is now in your process, and you must handle it like the
> plaintext it protects.*

### 7.14 When NOT to use Transit

Transit is powerful, and powerful tools get misused. Do **not** use it for:

1. **Secrets that OpenBao already stores.** If a value lives in KV, KV is
   the answer. Putting it through Transit as well adds a key to rotate and
   a second place to get the authorization wrong.
2. **Data you need to search, sort, or filter on.** Encryption destroys
   ordering and equality. `WHERE status = 'active'` on an encrypted column
   does not work. Encrypt the fields that are sensitive; keep the ones you
   query in the clear, and consider a blind index for the sensitive one.
3. **Low-volume, latency-critical request paths** where a network round trip
   per request is unacceptable — use a datakey and local crypto instead.
4. **Anything that is not actually sensitive.** Transit operations are
   audited, which is good, but audit noise hides the events that matter.
   Encrypting a user's country code is theatre.
5. **Password hashing.** Transit is not a KDF. Use Argon2id.
6. **As a substitute for TLS.** Transit protects data *at rest*. It does
   nothing for data in flight. TLS is still mandatory.
7. **Whole-database encryption.** Encrypting every row of every table
   destroys every index and every query you have. Encrypt columns.

And one more, specific to OpenBao 2.7:

8. **Do not use `type=external-key` until you have a KMS plugin installed.**
   The 2.7 feature is real, but the KMS plugins are **not built in**
   (`awskms`, `gcpckms`, `azurekeyvault`, `pkcs11` all moved to
   `openbao-plugins`). Without one, the feature is a 400 with a very
   specific error (Section 8).

---

## 8. External Keys (OpenBao 2.7)

### 8.1 What the feature is

External Keys lets PKI and Transit use key material that lives in an
external KMS or HSM and **never enters OpenBao's memory**. Instead of
OpenBao generating and holding a key, you register a *reference* to a key
that the KMS already holds. OpenBao asks the KMS to perform the operation.

This is the answer to "we have a CloudHSM / a cloud KMS and compliance
says the key cannot be in the vault". The application API does not change:
you still call `transit/encrypt`. What changes is where the key material
lives.

### 8.2 The API surface

Three paths, all under `sys/`:

```
sys/external-keys/configs                    LIST   - list configs
sys/external-keys/configs/<config>           GET/PUT/PATCH/DELETE - manage a config
sys/external-keys/configs/<config>/keys/<key> GET/PUT/PATCH/DELETE - manage a key
```

`bao path-help` confirms the routes and the methods:

```bash
$ bao path-help sys/external-keys/configs/aws-kms
Request:        external-keys/configs/aws-kms
Matching Route: ^external-keys/configs/(?P<config>\w(([\w-.]+)?\w)?)$

Manage configs.

## PARAMETERS

    config (string)

        Name of the config.

    plugin (string)

        Name of the KMS plugin.

    verify (bool)

        Verify the config against the KMS backend (default true).

## DESCRIPTION

This path responds to the following HTTP methods.

	GET /configs/<config>
		Read a config.

	PUT /configs/<config>
		Create or update a config.

	PATCH /configs/<config>
		Patch a config.

	DELETE /configs/<config>
		Remove a config.
```

```bash
$ bao path-help sys/external-keys/configs/aws-kms/keys/mykey
Request:        external-keys/configs/aws-kms/keys/mykey
Matching Route: ^external-keys/configs/(?P<config>\w(([\w-.]+)?\w)?)/keys/(?P<key>\w(([\w-.]+)?\w)?)$

Manage keys.

## PARAMETERS

    config (string)

        Name of the config.

    key (string)

        Name of the key.

    verify (bool)

        Verify the key against the KMS backend (default true).

## DESCRIPTION

This path responds to the following HTTP methods.

	GET /configs/<config>/keys/<key>
		Read a key.

	PUT /configs/<config>/keys/<key>
		Create or update a key.

	PATCH /configs/<config>/keys/<key>
		Patch a key.

	DELETE /configs/<config>/keys/<key>
		Remove a key.
```

The config list endpoint is **LIST-only**:

```bash
$ bao list sys/external-keys/configs
No value found at sys/external-keys/configs

$ bao read -format=json sys/external-keys/configs
Error reading sys/external-keys/configs: Error making API request.

URL: GET http://127.0.0.1:9274/v1/sys/external-keys/configs
Code: 405. Errors:

* 1 error occurred:
	* unsupported operation
```

### 8.3 Using it from Transit

A Transit key of type `external-key` points at an external key by
`"<config name>:<key name>"`:

```bash
$ bao write -format=json ai/transit/keys/hsm-backed type="external-key" \
    external_key_ref="aws-kms/meridian-key"
Error writing data to ai/transit/keys/hsm-backed: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/hsm-backed
Code: 400. Errors:

* failed to fetch external key: invalid key reference: must be "<config name>:<key name>"
```

The reference format is checked, and the two flags are interdependent:

```bash
$ bao write -format=json ai/transit/keys/hsm-backed type="external-key"
Error writing data to ai/transit/keys/hsm-backed: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/hsm-backed
Code: 400. Errors:

* must provide external_key_ref to create policy of type external-key
```

```bash
$ bao write -format=json ai/transit/keys/hsm-backed type="aes256-gcm96" \
    external_key_ref="aws-kms:meridian-key"
Error writing data to ai/transit/keys/hsm-backed: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/hsm-backed
Code: 400. Errors:

* must provide type=external-key to use external_key_ref
```

With the right reference format, the failure moves on to the missing
config:

```bash
$ bao write -format=json ai/transit/keys/hsm-backed type="external-key" \
    external_key_ref="aws-kms:meridian-key"
Error writing data to ai/transit/keys/hsm-backed: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/ai/transit/keys/hsm-backed
Code: 400. Errors:

* failed to fetch external key: key "aws-kms:meridian-key" does not exist
```

And creating the config itself fails, because the KMS plugin is not
installed:

```bash
$ bao write -format=json sys/external-keys/configs/aws-kms plugin=awskms
Error writing data to sys/external-keys/configs/aws-kms: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/external-keys/configs/aws-kms
Code: 400. Errors:

* unknown plugin: awskms
```

### 8.4 What I could and could not verify — read this part

This is a single-node lab with **no KMS plugin and no HSM**, so be precise
about what is demonstrated and what is not.

**Verified on this lab:**

- The endpoints `sys/external-keys/configs` and
  `sys/external-keys/configs/<config>/keys/<key>` exist in OpenBao 2.7.1,
  with the method sets and parameters quoted above.
- `sys/external-keys/configs` is **LIST-only**; a GET on it is
  `405 unsupported operation`.
- The transit key type `external-key` exists, and the
  `external_key_ref` validation works, with the three exact error strings
  quoted above.
- The `external_key_ref` format is `<config name>:<key name>`.
- The `archived_keys` structure of a transit key backup carries an
  `external_key_ref` field — the plumbing for external keys is present in
  the 2.7.1 key model.

**Not verified on this lab — you must verify these yourself:**

- Creating a working `sys/external-keys/configs/<config>` (needs a KMS
  plugin).
- Creating, reading, and using a key under
  `sys/external-keys/configs/<config>/keys/<key>`.
- A Transit key of type `external-key` actually encrypting and decrypting.
- PKI with external keys.
- The exact per-KMS configuration fields (`plugin=awskms` plus whatever
  region/credentials the plugin needs).
- Whether `verify=true` (the default) behaves as documented against a real
  KMS.
- Key rotation semantics for external keys — whether OpenBao rotates the
  KMS-side key, or whether you must orchestrate it.

**Why it cannot work here:** the KMS seal and KMS plugins are **not
built into OpenBao 2.7.1**. `bao plugin list` on this lab shows only
`kv`, `pki`, `ssh`, `totp`, `transit`, `rabbitmq`, `kubernetes` as secret
engines. `awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms` and
`pkcs11` all live in the separate `openbao-plugins` repository and must be
installed and registered before External Keys can be configured.

> **Production:** *do not design around External Keys until you have
> installed a KMS plugin in a real cluster and proven the round trip. Until
> then, treat OpenBao's own key storage as your trust boundary, and be
> explicit in your threat model that a compromise of the OpenBao process
> yields the transit key material.*

---

## 9. The GUI for this module

Open <http://127.0.0.1:8200/ui> and log in.

The top-level navigation in OpenBao 2.7.1 is **Secrets engines**, **Access**,
**Policies** and **Tools**. Everything in this module that has a GUI lives
under one of those two: **Secrets engines** for Transit, **Tools** for
random, hash, and the wrapping endpoints.

| What you want | GUI path | CLI equivalent |
|---|---|---|
| See the transit keys | **Secrets engines → Transit → ai/transit** | `bao list ai/transit/keys` |
| Inspect one key's versions | **Secrets engines → Transit → ai/transit → *key*** | `bao read ai/transit/keys/<name>` |
| Encrypt a value to try it out | **Secrets engines → Transit → ai/transit → *key* → *encrypt*** | `bao write ai/transit/encrypt/<name> plaintext=<b64>` |
| Decrypt a value | **Secrets engines → Transit → ai/transit → *key* → *decrypt*** | `bao write ai/transit/decrypt/<name> ciphertext=…` |
| Generate a data key | **Secrets engines → Transit → ai/transit → *key* → *datakey*** | `bao write ai/transit/datakey/plaintext/<name>` |
| Compute an HMAC | **Secrets engines → Transit → ai/transit → *key* → *hmac*** | `bao write ai/transit/hmac/<name> input=<b64>` |
| Key settings (rotation period, deletion, version floors) | **Secrets engines → Transit → ai/transit → *key* → edit form** | `bao write ai/transit/keys/<name>/config …` |
| Generate random bytes | **Tools → Random** | `bao write sys/tools/random/32 bytes=32` |
| Hash a value | **Tools → Hash** | `bao write sys/tools/hash/sha2-256 input=<b64>` |
| Wrap a payload | **Tools → Wrap** | `bao write sys/wrapping/wrap text="…"` |
| Inspect a wrapping token | **Tools → Lookup** | `bao write sys/wrapping/lookup token="s.…"` |
| Unwrap a payload | **Tools → Unwrap** | `bao write sys/wrapping/unwrap token="s.…"` |
| Mint a fresh wrapping token from an old one | **Tools → Rewrap** | `bao write sys/wrapping/rewrap token="s.…"` |

**Honest note on verification:** every label and path in that table was
read out of the OpenBao 2.7.1 UI bundle that the server actually serves,
not guessed. The server's own list of JavaScript assets is discoverable:

```bash
$ curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
assets/chunk.475.0d3d12c9247a2b3e141f.js
assets/chunk.524.db8024bf66127c1bac18.js
assets/engine-vendor.js
assets/engine.js
assets/vendor.js
assets/vault.js
```

Download those and grep them, and the menu strings are literally in
there. The **Tools** list comes from the UI's own action table:

```javascript
const n = ["wrap", "lookup", "unwrap", "rewrap", "random", "hash"]
```

rendered capitalised, which is where **Wrap**, **Lookup**, **Unwrap**,
**Rewrap**, **Random** and **Hash** come from. The Transit key page's
actions are the same story — the bundle ships one component per action
(`vault/components/transit-key-action/encrypt`, `…/decrypt`,
`…/datakey`, `…/rewrap`, `…/sign`, `…/hmac`, `…/verify`, `…/export`).
I did not drive the GUI in this lab, because the lab is a headless
container with no browser, so the *layout* of the pages is inferred from
the bundle and the *labels* are quoted from it.

**What the GUI does not do, and why the CLI stays primary:**

- **No cubbyhole page.** The Tools list above is the complete set of
  `sys/` tools the UI exposes, and cubbyhole is not one of them. That is
  correct: a cubbyhole is scoped to one token, and there is no "your
  cubbyhole" concept in a multi-user UI.
- **No "trim" button.** The Transit key edit form exposes
  **Auto-rotation period**, **Allow deletion**, **Minimum decryption
  version** and **Minimum encryption version** — but there is no **Trim**
  action anywhere in the bundle. Destroying old key material is
  CLI/API-only, which is exactly the right place for an irreversible
  operation like that to live.
- **The Tools forms are conveniences, not the API.** The Tools → Random
  form sends `{bytes, format}` and defaults to 32 bytes / base64; Tools
  → Hash sends `{input, format, algorithm}` and defaults to `sha2-256`.
  They do not expose the `seal` / `all` entropy sources, they do not let
  you set the wrapping TTL except through the wrap form, and the response
  comes back as the form's own JSON — not the raw envelope. When you
  need a specific field, the CLI is faster.

> **Rule of thumb:** *use the GUI to explore and to confirm what exists.
> Use the CLI for anything you will have to do twice, anything that changes
> a key, and anything that appears in a runbook.*

---

## 10. Policies for the crypto tooling

Every endpoint in this module is an ACL path — but **not** all of them are
locked away. In OpenBao 2.7.1 the `default` policy is not the near-empty
policy that a lot of people assume it is. It grants a working set of
`sys/` paths to *every* token, including your application tokens:

```bash
$ bao policy read default
```

The parts of it that matter for this module:

```hcl
# Allow a token to manage its own cubbyhole
path "cubbyhole/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

# Allow a token to wrap arbitrary values in a response-wrapping token
path "sys/wrapping/wrap" {
    capabilities = ["update"]
}

# Allow a token to look up the creation time and TTL of a given
# response-wrapping token
path "sys/wrapping/lookup" {
    capabilities = ["update"]
}

# Allow a token to unwrap a response-wrapping token.
path "sys/wrapping/unwrap" {
    capabilities = ["update"]
}

# Allow general purpose tools
path "sys/tools/hash" {
    capabilities = ["update"]
}
path "sys/tools/hash/*" {
    capabilities = ["update"]
}
```

So a token that carries only your own application policy can already
hash a value, wrap a value, unwrap a value, and write to its own
cubbyhole. It **cannot** mint random bytes and it **cannot** touch
Transit. Those two are the ones that need an explicit grant.

Here is the denial, for real:

```bash
$ BAO_TOKEN=$DATA_PIPELINE_TOKEN bao write -format=json sys/tools/random/32 bytes=32
Error writing data to sys/tools/random/32: Error making API request.

URL: PUT http://127.0.0.1:9274/v1/sys/tools/random/32
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

And here is what the *same* token does with `sys/wrapping/wrap` — it
succeeds, because the `default` policy already granted it:

```bash
$ BAO_TOKEN=$DATA_PIPELINE_TOKEN bao write -format=json sys/wrapping/wrap text="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"
{
  "request_id": "",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": null,
  "warnings": null,
  "wrap_info": {
    "token": "s.9ATLJnFSmEEGCi5AbliP2WKD",
    "accessor": "0evJv5k0pwBV0zeJGk5bGQd3",
    "ttl": 300,
    "creation_time": "2026-10-21T18:59:56.703944121Z",
    "creation_path": "sys/wrapping/wrap",
    "wrapped_accessor": ""
  }
}
```

> **Production:** *if you do not want your application tokens holding
> `sys/wrapping/wrap` and `sys/tools/hash`, mint them with
> `-no-default-policy` and grant exactly what the service needs. Then
> re-check with `bao token capabilities` — the difference is one flag,
> and it is the difference between "the service can hash a value" and
> "the service can only read the one path it was given".*

A workable set of grants for Meridian AI:

```hcl
# meridian-ai / platform-operator : may create bootstrap credentials
path "sys/wrapping/wrap" {
  capabilities = ["create", "update"]
}

path "sys/wrapping/lookup" {
  capabilities = ["create", "update"]
}

# meridian-ai / platform-operator : may generate new service secrets
path "sys/tools/random/*" {
  capabilities = ["create", "update"]
}

# meridian-ai / webhook-gateway : may fingerprint inbound shared tokens
path "sys/tools/hash/*" {
  capabilities = ["create", "update"]
}

# meridian-ai / data-pipeline : may encrypt and decrypt PII, and nothing else
path "ai/transit/encrypt/pii-column-encryption" {
  capabilities = ["create", "update"]
}

path "ai/transit/decrypt/pii-column-encryption" {
  capabilities = ["create", "update"]
}

path "ai/transit/hmac/user-lookup-index" {
  capabilities = ["create", "update"]
}
```

Two rules to take away:

1. **The `sys/tools` and `sys/wrapping` paths are powerful.** Anyone who
   can call `sys/tools/random` can mint credentials; anyone who can call
   `sys/wrapping/wrap` can package any secret they can already read into a
   portable token. Grant them to the operator role, not to services.
2. **Grant the transit *operation* paths, not the key path.** `deny` on
   `ai/transit/keys/*` and `deny` on `ai/transit/export/*` is what stops
   your application from walking off with the key. Check it with
   `bao token capabilities` every time you change a policy.
3. **A glob on a path with a count in it needs the count.** The grant
   `path "sys/tools/random/*"` covers `sys/tools/random/32`, but *not*
   the count-less form `sys/tools/random` — the `*` has to match
   something. Verify both forms if you use them:

   ```bash
   $ bao token capabilities "$R" sys/tools/random/32
   create, update
   $ bao token capabilities "$R" sys/tools/random
   deny
   ```

---

## 11. What you learned

- [ ] `sys/tools/random` returns base64 or hex random bytes, and the URL
      segment beats the `bytes=` body field.
- [ ] `sys/tools/hash` takes **base64** input and returns a **hex**
      digest; it is unkeyed and supports SHA-2 and SHA-3.
- [ ] A hash is a fingerprint, not a password hash. Passwords need
      Argon2id/scrypt/bcrypt.
- [ ] `sys/wrapping/wrap` produces a single-use token; unwrapping it
      twice fails with `wrapping token is not valid or does not exist`.
- [ ] The payload key is literally whatever you typed: `text=` gives
      `text`, `-text=` gives `-text`.
- [ ] `token=` is a data field. A leading dash is a flag, and an unknown
      flag errors differently depending on its position.
- [ ] `lookup` does not consume a wrapping token; `rewrap` **does**.
- [ ] The wrapping TTL comes from the `X-Vault-Wrap-TTL` header. A `ttl=`
      in the body becomes part of the payload.
- [ ] `bao unwrap <token>` needs no OpenBao login: the wrapping token is
      the credential, and the server grants it the internal
      `response-wrapping` policy.
- [ ] Cubbyhole is per-token. Another token sees "No value found", not
      "permission denied".
- [ ] The `default` policy is **not** empty: it already grants
      `cubbyhole/*`, `sys/wrapping/wrap|lookup|unwrap` and
      `sys/tools/hash/*` to every token. Use `-no-default-policy` when you
      want a machine token that can only do one thing.
- [ ] Transit ciphertext is `vault:v<key version>:…` — self-describing.
- [ ] A Transit key has versions, floors (`min_decryption_version`,
      `min_encryption_version`) and a material floor
      (`min_available_version`).
- [ ] Rotation is one call. Rewrap re-encrypts old ciphertext server-side.
      Trim destroys old key material for good.
- [ ] `exportable` keys can have their raw material read out;
      non-exportable keys cannot. The `export/` and `backup/` paths are
      the sensitive ones — `deny` them in application policies.
- [ ] Datakeys are for bulk encryption. For a small table, just call
      `transit/encrypt` per row.
- [ ] The `bao write` CLI cannot send a batch; batch operations need the
      HTTP API with a real JSON array.
- [ ] Convergent encryption makes equality visible. Use a blind index
      (HMAC) when you need lookup without that leak.
- [ ] External Keys (2.7) is real but needs a KMS plugin, and the KMS
      plugins are not built in.
- [ ] There are eight good reasons not to reach for Transit, and a
      datakey plus local crypto is the usual answer for hot paths.

---

## 12. What's next

Your secrets are stored, scoped, and now also *transportable*, *generatable*,
*comparable* and *encryptable*. The missing piece is the last mile: how does
the `ai-harness` container actually get the Gemini key at boot, and how do
you prove the key is not sitting in the image, the environment, or
`/proc`? That is [Module 07 — App Integration](../07-app-integration/README.md),
where the AppRole login, the in-memory fetch, and the "prove it is gone"
checks close the loop on the `.env` file that started all of this.

After that, [Module 08 — Other Engines](../08-other-engines/README.md) takes
on PKI, SSH, TOTP and the Postgres database engine, and
[Module 09 — Production Hardening](../09-production-hardening/README.md)
locks the whole thing down.

---

## 13. Homework

Each of these is runnable in your own lab. Do them in order.

**1. Build a bootstrap-credential kit.**
Write a policy `bootstrap-issuer` granting only `sys/wrapping/wrap` and
`sys/tools/random`. Create a token with it. Using only that token, mint a
32-byte random value and wrap it. Prove with `bao token capabilities` that
the token cannot read KV, cannot list mounts, and cannot rotate any transit
key. Write down the exact commands you would put in the platform-operator
runbook.

**2. Break the wrapping TTL three different ways.**
Show that (a) `ttl=60` in the body does not change the token's lifetime and
appears in the payload, (b) `X-Vault-Wrap-TTL: 60` does change it, and (c)
`X-Vault-Wrap-TTL: 0` is rejected. Then create a token with a 5-second TTL,
wait 8 seconds, and capture the exact error.

**3. Prove the cubbyhole is private.**
Create two tokens with different policies. Write a different value into each
token's `cubbyhole/meridian/probe`. Show that each token can read only its
own, and that a third token *without* `cubbyhole/*` gets a 403 rather than a
404. Explain in two sentences why that difference matters.

**4. Rotate a transit key without losing data.**
Create a key, encrypt ten values, rotate, encrypt ten more. Show the
ciphertext prefix changing from `vault:v1:` to `vault:v2:`. Rewrap all ten
old values and show they now carry `vault:v2:`. *Then* set
`min_decryption_version=2` and show that an un-rewrapped `vault:v1:`
ciphertext is refused with
`ciphertext or signature version is disallowed by policy (too old)`. Finish
with `trim` and show the version 1 entry gone from the key map.

**5. Write the batch encryptor.**
The `bao` CLI cannot send a batch. Write a Python function using `urllib`
that takes a list of strings and returns a list of ciphertexts in one
OpenBao call. Verify it against a list of 5 values and show the order is
preserved. Then work out how many OpenBao calls your service makes per
minute at 500 rows/second, and decide whether you need a datakey instead.

**6. Decide the PII column design and defend it.**
Your `meridian_ai.users` table needs email lookup by exact value, plus
"count customers per domain" analytics. Compare three designs: (a) plain
transit ciphertext, (b) convergent encryption, (c) transit ciphertext plus
an HMAC blind index. For each, say what it leaks and whether the analytics
query still works. Then implement your choice in the app and show the
lookup query returning the right row.

**7. Write the "when NOT to use transit" rules for your own team.**
Read Section 7.14 and add three rules that are specific to Meridian AI's
stack — FastAPI, LangChain, Gemini, Postgres, Redis, Keycloak. For each,
name the concrete thing in this repository that would tempt someone to
break the rule.

**8. External Keys, honestly.**
Install a KMS seal plugin in a *separate* lab — do not do this on a
production cluster — and try to create
`sys/external-keys/configs/<config>` pointing at it. Then create a Transit
key of type `external-key` that references it, encrypt and decrypt a value,
and record exactly which steps worked and which did not. If you cannot get a
KMS plugin working, write down the exact error you hit; that is a valid
answer to this homework and a useful piece of documentation for whoever
tries next.
