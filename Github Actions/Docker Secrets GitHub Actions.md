# Q: how to configure and use docker secrets for my gitub actions for my ai saas product. i need to configure secrets fr both GHCR and docker hub such that when i push a code to github it should automatically create containers in GHCR and docker hub


# A:

For your setup, the cleanest production architecture is:

```
GitHub Repository
        │
        │ git push
        ▼
 GitHub Actions
        │
        ├─────────────── Build Docker Image
        │
        ├─────────────── Security Scan
        │
        ├─────────────── Login to GHCR
        │                     │
        │                     ▼
        │               Push to GHCR
        │
        ├─────────────── Login to Docker Hub
        │                     │
        │                     ▼
        │               Push to Docker Hub
        │
        ▼
 Release Complete
```

There are **three different kinds of secrets** involved here, and it's important not to confuse them.

| Secret Type         | Stored Where      | Used For               |
| ------------------- | ----------------- | ---------------------- |
| GitHub Secrets      | GitHub Repository | GitHub Actions         |
| Docker Secrets      | Docker Swarm      | Runtime containers     |
| Application Secrets | Server            | API keys, DB passwords |

For your CI/CD, you only need **GitHub Secrets**. Docker Secrets are **not** used by GitHub Actions.

---

# Step 1. Create Docker Hub Access Token

Never use your Docker Hub password.

Go to

```
Docker Hub
→ Account Settings
→ Personal Access Tokens
```

Create

```
Name:
github-actions

Permissions:
Read
Write
Delete (optional)
```

You'll receive something like

```
dckr_pat_1A2B3C4D5E6F...
```

Save it.

---

# Step 2. Create GitHub Personal Access Token (GHCR)

GHCR requires a GitHub token.

Go to

```
GitHub

Settings

Developer Settings

Personal Access Tokens

Fine Grained Token
```

Repository access

```
Only your repository
```

Permissions

```
Packages
    Read
    Write

Contents
    Read
```

Generate.

Example

```
github_pat_11ABCDEF...
```

---

# Step 3. Open Repository Secrets

Inside your GitHub repository

```
Settings

Secrets and variables

Actions
```

Click

```
New Repository Secret
```

---

# Step 4. Add Docker Hub Secrets

Secret Name

```
DOCKERHUB_USERNAME
```

Value

```
yourdockerusername
```

Next

```
DOCKERHUB_TOKEN
```

Value

```
dckr_pat_xxxxxxxxx
```

---

# Step 5. Add GHCR Secrets

If you're using a Personal Access Token, add:

```
GHCR_USERNAME
```

```
yourgithubusername
```

and

```
GHCR_TOKEN
```

```
github_pat_xxxxx
```

However, for repositories you own, you usually **do not need a personal token**. GitHub automatically provides a temporary `GITHUB_TOKEN` to every workflow. With the correct workflow permissions (`packages: write` and `contents: read`), it can publish to GHCR without storing another secret. This is generally the recommended approach.

---

# Step 6. Configure Workflow Permissions

At the top of your workflow:

```yaml
permissions:
  contents: read
  packages: write
```

This allows the built-in `GITHUB_TOKEN` to publish to GHCR.

---

# Step 7. Login to Docker Hub

```yaml
- name: Login to Docker Hub
  uses: docker/login-action@v3

  with:
    username: ${{ secrets.DOCKERHUB_USERNAME }}
    password: ${{ secrets.DOCKERHUB_TOKEN }}
```

Notice

```
password:
```

actually contains the Docker Hub **Access Token**, not your password.

---

# Step 8. Login to GHCR

Using the built-in token:

```yaml
- name: Login to GHCR
  uses: docker/login-action@v3

  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

If you decide to use a PAT instead:

```yaml
- name: Login to GHCR
  uses: docker/login-action@v3

  with:
    registry: ghcr.io
    username: ${{ secrets.GHCR_USERNAME }}
    password: ${{ secrets.GHCR_TOKEN }}
```

---

# Step 9. Build Once

```yaml
- name: Build Image

  uses: docker/build-push-action@v6

  with:
    context: .
    load: true
    tags: myimage:latest
```

Using `load: true` makes the built image available locally within the workflow for reuse.

---

# Step 10. Tag the Image

Docker Hub

```yaml
- run: |
    docker tag myimage:latest \
    vbcreators/ai-saas:latest
```

GHCR

```yaml
- run: |
    docker tag myimage:latest \
    ghcr.io/USERNAME/ai-saas:latest
```

---

# Step 11. Push

Docker Hub

```yaml
- run: docker push vbcreators/ai-saas:latest
```

GHCR

```yaml
- run: docker push ghcr.io/USERNAME/ai-saas:latest
```

---

# A Better Approach: Build Once, Push to Both Registries

Instead of building twice, `docker/build-push-action` can push to multiple registries in one step:

```yaml
- name: Build and Push
  uses: docker/build-push-action@v6

  with:
    context: .
    push: true
    tags: |
      ghcr.io/USERNAME/ai-saas:latest
      ghcr.io/USERNAME/ai-saas:${{ github.sha }}
      vbcreators/ai-saas:latest
      vbcreators/ai-saas:${{ github.sha }}
```

This is faster and avoids duplicate builds.

---

# How Secrets Are Accessed

Secrets are only available through the `secrets` context:

```yaml
${{ secrets.DOCKERHUB_TOKEN }}
```

GitHub injects the value at runtime. It is never stored in your repository, and GitHub masks it in workflow logs if it appears.

---

# Security Best Practices

* Never store passwords or tokens directly in your workflow YAML.
* Use Docker Hub Personal Access Tokens instead of your account password.
* Prefer the built-in `GITHUB_TOKEN` for GHCR publishing when possible.
* Give tokens the minimum required permissions.
* Rotate long-lived access tokens periodically.
* Avoid printing secrets with commands like `echo`.
* Protect your `main` branch with required reviews if publishing is triggered from it.
* Pin GitHub Actions to specific major versions (or commit SHAs for maximum supply-chain security).
* Use immutable image tags (for example, commit SHA or semantic version) in addition to `latest`.

---

## Recommended Production Flow

```
Developer
     │
git push
     │
     ▼
GitHub Actions
     │
     ├── Checkout
     ├── Restore cache
     ├── Run tests
     ├── Run linting
     ├── Build Docker image
     ├── Security scan
     ├── Login to GHCR
     ├── Login to Docker Hub
     ├── Push image to GHCR
     ├── Push image to Docker Hub
     ├── Create Git tag (on release)
     └── Notify deployment
                    │
                    ▼
          Watchtower on your server
                    │
             Pull latest image
                    │
          Restart container automatically
```

This approach aligns well with a production-grade homelab or SaaS deployment and avoids unnecessary duplication while keeping credentials secure.
