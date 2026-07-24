# Part 8 — Tools, Libraries, and the Pre-Deployment Checklist
### The complete toolbox — and a checklist you can run on every PR

> The last file. This is your reference: what tool to reach for, what library to install, and the one-page checklist that goes on the wall next to your monitor.

---

## 8.1 The tool taxonomy

There are roughly seven kinds of security tools. Knowing which kind you need is half the battle.

| Kind | Question it answers | When in the lifecycle |
|------|---------------------|----------------------|
| **SAST** (Static Application Security Testing) | "Does this code have patterns known to be vulnerable?" | Write-time, pre-commit, PR, CI |
| **SCA** (Software Composition Analysis) | "Do my dependencies have known CVEs?" | PR, CI, daily |
| **Secret scanning** | "Did anyone commit a secret?" | Pre-commit, PR, daily |
| **DAST** (Dynamic Application Security Testing) | "If I send malicious traffic, does the running app break?" | Staging, nightly |
| **IAST** (Interactive AST) | "Inside a running app, which sinks are reachable from untrusted input?" | Staging |
| **Container/IaC scanning** | "Is my image, K8s manifest, or Terraform config safe?" | Build, pre-deploy |
| **RASP** (Runtime Application Self-Protection) | "Block the attack as it happens in production?" | Runtime |

A mature app uses **at least one tool from each kind**.

---

## 8.2 SAST — code-pattern scanners

### Bandit (Python-only, free, PyCQA)
```bash
pip install bandit
bandit -r myapp/                    # recursive
bandit -r myapp/ -f json -o bandit.json
bandit -r myapp/ -lll                # only medium + high severity
```

What it catches: `eval`, `exec`, `pickle`, `yaml.load`, `subprocess shell=True`, `assert` in prod, `hashlib.md5`, `random` for crypto, `try/except: pass`, hardcoded passwords, `requests verify=False`, and ~50 more.

What it doesn't catch: business-logic flaws, IDOR, missing authz, complex taint flows.

### Semgrep (multi-language, free for OSS, paid for pro)
```bash
pip install semgrep
semgrep --config=auto              # Semgrep's curated rules
semgrep --config=p/python          # Python-specific
semgrep --config=p/owasp-top-ten   # OWASP-mapped
semgrep --config=p/fastapi         # FastAPI-specific
semgrep --config=p/security-audit
semgrep --config=p/secrets
```

What it catches: everything Bandit does, plus inter-procedural taint analysis ("user input from this handler flows into this SQL query"), JWT issues, XSS, SSRF, IDOR patterns, and 1000+ more. Pro version adds auto-fix.

### CodeQL (GitHub-native, free for public repos)
```bash
# GitHub Action: github/codeql-action
- uses: github/codeql-action/init@v3
  with: { languages: python }
- uses: github/codeql-action/analyze@v3
```

What it catches: deep data-flow analysis. Best in class for finding real SQLi/XSS. Slower than Semgrep, but more thorough.

### SonarQube / SonarCloud
- Best for: combined code quality + security dashboard.
- Heavier than Semgrep but the trend tracking is great.

### Snyk Code
- AI-aware SAST.
- Free tier for OSS and small teams.
- Catches the kinds of bugs a junior dev would miss.

### Pyre / Pyright (type checkers, not security, but they catch bugs)
- Not security tools, but `pyright --strict` catches a class of bugs (e.g., `Optional` not checked) that often correlate with security issues.

---

## 8.3 SCA — dependency scanners

### pip-audit (PyPA, free, official)
```bash
pip install pip-audit
pip-audit                        # scan current env
pip-audit -r requirements.txt
pip-audit -r requirements.txt --fix   # auto-upgrade (careful)
```

Catches CVEs in your installed packages. Uses the OSV database.

### Safety (`safety scan`, free tier)
```bash
pip install safety
safety scan                      # uses Safety DB (commercial but has free tier)
safety check -r requirements.txt
```

### Snyk Open Source
```bash
npm install -g snyk
snyk auth
snyk test                        # free
snyk monitor                     # continuous monitoring
```

Best-in-class UX, broad database, free for OSS.

### OSV-Scanner (Google, free)
```bash
go install github.com/google/osv-scanner/cmd/osv-scanner@latest
osv-scanner -r requirements.txt
```

Backed by Google's OSV database (open).

### Dependabot / Renovate
- **Dependabot** is built into GitHub. Free. Auto-PRs for new versions / CVEs.
- **Renovate** is more configurable. Better for monorepos.

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    labels: ["dependencies", "security"]
    open-pull-requests-limit: 10
    groups:
      production:
        dependency-type: "production"
      development:
        dependency-type: "development"
```

### Socket.dev
- Catches **malicious** packages, not just CVEs.
- The xz-utils backdoor, the event-stream incident, the colors.js sabotage — Socket.dev flags these *before* they're in the CVE database.
- Free for OSS.

---

## 8.4 Secret scanners

### gitleaks (free, fast)
```bash
brew install gitleaks
gitleaks detect --source . --verbose
```

Pre-commit hook:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

### trufflehog (free, deeper)
```bash
docker run --rm -v "$PWD:/repo" trufflesecurity/trufflehog git file:///repo
```

Catches more than gitleaks, including high-entropy strings.

### detect-secrets (Yelp, free)
```yaml
# .pre-commit-config.yaml
- repo: https://github.com/Yelp/detect-secrets
  rev: v1.4.0
  hooks:
    - id: detect-secrets
      args: ['--baseline', '.secrets.baseline']
```

### GitHub secret scanning
- Built into GitHub. Auto-revokes tokens for known providers.
- Free for public repos, paid for private.

---

## 8.5 DAST — black-box scanners

### OWASP ZAP (free, the standard)
```bash
docker run -t owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000
docker run -t owasp/zap2docker-stable zap-full-scan.py -t http://localhost:8000
```

Active scan against a running app. Catches: missing security headers, common XSS, common SQLi, path traversal, exposed debug endpoints.

### Burp Suite (free + paid)
- The industry standard for manual pen-testing.
- Burp Scanner for automated.
- Extensions for everything.

### nuclei (ProjectDiscovery, free)
```bash
nuclei -u http://localhost:8000 -t cves/ -t misconfiguration/
```

Templates for known CVEs and misconfigurations. Fast, low-noise.

### wapiti (free, Python)
- Open-source web vuln scanner.

### SQLMap (free, for SQLi specifically)
```bash
sqlmap -u "http://localhost:8000/users?name=alice" --batch
```

---

## 8.6 Container & IaC scanning

### Trivy (Aqua, free)
```bash
trivy image myapp:latest                 # scan image
trivy fs .                               # scan filesystem
trivy config k8s/                        # scan k8s manifests
trivy repo https://github.com/me/myapp   # scan git repo
trivy iac terraform/                     # scan Terraform
```

Catches: OS CVEs, package CVEs, misconfigurations, hardcoded secrets, IaC drift.

### Grype (Anchore, free)
```bash
grype myapp:latest
```

### Clair (Quay, free)
- For K8s admission controllers.

### Kubescape (ARMO, free)
```bash
kubescape scan
```

### tfsec (free, now part of Trivy)
- For Terraform.

### checkov (free, by Bridgecrew/Prismacloud)
```bash
checkov -d terraform/
checkov -d k8s/
```

### Snyk Container / IaC
- The paid version is great. Free tier is limited.

---

## 8.7 Runtime — RASP, WAF, IDS

### ModSecurity + OWASP CRS (the WAF standard)
- NGINX: `ModSecurity-nginx`
- Apache: built-in
- Reverse proxy mode: docker image

### Cloud WAFs
- **AWS WAF** + managed rule sets
- **Cloudflare WAF**
- **Azure WAF**
- **GCP Armor**

### Falco (CNCF, free)
- Runtime anomaly detection for containers/k8s.
- "A process spawned a shell inside a container" → alert.
- "A file in /etc was modified" → alert.

### tracee (Aqua, free)
- eBPF-based runtime security for containers.

---

## 8.8 Logging, monitoring, error tracking

### Application logging
- **structlog** — structured JSON logs in Python.
- **loguru** — simpler, less configurable.
- **standard logging + python-json-logger** — stdlib.

### Aggregation
- **ELK** (Elasticsearch + Logstash + Kibana) — the original.
- **Grafana Loki** — cheaper than ELK.
- **Datadog** — paid, all-in-one.
- **New Relic** — paid.
- **Sentry** — errors + performance + release tracking.

### Security-specific
- **Wazuh** — OSSEC successor, HIDS + log analysis.
- **Splunk** — paid, the heavyweight.
- **Elastic Security** — free tier of Elastic with security analytics.

### Alerting
- Set up alerts for: failed login spikes, admin actions outside business hours, new IAM roles, package install/upgrade in prod, outbound traffic to non-allowlisted destinations.

---

## 8.9 Authentication / authorization libraries (the production-grade list)

| Library | Use | Notes |
|---------|-----|-------|
| **passlib[argon2]** | Password hashing | Argon2id is the OWASP recommendation |
| **argon2-cffi** | Password hashing (alt) | Lower-level, faster |
| **bcrypt** | Password hashing (alt) | Argon2 preferred in 2025 |
| **python-jose[cryptography]** | JWT | Pin algorithms |
| **PyJWT** | JWT (alt) | Older, also good |
| **Authlib** | OAuth1/2/OIDC client+server | The most complete |
| **pyotp** | TOTP/HOTP MFA | Standard, well-maintained |
| **qrcode** | MFA QR codes | For setup UI |
| **itsdangerous** | Signed cookies | Same author as Flask |
| **starlette.middleware.sessions** | Session middleware | Built-in |
| **fastapi-csrf-protect** | CSRF for FastAPI | |
| **slowapi** | Rate limiting | |
| **zxcvbn** | Password strength | |
| **cryptography** | All crypto primitives | Use this, never `pycrypto` |
| **PyNaCl** | Sealed boxes, signing | Wraps libsodium |
| **bcrypt** | Password hashing (alt) | |

---

## 8.10 Validation / serialization / ORM

| Library | Use |
|---------|-----|
| **Pydantic v2** | All input validation. `extra="forbid"` by default for security. |
| **pydantic-settings** | Env-based config (replaces manual `os.environ.get`). |
| **SQLAlchemy 2.x** | ORM with parameter binding. Use the expression language, not raw f-strings. |
| **asyncpg** | Async Postgres driver. Parameterized by default. |
| **psycopg 3** | The next-gen psycopg. Parameterized by default. |
| **SQLModel** | FastAPI + SQLAlchemy + Pydantic, less boilerplate. |
| **Alembic** | Migrations. Run as the migration user, not the app user. |

---

## 8.11 Defensive libraries

| Library | What it does |
|---------|-------------|
| **defusedxml** | Safe XML parsing (no XXE) |
| **defusedcsv** | Safe CSV (no formula injection) |
| **itsdangerous** | Signed data (cookies, webhooks) |
| **python-magic** | Detect file types from content |
| **bleach** | HTML sanitization (if you must allow user HTML) |
| **markupsafe** | Auto-escape for Jinja2 |
| **pyyaml** + `safe_load` | Safe YAML |
| **re2 / pyre2** | ReDoS-safe regex |
| **python-json-logger** | Structured logging |

---

## 8.12 Infrastructure / deployment

| Tool | What it does |
|------|-------------|
| **Docker** (rootless mode) | Container isolation |
| **Distroless / Chainguard** | Minimal container images (no shell, no package manager) |
| **gVisor / kata** | Stronger container isolation |
| **NGINX / Caddy / Traefik** | Reverse proxy + TLS termination |
| **Let's Encrypt** | Free TLS certs |
| **Caddy** | Automatic HTTPS |
| **Vault** | Secret management |
| **AWS Secrets Manager** | Cloud secret management |
| **Doppler** | Secret management + sync |
| **Sigstore / cosign** | Container signing |
| **in-toto** | Supply-chain attestation |
| **SLSA framework** | Build provenance levels |

---

## 8.13 CI/CD security

### A minimal secure pipeline

```yaml
# .github/workflows/secure.yml
name: Security checks
on: [push, pull_request]
jobs:
  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2

  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install bandit semgrep
      - run: bandit -r myapp/ -lll
      - run: semgrep --config=p/owasp-top-ten --error

  sca:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install pip-audit
      - run: pip-audit -r requirements.txt

  container:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp:${{ github.sha }} .
      - run: |
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
          aquasec/trivy image --severity HIGH,CRITICAL myapp:${{ github.sha }}

  dast:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d
      - run: |
        docker run --rm --network=host owasp/zap2docker-stable \
          zap-baseline.py -t http://localhost:8000
      - run: docker compose down
```

### Sign your builds (SLSA L3)

```yaml
- uses: slsa-framework/slsa-github-generator/.github/workflows/generator_container_slsa3.yml@v1.9.0
  with:
    image: myapp
    registry: ghcr.io/myorg
```

---

## 8.14 The pre-deployment checklist

This is the single most important page in the guide. Print it. Tape it to the wall. Run it on every release.

### Code-level

- [ ] No `eval`, `exec`, `pickle.loads`, `yaml.load`, `subprocess shell=True` in the codebase.
- [ ] All SQL is parameterized (or uses SQLAlchemy expression language).
- [ ] All inputs validated through Pydantic with `extra="forbid"`.
- [ ] Separate input and output schemas (no mass assignment).
- [ ] All endpoints have an explicit `Depends(get_current_user)` (or equivalent).
- [ ] All endpoints have an explicit authorization check (role, ownership, scope).
- [ ] Passwords hashed with Argon2id.
- [ ] JWTs use pinned algorithm and validate `iss`, `aud`, `exp`.
- [ ] All cookies: `httponly=True, secure=True, samesite="lax"`.
- [ ] No secrets in code. No secrets in env vars in source control. Secrets in Vault/SM/Doppler.
- [ ] No `DEBUG=True` in prod.
- [ ] `docs_url=None`, `redoc_url=None`, `openapi_url=None` in prod.
- [ ] CORS allowlist is an explicit list, not `*`.
- [ ] All errors return generic messages; details only in logs.
- [ ] All admin actions are in the audit log.
- [ ] All state-changing endpoints support `Idempotency-Key`.
- [ ] All time-bound resources (tokens, sessions, magic links) have an explicit `exp`.

### Headers

- [ ] `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- [ ] `X-Content-Type-Options: nosniff`
- [ ] `X-Frame-Options: DENY` (or `frame-ancestors 'none'` in CSP)
- [ ] `Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'`
- [ ] `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] `Permissions-Policy` set to deny features you don't use
- [ ] `Cross-Origin-Opener-Policy: same-origin`

### Database

- [ ] App DB user is **not** superuser.
- [ ] App DB user has only `CONNECT, USAGE, SELECT, INSERT, UPDATE, DELETE` on needed tables.
- [ ] Separate migration user.
- [ ] Separate audit-writer user with only `INSERT` on audit tables.
- [ ] `pg_hba.conf` requires `scram-sha-256` and `hostssl`.
- [ ] `postgresql.conf` has `ssl=on` and `pgaudit` loaded.
- [ ] RLS enabled and forced on tenant tables.
- [ ] DB constraints (`CHECK`, `UNIQUE`, `NOT NULL`) enforce invariants.
- [ ] Backups encrypted, access-controlled, restore-tested.

### Dependencies

- [ ] `pip-audit` clean (or only low-severity).
- [ ] `bandit` clean.
- [ ] `semgrep --config=p/owasp-top-ten` clean.
- [ ] All deps pinned with hashes.
- [ ] Dependabot or Renovate enabled.
- [ ] No deprecated / unmaintained packages.
- [ ] `gitleaks` / `trufflehog` clean (no secrets in history).

### Auth

- [ ] Argon2id with sane parameters (m=64MB, t=3, p=4).
- [ ] JWT pinned algorithm, with `iss`/`aud`/`exp` validated.
- [ ] Refresh token rotation enforced.
- [ ] Account lockout after N failed attempts.
- [ ] Rate limit on `/login`, `/signup`, `/refresh`, `/forgot-password`.
- [ ] MFA available for admin / high-value users.
- [ ] Password reset tokens are single-use, expire in 30 min, hashed at rest.
- [ ] Generic "Invalid credentials" on all auth failures (no username enumeration).

### Logging & monitoring

- [ ] Auth events logged: success, failure, lockout, password change, MFA change.
- [ ] Admin actions logged with full context.
- [ ] No PII / secrets in logs.
- [ ] Log shipping to a central store.
- [ ] Alerts on: failed-login spike, new admin promotion, new IAM role, prod `pip install`.

### Network / infrastructure

- [ ] TLS 1.2+ everywhere. Cert is valid and auto-renewed.
- [ ] HSTS preload list submitted.
- [ ] Reverse proxy blocks `/.git`, `/.env`, `*.pyc`, `*.map`, `/admin` (if external).
- [ ] Container runs as non-root, with read-only filesystem where possible.
- [ ] No privileged containers.
- [ ] No Docker socket mounted into app containers.
- [ ] Outbound traffic is allowlisted (or at least, monitored).
- [ ] WAF in front of public endpoints.
- [ ] DDoS protection (Cloudflare, AWS Shield, GCP Armor).

### Operational

- [ ] Secrets are rotated on a schedule.
- [ ] MFA is enforced for all humans with prod access.
- [ ] Incident response plan exists, is tested, has a runbook.
- [ ] Backups are tested monthly.
- [ ] Logs are retained for ≥ 1 year (security events) / ≥ 30 days (everything else).
- [ ] On-call rotation exists and is staffed.

### AI / vibe-coding specific

- [ ] AI assistant is configured to **not** train on your code.
- [ ] AI suggestions go through the same review as human PRs.
- [ ] No secrets in any file the AI can read.
- [ ] If you ship an LLM feature: rate limit, spend cap, prompt-injection testing, output sanitization.
- [ ] AI agent tools are sandboxed, allowlisted, audited.

### Compliance (if applicable)

- [ ] GDPR: data subject rights honored (access, deletion, portability).
- [ ] PCI DSS: card data never touches your servers (use Stripe / Adyen).
- [ ] HIPAA: BAA in place, encryption at rest + in transit, audit log of every PHI access.
- [ ] SOC 2: change management, access reviews, vulnerability scans.
- [ ] ISO 27001: risk assessment, statement of applicability, internal audits.

---

## 8.15 The "secure coding maturity model"

Where is your team on this scale? Be honest.

| Level | Description | Tools |
|-------|-------------|-------|
| **0 — Cowboy** | No tools, no review, no auth | None |
| **1 — Aware** | Pydantic, parameterized queries, `.env` | Bandit |
| **2 — Reactive** | Linter in CI, dep scan, secret scan | Bandit + pip-audit + gitleaks |
| **3 — Proactive** | SAST in CI, headers, CORS, security headers, rate limit | + Semgrep + OWASP ZAP nightly |
| **4 — Resilient** | MFA, audit log, RLS, least-privilege DB roles, structured logging | + WAF + Snyk + pgaudit |
| **5 — World-class** | Threat modeling on every feature, supply-chain security, signed builds, runtime protection, AI-aware tooling | + Sigstore + SLSA L3 + Falco + on-call rotation |

Most teams should be at level 3 before they ship. Aim for level 4 within 12 months. Level 5 if you're in finance, healthcare, or critical infrastructure.

---

## 8.16 The one-page reading list (after this guide)

| Topic | Resource |
|-------|----------|
| OWASP Top 10 | https://owasp.org/Top10/ |
| OWASP ASVS | https://owasp.org/www-project-application-security-verification-standard/ |
| OWASP Cheat Sheets | https://cheatsheetseries.owasp.org/ |
| OWASP Testing Guide | https://owasp.org/www-project-web-security-testing-guide/ |
| FastAPI security | https://fastapi.tiangolo.com/tutorial/security/ |
| Postgres security | https://www.postgresql.org/docs/current/sql-grant.html |
| Argon2 RFC | https://datatracker.ietf.org/doc/html/rfc9106 |
| JWT BCP | https://www.rfc-editor.org/rfc/rfc8725 |
| OAuth 2.0 BCP | https://www.rfc-editor.org/rfc/rfc9700.html |
| Python security | https://docs.python.org/3/library/security_warnings.html |
| Bandit docs | https://bandit.readthedocs.io/ |
| Semgrep rules | https://semgrep.dev/r |
| CIS Benchmarks | https://www.cisecurity.org/cis-benchmarks/ |
| NIST SSDF | https://csrc.nist.gov/Projects/ssdf |
| SLSA | https://slsa.dev/ |
| NIST AI RMF | https://www.nist.gov/itl/ai-risk-management-framework |
| OWASP LLM Top 10 | https://owasp.org/www-project-top-10-for-large-language-model-applications/ |
| Real-World CTF write-ups | https://github.com/ctfs |
| PortSwigger Web Security Academy | https://portswigger.net/web-security |
| HackerOne Hacktivity (real disclosed reports) | https://hackerone.com/hacktivity |

---

## 8.17 Final thoughts

You will not remember every detail in this guide. That's fine. What you should remember:

1. **Validate input at every trust boundary.** (Pydantic + Pydantic v2's `extra="forbid"`)
2. **Parameterize every query.** (SQLAlchemy expression language or bind parameters)
3. **Use Argon2id for passwords, with sane parameters.**
4. **Pin JWT algorithms, validate `iss`/`aud`/`exp`.**
5. **Apply the principle of least privilege everywhere** — DB users, file permissions, API scopes.
6. **Defense in depth.** Don't rely on one wall. Layer controls.
7. **Fail closed.** Default deny. Default to no admin.
8. **Log auth events and admin actions, ship to a central store.**
9. **Use the linters and scanners in CI.** Bandit, Semgrep, pip-audit, gitleaks.
10. **Threat-model new features** with STRIDE or the 4-question framework.

And the meta-rule, which is what this whole course has been trying to teach:

> **Be the attacker to be the defender.** Read a new feature and ask "how would I break this?". If you can't answer in 30 seconds, you don't understand the feature well enough yet.

Welcome to the team. Secure coding is a habit, not a checklist — and now you have the habit and the checklist.
