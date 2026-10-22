"""
FastAPI + OpenBao — production-shaped integration.

This mirrors Level 7, §7.3 of the course.

Rules encoded here:
  1. All OpenBao access goes through app/secrets.py — one place.
  2. Auth via AppRole; the token is renewed in a background task.
  3. Secrets are cached with a short TTL and never logged.
  4. Nothing secret is ever returned by an endpoint.
  5. Fail closed: if OpenBao is unreachable at boot, the app does not start.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

import hvac
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("harness")

BAO_ADDR = os.environ.get("BAO_ADDR", "https://openbao:8200")
BAO_CACERT = os.environ.get("BAO_CACERT")
ROLE_ID = os.environ.get("APPROLE_ROLE_ID", "")
SECRET_ID = os.environ.get("APPROLE_SECRET_ID", "")
SECRET_MOUNT = os.environ.get("SECRET_MOUNT", "secret")
SECRET_PATH = os.environ.get("SECRET_PATH", "myapp")
DB_MOUNT = os.environ.get("DB_MOUNT", "db")
DB_ROLE = os.environ.get("DB_ROLE", "app")
CACHE_TTL = float(os.environ.get("SECRET_CACHE_TTL", "300"))


class SecretManager:
    """Owns the OpenBao client, the token, and the secret cache."""

    def __init__(self) -> None:
        self.client = hvac.Client(url=BAO_ADDR, verify=BAO_CACERT, timeout=30)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ── authentication ───────────────────────────────────────────
    def login(self) -> None:
        if not ROLE_ID or not SECRET_ID:
            raise RuntimeError("APPROLE_ROLE_ID / APPROLE_SECRET_ID not set")
        resp = self.client.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
        self.client.token = resp["auth"]["client_token"]
        log.info("authenticated to OpenBao")

    def _renew(self) -> None:
        try:
            resp = self.client.auth.token.renew_self(
                token=self.client.token, increment="20m"
            )
            self.client.token = resp["auth"]["client_token"]
            log.info("renewed OpenBao token")
        except Exception:
            log.warning("renewal failed, re-authenticating")
            self.login()

    async def keepalive(self) -> None:
        while True:
            await asyncio.sleep(240)
            try:
                await asyncio.to_thread(self._renew)
            except Exception as exc:  # noqa: BLE001
                # Log the exception TYPE only — the payload can contain a token.
                log.error("openbao keepalive error: %s", type(exc).__name__)

    # ── secret access ────────────────────────────────────────────
    def get(self, path: str) -> dict[str, Any]:
        now = time.monotonic()
        hit = self._cache.get(path)
        if hit and hit[0] > now:
            return hit[1]
        resp = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=SECRET_MOUNT
        )
        data = resp["data"]["data"]
        self._cache[path] = (now + CACHE_TTL, data)
        return data

    def get_db_credentials(self) -> dict[str, Any]:
        """Dynamic database credentials — deliberately not cached long."""
        resp = self.client.secrets.database.read_creds(
            name=DB_ROLE, mount_point=DB_MOUNT
        )
        return resp["data"]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.client.revoke(self.client.token)


secrets = SecretManager()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        secrets.login()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"could not authenticate to OpenBao: {type(exc).__name__}"
        ) from exc

    task = asyncio.create_task(secrets.keepalive())
    try:
        yield
    finally:
        task.cancel()
        secrets.close()


app = FastAPI(title="AI Harness", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config-check")
def config_check() -> dict[str, Any]:
    """Prove the app can read its config — without leaking any of it."""
    cfg = secrets.get(SECRET_PATH)
    db = secrets.get_db_credentials()
    return {
        "db_host": cfg.get("db_host"),
        "db_port": cfg.get("db_port"),
        "llm_key_present": bool(cfg.get("llm_api_key")),
        "redis_host": cfg.get("redis_host"),
        "db_credential_issued": bool(db.get("username")),
        "db_lease_seconds": db.get("lease_duration"),
    }


@app.get("/audit-proof")
def audit_proof() -> dict[str, Any]:
    """
    Show that a request actually happened in the audit log.
    Useful while learning; harmless in production (it reveals no secrets).
    """
    return {
        "hint": "check the audit log for path secret/data/%s" % SECRET_PATH,
        "note": "the request you just made is recorded with your token accessor",
    }
