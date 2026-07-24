# Traefik: Complete Beginner-to-Advanced Guide

This guide teaches Traefik from the ground up. Every step builds on the last and gets progressively harder. Every command/config is commented so you understand *why*, not just *what*. Since you use Docker a lot, every section shows **both** a direct (binary) install version **and** a Docker version.

---

## STEP 0 — Theory: What is Traefik and why does it exist?

### The problem it solves
Imagine you run 5 apps on one server:
- `app1` on port 3000
- `app2` on port 4000
- `api` on port 5000
- `admin panel` on port 6000
- `blog` on port 7000

Without a reverse proxy, your users would have to remember `yourserver.com:3000`, `yourserver.com:4000`, etc. That's ugly and insecure (you're exposing many ports to the internet). Also, none of these apps have HTTPS by default — you'd have to configure SSL certificates separately for each one.

**Traefik sits in front of all these apps** as a single entry point (usually port 80/443). It looks at the incoming request (the domain name, the path, headers, etc.) and decides *which app* should handle it, then forwards ("proxies") the traffic there. It can also automatically get free HTTPS certificates for every app.

### Key vocabulary (learn these — everything else builds on them)

| Term | Meaning |
|---|---|
| **EntryPoint** | The "door" Traefik listens on. Example: port 80 (HTTP) or port 443 (HTTPS). |
| **Router** | The traffic cop. It inspects the request (e.g. "is the Host header `app1.example.com`?") and decides which Service should handle it. |
| **Service** | The actual backend — the real app/container that will process the request. |
| **Middleware** | Something that modifies the request/response along the way (e.g. redirect HTTP→HTTPS, add auth, rate-limit). Optional, chained between Router and Service. |
| **Provider** | Where Traefik gets its configuration from. Examples: a static file, Docker labels, Kubernetes, Consul. This is what makes Traefik "dynamic" — it watches Docker and auto-updates routes when containers start/stop. |

### Static config vs Dynamic config (important distinction!)
- **Static configuration**: settings Traefik needs at startup and can't change without a restart. Example: which entrypoints exist, which providers to use, dashboard on/off. Set via a `traefik.yml` file, CLI flags, or environment variables.
- **Dynamic configuration**: the actual routing rules (routers, services, middlewares). These CAN change live, without restarting Traefik — that's the whole point. Set via a file provider, or (most commonly for you) **Docker labels**.

Think of it like this: static config = "how the restaurant kitchen is built." Dynamic config = "today's menu," which can change every day without rebuilding the kitchen.

---

## STEP 1 — Installation

### Option A: Direct (binary) install on Linux

```bash
# 1. Download the latest Traefik binary (check https://github.com/traefik/traefik/releases for the newest version number)
curl -L https://github.com/traefik/traefik/releases/download/v3.1.2/traefik_v3.1.2_linux_amd64.tar.gz -o traefik.tar.gz

# 2. Extract the tar.gz archive
tar -xzf traefik.tar.gz

# 3. Move the binary somewhere in your PATH so you can run "traefik" from anywhere
sudo mv traefik /usr/local/bin/

# 4. Confirm it works and check the version
traefik version
```

### Option B: Docker install

You don't "install" Traefik with Docker — you just run it as a container. No download/PATH steps needed.

```bash
# Pull the official image (Docker Hub: traefik)
docker pull traefik:v3.1

# Quick sanity check: run it once just to see the version, then remove the container
docker run --rm traefik:v3.1 version
```

**Why Docker is nicer for Traefik specifically:** Traefik's main superpower is watching the Docker socket and auto-discovering containers. Running Traefik itself in Docker keeps everything in one ecosystem.

---

## STEP 2 — Your first working Traefik (static config + dashboard)

This step gets Traefik running and lets you see its dashboard, proving it's alive. No real apps routed yet.

### Direct install version

Create a folder and a static config file `traefik.yml`:

```yaml
# traefik.yml
# ---------------------------------------------
# STATIC CONFIGURATION FILE
# This controls how Traefik itself boots up.
# ---------------------------------------------

entryPoints:
  web:
    # "web" is just a name we chose. It listens on port 80 (plain HTTP).
    address: ":80"

api:
  # Enables the built-in API, which the dashboard uses.
  dashboard: true
  # insecure: true means the dashboard is served with NO authentication
  # on port 8080. Fine for local testing, NEVER do this in production.
  insecure: true

log:
  level: INFO   # options: DEBUG, INFO, WARN, ERROR — DEBUG is noisy but useful when learning
```

Run it:

```bash
# --configFile tells Traefik which static config file to load
traefik --configFile=traefik.yml
```

Now open `http://localhost:8080` in your browser — you'll see the Traefik dashboard (currently empty, since we haven't routed anything yet).

### Docker version

Run Traefik as a container, mapping the ports and mounting the config:

```bash
docker run -d \
  --name traefik \
  -p 80:80 \       # map host port 80 -> container port 80 (the "web" entrypoint)
  -p 8080:8080 \   # map host port 8080 -> container port 8080 (the dashboard)
  -v $(pwd)/traefik.yml:/etc/traefik/traefik.yml \  # mount our static config into the default location Traefik reads from
  traefik:v3.1
```

Same `traefik.yml` as above works here. Visit `http://localhost:8080` — same empty dashboard.

**Checkpoint:** if you see the dashboard, Traefik itself is working correctly. Now let's route real traffic to it.

---

## STEP 3 — Routing your first real app (Docker provider)

This is where Traefik gets fun: it will **auto-discover** containers using labels, no manual route files needed.

### Update `traefik.yml` to enable the Docker provider

```yaml
entryPoints:
  web:
    address: ":80"

api:
  dashboard: true
  insecure: true

providers:
  docker:
    # exposedByDefault: false means Traefik will IGNORE containers
    # unless they explicitly opt in with a label (traefik.enable=true).
    # This is a critical safety setting — without it, Traefik would try
    # to expose EVERY container on your machine to the internet.
    exposedByDefault: false
```

### Docker Compose version (recommended — this is how you'll really use Traefik)

```yaml
# docker-compose.yml
version: "3.9"

services:
  traefik:
    image: traefik:v3.1
    command:
      # These CLI flags are equivalent to writing them in traefik.yml.
      # Using command: here is common because it keeps everything in one file.
      - "--entrypoints.web.address=:80"
      - "--api.dashboard=true"
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
    ports:
      - "80:80"
      - "8080:8080"
    volumes:
      # Mounting the Docker socket lets Traefik "see" other containers
      # (their labels, when they start/stop, etc). This is the magic
      # that makes dynamic discovery work.
      - /var/run/docker.sock:/var/run/docker.sock:ro   # read-only, for safety

  whoami:
    # "whoami" is a tiny test app that just echoes request info back — great for testing
    image: traefik/whoami
    labels:
      # This is DYNAMIC configuration, defined as Docker labels on the app itself,
      # not in Traefik's own config file. Traefik reads these labels live.
      - "traefik.enable=true"   # opt this container INTO Traefik (required, since exposedByDefault=false)
      - "traefik.http.routers.whoami.rule=Host(`whoami.localhost`)"
      # ^ the ROUTER: "if the request's Host header is whoami.localhost, use this route"
      - "traefik.http.routers.whoami.entrypoints=web"
      # ^ tells the router which entrypoint (door) it should listen on
```

Start it:

```bash
docker compose up -d
```

Test it:

```bash
# curl with a fake Host header, simulating a browser request to whoami.localhost
curl -H "Host: whoami.localhost" http://localhost
```

You should get back a text response showing headers, IP, etc. Also check `http://localhost:8080` — you'll now see the `whoami` router listed on the dashboard!

### Direct install equivalent (no Docker provider — file provider instead)

Without Docker, you don't have container labels, so you define routes in a **dynamic config file** instead.

`traefik.yml` (static):
```yaml
entryPoints:
  web:
    address: ":80"
api:
  dashboard: true
  insecure: true
providers:
  file:
    filename: dynamic.yml   # tell Traefik where to find dynamic routing rules
    watch: true             # auto-reload when this file changes
```

`dynamic.yml` (dynamic — the actual routes):
```yaml
http:
  routers:
    whoami:
      rule: "Host(`whoami.localhost`)"
      entryPoints:
        - web
      service: whoami-service

  services:
    whoami-service:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:5000"   # wherever your real app is running
```

---

## STEP 4 — Load balancing multiple instances of an app

A **Service** can point to more than one backend server. Traefik will round-robin between them — this is real load balancing.

### Docker Compose version

```yaml
services:
  traefik:
    image: traefik:v3.1
    command:
      - "--entrypoints.web.address=:80"
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
    ports:
      - "80:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

  whoami:
    image: traefik/whoami
    # "deploy.replicas" only works in Swarm mode; for plain docker compose,
    # scale using the CLI instead (see command below).
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.whoami.rule=Host(`whoami.localhost`)"
      - "traefik.http.routers.whoami.entrypoints=web"
      # We're NOT specifying a port label here because whoami only exposes one port.
      # If a container exposes multiple ports, you'd add:
      # "traefik.http.services.whoami.loadbalancer.server.port=80"
```

Scale it up to 3 copies:

```bash
# This spins up 3 containers of the "whoami" service.
# Traefik automatically detects all 3 (via the Docker provider watching events)
# and load-balances between them — no config changes needed!
docker compose up -d --scale whoami=3
```

Test with several requests — notice the "Hostname" field in the response changes, proving it's hitting different containers:

```bash
for i in 1 2 3 4; do curl -s -H "Host: whoami.localhost" http://localhost | grep Hostname; done
```

### Direct install equivalent

You'd manually list multiple server URLs under the same service in `dynamic.yml`:

```yaml
http:
  services:
    whoami-service:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:5001"
          - url: "http://127.0.0.1:5002"
          - url: "http://127.0.0.1:5003"
        # (Optional) health check: Traefik will periodically ping this path
        # and automatically stop sending traffic to unhealthy servers.
        healthCheck:
          path: /health
          interval: "10s"
          timeout: "3s"
```

---

## STEP 5 — Middlewares (redirects, headers, basic auth)

Middlewares sit between the Router and the Service, modifying traffic. You chain them onto a router.

### Example: force HTTP → HTTPS redirect (Docker labels)

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.whoami.rule=Host(`whoami.localhost`)"
  - "traefik.http.routers.whoami.entrypoints=web"
  # Define a middleware called "redirect-https"
  - "traefik.http.middlewares.redirect-https.redirectscheme.scheme=https"
  # Attach it to our router
  - "traefik.http.routers.whoami.middlewares=redirect-https"
```

### Example: HTTP Basic Auth (protect the dashboard properly — see Step 7)

```yaml
labels:
  # Generate the password hash first with: htpasswd -nb admin yourpassword
  # (install with: sudo apt install apache2-utils)
  - "traefik.http.middlewares.my-auth.basicauth.users=admin:$$apr1$$xyz...hashedpassword"
  - "traefik.http.routers.whoami.middlewares=my-auth"
```

**Note:** in Docker Compose YAML, `$` must be escaped as `$$`, otherwise Compose tries to interpret it as a variable substitution.

### Direct install equivalent (dynamic.yml)

```yaml
http:
  middlewares:
    redirect-https:
      redirectScheme:
        scheme: https

    my-auth:
      basicAuth:
        users:
          - "admin:$apr1$xyz...hashedpassword"   # no need to escape $ here, it's not Compose

  routers:
    whoami:
      rule: "Host(`whoami.localhost`)"
      entryPoints:
        - web
      middlewares:
        - redirect-https
      service: whoami-service
```

---

## STEP 6 — Automatic HTTPS with Let's Encrypt (ACME)

This is Traefik's headline feature: **zero-effort, auto-renewing, free SSL certificates.**

### Prerequisites
- A real domain name pointing to your server's public IP (Let's Encrypt can't issue certs for `localhost` or private IPs).
- Ports 80 and 443 open to the internet.

### Docker Compose version

```yaml
services:
  traefik:
    image: traefik:v3.1
    command:
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"   # new entrypoint for HTTPS
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      # ACME (Let's Encrypt) settings:
      - "--certificatesresolvers.myresolver.acme.email=you@example.com"   # LE will email you about cert issues
      - "--certificatesresolvers.myresolver.acme.storage=/letsencrypt/acme.json"   # where certs get saved
      - "--certificatesresolvers.myresolver.acme.httpchallenge.entrypoint=web"
      # ^ "HTTP challenge" is how Let's Encrypt verifies you own the domain:
      # it makes a request to port 80 and expects a specific response.
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt   # persist certs across restarts! Without this you'd hit LE rate limits.

  whoami:
    image: traefik/whoami
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.whoami.rule=Host(`whoami.yourdomain.com`)"
      - "traefik.http.routers.whoami.entrypoints=websecure"    # now listening on HTTPS entrypoint
      - "traefik.http.routers.whoami.tls.certresolver=myresolver"  # tells this router to use our ACME resolver
```

Important file-permission note:
```bash
# acme.json MUST have 600 permissions or Traefik will refuse to use it (security requirement)
touch letsencrypt/acme.json
chmod 600 letsencrypt/acme.json
```

### Direct install equivalent (traefik.yml)

```yaml
entryPoints:
  web:
    address: ":80"
  websecure:
    address: ":443"

certificatesResolvers:
  myresolver:
    acme:
      email: you@example.com
      storage: acme.json
      httpChallenge:
        entryPoint: web

providers:
  file:
    filename: dynamic.yml
    watch: true
```

`dynamic.yml`:
```yaml
http:
  routers:
    whoami:
      rule: "Host(`whoami.yourdomain.com`)"
      entryPoints:
        - websecure
      tls:
        certResolver: myresolver
      service: whoami-service
```

---

## STEP 7 — Securing the dashboard properly

`api.insecure=true` is only for local testing. In production, expose the dashboard as a normal router, protected by auth and HTTPS.

```yaml
command:
  - "--api.dashboard=true"
  # NOTE: api.insecure is REMOVED — dashboard is no longer open on 8080

labels:
  - "traefik.enable=true"
  # The dashboard's internal service is called "api@internal" — special built-in name
  - "traefik.http.routers.dashboard.rule=Host(`traefik.yourdomain.com`)"
  - "traefik.http.routers.dashboard.service=api@internal"
  - "traefik.http.routers.dashboard.entrypoints=websecure"
  - "traefik.http.routers.dashboard.tls.certresolver=myresolver"
  - "traefik.http.routers.dashboard.middlewares=my-auth"   # reuse the basic-auth middleware from Step 5
```

---

## STEP 8 — Multiple apps, path-based routing, and priorities

You can route by path instead of (or combined with) domain:

```yaml
labels:
  - "traefik.http.routers.api.rule=Host(`example.com`) && PathPrefix(`/api`)"
  - "traefik.http.routers.frontend.rule=Host(`example.com`)"
  # When rules overlap, Traefik picks the MORE SPECIFIC rule automatically,
  # but you can force it explicitly with priority (higher number = higher priority):
  - "traefik.http.routers.api.priority=10"
  - "traefik.http.routers.frontend.priority=1"
```

A common pattern: strip the `/api` prefix before forwarding, since your backend might not expect it:

```yaml
- "traefik.http.middlewares.strip-api.stripprefix.prefixes=/api"
- "traefik.http.routers.api.middlewares=strip-api"
```

---

## STEP 9 — Advanced: TCP/UDP routing, rate limiting, and Docker networks

### Isolating Traefik on its own Docker network (best practice)
Instead of exposing the Docker socket broadly and mixing networks, use a dedicated network:

```yaml
networks:
  traefik-net:
    external: true   # create once with: docker network create traefik-net

services:
  traefik:
    networks:
      - traefik-net
    # ...
  myapp:
    networks:
      - traefik-net
    # myapp does NOT need to publish ports to the host — Traefik reaches it
    # directly over the internal Docker network, which is more secure.
```

### Rate limiting middleware
```yaml
- "traefik.http.middlewares.ratelimit.ratelimit.average=100"  # 100 requests
- "traefik.http.middlewares.ratelimit.ratelimit.burst=50"     # allow short bursts above average
- "traefik.http.routers.whoami.middlewares=ratelimit"
```

### TCP routing (e.g., proxying a raw database connection)
```yaml
entryPoints:
  postgres:
    address: ":5432"
```
```yaml
labels:
  - "traefik.tcp.routers.pg.rule=HostSNI(`*`)"   # TCP routing matches differently than HTTP
  - "traefik.tcp.routers.pg.entrypoints=postgres"
  - "traefik.tcp.services.pg.loadbalancer.server.port=5432"
```

---

## STEP 10 — Production checklist (putting it all together)

A realistic production `docker-compose.yml` skeleton:

```yaml
version: "3.9"

networks:
  traefik-net:
    external: true

services:
  traefik:
    image: traefik:v3.1
    restart: unless-stopped   # auto-restart on crash or server reboot
    command:
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--providers.docker.network=traefik-net"
      - "--certificatesresolvers.myresolver.acme.email=you@example.com"
      - "--certificatesresolvers.myresolver.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.myresolver.acme.httpchallenge.entrypoint=web"
      - "--api.dashboard=true"
      - "--log.level=WARN"     # quieter logs in production
      - "--accesslog=true"     # log every request — useful for debugging/auditing
    ports:
      - "80:80"
      - "443:443"
    networks:
      - traefik-net
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dashboard.rule=Host(`traefik.yourdomain.com`)"
      - "traefik.http.routers.dashboard.service=api@internal"
      - "traefik.http.routers.dashboard.entrypoints=websecure"
      - "traefik.http.routers.dashboard.tls.certresolver=myresolver"
      - "traefik.http.routers.dashboard.middlewares=my-auth"
      - "traefik.http.middlewares.my-auth.basicauth.users=admin:$$apr1$$hashedpw"
      # Global redirect: catch ALL http traffic and send to https
      - "traefik.http.routers.http-catchall.rule=HostRegexp(`{host:.+}`)"
      - "traefik.http.routers.http-catchall.entrypoints=web"
      - "traefik.http.routers.http-catchall.middlewares=redirect-https"
      - "traefik.http.middlewares.redirect-https.redirectscheme.scheme=https"
```

---

## Beginner Mistakes (learn from these before you make them!)

1. **Forgetting `exposedByDefault: false`.** Without it, Traefik tries to expose *every* container on your Docker host, including ones you never intended to be public. Always set this explicitly.

2. **Forgetting `traefik.enable=true` on containers.** Even with `exposedByDefault=false`, each app container needs this label or Traefik will ignore it silently — no error, it just won't route.

3. **Not mounting the Docker socket, or mounting it read-write unnecessarily.** Mount it read-only (`:ro`) — Traefik only needs to *read* container info, never write to Docker.

4. **Leaving `api.insecure=true` in production.** This exposes your dashboard (and full config, including internal service names) with zero authentication on port 8080. Always disable it and use a proper authenticated router (Step 7) in production.

5. **Losing Let's Encrypt certificates on every restart.** If you don't persist `acme.json` outside the container (via a volume), Traefik will request brand-new certificates every restart and you'll hit Let's Encrypt's rate limits (currently 5 duplicate certs per domain per week). Always mount it to a host path.

6. **Wrong permissions on `acme.json`.** It must be `chmod 600`. If it's more permissive, Traefik refuses to use it for security reasons and silently fails to save certs.

7. **Confusing static vs dynamic configuration.** Trying to put a router definition inside `traefik.yml` (static) instead of a dynamic file/labels — it won't work. Static config = *how Traefik boots*. Dynamic config = *the actual routes*.

8. **Not escaping `$` in Docker Compose label values.** Password hashes (bcrypt/apr1) contain `$` characters. In `docker-compose.yml`, write `$$` instead of `$`, or Compose will try (and fail) to substitute an environment variable.

9. **Expecting `.localhost` domains to work over the public internet.** `whoami.localhost` only resolves on your own machine (most OSes treat `*.localhost` as loopback). For real testing with real domains, you need actual DNS records or `/etc/hosts` entries.

10. **Multiple containers accidentally getting the same router name.** If two services define a router with the same name (e.g., both named `whoami`), Traefik will only keep one — leading to confusing "why isn't my second app showing up" bugs. Router (and service, middleware) names must be unique.

11. **Forgetting `traefik.http.services.<name>.loadbalancer.server.port` when a container exposes multiple ports.** Traefik can't guess which port to use, so it may pick the wrong one or fail to route.

12. **Not putting Traefik and your apps on the same Docker network.** If they're on different networks, Traefik can discover the container (via labels) but can't actually reach it, resulting in 502 Bad Gateway errors.

---

### Suggested next steps for you
- Get Step 3 running today (Docker Compose + whoami) since it's the fastest way to *see* Traefik working.
- Once comfortable, move to Step 6 (HTTPS) with a real domain you own.
- Explore the official docs for middlewares you haven't tried yet (compression, circuit breakers, retries): https://doc.traefik.io/traefik/middlewares/overview/
