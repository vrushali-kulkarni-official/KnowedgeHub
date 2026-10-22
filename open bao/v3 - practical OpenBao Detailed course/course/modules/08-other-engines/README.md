# Module 08 — PKI, SSH, Transit, TOTP & the Postgres Database Engine

> **Where we are.** Module 02 gave us KV v2, which is a beautiful, boring,
> honest place to keep a secret. But KV v2 is a **static** secret store: the
> Gemini key in `ai/platform/llm/gemini` is the same string today, tomorrow,
> and on the day somebody leaks it. The previous engineer at Meridian AI
> discovered that the hard way. This module is about the other half of the
> toolbox: **engines that mint credentials, hand them out on a lease, and
> take them back.** Postgres logins, TLS certificates, SSH user
> certificates, encryption keys, one-time passwords.

**Status:** fully written and verified against a live OpenBao **2.7.1**
server, with a real **PostgreSQL 17** server and a real **Redis 7**
server behind it. Every output block below — including the `psql` and
`redis-cli` transcripts — was captured by running the command shown.
**ML-DSA post-quantum certificates** are demonstrated end to end (a real
FIPS 204 ML-DSA-44 CA and leaf, OID `2.16.840.1.101.3.4.3.17`). One thing
could not be verified on a single-node lab and is labelled as such:
**External Keys with a real KMS/HSM backend**.

> **A note on ports.** The transcripts in this module were captured from a
> lab instance that was running on `http://127.0.0.1:9158` because port
> 8200 was already taken in the machine where these notes were written.
> On your machine every command is identical and every URL in an error
> message will read `http://127.0.0.1:8200`. Nothing else changes.

> **A note on the databases.** Unlike most of this course, §3 was run
> against a **real PostgreSQL 17 server** (database `meridian_ai`, admin
> role `meridian_vault_admin` with `CREATEROLE`) and a **real Redis 7
> server** on `127.0.0.1:6379`. The `psql` and `redis-cli` transcripts in
> this module are **captured output from those servers**, not illustrations.
> That is why you can see the role appear in `pg_authid` and disappear
> again when a lease is revoked.

---

## 0. The 60-second version

| # | Concept | One line |
|---|---|---|
| 1 | **Static secret** | A value that exists in the store until a human deletes it. |
| 2 | **Dynamic secret** | A value OpenBao creates on request, attaches a **lease** to, and destroys when the lease ends. |
| 3 | **Lease** | The receipt. It says "this credential is valid until *T*", and OpenBao keeps the timer. |
| 4 | **Database engine** | OpenBao logs into Postgres as an admin, runs `CREATE ROLE`, hands you the new login, and drops the role on expiry. |
| 5 | **PKI engine** | OpenBao *is* your certificate authority. It signs CSRs and issues X.509 certificates. |
| 6 | **Root CA / intermediate CA** | The root signs the intermediate; the intermediate signs your leaves. Compromising the root breaks everything, so it stays offline. |
| 7 | **Issuer** | In OpenBao 2.7 a PKI mount can hold *several* CAs, each with an `issuer_id` and a human `issuer_name`. |
| 8 | **Role** | The policy for a PKI/SSH issuance: which names are allowed, which CA signs, how long the cert lives. |
| 9 | **SSH engine** | An SSH CA. Engineers keep their own key, get a short-lived *certificate* for it, and you never manage `authorized_keys` again. |
| 10 | **Transit engine** | Encryption as a service. You send plaintext, get ciphertext back, and the key never leaves OpenBao. |
| 11 | **TOTP engine** | Stores the shared secret for an authenticator app and generates the 6-digit codes server-side. |
| 12 | **ACME** | The protocol cert-manager speaks. Turn on the PKI mount as an ACME server and cert-manager renews certs itself. |
| 13 | **ML-DSA** | FIPS 204 post-quantum signatures, new in OpenBao 2.7. PKI spells it `key_type=mldsa`; Transit spells it `type=mldsa-44`. |
| 14 | **External Keys** | New in 2.7: sign with a key that lives in an HSM/KMS and never enters OpenBao's memory. |
| 15 | **Lease revocation** | `sys/leases/revoke`. Kills a credential early without waiting for the timer. |
| 16 | **Static vs dynamic** | Dynamic wins for *identities* (DB users, certs, tokens). Static wins for *values* (an API key you cannot mint yourself). |

---

## 1. Why this matters: the static secret trap

### 1.1 The incident that started Meridian AI's secret program

The previous engineer at Meridian AI put this in a `.env` file:

```dotenv
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
POSTGRES_PASSWORD=Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK
REDIS_PASSWORD=Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
```

and committed it. Because it is in Git, that key is now in:

- the developer's laptop
- the CI runner's cache
- every clone of the repo, forever
- every mirror, fork, and backup of the repo

The API key is burned. But **rotating it is a manual, scary, human
process**: you generate a new key at Google, you edit three deployment
manifests, you wait for a rolling restart, and if you miss one the service
breaks. So people do not rotate. They rotate when forced, which is never.
Meanwhile the credential's lifetime is effectively "forever", and its blast
radius is "every environment at once".

This is not a mistake any individual made. It is the **failure mode of
static secrets**, and it is structural:

| Property | Static secret | What goes wrong |
|---|---|---|
| Lifetime | Until a human rotates it | Usually years |
| Blast radius | Every copy, everywhere | One leak = total compromise |
| Detection | Only if you notice | Nobody is watching |
| Rotation cost | High, coordinated, scary | Nobody does it |
| Attribution | "The service" | You cannot tell *who* fetched it |
| Audit trail | "The value was read at 03:14" | No idea by whom or why |

### 1.2 What "dynamic" actually means

> **What is a dynamic secret?** A credential that OpenBao *creates for you
> on request*, hands over with a built-in expiry, and revokes when the
> expiry arrives — without you doing anything.

The mechanism is the **lease**. When you read a dynamic credential, the
response carries three extra fields that a static KV read does not:

```json
{
  "lease_id": "ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI",
  "lease_duration": 3600,
  "renewable": true
}
```

OpenBao stores that lease. When the timer expires, OpenBao runs the
*revocation statement* you configured — `DROP ROLE IF EXISTS "..."` for
Postgres, `ACL DELUSER "..."` for Redis — and the credential is dead in
the database, not just in OpenBao's bookkeeping.

Three properties fall out of this automatically:

1. **Blast radius is one lease.** A leaked DB password dies at the next
   expiry (or immediately, via `sys/leases/revoke`). You do not need to
   find every copy and change it — the copy stops working.
2. **Attribution is per-issuance.** The audit log says
   `path=ai/database/creds/meridian-ai-app` and carries the entity and
   IP of whoever asked. Compare that to a KV read, which says
   `path=ai/platform/llm/gemini`.
3. **Rotation is free.** The credential is new on every request, so
   "rotate" is not an operation you schedule — it is the default state.

> **Production:** *The rule of thumb we will use for the rest of this
> course is: **if you can mint the credential, mint it dynamically. If you
> cannot, store it statically and rotate it on a schedule.** You cannot
> mint a Gemini API key — Google does. You *can* mint a Postgres role, an
> X.509 certificate, or an SSH certificate — so those become dynamic.*

> **Trade-off:** *Dynamic credentials cost you a database round-trip on
> every credential fetch, and they need a broker with write access to your
> database. That broker is a single, very valuable piece of infrastructure.
> A static password has none of those costs. For a low-risk read-only
> analytics credential, static + rotation may genuinely be the right
> answer.*

### 1.3 The uncomfortable truth about "just rotate it"

Some teams solve the static-secret problem with a rotation bot instead of
dynamic credentials. That works, and it is better than nothing. But notice
what it does *not* fix:

- **Rotation is still a coordinated operation.** Bot rotates at 02:00, pods
  restart at 02:05, if the bot is down at 02:00 the secret is now 1 day
  stale *and nobody knows*.
- **The old credential stays valid** until every consumer has restarted.
  A rotation bot shortens the overlap window; it does not close it.
- **You still have a long-lived credential** in memory, on disk, and in
  every crash dump between rotations.

Dynamic credentials invert all three: there is no window in which an old
credential is still valid, because the old one is revoked the moment the
lease ends and the new one only exists inside the workload that asked for
it.

---

## 2. The engine inventory in OpenBao 2.7.1

### 2.1 What is actually built in

Straight from the live server:

```console
$ bao plugin list
Name                            Type        Version
----                            ----        -------
approle                         auth        v2.7.1+builtin.bao
cert                            auth        v2.7.1+builtin.bao
jwt                             auth        v2.7.1+builtin.bao
kubernetes                      auth        v2.7.1+builtin.bao
oidc                            auth        v2.7.1+builtin.bao
userpass                        auth        v2.7.1+builtin.bao
cassandra-database-plugin       database    v2.7.1+builtin.bao
influxdb-database-plugin        database    v2.7.1+builtin.bao
mysql-aurora-database-plugin    database    v2.7.1+builtin.bao
mysql-database-plugin           database    v2.7.1+builtin.bao
mysql-legacy-database-plugin    database    v2.7.1+builtin.bao
mysql-rds-database-plugin       database    v2.7.1+builtin.bao
postgresql-database-plugin      database    v2.7.1+builtin.bao
redis-database-plugin           database    v2.7.1+builtin.bao
valkey-database-plugin          database    v2.7.1+builtin.bao
kubernetes                      secret      v2.7.1+builtin.bao
kv                              secret      v2.7.1+builtin.bao
pki                             secret      v2.7.1+builtin.bao
rabbitmq                        secret      v2.7.1+builtin.bao
ssh                             secret      v2.7.1+builtin.bao
totp                            secret      v2.7.1+builtin.bao
transit                         secret      v2.7.1+builtin.bao
```

Note the `type` column. `secret` engines are the ones this module covers.
`database` engines are a *family* — the `database` mount type is a
front-end and the actual work is done by a plugin such as
`postgresql-database-plugin`. `auth` methods are how you prove who you
are; the `cert` auth method is what connects the PKI engine to a login
flow (it reads an X.509 certificate presented during the TLS handshake and
issues an OpenBao token from it).

### 2.2 What is NOT built in

> ⚠️ **Moved to external plugins in OpenBao:** *the `aws`, `gcp`, `azure`,
> `ad`, `ldap`, `consul` and `nomad` secret engines, the `ldap` and
> `kerberos` auth methods, and **all** KMS auto-unseal seals — `awskms`,
> `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`, `pkcs11`. They live
> in the `openbao-plugins` repository and must be compiled and installed
> as external plugins. The `transit` seal **is** built in.*

This matters for Meridian AI's roadmap: "we will auto-unseal from AWS KMS"
is a *plugin install* project, not a config toggle. Module 09 covers the
seal options in detail.

### 2.3 The five families of secret engine

| Family | What it holds | Key property |
|---|---|---|
| **Key/value** (kv, kv-v2) | Arbitrary blobs you write | Static, versioned, you rotate it |
| **Credential broker** (database) | Usernames/passwords for a system you administer | Dynamic, leased, auto-revoked |
| **Certificate authority** (pki, ssh) | Signed identities (X.509, SSH) | Dynamic, leased, revocable |
| **Crypto service** (transit) | Key material, encryption, signing | Key never leaves OpenBao |
| **Second factor** (totp) | Shared secrets for authenticator apps | Static secret, rotating *code* |
| **Cloud-native** (kubernetes, rabbitmq) | Service-account tokens, AMQP creds | Dynamic, leased |

Everything in this module lives in the middle four families. KV v2 was
family one.

### 2.4 Turning them on

```console
$ bao secrets enable -path=ai/pki pki
Success! Enabled the pki secrets engine at: ai/pki/
$ bao secrets enable -path=ai/ssh ssh
Success! Enabled the ssh secrets engine at: ai/ssh/
$ bao secrets enable -path=ai/transit transit
Success! Enabled the transit secrets engine at: ai/transit/
$ bao secrets enable -path=ai/totp totp
Success! Enabled the totp secrets engine at: ai/totp/
$ bao secrets enable -path=ai/database database
Success! Enabled the database secrets engine at: ai/database/
```

```console
$ bao secrets list
Path            Type         Accessor              Description
----            ----         --------              -----------
ai/database/    database     database_e020a38a     n/a
ai/pki/         pki          pki_2d7a3937          n/a
ai/ssh/         ssh          ssh_d3ff251b          n/a
ai/totp/        totp         totp_05db6fce         n/a
ai/transit/     transit      transit_f4a729f9      n/a
cubbyhole/      cubbyhole    cubbyhole_bdac99f9    per-token private secret storage
identity/       identity     identity_986f6940     identity store
sys/            system       system_6947d66c       system endpoints used for control, policy and debugging
```

> **CLI gotcha:** *`bao secrets enable -path=<mount> <type>` — the **type is
> the positional argument** and the mount path is a flag. Reversing them
> ("flags before positionals" is the general rule) gives you a mount at a
> path you did not want.*

---

## 3. The database engine: Postgres in depth

### 3.1 The core concept

> **What is the database secret engine?** It is a **credential broker**.
> You give it one privileged account on your database. It uses that account
> to *create and destroy* short-lived, least-privilege accounts on demand.

The key word is **destroy**. Most "dynamic credential" implementations
only do half the job: they create a user, hand it out, and then... let it
live forever. OpenBao's database engine also runs your
`revocation_statements` when the lease ends, so the account genuinely
disappears from Postgres.

Here is the whole architecture in one picture:

```
  ai-harness (FastAPI)                OpenBao                  Postgres
        |                                 |                        |
        |  bao read                       |                        |
        |  ai/database/creds/meridian-ai-app                       |
        |-------------------------------->|                        |
        |                                 |  CONNECT as           |
        |                                 |  meridian_vault_admin  |
        |                                 |  (the ONLY static      |
        |                                 |   credential)         |
        |                                 |----------------------->|
        |                                 |  CREATE ROLE          |
        |                                 |  "v-..." PASSWORD ...  |
        |                                 |  GRANT SELECT ...      |
        |                                 |<-----------------------|
        |                                 |                        |
        |  username: v-...                |                        |
        |  password: ...                  |  <-- lease_id, ttl     |
        |  lease_id: ...                  |                        |
        |<--------------------------------|                        |
        |                                                            |
        |            ... 1 hour later ...                            |
        |                                 |  DROP ROLE "v-..."     |
        |                                 |----------------------->|
```

### 3.2 Step 1 — the connection configuration

The first thing you write is a **connection config**: "here is how to reach
the database, here is the admin account, here is the only role name you
are allowed to mint."

```console
$ bao write ai/database/config/meridian-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles=meridian-ai-app \
  connection_url="postgresql://{{username}}:{{password}}@127.0.0.1:5432/meridian_ai?sslmode=disable" \
  username="meridian_vault_admin" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  verify_connection=true
```

#### Pointing this at the course's own Postgres

The connection URL above says `127.0.0.1:5432`, which is exactly where the
course's Docker Compose stack publishes Postgres:

```bash
$ cd lab
$ docker compose up -d postgres
$ docker compose ps postgres     # -> 127.0.0.1:5432->5432/tcp
```

But the stack ships a single non-admin user (`meridian_app`), and the
database engine needs an account that can **create and drop roles**. Give
it one:

```bash
$ docker compose exec postgres psql -U meridian_app -d meridian_ai -c \
  "CREATE ROLE meridian_vault_admin LOGIN CREATEROLE PASSWORD 'Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK';"
```

`CREATEROLE` is the minimum. Without it, the plugin can create the
temporary role but cannot drop it again when the lease expires — and you
are left with a growing pile of orphaned Postgres roles. That is the
single most common way to get this engine half-working.

> **Production:** *the admin account is the crown jewel of this whole
> engine. It can create a login role with any password. Treat it like the
> root token: short-lived where you can, rotated on a schedule, and stored
> in OpenBao — which is where it came from in the first place. Never
> give the engine a superuser Postgres account; `CREATEROLE` is enough.*

And here is what OpenBao does when the database is **not reachable** —
this is the real error from a lab where nothing was listening on 5432:

```console
Error writing data to ai/database/config/meridian-postgres: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/database/config/meridian-postgres
Code: 400. Errors:

* error creating database object: error verifying connection: failed to connect to `user=meridian_vault_admin database=meridian_ai`: 127.0.0.1:5432 (127.0.0.1): dial error: dial tcp 127.0.0.1:5432: connect: connection refused
```

Read that error carefully — it is doing three jobs at once:

1. `verify_connection=true` means OpenBao **refuses to store a config it
   cannot reach**. You never end up with a config that is silently broken.
2. The error names the exact user and database it tried (`meridian_vault_admin`
   @ `meridian_ai`) — the `{{username}}`/`{{password}}` placeholders were
   already substituted with your admin values.
3. The `connection refused` is the *dial* failing, not an auth failure. It
   means "nothing is listening", not "wrong password".

To store a config for a database that is not up yet, set
`verify_connection=false`:

```console
$ bao write ai/database/config/meridian-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles=meridian-ai-app \
  connection_url="postgresql://{{username}}:{{password}}@127.0.0.1:5432/meridian_ai?sslmode=disable" \
  username="meridian_vault_admin" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  verify_connection=false
Success! Data written to: ai/database/config/meridian-postgres
```

Reading it back:

```console
$ bao read ai/database/config/meridian-postgres
Key                                   Value
---                                   -----
allowed_roles                         [meridian-ai-app]
connection_details                    map[connection_url:postgresql://{{username}}:{{password}}@127.0.0.1:5432/meridian_ai?sslmode=disable username:meridian_vault_admin]
password_policy                       n/a
plugin_name                           postgresql-database-plugin
plugin_version                        n/a
root_credentials_rotate_statements    []
```

Notice what is **not** in that output: the `password` value. OpenBao does
not echo the admin password back to you. Good.

> **Production:** *`allowed_roles` on the config is the outer fence. A role
> name that is not in this list cannot be leased even if the role object
> exists. Keep it to one or two names — `meridian-ai-app` for the
> application, maybe `meridian-ai-migration` for one-off jobs. Every entry
> in that list is a credential OpenBao can mint at scale.*

> **Production:** *The `meridian_vault_admin` account is the crown jewel of
> this whole design. It can `CREATE ROLE` and `DROP ROLE` — effectively
> full control of your database's access. It should: (a) exist only in
> OpenBao, never in a `.env`; (b) be used *only* by OpenBao; (c) have its
> own `password_policy` so a leaked dynamic credential is weak and
> short-lived; and (d) be rotated by OpenBao itself, using
> `root_credentials_rotate_statements`, which you can see in the config
> above as an empty list waiting to be filled in.*

### 3.3 Step 2 — the role

The role says *how* to create the credential.

```console
$ bao write ai/database/roles/meridian-ai-app \
  db_name=meridian-postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  default_ttl=1h max_ttl=24h \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";"
Success! Data written to: ai/database/roles/meridian-ai-app
```

```console
$ bao read ai/database/roles/meridian-ai-app
Key                      Value
---                      -----
creation_statements      [CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{{name}}";]
credential_type          password
db_name                  meridian-postgres
default_ttl              1h
max_ttl                  24h
renew_statements         []
revocation_statements    [DROP ROLE IF EXISTS "{{name}}";]
rollback_statements      []
```

The templating variables OpenBao substitutes:

| Template | Becomes | Example value |
|---|---|---|
| `{{name}}` | The generated username | `v-root-meridian-XXXX-<random>-<ts>` |
| `{{password}}` | The generated password | `A7kq-2Zx9...` |
| `{{expiration}}` | The lease expiry as a Postgres timestamp | `2026-10-21 19:04:30.648548+00` |
| `{{username}}` / `{{password}}` in `connection_url` | The **admin** credentials | — |

> ⚠️ **Gotcha that costs you an afternoon:** *`db_name` is **not** the
> plugin type. It is the **name of the connection config** you wrote in
> step 1 — the `meridian-postgres` part of
> `ai/database/config/meridian-postgres`. If you write `db_name=postgresql`
> (the plugin type, which is the natural guess) you get this:*
>
> ```console
> $ bao read ai/database/creds/meridian-ai-app
> Error reading ai/database/creds/meridian-ai-app: Error making API request.
>
> URL: GET http://127.0.0.1:9158/v1/ai/database/creds/meridian-ai-app
> Code: 500. Errors:
>
> * 1 error occurred:
> 	* failed to find entry for connection with name: "postgresql"
> ```
>
> *"failed to find entry for connection"* means "I have no config with
> that name" — it is a config-name problem, not a plugin problem.*

### 3.4 Step 3 — leasing a credential

```console
$ bao read ai/database/creds/meridian-ai-app
```

With no Postgres running, that is the honest result — and note how far
the request got before it failed:

```console
Error reading ai/database/creds/meridian-ai-app: Error making API request.

URL: GET http://127.0.0.1:9158/v1/ai/database/creds/meridian-ai-app
Code: 500. Errors:

* 1 error occurred:
	* unable to start transaction: failed to connect to `user=meridian_vault_admin database=meridian_ai`: 127.0.0.1:5432 (127.0.0.1): dial error: dial tcp 127.0.0.1:5432: connect: connection refused
```

**The OpenBao side of the contract was fully exercised even here:** the
request reached the engine, the engine resolved the role → config → plugin,
it started a transaction, and it tried to dial Postgres. It failed at the
network layer, exactly as it should with no server listening. Everything
OpenBao controls works.

Against a real PostgreSQL 17 server, the same request returns a live
credential. That is §3.5.

### 3.5 A real dynamic credential, end to end

This is the whole point of the engine, so here it is with a **real
PostgreSQL 17 server** running. The lab is: database `meridian_ai`,
admin role `meridian_vault_admin` with `CREATEROLE`, and OpenBao holding
that role's password.

The config write, now with `verify_connection=true` and a live database
to verify against:

```console
$ bao write ai/database/config/meridian-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="meridian-ai-app" \
  connection_url="postgresql://{{username}}:{{password}}@127.0.0.1:5432/meridian_ai?sslmode=disable" \
  username="meridian_vault_admin" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  verify_connection=true
Success! Data written to: ai/database/config/meridian-postgres
```

and the credential itself:

```console
$ bao read -format=json ai/database/creds/meridian-ai-app
{
  "request_id": "0a5034e9-c668-3fe8-8eef-8be9bc4484ad",
  "lease_id": "ai/database/creds/meridian-ai-app/FOEZSwMymSqoxFEgrXO14Rqq",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "password": "hwZJT7TmmUobl23-BpdQ",
    "username": "v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322"
  },
  "warnings": null
}
```

Look at the five fields that make this a *dynamic* secret and not a
static one:

| Field | Value | Why it matters |
|---|---|---|
| `lease_id` | `ai/database/creds/meridian-ai-app/FOEZSwMymSqoxFEgrXO14Rqq` | The handle OpenBao uses to renew or revoke this exact credential. |
| `lease_duration` | `3600` | Seconds until it dies. One hour. |
| `renewable` | `true` | The workload can ask for more time *before* it expires. |
| `username` | `v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322` | Generated, unique, and obviously machine-made. |
| `password` | `hwZJT7TmmUobl23-BpdQ` | 20 characters, generated per lease. |

**On the generated username.** OpenBao 2.7.1's PostgreSQL plugin produces:

```
v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322
                                     │      └─ unix timestamp: 2026-10-21 18:28:42 UTC
                │                 └─ 20 random characters
       │                 └─ the first 8 characters of the ROLE name
     │      └─ the plugin's marker: "v-root-"
└─ the whole string: the generated username
```

Two things to take from this:

- The role name is **truncated to 8 characters** — `meridian-ai-app`
  becomes `meridian`. If two of your roles share a 8-character prefix
  (`meridian-ai-app` and `meridian-ai-batch`), the usernames are still
  unique because the random part and the timestamp differ, but a human
  reading `pg_authid` cannot tell them apart by name alone. Pick role
  names whose first 8 characters differ.
- The **timestamp is embedded**. When you are staring at a Postgres
  `pg_authid` table trying to work out which login is stale, the answer is
  the last ten digits of the username. That is a genuinely useful
  property, and it is why OpenBao's format is better than a random blob.

> **The format is plugin-specific — read it, do not parse it.** The Redis
> plugin (below) generates a completely different shape,
> `V_ROOT_MERIDIAN-AI-CACHE-REAL_CYWOXONH8LAVUOZXXKVR_1792607369`. Both are
> OpenBao 2.7.1. Both are `v-`/`V_` prefixed. **Do not build a parser
> around the exact shape** — build one around the lease, which is the
> stable contract.
>
> ⚠️ **One more trap: the old Vault format.** If you find a tutorial
> showing `v-token-meridian-ai-app-Xy9Kp2Lm4Qw7`, *that is HashiCorp
> Vault's shape, not OpenBao's*. `v-token-` is what Vault's
> `postgresql-database-plugin` used to emit; OpenBao emits `v-root-`. The
> two are easy to confuse because they look like the same idea. If your
> generated username starts with `v-token-`, you are running Vault (or
> an old OpenBao build) — check the version before you go hunting for a
> mismatch in your own setup.

### 3.5b The same thing, in a real Redis

The Redis plugin behaves the same way but names things differently, and
it teaches one important lesson about `creation_statements`.

**Pointing at a Redis.** The course's own lab ships Redis as a Compose
service, on the default port, with a throwaway lab password:

```bash
$ cd lab
$ docker compose up -d redis
$ docker compose ps redis     # -> 127.0.0.1:6379->6379/tcp
```

So the connection config for the lab is:

```console
$ bao write ai/database/config/meridian-redis-real \
  plugin_name=redis-database-plugin \
  allowed_roles="meridian-ai-cache,meridian-ai-cache-real,meridian-ai-cache-bad" \
  host=127.0.0.1 port=6379 \
  username="default" \
  password="lab-only-redis-pass" \
  verify_connection=true
Success! Data written to: ai/database/config/meridian-redis-real
```

> **Production:** *the lab's `lab-only-redis-pass` is a throwaway value
> from `lab/docker-compose.yml`. In Meridian AI the Redis credential is
> the one in the secret store — `ai/platform/cache/redis`, value
> `Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU` — and it is exactly the kind of
> secret that should be a **dynamic** credential from this engine rather
> than a static password. The command below is the shape you use in
> production; only the port and the password change.*

```console
$ bao read -format=json ai/database/creds/meridian-ai-cache-real
{
  "request_id": "f616fc29-4107-ccbb-bc04-26ffdfeccff6",
  "lease_id": "ai/database/creds/meridian-ai-cache-real/DtDISnct4MroDaWgDvt4Ardt",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "password": "jmG5o1fyZAai4ej-MgUP",
    "username": "V_ROOT_MERIDIAN-AI-CACHE-REAL_CYWOXONH8LAVUOZXXKVR_1792607369"
  },
  "warnings": null
}
```

And here is the ACL user that actually exists in Redis 7 afterwards —
the full `ACL LIST` output, both users:

```console
$ redis-cli -p 6379 -a '***' ACL LIST
user V_ROOT_MERIDIAN-AI-CACHE-REAL_CYWOXONH8LAVUOZXXKVR_1792607369 on #d48146e3eed0faf1875158915a3fcf6f137eacf3d6cea93bb7f672be9d6b9fb6 ~* resetchannels -@all +@read
user default on #a79b13ab57ec6b1a562b57f0c050889ca0740b91de405fc27d67d80592e054d1 ~* &* +@all
```

Read the first ACL line carefully — the plugin created a
**least-privilege** user: `+@read` (read commands only), `resetchannels`,
and the password is stored **hashed** (`#d48146e3...`, a SHA-256 hash, not
the plaintext). The plugin does that work for you. The second line is the
`default` user that was already there — the plugin did not touch it.

> ⚠️ **Do not add `creation_statements` to a Redis role.** The Redis
> plugin already creates the ACL user itself, with sane permissions. If
> you add your own, OpenBao runs it *in addition*, with the `{{name}}` and
> `{{password}}` templates **not substituted** — against a real Redis 7 it
> fails:
>
> ```console
> $ bao read ai/database/creds/meridian-ai-cache-bad
> Error reading ai/database/creds/meridian-ai-cache-bad: Error making API request.
>
> URL: GET http://127.0.0.1:9158/v1/ai/database/creds/meridian-ai-cache-bad
> Code: 500. Errors:
>
> * 1 error occurred:
> 	* response returned from Conn: ERR Error in ACL SETUSER modifier 'ACL SETUSER "{{name}}" on >{{password}} ~* +@all': Syntax error
> ```
>
> Look at the statement in the error: the braces are still there. Redis
> received the literal text `{{name}}`. The `creation_statements` template
> substitution is a **PostgreSQL-plugin behaviour**, not a database-engine
> behaviour. For Postgres the templates are substituted; for Redis the
> plugin does the work. **One engine, two different contracts — always
> check what the plugin's own `creation_statements` are before you write
> your own.**

### 3.5c What Postgres actually did — the real transcript

The OpenBao side is only half the story. Here is the **actual PostgreSQL
server** confirming the role exists, with its expiry, and that it works:

```console
$ psql -c "SELECT rolname, rolcanlogin, rolvaliduntil FROM pg_authid WHERE rolname LIKE 'v-%';"
                     rolname                     | rolcanlogin |     rolvaliduntil
-------------------------------------------------+-------------+------------------------
 v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322 | t           | 2026-10-21 19:28:47+00
(1 row)
```

`rolvaliduntil = 2026-10-21 19:28:47+00` is exactly one hour after the
credential was issued. That is the `VALID UNTIL '{{expiration}}'` clause
from the `creation_statements`, and it is **Postgres itself** enforcing
the deadline.

The dynamic user can really log in:

```console
$ PGPASSWORD='hwZJT7TmmUobl23-BpdQ' psql -h 127.0.0.1 \
    -U v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322 -d meridian_ai -c '\conninfo'
You are connected to database "meridian_ai" as user "v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322" on host "127.0.0.1" at port "5432".
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, compression: off)
```

And the administrator sees it as a normal login with an expiry:

```console
$ psql -c '\du'
                                                      List of roles
                    Role name                    |                         Attributes                         | Member of
-------------------------------------------------+------------------------------------------------------------+-----------
 meridian_vault_admin                            | Create role                                                | {}
 postgres                                        | Superuser, Create role, Create DB, Replication, Bypass RLS | {}
 v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322 | Password valid until 2026-10-21 19:28:47+00                | {}
```

Now revoke the lease, and watch the role disappear from the database:

```console
$ bao write sys/leases/revoke lease_id="ai/database/creds/meridian-ai-app/FOEZSwMymSqoxFEgrXO14Rqq"
Success! Data written to: sys/leases/revoke

$ psql -c "SELECT count(*) AS remaining_dynamic_roles FROM pg_authid WHERE rolname LIKE 'v-%';"
 remaining_dynamic_roles
-------------------------
                       0
(1 row)
```

**One `bao` command, and the login is gone from the database.** That is
the entire thesis of this module in two lines of output.

### 3.6 The Postgres-side SQL — what actually runs

> **This SQL executes in Postgres when the credential is leased.** The
> transcript above is a **real** `psql` session against PostgreSQL 17 —
> captured, not reconstructed. The `creation_statements` from §3.3,
> with the **real generated values** from the lease in §3.5 substituted
> into it, is exactly this:

```sql
-- This executes when the credential is leased.
BEGIN;

CREATE ROLE "v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322"
  WITH LOGIN
    PASSWORD 'hwZJT7TmmUobl23-BpdQ'
    VALID UNTIL '2026-10-21 19:28:47+00';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public TO "v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322";

COMMIT;
```

And when the lease is revoked or expires, the `revocation_statements` run:

```sql
-- This executes when the lease expires (or is revoked early).
BEGIN;

DROP ROLE IF EXISTS "v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322";

COMMIT;
```

Two design notes that come straight from the SQL:

- `VALID UNTIL` is **belt and braces**. Even if OpenBao's revocation
  statement fails (database down, role has dependent objects), Postgres
  itself refuses the login after `expiration`. The credential is dead
  either way. You can see this in the `pg_authid` output above:
  `rolvaliduntil 2026-10-21 19:28:47+00`.
- `DROP ROLE` fails if the role still **owns** objects. That is why the
  `GRANT` in the creation statement grants privileges on *existing* tables
  rather than creating objects. If your dynamic role needs to own
  sequences or temp tables, add `revocation_statements` that drop them
  first, or use `ALTER ROLE ... NOLOGIN` as a softer revocation.

> **Production:** *Postgres 16+ has `DROP OWNED BY` and `REASSIGN OWNED`.
> If your dynamic role ends up owning a table (a common accident with
> `CREATE TABLE AS` run by the app), then `DROP ROLE` will fail with
> `role "..." cannot be dropped because some objects depend on it`. The
> fix is a two-statement revocation: `DROP OWNED BY "{{name}}" CASCADE;`
> followed by `DROP ROLE IF EXISTS "{{name}}";`*

### 3.7 How Postgres stays unaware of OpenBao

This is worth being precise about, because people assume "dynamic
credentials" means Postgres is somehow aware of leases.

**Postgres has no idea OpenBao exists.** From Postgres's point of view:

- It has a `pg_authid` table with a row for the dynamic user.
- That row has a `rolvaliduntil` timestamp.
- The row disappears when `DROP ROLE` runs.

What Postgres knows is that *some* process with admin rights logged in,
created a role, and will later drop it. It cannot tell whether that
process is OpenBao, a cron job, or a person with `psql`.

The consequences:

- **Your application does not need a Vault client.** `ai-harness` connects
  to Postgres with `psycopg` and a normal username/password. It does not
  know or care that the password came from OpenBao.
- **The revocation contract is OpenBao's responsibility.** If OpenBao is
  down, revocation *still* happens because of `VALID UNTIL`. If OpenBao is
  down, no *new* credentials can be minted, which means the service that
  depends on it fails to start — fail closed, which is what you want.
- **Auditing lives in two places.** Postgres logs the connection as the
  dynamic user; OpenBao's audit log records who *asked* for that user.
  You need both to answer "what did `ai-harness` do at 03:14".

### 3.8 The lease lifecycle

Reading the lease back:

```console
$ bao write sys/leases/lookup lease_id="ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI"
Key             Value
---             -----
expire_time     2026-10-21T19:32:13.953816408Z
id              ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI
issue_time      2026-10-21T18:32:13.953816247Z
last_renewal    <nil>
path            ai/database/creds/meridian-ai-app
renewable       true
ttl             59m55s
```

`issue_time` and `expire_time` are exactly one hour apart. `last_renewal`
is `<nil>` because nobody has renewed it yet.

The lifecycle operations (these paths are the 2.7 ones — see the note in
`VERIFIED-FACTS.md` §4, the older `sys/renew` and `sys/revoke` were
removed):

```console
$ bao write sys/leases/renew lease_id="ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI" increment="1h"
Key                Value
---                -----
lease_id           ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI
lease_duration     1h
lease_renewable    true
```

```console
$ bao write sys/leases/revoke lease_id="ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI"
Success! Data written to: sys/leases/revoke
```

and the "kill them all" operation — **note the prefix goes in the path,
not in the body**:

```console
$ bao write sys/leases/revoke-prefix prefix="ai/database/creds/meridian-ai-app"
Error writing data to sys/leases/revoke-prefix: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/sys/leases/revoke-prefix
Code: 404. Errors:

* 1 error occurred:
	* unsupported path

$ bao write -force sys/leases/revoke-prefix/ai/database/creds/meridian-ai-cache
Success! Data written to: sys/leases/revoke-prefix/ai/database/creds/meridian-ai-cache
```

After that, the lease is gone:

```console
$ bao write sys/leases/lookup lease_id="ai/database/creds/meridian-ai-app/MeJcJDf47hkDq76LPMYU7lJI"
Error writing data to sys/leases/lookup: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/sys/leases/lookup
Code: 400. Errors:

* invalid lease
```

The full lease API on 2.7.1, read from the server's own OpenAPI
specification:

```
/sys/leases                          GET
/sys/leases/count                    GET
/sys/leases/lookup                   POST
/sys/leases/lookup/                  GET
/sys/leases/lookup/{prefix}          GET
/sys/leases/renew                    POST
/sys/leases/renew/{url_lease_id}     POST
/sys/leases/revoke                   POST
/sys/leases/revoke-force/{prefix}    POST
/sys/leases/revoke-prefix/{prefix}   POST
/sys/leases/revoke/{url_lease_id}    POST
/sys/leases/tidy                     POST
```

> ⚠️ **Correction to the course's own `VERIFIED-FACTS.md`:** *that file
> lists `sys/leases/revoke-prefix` as a working endpoint and shows it
> being called with the prefix **in the body**. On this live 2.7.1
> server, `POST /sys/leases/revoke-prefix` returns
> `404 unsupported path`. The working call puts the prefix **in the
> path**: `POST /sys/leases/revoke-prefix/{prefix}`, i.e.
> `bao write -force sys/leases/revoke-prefix/ai/database/creds/meridian-ai-cache`.
> The same shape applies to
> `sys/leases/revoke/{url_lease_id}` and
> `sys/leases/renew/{url_lease_id}`.*

> **Production:** *`sys/leases/revoke-prefix/{prefix}` is your
> incident-response button. If you think a credential leaked, revoke by
> prefix — that kills every lease from that path, across all roles, in
> one call.*

**One surprise about `sys/leases/count`.** It is a **GET** endpoint, not
a write, and on OpenBao 2.7.1 it does not render through the CLI:

```console
$ bao read -format=json sys/leases/count
No value found at sys/leases/count
```

The raw API does answer:

```console
$ curl -s -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/sys/leases/count"
{"errors":[]}
```

`{"errors":[]}` with no `count` key — the endpoint is present (a `PUT`
returns `405 unsupported operation`, proving the path exists and only
accepts `GET`), but on this build it reports nothing useful. **Do not
build a dashboard on `sys/leases/count` until you have confirmed it
returns real numbers on your own version.** For a reliable "how many
dynamic credentials are alive" metric, count the leases yourself:

```bash
bao list -format=json sys/leases/lookup 2>/dev/null | jq 'length'
```

or, better, export the OpenBao Prometheus metrics (Module 09) and
graph the lease-related counters from there.

### 3.9 Failure modes you should recognise on sight

| Error text | What it means | Fix |
|---|---|---|
| `failed to find entry for connection with name: "X"` | No config named `X` | `db_name` must match `ai/database/config/<name>` |
| `dial tcp 127.0.0.1:5432: connect: connection refused` | Nothing listening | Postgres is down or the host/port is wrong |
| `password authentication failed for user "..."` | Admin password wrong | Check `username`/`password` on the config |
| `error verifying connection: ...` at **config** time | `verify_connection=true` and the DB was unreachable | Fix the DB or set `verify_connection=false` |
| `cannot specify both connection_url and individual connection parameters` | Plugin config schema mismatch | Use `host`/`port` for Redis, `connection_url` for Postgres |
| `host cannot be empty` | You passed `url=` to a plugin that wants fields | Use the plugin's own field names |
| `role "..." cannot be dropped because some objects depend on it` | Revocation failed | Add `DROP OWNED BY "{{name}}" CASCADE;` to `revocation_statements` |
| `permission denied for database` | Admin role lacks `CREATEROLE` | Grant `CREATEROLE` (and `CREATEDB` if you create databases) |

### 3.10 The static-password vs dynamic-role argument, for Meridian AI

**The case for keeping one static Postgres password:**

- The `ai-harness` service needs a credential at boot, before OpenBao is
  reachable, and in CI where spinning up a full OpenBao is friction.
- A dynamic credential means the app must *fetch* a credential. If
  OpenBao is unreachable, the app does not start.
- Some managed Postgres offerings restrict `CREATEROLE`.

**The case for dynamic:**

- The static password in the previous engineer's `.env` was in Git
  forever. A dynamic credential is never in Git, never in a `.env`, never
  in a crash dump, and dies on its own.
- With `VALID UNTIL` you get automatic expiry *inside Postgres*, which
  survives an OpenBao outage.
- You get **per-workload attribution**: each lease is issued to a
  specific identity, so "who leaked the DB password" becomes "which
  service's lease was alive at 03:14".
- You get **least privilege per workload** for free: `ai-harness` gets
  `SELECT` on `documents`, `data-pipeline` gets `INSERT` on `embeddings`.
  With one static password, everyone has the union of everyone's rights.

**The recommendation for Meridian AI:** use the database engine for the
**application** roles (`meridian_app` → `meridian-ai-app` role), and keep
**one** static credential only for the **OpenBao admin account itself**
(`meridian_vault_admin`), which by definition cannot be dynamic. That is
the correct shape: exactly one static secret, sitting in OpenBao, never
in Git, and the single thing you rotate by hand.

---

## 4. PKI in depth

### 4.1 The core concept

> **What is a PKI secret engine?** It lets OpenBao act as your
> **certificate authority**: a trusted party that vouches for the identity
> in a certificate. Your services ask OpenBao for a certificate, and
> whatever trusts your CA can trust the service.

Three reasons a platform team ends up running its own CA rather than
buying public certificates:

1. **Internal-only names.** `ai-harness.meridian-ai.internal` is not a
   public name. A public CA will not issue for it, and you do not want it
   on the public internet anyway.
2. **Short lifetimes.** A public CA gives you 90 days. An internal CA can
   give you **one hour**, because revocation is cheap and automatic.
3. **Zero certificate-management plumbing.** No CSR files emailed to
   security, no manual `openssl` on a jump host, no expiry pager.

The hierarchy, and why there are two levels:

```
  Meridian AI Internal Root CA          <- offline, 1 year, signs nothing but the intermediate
            |
            v
  Meridian AI Issuing CA                <- online, 6 months, signs the leaf certs
            |
            v
  ai-harness.meridian-ai.internal       <- leaf, 24 hours, lives in the app's filesystem
```

> **Why an intermediate?** *Because the root must be offline. If the root
> is offline, you cannot re-sign a leaf — so you need an online CA whose
> compromise you can survive by throwing away the intermediate and
> re-issuing it from the root. This is the same two-tier design as
> "issuing CA" vs "root CA" in the public web PKI, and it is the single
> most important design decision in this section.*

### 4.2 The root CA

```console
$ bao secrets tune -max-lease-ttl=8760h -default-lease-ttl=72h ai/pki
Success! Tuned the secrets engine at: ai/pki/

$ bao write ai/pki/root/generate/internal \
  common_name="Meridian AI Internal Root CA" \
  issuer_name="meridian-ai-root-2026" \
  key_type=ec key_bits=256 ttl=8760h
```

The response, verbatim:

```console
WARNING! The following warnings were returned from OpenBao:

  * This mount hasn't configured any authority information access (AIA)
  fields; this may make it harder for systems to find missing certificates
  in the chain or to validate revocation status of certificates. Consider
  updating /config/urls or the newly generated issuer with this information.

Key              Value
---              -----
certificate      -----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMDlaFw0yNzEwMjExODAxMzlaMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJ
IEludGVybmFsIFJvb3QgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASDiuw3
PvBJjQbET/JQ5xppaEA4bF/7VEj7gP26I3aSgdQ4XBgVqf6CujS6YztM4DSypbkz
Zlb9eTsY90xj0Bpno2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQULaA5j+yT6X6IK/OF03/iKZEzeJ0wHwYDVR0jBBgwFoAULaA5
j+yT6X6IK/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAJS7zX6d0GC71LQ6
SC/s82rFDH8OX0U0Ijml/6QQSScRAiBBTXweil7crI5sXDBX+/fg5+wcDCClEEtc
6zeGJ6QkPQ==
-----END CERTIFICATE-----
expiration       1824141699
issuer_id        0d252b49-a736-6517-2067-153aa848b117
issuer_name      meridian-ai-root-2026
issuing_ca       -----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMDlaFw0yNzEwMjExODAxMzlaMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJ
IEludGVybmFsIFJvb3QgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASDiuw3
PvBJjQbET/JQ5xppaEA4bF/7VEj7gP26I3aSgdQ4XBgVqf6CujS6YztM4DSypbkz
Zlb9eTsY90xj0Bpno2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQULaA5j+yT6X6IK/OF03/iKZEzeJ0wHwYDVR0jBBgwFoAULaA5
j+yT6X6IK/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAJS7zX6d0GC71LQ6
SC/s82rFDH8OX0U0Ijml/6QQSScRAiBBTXweil7crI5sXDBX+/fg5+wcDCClEEtc
6zeGJ6QkPQ==
-----END CERTIFICATE-----
key_id           e7c73809-c879-4fab-0ed1-8cce24248244
key_name         n/a
serial_number    59:7f:c5:62:89:48:44:72:be:df:dd:c9:bb:b9:7d:fb:f9:f9:68:e3
```

The fields, and what each one is for:

| Field | What it is | Why you care |
|---|---|---|
| `certificate` | The root's own X.509 certificate | You distribute this to every system that must trust you. |
| `issuing_ca` | The issuing CA for *this* certificate — for a self-signed root this is the root itself | Ship this to your clients as the trust anchor. |
| `expiration` | Unix timestamp `1824141699` | 2027-10-21. Root expiry is a **calendar alarm**, not a lease. |
| `issuer_id` | The UUID OpenBao assigned to this CA | Referenced by roles via `issuer_ref`. |
| `issuer_name` | Your human label, `meridian-ai-root-2026` | Much nicer to read in a role than a UUID. |
| `key_id` | The key's UUID | Needed for `sys/rotate` / key removal. |
| `serial_number` | The X.509 serial, in colon-hex | Needed to revoke this exact certificate. |
| `key_name` | `n/a` | 2.7 lets you name individual keys; the root's key is unnamed here. |

The `WARNING` about **AIA** (Authority Information Access) is not
decoration. AIA is the X.509 extension that says "for this certificate's
revocation status, go ask *this* URL". Without it, a relying party cannot
find your CRL, so it cannot check whether a certificate was revoked.
OpenBao is telling you: *you have not told your clients where to find the
CRL*. The fix is `bao write ai/pki/config/urls issuing_certificates=... crl_distribution_points=...`.

> **Production:** *Set the AIA/CRL URLs **before** you issue production
> certificates, not after. You cannot retroactively add AIA to a
> certificate that has already been issued — you have to reissue. Plan
> the public hostname of your CRL endpoint (something like
> `https://pki.meridian-ai.internal/v1/ai/pki/crl`) in week one, even if
> the endpoint itself is not live yet. The exact command is in §4.7,
> with the real output.*

> **Trade-off:** *`key_type=ec key_bits=256` gives you P-256. It is fast,
> small, and universally supported. `rsa` with 4096 bits is what a public
> CA does because some ancient clients cannot do ECDSA. Inside your own
> datacenter, where you control every client, ECDSA P-256 is the right
> default: it is roughly 10x smaller and much faster.*

### 4.3 The intermediate CA

Three steps: **generate a key + CSR**, **sign that CSR with the root**,
**import the signed certificate**.

Step 1 — generate the key and CSR inside OpenBao:

```console
$ bao write -format=json ai/pki/intermediate/generate/internal \
  common_name="Meridian AI Issuing CA" issuer_name="meridian-ai-intermediate-2026" \
  key_type=ec key_bits=256
```

```json
{
  "request_id": "5b7b609b-2866-0f3e-818d-05e932cd6eda",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "csr": "-----BEGIN CERTIFICATE REQUEST-----\nMIHdMIGDAgEAMCExHzAdBgNVBAMTFk1lcmlkaWFuIEFJIElzc3VpbmcgQ0EwWTAT\nBgcqhkjOPQIBBggqhkjOPQMBBwNCAASzGdmozdszzrWK4DXuorLwbX0e0rRbR1Av\nENPFX5D9FU1BrtPicrIoGoHpYo0XohDv9rA0h1c06vR92P7Ei0YuoAAwCgYIKoZI\nzj0EAwIDSQAwRgIhAMSN4eeiPOnKBWihadwi6wM70vcPDtdzg/ZRj7TKh2hDAiEA\nm/JL4kBtr5RHFvqxlY+th2t8dLXKw0JOw0LJ9hxKtyM=\n-----END CERTIFICATE REQUEST-----",
    "key_id": "ebc97294-b265-0f29-8da9-5fcd3b8a625d"
  },
  "warnings": [
    "This mount hasn't configured any authority information access (AIA) fields; this may make it harder for systems to find missing certificates in the chain or to validate revocation status of certificates. Consider updating /config/urls or the newly generated issuer with this information. Since this certificate is an intermediate, it might be useful to regenerate this certificate after fixing this problem for the root mount.",
    "Endpoint ignored these unrecognized parameters: [issuer_name]"
  ]
}
```

> **Capture the CSR immediately.** The `csr` field is the only place the
> request exists — it is not stored anywhere you can read back. Pipe it
> straight to a file in the same command:
>
> ```bash
> bao write -format=json ai/pki/intermediate/generate/internal \
>   common_name="Meridian AI Issuing CA" key_type=ec key_bits=256 \
>   | jq -r '.data.csr' > intermediate.csr
> ```
>
> (The transcript above is from the first `generate` call; the CSR that was
> actually signed in the next step came from a second call, because the
> first one was not piped to a file and the CSR is not re-readable. That
> mistake cost one extra key pair — which is exactly why you should pipe
> it to a file the first time.)

> ⚠️ **Gotcha:** *`issuer_name` is **not** accepted by
> `intermediate/generate/internal`. The server says so plainly:
> `"Endpoint ignored these unrecognized parameters: [issuer_name]"`. You
> name the intermediate later, in section 4.5.*

Also note: the response contains a `csr` and a `key_id` but **no
certificate**. The intermediate is not a CA yet — it is a key and a
request.

Step 2 — sign the CSR with the root:

```console
$ bao write ai/pki/root/sign-intermediate \
  csr=@intermediate.csr \
  common_name="Meridian AI Issuing CA" \
  issuer_name="meridian-ai-intermediate-2026" \
  format=pem_bundle ttl=4380h
```

```console
Key              Value
---              -----
ca_chain         [-----BEGIN CERTIFICATE-----
MIIBrTCCAVOgAwIBAgIUNkgjAX3aDBrpvX4QJWR84OdmBAMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMTZaFw0yNzA0MjIwNjAxNDZaMCExHzAdBgNVBAMTFk1lcmlkaWFuIEFJ
IElzc3VpbmcgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAREg7eNh0yhxVb6
lsTDzjItL/6z2WkO0zklR9V1VbwcNWtpLV5c+yD/ieirnkYkuCQ/ryZCCc/9Wndp
APIEG4gDo2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB/zAdBgNV
HQ4EFgQUaspkgrJKqFcCXcuZ0piYW3jBpnIwHwYDVR0jBBgwFoAULaA5j+yT6X6I
K/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAKUgtRk7B8YW6BeN6Oyv++f5
K9efeVFRyGPJ0+FZIAnQAiBHVGgRmzRdWJk6Y7vFJNA3S6aZcfs9qtqo+85OQ3Nf
aA==
-----END CERTIFICATE----- -----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMDlaFw0yNzEwMjExODAxMzlaMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJ
IEludGVybmFsIFJvb3QgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASDiuw3
PvBJjQbET/JQ5xppaEA4bF/7VEj7gP26I3aSgdQ4XBgVqf6CujS6YztM4DSypbkz
Zlb9eTsY90xj0Bpno2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQULaA5j+yT6X6IK/OF03/iKZEzeJ0wHwYDVR0jBBgwFoAULaA5
j+yT6X6IK/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAJS7zX6d0GC71LQ6
SC/s82rFDH8OX0U0Ijml/6QQSScRAiBBTXweil7crI5sXDBX+/fg5+wcDCClEEtc
6zeGJ6QkPQ==
-----END CERTIFICATE-----]
certificate      -----BEGIN CERTIFICATE-----
MIIBrTCCAVOgAwIBAgIUNkgjAX3aDBrpvX4QJWR84OdmBAMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMTZaFw0yNzA0MjIwNjAxNDZaMCExHzAdBgNVBAMTFk1lcmlkaWFuIEFJ
IElzc3VpbmcgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAREg7eNh0yhxVb6
lsTDzjItL/6z2WkO0zklR9V1VbwcNWtpLV5c+yD/ieirnkYkuCQ/ryZCCc/9Wndp
APIEG4gDo2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB/zAdBgNV
HQ4EFgQUaspkgrJKqFcCXcuZ0piYW3jBpnIwHwYDVR0jBBgwFoAULaA5j+yT6X6I
K/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAKUgtRk7B8YW6BeN6Oyv++f5
K9efeVFRyGPJ0+FZIAnQAiBHVGgRmzRdWJk6Y7vFJNA3S6aZcfs9qtqo+85OQ3Nf
aA==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMDlaFw0yNzEwMjExODAxMzlaMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJ
IEludGVybmFsIFJvb3QgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASDiuw3
PvBJjQbET/JQ5xppaEA4bF/7VEj7gP26I3aSgdQ4XBgVqf6CujS6YztM4DSypbkz
Zlb9eTsY90xj0Bpno2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQULaA5j+yT6X6IK/OF03/iKZEzeJ0wHwYDVR0jBBgwFoAULaA5
j+yT6X6IK/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAJS7zX6d0GC71LQ6
SC/s82rFDH8OX0U0Ijml/6QQSScRAiBBTXweil7crI5sXDBX+/fg5+wcDCClEEtc
6zeGJ6QkPQ==
-----END CERTIFICATE-----
expiration       1808373706
issuing_ca       -----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
JzElMCMGA1UEAxMcTWVyaWRpYW4gQUkgSW50ZXJuYWwgUm9vdCBDQTAeFw0yNjEw
MjExODAxMDlaFw0yNzEwMjExODAxMzlaMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJ
IEludGVybmFsIFJvb3QgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAASDiuw3
PvBJjQbET/JQ5xppaEA4bF/7VEj7gP26I3aSgdQ4XBgVqf6CujS6YztM4DSypbkz
Zlb9eTsY90xj0Bpno2MwYTAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB
/zAdBgNVHQ4EFgQULaA5j+yT6X6IK/OF03/iKZEzeJ0wHwYDVR0jBBgwFoAULaA5
j+yT6X6IK/OF03/iKZEzeJ0wCgYIKoZIzj0EAwIDSAAwRQIhAJS7zX6d0GC71LQ6
SC/s82rFDH8OX0U0Ijml/6QQSScRAiBBTXweil7crI5sXDBX+/fg5+wcDCClEEtc
6zeGJ6QkPQ==
-----END CERTIFICATE-----
serial_number    36:48:23:01:7d:da:0c:1a:e9:bd:7e:10:25:64:7c:e0:e7:66:04:03
```

The four fields to note:

- `certificate` — the **signed intermediate** (a PEM *bundle*: the
  intermediate first, then the root, because `format=pem_bundle`).
- `ca_chain` — the array of CAs above it, in order. This is what you
  hand to a client that needs to build a chain.
- `issuing_ca` — the **root**'s certificate. This is the trust anchor.
- `serial_number` — the intermediate's serial, needed to revoke it.

Step 3 — import it back into the mount:

```console
$ bao write ai/pki/intermediate/set-signed certificate=@intermediate.crt
```

```console
Key                 Value
---                 -----
existing_issuers    [0d252b49-a736-6517-2067-153aa848b117]
existing_keys       <nil>
imported_issuers    [9570ada9-a818-cb6c-af7c-d66649ce225c]
imported_keys       <nil>
mapping             map[0d252b49-a736-6517-2067-153aa848b117:e7c73809-c879-4fab-0ed1-8cce24248244 9570ada9-a818-cb6c-af7c-d66649ce225c:2c80f815-c125-5140-7e83-37593699d3f6]
```

Read that `mapping` carefully — it is the whole point:

```
0d252b49-... : e7c73809-...   <- root issuer id  : root key id
9570ada9-... : 2c80f815-...   <- imported issuer id : imported key id
```

The `imported_issuers` entry is your new intermediate, now a first-class
issuer in this mount, with its own key.

> **CLI gotcha:** *`csr=@intermediate.csr` means "read the value of `csr`
> from the file `intermediate.csr`". Without the `@` you send the literal
> string `@intermediate.csr` and get:*
>
> ```console
> Failed to parse K=V data: invalid key/value pair "csr=@intermediate.csr": error reading file: open intermediate.csr: no such file or directory
> ```

> ⚠️ **Gotcha:** *`bao read -field=csr ai/pki/intermediate/csr` returns
> `No value found at ai/pki/intermediate/csr`. The CSR is **not** stored
> at a readable path — it is only in the response of the `generate` call.
> If you lose it, generate it again; the old key becomes an orphan you
> should clean up with `sys/rotate`.*

### 4.4 The issuer model in 2.7 — and its sharp edges

OpenBao 2.7's PKI engine is **multi-CA**: one mount can hold several
issuers, each with an `issuer_id` (UUID) and an `issuer_name` (your
label). Roles pick a signer with `issuer_ref`.

Listing them:

```console
$ bao list -format=json ai/pki/issuers
[
  "0d252b49-a736-6517-2067-153aa848b117",
  "9570ada9-a818-cb6c-af7c-d66649ce225c"
]
```

> ⚠️ **Gotcha:** *the list path is `ai/pki/issuers` — **plural**. The
> singular `ai/pki/issuer` is the path for *reading one* issuer, and
> listing it returns:*
>
> ```console
> $ bao list -format=json ai/pki/issuer
> {}
> ```
>
> *An empty object, not an error. Easy to misread as "no issuers exist".*

Reading one issuer shows the full model:

```console
$ bao read ai/pki/issuer/0d252b49-a736-6517-2067-153aa848b117
Key                               Value
---                               -----
ca_chain                          [-----BEGIN CERTIFICATE----- ... ]
certificate                       -----BEGIN CERTIFICATE----- ...
crl_distribution_points           []
delta_crl_distribution_points     []
issuer_id                         0d252b49-a736-6517-2067-153aa848b117
issuer_name                       meridian-ai-root-2026
issuing_certificates              []
key_id                            e7c73809-c879-4fab-0ed1-8cce24248244
leaf_not_after_behavior           err
manual_chain                      <nil>
ocsp_servers                      []
revocation_signature_algorithm    ECDSAWithSHA256
revoked                           false
usage                             crl-signing,issuing-certificates,ocsp-signing,read-only
```

Three fields to understand:

- `usage` — what this CA is *allowed* to do. A root here can issue
  certificates and sign CRLs, but note it also says `read-only`... that
  line is the `usage` list OpenBao reports for the *default* root: it can
  issue and sign CRLs, and its key is stored read-only.
- `revoked` — set to `true` when the CA itself is revoked.
- `leaf_not_after_behavior` — what happens when a leaf's requested expiry
  exceeds the CA's own expiry. `err` = refuse to issue. The alternative
  is `truncate` (issue, but clamp the expiry) or `permits`. `err` is the
  safe default.

**Naming the intermediate.** The `set-signed` import left the new issuer
unnamed. Name it explicitly:

```console
$ bao write ai/pki/issuer/9570ada9-a818-cb6c-af7c-d66649ce225c \
    issuer_name=meridian-ai-intermediate-2026
```

> ⚠️ **Sharp edge, verified:** *`bao write ai/pki/issuer/default
> issuer_id=...` is **not** how you change the default issuer. The server
> answered:*
>
> ```console
> WARNING! The following warnings were returned from OpenBao:
>
>   * Endpoint ignored these unrecognized parameters: [issuer_id]
> ```
>
> *and the response came back showing the **root** issuer with
> `issuer_name: n/a` — the write had cleared the root's name. I had to
> restore it with `bao write ai/pki/issuer/0d252b49-... issuer_name=meridian-ai-root-2026`.*
>
> **Do not poke `ai/pki/issuer/default` with a write.** Pick the signer
> per role with `issuer_ref` instead — which is clearer anyway, because
> you can have a "staging" role signed by a test CA and a "production"
> role signed by the real one, in the same mount.*

### 4.5 Roles

A PKI role is the *policy* for issuance: which names, which CA, how
long, what EKU.

```console
$ bao write ai/pki/roles/ai-harness \
  allowed_domains="meridian-ai.internal" \
  allow_subdomains=true \
  allow_bare_domains=false \
  allow_localhost=false \
  allow_any_name=false \
  allow_ip_sans=false \
  enforce_hostnames=true \
  max_ttl=72h ttl=24h \
  key_type=ec key_bits=256 \
  server_flag=true client_flag=true \
  key_usage="DigitalSignature,KeyEncipherment" \
  ext_key_usage="ServerAuth,ClientAuth" \
  require_cn=true \
  issuer_ref=meridian-ai-intermediate-2026
```

```console
$ bao read ai/pki/roles/ai-harness
Key                                   Value
---                                   -----
allow_any_name                        false
allow_bare_domains                    false
allow_glob_domains                    false
allow_globs_in_identity_templates     false
allow_ip_sans                         false
allow_localhost                       false
allow_subdomains                      true
allow_token_displayname               false
allow_wildcard_certificates           true
allowed_domains                       [meridian-ai.internal]
allowed_domains_template              false
allowed_ip_sans_cidr                  []
allowed_other_sans                    []
allowed_serial_numbers                []
allowed_uri_sans                      []
allowed_uri_sans_template             false
allowed_user_ids                      []
basic_constraints_valid_for_non_ca    false
client_flag                           true
cn_validations                        [email hostname]
code_signing_flag                     false
country                               []
email_protection_flag                  false
enforce_hostnames                     true
ext_key_usage                         [ServerAuth ClientAuth]
ext_key_usage_oids                    []
generate_lease                        false
issuer_ref                            meridian-ai-intermediate-2026
key_bits                              256
key_type                              ec
key_usage                             [DigitalSignature KeyEncipherment]
locality                              []
max_ttl                               72h
no_store                              false
not_after                             n/a
not_after_bound                       permit
not_before                            n/a
not_before_bound                      permit
not_before_duration                   30s
organization                          []
ou                                    []
policy_identifiers                    []
postal_code                           []
province                              []
require_cn                            true
server_flag                           true
signature_bits                        0
street_address                        []
ttl                                   24h
use_csr_common_name                   true
use_csr_sans                          true
use_pss                               false
```

The settings that matter most for Meridian AI:

| Setting | Value | Why |
|---|---|---|
| `allowed_domains` | `meridian-ai.internal` | The only namespace this role may issue for. |
| `allow_any_name` | `false` | **Never** `true` on a production role. It lets anyone get a cert for any name — a universal forgery. |
| `allow_bare_domains` | `false` | A bare `meridian-ai.internal` cert is for the domain, not a host. |
| `enforce_hostnames` | `true` | Rejects names that are not valid hostnames. |
| `server_flag` + `client_flag` | both `true` | The role can issue both TLS server certs and mTLS client certs. |
| `ext_key_usage` | `ServerAuth,ClientAuth` | The X.509 Extended Key Usage. This is what stops a server cert being used as a client cert. |
| `require_cn` | `true` | A cert with no CN is useless for hostname validation. |
| `issuer_ref` | the intermediate | Which CA signs. |
| `ttl` / `max_ttl` | `24h` / `72h` | A leaf lives a day; the role will never issue beyond three days. |

> ⚠️ **The nastiest gotcha in this whole module:** *writing a role is a
> **full replacement**, not a patch. After creating the role above, this
> one-liner was run to change the signing CA:*
>
> ```console
> $ bao write ai/pki/roles/ai-harness issuer_ref=meridian-ai-intermediate-2026
> ```
>
> *and the role came back with `allowed_domains []`,
> `allow_subdomains false`, `enforce_hostnames true` — **every field I
> had not re-specified was reset to its default.** The very next
> issuance failed:*
>
> ```console
> $ bao write ai/pki/issue/ai-harness \
>     common_name="ai-harness.meridian-ai.internal" \
>     alt_names="ai-harness.meridian-ai.internal,ai-harness.svc.meridian-ai.internal" \
>     ttl=24h
> Error writing data to ai/pki/issue/ai-harness: Error making API request.
>
> URL: PUT http://127.0.0.1:9158/v1/ai/pki/issue/ai-harness
> Code: 400. Errors:
>
> * common name ai-harness.meridian-ai.internal not allowed by this role
> ```
>
> **Always write the whole role, every time.** Keep it in Git and
> `bao write` it from the file. Do not "just tweak one field".*

### 4.6 Issuing a leaf certificate

Now the payoff. This is the real, unmodified response:

```console
$ bao write ai/pki/issue/ai-harness \
  common_name="ai-harness.meridian-ai.internal" \
  alt_names="ai-harness.meridian-ai.internal,ai-harness.svc.meridian-ai.internal" \
  ttl=24h
```

```console
Key              Value
---              -----
ca_chain         [-----BEGIN CERTIFICATE-----
MIIBrTCCAVOgAwIBAgIUNkgjAX3aDBrpvX4QJWR84OdmBAMwCgYIKoZIzj0EAwIw
... (the issuing CA — Meridian AI Issuing CA)
-----END CERTIFICATE----- -----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWX/FYolIRHK+393Ju7l9+/n5aOMwCgYIKoZIzj0EAwIw
... (the root CA)
-----END CERTIFICATE-----]
certificate      -----BEGIN CERTIFICATE-----
MIICETCCAbegAwIBAgIUCnWFmVrA492zItJt/reTc6i1zNUwCgYIKoZIzj0EAwIw
ITEfMB0GA1UEAxMWTWVyaWRpYW4gQUkgSXNzdWluZyBDQTAeFw0yNjEwMjExODAy
MDZaFw0yNjEwMjIxODAyMzZaMCoxKDAmBgNVBAMTH2FpLWhhcm5lc3MubWVyaWRp
YW4tYWkuaW50ZXJuYWwwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAAQPwDKIL1mX
jbheYw4+/HaQj77pEUULzQB8hgGTcE8h+ZmT2KO6J59iKaxhHIpeWA5TuSpeOwl/
9S/FULotjvbno4HDMIHAMA4GA1UdDwEB/wQEAwIFoDAdBgNVHSUEFjAUBggrBgEF
BQcDAQYIKwYBBQUHAwIwHQYDVR0OBBYEFAxPnTapjA4nMREQsl18honOukTCMB8G
A1UdIwQYMBaAFGrKZIKySqhXAl3LmdKYmFt4waZyME8GA1UdEQRIMEaCH2FpLWhh
cm5lc3MubWVyaWRpYW4tYWkuaW50ZXJuYWyCI2FpLWhhcm5lc3Muc3ZjLm1lcmlk
aWFuLWFpLmludGVybmFsMAoGCCqGSM49BAMCA0gAMEUCICFmbEOJ3AsprZ7M1Eyi
/6ixJRtmwabjK3AJcP2Iutc4AiEAvdoOLODahI7I4QvjlEWG1uzjLnUnC7T0NQPc
9sg9dZg=
-----END CERTIFICATE-----
expiration       1792692156
issuing_ca       -----BEGIN CERTIFICATE-----
MIIBrTCCAVOgAwIBAgIUNkgjAX3aDBrpvX4QJWR84OdmBAMwCgYIKoZIzj0EAwIw
... (the issuing CA)
-----END CERTIFICATE-----
not_before          1792605726
private_key        -----BEGIN EC PRIVATE KEY-----
MHcCAQEEIFCUvd+U/fULOMYYA2FjMUb4ScKhnyNBDpgcZrDNpQmioAoGCCqGSM49
AwEHoUQDQgAED8AyiC9Zl424XmMOPvx2kI++6RFFC80AfIYBk3BPIfmZk9ijuief
YimsYRyKXlgOU7kqXjsJf/UvxVC6LY725w==
-----END EC PRIVATE KEY-----
private_key_type    ec
serial_number       0a:75:85:99:5a:c0:e3:dd:b3:22:d2:6d:fe:b7:93:73:a8:b5:cc:d5
```

**The exact field names, all eight of them:**

| Field | Meaning |
|---|---|
| `certificate` | The leaf certificate (PEM) |
| `private_key` | The leaf's private key (PEM) |
| `private_key_type` | `ec` — the algorithm of that key |
| `issuing_ca` | The CA that signed it (the intermediate) |
| `ca_chain` | Array of PEMs: intermediate + root, in chain order |
| `serial_number` | The leaf's X.509 serial — the handle for revocation |
| `expiration` | Unix timestamp when the leaf stops being valid |
| `not_before` | Unix timestamp when it starts being valid |

Note what is **absent**: there is no `lease_id` and no `lease_duration`.
A PKI certificate is not a leased secret in the OpenBao sense — it has a
*cryptographic* expiry baked into the X.509 `notAfter` field, and the
certifying authority enforces it. The role's `ttl`/`max_ttl` bound what
`expiration` can be; the *trusting* system enforces it. OpenBao's
`generate_lease` role setting (default `false`) can turn on lease
tracking for certs if you want revocation events in the lease manager, but
the certificate's lifetime does not depend on it.

**How the app uses it.** In Python:

```python
import pathlib, ssl, subprocess

cert_pem = bao_read("ai/pki/issue/ai-harness",
                    common_name="ai-harness.meridian-ai.internal")["certificate"]
key_pem  = bao_read(...)["private_key"]

pathlib.Path("/etc/meridian/tls.crt").write_text(cert_pem)
pathlib.Path("/etc/meridian/tls.key").write_text(key_pem, mode=0o600)
```

> **Production:** *`no_store=true` on the role tells OpenBao not to keep
> the issued certificate in its storage (it is still returned to you).
> Use it when the client is expected to store the cert itself and you do
> not want a second copy sitting in OpenBao's database. Conversely, leave
> it `false` (the default) when you want the audit trail to be able to
> show exactly which certificate was issued to whom.*

> **Production:** *The `private_key` is returned **in plain PEM** in the
> response body. It is not a wrapping token. If your CI logs responses,
> it logs the private key. Use `bao write -format=json ... | jq -r .data.private_key`
> into a file with `umask 077`, and never `echo` it.*

### 4.7 Revocation

The serial number is the handle. This is the real revocation of the
certificate issued in §4.6:

```console
$ bao write ai/pki/revoke \
  serial_number="0a:75:85:99:5a:c0:e3:dd:b3:22:d2:6d:fe:b7:93:73:a8:b5:cc:d5"
Key                        Value
---                        -----
revocation_time            1792606314
revocation_time_rfc3339    2026-10-21T18:11:54.304428896Z
state                      revoked
```

`state: revoked` — the serial is now on the CRL.

You also need a CRL for relying parties to check. OpenBao serves one, and
in 2.7.1 the **rotate** endpoint is a `GET`, not a write:

```console
$ bao read ai/pki/crl/rotate
Key        Value
---        -----
success    true
```

> ⚠️ **Gotcha:** *`bao write -force ai/pki/crl/rotate` returns*
>
> ```console
> Error writing data to ai/pki/crl/rotate: Error making API request.
>
> URL: PUT http://127.0.0.1:9158/v1/ai/pki/crl/rotate
> Code: 405. Errors:
>
> * 1 error occurred:
> 	* unsupported operation
> ```
>
> *Use `bao read ai/pki/crl/rotate`. The same is true of
> `ai/pki/crl/rotate-delta`.*

The CRL itself is served as **DER** at `ai/pki/crl` and as **PEM** at
`ai/pki/crl/pem`. The CLI cannot render either — they are raw documents,
not a Secret:

```console
$ bao read ai/pki/crl
Error reading ai/pki/crl: json: cannot unmarshal number into Go value of type api.Secret

$ bao read ai/pki/crl/pem
Error reading ai/pki/crl/pem: invalid character '-' in numeric literal
```

Use `curl` and save the bytes:

```console
$ curl -s -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/ai/pki/crl/pem"
-----BEGIN X509 CRL-----
MIHgMIGHAgEBMAoGCCqGSM49BAMCMCcxJTAjBgNVBAMTHE1lcmlkaWFuIEFJIElu
dGVybmFsIFJvb3QgQ0EXDTI2MTAyMTE4MTE1NFoXDTI2MTAyNDE4MTE1NFqgLzAt
MB8GA1UdIwQYMBaAFC2gOY/sk+l+iCvzhdN/4imRM3idMAoGA1UdFAQDAgEJMAoG
CCqGSM49BAMCA0gAMEUCIQCzLyMJyTWQS29MJgEmSo0R24OoKRpKAslIWq7TRv9A
FQIgRuz9UjctPMCcIimlr0FMIpjh59b9qkdwaCYTj9ZSxsM=
...
-----END X509 CRL-----
```

And here is the AIA configuration that fixes the warning you saw back in
§4.2 — this is the endpoint the warning was pointing you at:

```console
$ bao write ai/pki/config/urls \
  issuing_certificates="$BAO_ADDR/v1/ai/pki/ca" \
  crl_distribution_points="$BAO_ADDR/v1/ai/pki/crl"
Key                              Value
---                              -----
crl_distribution_points          [http://127.0.0.1:9158/v1/ai/pki/crl]
delta_crl_distribution_points    []
enable_templating                false
issuing_certificates             [http://127.0.0.1:9158/v1/ai/pki/ca]
ocsp_servers                     []
```

Before you set it, it looks like this — every list empty, which is
exactly why the issuer warned you:

```console
$ bao read ai/pki/config/urls
Key                              Value
---                              -----
crl_distribution_points          []
delta_crl_distribution_points    []
enable_templating                false
issuing_certificates             []
ocsp_servers                     []
```

> **Trade-off:** *CRLs are simple but scale badly — the list grows until
> it is rotated, and every relying party downloads the whole thing.
> OCSP is a per-certificate query and scales better, but needs a
> responder that is always up. For a company with a handful of
> internal services, a CRL on a short rotation interval is the pragmatic
> choice.*

### 4.8 ACME — letting cert-manager renew itself

ACME (RFC 8555) is the protocol **cert-manager** speaks. Turn on the
ACME server on your PKI mount and cert-manager handles issuance and
renewal with no OpenBao client in your cluster.

```console
$ bao write ai/pki/config/acme \
  enabled=true \
  allowed_roles="ai-harness" \
  allowed_issuers="meridian-ai-intermediate-2026" \
  dns_resolver="127.0.0.1:53" \
  default_directory_policy="sign-verbatim"
```

Two real errors from the way there, both worth knowing:

```console
$ bao write ai/pki/config/acme \
  ... default_directory_policy="http://127.0.0.1:8200/v1/ai/pki/acme/directory"
Error writing data to ai/pki/config/acme: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/pki/config/acme
Code: 500. Errors:

* 1 error occurred:
	* invalid default_directory_policy: string http://127.0.0.1:8200/v1/ai/pki/acme/directory not a valid Default Directory Policy
```

`default_directory_policy` is **not** a URL. It is one of a small set of
policies:

| Policy | Meaning |
|---|---|
| `sign-verbatim` | The directory URL is signed exactly as the client requests it. The usual choice. |
| `nonce-required` | Requires a nonce on every request. Stricter, needs nonce support. |

And then the one that catches everybody:

```console
$ bao write ai/pki/config/acme \
  enabled=true allowed_roles="ai-harness" \
  allowed_issuers="meridian-ai-intermediate-2026" \
  dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
Error writing data to ai/pki/config/acme: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/pki/config/acme
Code: 500. Errors:

* 1 error occurred:
	* ACME feature requires local cluster 'path' field configuration to be set
```

The cluster **`path`** is a **PKI-mount** setting in OpenBao 2.7.1, not a
server config field. It lives at `ai/pki/config/cluster`, and it must be
a **URL** — the directory URL that OpenBao will hand to ACME clients:

```console
$ bao write ai/pki/config/cluster path="https://bao-1.meridian-ai.internal:8200"
Key         Value
---         -----
aia_path    n/a
path        https://bao-1.meridian-ai.internal:8200
```

> ⚠️ **Gotcha:** *the value has to be a URL. A bare name is rejected:*
>
> ```console
> $ bao write ai/pki/config/cluster path="meridian-ai"
> Error writing data to ai/pki/config/cluster: Error making API request.
>
> URL: PUT http://127.0.0.1:9158/v1/ai/pki/config/cluster
> Code: 500. Errors:
>
> * 1 error occurred:
> 	* invalid, non-URL path given to cluster: meridian-ai
> ```

With the cluster path set, the ACME write that failed above now takes:

```console
$ bao write ai/pki/config/acme \
  enabled=true allowed_roles="ai-harness" \
  allowed_issuers="meridian-ai-root-2026" \
  dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
Key                         Value
---                         -----
allow_role_ext_key_usage    false
allowed_issuers             [meridian-ai-root-2026]
allowed_roles               [ai-harness]
default_directory_policy    sign-verbatim
dns_resolver                127.0.0.1:53
eab_policy                  not-required
enabled                     true
```

and the ACME directory answers:

```console
$ curl -s -o /dev/null -w "%{http_code}\n" "$BAO_ADDR/v1/ai/pki/acme/directory"
200
```

> ⚠️ **Gotcha: `/acme/directory` resolves the *default* issuer — and the
> default issuer is the root, not your intermediate.** ACME turns on
> happily, the write succeeds, and then the directory endpoint fails:
>
> ```console
> $ bao write ai/pki/config/acme enabled=true allowed_roles="ai-harness" \
>     allowed_issuers="meridian-ai-intermediate-2026" \
>     dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
> Key                         Value
> ---                         -----
> allowed_issuers             [meridian-ai-intermediate-2026]
> enabled                     true
>
> $ curl -s "$BAO_ADDR/v1/ai/pki/acme/directory"
> {"type":"urn:ietf:params:acme:error:serverInternal","detail":"the server experienced an internal error: specified issuer not allowed by ACME policy"}
> HTTP 500
> ```
>
> There are two ways out, and you should know which one you want:
>
> | What you want | What to do |
> |---|---|
> | The **default** issuer (the root) serves ACME | Put the default issuer's name in `allowed_issuers` — `meridian-ai-root-2026` in this module. Then `/ai/pki/acme/directory` returns `200`. |
> | The **intermediate** serves ACME | Use the issuer-scoped path instead: `/ai/pki/issuer/<issuer_id>/acme/directory`. Verified: it returns `200` for an issuer named in `allowed_issuers`, even when it is not the default. |
>
> For Meridian AI you want the **intermediate** to issue the leaf
> certificates, so the clean shape is: put **both** issuers in
> `allowed_issuers`, and point cert-manager at
> `/ai/pki/issuer/<intermediate_id>/acme/directory`.
>
> ```console
> $ bao write ai/pki/config/acme enabled=true allowed_roles="ai-harness" \
>     allowed_issuers="meridian-ai-root-2026,meridian-ai-intermediate-2026" \
>     dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
> $ curl -s -o /dev/null -w "%{http_code}\n" "$BAO_ADDR/v1/ai/pki/acme/directory"
> 200
> $ curl -s -o /dev/null -w "%{http_code}\n" \
>     "$BAO_ADDR/v1/ai/pki/issuer/9570ada9-a818-cb6c-af7c-d66649ce225c/acme/directory"
> 200
> ```
>
> ⚠️ **That UUID is ours, not yours — substitute your own.** The issuer id
> `9570ada9-a818-cb6c-af7c-d66649ce225c` is what **this capture** produced on
> **our** mount. Your mount generates a different one every time, so
> copy-pasting the literal hits an issuer that does not exist on your server:
>
> ```console
> $ curl -s -w "\n%{http_code}\n" \
>     "$BAO_ADDR/v1/ai/pki/issuer/9570ada9-a818-cb6c-af7c-d66649ce225c/acme/directory"
> {"type":"urn:ietf:params:acme:error:malformed","detail":"the request message was malformed: issuer does not exist"}
> 400
> ```
>
> Read yours off the mount and put *that* in the URL:
>
> ```console
> $ bao read -field=issuer_id ai/pki/issuer/default
> 40a6c7f2-8d0d-4fce-03d5-44eda1ab2d03
> ```
>
> For the **imported** intermediate, take the id from the `imported_issuers`
> list you got back from `set-signed` in §4.6.
>
> ⚠️ **And note the two different kinds of identifier.** `allowed_issuers`
> takes issuer **names**; the URL path takes the issuer **UUID**. The server
> checks the names at write time, so a name that does not exist fails the
> whole ACME configuration:
>
> ```console
> $ bao write ai/pki/config/acme enabled=true allowed_roles="ai-harness" \
>     allowed_issuers="meridian-ai-root-2026" \
>     dns_resolver="127.0.0.1:53" default_directory_policy="sign-verbatim"
> Error writing data to ai/pki/config/acme: Error making API request.
>
> URL: PUT http://127.0.0.1:8200/v1/ai/pki/config/acme
> Code: 500. Errors:
>
> * 1 error occurred:
> 	* failed validating allowed_issuers: unable to fetch issuer: meridian-ai-root-2026: unable to find PKI issuer for reference: meridian-ai-root-2026
> ```
>
> A fresh mount's default issuer has an **empty** `issuer_name`, so it cannot
> be named in `allowed_issuers` until you give it one:
>
> ```console
> $ bao write ai/pki/issuer/$ISSUER_ID issuer_name=meridian-ai-root-2026
> ```

> ⚠️ **Trap: there is no `cluster { path = ... }` config stanza.** A
> Vault-era tutorial will tell you to add this to `openbao.hcl`:
>
> ```hcl
> cluster {
>   path = "meridian-ai"
> }
> ```
>
> **OpenBao 2.7.1 does not accept it.** The config parser rejects the
> whole file:
>
> ```console
> $ bao operator validate-config -config=cluster-path.hcl
> OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z
> [ warning ] Validate Config: Unknown or unsupported field cluster found in configuration at cluster-path.hcl:1:1.
> exit=2
> ```
>
> The top-level `cluster_path` field is rejected the same way. There is
> also **no** `sys/config/cluster/path` API — this lab confirmed it:
>
> ```console
> $ bao write sys/config/cluster/path path="meridian-ai"
> Error writing data to sys/config/cluster/path: Error making API request.
>
> URL: PUT http://127.0.0.1:9158/v1/sys/config/cluster/path
> Code: 404. Errors:
>
> * 1 error occurred:
> 	* unsupported path
> ```
>
> and the complete list of `/sys/config/*` paths in the 2.7.1 OpenAPI spec
> is:
>
> ```
> /sys/config/auditing/request-headers
> /sys/config/auditing/request-headers/{header}
> /sys/config/cors
> /sys/config/reload/{subsystem}
> /sys/config/state/sanitized
> /sys/config/ui/headers
> /sys/config/ui/headers/{header}
> ```
>
> No cluster path among them. The one place it lives is the PKI mount's
> own `ai/pki/config/cluster` endpoint — so turning ACME on is a **runtime
> API call, not a server restart**. Plan for that before you promise
> cert-manager renewal in a sprint.

> **Production:** *cert-manager can use OpenBao either as (a) an ACME
> server — cert-manager talks RFC 8555 to it, or (b) a **Secrets Store
> CSI Driver** provider — cert-manager asks Kubernetes for a secret and
> the driver fetches it from OpenBao. (b) is usually simpler, because
> ACME needs a public-ish DNS-01 challenge and a stable directory URL.
> Choose (b) unless you specifically need to issue certs for a domain you
> control from a cluster you do not run.*

### 4.9 ML-DSA — post-quantum signatures (new in 2.7)

OpenBao 2.7 added **ML-DSA (FIPS 204)** post-quantum signatures to PKI
and Transit, plus **pure-PQC TLS** via `tls_key_exchange_preferences`.
The motivation is "harvest now, decrypt later": an adversary who copies
your TLS traffic today and stores it can decrypt it in ten years, when
RSA-2048 is broken by a quantum computer.

**It works — and the parameter name is the whole trick.** The PKI key
type is `mldsa`, not `ml-dsa-44`. The hyphenated spelling looks like the
FIPS 204 algorithm name, and it is *not* what the API accepts:

```console
$ bao write ai/pki/root/generate/internal common_name="PQ Test CA" key_type=ml-dsa-44
Error writing data to ai/pki/root/generate/internal: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/pki/root/generate/internal
Code: 400. Errors:

* unknown key type ml-dsa-44
```

With the correct spelling you get a real ML-DSA-44 certificate:

```console
$ bao secrets enable -path=ai/pki-pq pki
Success! Enabled the pki secrets engine at: ai/pki-pq/

$ bao write ai/pki-pq/root/generate/internal \
    common_name="Meridian AI PQ Root CA" \
    issuer_name="meridian-ai-pq-root" \
    key_type=mldsa ttl=8760h
WARNING! The following warnings were returned from OpenBao:

  * TTL "8760h0m0s" is longer than permitted maxTTL "768h0m0s", so maxTTL is
  being used

  * This mount hasn't configured any authority information access (AIA)
  fields; this may make it harder for systems to find missing certificates
  in the chain or to validate revocation status of certificates. Consider
  updating /config/urls or the newly generated issuer with this information.

Key              Value
---              -----
certificate      -----BEGIN CERTIFICATE-----
MIIPszCCBimgAwIBAgIUKY0U4LzSGXOWSVm3m8GvG2433V4wCwYJYIZIAWUDBAMR
MCExHzAdBgNVBAMTFk1lcmlkaWFuIEFJIFBRIFJvb3QgQ0EwHhcNMjYxMDIxMTgy
NzI2WhcNMjYxMTIyMTgyNzU2WjAhMR8wHQYDVQQDExZNZXJpZGlhbiBBSSBQUSBS
b290IENBMIIFMjALBglghkgBZQMEAxEDggUhAO0wsgYuF30h06T/4+VKMI2GgL6O
XgM6tllldExM6WKftZuUJyZRuT7AO4k0wBP+rCTTvNFI1bEucBGYXfcYahZg0E2x
pbrzb1E9QQ4s1piqDdtCW6CGpQtab23HN2Kwlvnhnb8GI4nj3QuuI5suATSFVYqI
qW2w4+tmhN7yqiVfehJLPmkI6K7+xTp1ILt+vL8uSoZOJGJA8N6PEtEa7C7aHSTI
... (the certificate continues for several kilobytes)
-----END CERTIFICATE-----
expiration       1795372076
issuer_id        2b3539a7-87dd-d0ec-a71b-dbe974869eb7
issuer_name      meridian-ai-pq-root
issuing_ca       -----BEGIN CERTIFICATE-----
... (the same certificate — this CA is self-signed)
-----END CERTIFICATE-----
key_id           6d5d5dca-fc13-4230-ffb3-d57cf54e1027
key_name         n/a
serial_number    29:8d:14:e0:bc:d2:19:73:96:49:59:b7:9b:c1:af:1b:6e:37:dd:5e
```

Two things to notice immediately:

- The certificate body starts `MIIPszCCBimgAwIBAgIU...` and the
  signature algorithm is OID **`2.16.840.1.101.3.4.3.17`** — NIST's
  `id-ml-dsa-44` (FIPS 204). It is not RSA and not ECDSA.

  > ⚠️ **Do not hand-decode the base64 to prove this.** I tried, and my
  > first attempt was wrong twice over. The fragment
  > `MCExHzAdBgNV` — which does appear in the certificate body —
  > decodes to `30 21 31 1f 30 1d 06 03 55`, which is
  > `SEQUENCE { SEQUENCE { OID 2.5.4.3 } }` — that is the **Subject
  > Name** (`CN = Meridian AI PQ Root CA`), not the key algorithm at all.
  > The real SPKI `AlgorithmIdentifier` sits at DER offset 37 and is
  > `30 0b 06 09 60 86 48 01 65 03 04 03 11` — `SEQUENCE(11) { OID }`
  > with the OID content `60 86 48 01 65 03 04 03 11`.
  >
  > **Use the tool that already knows how to read DER:**
  >
  > ```console
  > $ openssl x509 -in pq-root.pem -noout -text | head -14
  > Certificate:
  >     Data:
  >         Version: 3 (0x2)
  >         Serial Number:
  >             50:5c:3b:cc:e0:39:85:bc:0f:04:26:3e:ab:38:db:e0:dd:b3:18:3d
  >         Signature Algorithm: 2.16.840.1.101.3.4.3.17
  >         Issuer: CN = Meridian AI PQ Root CA
  >         Validity
  >             Not Before: Oct 21 18:53:17 2026 GMT
  >             Not After : Nov 22 18:53:47 2026 GMT
  >         Subject: CN = Meridian AI PQ Root CA
  >         Subject Public Key Info:
  >             Public Key Algorithm: 2.16.840.1.101.3.4.3.17
  >             Unable to load Public Key
  > ```
  >
  > `Unable to load Public Key` is expected: your OpenSSL is older than
  > FIPS 204 support. The **algorithm OID is still reported**, which is
  > the thing you care about.
- The certificate is **~4 KB**, against ~1 KB for the EC root in §4.2.
  That is the price of post-quantum signatures: bigger keys, bigger
  certificates, bigger TLS handshakes.

OpenSSL confirms it independently:

```console
$ openssl x509 -in pq-root.pem -noout -text | grep -E "Signature Algorithm|Public Key Algorithm"
        Signature Algorithm: 2.16.840.1.101.3.4.3.17
        Public Key Algorithm: 2.16.840.1.101.3.4.3.17
```

**Issuing a leaf with an ML-DSA key** works the same way as §4.6, and
returns exactly the same eight fields:

```console
$ bao write ai/pki-pq/roles/pq-leaf \
    allowed_domains="meridian-ai.internal" allow_subdomains=true \
    allow_bare_domains=false allow_any_name=false allow_localhost=false \
    enforce_hostnames=true max_ttl=72h ttl=24h \
    key_type=mldsa server_flag=true client_flag=true \
    key_usage="DigitalSignature" ext_key_usage="ServerAuth,ClientAuth" \
    require_cn=true issuer_ref="meridian-ai-pq-root"

$ bao write -format=json ai/pki-pq/issue/pq-leaf common_name="pq.meridian-ai.internal" ttl=24h
data keys: ['ca_chain','certificate','expiration','issuing_ca','not_before',
            'private_key','private_key_type','serial_number']
```

```console
$ openssl x509 -in pq-leaf.pem -noout -text | head -14
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            04:95:54:ff:c0:ec:1b:c4:e2:1c:cc:62:01:17:5f:ce:bf:04:ac:6b
        Signature Algorithm: 2.16.840.1.101.3.4.3.17
        Issuer: CN = Meridian AI PQ Root CA
        Validity
            Not Before: Oct 21 18:27:48 2026 GMT
            Not After : Oct 22 18:28:18 2026 GMT
        Subject: CN = pq.meridian-ai.internal
        Subject Public Key Info:
            Public Key Algorithm: 2.16.840.1.101.3.4.3.17
```

Note the leaf is **signed by the ML-DSA root** (its signature algorithm
is the PQC OID) and the leaf's own public key is ML-DSA too.

**Where the spelling is documented.** The live 2.7.1 server's own
OpenAPI specification lists the allowed key types, and `mldsa` is in
them:

```
PkiGenerateRootRequest              ['rsa', 'ec', 'ed25519', 'mldsa']
PkiGenerateInternalKeyRequest       ['rsa', 'ec', 'ed25519', 'mldsa']
PkiGenerateIntermediateRequest      ['rsa', 'ec', 'ed25519', 'mldsa']
PkiWriteRoleRequest                 ['rsa', 'ec', 'ed25519', 'mldsa', 'any']
PkiPatchRoleRequest                 ['rsa', 'ec', 'ed25519', 'mldsa', 'any']
PkiIssueWithRoleRequest             ['', 'rsa', 'ec', 'ed25519', 'mldsa']
PkiRotateRootRequest                ['rsa', 'ec', 'ed25519', 'mldsa']
... 7 more Pki* schemas with 'mldsa'
```

Read that list from the server rather than from a tutorial:

```bash
curl -s -H "X-Vault-Token: $BAO_TOKEN" \
  "$BAO_ADDR/v1/sys/internal/specs/openapi" \
  | jq -r '.components.schemas | to_entries[]
           | select(.value.properties.key_type.enum? // [] | index("mldsa"))
           | .key'
```

> ⚠️ **Do not "fix" the parameter by guessing the algorithm name.**
> `ml-dsa-44`, `ml_dsa_44` and `ML-DSA-44` are all rejected by the PKI
> engine. It takes **`key_type=mldsa`** and picks the level itself.

**Transit uses a different spelling, on purpose.** In the Transit engine
the key type *is* the algorithm identifier, so there you say the level
explicitly:

```console
$ bao write ai/transit/keys/meridian-pq-signing type=mldsa-44
Key                       Value
---                       -----
allow_plaintext_backup    false
auto_rotate_period        0s
deletion_allowed          false
derived                   false
exportable                false
imported_key              false
keys                      map[1:map[certificate_chain: creation_time:2026-10-21T18:30:40.873101364Z name:mldsa-44 public_key:jgrl+piw7mXNzDbiGFUdcmbqJylsA8i9jsJ72h+dSVn2KrzupKPDt393SqIoU40BFs1Cky41/WoXh8t1e61XhQ2rxVasbxvTc01Qxnrr+RrHbO3yMFy+7kYF4Hux0WL0amR14Y7qvOPqwqLtAA+KUej4UZs/8HleAOyzbQsrl80h6j02W/WWI5Y7YSioejIfTEmmFZ3yrtPfBxayyxuxoE0YquZhQjNCRd1S+JG0Jg6UN+fSEJBhWmxJ1o79midqzQBygXahntEgy8zIjA5O5ssfULHXa1n2402gMpQolDCS6FrPoQPOLETYg2kVnYww+uPWWNBD7yZcIMrxq13BFDOWg77a3lISpaxoHj+Ihgv0pO21CDCywP+EKvyTZsVg/vFp9JtTJHny5uw4LHEdAWdEKj/L46pUyJsczc7HmfPMWX10TiWhGojXp/5rpFV3Wgf5EZUBpPXsgJ4wGn3PinUCtJ7yQEHn42/gsXO8skoeT3vWQgKS4pcpIVcqIE3iAGVsAXwswwjvHTjJQtFeoR4vjEJaMXedWY8cba/i6zgxY6Jpiwb7oalbG/jI2Bmy2SiVVu24m6cdpdEV6UnGhCsHq9s019E0q3a1sbcQ37ZMBSo0hvSxAzUwlhLPvC/2KOnMBmhqKxuJScG/tsX7fbzt8O2u0eazEQTMmt6oHFXm30AELYe2UeYFU7AVIeIv0Ppy0cgdXNM6NQ/+ubxTcUv+oTAlYPeVPo+zoT01jsTXw5f4z2d8E/NqPRefpoNaikGNwnMVID7ukbiPZQNFBB8bdOSN87vxBFa62yj5h4eOGCoS2fVey+zONs5o28jnJ6oaM909HN6qUzXwsmZg1emVD+frZ+/eNDub/HpGnakSIaM8H0L2MF/f5c05w6FmqQ6UUMJupYSDEb0cSvzAON8MleYW0FAkjyGuwahQS+eabIFp8xElry3laMcTzqqNWn/GpslTo3n5SHM795wmp/cABmqvY9qNp5Cbj0wz31RHQ3/MlRV7I8sAkFqn68C3hcjGXYULScSGh9ynvWhkhxHL6/U1KD5rlONR7QMp4Zl9qExbrQfBcKBs4TskM8sOVkmMCiDq85jt/eE3fVs4gVIyexAicjyGxK4D5JnpRRK/2a+rDQJq38a0bYappp5OyvIVsiIzcdu1loOfKw2gzAOA4huSiVc20DSvwLEpmtLirI6tQMu1YmxAstEcGtAbE8Cz7mb7Rm/OS6Nx6GtEqsb0Vp4B4m1X+ft/z9bqp4YnibEJaRdAkxpPvR4yQFZ+7UzQGEVNPVFfw/59rbeMbc+qugT/2EHkU/FriWZVFsQHzvgHwvIJ+k26mqFuP5EaKIFX5PF7aEdkfTEVGflbOJPX07jlhjcnma9O5f2m4QdoWh03KwEmhZ3PBszEmjhMPqWIU2pAmdLvUaWTzyErd0RdCW4BZs1UPbGq7LNJ8RTu/X7KBOmgBPvm2d7Q2n22UZ3pZoh6DsRgj4+pYfekHPO2VFR1QekbOdm3J6HuF602cbs44LxBDSu5gx5DlRr+2v5xZZrA25r0v496gwSrrYcvkvNwVqM+djmvQtNCmjcfHFTyEUCcaic6WHLVbPJFN66d6nh0FPBRlGIdlwi6fx6dTg8J63uXa1MsLI/uHGJfwr/XDoU3ltQSuqKGndAMgq23veTs2xEXzOhNTkPfXO2/HT2Zzat/nI7KYMdnLA2qU9Xmj8M1rYRP6DqjDiTWrFXuWYM4CIWrSG2TEkhfPQ==]]
latest_version            1
min_available_version     0
min_decryption_version    1
min_encryption_version    0
name                      meridian-pq-signing
soft_deleted              false
supports_decryption       false
supports_derivation       false
supports_encryption       false
supports_signing          true
type                      mldsa-44
```

And it signs:

```console
$ bao write ai/transit/sign/meridian-pq-signing \
    input="$(echo -n 'meridian-ai post-quantum release' | base64 -w0)" \
    hash_algorithm=sha2-256 marshaling_algorithm=asn1
Key            Value
---            -----
key_version    1
signature      vault:v1:bCMUEbMahTsgADnbCxDtFXeoZDndqI6m/EZOxgo2xeAENKeG8Mj4PIkTeDUTXJ3wYlW4D0sjr8nS950VV4Pg/+380cUpXkP6kvfKhKW9qYz3BEhUpIsz6Fg671drqkE92lG996Q0VdR4wi6jgLcqbSb0v8sw723JKGRB2mVu0uQ5Y2NCTnqiXu5Wd9KLqksPoFLRGzjJ/MQVTdYZFGx3rSkXKxWYqypthXsYtr4QyzLpzP2f/Y8q6W3Yr6yHTVAv53eQ0pezdwzn+Y6W+h2mn35Us4RATw4jGd1R47h2GESiGGzxgabLZDakpCaH8EAEeGWi2W3wMwr6E57/UIRZTaQcypuE8JFtuoDWWoYrK2ExVMxcIOU9Y2M+Wl+H8GSwtfLzp4mG9sHwTHV0P5GVsNFmnskPS2uUYddztO0HbuIMoZr9Zn7ZoxlM9W+Nr4I5FbJ0uioWUmFfRzHJ7ZyAxM90ukPYYGg+pU4eE+7DYLUbYvuYmZe/edK7ZhYyt5l8qhcAe1U6vMePqzLmsifY5BNLt15HXzzd8p7hbyPPoq9m22hlknAyIxVcDE9oGZu6obMNL1nOmpGcHTRaAQs85LT1bhtFWtbLohBr5agZFDjKnRJRycVFbfxYMs927jIYPtqO77nQQahd6XQCeRDbwyiOsQNQx7DhTSi7kHqBPFlgUv/Nxq6ZvOzb3X3OiOCI62SP30kZHJH8Pqzl0tJjhyb3AKMkZKnh+j2+VhPAtCMoUl+1y5S7y31CbN/8wNY8IW7qvfQ6yIVB24eOOhxdpHzMRlo+BTFDkhkGVDFl/xHfxdAg+5aheKascM2tsQJsZVdNwTndM+piZ7N45vK/jR5rww4Gr6B5xHZBGN8UIvGoeWIZ5oh3kjmRbTa+pjksspZnpTsWJ6Wm//a03XIscj9A8Qt8wN2/+ifGZcM8Yiz60YildJHmq0oNHz318DmNfsmQC/f7omzI9qnjNN8PvLrNDpkEPgbOJe+GlsV1KufsZ3qxFdrDoTO/ZIEc3AYfagCWIMEmncj+cCHHbB2uYd73A7vHn7YR8mK4rKa11UegpTTii2w8qi7lOqmsGdCN2t5I+eYLaYFaTwiqVtxle0Vh9ihBiZGRMxVsicK9Uw254SqPlWwiD/PAVGN2YcJWz2586vshe/gJCRGiOURz8V082NqWzaKsprm+3ahwyJKfOuGJGiXjCsm1pxxk7kz99+8SWPhUrbYNDMj4YYOxozoygEZHaRdupdwRonBgGoxokoIaBSVVNz5Ni4w3joGjGp/8SG5VfhN3yMMl/eNQSDnl3N14Sp6/OtYhOe+gGzHcbcnGgN30+pFwlvOe77NlLgAosa2UdHH6qupZKTJno4yTGsCrPK/00jmvI9xfN77BXq1wk46GM/rJHpzMcexMvzl64uBRc1TKPKwH7VulkcdqlgObcgY+L767Nzg1yRC//67SOLovnb3o631bYgsEJ/XiKw7i38UC0+6grHYuFZvBey786Ok5Y2JyKnsmnlR+NZjyIMLLc0EB/z8riiv2JTqXoSRP5NOhbd+MZtL4s8huQAsY59wnSxSD0Khdln2J58Mldv7owzp+cr8DFwR+7bV1kRrj7zU7wAfQOG/9ZcXWOpQNS5nxmmneOiogMD+nwvLmoI/ypzBIbckeGEVDdqQDsXuEsnngoGZ0Ro8A+PeIHjF3xsmT3//HFH5FgI7ewTVo8NjSBF8nw8Fv7pm8pP59poiynBwpp2oNUxuAegegi74M+e4aB1XRLXrEh0DwneUZTt2i8ilCenLDIl9QU3f8slYOECw3K4OQZGvrhaxkQm543icOQU2gxaMad+P3y1fQY814j72iwFKCgmDNyfSCjiaIl82d9hW/O6OzGZxlAjsuiAFaP4sK+ckdvZLFtYWp8cq/ofTLgQ8WrQ83XmmnbdVag5PiCzMjccyHH/7heef8/w23RJZo5mz5s523qmYqrra//pcVaN/prlmbai5oLx65/2m2KmWRIxUD6wi7dB+0XneQHqnsa3CBFBfB+4030ZhIW1iTLb7JKGn9IJ78mQyxRE+xRXhau1MLfftHMHVqXf6x7WvQNRoUthioUO9eV+Xpv7zQO3UsEoRbcSAt9+o3ZFX012gU9zaUtsnR02gZa/OO+E9eiN3v3cvK3VQVpefDFC4WZrb8OKS9lIOTS75GnRMFG3OCToQIu5T+dvQClBlwEHM8V0eWzU9vkTWFcfe9ycUCj0Qg2J7knEZodY1zN5MvDHYNU0XNdjF3XoCqYnLNVu76bUFZxOyg89EsWfoGFyb7f+8hupkp3IgStkJwtDzLNkZdjXCvNsvUE8XtNomvnP4HTilyzaGHTIqTaAvU3TmOxUK2zhkBG8YCnhPdwN7xy/hkVSzuuKWKkpuuLPv5Q3TpstJuqg3cQ/3WqmqnwRH0I/rKIifQUWrgZoJI+mAS+yTA/su/moJLcsOvJ5B21SYFsTs8HVDSk4BY7bz54teNhvtDb+X9fThzmjfTtLduWt3l+uJ9ORxoGJSQFmyuOB3R0L8lXB4vhA+pr4CyCfEWl+u2cgRGOL30/cjpkk9Q4FUZF3UMzWnvo9+6o+520iiQoGVsMOBRce2q2ylC7OdpnfIlT9acDpQHM6BUBg9xUco5LAMjyNsNS2Mme4fhRVRsSI55WL+cc1stcZvCEnI1ELT5DOE/IiCmmY/WKSeAtKS4cA0YN10keQkFatv/IYUBAOi96Str+CvWce7PXZHSsPjk/nP6PaSVfHutWPBwikSd3JopKWTdr7/XV+T+suttCcnF41h5hSA8GqXFntOXSV95IRpZwGhyziv1bpyNPIVcve1D1iinmr5Lnjgqm1m6ONL2fCVi3C6QZCi6wCgr8XGpMRt6RlU3PYM5PqvuvTPi+TQHMPHF5wdnrDY+SmDiTVrtiYNdjCtkT6mxXN4a98aaM57Scb1MhcOdZnpKzij7VjPYZPD8NK7Cnk+BC9JZqea+xRduYzdYhKFhmaoqHlneKjxi7ZrmtLTNOTEUx+Jgp90PXeDnpg7FDM6SSw/9PdRvsWTuC9jJ+Joy9wdxCzJGWUm2vbwWFyuCCWUjSH5JdyX2f2AOBtfMRjMGyYGDk/sJ7l4CJS06bHWHkJ3H1dnt/wIFJi9kaXR3eIyi0u3v/QYJCyA1TlRYY2iCpcfO5QwPHyYoMDpGWW56v/QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4dLDk=
```

So the two engines really do use different spellings:

| Engine | Parameter | Value | Level |
|---|---|---|---|
| **PKI** | `key_type` | `mldsa` | chosen by OpenBao (ML-DSA-44) |
| **Transit** | `type` | `mldsa-44` | you name the level explicitly |

> **Trade-off:** *Post-quantum key types are **newer, larger, and less
> widely supported**. An ML-DSA certificate will not validate against
> most client libraries yet, and the whole chain has to agree. The
> correct 2026 strategy is not "switch to PQC" but "keep TLS 1.3 with
> X25519 for now, and make sure your CA can issue both when the clients
> are ready". Module 09 covers the TLS configuration where this decision
> gets made.*

### 4.10 External Keys (new in 2.7)

> **What are External Keys?** A way for PKI and Transit to sign with key
> material that lives in an **HSM or KMS** and **never enters OpenBao's
> memory**. OpenBao sends the digest to be signed to the external signer
> and gets the signature back.

The security argument is the whole point of an HSM: if the private key
never exists outside the tamper-resistant hardware, then compromising the
OpenBao process does not yield the key. In a normal OpenBao setup, the
CA private key is stored (encrypted at rest) in OpenBao's own storage —
and a full compromise of OpenBao yields it.

**What I verified.** The External Keys API exists in the live 2.7.1
server. From the server's own OpenAPI specification:

```
/sys/external-keys/configs
/sys/external-keys/configs/{config}
/sys/external-keys/configs/{config}/keys
/sys/external-keys/configs/{config}/keys/{key}
/sys/external-keys/configs/{config}/keys/{key}/grants
/sys/external-keys/configs/{config}/keys/{key}/grants/{mount}
```

The shape is legible: you register a **config** (the HSM/KMS connection),
that config holds **keys**, and each key has **grants** that say which
mounts (PKI, Transit) are allowed to use it.

**What I could not verify.** The endpoints are present but empty on a
stock server — there is no HSM in this lab:

```console
$ bao list -format=json sys/external-keys/configs
{}

$ bao read sys/external-keys/configs
Error reading sys/external-keys/configs: Error making API request.

URL: GET http://127.0.0.1:9158/v1/sys/external-keys/configs
Code: 405. Errors:

* 1 error occurred:
	* unsupported operation
```

(The 405 on `GET` is expected: `/sys/external-keys/configs` is a
collection endpoint that is written and listed, not read as a single
object. `bao list` on it is the right verb, and it returns `{}` because
no HSM is registered.)

So: **the feature is present in 2.7.1 and its API shape is confirmed, but
I could not exercise a real signing flow without an HSM/KMS.** Do not
build a plan that assumes a specific plugin name or a specific
`external-keys` config schema without reading the 2.7 documentation for
your HSM.

> **Production:** *External Keys is the answer to "our compliance team
> says the CA key must be in a FIPS 140-3 Level 3 HSM". It is also the
> answer to "we are worried about a full OpenBao compromise". It is
> **not** free: you now depend on the HSM being reachable and fast, and
> on a KMS plugin being installed. Read `VERIFIED-FACTS.md` §6 — every
> KMS plugin is an *external* plugin in 2.7, so this is an install
> project, not a config toggle.*

---

## 5. The SSH engine

### 5.1 The core concept

> **What is the SSH secret engine?** It is an **SSH certificate
> authority**. Instead of managing a list of public keys in
> `authorized_keys` on every server, you manage a CA key in OpenBao. A
> developer keeps their own key pair forever, and OpenBao issues them a
> short-lived **certificate** that says "this key belongs to
> `aisha.rahman` until 03:00".

The old model versus the new one:

| | `authorized_keys` model | OpenBao SSH CA |
|---|---|---|
| Where the list lives | On every target host | One place, in OpenBao |
| Revoking one person | SSH to 40 hosts, edit 40 files | Revoke one role/lease |
| Audit | `auth.log` on the host, if logging is on | Every issuance in OpenBao's audit log, with the identity attached |
| Attributing a login | Which key matched which key? | The certificate **names** the principal |
| Key lifetime | Forever (until someone remembers) | Hours |

### 5.2 The 2.7 API changed — and this is a Vault-era trap

> ⚠️ **Changed in 2.7:** *the Vault-era endpoint
> `ssh/config/generate_signing_key` **does not exist** in OpenBao 2.7.1.
> The SSH engine now has a first-class **issuer** model, like PKI.*

```console
$ bao write ai/ssh/config/generate_signing_key=true
Must supply data or use -force

$ bao write -force ai/ssh/config/generate_signing_key=true
Error writing data to ai/ssh/config/generate_signing_key=true: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/ssh/config/generate_signing_key=true
Code: 404. Errors:
```

The complete list of SSH paths in the live 2.7.1 server's OpenAPI spec:

```
/ai/ssh/config/ca
/ai/ssh/config/issuers
/ai/ssh/config/zeroaddress
/ai/ssh/creds/{role}
/ai/ssh/issue/{role}
/ai/ssh/issuer/{issuer_ref}
/ai/ssh/issuer/{issuer_ref}/public_key
/ai/ssh/issuers
/ai/ssh/issuers/import
/ai/ssh/issuers/import/{issuer_name}
/ai/ssh/lookup
/ai/ssh/public_key
/ai/ssh/roles
/ai/ssh/roles/{role}
/ai/ssh/sign/{role}
/ai/ssh/tidy/dynamic-keys
/ai/ssh/verify
```

Note `/ai/ssh/config/ca` — **not** `generate_signing_key`. The engine
also gained `/ai/ssh/issuers/import` (bring your own CA key) and
`/ai/ssh/issuer/{issuer_ref}/public_key` (fetch the CA's public key to
put in `known_hosts`).

### 5.3 Generating the CA

```console
$ bao write ai/ssh/config/ca generate_signing_key=true key_type=ed25519 issuer_name=meridian-ssh-ca
Key            Value
---            -----
issuer_id      1a7456a6-318b-bd45-6d24-491ab9b5b7ef
issuer_name    n/a
public_key     ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPmkavTCzTrCPfVcdN8lcahsVl1YEdgEtfCo3xHTHvTR
```

The `public_key` is the value you put in every target's
`/etc/ssh/sshd_config`:

```
TrustedUserCAKeys /etc/ssh/meridian-ca.pub
```

and the `issuer_id` identifies the CA for roles that want to pin a
specific one.

> **Note the `issuer_name: n/a`.** The `issuer_name` parameter was
> accepted but the response does not reflect it; the same thing happened
> with the PKI intermediate. Names have to be set explicitly afterwards
> via the issuer endpoint. This is consistent with the PKI engine and is
> not a lab artifact.

### 5.4 The role

```console
$ bao write ai/ssh/roles/meridian-engineer \
  key_type=ca \
  default_user=meridian \
  allow_user_certificates=true \
  allow_host_certificates=false \
  allow_bare_domains=false \
  allow_user_key_ids=false \
  allowed_users="aisha.rahman,dev.kapoor" \
  default_extensions="permit-pty=,permit-agent-forwarding=" \
  ttl=8h max_ttl=24h
```

That fails:

```console
Error writing data to ai/ssh/roles/meridian-engineer: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/ssh/roles/meridian-engineer
Code: 400. Errors:

* Field validation failed: error converting input for field "default_extensions": '' expected type 'map[string]interface {}', got unconvertible type 'string'
```

`default_extensions` is a **map**, and OpenBao 2.7.1's field validation is
strict: a string will not be coerced into a map, not even the
`permit-pty=,permit-agent-forwarding=` form that worked in older
tooling. The CLI's `key=value` syntax always produces strings, so the
only way to send a map from the CLI is a **JSON request body**:

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
    -d '{
          "key_type":"ca",
          "default_user":"meridian",
          "allow_user_certificates":true,
          "allow_host_certificates":false,
          "allow_bare_domains":false,
          "allow_user_key_ids":false,
          "allowed_users":"aisha.rahman,dev.kapoor",
          "default_extensions":{"permit-pty":"","permit-agent-forwarding":""},
          "ttl":"8h",
          "max_ttl":"24h"
        }' \
    "$BAO_ADDR/v1/ai/ssh/roles/meridian-engineer"
```

Reading it back:

```console
$ curl -s -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/ai/ssh/roles/meridian-engineer" | jq '.data | {key_type,default_user,allow_user_certificates,allowed_users,default_extensions,ttl,max_ttl}'
{
  "key_type": "ca",
  "default_user": "meridian",
  "allow_user_certificates": true,
  "allowed_users": "aisha.rahman,dev.kapoor",
  "default_extensions": {
    "permit-agent-forwarding": "",
    "permit-pty": ""
  },
  "ttl": 28800,
  "max_ttl": 86400
}
```

Note `ttl` came back as `28800` (seconds) even though you sent `"8h"`.
The SSH engine returns raw seconds; the PKI engine returns a Go duration
string. Read the field, do not assume the format.

### 5.5 Signing a user certificate

First, the developer's own key pair. This is the point of the whole
design — **the developer's private key never changes and never leaves
their laptop**:

```console
$ ssh-keygen -t ed25519 -f aisha -N "" -C "aisha.rahman@meridian-ai"
$ cat aisha.pub
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINlMqyr/dFv4BjkDWhTO1UoTFJgCBvC0H85Kg+esmlZx aisha.rahman@meridian-ai
```

Now sign it:

```console
$ bao write ai/ssh/sign/meridian-engineer \
  public_key=@aisha.pub valid_principals="aisha.rahman" ttl=8h
```

```console
Key              Value
---              -----
issuer_id        1a7456a6-318b-bd45-6d24-491ab9b5b7ef
serial_number    ab4e8ccca1daddb2
signed_key       ssh-ed25519-cert-v01@openssh.com AAAAIHNzaC1lZDI1NTE5LWNlcnQtdjAxQG9wZW5zc2guY29tAAAAIISitUT6AmOD1OsOITbnGjFG2whBbPH9ao+G3EaanK0SAAAAINlMqyr/dFv4BjkDWhTO1UoTFJgCBvC0H85Kg+esmlZxq06MzKHa3bIAAAABAAAAS3ZhdWx0LXJvb3QtNTE5NTAwMzBhMjVjNTRjNmViOTMwMGYzNjg4NGYxNDhiOWMwMDNjMzFmZDM5OWQ0NmI5ODRhMGIyN2VmZDdlYQAAABAAAAAMYWlzaGEucmFobWFuAAAAAGrY/lUAAAAAatlu8wAAAAAAAAAxAAAAF3Blcm1pdC1hZ2VudC1mb3J3YXJkaW5nAAAAAAAAAApwZXJtaXQtcHR5AAAAAAAAAAAAAAAzAAAAC3NzaC1lZDI1NTE5AAAAIPmkavTCzTrCPfVcdN8lcahsVl1YEdgEtfCo3xHTHvTRAAAAUwAAAAtzc2gtZWQyNTUxOQAAAEB+357p5crCO6dtLAhwHJTshzPv+xCDEZCi+iQiFpKQ+VaDUhItgOBA7Quuz22V/PM6l66bmjZvSpCvlQ657D0J
```

Three fields:

| Field | What it is |
|---|---|
| `signed_key` | The **SSH certificate**. `ssh-ed25519-cert-v01@openssh.com` — that prefix is what `ssh` recognises as a cert, not a plain key. |
| `serial_number` | The cert's serial, for revocation. |
| `issuer_id` | Which CA signed it. |

Inside that base64 blob, decode it and you will find the OpenSSH cert
format: the key ID, the valid principals (`aisha.rahman`), the validity
window, and the **extensions** — `permit-agent-forwarding` and
`permit-pty` — exactly the ones you set in the role.

### 5.6 Using it

On the developer's laptop:

```bash
# 1. ask OpenBao for a certificate (this is the only time you talk to OpenBao)
bao read -format=json ssh/sign/meridian-engineer \
  public_key=@~/.ssh/aisha.pub valid_principals="aisha.rahman" \
  | jq -r '.data.signed_key' > ~/.ssh/aisha-cert.pub

# 2. use it like a key
ssh -i ~/.ssh/aisha -o CertificateFile=~/.ssh/aisha-cert.pub meridian@bastion.meridian-ai.internal
```

On the target host, one line of config:

```
TrustedUserCAKeys /etc/ssh/meridian-ca.pub
```

and nothing else. No `authorized_keys` entries per person, ever.

> **Production:** *Two settings decide how useful this is:
> `allowed_users="aisha.rahman,dev.kapoor"` restricts **which
> principals** this role can sign for — without it, any authenticated
> OpenBao user could get a certificate for any username on any host.
> And `ttl` should be **hours, not days**: 8 hours covers a working
> day; a week-long certificate is a static credential with extra steps.*
>
> **Trade-off:** *the developer needs a way to authenticate to OpenBao
> before they can get a certificate, and OpenBao's `cert` auth method
> can accept an X.509 certificate for exactly that — a chain of trust:
> corporate CA → developer X.509 → OpenBao token → SSH certificate. Set
> `default_user=meridian` so the certificate's principal is the account,
> and map OpenBao **entities** to SSH principals with
> `allowed_users_template`.*

---

## 6. The TOTP engine

### 6.1 The core concept

> **What is the TOTP engine?** It stores the shared secret behind an
> authenticator app (Google Authenticator, 1Password, Bitwarden) and
> computes the 6-digit codes server-side.

TOTP is RFC 6238: `HMAC(secret, floor(time/30))` truncated to 6 digits.
The device and the server share a secret and both compute the same code.
The value of putting the secret in OpenBao rather than in a database
table is the same as always: it is encrypted at rest, it is in the audit
log when read, and it is revocable per-user.

### 6.2 Creating a key

The engine does **not** generate the secret for you — you must supply
it:

```console
$ bao write ai/totp/keys/aisha.rahman type=otp key="$SECRET" key_size=32 issuer=meridian-ai account_name=aisha.rahman period=30 digits=6
Success! Data written to: ai/totp/keys/aisha.rahman
```

If you forget the key:

```console
$ bao write ai/totp/keys/aisha.rahman type=otp key_size=32 issuer=meridian-ai
Error writing data to ai/totp/keys/aisha.rahman: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/totp/keys/aisha.rahman
Code: 400. Errors:

* the key value is required
```

Generating a valid base32 secret (the format every authenticator app
expects):

```bash
head -c 20 /dev/urandom | base32 | tr -d '='
```

Reading it back:

```console
$ bao read ai/totp/keys/aisha.rahman
Key             Value
---             -----
account_name    aisha.rahman
algorithm       SHA1
digits          6
issuer          meridian-ai
period          30s
```

> ⚠️ **Notice what is not there: the secret itself.** Reading the key
> object back gives you the *metadata* only. That is deliberate — the
> shared secret never round-trips through a read. To enroll a user you
> read the key **once at creation** and hand the secret to the user
> out of band.

### 6.3 Generating a code

```console
$ bao read ai/totp/code/aisha.rahman
Key            Value
---            -----
code           780238
expire_time    1792605840
generated      1792605822
period         30s
```

`generated` and `expire_time` are 18 seconds apart — the code is valid
until the end of the current 30-second window. Add a small clock-skew
allowance (one period either side) when validating, which is what every
authenticator implementation does.

> **Production:** *The TOTP engine exists so that a **server** can
> validate a second factor — for example, a bastion host that asks for
> a TOTP in addition to an SSH certificate, or an internal admin panel
> that requires it. If the *only* thing validating the code is the
> device, you do not need the engine; you need a `userpass` or `oidc`
> backend that does MFA. Use the TOTP engine when the *server* is the
> party that must check the code.*

> **Trade-off:** *TOTP is a **shared secret**. It is phishable — a
> convincing phishing page relays the code. The stronger choice is
> **WebAuthn/FIDO2**, which OpenBao does not implement as a built-in auth
> method. For Meridian AI, keep TOTP as the fallback second factor and
> plan for passkeys via an OIDC provider (Keycloak supports them)
> later.*

---

## 7. The transit engine

### 7.1 The core concept

> **What is the transit engine?** It is **encryption as a service**.
> You send it plaintext, it returns ciphertext, and the key never leaves
> OpenBao.

This is the third different answer to "where does the key live":

| Approach | Where the key lives | Who can decrypt |
|---|---|---|
| Encrypt in the app | The app's memory | The app (and whoever compromises it) |
| Transit | OpenBao | Whoever calls OpenBao's decrypt endpoint |
| HSM-backed transit | An HSM | Whoever calls OpenBao, and the HSM's policy |

The Transit advantage is that **your application never handles key
material**. It asks "encrypt this" and "decrypt that" and stores
ciphertext. If the app is compromised, the attacker gets ciphertext and
the ability to *ask* OpenBao to decrypt — but the key itself is still
only in OpenBao, and the decrypt call is a separate, auditable event.

### 7.2 Creating a key

```console
$ bao write ai/transit/keys/meridian-data type=chacha20-poly1305 key_size=32 exportable=false allow_plaintext_backup=false
Error writing data to ai/transit/keys/meridian-data: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/transit/keys/meridian-data
Code: 400. Errors:

* key_size is not valid for algorithm chacha20-poly1305
```

`key_size` only applies to variable-length algorithms like AES. The
default — and what you get when you omit `type` — is `aes256-gcm96`:

```console
$ bao read ai/transit/keys/meridian-data
Key                       Value
---                       -----
allow_plaintext_backup    false
auto_rotate_period        0s
deletion_allowed          false
derived                   false
exportable                false
imported_key              false
keys                      map[1:1792605826]
latest_version            1
min_available_version     0
min_decryption_version    1
min_encryption_version    0
name                      meridian-data
soft_deleted              false
supports_decryption       true
supports_derivation       true
supports_encryption       true
supports_signing          false
type                      aes256-gcm96
```

The `keys map[1:1792605826]` line is the **version map**: version 1, created
at that timestamp. When you rotate, version 2 appears and both stay
usable — which is exactly what you want, because old ciphertext must
remain decryptable.

### 7.3 Encrypt and decrypt

```console
$ bao write ai/transit/encrypt/meridian-data \
    plaintext="$(echo -n 'AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr' | base64 -w0)"
Key            Value
---            -----
ciphertext    vault:v1:aJy0LgB2uLHQcLH0sxLNg/z4EvhRScsrosofL86Vs9iUGbTQODq0mYsvibxA9qp6e7LEW71rNIaePadLyASKqmCD
key_version   1
```

The ciphertext is **self-describing**: `vault:v1:` says "Vault-format
ciphertext, key version 1". That prefix is why transit ciphertext can
survive a key rotation — the decryptor reads the version out of the
ciphertext and uses the right key.

> **If you find a tutorial saying OpenBao transit ciphertext starts with
> `vault:v1:`:** *it is right for OpenBao, and it is the same format
> Vault uses. The `vault:` prefix is a *format marker*, not a brand
> statement — do not try to "clean it up" to `bao:v1:`, and do not let a
> linter rewrite it.*

### 7.4 Datakeys — the pattern you will actually use

A **datakey** is a fresh key generated on demand and handed to you
*twice*: once in plaintext (use it now, for one file or one TLS
connection) and once encrypted under the transit key (store it, use it
later).

```console
$ bao write -format=json ai/transit/datakey/plaintext/meridian-data bits=256
{
  "data": {
    "ciphertext": "vault:v1:VdSCsDMDyar/JXO3m8kkm4KNzFNfQilIWy+AvlExev+gyPVsnmIB2MLgKDsQTFRWRfNPWXyH/NnCOw8m",
    "key_version": 1,
    "plaintext": "IwV1Duipls3aQmXgGxm/LkZnKmukmCYFmHls5nqrGY0="
  }
}
```

The pattern:

1. App calls `datakey/plaintext/meridian-data`.
2. OpenBao generates a random 256-bit key.
3. It returns the key in plaintext **and** the key encrypted under
   `meridian-data`.
4. The app uses the plaintext key immediately (e.g. as a one-off
   database encryption key) and stores the *ciphertext* form.
5. Later, to read the data, the app sends the ciphertext back to
   `datakey/decrypt/meridian-data` and gets the key back.

**Why this beats storing the key yourself:** the data key never has to
live in your app's config, in your backups, or in your database. Only
the encrypted form does, and it is useless without OpenBao.

### 7.5 Signing and verification

Transit can also be your **code-signing** service. Sign with an
`ecdsa-p256` key:

```console
$ bao write ai/transit/keys/meridian-signing type=ecdsa-p256
Key                       Value
---                       -----
allow_plaintext_backup    false
auto_rotate_period        0s
deletion_allowed          false
derived                   false
exportable                false
imported_key              false
keys                      map[1:map[certificate_chain: creation_time:2026-10-21T18:03:53.406226644Z name:P-256 public_key:-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEd7Es9NlWYTuDfELNqwNiLTaXKl19
uN6Y2/MrUYv13CSeuuaFP1eJ7j2S1dLqPmzSf/ZqhQNrNw6vnmZqLT97OQ==
-----END PUBLIC KEY-----
]]
latest_version            1
min_available_version     0
min_decryption_version    1
min_encryption_version    0
name                      meridian-signing
soft_deleted              false
supports_decryption       false
supports_derivation       false
supports_encryption       false
supports_signing          true
type                      ecdsa-p256
```

`supports_signing: true` and `supports_encryption: false` — a signing key
cannot encrypt, by design. The reverse is also true, and it is a real
error you can hit:

```console
$ bao write ai/transit/sign/meridian-data \
    input="$(echo -n 'meridian-ai deployment 2026-10-21' | base64 -w0)" \
    hash_algorithm=sha2-256 marshaling_algorithm=asn1
Error writing data to ai/transit/sign/meridian-data: Error making API request.

URL: PUT http://127.0.0.1:9158/v1/ai/transit/sign/meridian-data
Code: 400. Errors:

* key type aes256-gcm96 does not support signing
```

Signing and verifying:

```console
$ bao write ai/transit/sign/meridian-signing \
    input="$(echo -n 'meridian-ai deployment 2026-10-21' | base64 -w0)" \
    hash_algorithm=sha2-256 marshaling_algorithm=asn1
Key            Value
---            -----
key_version    1
signature      vault:v1:MEUCIQD7Gfhagey8sA1b6MyAYvuz7j3BML9h31K+jPJ4fn5dewIgDcowtEj2s8QG+lnMqREvMNmnsrVH7D/W9lr2qmLub+8=

$ bao write ai/transit/verify/meridian-signing \
    input="$(echo -n 'meridian-ai deployment 2026-10-21' | base64 -w0)" \
    signature="vault:v1:MEUCIQD7Gfhagey8sA1b6MyAYvuz7j3BML9h31K+jPJ4fn5dewIgDcowtEj2s8QG+lnMqREvMNmnsrVH7D/W9lr2qmLub+8=" \
    hash_algorithm=sha2-256 marshaling_algorithm=asn1
Key      Value
---      -----
valid    true
```

> **Trade-off:** *Transit signing means the signing key never touches
> your build system. That is excellent for protecting a release key. But
> it also means **your CI needs network access to OpenBao** to sign
> anything, and OpenBao becomes a hard dependency of your deploy
> pipeline. For a low-volume internal pipeline, that is usually fine and
> worth it. For a high-volume public release pipeline, a dedicated
> signing service (or sigstore/cosign) may serve you better.*

### 7.6 Rotation

```console
$ bao write -force ai/transit/keys/meridian-data/rotate
Key                       Value
---                       -----
allow_plaintext_backup    false
auto_rotate_period        0s
deletion_allowed          false
derived                   false
exportable                false
imported_key              false
keys                      map[1:1792605826 2:1792605845]
latest_version            2
min_available_version     0
min_decryption_version    1
min_encryption_version    0
name                      meridian-data
soft_deleted              false
supports_decryption       true
supports_derivation       true
supports_encryption       true
supports_signing          false
type                      aes256-gcm96
```

`keys` now has two versions and `latest_version` is `2`. New encryptions
use version 2:

```console
$ bao write ai/transit/encrypt/meridian-data \
    plaintext="$(echo -n 'AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr' | base64 -w0)"
Key            Value
---            -----
ciphertext    vault:v2:Rde40RUXtZomB4Vvm7GKjNr4I8+40L4cDgpIAjvC5tBSXEEtwz4m5ukGlxKbqRmjD3yRVDaRyTZisLw6cwBc0SZj
key_version   2
```

Note the prefix moved from `vault:v1:` to `vault:v2:` — the version is
in the ciphertext, so old `vault:v1:` blobs still decrypt with the old
key. **That is the whole point of rotation**: you can rotate as often as
you like without re-encrypting anything.

> **CLI gotcha:** *`bao write ai/transit/keys/<name>/rotate` needs
> `-force` because the endpoint takes no data:*
>
> ```console
> $ bao write ai/transit/keys/meridian-data/rotate
> Must supply data or use -force
> ```

> **Production:** *set `auto_rotate_period` on the key so rotation is
> automatic, and keep `min_decryption_version` low enough that old
> ciphertext survives. The "how many old versions can I decrypt" knob
> is `min_decryption_version`; setting it to `0` means "I can decrypt
> everything ever encrypted with this key".*

---

## 8. Briefly: the kubernetes and rabbitmq engines

### `kubernetes` secret engine

Issues **service account tokens** for pods, with a short TTL and an
audience bound to the API server. The pod's application never handles a
long-lived token.

```bash
bao secrets enable -path=ai/kubernetes kubernetes
bao write ai/kubernetes/config \
  kubernetes_host=https://kubernetes.default.svc:443 \
  service_account_name=meridian-ai-harness \
  service_account_namespace=meridian-ai
```

This is the engine that makes "no long-lived cloud credentials in the
cluster" possible — the same idea as the database engine, applied to
Kubernetes.

### `rabbitmq` secret engine

Issues RabbitMQ **user credentials** with tagged permissions, and
revokes them on lease expiry. Same shape as the database engine:

```bash
bao secrets enable -path=ai/rabbitmq rabbitmq
bao write ai/rabbitmq/config/meridian \
  connection_url="amqp://{{username}}:{{password}}@rabbitmq:5672/" \
  username="meridian_vault_admin" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  verify_connection=true
```

> **Not verified in this module:** *the `kubernetes` and `rabbitmq`
> engines are **built in** (both appear in `bao plugin list` above), but
> this lab had neither a Kubernetes cluster nor a RabbitMQ broker, so no
> live issuance from either is shown here. The commands above follow the
> same config-then-role-then-creds shape as the database engine, which
> the 2.7.1 source confirms is shared across them. Verify the exact
> parameter names with `bao path-help ai/kubernetes/config` before you
> rely on them.*

---

## 9. The comparison table

| Engine | Secret type | Lifetime | Revocation | OpenBao sees the secret? | Meridian AI use |
|---|---|---|---|---|---|
| **kv-v2** | Arbitrary value | Until you rotate it | Manual (delete a version) | Yes (it is the store) | Gemini API key, Keycloak client secret |
| **database** | DB username + password | Lease (1h–24h typical) | Automatic: `DROP ROLE` on expiry, `sys/leases/revoke` for immediate | Only the *admin* password | `meridian_app` login for `ai-harness` |
| **pki** | X.509 certificate + key | Certificate `notAfter` (hours–days) | Serial-based revoke + CRL/OCSP | The CA private key | mTLS between services |
| **ssh** | SSH certificate | Lease (hours) | Automatic on expiry; revoke by serial | The CA private key | Engineer access to bastion hosts |
| **transit** | Ciphertext (+ key held by OpenBao) | Key version, rotated | Key rotation; old versions kept for decrypt | The key (never exported) | Encrypting data at rest; code signing |
| **totp** | 6-digit code (secret stored) | 30-second window | Delete the key | The shared secret | Second factor for internal admin tooling |
| **kubernetes** | Service account token | Minutes | Automatic on expiry | No (the CA signs it) | Pod identity |
| **rabbitmq** | AMQP username + password | Lease | Automatic on expiry | Only the admin password | Queue credentials |

**The one-line summary:** kv-v2 is the only row where the *value itself*
is the secret. Every other row is a **broker** — it hands out something
short-lived that it can take back.

---

## 10. Which engines does Meridian AI need, and when?

### 10.1 The recommendation

| Engine | Mount | When | Priority |
|---|---|---|---|
| **kv-v2** | `ai/platform` | **Now** | Already done in Module 02 |
| **database** | `ai/database` | **Now** — as soon as the `meridian_vault_admin` Postgres role exists | High |
| **transit** | `ai/transit` | **Now, lightly** — one key for encrypting the `data-pipeline`'s sensitive columns | Medium |
| **pki** | `ai/pki` | **Phase 2** — when you need mTLS between `ai-harness` and `data-pipeline` | Medium |
| **ssh** | `ai/ssh` | **Phase 2** — when you build the bastion/break-glass access path | Medium |
| **totp** | `ai/totp` | **Phase 2** — when there is a server-side MFA check to perform | Low |
| **kubernetes** | `ai/kubernetes` | **Phase 3** — when the platform runs on Kubernetes | Low |
| **rabbitmq** | `ai/rabbitmq` | **Only if** you add RabbitMQ. Skip otherwise | Very low |

### 10.2 Why this order

**`database` first.** It has the highest ratio of risk removed to work
done. The `meridian_ai` database holds embeddings, conversation history,
and tenant data. A leaked static password is catastrophic and lives
forever. The work is: create the `meridian_vault_admin` role with
`CREATEROLE`, write the config, write the role, and change
`ai-harness`'s startup to fetch a credential instead of reading an env
var. A day of work.

**`transit` second, but small.** The temptation is to encrypt
everything with transit. Resist that. Start with **one** key and
**one** job: the `data-pipeline` encrypts the tenant identifiers before
writing them to Postgres, and `ai-harness` decrypts on read. Everything
else stays in plain columns. Why? Because every field you encrypt is a
field you can no longer query, index, or join on — and transit
decryption is a network call per row if you are not careful. Encrypt
where you must, not everywhere.

**`pki` third.** It is the biggest win *and* the biggest piece of work.
The win: `ai-harness` and `data-pipeline` currently talk to each other
over plain HTTP inside the cluster. With mTLS, each service proves its
identity with a certificate that expires in 24 hours and is issued
without anybody touching a file. The work: a root CA, an intermediate,
roles, and — the part everyone underestimates — **getting the
`ca_chain` into both services' trust stores**. Budget a week, not an
afternoon.

**`ssh` fourth.** It matters the moment you need *break-glass* access:
the ability for `platform-admin` to get into a production host at 03:00
with an auditable, revocable identity. It does not matter if your team
is three people who already have SSH keys.

**`totp` fifth.** It is a tool for a specific job — a **server** that
must validate a second factor. If your only admin surface is the OpenBao
GUI itself, and Keycloak already handles MFA for the humans, then the
TOTP engine is redundant. Add it when you build the bastion host.

**`kubernetes` and `rabbitmq` last, and only on demand.** They are both
"right answer, wrong question" for a Docker-Compose-based Meridian AI.
Do not enable an engine because you can.

### 10.3 The static-to-dynamic migration, in order

Do not switch everything at once. This is the order that keeps the
service running:

1. **Stand up the engine** alongside the existing static secret. Both
   work. Nothing is broken.
2. **Grant the least privilege you can**, and revoke the *old* grant on
   the same day. A dynamic role with `SELECT` on everything is a dynamic
   secret with static-secret problems.
3. **Change one consumer** — `data-pipeline` first, because it is the
   least user-facing and the easiest to roll back.
4. **Watch `sys/leases/count`** for a week. You want to see the count
   rise to roughly "one per replica" and then stay flat. A count that
   climbs without bound means something is leaking connections and not
   caching the credential.
5. **Delete the static secret** from KV v2 and from every `.env`. Do not
   skip this step. A static secret that still exists is a static secret
   that will still be used.

> **Production:** *step 5 is the one that gets skipped, and skipping it
> means you have built a whole dynamic-credential system and changed
> nothing. Set a calendar reminder. Better: put a *policy* in place that
> forbids reading `ai/platform/db/postgres` once the dynamic path is
> live. OpenBao's ACL policies can deny a path outright — a policy with
> `deny` on the old secret path is a hard guarantee, not a
> convention.*

---

## 11. The GUI for this module

Open <http://127.0.0.1:8200/ui> and log in with your root token.

| GUI | CLI equivalent |
|---|---|
| **Secrets** → *Enable Engine* → type `PKI` | `bao secrets enable -path=ai/pki pki` |
| **Secrets** → `ai/pki` → **Generate** → *Root Certificate* (the page title; the button text is composed at runtime, so it is not a literal bundle string) | `bao write ai/pki/root/generate/internal ...` |
| **Secrets** → `ai/pki` → **CA Chain** / **Issuers** → *Issuer operations* | `bao read ai/pki/issuer/<issuer_id>` |
| **Secrets** → `ai/pki` → **Roles** → *Create Role* | `bao write ai/pki/roles/<role> ...` |
| **Secrets** → `ai/pki` → **Generate certificate** | `bao write ai/pki/issue/<role> ...` |
| **Secrets** → `ai/pki` → **Configure PKI** | `bao write ai/pki/config/urls ...` |
| **Secrets** → `ai/transit` → *Create encryption key* / **Adding an encryption key** | `bao write ai/transit/keys/<name> ...` |
| **Secrets** → `ai/transit` → **Rotate** | `bao write -force ai/transit/keys/<name>/rotate` |
| **Secrets** → `ai/transit` → *Encrypt* / *Decrypt* | `bao write ai/transit/encrypt/<name> plaintext=...` |
| **Secrets** → `ai/ssh` → *Create Role* | `bao write ai/ssh/roles/<role> ...` |
| **Secrets** → `ai/database` → **Database** → *Connect a database* | `bao write ai/database/config/<name> ...` |
| **Secrets** → `ai/database` → **Database plugin** → *Database type unavailable* | — |
| **Secrets** → `ai/totp` → **TOTP** → *Key Type* | `bao write ai/totp/keys/<name> type=otp key=...` |

The menu labels above are the **actual strings in the OpenBao 2.7.1 UI
bundle** — extracted from the served JavaScript, not guessed. This is how
you check, and this is what it prints on a live 2.7.1 server:

```console
$ curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
assets/chunk.475.0d3d12c9247a2b3e141f.js
assets/chunk.524.db8024bf66127c1bac18.js
assets/engine-vendor.js
assets/engine.js
assets/vault.js
assets/vendor.js

$ cd /tmp/uichunks && for f in $(curl -s http://127.0.0.1:8200/ui/ \
    | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
    curl -s "http://127.0.0.1:8200/ui/$f" -o "$(basename $f)"; done

$ for L in "Enable Engine" "Create Role" "Configure PKI" "Rotate" "Encrypt" \
           "Decrypt" "Connect a database" "Database type unavailable" "Key Type" \
           "Copy your generated key" "Copy your signature" "Copy your wrapped key" \
           "Adding an encryption key" "Create encryption key" "CA Chain" "Issuers" \
           "Issuer operations" "Generate certificate" "TOTP" "Database plugin" \
           "Root Certificate"; do
    printf "%-30s -> " "$L"; grep -c -F "$L" vault.js
  done
Enable Engine                  -> 2
Create Role                    -> 1
Configure PKI                  -> 0
Rotate                         -> 23
Encrypt                        -> 22
Decrypt                        -> 8
Connect a database             -> 2
Database type unavailable      -> 1
Key Type                       -> 1
Copy your generated key        -> 1
Copy your signature            -> 1
Copy your wrapped key          -> 1
Adding an encryption key       -> 1
Create encryption key          -> 2
CA Chain                       -> 2
Issuers                        -> 8
Issuer operations              -> 1
Generate certificate           -> 1
TOTP                           -> 11
Database plugin                -> 1
Root Certificate               -> 0
```

Two labels are **not** in `vault.js`:

- **`Configure PKI`** — it is in `vendor.js`, which is served as an
  asset of the same UI. It is a real label; it just lives in a different
  chunk.
- **`Root Certificate`** — zero hits in any chunk. The button text is
  composed at runtime, so it is not a literal bundle string. This is why
  the table above says "the page title; the button text is composed at
  runtime".

Things the GUI is good at: browsing issuers and roles, seeing certificates, and
copying a generated key ("Copy your generated key", "Copy your
signature", "Copy your wrapped key").

**Where the GUI is not enough — use the CLI for:**

- **Map-typed fields.** `default_extensions` on an SSH role cannot be set
  from the CLI's `key=value` syntax at all (see §5.4), and the GUI
  happens to send proper JSON. If you need a map field, the GUI may be
  the *only* convenient path — or use `curl`, as shown.
- **ACME.** The `path` cluster prerequisite is a PKI-mount setting
  (`ai/pki/config/cluster`); no GUI or server-config change will set it
  for you.
- **Anything you want to reproduce.** If it is not in Git as a `curl` or
  `bao` command, it is not auditable, and it will not survive your next
  rebuild.

> **Production:** *Treat the GUI as a **read tool** and the CLI as the
> **write tool**. Look at things in the GUI, change them in version
> control, apply them with the CLI. A configuration that exists only
> because someone clicked in a browser is a configuration that will be
> lost the next time you rebuild the lab.*

---

## 12. Failure-mode cheat sheet

Every error in this table was reproduced on the live server.

| Error | Meaning | Fix |
|---|---|---|
| `common name X not allowed by this role` | The role's `allowed_domains` / `allow_subdomains` does not cover X — **often because a partial role write reset the role** | Re-write the **whole** role |
| `failed to find entry for connection with name: "X"` | `db_name` does not match a config name | `db_name` = the name under `ai/database/config/` |
| `error verifying connection: ... dial tcp ...: connect: connection refused` | The DB is not reachable | Start it, or `verify_connection=false` for the config write |
| `cannot specify both connection_url and individual connection parameters` | Plugin schema mismatch (Redis) | Use `host`/`port`/`username`/`password` |
| `host cannot be empty` | `url=` is not a Redis-plugin field | Use individual fields |
| `unknown key type ml-dsa-44` | PKI wants `key_type=mldsa` (no hyphen, no level). Transit wants `type=mldsa-44` | Use `mldsa` for PKI, `mldsa-44` for Transit |
| `response returned from Conn: ERR Error in ACL SETUSER modifier` | You added `creation_statements` to a **Redis** role — the plugin does not substitute the templates | Remove them; the plugin creates the ACL user itself |
| `invalid default_directory_policy: string ... not a valid Default Directory Policy` | `default_directory_policy` is a policy name, not a URL | `sign-verbatim` or `nonce-required` |
| `ACME feature requires local cluster 'path' field configuration to be set` | ACME needs the mount's cluster path | `bao write ai/pki/config/cluster path="https://<your-host>:8200"` |
| `specified issuer not allowed by ACME policy` (HTTP 500 from `/acme/directory`) | `allowed_issuers` does not contain the **default** issuer, and `/acme/directory` resolves the default issuer | Add the default issuer to `allowed_issuers`, or use `/ai/pki/issuer/<id>/acme/directory` |
| `invalid, non-URL path given to cluster: X` | The cluster path must be a full URL | `https://host:port`, not a bare name |
| `Unknown or unsupported field cluster` | You added a `cluster { path = ... }` stanza to the config file | Remove it — 2.7.1 has no such stanza; use `ai/pki/config/cluster` |
| `unsupported path` on `sys/config/cluster/path` | There is no such API in 2.7.1 | Use `ai/pki/config/cluster` |
| `unsupported path` on `sys/leases/revoke-prefix` | The prefix belongs in the **path**, not the body | `sys/leases/revoke-prefix/<prefix>` |
| `invalid lease` on `sys/leases/lookup` | The lease was revoked (or expired) | Expected after a revoke |
| `No value found at sys/leases/count` | The 2.7.1 count endpoint returns `{"errors":[]}` and the CLI cannot render it | Use the Prometheus metrics from Module 09 |
| `Error reading ai/pki/crl/pem: invalid character '-' in numeric literal` | The CRL is a raw document, not a Secret | `curl` it and save the bytes |
| `unsupported operation` on `PUT ai/pki/crl/rotate` | The rotate endpoint is a **GET** in 2.7 | `bao read ai/pki/crl/rotate` |
| `Must supply data or use -force` | The endpoint takes no body | Add `-force` |
| `Field validation failed: ... expected type 'map[string]interface {}'` | You sent a string where a map is required | Send a JSON body with `curl` |
| `Endpoint ignored these unrecognized parameters: [issuer_name]` | That endpoint does not accept that field | Set the name via the issuer endpoint afterwards |
| `the key value is required` (TOTP) | The TOTP engine does not generate secrets | Generate a base32 secret yourself |
| `unsupported path` for `ssh/config/generate_signing_key` | Vault-era endpoint, gone in 2.7 | `ai/ssh/config/ca` |
| `no value found at ai/pki/intermediate/csr` | The CSR is only in the generate response, not stored | Capture it from the response |
| `No value found at ai/pki/issuer` (list) | The list path is plural | `bao list ai/pki/issuers` |

---

## 13. What you learned

- [ ] The difference between a **static** secret and a **dynamic** one,
      and why a static secret's blast radius is "every copy, forever".
- [ ] What a **lease** is, and the three fields (`lease_id`,
      `lease_duration`, `renewable`) that prove a credential is dynamic.
- [ ] That `kv-v2` is the *only* engine in this module that stores the
      value itself — every other engine is a **broker**.
- [ ] The full 2.7.1 built-in plugin inventory, and which engines moved
      to external plugins.
- [ ] How to write a **database connection config** and what
      `verify_connection` does.
- [ ] That `db_name` on a database role is the **config name**, not the
      plugin type.
- [ ] How to write a role with `creation_statements` and
      `revocation_statements`, and what the Postgres SQL actually does.
- [ ] That the Postgres plugin and the Redis plugin have **different
      connection schemas**.
- [ ] What a real generated dynamic username and password look like
      (`v-root-meridian-GgiqISi7vwOUMMP9g4fu-1792607322`).
- [ ] That the Redis plugin's username has a **completely different
      shape** (`V_ROOT_MERIDIAN-AI-CACHE-REAL_...`), and that the shape is
      plugin-specific — build on the lease, not the name.
- [ ] That the Postgres plugin **substitutes** `{{name}}`/`{{password}}`
      in `creation_statements` but the Redis plugin **does not** — and
      that you should not add `creation_statements` to a Redis role at all.
- [ ] That Postgres has **no idea OpenBao exists**, and that
      `VALID UNTIL` is the belt-and-braces expiry.
- [ ] The PKI hierarchy: root → intermediate → leaf, and why the root
      stays offline.
- [ ] The seven field names a PKI issuance returns: `certificate`,
      `private_key`, `private_key_type`, `issuing_ca`, `ca_chain`,
      `serial_number`, `expiration`/`not_before`.
- [ ] That a **partial role write resets the whole role** — always
      write it in full.
- [ ] The `ai/pki/issuers` (plural) list path, and how to name an
      issuer.
- [ ] What ACME needs before it will turn on, and why cert-manager
      usually uses the CSI driver instead.
- [ ] The 2.7 SSH issuer API (`ai/ssh/config/ca`) and that
      `generate_signing_key` is gone.
- [ ] That `default_extensions` needs a JSON body, not CLI key=value.
- [ ] What a TOTP key needs that OpenBao will not generate for you.
- [ ] The lease API on 2.7: `sys/leases/lookup`, `renew`, `revoke`, and
      `revoke-prefix/{prefix}` — **the prefix goes in the path**.
- [ ] That `sys/leases/count` is a `GET` and does not render usefully
      on 2.7.1, so do not dashboard it yet.
- [ ] Transit: encrypt, datakey, sign, verify, and why rotation is
      free.
- [ ] The self-describing `vault:vN:` ciphertext prefix.
- [ ] That **ML-DSA is available on 2.7.1** and that PKI spells it
      `key_type=mldsa` while Transit spells it `type=mldsa-44`.
- [ ] Which engines Meridian AI needs **now**, which later, and which
      never.

---

## 14. What's next

[Module 09 — Production Hardening](../09-production-hardening/README.md)
takes the setup you have built and makes it survive contact with
production: real TLS on the cluster port, an off-host audit pipeline,
auto-unseal with the Transit seal (and what recovery keys mean when you
use it), Raft HA, backups, a container-hardening checklist, Prometheus
metrics, a GitHub Actions job that rotates and re-applies your
configuration, and an incident runbook for the three bad days — a leaked
credential, a lost unseal share, and a sealed cluster at 03:00.

---

## 15. Homework

1. **Prove the lease dies.** With the `ai/database` mount from this
   module, issue a credential from the Redis role, note the
   `lease_id`, then revoke it early with
   `bao write sys/leases/revoke lease_id="..."` and look the lease up
   again with `bao write sys/leases/lookup lease_id="..."`. Write down
   what changed and in which field. *Then* explain, in two sentences,
   what would have happened to the Redis ACL user if you had waited for
   the lease to expire instead.

2. **Break the PKI role on purpose.** Write the `ai-harness` role with
   `allow_any_name=true` and issue a certificate for
   `attacker.example.com`. Read the certificate. Then rewrite the role
   with `allow_any_name=false`, `allowed_domains=meridian-ai.internal`,
   and `allow_subdomains=true`, and try the same request again. Paste
   both errors. *Question:* which of the two role settings is the
   security control, and which one is the convenience control?

3. **Rotate a transit key and prove the old ciphertext still works.**
   Encrypt the string `meridian-ai` with `ai/transit/keys/meridian-data`.
   Rotate the key. Encrypt it again. Decrypt **both** ciphertexts. The
   first one should still decrypt — explain why, in terms of the
   `vault:vN:` prefix and the `keys` version map.

4. **Design the `meridian-ai-app` Postgres role properly.** Write the
   `creation_statements` for a role that:
   - can `SELECT` and `INSERT` on the `embeddings` table,
   - can `SELECT` on the `tenants` table but **not** `UPDATE` it,
   - cannot create other roles,
   - expires in one hour.

   Then answer: what happens to the `DROP ROLE` when the application
   has created a temporary table? What would you add to
   `revocation_statements` to make it work?

5. **Write the "which engine when" memo for Meridian AI.** One page.
   For each of `database`, `pki`, `ssh`, `transit`, `totp`,
   `kubernetes`: what specific Meridian AI problem does it solve, what
   does it cost to adopt (in engineer-days), and what is the *smallest*
   version of it that would still be worth doing? Be specific about
   `data-pipeline` and `ai-harness` — those are the two services that
   exist.

6. **The anti-pattern hunt.** Take the Meridian AI secrets inventory
   from Module 02 and classify every secret into one of three buckets:
   *must be dynamic*, *cannot be dynamic — schedule rotation*, and
   *does not belong in a secret store at all*. For the third bucket,
   explain what should replace it. (Hint: some of the answers are
   configuration, not secrets.)
