Absolutely. Since you are a beginner, I would **not** recommend trying to apply 50 security settings at once. The best approach is to build security in layers:

**Your laptop → Git → SSH → GitHub account → repository → branches → pull requests → GitHub Actions → secrets → Docker/registry → deployment.**

For your setup, where you use **Fedora 44**, multiple GitHub accounts, SSH aliases, and GitHub Actions for Docker builds/deployment, I would use the following security baseline. ([GitHub Docs][1])

---

# 1. First understand what we are protecting

Think of your development system like a building:

```text
                         INTERNET
                            │
                            ▼
                    ┌───────────────┐
                    │    GitHub     │
                    │               │
                    │ Account       │
                    │ Repository    │
                    │ Actions       │
                    │ Secrets       │
                    └───────┬───────┘
                            │
                     SSH / HTTPS
                            │
                            ▼
                    ┌───────────────┐
                    │ Fedora 44     │
                    │               │
                    │ Git           │
                    │ SSH keys      │
                    │ Source code   │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ GitHub Actions│
                    │               │
                    │ Test          │
                    │ Scan          │
                    │ Build         │
                    │ Push image    │
                    │ Deploy        │
                    └───────────────┘
```

There are therefore several different attack surfaces.

### Git security

Protect against:

* accidentally committing `.env`
* committing passwords
* committing private keys
* malicious Git configuration
* incorrect author identity
* destructive commands
* accidentally pushing to the wrong repository

### GitHub account security

Protect against:

* password theft
* stolen sessions
* stolen personal access tokens
* compromised SSH keys
* unauthorized repository access

### Repository security

Protect against:

* direct pushes to `main`
* malicious pull requests
* accidental force pushes
* unauthorized workflow changes
* unauthorized releases/tags

### GitHub Actions security

This is particularly important.

A workflow can potentially:

```text
read repository
       ↓
read secrets
       ↓
execute arbitrary commands
       ↓
build Docker image
       ↓
push Docker image
       ↓
deploy production
```

So **GitHub Actions should be treated almost like production infrastructure**, not merely "a CI tool."

GitHub itself recommends least-privilege `GITHUB_TOKEN` permissions, immutable action references, careful secret handling, and auditing third-party actions. ([GitHub Docs][1])

---

# 2. Our target security architecture

I recommend eventually reaching this:

```text
                           GitHub
                              │
                ┌─────────────┴─────────────┐
                │                           │
          Account Security            Repository Security
                │                           │
          2FA / Passkey                Rulesets
          SSH keys                     Protected main
          Recovery                     Protected develop
                │                      CODEOWNERS
                │                      PR reviews
                │
                └──────────────┬────────────┘
                               │
                               ▼
                       GitHub Actions
                               │
                 ┌─────────────┼─────────────┐
                 │             │             │
              Testing       Security       Build
                 │             │             │
                 ▼             ▼             ▼
              pytest      CodeQL/SAST    Docker
                           Secret scan    SBOM
                           Dependabot     Attestation
                                           │
                                           ▼
                                      GHCR/Docker Hub
                                           │
                                           ▼
                                       Deployment
```

The important principle is:

> **No single compromised component should automatically give an attacker everything.**

---

# 3. Step 1 — Secure your GitHub account first

Before touching Git or Actions, secure the GitHub account itself.

Go to:

[GitHub Security Settings](https://github.com/settings/security?utm_source=chatgpt.com)

## Enable 2FA

Use a strong authentication method.

Ideally:

```text
Passkey / security key
        +
Authenticator app
        +
Recovery codes
```

Do not depend only on SMS if stronger options are available.

---

# 4. Protect your recovery codes

When GitHub gives you recovery codes, treat them like passwords.

Do **not** put them in:

```text
Git repository
GitHub repository
Google Drive
email
.env
notes.txt
```

Store them in a secure password manager or offline secure storage.

---

# 5. Review your GitHub sessions

Periodically inspect:

* active sessions
* authorized applications
* SSH keys
* personal access tokens

Remove anything you don't recognize.

A good security habit is:

> **Every credential should have a purpose.**

If you can't explain why an SSH key/token exists, remove it.

---

# 6. Your multiple GitHub accounts need special care

You currently have separate GitHub identities, including:

```text
VBCreators
vrushali-kulkarni-official
```

and you already have separate SSH aliases such as:

```text
Host VBCreators
    HostName github.com
    User git
    IdentityFile ~/.ssh/githubAlienKey
    IdentitiesOnly yes

Host vrushali-kulkarni-official
    HostName github.com
    User git
    IdentityFile ~/.ssh/vbalien_github_vrushali
    IdentitiesOnly yes
```

This is actually a **good security architecture**.

Keep the identities separate.

Your repository remotes should use the appropriate SSH alias.

For example:

```bash
git remote -v
```

You want something like:

```text
origin git@VBCreators:VBCreators/project.git
```

or:

```text
origin git@vrushali-kulkarni-official:vrushali-kulkarni-official/project.git
```

rather than blindly using:

```text
git@github.com:...
```

because the explicit SSH host alias makes the intended identity much clearer.

---

# 7. Harden your SSH keys

Check your keys:

```bash
ls -la ~/.ssh
```

You should see private/public pairs such as:

```text
githubAlienKey
githubAlienKey.pub

vbalien_github_vrushali
vbalien_github_vrushali.pub
```

Your private keys should have restrictive permissions.

Run:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/githubAlienKey
chmod 644 ~/.ssh/githubAlienKey.pub

chmod 600 ~/.ssh/vbalien_github_vrushali
chmod 644 ~/.ssh/vbalien_github_vrushali.pub
```

The important concept:

```text
PRIVATE KEY
    ↓
600

PUBLIC KEY
    ↓
644
```

Never upload the private key anywhere.

---

# 8. Use Ed25519 SSH keys

For new GitHub SSH keys, prefer:

```bash
ssh-keygen -t ed25519
```

For example:

```bash
ssh-keygen -t ed25519 -C "your-email@example.com"
```

Do **not** put your actual private key into Git.

Your:

```text
something
```

private key stays on your machine.

Only:

```text
something.pub
```

goes to GitHub.

---

# 9. Use SSH agent correctly

Check:

```bash
ssh-add -l
```

You should see the keys currently loaded.

You can add one with:

```bash
ssh-add ~/.ssh/githubAlienKey
```

and:

```bash
ssh-add ~/.ssh/vbalien_github_vrushali
```

Your `IdentitiesOnly yes` setting is particularly useful with multiple accounts because SSH won't randomly try unrelated identities.

---

# 10. Test every GitHub identity

For your first account:

```bash
ssh -T git@VBCreators
```

For your second:

```bash
ssh -T git@vrushali-kulkarni-official
```

You should verify that each identity authenticates to the **correct GitHub account**.

This is important because your previous issue involved a repository being accessed as the wrong GitHub account.

---

# 11. Harden Git itself

Now let's secure Git.

First inspect your configuration:

```bash
git config --global --list --show-origin
```

This is an excellent command for beginners because it shows:

```text
setting
    ↓
value
    ↓
where it came from
```

For example:

```text
~/.gitconfig
repository/.git/config
system configuration
```

---

# 12. Configure your Git identity

Because you use multiple GitHub accounts, **don't blindly use one global identity for everything**.

Instead, use repository-level configuration where appropriate.

Inside a repository:

```bash
git config user.name "Your Name"
git config user.email "your-email@example.com"
```

Check:

```bash
git config user.name
git config user.email
```

This prevents a very common problem:

```text
personal repository
        ↓
work email
        ↓
wrong GitHub identity
```

---

# 13. Use a global `.gitignore`

Create:

```bash
nano ~/.gitignore_global
```

For example:

```gitignore
# Environment files
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Virtual environments
.venv/
venv/
env/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Secrets
*.pem
*.key
*.p12
*.pfx

# SSH
id_rsa
id_ed25519
```

Then:

```bash
git config --global core.excludesfile ~/.gitignore_global
```

Check:

```bash
git config --global core.excludesfile
```

---

# 14. But understand an important limitation

`.gitignore` is **not a security mechanism**.

Suppose you do:

```bash
git add secret.txt
git commit
```

and then add:

```text
secret.txt
```

to `.gitignore`.

The secret is **already in Git history**.

Therefore:

> `.gitignore` prevents accidental tracking; it does not remove secrets that were already committed.

If a secret is committed, assume it is compromised and **rotate/revoke it**.

---

# 15. Never put secrets into Git

Never commit:

```text
.env
.env.production
.env.staging
password.txt
private.pem
id_ed25519
database credentials
API keys
JWT secrets
cloud credentials
Docker registry passwords
SSH private keys
```

Instead commit:

```text
.env.example
```

For example:

```env
DATABASE_URL=
GEMINI_API_KEY=
REDIS_URL=
```

without actual values.

---

# 16. Scan your repository for secrets

Before pushing important repositories, use a secret scanner.

One good option is **Gitleaks**.

You can install it through your preferred Fedora package/source method and then scan:

```bash
gitleaks detect
```

The important concept is:

```text
Developer
   ↓
git add
   ↓
secret scanner
   ↓
commit
   ↓
GitHub
```

rather than:

```text
Developer
   ↓
GitHub
   ↓
"Oh no, I committed my API key."
```

GitHub also provides secret scanning features for detecting exposed credentials.

---

# 17. Protect Git's configuration from malicious repositories

One subtle Git security issue is repository-provided configuration.

When working with repositories you don't fully trust, be careful with:

```text
.git/config
```

A repository can contain Git configuration that influences behavior.

For example, don't blindly run unfamiliar scripts or commands just because a repository tells you to.

Treat:

```text
README
Makefile
package scripts
shell scripts
Git hooks
Dockerfiles
GitHub workflows
```

as **code**, not documentation.

---

# 18. Understand Git hooks

Git supports hooks such as:

```text
pre-commit
commit-msg
pre-push
post-checkout
```

Hooks can execute programs.

Therefore:

> Don't blindly copy `.git/hooks` or install hooks from an untrusted repository.

For your own projects, hooks can actually improve security.

For example:

```text
pre-commit
    ↓
secret scan
    ↓
lint
    ↓
format check
```

---

# 19. Sign your Git commits

GitHub supports commit signing with:

* SSH
* GPG
* S/MIME

GitHub documents all three. ([GitHub Docs][2])

For a beginner, **SSH commit signing** is attractive because you already understand SSH keys.

The concept becomes:

```text
Normal commit:

commit → author says "I made this"


Signed commit:

commit → cryptographic signature → GitHub verifies it
```

That doesn't mean the code is automatically safe.

It means:

> "This commit was cryptographically signed by a key associated with this identity."

---

# 20. Turn on commit signing

Once configured, Git can sign commits automatically.

The configuration is conceptually:

```bash
git config --global commit.gpgsign true
```

GitHub documents automatic commit signing configuration. ([GitHub Docs][2])

However, because you have **multiple GitHub accounts**, I would configure signing carefully per identity/repository rather than blindly applying one signing identity everywhere.

---

# 21. Understand the GitHub repository model

Now move to GitHub.

For your workflow, I recommend:

```text
main
  │
  │ production
  │
develop
  │
  │ integration
  │
feature/*
```

Example:

```text
main
  │
  └── develop
        ├── feature/auth
        ├── feature/rag
        ├── feature/api
        └── feature/frontend
```

The important security rule:

> Developers should normally not push directly to `main`.

---

# 22. Protect `main`

Go to:

**Repository → Settings → Rules → Rulesets**

GitHub rulesets can enforce things such as:

* pull requests
* status checks
* signed commits
* linear history
* blocking force pushes
* code scanning results
* deployment requirements. ([GitHub Docs][3])

Create a ruleset for:

```text
main
```

---

# 23. Recommended `main` rules

For an extremely secure setup:

```text
✓ Require pull request
✓ Require approvals
✓ Require status checks
✓ Require conversation resolution
✓ Block force pushes
✓ Restrict deletions
✓ Require signed commits
✓ Require code scanning
✓ Require deployment checks where appropriate
```

The exact options available depend on your GitHub plan.

---

# 24. Protect `develop` too

Don't make this mistake:

```text
main       🔒
develop    🔓
```

If an attacker compromises `develop`, they can potentially inject malicious code that later reaches `main`.

So protect both:

```text
main       🔒🔒🔒
develop    🔒🔒
feature/*  🔓
```

A reasonable policy:

### `main`

```text
PR required
2 approvals
CI required
security scan required
no force push
signed commits
```

### `develop`

```text
PR required
1 approval
CI required
security scan required
no force push
```

---

# 25. Never allow force pushes to main

Avoid:

```bash
git push --force origin main
```

Especially:

```bash
git push --force --no-verify
```

Force pushing can destroy history and bypass normal workflow protections.

Use:

```bash
git push --force-with-lease
```

only when you genuinely understand why history needs rewriting.

And ideally:

> Never rewrite protected branch history.

---

# 26. Use Pull Requests as a security boundary

Your workflow becomes:

```text
feature
   │
   ▼
Pull Request
   │
   ├── tests
   ├── lint
   ├── security scan
   ├── dependency scan
   ├── secret scan
   ├── build
   │
   ▼
Human review
   │
   ▼
develop
```

Then:

```text
develop
   │
   ▼
Pull Request
   │
   ├── tests
   ├── security
   ├── build
   │
   ▼
Approval
   │
   ▼
main
```

This is much safer than:

```text
git push main
```

---

# 27. Add CODEOWNERS

Create:

```text
.github/CODEOWNERS
```

Example:

```text
.github/workflows/    @YOUR_GITHUB_USERNAME
Dockerfile            @YOUR_GITHUB_USERNAME
docker-compose.yml    @YOUR_GITHUB_USERNAME
```

This is particularly important for:

```text
.github/workflows/
```

because changing a workflow can change what your CI/CD system is allowed to do.

GitHub explicitly recommends using `CODEOWNERS` to monitor workflow changes. ([GitHub Docs][1])

---

# 28. Why workflow files deserve special protection

Imagine your workflow currently says:

```yaml
permissions:
  contents: read
```

An attacker modifies it to:

```yaml
permissions:
  contents: write
```

or adds access to secrets.

That could completely change your security posture.

Therefore:

```text
.github/workflows/
```

should be treated almost like:

```text
production infrastructure
```

---

# 29. Secure GitHub Actions with least privilege

This is one of the **most important steps**.

Never assume:

```yaml
permissions: write-all
```

is acceptable.

Start with:

```yaml
permissions:
  contents: read
```

Then give individual jobs only what they require.

GitHub recommends setting the default `GITHUB_TOKEN` permission to read-only and increasing permissions only where necessary. ([GitHub Docs][1])

For example:

```yaml
permissions:
  contents: read
```

Then perhaps a publishing job:

```yaml
permissions:
  contents: read
  packages: write
```

Only that job gets package publishing capability.

---

# 30. Understand `GITHUB_TOKEN`

Every GitHub Actions workflow gets a token called:

```text
GITHUB_TOKEN
```

Think of it as:

```text
temporary GitHub password
```

but controlled by GitHub.

If you give it:

```yaml
contents: write
```

the workflow may be able to modify repository contents.

If you give:

```yaml
packages: write
```

it can potentially publish packages.

Therefore:

> Give the workflow exactly what it needs — nothing more.

---

# 31. Pin GitHub Actions to full commit SHAs

This is one of the strongest GitHub Actions security improvements.

Avoid:

```yaml
uses: actions/checkout@v4
```

A tag can theoretically move.

Prefer:

```yaml
uses: actions/checkout@<FULL_COMMIT_SHA>
```

GitHub's security documentation specifically recommends pinning actions to full-length commit SHAs because that gives you an immutable reference. ([GitHub Docs][1])

---

# 32. Why SHA pinning matters

Imagine:

```text
actions/example@v4
```

Today:

```text
v4 → safe commit A
```

Later:

```text
v4 → malicious commit B
```

Your workflow automatically gets B.

With:

```text
actions/example@SHA-A
```

you get:

```text
SHA-A
```

forever unless you intentionally update it.

That's much safer.

---

# 33. Don't blindly trust third-party Actions

This:

```yaml
uses: random-user/super-action@v1
```

means you're giving code from another repository the ability to execute inside your workflow.

Before using an Action:

1. Who maintains it?
2. Is the repository reputable?
3. Is the source public?
4. What permissions does it require?
5. Does it access secrets?
6. Does it send data externally?
7. Is it pinned?
8. Is it maintained?

GitHub explicitly recommends auditing third-party action source and pinning actions to immutable SHAs. ([GitHub Docs][1])

---

# 34. Restrict allowed Actions

GitHub lets you configure Actions policies.

You can restrict which actions are allowed and, depending on your settings, require actions to use full-length commit SHAs. ([GitHub Docs][4])

For a hardened repository, I would aim for:

```text
Allow:
✓ GitHub-authored actions you need
✓ Trusted organization actions
✓ Specifically approved third-party actions

Block:
✗ arbitrary Actions
✗ unknown marketplace Actions
✗ unnecessary reusable workflows
```

---

# 35. Secrets: understand the golden rule

Never do this:

```yaml
run: echo "${{ secrets.API_KEY }}"
```

Never.

Even though GitHub masks secrets in many situations, secret redaction isn't a magical guarantee against every transformation or leakage path. GitHub explicitly warns about this. ([GitHub Docs][1])

---

# 36. Use GitHub Secrets

For example:

```text
Repository
   ↓
Settings
   ↓
Secrets and variables
   ↓
Actions
```

Put secrets there.

Examples:

```text
GEMINI_API_KEY
DATABASE_PASSWORD
DOCKERHUB_TOKEN
DEPLOY_TOKEN
```

But don't automatically put every secret at repository level.

---

# 37. Use environments for production

Create:

```text
development
staging
production
```

Then:

```text
production
    ↓
environment secrets
    ↓
approval
    ↓
deployment
```

This is much safer than:

```text
every workflow
    ↓
production secrets
```

GitHub supports environment-level Actions secrets specifically for environments such as staging and production. ([GitHub Docs][5])

---

# 38. Separate staging and production credentials

Never use:

```text
PRODUCTION_DATABASE_PASSWORD
```

for:

```text
staging
```

Use:

```text
STAGING_DATABASE_URL
```

and:

```text
PRODUCTION_DATABASE_URL
```

Better yet, use environment-scoped secrets so workflows don't even have access to credentials they don't need.

---

# 39. Prefer OIDC over long-lived cloud credentials

If you deploy to a cloud provider that supports GitHub OIDC, use:

```text
GitHub Actions
      │
      │ short-lived identity
      ▼
    OIDC
      │
      ▼
Cloud provider
```

rather than:

```text
GitHub Secret
      │
      ▼
Long-lived AWS/Azure/GCP credential
```

OIDC allows GitHub Actions to obtain short-lived credentials and eliminates the need to store long-lived cloud credentials in GitHub. ([GitHub Docs][6])

---

# 40. Your homelab deployment needs special attention

You have been working with:

```text
GitHub
   ↓
GitHub Actions
   ↓
Docker
   ↓
GHCR/Docker Hub
   ↓
homelab server
```

I would **not** give GitHub Actions unrestricted SSH access to your server.

Avoid:

```text
root SSH
```

and avoid giving a deployment key:

```text
sudo ALL=(ALL) NOPASSWD: ALL
```

That's effectively:

> "If GitHub Actions is compromised, my entire server is compromised."

---

# 41. Create a dedicated deployment identity

Use a dedicated deployment user:

```text
github-deploy
```

not:

```text
root
```

The deployment account should have only the permissions necessary to:

```text
pull image
restart application
read required deployment files
```

Nothing else.

---

# 42. Separate deployment from source-code permissions

Think of permissions like this:

```text
GitHub Actions
      │
      ├── read source
      │
      ├── run tests
      │
      ├── build image
      │
      └── publish image
```

Production deployment should be another tightly controlled step.

For example:

```text
main
 ↓
build
 ↓
security checks
 ↓
image
 ↓
approval
 ↓
production deployment
```

Don't let every pull request deploy production.

---

# 43. Protect production with an environment

Use:

```text
production
```

environment.

Then configure:

```text
Required reviewers
Environment secrets
Deployment restrictions
```

So the pipeline becomes:

```text
PR
 ↓
tests
 ↓
security
 ↓
merge
 ↓
build
 ↓
production approval
 ↓
deploy
```

---

# 44. Secure GHCR and Docker Hub

For your container pipeline:

```text
GitHub
    ↓
GitHub Actions
    ↓
Docker build
    ↓
security scan
    ↓
GHCR
```

and optionally:

```text
Docker Hub
```

Don't use your normal Docker Hub password in GitHub Actions.

Use an appropriately scoped access token.

And don't give a token more privileges than required.

---

# 45. Don't build Docker images from untrusted PRs with secrets

This is extremely important.

Suppose someone submits:

```text
Pull Request
```

and your workflow does:

```yaml
- run: docker build .
- run: docker run ...
```

with production secrets available.

The PR could potentially modify the Dockerfile or scripts.

Now your "CI" might execute attacker-controlled code.

Therefore:

> Never expose powerful secrets to untrusted pull requests.

GitHub specifically documents security risks around untrusted code and workflow events. ([GitHub Docs][1])

---

# 46. Be extremely careful with `pull_request_target`

You should understand this event before using it:

```yaml
pull_request_target:
```

It can run with privileges associated with the target repository.

Therefore:

```text
untrusted PR code
        +
privileged workflow
        =
danger
```

GitHub has dedicated documentation on the security risks of `pull_request_target`. ([GitHub Docs][7])

As a beginner:

> **Don't use `pull_request_target` unless you understand exactly why you need it.**

---

# 47. Add dependency scanning

Your Python application might have:

```text
FastAPI
Pydantic
LangChain
PostgreSQL drivers
Redis
Qdrant
etc.
```

Dependencies can contain vulnerabilities.

Enable:

```text
Dependabot
```

and GitHub dependency/security features.

GitHub can also analyze Actions dependencies and show vulnerabilities in the dependency graph. ([GitHub Docs][1])

---

# 48. Add static code analysis

For Python:

```text
Code
 ↓
SAST
 ↓
vulnerabilities
```

Consider:

```text
CodeQL
Bandit
Ruff
mypy
```

For your FastAPI application, this can catch classes of problems before deployment.

---

# 49. Add secret scanning

Your pipeline should effectively become:

```text
git push
   │
   ├── secret scanning
   ├── dependency scanning
   ├── SAST
   ├── tests
   ├── lint
   └── build
```

Do this **before** publishing a production Docker image.

---

# 50. Scan your Docker images

Your Docker pipeline should be:

```text
Dockerfile
    ↓
docker build
    ↓
image scanner
    ↓
vulnerability check
    ↓
push registry
```

Tools such as:

```text
Trivy
```

can scan container images.

For example conceptually:

```bash
trivy image your-image:tag
```

Don't automatically publish images if critical vulnerabilities are detected.

---

# 51. Use immutable image tags

Avoid relying only on:

```text
latest
```

For production.

Instead:

```text
chatbot:1.4.2
```

or:

```text
chatbot:<git-sha>
```

Even better:

```text
chatbot:<git-sha>
```

because you know exactly which source commit produced the image.

---

# 52. Understand why `latest` is dangerous

Imagine:

```text
latest
   ↓
image A
```

Tomorrow:

```text
latest
   ↓
image B
```

Your server doesn't necessarily have an obvious record of which source commit produced B.

With:

```text
chatbot:abc1234
```

you have:

```text
Git commit
     ↓
Docker image
     ↓
Deployment
```

That creates traceability.

---

# 53. Generate SBOMs

SBOM means:

> **Software Bill of Materials**

Think of it as:

```text
Docker image
   ↓
What is inside it?
   ↓
Python
FastAPI
OpenSSL
glibc
etc.
```

An SBOM helps you understand your software supply chain.

---

# 54. Use artifact attestations

GitHub supports artifact attestations to establish build provenance and help verify the software you produce. ([GitHub Docs][8])

Conceptually:

```text
Source commit
      ↓
GitHub Actions
      ↓
Build
      ↓
Artifact
      ↓
Attestation
```

Now you can establish:

> "This image was produced by this workflow from this source."

That's a significant supply-chain security improvement.

---

# 55. Secure your workflow files

Your repository should have something like:

```text
.github/
└── workflows/
    ├── ci.yml
    ├── security.yml
    └── docker.yml
```

And:

```text
.github/CODEOWNERS
```

Protect those files with branch rules and CODEOWNERS.

---

# 56. A secure CI/CD pipeline for your project

For your Python/FastAPI/Docker architecture, I'd aim for:

```text
Developer
    │
    │ git push feature/*
    ▼
GitHub
    │
    ▼
Pull Request
    │
    ├───────────────┐
    │               │
    ▼               ▼
Secret scan       Dependency scan
    │               │
    └───────┬───────┘
            ▼
          SAST
            │
            ▼
          Tests
            │
            ▼
          Lint
            │
            ▼
       Docker build
            │
            ▼
      Container scan
            │
            ▼
         SBOM
            │
            ▼
       Attestation
            │
            ▼
       Human review
            │
            ▼
         develop
            │
            ▼
       Release PR
            │
            ▼
           main
            │
            ▼
      Production approval
            │
            ▼
         Deployment
```

That is the architecture I would build toward.

---

# 57. Your repository should eventually look like this

```text
project/
│
├── .github/
│   ├── CODEOWNERS
│   │
│   └── workflows/
│       ├── ci.yml
│       ├── security.yml
│       ├── docker.yml
│       └── deploy.yml
│
├── app/
│
├── tests/
│
├── Dockerfile
├── compose.yml
├── requirements.txt
├── pyproject.toml
│
├── .env.example
├── .gitignore
│
└── README.md
```

Notice what is **not** there:

```text
.env
.env.production
private keys
password files
API keys
```

---

# 58. Add a secure `.gitignore`

At minimum:

```gitignore
# Environment
.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]

# Virtual environment
.venv/
venv/

# Testing
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/

# Secrets
*.pem
*.key
*.p12
*.pfx

# OS
.DS_Store
```

---

# 59. Add a security policy

Create:

```text
SECURITY.md
```

It should explain:

```text
How to report vulnerabilities
Supported versions
Security contact
Expected response
```

This becomes particularly useful once your projects become public.

---

# 60. Don't expose secrets through logs

Avoid:

```yaml
- run: env
```

Avoid:

```yaml
- run: printenv
```

Avoid:

```yaml
- run: cat .env
```

Avoid debugging with:

```yaml
set -x
```

when secrets may be present.

A secret accidentally printed to logs may become a security incident.

---

# 61. Don't put secrets in command-line arguments unnecessarily

For example, avoid:

```bash
some-command --password "$PASSWORD"
```

when the tool provides a safer environment-variable/stdin mechanism.

Command arguments can sometimes appear in process listings or logs.

Prefer the application's supported secure secret mechanism.

---

# 62. Use minimal Docker permissions

Since you're already working with Docker security, continue with:

```yaml
security_opt:
  - no-new-privileges:true
```

and where possible:

```yaml
cap_drop:
  - ALL
```

and:

```yaml
read_only: true
```

with specific writable `tmpfs`/volumes where needed.

This is another layer:

```text
GitHub compromise
       ↓
CI compromise
       ↓
container compromise
       ↓
limited container privileges
```

Defense in depth matters.

---

# 63. Never run your application as root inside Docker

Prefer:

```dockerfile
RUN useradd --create-home appuser
USER appuser
```

instead of:

```dockerfile
USER root
```

If your application is compromised, the attacker starts with fewer privileges.

---

# 64. Keep GitHub Actions runners in mind

GitHub-hosted runners are generally preferable to maintaining your own runner when you don't need custom infrastructure.

Be especially careful with self-hosted runners.

A malicious workflow running on a self-hosted runner can potentially attack the machine hosting that runner.

For your homelab:

```text
GitHub Actions
       ↓
self-hosted runner
       ↓
homelab
```

creates a significant trust boundary.

Don't install a self-hosted runner on the same machine that contains your most sensitive infrastructure unless you have a strong isolation strategy.

---

# 65. If you eventually use self-hosted runners

Prefer:

```text
dedicated VM
        ↓
dedicated runner
        ↓
minimal permissions
```

rather than:

```text
Ubuntu server
    ↓
Docker
    ↓
database
    ↓
Traefik
    ↓
Cloudflare
    ↓
self-hosted GitHub runner
```

That second architecture creates too much blast radius.

---

# 66. Protect tags and releases

Attackers may target:

```text
v1.0.0
latest
production
```

Protect important tags.

Your release process should look like:

```text
main
 ↓
release
 ↓
tag
 ↓
build
 ↓
scan
 ↓
publish
```

rather than letting anyone freely create production tags.

GitHub rulesets can also apply protections to tags. ([GitHub Docs][3])

---

# 67. Protect GitHub Actions from workflow injection

Be careful with:

```yaml
run: echo "${{ github.event.pull_request.title }}"
```

or:

```yaml
run: some-command "${{ github.event.issue.body }}"
```

because GitHub event fields can contain attacker-controlled input.

Treat all external input as:

```text
UNTRUSTED
```

especially:

```text
PR title
PR body
issue title
issue body
branch names
commit messages
user input
```

---

# 68. Separate trusted and untrusted workflows

Think:

```text
UNTRUSTED PR
     ↓
tests
     ↓
NO production secrets
     ↓
NO production deployment
```

versus:

```text
TRUSTED main
     ↓
production credentials
     ↓
deployment
```

That separation is fundamental.

---

# 69. Don't give every workflow every secret

Bad:

```text
CI workflow
   ↓
ALL SECRETS
```

Better:

```text
CI
 ├── no secrets

Docker
 └── registry publishing token

Deploy
 └── deployment credentials

Production
 └── production secrets
```

This dramatically reduces blast radius.

---

# 70. Create a permission matrix

For your project, something like:

| Component         | Read code | Write code |       Secrets | Publish image | Deploy |
| ----------------- | --------: | ---------: | ------------: | ------------: | -----: |
| Developer         |         ✓ |    feature |            No |            No |     No |
| CI                |         ✓ |         No |            No |            No |     No |
| Security scan     |         ✓ |         No |            No |            No |     No |
| Docker build      |         ✓ |         No | Registry only |             ✓ |     No |
| Production deploy |         ✓ |         No |   Deploy only |    No/limited |      ✓ |
| Repository admin  |         ✓ |          ✓ |        Manage |             ✓ |      ✓ |

This is **least privilege** in a form you can understand.

---

# 71. Make security failures stop the pipeline

For example:

```text
secret detected
     ↓
❌ STOP
```

```text
critical vulnerability
     ↓
❌ STOP
```

```text
tests fail
     ↓
❌ STOP
```

```text
security scan fails
     ↓
❌ STOP
```

Don't create a pipeline where everything says:

```text
warning
warning
warning
warning
Deploy anyway
```

---

# 72. Don't blindly auto-update everything

This is a subtle supply-chain issue.

You want:

```text
Dependabot
    ↓
PR
    ↓
tests
    ↓
security
    ↓
review
    ↓
merge
```

rather than:

```text
new dependency
    ↓
automatic production deployment
```

Dependabot can help keep GitHub Actions and dependencies updated, and GitHub recommends it as part of Actions security maintenance. ([GitHub Docs][1])

---

# 73. Have a vulnerability response procedure

If you accidentally commit:

```text
GEMINI_API_KEY=abc123
```

do **not** simply do:

```bash
git rm .env
git commit
git push
```

That is not enough.

Instead:

```text
1. Revoke the key
        ↓
2. Generate new key
        ↓
3. Update secret
        ↓
4. Remove secret from repository
        ↓
5. Clean Git history if necessary
        ↓
6. Search logs/artifacts
        ↓
7. Investigate possible usage
```

The first step is always:

> **Invalidate the credential.**

---

# 74. Understand Git history

This command:

```bash
git log --all --oneline
```

shows your history.

You can inspect all branches:

```bash
git log --all --decorate --graph --oneline
```

This is useful when investigating whether sensitive information exists somewhere in history.

Remember:

```text
working tree
      ≠
Git history
      ≠
GitHub repository
      ≠
GitHub Actions logs
      ≠
Docker registry
      ≠
deployment server
```

A secret can leak into any of these.

---

# 75. Audit your GitHub repository regularly

Once a month, check:

```text
Repository access
SSH keys
PATs
Actions
Secrets
Deploy keys
Webhooks
Apps
Rulesets
Branches
Environments
Workflow permissions
```

Security isn't:

```text
configure once → done
```

It's:

```text
configure
   ↓
monitor
   ↓
review
   ↓
rotate
   ↓
update
```

---

# 76. Your "extremely secure" baseline

If you want a checklist, this is the target I recommend.

### GitHub account

```text
[ ] 2FA/passkey enabled
[ ] Recovery codes secured
[ ] Sessions reviewed
[ ] Authorized applications reviewed
[ ] Old PATs removed
[ ] SSH keys reviewed
```

### SSH

```text
[ ] Ed25519 keys
[ ] Separate keys for separate accounts
[ ] Correct SSH aliases
[ ] IdentitiesOnly yes
[ ] Private keys chmod 600
[ ] SSH agent configured
```

### Git

```text
[ ] Correct user.name
[ ] Correct user.email
[ ] Global .gitignore
[ ] No .env committed
[ ] Secret scanning
[ ] Commit signing
[ ] Git hooks understood
```

### Repository

```text
[ ] main protected
[ ] develop protected
[ ] PR required
[ ] Reviews required
[ ] Status checks required
[ ] Force pushes blocked
[ ] Deletion blocked
[ ] CODEOWNERS
[ ] Signed commits
```

### GitHub Actions

```text
[ ] Least privilege GITHUB_TOKEN
[ ] Actions pinned to SHA
[ ] Third-party Actions reviewed
[ ] Allowed Actions restricted
[ ] No unnecessary secrets
[ ] Production environment protected
[ ] No secrets in PR workflows
[ ] pull_request_target avoided unless necessary
[ ] OIDC where applicable
```

### Supply chain

```text
[ ] Dependabot
[ ] CodeQL/SAST
[ ] Secret scanning
[ ] Dependency scanning
[ ] Docker image scanning
[ ] SBOM
[ ] Artifact attestations
[ ] Immutable image tags
```

### Deployment

```text
[ ] Dedicated deployment user
[ ] Never deploy using root
[ ] Minimal SSH permissions
[ ] Production approval
[ ] Separate staging/production credentials
[ ] Container runs non-root
[ ] Docker capabilities minimized
[ ] No unnecessary host mounts
```

---

# 77. The order I recommend you implement this

**Don't implement everything simultaneously.**

Do it in this order:

```text
PHASE 1 — GitHub account
        ↓
2FA
SSH keys
sessions
PAT cleanup

PHASE 2 — Git
        ↓
identity
.gitignore
secret scanning
commit signing

PHASE 3 — Repository
        ↓
main ruleset
develop ruleset
PRs
CODEOWNERS

PHASE 4 — GitHub Actions
        ↓
permissions
SHA pinning
trusted Actions
secret separation

PHASE 5 — Security scanning
        ↓
Dependabot
CodeQL
secret scanning
dependency scanning

PHASE 6 — Docker
        ↓
non-root
minimal capabilities
image scanning
SBOM
immutable tags

PHASE 7 — Deployment
        ↓
environment protection
deployment identity
OIDC where possible
minimal server permissions

PHASE 8 — Supply-chain security
        ↓
attestations
provenance
signed artifacts
continuous monitoring
```

---

# 78. The most important concepts to remember

If you're new to security, don't try to memorize commands. Remember these **10 principles**:

### 1. Least privilege

Give something only the permissions it actually needs.

### 2. Defense in depth

Don't rely on one security mechanism.

### 3. Secrets are credentials

Treat API keys, tokens, SSH keys and passwords as extremely sensitive.

### 4. Don't trust input

PRs, branches, commits and issue text can be attacker-controlled.

### 5. Protect CI/CD

Your GitHub Actions pipeline is part of your production security boundary.

### 6. Make important things immutable

This is why SHA-pinned Actions and immutable image tags are useful.

### 7. Separate environments

```text
development
staging
production
```

should not share unrestricted credentials.

### 8. Reduce blast radius

If something is compromised:

```text
What can it access?
```

should have a very small answer.

### 9. Audit continuously

Security configuration becomes stale.

### 10. Assume compromise is possible

Design your system so that:

```text
developer account compromised
        ↓
doesn't automatically mean
        ↓
production compromised
```

That's the real goal.

---

## One particularly important recommendation for your setup

Because you are building an AI SaaS stack with **FastAPI/Python, PostgreSQL, Redis, Qdrant, Docker, GHCR/Docker Hub, GitHub Actions and a homelab deployment**, I would eventually build your security pipeline around this exact model:

```text
                    ┌───────────────┐
                    │   Developer   │
                    └───────┬───────┘
                            │
                       SSH signed
                         commit
                            │
                            ▼
                    ┌───────────────┐
                    │    GitHub     │
                    │               │
                    │ Rulesets      │
                    │ PR review     │
                    │ CODEOWNERS    │
                    └───────┬───────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │   GitHub Actions   │
                 │                    │
                 │ contents: read     │
                 │ SHA-pinned Actions │
                 └─────────┬──────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
        Secret scan      SAST       Dependency scan
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                         Tests
                           │
                           ▼
                     Docker Build
                           │
                           ▼
                    Image Scan/ SBOM
                           │
                           ▼
                       Attestation
                           │
                           ▼
                     GHCR / Registry
                           │
                           ▼
                 Production Approval
                           │
                           ▼
                      Deployment
                           │
                           ▼
                    Homelab Server
                           │
                    ┌──────┴──────┐
                    │             │
                  Docker       Traefik
                    │
                 non-root
                 read-only
                 minimal caps
```

That gives you a **defense-in-depth supply-chain architecture**, rather than simply "GitHub Actions builds my Docker image."

GitHub's current security guidance specifically supports the major pieces here: least-privilege workflow permissions, SHA-pinned Actions, CODEOWNERS protection for workflows, OIDC for short-lived cloud credentials, dependency/security analysis, and artifact attestations. ([GitHub Docs][1])

If you want to implement this rather than just understand it, the best next step is to do it **hands-on, one phase at a time**. We can start with **Phase 1: completely hardening your GitHub accounts + your two SSH identities on Fedora 44**, then move to repository rulesets, then Actions, and finally your Docker/production deployment.

[1]: https://docs.github.com/en/actions/reference/security/secure-use?learn=getting_started&learnProduct=actions&utm_source=chatgpt.com "Secure use reference - GitHub Docs"
[2]: https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits?apiVersion=2022-11-28&utm_source=chatgpt.com "Signing commits - GitHub Docs"
[3]: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets?utm_source=chatgpt.com "Available rules for rulesets - GitHub Docs"
[4]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/actions-policies/about-actions-policies?utm_source=chatgpt.com "About Actions policies - GitHub Docs"
[5]: https://docs.github.com/en/code-security/reference/secret-security/secret-types?utm_source=chatgpt.com "Understanding GitHub secret types - GitHub Docs"
[6]: https://docs.github.com/en/actions/reference/security/oidc?utm_source=chatgpt.com "OpenID Connect reference - GitHub Docs"
[7]: https://docs.github.com/en/actions/reference/security?utm_source=chatgpt.com "Security reference - GitHub Docs"
[8]: https://docs.github.com/en/actions/how-tos/secure-your-work?utm_source=chatgpt.com "Security for GitHub Actions - GitHub Docs"
