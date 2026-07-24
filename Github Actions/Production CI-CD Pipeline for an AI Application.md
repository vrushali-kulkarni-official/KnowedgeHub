Given everything you've shared over the past few days (Ubuntu homelab, Cloudflare Tunnel, Docker, LangGraph/LangChain Python application, preference for open-source software), I would design your CI/CD pipeline almost exactly like a modern SaaS company would, except using mostly free tools.

The biggest thing to understand first is that **CI (Continuous Integration)** and **CD (Continuous Delivery/Deployment)** are two separate stages.

```
Write Code
      │
      ▼
Push to GitHub
      │
      ▼
GitHub Actions (CI)
      │
      ├── Code Quality
      ├── Unit Tests
      ├── Integration Tests
      ├── AI Tests
      ├── Security Tests
      ├── Secret Scanning
      ├── Dependency Scanning
      ├── Container Scanning
      ├── Build Docker Image
      └── Push Docker Image
                │
                ▼
Home Lab Server (CD)
                │
        Pull Latest Image
                │
      Docker Compose Restart
                │
             Health Check
                │
              Live
```

---

# Overall Architecture

```
                GitHub

           Push to main
                │
                ▼

      GitHub Actions Runner
                │
                ▼

     ┌────────────────────┐
     │ Lint               │
     │ Format Check       │
     │ Unit Tests         │
     │ Integration Tests  │
     │ Coverage           │
     │ AI Evaluation      │
     │ SAST              │
     │ Secrets Scan       │
     │ Dependency Scan    │
     │ Docker Build       │
     │ Container Scan     │
     │ Push Docker Image  │
     └────────────────────┘

                │

                ▼

         Docker Hub / GHCR

                │

                ▼

      Home Server (Ubuntu)

      Watchtower / Deploy Script

                │

                ▼

        Docker Compose

                │

                ▼

          Cloudflare Tunnel

                │

                ▼

            Internet
```

---

# Step 1

## Source Control

Use GitHub.

Every feature gets its own branch.

```
main
develop
feature/chat-memory

feature/rag

feature/search
```

---

# Step 2

## GitHub Actions

This becomes your CI server.

Every push automatically runs.

No manual work.

---

# Stage 1

## Code Formatting

Tools

```
Black

isort

Ruff
```

Checks

✓ Formatting

✓ Import ordering

✓ Code style

✓ Common mistakes

---

# Stage 2

## Type Checking

```
mypy
```

Checks

```
Incorrect types

None errors

Wrong return values

Missing attributes

etc.
```

---

# Stage 3

## Unit Testing

Framework

```
pytest
```

Plugins

```
pytest-cov

pytest-xdist

pytest-mock

pytest-asyncio
```

---

Example

```
test_vectorstore.py

test_llm.py

test_embedding.py

test_agent.py

test_tools.py

test_api.py

test_database.py
```

Automatically run.

---

# Stage 4

## Integration Testing

Test things working together.

Example

```
FastAPI

↓

LangGraph

↓

Postgres

↓

Redis

↓

Gemini API
```

---

# Stage 5

## End-to-End Testing

Run the entire application.

Example

```
User asks

↓

Agent answers

↓

Memory stored

↓

Retrieved

↓

Response generated
```

---

# Stage 6

## AI Testing

Very few beginners know this exists.

Modern AI applications test the AI itself.

Tools

LangSmith (free tier available)

DeepEval

Promptfoo

Ragas

OpenEvals

Examples

```
Does RAG retrieve correct document?

Hallucination score

Answer relevance

Faithfulness

Context precision

Context recall

Tool usage

Agent trajectory

Latency

Cost
```

This is becoming standard practice.

---

# Stage 7

## Code Coverage

```
pytest-cov
```

Target

```
90%
```

Never deploy if

```
Coverage <80%
```

---

# Stage 8

# Security

This is where companies spend huge effort.

---

## SAST

Static Application Security Testing

Use

```
Semgrep

Bandit
```

Finds

```
SQL Injection

OS Command Injection

Unsafe pickle

eval()

exec()

Hardcoded passwords

etc
```

---

## Secret Scanning

```
Gitleaks
```

Detects

```
API Keys

Gemini Key

OpenAI Key

JWT Secrets

AWS Keys

Passwords

Tokens
```

---

## Dependency Scanning

Use

```
pip-audit

Safety

Dependabot
```

Checks

```
Known CVEs

Critical libraries

Outdated packages
```

---

## SBOM Generation

Software Bill of Materials

Use

```
Syft
```

Creates

```
Every dependency

Every package

Every version
```

---

## Container Vulnerability Scan

Build Docker image.

Then scan.

Use

```
Trivy
```

Checks

```
Linux Packages

Python packages

OpenSSL

glibc

Container CVEs
```

---

## Container Best Practices

Also Trivy checks

```
Running as root

Permissions

Dockerfile mistakes

Secrets

Packages
```

---

## Dockerfile Lint

```
Hadolint
```

---

# AI Code Review

GitHub now supports

```
GitHub Copilot Code Review
```

Also

```
CodeRabbit AI

DeepSource

Reviewdog

Qodo

Bito
```

I recommend

```
Semgrep

+

CodeRabbit

+

GitHub Reviewdog
```

---

# License Scanning

```
FOSSA

or

ScanCode Toolkit
```

Useful when using open source.

---

# Docker Build

After everything passes

```
docker build
```

---

# Image Signing

Modern production practice.

Use

```
Cosign
```

Now every image is signed.

Protects against tampering.

---

# Push Image

Instead of Docker Hub I actually recommend

```
GitHub Container Registry (GHCR)
```

Advantages

Unlimited public

Good free private allowance

Integrated with GitHub

No Docker Hub rate limits

If you prefer Docker Hub that's also perfectly fine.

---

# Deployment

There are several options.

## Option 1

SSH from GitHub

```
GitHub

↓

SSH

↓

Ubuntu

↓

docker compose pull

↓

docker compose up -d
```

Simple.

---

## Option 2 (Better)

Run

```
Watchtower
```

Server watches Docker Hub.

New image appears.

Automatically updates.

No SSH required.

---

## Option 3 (Production)

Self-hosted GitHub Runner.

Runs directly on Ubuntu.

Very common.

---

# Health Check

After deployment

Run

```
GET /health

GET /ready

GET /live
```

If unhealthy

Rollback.

---

# Monitoring

Containers

```
Prometheus

Grafana

cAdvisor

Node Exporter
```

Application

```
OpenTelemetry

LangSmith

Grafana Tempo

Loki
```

Logs

```
Loki

Promtail
```

---

# Testing Pyramid

```
          E2E

     Integration

       Unit Tests
```

Most tests should be unit tests.

---

# Docker Compose

Your AI application

```
nginx

↓

FastAPI

↓

LangGraph

↓

Redis

↓

Postgres

↓

pgvector

↓

Prometheus

↓

Grafana

↓

Loki

↓

Watchtower
```

Everything inside Docker.

---

# Firewall

Because you use Cloudflare Tunnel:

### You do **not** need to expose:

```
80

443
```

Cloudflare Tunnel makes inbound HTTP/HTTPS unnecessary.

### You should also avoid exposing:

```
8000

8080

5000

3000
```

These should remain internal Docker networks unless you specifically need local LAN access.

### The only port you may want open is:

```
22 (SSH)
```

Even then, you have choices:

- If you manage the server only from your local network, allow SSH only on the LAN interface or restrict it with firewall rules.

- If you need remote SSH, don't expose it directly to the internet unless necessary. Consider using a VPN (such as Tailscale or WireGuard) or Cloudflare Zero Trust instead.

All other containers (Postgres, Redis, pgvector, etc.) should **never** have published ports to the internet.

---

# Recommended Docker Networks

```
proxy network

↓

app network

↓

database network

↓

monitoring network
```

Each container only joins the networks it actually needs.

---

# Secrets

Never store secrets in Git.

Use

```
GitHub Secrets

↓

GitHub Actions

↓

Docker Secrets
```

Avoid putting API keys directly in your repository or Docker image.

---

# My recommended stack

| Category           | Tool                                |
| ------------------ | ----------------------------------- |
| Git Hosting        | GitHub                              |
| CI/CD              | GitHub Actions                      |
| Formatter          | Black                               |
| Linter             | Ruff                                |
| Import Sorter      | isort                               |
| Type Checking      | mypy                                |
| Unit Testing       | pytest                              |
| Coverage           | pytest-cov                          |
| Security (Python)  | Bandit                              |
| Security (General) | Semgrep                             |
| Secret Scanning    | Gitleaks                            |
| Dependency Scan    | pip-audit                           |
| Container Scan     | Trivy                               |
| Dockerfile Lint    | Hadolint                            |
| SBOM               | Syft                                |
| Image Signing      | Cosign                              |
| AI Evaluation      | DeepEval + Promptfoo + Ragas        |
| AI Code Review     | CodeRabbit                          |
| Container Registry | GHCR (or Docker Hub)                |
| Deployment         | GitHub Actions → SSH, or Watchtower |
| Monitoring         | Prometheus + Grafana                |
| Logs               | Loki + Promtail                     |
| Metrics            | OpenTelemetry                       |
| Reverse Proxy      | NGINX                               |
| Tunnel             | Cloudflare Tunnel                   |
| Database           | PostgreSQL + pgvector               |
| Cache              | Redis                               |

## One recommendation for your setup

Since you're learning and want to build production-grade AI systems, I would **not** start by implementing everything at once. The best approach is to build the pipeline in stages:

1. GitHub Actions (lint, format, tests)

2. Security scanning (Semgrep, Bandit, Gitleaks, pip-audit)

3. Docker build and Trivy image scanning

4. Push signed image to GHCR or Docker Hub

5. Automatic deployment to your Ubuntu homelab

6. AI-specific evaluation (DeepEval, Promptfoo, Ragas)

7. Monitoring, logging, and automatic rollback

This progression mirrors how many engineering teams evolve their CI/CD systems and will make each step much easier to understand and troubleshoot.

Given your interest in learning AI engineering deeply rather than just getting something working, I'd also recommend treating this as infrastructure-as-code: keep your GitHub Actions workflows, Dockerfiles, Docker Compose files, monitoring configuration, and deployment scripts version-controlled alongside your application code. That way, your entire production environment can be recreated from your repository.
