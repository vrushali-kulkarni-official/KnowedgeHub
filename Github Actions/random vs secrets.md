In Python, the `random` module and the `secrets` module serve very different purposes. Choosing the wrong one can introduce serious security vulnerabilities.

| Feature        | `random`                           | `secrets`                         |
| -------------- | ---------------------------------- | --------------------------------- |
| Purpose        | Simulations, games, statistics     | Passwords, tokens, authentication |
| Randomness     | Pseudorandom (deterministic)       | Cryptographically secure          |
| Predictable?   | Yes, if the seed or state is known | Designed to be unpredictable      |
| Security       | ❌ Not secure                       | ✅ Secure                          |
| Speed          | Faster                             | Slightly slower                   |
| Uses OS CSPRNG | No                                 | Yes                               |

## 1. `random` module

The `random` module generates **pseudo-random numbers (PRNG)**.

Internally it uses the **Mersenne Twister** algorithm.

Characteristics:

- Extremely fast

- Produces statistically random numbers

- Generates the same sequence when given the same seed

- State can potentially be recovered if enough outputs are observed

Example:

```python
import random

print(random.randint(1, 100))
print(random.random())
```

If someone does:

```python
random.seed(42)
```

every execution gives exactly the same numbers.

```python
import random

random.seed(42)

print(random.randint(1,100))
print(random.randint(1,100))
print(random.randint(1,100))
```

Output every time:

```
82
15
4
```

This predictability is useful for:

- scientific simulations

- testing

- games

- Monte Carlo methods

It is **not suitable for security**.

---

## 2. `secrets` module

The `secrets` module was introduced specifically for **security-sensitive randomness**.

It gets randomness from the operating system's **Cryptographically Secure Pseudo-Random Number Generator (CSPRNG)**.

On Linux, this is backed by secure OS entropy sources (e.g., `getrandom()`).

Example:

```python
import secrets

print(secrets.randbelow(100))
```

Every value is generated from secure entropy and is intended to be infeasible to predict.

---

# Why `random` is insecure

Suppose you generate password reset tokens like this:

```python
import random

token = str(random.randint(100000, 999999))
```

An attacker who can infer or recover the PRNG state may be able to predict future tokens.

Similarly:

```python
random.seed(time.time())
```

If the attacker can estimate when the server started, they may brute-force likely seeds and reproduce the sequence.

---

# Secure alternative

```python
import secrets

token = secrets.token_hex(32)
```

Example output:

```
8f95d62451a774e1b7...
```

Even observing many previous tokens should not let an attacker predict future ones.

---

# Common functions

## `random`

```python
random.random()
```

Returns:

```
0.3453432
```

---

```python
random.randint(1,10)
```

Returns integer from 1–10.

---

```python
random.choice(items)
```

Chooses one item.

---

```python
random.shuffle(list)
```

Shuffles a list.

---

## `secrets`

### Random integer

```python
secrets.randbelow(100)
```

Produces an integer in `[0, 99]`.

---

### Random choice

```python
import secrets

color = secrets.choice(
    ["red", "green", "blue"]
)
```

---

### Hex token

```python
token = secrets.token_hex(16)
```

Example:

```
e9fbc4ab3b2f...
```

A 16-byte token becomes a 32-character hexadecimal string.

---

### URL-safe token

```python
token = secrets.token_urlsafe(32)
```

Example:

```
O6Y4k7YjTf8w...
```

Useful for:

- password reset links

- email verification links

- API keys

---

### Random bytes

```python
token = secrets.token_bytes(32)
```

Returns 32 cryptographically secure random bytes.

---

# Comparing password generation

### Incorrect

```python
import random
import string

password = ''.join(
    random.choice(string.ascii_letters)
    for _ in range(12)
)
```

This password may be predictable if the PRNG state is compromised.

---

### Correct

```python
import secrets
import string

alphabet = string.ascii_letters + string.digits

password = ''.join(
    secrets.choice(alphabet)
    for _ in range(12)
)
```

---

# Typical use cases

### Use `random` for:

- Games

- Dice rolls

- Card shuffling

- Simulations

- Machine learning experiments

- Testing

- Random sampling

- Monte Carlo methods

---

### Use `secrets` for:

- Password generation

- Password reset tokens

- Session IDs

- CSRF tokens

- JWT signing secrets (for generating the secret)

- API keys

- OAuth state parameters

- Email verification links

- Cryptographic nonces

- Temporary access codes

---

# Performance

`random` is generally faster because it uses an in-memory deterministic algorithm.

`secrets` is slightly slower because it relies on the operating system's cryptographically secure random source. For almost all security-related tasks, this overhead is negligible compared to the security benefits.

---

# Best practices for secure coding

- **Never** use `random` for anything related to authentication, authorization, encryption, or secret generation.

- Use `secrets` for all security-sensitive randomness.

- Avoid manually seeding random values for security purposes.

- Generate tokens with sufficient entropy (e.g., `secrets.token_urlsafe(32)` or `secrets.token_hex(32)` for most applications).

- Keep generated secrets out of source code; store long-lived secrets in a secure secret manager or environment variables.

- Use well-established cryptographic libraries rather than implementing your own cryptographic algorithms.

### Rule of thumb

- **Need randomness for functionality or simulations?** → Use `random`.

- **Need randomness that protects users or data?** → Use `secrets`.

If there's any chance an attacker could benefit from predicting the value, use `secrets`.
