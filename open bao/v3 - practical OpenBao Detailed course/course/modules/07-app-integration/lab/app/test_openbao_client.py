#!/usr/bin/env python3
"""
Unit tests for the Meridian AI OpenBao client.

These tests need NO server, NO credentials, and NO test runner beyond the
standard library:

    cd lab/app
    python -m unittest test_openbao_client -v

Why this matters: the client sits on the secret-fetching path, so it is the
last line of defence between a broken code path and a silent fallback to a
default credential. Every test here is about that class of failure - a 403 that
looks like a schema error, a network error that quietly returns an empty
secret, a path that loses KV v2's `/data/` segment.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openbao_client import (  # noqa: E402
    OpenBaoClient,
    OpenBaoError,
    get_gemini_credentials,
)

GEMINI_KEY = "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"


def _response(payload: dict, status: int = 200) -> mock.MagicMock:
    """A mock for what urllib.request.urlopen returns."""
    body = json.dumps(payload).encode()
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.status_code = status
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


def _http_error(status: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://127.0.0.1:8200/v1/whatever",
        code=status,
        msg="error",
        hdrs=None,
        fp=mock.MagicMock(read=mock.MagicMock(return_value=body.encode())),
    )


class _IsolatedEnv(unittest.TestCase):
    """Base class that makes the suite independent of the ambient shell.

    The unit tests promise they need no server, no credentials and no
    configuration. That promise is only true if the environment cannot
    leak in: a learner following the course will have BAO_ADDR,
    BAO_ROLE_ID and BAO_SECRET_ID exported, and the client's defaults
    read those variables. Without this isolation the path assertions
    fail whenever BAO_ADDR points anywhere other than the default.
    """

    _BAO_ENV = ("BAO_ADDR", "BAO_TOKEN", "BAO_ROLE_ID", "BAO_SECRET_ID", "BAO_NAMESPACE")

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in self._BAO_ENV}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v


class TestPathConstruction(_IsolatedEnv):
    """The URL the client builds is the single most important thing it does."""

    def test_read_secret_builds_the_kv_v2_data_path(self):
        """The single most important assertion in this file.

        KV v2's HTTP API is <mount>/data/<key>. If this ever regresses to
        <mount>/<key>, every read returns 403 'permission denied' and the
        on-call engineer debugs the policy instead of the code.
        """
        client = OpenBaoClient(role_id="r", secret_id="s")
        body = {
            "data": {
                "data": {"api_key": GEMINI_KEY},
                "metadata": {"version": 3, "created_time": "2026-10-21T18:01:46Z"},
            }
        }
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            lease = client.read_secret("ai/platform", "llm/gemini")

        self.assertEqual(lease.version, 3)
        self.assertEqual(lease.value["api_key"], GEMINI_KEY)
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8200/v1/ai/platform/data/llm/gemini",
        )

    def test_read_secret_version_passes_version_as_a_query_param(self):
        """A historical read is the same path plus ?version=N."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        body = {
            "data": {
                "data": {"api_key": GEMINI_KEY},
                "metadata": {"version": 2},
            }
        }
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            lease = client.read_secret_version("ai/platform", "llm/gemini", 2)

        self.assertEqual(lease.version, 2)
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8200/v1/ai/platform/data/llm/gemini?version=2",
        )

    def test_list_uses_the_metadata_path(self):
        """Listing reads the metadata layer, not the data layer."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response({"data": {"keys": ["gemini"]}})
            keys = client.list_secrets("ai/platform", "llm")

        self.assertEqual(keys, ["gemini"])
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8200/v1/ai/platform/metadata/llm",
        )


class TestFailFast(_IsolatedEnv):
    """Every failure must raise, loudly, with the server's own words."""

    def test_403_is_wrapped_with_the_server_body(self):
        """The body is what tells the on-call engineer it is a POLICY
        problem, not a schema problem. Do not swallow it."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.fake"
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = _http_error(403, "permission denied")
            with self.assertRaises(OpenBaoError) as ctx:
                client.read_secret("ai/platform", "llm/gemini")

        self.assertIn("403", str(ctx.exception))
        self.assertIn("permission denied", str(ctx.exception))

    def test_missing_api_key_is_a_schema_error_not_a_403(self):
        """A secret that exists but has no api_key is a different fault from
        a secret you are not allowed to read. They must not be conflated."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.fake"
        body = {"data": {"data": {"model": "gemini-2.0-flash"}, "metadata": {"version": 1}}}
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            with self.assertRaises(OpenBaoError) as ctx:
                get_gemini_credentials(client)

        self.assertIn("api_key", str(ctx.exception))

    def test_login_without_credentials_refuses(self):
        """The client must refuse to run without a role_id and secret_id
        rather than quietly using an ambient token.

        The environment is cleared first on purpose: a learner following
        the course will have BAO_ROLE_ID and BAO_SECRET_ID exported, and
        this test must behave identically whether or not they are set.
        """
        client = OpenBaoClient(role_id="", secret_id="")
        with self.assertRaises(OpenBaoError) as ctx:
            client.login()
        self.assertIn("BAO_ROLE_ID", str(ctx.exception))

    def test_network_failure_never_falls_back(self):
        """There is no code path that returns a default secret. A silent
        fallback to an empty credential is how an AI harness ends up
        'working' while talking to nobody."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.fake"
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = urllib.error.URLError("connection refused")
            with self.assertRaises(OpenBaoError) as ctx:
                client.read_secret("ai/platform", "llm/gemini")

        self.assertIn("Refusing", str(ctx.exception))


class TestNoDiskWrites(_IsolatedEnv):
    """The client is in-memory only. If this ever starts writing a
    credential to disk, the whole design is broken."""

    def test_reading_a_secret_creates_no_files(self):
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.fake"
        body = {
            "data": {
                "data": {"api_key": GEMINI_KEY},
                "metadata": {"version": 1},
            }
        }
        before = set(os.listdir(tempfile.gettempdir()))
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            client.read_secret("ai/platform", "llm/gemini")
        after = set(os.listdir(tempfile.gettempdir()))

        self.assertEqual(before, after)


class TestTokenLifecycle(_IsolatedEnv):
    """Token TTL, refresh, and the three-state token parameter."""

    def test_login_sends_an_empty_token_header(self):
        """The login request must NOT carry a stale token. `_headers` uses
        None for 'use my cached token' and '' for 'send an empty header'."""
        client = OpenBaoClient(role_id="r", secret_id="s")
        client._token = "s.stale-token"
        body = {
            "auth": {
                "client_token": "s.fresh",
                "lease_duration": 900,
                "renewable": True,
                "policies": ["ai-harness-service"],
            }
        }
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)
            client.login()

        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("X-vault-token"), "")

    def test_reauth_happens_at_eighty_percent_of_the_ttl(self):
        """A 100-second token must be refreshed at 80 seconds, not 100.

        The client applies the 80% rule at LOGIN time: it stores
        `_token_expires_at = now + ttl * 0.8`. So the refresh deadline is
        80s after the token was issued, and `_ensure_token` re-authenticates
        once that moment passes.
        """
        client = OpenBaoClient(role_id="r", secret_id="s")
        body = {
            "auth": {
                "client_token": "s.fresh",
                "lease_duration": 100,
                "renewable": True,
                "policies": ["ai-harness-service"],
            }
        }
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value = _response(body)

            # login() must have stored the deadline at 80% of the TTL.
            client.login()
            self.assertAlmostEqual(
                client._token_expires_at - time.time(),
                80,
                delta=2,
                msg="token deadline should be 80% of the TTL, not the full TTL",
            )

            # At 79s of a 100s token we are still inside the window: no re-auth.
            client._token_expires_at = time.time() + 79
            with mock.patch.object(
                OpenBaoClient, "login", wraps=client.login
            ) as login:
                client._ensure_token()
                login.assert_not_called()

            # Once the window has closed it MUST re-authenticate.
            client._token_expires_at = time.time() - 1
            with mock.patch.object(
                OpenBaoClient, "login", wraps=client.login
            ) as login:
                client._ensure_token()
                login.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
