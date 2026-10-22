"""
Meridian AI harness - OpenBao client bootstrap.

This module is the heart of Module 07: it proves an application can pull
secrets from OpenBao at runtime with NO secret material on disk.

Design decisions (and why):

1.  AppRole, not a static token.
    A static token in an env var is just the .env file with extra steps.
    AppRole gives us a short-lived token (default 15m) that we fetch with a
    role_id + secret_id, so the blast radius of a leaked env var is minutes,
    not forever.

2.  Stdlib only - no third-party HTTP client.
    This module sits on the secret-fetching path, i.e. inside the trust
    boundary of "who can read my credentials". Every dependency there is
    supply-chain risk. urllib.request is in the standard library, is
    audited with CPython, and has no transitive dependency tree. The app's
    own business logic (FastAPI, LangChain) is not in this trust boundary
    in the same way, so it can use whatever it likes.

3.  Fail fast and loud.
    If OpenBao is unreachable we raise immediately. We NEVER fall back to a
    default value or an env var. A silent fallback to an empty API key means
    your app starts "fine" and then fails confusingly in production.

4.  Cache in memory, not on disk.
    The token lives in the process's memory. It is never written to a file.

5.  Re-auth on expiry.
    The token has a TTL. We track the lease and re-login before it expires.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class OpenBaoError(RuntimeError):
    """Raised when OpenBao cannot be reached or refuses an operation."""


@dataclass(frozen=True)
class SecretLease:
    """A secret plus the metadata OpenBao attached to it."""

    value: dict[str, Any]
    version: int
    created_time: str
    lease_id: str = ""
    lease_duration: int = 0
    renewable: bool = False

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "SecretLease":
        auth = data.get("auth", {})
        envelope = data.get("data", {}) or {}
        return cls(
            value=envelope.get("data", {}) or {},
            version=(envelope.get("metadata", {}) or {}).get("version", 0),
            created_time=(envelope.get("metadata", {}) or {}).get("created_time", ""),
            lease_id=data.get("lease_id", "") or "",
            lease_duration=data.get("lease_duration", 0) or 0,
            renewable=data.get("renewable", False),
        )


class OpenBaoClient:
    """Minimal, dependency-free OpenBao client for the Meridian AI harness.

    Deliberately built on urllib.request rather than hvc:
      - hvc pulls in a large dependency tree for what we need here.
      - Module 09 discusses when hvc's abstractions (HA retry, standby
        handling) are worth the dependency.
    """

    def __init__(
        self,
        addr: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        namespace: str | None = None,
        ca_cert: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.addr = (addr or os.getenv("BAO_ADDR", "http://127.0.0.1:8200")).rstrip("/")
        self.role_id = role_id or os.getenv("BAO_ROLE_ID", "")
        self.secret_id = secret_id or os.getenv("BAO_SECRET_ID", "")
        self.namespace = namespace or os.getenv("BAO_NAMESPACE", "") or None
        self.timeout = timeout

        self._token: str = ""
        self._token_expires_at: float = 0.0

        # TLS verification. In production you MUST point ca_cert at your
        # internal CA bundle. Never set verify=False.
        self._ssl_context: ssl.SSLContext | None = None
        if self.addr.startswith("https://"):
            self._ssl_context = ssl.create_default_context(cafile=ca_cert)

    # -- plumbing ------------------------------------------------------------

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {"X-Vault-Token": token if token is not None else self._token}
        if self.namespace:
            headers["X-Vault-Namespace"] = self.namespace
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated request against OpenBao."""
        url = f"{self.addr}/v1/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urlencode(params)}"

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(token),
            method=method,
        )
        if data is not None:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise OpenBaoError(
                f"OpenBao returned {exc.code} for {method} {path}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise OpenBaoError(
                f"Cannot reach OpenBao at {self.addr}: {exc}. "
                "Refusing to start - a secret-less fallback is not acceptable."
            ) from exc

        if not raw:
            return {}
        return json.loads(raw.decode())

    # -- authentication ------------------------------------------------------

    def login(self) -> str:
        """Authenticate via AppRole and cache the token.

        Raises OpenBaoError if credentials are missing. We deliberately do
        NOT accept a pre-set BAO_TOKEN here for production use: an
        environment-provided token is the .env pattern we are replacing.
        """
        if not self.role_id or not self.secret_id:
            raise OpenBaoError(
                "BAO_ROLE_ID and BAO_SECRET_ID are required for AppRole login. "
                "Refusing to start without credentials."
            )

        data = self._request(
            "POST",
            "auth/approle/login",
            token="",
            body={"role_id": self.role_id, "secret_id": self.secret_id},
        )
        auth = data.get("auth", {})
        self._token = auth.get("client_token", "")
        ttl = int(auth.get("lease_duration", 0))
        # Renew at 80% of TTL to leave headroom for slow requests.
        self._token_expires_at = time.time() + max(ttl * 0.8, 1)
        logger.info(
            "Authenticated to OpenBao via AppRole (ttl=%ss, policies=%s)",
            ttl,
            auth.get("policies"),
        )
        return self._token

    def _ensure_token(self) -> None:
        if not self._token or time.time() >= self._token_expires_at:
            self.login()

    # -- secrets -------------------------------------------------------------

    def read_secret(self, mount: str, key_path: str = "") -> SecretLease:
        """Read a KV v2 secret.

        IMPORTANT - KV v2's API layout is `<mount>/data/<key>`, NOT
        `<mount>/<key>/data`. The `bao kv` CLI hides this because it knows
        the mount; raw HTTP does not. Getting it wrong returns a confusing
        403 ("permission denied") because the policy grants
        `<mount>/data/<key>` and you asked for a path that does not exist.

        Example:
            read_secret("ai/platform", "llm/gemini")
            -> GET /v1/ai/platform/data/llm/gemini
        """
        self._ensure_token()
        api_path = f"{mount.rstrip('/')}/data"
        if key_path:
            api_path = f"{api_path}/{key_path.lstrip('/')}"
        data = self._request("GET", api_path)
        return SecretLease.from_response(data)

    def read_secret_version(self, mount: str, key_path: str, version: int) -> SecretLease:
        """Read a specific historical version of a KV v2 secret."""
        self._ensure_token()
        api_path = f"{mount.rstrip('/')}/data/{key_path.lstrip('/')}"
        data = self._request("GET", api_path, params={"version": version})
        return SecretLease.from_response(data)

    def list_secrets(self, mount: str, key_path: str = "") -> list[str]:
        """List secret names under a path (KV v2 metadata layer)."""
        self._ensure_token()
        api_path = f"{mount.rstrip('/')}/metadata"
        if key_path:
            api_path = f"{api_path}/{key_path.lstrip('/')}"
        data = self._request("GET", api_path)
        return list((data.get("data") or {}).get("keys", []) or [])

    def health(self) -> dict[str, Any]:
        """Unauthenticated health probe. Useful for container healthchecks."""
        req = urllib.request.Request(f"{self.addr}/v1/sys/health", method="GET")
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Health returns 429/472/473/501/503 for degraded states - those
            # are still valid JSON bodies, so parse them rather than raise.
            try:
                return json.loads(exc.read().decode())
            except Exception:
                return {"initialized": False, "sealed": True, "code": exc.code}
        except (urllib.error.URLError, OSError):
            return {"initialized": False, "sealed": True, "code": 0}


def get_gemini_credentials(client: OpenBaoClient) -> dict[str, str]:
    """Fetch the Gemini API credentials from OpenBao.

    This is the function the FastAPI app calls at startup. Note the shape of
    the return value: a plain dict of strings, with the key present only in
    memory.
    """
    lease = client.read_secret("ai/platform", "llm/gemini")
    api_key = lease.value.get("api_key")
    if not api_key:
        raise OpenBaoError(
            f"Gemini secret at ai/platform/llm/gemini has no 'api_key' field. "
            f"Version={lease.version} created={lease.created_time}"
        )
    return {
        "api_key": api_key,
        "model": lease.value.get("model", "gemini-2.0-flash"),
        "project_id": lease.value.get("project_id", ""),
    }
