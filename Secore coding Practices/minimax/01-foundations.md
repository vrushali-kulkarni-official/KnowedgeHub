# Part 1 — Foundations of Secure Coding
### Before any code, the mental models

This part is the most important. If you skip it, the rest of the course will feel like a list of fixes. With it, you'll be able to invent the fix yourself.

---

## 1.1 The CIA Triad (and the extra letters)

The simplest model of information security. Every vulnerability, every defense, every control in this course is trying to protect at least one of these three things.

```
        Confidentiality
              ▲
             / \
            /   \
           /     \
          /  YOU  \
         /  WANT   \
        /  TO      \
       / PROTECT   \
      ▼─────────────▼
 Integrity      Availability
```

### Confidentiality — *only the right people can read it*
- A patient's medical record is read by their doctor, not by another patient.
- An attack that breaks it: **data breach, IDOR, information disclosure**.
- Defenses: **encryption at rest, encryption in transit, access control, redacting logs**.

### Integrity — *data hasn't been tampered with*
- A "transfer $100" request actually transfers $100, not $100,000, and to the account you typed, not to the attacker's.
- An attack that breaks it: **SQL injection, request tampering, MITM**.
- Defenses: **parameterized queries, signed requests, checksums, audit logs**.

### Availability — *the system works when you need it*
- Your API responds in 200ms under normal load, and still responds under attack.
- An attack that breaks it: **DDoS, resource exhaustion, infinite loops in input parsing**.
- Defenses: **rate limits, timeouts, input size caps, queues, autoscaling**.

### The "extra" letters security pros add

- **Authenticity** — *the data really came from who it says it came from.* (HMAC, digital signatures, JWTs)
- **Non-repudiation** — *the sender can't deny sending it later.* (signed audit logs)
- **Privacy** — *the right to be forgotten, data minimization, lawful basis for processing.* (GDPR, CCPA)

> **Mental model:** when you read a new feature ticket, ask yourself, "Which of CIA does this feature protect, and what is the *threat* against each one?" If you can't answer, the ticket isn't done.

---

## 1.2 Trust boundaries — the most important diagram you'll ever draw

A **trust boundary** is the line between code that you trust and code that you don't. Crossing a trust boundary is where most bugs are born.

```
   Untrusted world          │        Trusted world (your process)
   ─────────────────────────┼────────────────────────────────────
   HTTP request body        │        Pydantic model
   URL path segment         │        function argument
   File on disk from user   │        bytes in memory
   Third-party API response │        dict in your code
   Environment variable     │        constant
   Database cell (could be  │        Python str
   anything — admins are    │
   users too)               │
```

**Rule:** every byte that crosses a trust boundary from left to right must be **validated, normalized, and often authenticated**, before it touches anything on the right.

### Example in FastAPI

```python
# ❌ Untrusted data touches trusted code without validation
@app.get("/users/{user_id}")
def get_user(user_id: str):                       # ← left side: HTTP path
    row = db.execute(f"SELECT * FROM users WHERE id = {user_id}")  # ← right side: SQL
    return row
```

```python
# ✅ Validated at the boundary
@app.get("/users/{user_id}")
def get_user(user_id: int):                        # ← FastAPI validates it's an int
    row = db.execute(select(User).where(User.id == user_id))      # ← parameterized
    return row
```

Two trust-boundary crossings were fixed in those four lines. We'll do this all course.

---

## 1.3 The 10 principles of secure coding (memorize these)

These are the rules. Every fix in this guide is an instance of one of them.

| # | Principle | Plain English | One-liner in code |
|---|-----------|---------------|-------------------|
| 1 | **Validate input** | Never trust the caller | Pydantic models on every endpoint |
| 2 | **Encode output** | Never trust your data when it leaves you | `html.escape`, `json.dumps`, parameterized SQL |
| 3 | **Authenticate** | Prove who they are | OAuth2, mTLS, signed JWT |
| 4 | **Authorize** | Prove they *can* | RBAC, ABAC, ownership checks |
| 5 | **Least privilege** | Give the minimum | App's DB user can't DROP TABLE |
| 6 | **Defense in depth** | Don't rely on one wall | Validate + escape + DB constraints + WAF |
| 7 | **Fail closed** | When in doubt, deny | Default `is_admin = False` |
| 8 | **Keep it simple** | Auditable beats clever | No clever meta-programming in auth code |
| 9 | **Log security events** | If you can't see it, you can't fix it | Log every auth event with correlation ID |
| 10 | **Patch your deps** | Most breaches are known CVEs | `pip-audit`, Dependabot, Renovate |

> **Mental model:** every fix you'll see in this course has a number from this table. When you write a new fix, name the number out loud. ("This is principle #5: the JWT token is scoped to the user's tenant, so even if a token leaks, it can't read another tenant's data.")

---

## 1.4 Threat modeling — STRIDE in 5 minutes

Before writing a single line of code, you should be able to answer: "What could go wrong with this endpoint?"

**STRIDE** is a checklist invented at Microsoft. Run through it for every new feature.

| Letter | Threat | One-line question | FastAPI example |
|--------|--------|-------------------|-----------------|
| **S**poofing | Pretending to be someone else | Can a user send a request as another user? | JWT verification, mTLS |
| **T**ampering | Changing data in transit/at rest | Can a user change the price in the request body? | Signed payloads, DB constraints |
| **R**epudiation | Denying an action later | Can a user later say "I never sent that"? | Append-only audit log, signed logs |
| **I**nformation disclosure | Leaking data | Can one tenant see another's data? | Row-Level Security, scoped queries |
| **D**enial of service | Knocking the service over | Can a user cause a 10-second blocking call? | Timeouts, async, rate limits |
| **E**levation of privilege | Becoming admin | Can a regular user become admin? | RBAC, `is_admin` checks on every privileged op |

### The 4-question framework (lighter than STRIDE, use it for every PR)

1. What data does this code touch? (Sensitivity classification)
2. Who is allowed to touch it? (Authorization)
3. How is it coming in? (Validation)
4. What could go wrong? (Failure modes — including "the DB is down", "the user is malicious", "the user is logged in as a different tenant")

If your PR review can't answer all four, the PR isn't done.

---

## 1.5 The cost-of-a-bug curve (a motivating story)

```
Cost
 ▲
 │                                          ╭─── Breach + GDPR fine
 │                                       ╭──┤
 │                                    ╭──┘  │
 │                                 ╭──┘     │
 │                              ╭──┘        │
 │                           ╭──┘           │
 │                        ╭──┘              │
 │                     ╭──┘                 │
 │                  ╭──┘                    │
 │               ╭──┘                       │
 │            ╭──┘                          │
 │         ╭──┘                             │
 │      ╭──┘                                │
 │   ╭──┘                                   │
 └──┴──────────────────────────────────────────▶ Time from commit
  design   dev   review   prod   prod   prod
```

The cost grows roughly 10× per stage. A bug fixed at design time costs a 5-minute conversation. The same bug fixed in production costs a Saturday, a post-mortem, and maybe a fine. **This is why the OWASP Top 10 exists** — to find these bugs at design time, not at breach time.

---

## 1.6 "But I'm using a framework, so I'm safe, right?"

No. Frameworks make the *easy* path the *secure* path. They don't make the impossible impossible. Here are real ways FastAPI users ship insecure code every day:

| You think | Reality |
|-----------|---------|
| "Pydantic validates, so input is safe." | Pydantic validates *type and shape*. It does not check *semantics* — `is_admin=False` is a valid bool the user can still send unless you have a separate schema for trusted input. |
| "SQLAlchemy parameterizes, so I'm SQLi-safe." | True *only* if you use the ORM expression language or `text(..., bindparams(...))`. The moment you write `f"... {user_input} ..."` into a `text()` call, you're back to 2003. |
| "JWT is signed, so it's tamper-proof." | Signed ≠ encrypted. The payload is *base64*. Anyone can read it. And if you accept `alg: none`, anyone can forge one. |
| "I have HTTPS, so I'm safe in transit." | You still need HSTS, certificate pinning in some apps, and you still need to verify TLS *outbound* (don't disable cert verification "just for testing"). |
| "Docker isolates me." | Containers are a process boundary, not a security boundary. `--privileged`, mounting the Docker socket, or running as root inside the container defeats it. |

**A framework is a seatbelt. You still have to wear it, and you still have to drive carefully.**

---

## 1.7 The vocabulary — words you'll see 100 times in this guide

| Term | Meaning | Example |
|------|---------|---------|
| **CVE** | Common Vulnerabilities and Exposures — a public ID for a known bug | `CVE-2024-12345` |
| **CWE** | Common Weakness Enumeration — a *category* of bug | `CWE-89` is "SQL Injection" |
| **CVSS** | Common Vulnerability Scoring System — a 0–10 severity score | CVSS 9.8 = critical |
| **Exploit** | Code that *uses* a vulnerability | `curl 'http://.../?id=1 OR 1=1'` |
| **Payload** | The malicious data sent across a trust boundary | `' OR 1=1 --` |
| **Sink** | The dangerous function that receives untrusted data | `db.execute()`, `eval()`, `subprocess.run(shell=True)` |
| **Source** | Where untrusted data comes from | HTTP body, query string, file upload, env var |
| **Taint analysis** | Tracking data from source to sink automatically | Semgrep, CodeQL |
| **Zero-day** | A bug known to attackers *before* a patch exists | Log4Shell was a 0-day |
| **POC** | Proof of Concept — minimal code that demonstrates a bug | A 10-line `curl` that reads `/etc/passwd` |
| **Mitigation** | A change that reduces the impact or likelihood | Input validation, escaping |
| **Remediation** | A change that *fixes* the root cause | Switching from `f-string` SQL to parameterized queries |
| **RCE** | Remote Code Execution — attacker runs code on your server | `eval(request.body)` |
| **SSRF** | Server-Side Request Forgery — your server makes a request the attacker chose | The `image_url` param hitting `http://169.254.169.254/...` (AWS metadata) |
| **XSS** | Cross-Site Scripting — attacker injects JS into your page | A comment field that allows `<script>` |
| **CSRF** | Cross-Site Request Forgery — a logged-in user's browser is tricked | A hidden form on evil.com that hits your bank |
| **IDOR** | Insecure Direct Object Reference — `GET /invoice/123` works for *any* user | Changing 123 to 124 to read someone else's invoice |
| **SSRF/RCE/IDOR/etc.** | Memorize the acronyms; security culture is acronym-heavy | |

---

## 1.8 A mental warm-up exercise

Read this FastAPI endpoint and find **five** security smells. Don't worry about the names yet, just notice what feels off.

```python
from fastapi import FastAPI, Request
import os, pickle, hashlib, subprocess

app = FastAPI()
SECRET = "mysecret"
API_KEYS = {"alice": "abc123"}

@app.post("/login")
def login(req: Request):
    body = await req.json()
    user = body["user"]
    pw = body["pw"]
    # Check password
    if hashlib.md5(pw.encode()).hexdigest() == open(f"/data/{user}.pw").read():
        return {"token": f"{user}:{SECRET}"}

@app.post("/run")
def run(req: Request):
    body = await req.json()
    cmd = body["cmd"]
    if body.get("api_key") in API_KEYS:
        return {"out": subprocess.check_output(cmd, shell=True)}

@app.get("/load")
def load(name: str):
    with open(f"/data/{name}.pkl", "rb") as f:
        return pickle.load(f)
```

Take 60 seconds. Write down what you saw. Then read on.

### What you should have spotted

1. **Plaintext passwords on disk**, hashed with **MD5** (broken since 2004).
2. **String-equality token** — no signing, no expiry, no integrity.
3. **`subprocess.check_output(..., shell=True)`** with user input — full RCE.
4. **API key checked against a dict in source** — keys never rotate, are visible in git, and `body.get("api_key") in API_KEYS` is timing-vulnerable.
5. **`pickle.load` on a user-controlled path** — arbitrary code execution.
6. Bonus: **path traversal** in both `f"/data/{name}.pkl"` and `f"/data/{user}.pw"` — `name="../../etc/passwd"` reads outside `/data`.

We'll fix every one of these — and the categories they belong to — in the next part.

---

## 1.9 What to do before Part 2

1. Read the warm-up code one more time and confirm you can name *which* principle from §1.3 each smell breaks.
2. Install the dev dependencies (see the `00-README.md`).
3. Make a `~/labs` directory — every code sample in this course lives there. We'll come back to it in Part 5.

Open `02-owasp-2021.md` next.
