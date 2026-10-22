-- ─────────────────────────────────────────────────────────────
--  PostgreSQL init — creates the OpenBao admin account used for
--  dynamic credentials.
--
--  ⚠️  CREATEROLE is the minimum. Never grant SUPERUSER:
--      OpenBao needs to create roles, not to own the database.
--  ⚠️  The password here is a placeholder. Change it, or better,
--      let OpenBao manage it.
-- ─────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'openbao_admin') THEN
    CREATE ROLE openbao_admin WITH LOGIN PASSWORD 'CHANGE_ME_openbao_admin' CREATEROLE;
    RAISE NOTICE 'created role openbao_admin';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE appdb TO openbao_admin;

-- Allow OpenBao to create roles in this database
GRANT CREATEROLE TO openbao_admin;
