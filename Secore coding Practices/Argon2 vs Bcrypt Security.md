If you're starting a new project in **2026**, the recommendation is:

* ❌ **Do not choose bcrypt for new applications** unless you must maintain compatibility with an existing system.
* ✅ **Use Argon2id**. It is the password hashing algorithm recommended by security experts, including the Password Hashing Competition (PHC), and is widely recommended by organisations such as OWASP.

Let's understand why.

---

# Evolution of Password Hashing

```
Plain Password
      │
      ▼
MD5
      │
      ▼
SHA1
      │
      ▼
SHA256
      │
      ▼
PBKDF2
      │
      ▼
bcrypt
      │
      ▼
scrypt
      │
      ▼
Argon2 (Winner)
```

Every generation solved weaknesses of the previous one.

---

# Why MD5 and SHA were bad

Imagine storing

```
password123
```

If you store

```
SHA256(password123)
```

SHA256 is designed to be **very fast**.

Modern GPUs can compute **billions of SHA256 hashes per second**.

Attackers simply guess passwords until one matches.

---

# PBKDF2 solved speed

PBKDF2 intentionally repeats hashing thousands or millions of times.

Example

```
password
      │
SHA256
      │
SHA256
      │
SHA256
      │
...
      │
600,000 iterations
```

This slows attackers.

Problem:

PBKDF2 mostly consumes CPU.

GPUs still perform PBKDF2 efficiently.

---

# bcrypt solved GPU attacks (partially)

bcrypt introduced:

* configurable work factor
* automatic salting
* Blowfish-based expensive key schedule

Example

```
password
      │
random salt
      │
Blowfish key expansion
      │
2^cost rounds
      │
hash
```

---

# Why bcrypt became insufficient

bcrypt is still considered secure if configured correctly, but it has several limitations.

## 1. Very little memory usage

bcrypt uses only around **4 KB** internally.

A GPU can therefore run millions of bcrypt computations simultaneously.

Example

GPU memory

```
24 GB
```

Each bcrypt

```
4 KB
```

GPU can execute enormous numbers of parallel hashes.

bcrypt slows CPUs,

but GPUs remain very effective.

---

## 2. Cannot scale memory

Increasing bcrypt cost only increases CPU time.

```
Cost 10

CPU ↑

Memory →
```

You cannot tell bcrypt

> Use 128 MB RAM.

It simply cannot.

---

## 3. Password length limitation

bcrypt effectively uses only the first **72 bytes** of the password. Extra bytes are ignored.

Example

```
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaA
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaB
```

If they differ only after byte 72, bcrypt treats them as the same password.

Argon2 does not have this practical limitation.

---

## 4. Older design

bcrypt dates from **1999**.

GPU hardware has improved enormously since then.

Argon2 was designed with modern hardware in mind.

---

# Why scrypt was created

scrypt introduced

```
CPU
+
Memory
```

Now attackers need both.

Instead of

```
CPU only
```

they need

```
CPU
RAM
Bandwidth
```

which is much harder to parallelise.

---

# Argon2 improves further

Argon2 won the Password Hashing Competition in **2015**.

It has three variants.

```
Argon2d
Argon2i
Argon2id
```

---

# Which Argon2 should you use?

Always

```
Argon2id
```

Why?

It combines

```
Argon2i
+
Argon2d
```

giving protection against both:

* side-channel attacks
* GPU cracking

---

# Latest Argon2 version

Current specification:

```
Argon2 Version 1.3
```

Internally this is stored as

```
v = 19
```

You'll often see hashes like:

```
$argon2id$v=19$m=65536,t=3,p=4$...
```

`v=19` corresponds to Argon2 specification version 1.3.

---

# How Argon2 works (algorithm)

Suppose password

```
hunter2
```

Step 1

Generate random salt

```
16 bytes

7f8a2c91...
```

---

Step 2

Mix together

```
password
salt
parameters
secret
```

---

Step 3

Allocate memory

Suppose

```
64 MB
```

It literally reserves

```
□□□□□□□□□□□□□□□□□□□□□□□□
64 MB memory
□□□□□□□□□□□□□□□□□□□□□□□□
```

---

Step 4

Fill memory

Each block depends on previous blocks.

```
Block1
 ↓
Block2
 ↓
Block3
 ↓
Block4
```

Later blocks reference earlier blocks, making computation memory-intensive.

---

Step 5

Repeat multiple passes

```
Pass 1
Pass 2
Pass 3
```

Each pass revisits and mixes memory.

---

Step 6

Compress final state

Result

```
argon2 hash
```

---

# Why memory matters

Suppose server uses

```
64 MB
```

per hash.

Attacker wants

```
1,000,000 hashes
```

They now need roughly

```
64 TB RAM
```

to compute them fully in parallel.

This dramatically raises the cost of GPU or ASIC attacks.

---

# Parameters

Argon2 has three primary tuning parameters.

## Memory Cost (`m`)

```
m = 65536
```

means

```
64 MB
```

More memory = harder for attackers.

---

## Time Cost (`t`)

Number of passes.

Example

```
t = 3
```

```
Memory

Pass1
Pass2
Pass3
```

More passes = slower hashing.

---

## Parallelism (`p`)

Number of lanes/threads.

```
p = 4
```

Uses four lanes internally.

Choose a value that makes sense for your server's CPU resources.

---

# Production recommendations

There is no single perfect configuration; choose parameters that make verification take an acceptable amount of time on your production hardware. A commonly used starting point for interactive logins is:

| Parameter   | Recommended starting point                   |
| ----------- | -------------------------------------------- |
| Variant     | Argon2id                                     |
| Version     | v=19                                         |
| Salt        | 16 bytes (128 bits) or more                  |
| Memory      | 64–256 MB                                    |
| Time        | 2–4 passes                                   |
| Parallelism | 1–4 (often matching available CPU resources) |
| Hash length | 32 bytes                                     |
| Salt source | Cryptographically secure RNG                 |

Then benchmark on your deployment hardware and adjust so that a password verification typically takes around **100–500 ms** under normal load. Higher values improve resistance to offline attacks but also increase CPU and memory usage on your servers.

---

# Does Argon2 use salting?

Yes.

Every password receives a unique random salt.

Example

```
password
salt1
```

↓

```
hash1
```

Same password

```
password
salt2
```

↓

```
hash2
```

Different salt

Different hash

Always.

This prevents rainbow table attacks and ensures that identical passwords produce different stored hashes.

---

# Python implementation

The most commonly used library is **argon2-cffi**.

Install

```bash
pip install argon2-cffi
```

---

## Hashing

```python
from argon2 import PasswordHasher

ph = PasswordHasher()

hashed = ph.hash("my_secret_password")

print(hashed)
```

Example output

```
$argon2id$v=19$m=65536,t=3,p=4$...
```

Everything needed to verify the password—including the algorithm, version, parameters, salt, and hash—is encoded into this single string.

---

## Verification

```python
from argon2 import PasswordHasher

ph = PasswordHasher()

stored_hash = ph.hash("password123")

ph.verify(stored_hash, "password123")
```

Returns

```
True
```

or raises an exception if verification fails.

---

## Recommended configuration

```python
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,   # 64 MB (value is in KiB)
    parallelism=4,
    hash_len=32,
    salt_len=16,
)
```

---

## Checking whether a stored hash should be upgraded

As hardware improves, you may increase your Argon2 parameters. The library can tell you whether an existing hash should be replaced after a successful login.

```python
from argon2 import PasswordHasher

ph = PasswordHasher()

stored_hash = get_hash_from_database()

if ph.verify(stored_hash, password):
    if ph.check_needs_rehash(stored_hash):
        new_hash = ph.hash(password)
        save_hash_to_database(new_hash)
```

This lets you migrate users to stronger settings transparently over time.

---

# What is stored in the database?

You store **only one string**:

```
$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
```

It contains:

* Algorithm (`argon2id`)
* Version (`v=19`)
* Memory cost (`m`)
* Time cost (`t`)
* Parallelism (`p`)
* Random salt
* Derived hash

You **do not** need a separate salt column. The salt is not secret and is stored alongside the hash by design.

---

# Argon2 vs bcrypt

| Feature                      | bcrypt               | Argon2id                          |
| ---------------------------- | -------------------- | --------------------------------- |
| Year introduced              | 1999                 | 2015                              |
| PHC winner                   | No                   | Yes                               |
| Automatic salting            | ✅                    | ✅                                 |
| Memory-hard                  | ❌ (~4 KB fixed)      | ✅ Configurable                    |
| Adjustable memory            | ❌                    | ✅                                 |
| Adjustable CPU cost          | ✅                    | ✅                                 |
| Parallelism control          | ❌                    | ✅                                 |
| 72-byte password limit       | ✅                    | ❌ (no comparable practical limit) |
| Recommended for new projects | Legacy compatibility | ✅ Yes                             |

## Recommendation for a FastAPI application

For a new FastAPI application in 2026:

* Use **Argon2id** via `argon2-cffi`.
* Start with approximately `memory_cost=65536` (64 MiB), `time_cost=3`, and `parallelism` tuned to your server.
* Benchmark on production hardware and adjust to balance security and login latency.
* Use `check_needs_rehash()` to upgrade hashes over time without forcing password resets.
* Never invent your own salting scheme or store plaintext passwords; let the library generate a unique random salt for every password and store the complete encoded Argon2 hash string.
