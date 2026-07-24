# The Complete Nginx Learning Path — From Zero to Confident

A step-by-step guide that goes from "what even is a web server" to running Nginx in production-style setups with Docker, reverse proxying, load balancing, and SSL. Every command is commented. Every concept is explained before you're asked to use it.

---

## STEP 0 — Theory: What Nginx Actually Is (Read this before touching a terminal)

### What is a web server, really?

When you type `google.com` into a browser, your computer sends a message over the internet that essentially says: *"Give me the webpage at this address."* Something on Google's servers has to **listen** for that message, **understand** what's being asked, and **respond** with data (HTML, images, JSON, etc.).

That "something" is a **web server**. It's just a program that:
1. Listens on a network port (usually port 80 for regular web traffic, or 443 for encrypted/HTTPS traffic)
2. Accepts incoming connections
3. Reads what the client is asking for
4. Sends back a response

Nginx (pronounced "engine-x") is one such program. Apache is another famous one. Node.js's `http` module can technically do it too. They all solve the same problem, but differently.

### Why is Nginx special?

Older web servers (like early Apache) handled traffic by spinning up a new **process or thread** for every single connection. If you had 10,000 people connecting at once, that meant 10,000 processes/threads competing for CPU and memory — this gets slow and resource-hungry fast.

Nginx uses a different model called **event-driven, asynchronous architecture**:

- Nginx starts a small number of **worker processes** (often one per CPU core).
- Each worker can handle **thousands of connections simultaneously** using non-blocking I/O — meaning it doesn't sit around "waiting" for slow things (like a database query or a slow client) to finish. It moves on to handle other connections and comes back when there's actual work to do.

Think of it like a restaurant analogy:
- **Apache's old model** = one waiter assigned to one table, standing there the entire meal doing nothing until that table needs something.
- **Nginx's model** = a few waiters who circulate constantly, only stopping at a table the instant it actually needs something, then moving on.

This is why Nginx can handle huge amounts of traffic with relatively little memory and CPU.

### What is Nginx used for? (This matters — Nginx wears many hats)

1. **Static web server** — serving HTML/CSS/JS/image files directly to browsers.
2. **Reverse proxy** — sitting in front of your actual application (e.g., a Node.js, Python, or Java app) and forwarding requests to it. The client only ever talks to Nginx; Nginx talks to your app behind the scenes.
3. **Load balancer** — distributing incoming traffic across multiple copies of your app so no single server gets overwhelmed.
4. **SSL/TLS terminator** — handling the encryption/decryption of HTTPS traffic so your backend app doesn't have to.
5. **Caching layer** — storing copies of responses so repeated requests don't have to hit your slow backend every time.

You'll use Nginx for **all of these** by the end of this guide, in increasing order of complexity.

### The master-worker process model (important for later, e.g. reloading config)

When Nginx starts, it creates:
- **One master process** — reads the configuration file, manages the worker processes, doesn't handle traffic itself.
- **One or more worker processes** — these actually handle client connections and requests.

This matters because when you *reload* Nginx's configuration (which you'll do constantly), the master process spins up new workers with the new config and gracefully lets old workers finish their current requests before shutting down — meaning **zero downtime reloads**. This is a big deal in production.

---

## STEP 1 — Installing Nginx (Two ways: Native install vs Docker)

I'll teach you both, because understanding native installation first makes Docker make more sense later.

### 1A. Native installation (directly on a Linux machine, e.g. Ubuntu)

```bash
# Update the list of available packages from Ubuntu's repositories
# This doesn't install anything yet -- it just refreshes what versions are available
sudo apt update

# Install nginx from the official Ubuntu package repository
# "-y" auto-confirms the "do you want to continue?" prompt
sudo apt install nginx -y

# Check that nginx installed correctly and see its version
nginx -v

# Check if the nginx service is running
sudo systemctl status nginx
```

After this, if you open a browser and go to `http://localhost` (or your server's IP), you'll see the default "Welcome to nginx!" page. That page is just a static HTML file Nginx is serving out of the box.

Useful service commands you'll use constantly:

```bash
# Start nginx if it's not running
sudo systemctl start nginx

# Stop nginx completely
sudo systemctl stop nginx

# Restart nginx (stops then starts -- causes a brief connection drop)
sudo systemctl restart nginx

# Reload nginx (re-reads config WITHOUT dropping active connections -- preferred method)
sudo systemctl reload nginx

# Make nginx start automatically when the machine boots
sudo systemctl enable nginx
```

**Key lesson:** always prefer `reload` over `restart` when you've only changed configuration. `restart` briefly kills the process (dropping active connections); `reload` gracefully swaps in new config.

### 1B. Docker installation (explained from first principles, since you're new to Docker)

**What is Docker, in one paragraph?**
Docker lets you package an application together with everything it needs to run (its own mini operating-system-like environment, dependencies, config) into a single unit called a **container**. Instead of installing Nginx directly onto your computer (where it might conflict with other software, or behave differently on different machines), you run it inside an isolated container that behaves identically everywhere. Think of a container as a lightweight, disposable virtual machine that starts in milliseconds.

A **Docker image** is the blueprint (like a recipe). A **container** is a running instance of that image (like a dish made from the recipe). You can spin up and destroy containers constantly without affecting your actual machine.

```bash
# Pull (download) the official nginx image from Docker Hub (the public registry of images)
# "latest" is a "tag" -- meaning the newest stable version
docker pull nginx:latest

# Run a container from that image
docker run \
  --name my-nginx \        # give the container a friendly name instead of a random one
  -d \                     # "detached" mode -- runs in the background instead of taking over your terminal
  -p 8080:80 \              # map port 8080 on YOUR machine to port 80 INSIDE the container
                             # (nginx listens on port 80 by default inside the container)
  nginx:latest              # the image to run

# Check that it's running
docker ps
```

Now open `http://localhost:8080` in your browser — you'll see the same "Welcome to nginx!" page, except it's running fully isolated inside a container instead of directly on your machine.

**Why the port mapping `-p 8080:80` matters:** Inside the container, Nginx is listening on port 80, exactly like a native install. But your actual machine (the "host") can't see inside the container directly. The `-p HOST_PORT:CONTAINER_PORT` flag tells Docker: "forward any traffic that arrives at my machine's port 8080 into the container's port 80." You could map it to any host port, e.g. `-p 9000:80`.

Other essential Docker commands:

```bash
# See all running containers
docker ps

# See ALL containers, including stopped ones
docker ps -a

# Stop the container (doesn't delete it)
docker stop my-nginx

# Start it again later
docker start my-nginx

# Remove the container completely (must be stopped first)
docker rm my-nginx

# View the container's logs (very useful for debugging)
docker logs my-nginx

# Follow logs live (like "tail -f")
docker logs -f my-nginx

# Get an interactive shell INSIDE the running container
# This lets you poke around the container's filesystem like it's a mini Linux machine
docker exec -it my-nginx /bin/bash
```

From this point forward in the guide, I'll show you commands for **both** native and Docker setups where it matters, but the actual **Nginx configuration syntax is identical either way** — that's the whole point of learning Nginx itself, independent of how it's deployed.

---

## STEP 2 — Understanding the Configuration File Structure

Before writing any config, you need to know **where files live** and **how the syntax works**.

### Where config files live (native install)

```bash
/etc/nginx/nginx.conf          # the main config file -- the entry point
/etc/nginx/sites-available/    # where you WRITE individual site configs (not active yet)
/etc/nginx/sites-enabled/      # where ACTIVE site configs live (usually symlinks to sites-available)
/etc/nginx/conf.d/             # alternative location for extra config snippets, auto-loaded
/var/www/html/                 # default location Nginx serves static files from
/var/log/nginx/access.log      # logs every request made to the server
/var/log/nginx/error.log       # logs errors (misconfigurations, failed requests, etc.)
```

**Why `sites-available` vs `sites-enabled`?** This is a convention (not a hard rule) that lets you keep configs for many different sites written out, but only "turn on" the ones you want by creating a symbolic link (a shortcut) in `sites-enabled`. It's like having a folder of all possible playlists (`available`) but only some are actually queued up to play (`enabled`).

### Where config lives in the Docker Nginx image

Same paths, but *inside* the container: `/etc/nginx/nginx.conf`, `/etc/nginx/conf.d/default.conf`, etc. Later, we'll learn how to get your own config files into the container.

### Basic syntax rules of Nginx config files

```nginx
# This is a comment -- nginx ignores anything after a "#"

# Nginx config is made of "directives" (settings) and "blocks" (grouped settings in { })
# Every simple directive line MUST end with a semicolon ;

worker_processes auto;   # <-- directive: "worker_processes" is the setting, "auto" is the value

# A "block" groups related directives together using curly braces
http {
    # settings inside here apply to all HTTP traffic handling

    server {
        # settings inside here apply to ONE specific "virtual server" (site)

        location / {
            # settings inside here apply to requests matching the path "/"
        }
    }
}
```

The nesting matters a lot: `http { server { location { } } }` is the typical hierarchy. Settings defined at an outer level (like `http`) are inherited by inner blocks (like `server`) unless overridden.

### The main nginx.conf skeleton, fully explained

```nginx
# ---- TOP LEVEL (called "main" context) ----
# Settings here affect the whole nginx process, not just HTTP traffic

user www-data;              # which system user nginx worker processes run as (security-relevant)
worker_processes auto;      # "auto" tells nginx to spawn one worker per CPU core detected
error_log /var/log/nginx/error.log warn;  # where to log errors, and minimum severity level to log
pid /run/nginx.pid;         # file where nginx stores its master process ID

events {
    # settings related to how nginx handles connections at a low level
    worker_connections 1024;  # max simultaneous connections EACH worker process can handle
}

http {
    # settings related to HTTP traffic specifically

    include       /etc/nginx/mime.types;  # load a file that maps file extensions to content types
                                            # (so nginx knows to send .html as text/html, .png as image/png, etc.)
    default_type  application/octet-stream;  # fallback content type if unknown

    sendfile on;  # enables an efficient kernel-level method of sending files (performance optimization)

    keepalive_timeout 65;  # how long (seconds) to keep a client connection open for reuse

    # Pull in additional config files -- this is how sites-enabled and conf.d get loaded
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

**Key takeaway:** `nginx.conf` is mostly just a shell that sets global behavior and then **includes** other files. You'll rarely edit `nginx.conf` directly after initial setup — you'll mostly work inside individual site config files.

### Testing and applying configuration changes (memorize this workflow)

```bash
# ALWAYS test your config syntax before reloading -- this catches typos before they break your server
sudo nginx -t

# Expected successful output looks like:
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful

# Only if the test passes, reload nginx to apply changes
sudo systemctl reload nginx
```

**This two-step habit (test, then reload) will save you from countless outages.** Never reload blindly.

---

## STEP 3 — Your First Real Config: Serving a Static Website

Let's make Nginx serve an actual website you control, instead of the default welcome page.

### 3A. Native setup

```bash
# Create a directory to hold your website files
sudo mkdir -p /var/www/mysite

# Create a simple test HTML file
echo "<h1>Hello from my first Nginx site!</h1>" | sudo tee /var/www/mysite/index.html

# Create a new site config file
sudo nano /etc/nginx/sites-available/mysite
```

Paste this into the file:

```nginx
server {
    listen 80;                     # listen for incoming traffic on port 80 (standard HTTP port)
    server_name mysite.local;      # the hostname this server block responds to
                                    # (for local testing, we'll map this in /etc/hosts later)

    root /var/www/mysite;          # the base directory nginx serves files from for this site
    index index.html;              # the default file to serve when a directory is requested

    location / {
        # "location /" means: for any request path starting with "/"
        try_files $uri $uri/ =404;
        # try_files attempts, in order:
        #   1. $uri            -- the exact file requested (e.g. /about.html)
        #   2. $uri/            -- treat it as a directory and look for an index file inside
        #   3. =404             -- if nothing matches, return an actual 404 Not Found response
    }
}
```

```bash
# Enable the site by creating a symbolic link into sites-enabled
sudo ln -s /etc/nginx/sites-available/mysite /etc/nginx/sites-enabled/

# Test the config for syntax errors
sudo nginx -t

# Reload nginx to apply the new config
sudo systemctl reload nginx

# Map "mysite.local" to your own machine for local testing
# (edit your hosts file so your OS resolves this fake domain to localhost)
echo "127.0.0.1 mysite.local" | sudo tee -a /etc/hosts
```

Now visiting `http://mysite.local` in your browser shows your custom HTML page.

### 3B. Docker equivalent

With Docker, instead of editing files inside the container directly (changes would be lost when the container is deleted), we use **volumes** — a way of sharing a folder from your actual machine into the container.

```bash
# -v HOST_PATH:CONTAINER_PATH mounts your local folder into the container
docker run \
  --name my-nginx \
  -d \
  -p 8080:80 \
  -v /var/www/mysite:/usr/share/nginx/html:ro \
  # ":ro" = read-only -- the container can read these files but not modify them
  nginx:latest
```

`/usr/share/nginx/html` is the **default** root directory in the official Nginx Docker image (different from the `/var/www` convention on native Ubuntu — the Docker image has its own defaults). Anything you put in your local `/var/www/mysite` folder now appears inside the container automatically, live.

---

## STEP 4 — Location Blocks and Matching Rules (Where Nginx Gets Powerful)

`location` blocks decide **which config applies to which URL path**. Understanding matching precedence is one of the most important Nginx skills.

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/example;

    # EXACT match -- only matches the URL "/exactly-this", nothing else
    location = /exactly-this {
        return 200 "You hit the exact match\n";
    }

    # PREFIX match -- matches anything starting with /images/
    location /images/ {
        root /var/www/example;
    }

    # REGEX match (case-sensitive) -- matches paths ending in these file extensions
    location ~ \.(jpg|jpeg|png|gif)$ {
        expires 30d;   # tell browsers to cache these files for 30 days
    }

    # REGEX match (case-INsensitive) -- note the ~* instead of ~
    location ~* \.(css|js)$ {
        expires 7d;
    }

    # Generic catch-all prefix match (lowest priority among these)
    location / {
        try_files $uri $uri/ =404;
    }
}
```

**Matching priority order (memorize this — it trips up everyone at first):**
1. Exact match (`location = /path`) — highest priority, stops searching immediately.
2. Regex matches (`location ~` or `location ~*`) — checked in the order they appear in the file, first match wins.
3. Prefix matches (`location /path/`) — the *longest* matching prefix wins.
4. The plain `location /` catch-all — lowest priority, used as a fallback.

This is a common beginner trap: people assume location blocks are matched top-to-bottom like a simple list, but it's actually this priority system.

---

## STEP 5 — Reverse Proxying: Putting Nginx in Front of a Real Application

This is where Nginx becomes genuinely powerful. Instead of serving static files, we'll make Nginx forward requests to a backend application (like a Node.js or Python app) running on a different port.

### Why do this at all?

- You can put Nginx in front of an app and let Nginx handle HTTPS, compression, and caching, while your app focuses purely on business logic.
- You can run your app on a non-standard port (e.g. 3000) and let Nginx expose it cleanly on port 80/443.
- You can put MULTIPLE apps behind one Nginx instance and route by domain or path.

### Example: proxying to a Node.js app running on port 3000

Assume you already have some app running locally that responds on `http://127.0.0.1:3000`.

```nginx
server {
    listen 80;
    server_name myapp.local;

    location / {
        proxy_pass http://127.0.0.1:3000;
        # proxy_pass tells nginx: "don't serve a file yourself, forward this request to this address instead"

        # The following headers are CRITICAL and commonly forgotten by beginners.
        # Without them, your backend app loses important information about the original request.

        proxy_set_header Host $host;
        # forwards the ORIGINAL hostname the client requested (otherwise backend sees "127.0.0.1")

        proxy_set_header X-Real-IP $remote_addr;
        # forwards the client's real IP address (otherwise backend sees nginx's IP)

        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # forwards the full chain of IPs if there are multiple proxies involved

        proxy_set_header X-Forwarded-Proto $scheme;
        # tells backend whether original request was http or https
    }
}
```

Test and reload as always:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Running this whole setup with Docker Compose (introducing multi-container apps)

**What is Docker Compose?** Instead of running `docker run` with long commands for each container separately, Compose lets you describe your ENTIRE multi-container setup (e.g., "one Nginx container + one app container") in a single YAML file, then start everything with one command.

Folder structure:
```
myproject/
├── docker-compose.yml
├── nginx/
│   └── default.conf
└── app/
    └── (your app's code + Dockerfile)
```

`nginx/default.conf`:
```nginx
server {
    listen 80;

    location / {
        # Notice we use the SERVICE NAME "app" instead of an IP address or "localhost"
        # Docker Compose creates an internal network where containers can reach each other
        # by their service name, like a mini private DNS system
        proxy_pass http://app:3000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`docker-compose.yml`:
```yaml
# version of the compose file format (recent Docker versions no longer require this line, but it's fine to include)
version: "3.9"

services:
  # ---- our nginx container ----
  nginx:
    image: nginx:latest           # use the official nginx image
    ports:
      - "80:80"                   # expose port 80 on your machine, mapped to port 80 in the container
    volumes:
      # mount our custom config file into the container, replacing the default one
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - app                        # make sure "app" container starts before nginx (doesn't guarantee it's READY, just started)

  # ---- our backend application container ----
  app:
    build: ./app                   # build an image from the Dockerfile inside ./app
    expose:
      - "3000"                     # expose port 3000 to OTHER containers only (not to your host machine)
    # note: we don't need "ports" here because only nginx needs to reach it,
    # the outside world only ever talks to nginx
```

```bash
# Start the whole multi-container setup in the background
docker compose up -d

# View logs from all services combined
docker compose logs -f

# Stop and remove all containers defined in this compose file
docker compose down

# Rebuild images after you change the app's Dockerfile/code
docker compose up -d --build
```

**Key Docker Compose concept:** containers on the same Compose network can reach each other **by service name** (`app`, `nginx`) instead of IP addresses. This is why `proxy_pass http://app:3000;` works — Docker's internal DNS resolves `app` to the right container automatically, even if its IP changes on restart.

---

## STEP 6 — Load Balancing Across Multiple Backend Instances

Once one instance of your app isn't enough to handle traffic, you run several copies and let Nginx distribute requests between them.

```nginx
# "upstream" defines a named group of backend servers
upstream backend_servers {
    # default load balancing method is round-robin (each request goes to the next server in turn)
    server 127.0.0.1:3001;
    server 127.0.0.1:3002;
    server 127.0.0.1:3003;

    # you could instead specify weighted distribution:
    # server 127.0.0.1:3001 weight=3;   # gets 3x more traffic than the others
    # server 127.0.0.1:3002 weight=1;

    # or mark a server as backup (only used if all primary servers are down):
    # server 127.0.0.1:3004 backup;
}

server {
    listen 80;
    server_name myapp.local;

    location / {
        proxy_pass http://backend_servers;   # note: referencing the upstream NAME, not a specific server
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Load balancing algorithms available:**
```nginx
upstream backend_servers {
    least_conn;   # send new requests to whichever server currently has the FEWEST active connections
    # OR
    ip_hash;      # always send the same client IP to the same server (useful for session persistence)
    # (if you specify neither, it defaults to round-robin)

    server 127.0.0.1:3001;
    server 127.0.0.1:3002;
}
```

### Scaling this with Docker Compose

```yaml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - app

  app:
    build: ./app
    expose:
      - "3000"
    deploy:
      replicas: 3   # run 3 identical copies of this service
      # NOTE: "replicas" only works with "docker compose up --scale" on plain Compose,
      # or natively if you're using Docker Swarm. For plain Compose, use the scale flag instead:
```

```bash
# Alternative way to run multiple copies of a service with plain docker compose
docker compose up -d --scale app=3
```

Then in `nginx/default.conf`, since Docker Compose gives all replicas the SAME service name, you can point directly at the service name and Docker's internal DNS will round-robin between the replicas automatically:

```nginx
location / {
    proxy_pass http://app:3000;   # Docker DNS round-robins across all 3 "app" replicas automatically
}
```

This is a subtle but powerful point: **Docker Compose's built-in DNS load balancing can substitute for an explicit `upstream` block** in simple cases, but the explicit `upstream` approach gives you far more control (weights, health checks, algorithms) — which matters more as you scale.

---

## STEP 7 — HTTPS / SSL/TLS Setup (Securing Traffic)

### The theory first

HTTP traffic is sent in plaintext — anyone intercepting it (on public WiFi, a compromised router, etc.) can read it. HTTPS encrypts traffic using **TLS** (the modern successor to SSL — people still say "SSL" out of habit). To enable HTTPS, your server needs a **certificate** proving its identity, issued by a trusted **Certificate Authority (CA)**.

**Let's Encrypt** is a free, automated CA that most people use today. The tool `certbot` automates getting and renewing these certificates.

### 7A. Native setup with Certbot (requires a real domain pointed at your server)

```bash
# Install certbot and its nginx plugin
sudo apt install certbot python3-certbot-nginx -y

# Certbot will automatically detect your existing nginx server blocks,
# obtain a certificate for the domain, and edit your nginx config to use it
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Certbot sets up automatic renewal via a systemd timer or cron job -- verify it exists:
sudo systemctl list-timers | grep certbot

# You can manually test that renewal works without actually renewing:
sudo certbot renew --dry-run
```

After running certbot, your config gets automatically modified to look something like this:

```nginx
server {
    listen 443 ssl;                       # listen on the standard HTTPS port, with SSL enabled
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;      # the public certificate
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;    # the private key (keep secret!)

    # additional recommended settings certbot usually adds:
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        try_files $uri $uri/ =404;
    }
}

server {
    # this second block catches plain HTTP requests and redirects them to HTTPS
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
    # 301 = permanent redirect. $host = the requested hostname. $request_uri = the original path+query string.
}
```

### 7B. Docker setup with Certbot

This is more involved because the container's filesystem is normally ephemeral (temporary — wiped when the container is removed), so certificates need to live in a persisted volume.

```yaml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/www:/var/www/certbot:ro          # used for the domain-ownership verification challenge
      - ./certbot/conf:/etc/letsencrypt:ro          # where the actual certificates get stored

  certbot:
    image: certbot/certbot
    volumes:
      - ./certbot/www:/var/www/certbot
      - ./certbot/conf:/etc/letsencrypt
    # this container runs once to obtain a cert, then exits -- you re-run it periodically for renewal
    entrypoint: >
      certonly --webroot -w /var/www/certbot
      --email you@example.com -d yourdomain.com
      --agree-tos --no-eff-email
```

```bash
# First run: obtain the initial certificate
docker compose run --rm certbot

# Afterward, reload nginx so it picks up the new certificate files
docker compose exec nginx nginx -s reload

# Set up a cron job on your HOST machine (outside Docker) to renew periodically, e.g. twice daily:
# 0 */12 * * * docker compose run --rm certbot renew && docker compose exec nginx nginx -s reload
```

### Security hardening additions worth knowing about

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;     # only allow modern, secure TLS versions -- disable old vulnerable ones
    ssl_prefer_server_ciphers on;       # server picks the strongest mutually-supported cipher, not the client

    add_header Strict-Transport-Security "max-age=63072000" always;
    # HSTS header -- tells browsers "always use HTTPS for this domain from now on, even if the user types http://"
}
```

---

## STEP 8 — Caching (Making Nginx Fast for Repeated Requests)

Caching stores a copy of a response so future identical requests don't need to hit your (potentially slow) backend again.

```nginx
# Define WHERE and HOW cached content is stored -- placed in the http {} block
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m max_size=1g inactive=60m use_temp_path=off;
# levels=1:2       -- organizes cached files into a 2-level subdirectory structure (performance optimization)
# keys_zone=my_cache:10m  -- names this cache "my_cache" and reserves 10MB of memory for tracking cache KEYS
#                             (not the actual cached data itself, just metadata -- 10MB can track ~80,000 keys)
# max_size=1g      -- cap the total disk space cache can use to 1GB
# inactive=60m     -- remove cached items that haven't been requested in 60 minutes
# use_temp_path=off -- write cache files directly to the cache path (slightly faster)

server {
    listen 80;
    server_name myapp.local;

    location / {
        proxy_pass http://127.0.0.1:3000;

        proxy_cache my_cache;             # use the cache zone defined above
        proxy_cache_valid 200 10m;        # cache successful (200) responses for 10 minutes
        proxy_cache_valid 404 1m;         # cache 404 responses too, but for a shorter time

        add_header X-Cache-Status $upstream_cache_status;
        # adds a response header showing HIT, MISS, EXPIRED, etc. -- extremely useful for debugging caching
    }
}
```

```bash
# After changing cache config, always test then reload
sudo nginx -t && sudo systemctl reload nginx
```

Check whether caching is working by inspecting response headers:

```bash
# -I fetches only the headers, not the full body -- fast way to check cache status
curl -I http://myapp.local/
# Look for the "X-Cache-Status" header we added: MISS on first request, HIT on subsequent ones
```

---

## STEP 9 — Logging and Monitoring (Understanding What's Actually Happening)

```nginx
http {
    # Define a custom log FORMAT -- gives you control over exactly what gets logged
    log_format detailed '$remote_addr - $remote_user [$time_local] '
                         '"$request" $status $body_bytes_sent '
                         '"$http_referer" "$http_user_agent" '
                         'rt=$request_time';
    # $remote_addr     -- client's IP address
    # $remote_user     -- authenticated username, if any (basic auth)
    # $time_local      -- timestamp of the request
    # $request         -- the actual HTTP request line, e.g. "GET /index.html HTTP/1.1"
    # $status          -- HTTP response status code, e.g. 200, 404, 500
    # $body_bytes_sent -- size of the response body
    # $http_referer    -- what page the client was on when it made this request
    # $http_user_agent -- what browser/client made the request
    # $request_time    -- how long the request took to process (in seconds) -- great for spotting slow endpoints

    server {
        listen 80;
        access_log /var/log/nginx/myapp_access.log detailed;   # use our custom format
        error_log /var/log/nginx/myapp_error.log warn;

        location / {
            proxy_pass http://127.0.0.1:3000;
        }
    }
}
```

```bash
# Watch logs live as requests come in -- essential for real-time debugging
sudo tail -f /var/log/nginx/myapp_access.log

# In Docker, container logs (stdout/stderr) are viewed differently:
docker logs -f my-nginx

# Find the slowest requests in a log file (requires the custom "rt=" field above)
awk -F'rt=' '{print $2, $0}' /var/log/nginx/myapp_access.log | sort -rn | head -10

# Count requests by HTTP status code -- quick health overview
awk '{print $9}' /var/log/nginx/myapp_access.log | sort | uniq -c | sort -rn
```

---

## STEP 10 — Performance Tuning (Advanced)

These are settings you adjust once you actually have real traffic and want to squeeze out more performance.

```nginx
# ---- in the main/top-level context ----
worker_processes auto;          # one worker per CPU core -- almost always the right choice
worker_rlimit_nofile 65535;     # raise the max number of open file descriptors per worker
                                  # (each connection uses a file descriptor -- default OS limits are often too low)

events {
    worker_connections 4096;    # raise max simultaneous connections per worker (default is often only 512-1024)
    use epoll;                  # explicitly use epoll -- Linux's efficient event-notification mechanism
                                  # (nginx usually auto-detects this, but being explicit doesn't hurt)
    multi_accept on;            # let a worker accept multiple new connections in one go, instead of one at a time
}

http {
    # ---- compression: shrink responses before sending them, saving bandwidth and speeding up page loads ----
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 256;        # don't bother compressing tiny responses -- the overhead isn't worth it
    gzip_comp_level 5;          # compression level 1 (fastest, less compression) to 9 (slowest, best compression)

    # ---- connection reuse ----
    keepalive_timeout 65;       # how long to keep idle client connections open for potential reuse
    keepalive_requests 1000;    # max requests allowed per single keep-alive connection before closing it

    # ---- buffer sizes: tune based on your typical request/response sizes ----
    client_max_body_size 10M;   # reject request bodies larger than 10MB (protects against huge uploads/abuse)
    client_body_buffer_size 128k;

    # ---- upstream connection reuse for reverse proxy setups ----
    upstream backend_servers {
        server 127.0.0.1:3001;
        keepalive 32;    # keep up to 32 idle connections OPEN to the backend for reuse,
                          # instead of opening a brand new TCP connection for every single request
    }

    server {
        location / {
            proxy_pass http://backend_servers;
            proxy_http_version 1.1;         # required for keepalive to work with proxied connections
            proxy_set_header Connection ""; # clear the "Connection" header so keepalive isn't accidentally disabled
        }
    }
}
```

**Rule of thumb:** don't tune these blindly. Change one thing, measure the impact (using a load testing tool like `ab`, `wrk`, or `k6`), then decide if it actually helped.

```bash
# A basic load test example using Apache Bench (ab) -- sends 1000 requests, 50 at a time concurrently
ab -n 1000 -c 50 http://myapp.local/
```

---

## STEP 11 — Advanced Docker: A Production-Style Multi-Stage Setup

Let's put everything together: a custom Nginx image (instead of just mounting config into the official one), multiple backend replicas, and a clean project layout.

**What is a "custom image" and why bother?** So far we've taken the official `nginx` image and mounted OUR config files into it at runtime. In production, it's often cleaner to **bake your config directly into a custom image** — this way the image itself is a complete, self-contained, versioned artifact you can deploy anywhere without needing to separately manage config files.

`Dockerfile` for a custom nginx image:

```dockerfile
# Start FROM the official lightweight nginx image based on Alpine Linux (a minimal, small Linux distro)
FROM nginx:alpine

# Remove the default config that ships with the image, since we're replacing it
RUN rm /etc/nginx/conf.d/default.conf

# Copy OUR config file from our project into the image at build time
COPY ./nginx/default.conf /etc/nginx/conf.d/default.conf

# Copy static assets (if serving any directly) into the image
COPY ./public /usr/share/nginx/html

# Document which port this container listens on (informational only -- doesn't actually publish it)
EXPOSE 80

# The default command that runs when the container starts
# "daemon off" keeps nginx running in the FOREGROUND, which Docker requires
# (otherwise nginx would background itself and Docker would think the container exited)
CMD ["nginx", "-g", "daemon off;"]
```

```bash
# Build the custom image from this Dockerfile, tagging it as "my-custom-nginx:1.0"
docker build -t my-custom-nginx:1.0 .

# Run a container from your OWN image instead of the generic official one
docker run -d -p 80:80 --name my-nginx my-custom-nginx:1.0
```

Full production-style `docker-compose.yml` tying it together:

```yaml
services:
  nginx:
    build:
      context: ./nginx           # build using the Dockerfile inside ./nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    depends_on:
      - app
    restart: unless-stopped        # automatically restart this container if it crashes,
                                     # UNLESS it was manually stopped by you

  app:
    build: ./app
    expose:
      - "3000"
    environment:
      - NODE_ENV=production        # environment variables passed into the container
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.5"               # cap this container to half a CPU core
          memory: 256M               # cap it to 256MB of RAM -- prevents one misbehaving container
                                       # from starving the rest of the machine
```

```bash
# Build and start everything
docker compose up -d --build

# Check resource usage live across all running containers
docker stats
```

**Key concept recap for Docker beginners:**
- **Image** = the packaged blueprint (built once, via `docker build` or pulled from a registry).
- **Container** = a running (or stopped) instance of an image.
- **Volume/bind mount** = a way to share files between your real machine and a container, or persist data beyond a container's lifetime.
- **Docker Compose** = a tool for defining and running multiple related containers together as one system, using a YAML file.
- **Network** = Compose automatically creates a private network so your containers can talk to each other by service name.

---

## Quick Reference: The Core Commands Cheat Sheet

```bash
# ---- Native nginx ----
sudo nginx -t                        # test config syntax
sudo systemctl reload nginx          # apply config changes with zero downtime
sudo systemctl restart nginx         # full restart (drops connections)
sudo systemctl status nginx          # check if running
sudo tail -f /var/log/nginx/error.log   # watch errors live

# ---- Docker ----
docker run -d -p 8080:80 --name my-nginx nginx     # quick container run
docker exec -it my-nginx nginx -t                   # test config INSIDE a running container
docker exec -it my-nginx nginx -s reload            # reload config INSIDE a running container
docker logs -f my-nginx                             # follow logs

# ---- Docker Compose ----
docker compose up -d          # start everything in the background
docker compose down           # stop and remove everything
docker compose logs -f        # follow logs from all services
docker compose exec nginx nginx -t     # test config in the nginx service's container
```

---

## Common Beginner Mistakes (Read This Before You Start Troubleshooting Blindly)

1. **Forgetting to run `nginx -t` before reloading.**
   A single typo or missing semicolon can take down your entire server on reload. Always test first — it takes two seconds and will save you a bad afternoon.

2. **Using `restart` instead of `reload` for simple config changes.**
   `restart` briefly kills the server and drops active connections. `reload` swaps in the new config gracefully. Save `restart` for when nginx is genuinely stuck or unresponsive.

3. **Missing the trailing slash in `location` blocks and `proxy_pass`.**
   `location /api { proxy_pass http://backend/; }` behaves *differently* than `location /api/ { proxy_pass http://backend/; }`. The trailing slash on `proxy_pass` tells nginx to strip the matched location prefix before forwarding; without it, the whole original path gets forwarded as-is. This single character causes enormous confusion — test carefully whenever you change it.

4. **Forgetting `proxy_set_header Host $host;` in reverse proxy setups.**
   Without it, your backend app sees requests as if they came from `127.0.0.1` or the internal proxy address, not the real domain the client used — this breaks things like generating correct absolute URLs, cookies scoped to a domain, and CORS logic.

5. **Not understanding `location` block matching priority.**
   Beginners assume location blocks are checked strictly top-to-bottom like a normal list. In reality, exact matches beat regex matches, which beat prefix matches (longest prefix wins), regardless of the order they're written in the file. Re-read Step 4 if a location block "isn't working" — it's very often a priority conflict, not a syntax error.

6. **Editing files directly inside a running Docker container and expecting changes to persist.**
   Any change made directly inside a container (without a volume/bind mount) disappears the moment that container is removed. Always edit config on your host machine and mount it in, or bake it into a custom image via a Dockerfile.

7. **Exposing a backend app's port directly to the internet alongside Nginx.**
   If your app runs on port 3000 and you accidentally also publish `-p 3000:3000` in Docker (or leave a firewall rule open), people can bypass Nginx entirely and hit your app directly — skipping your caching, rate limiting, SSL termination, and logging. Only Nginx's ports (80/443) should generally be exposed to the outside world; backend ports should stay internal (`expose` instead of `ports` in Compose).

8. **Confusing `server_name` with actual DNS.**
   Setting `server_name mysite.com;` in an Nginx config does **not** magically make that domain point to your server. DNS records (managed elsewhere, e.g. your domain registrar or DNS provider) must actually resolve that domain to your server's IP address first. `server_name` only tells Nginx *which* configured site block should handle a request once it already arrives.

9. **Forgetting `client_max_body_size` and being confused by mysterious 413 errors.**
   By default, Nginx rejects request bodies larger than 1MB with a `413 Request Entity Too Large` error. If you're building something with file uploads, you'll hit this immediately and not know why — increase `client_max_body_size` in the relevant `server` or `location` block.

10. **Not checking the error log first.**
    New users often stare at a blank browser error page trying to guess what's wrong. `sudo tail -f /var/log/nginx/error.log` (or `docker logs -f my-nginx`) almost always tells you exactly what broke and why, in plain language — check it before doing anything else.

11. **Certificate permission or path issues after moving/copying servers.**
    SSL certificate private keys have strict file permissions for security reasons. Copying certs between machines carelessly (e.g. via a method that resets permissions) is a common source of "SSL handshake failed" errors that have nothing to do with your actual nginx config.

12. **Running Nginx as root unnecessarily.**
    The official Docker image and most native installs already run Nginx's worker processes as an unprivileged user (`nginx` or `www-data`) by design — only the master process needs elevated privileges to bind to ports below 1024. Don't override this out of impatience; it removes an important security boundary.

---

## Suggested Practice Path

If you want to solidify all of this hands-on, work through these in order:

1. Native install → serve a static HTML page.
2. Same static page, but now inside a Docker container using a volume mount.
3. Build a tiny Node.js or Python "Hello World" app, reverse proxy Nginx to it.
4. Turn that into a Docker Compose setup with two services (nginx + app).
5. Scale the app to 3 replicas and observe load balancing in the logs.
6. Add a second, unrelated app and route between them using two different `server_name` blocks or path-based `location` routing.
7. Get a free domain (or use a service like nip.io for testing) and set up real HTTPS with Certbot.
8. Add caching and compression, then benchmark before/after with `ab`.
9. Bake everything into a custom Nginx Docker image with a Dockerfile.

By the end of that list, you'll have touched every concept in this guide with your own hands — which is the only way any of this really sticks.
