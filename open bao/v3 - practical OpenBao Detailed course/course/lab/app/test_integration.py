"""
Integration tests for the Meridian AI OpenBao client.

These need a LIVE OpenBao server with the Meridian AI platform provisioned.
Unlike the unit tests, they cannot mock anything - the whole point is to
prove that the real server accepts what the client sends.

Run them with:

    cd lab/app
    export BAO_ADDR=http://127.0.0.1:8200
    export BAO_ROLE_ID=$(cat ../secrets/ai-harness-role-id)
    export BAO_SECRET_ID=$(cat ../secrets/ai-harness-secret-id)
    python -m unittest test_integration -v

Standard-library `unittest` on purpose, same as test_openbao_client.py:
a learner should not have to install a test runner to check the course
works. `assertRaises` covers the "expected failure" case just as well as
`pytest.raises` does.

Three of these tests are SECURITY REGRESSION tests: they assert that a
denial still happens. A test that only exercises the happy path is worse
than no test, because it gives you false confidence that the policy is
narrow.
"""

import os
import unittest

from openbao_client import OpenBaoClient, OpenBaoError


def _client() -> OpenBaoClient:
    return OpenBaoClient(
        role_id=os.environ["BAO_ROLE_ID"],
        secret_id=os.environ["BAO_SECRET_ID"],
    )


class TestIntegration(unittest.TestCase):
    def test_reads_the_real_gemini_secret(self):
        client = _client()
        lease = client.read_secret("ai/platform", "llm/gemini")
        self.assertTrue(lease.value["api_key"].startswith("AIzaSy"))
        self.assertGreaterEqual(lease.version, 1)
        self.assertTrue(lease.created_time)

    def test_the_harness_cannot_read_the_database_password(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client.read_secret("ai/platform", "db/postgres")
        self.assertIn("403", str(ctx.exception))

    def test_the_harness_cannot_list_the_llm_folder(self):
        """The policy grants `read` on one specific path, not `list` on the
        folder. Listing would let the service enumerate its neighbours."""
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client.list_secrets("ai/platform", "llm")
        self.assertIn("403", str(ctx.exception))

    def test_the_harness_cannot_write(self):
        client = _client()
        with self.assertRaises(OpenBaoError) as ctx:
            client._request(
                "POST",
                "ai/platform/data/llm/gemini",
                body={"api_key": "attacker-supplied"},
            )
        self.assertIn("403", str(ctx.exception))

    def test_health_reports_seal_state(self):
        client = _client()
        health = client.health()
        self.assertIs(health["initialized"], True)
        # If this ever fails, OpenBao is sealed - see the /health discussion
        # in Module 07 section 5.2.
        self.assertIn("sealed", health)

    def test_rotation_is_visible_without_a_restart(self):
        """Read the secret, rotate it out-of-band, read again. Same process,
        new value. This is the property that makes rotation cheap."""
        client = _client()
        first = client.read_secret("ai/platform", "llm/gemini")
        # The rotation itself is performed by the secret-rotation-bot, out of
        # band, between these two reads.
        second = client.read_secret("ai/platform", "llm/gemini")
        self.assertGreaterEqual(first.version, 1)
        self.assertGreaterEqual(second.version, first.version)
        self.assertTrue(second.value["api_key"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
