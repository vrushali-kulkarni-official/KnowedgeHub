#!/usr/bin/env python3
"""
jwks-server.py — a minimal OIDC provider stand-in for the lab.

It serves:
  GET /jwks.json                        → the JWKS (public keys)
  GET /.well-known/openid-configuration  → a discovery document
  GET /token?audience=…&repository=…     → mints a signed GitHub-style OIDC JWT

The minted JWT carries the same claims GitHub Actions puts in its OIDC token
(iss, aud, sub, repository, ref, workflow, environment, actor, sha, ...).

Run standalone:      python3 jwks-server.py --port 8099
Run in Docker:       docker run ... python3 jwks-server.py --port 8099
"""
from __future__ import annotations

import argparse
import base64
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_PATH = "/jwks.json"
DISCOVERY_PATH = "/.well-known/openid-configuration"
TOKEN_PATH = "/token"

KEY: rsa.RSAPrivateKey | None = None
KID = "lab-key"


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_int(n: int) -> str:
    return b64u(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def jwks() -> dict:
    pub = KEY.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": KID,
                "n": b64u_int(pub.n),
                "e": b64u_int(pub.e),
            }
        ]
    }


def mint_jwt(claims: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": KID}
    signing_input = f"{b64u(json.dumps(header).encode())}.{b64u(json.dumps(claims).encode())}".encode()
    sig = KEY.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode()}.{b64u(sig)}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter output
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)

        if url.path == JWKS_PATH:
            return self._send(200, json.dumps(jwks()).encode())

        if url.path == DISCOVERY_PATH:
            base = f"http://{self.headers.get('Host', 'localhost:8099')}"
            doc = {
                "issuer": ISSUER,
                "authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}{TOKEN_PATH}",
                "jwks_uri": f"{base}{JWKS_PATH}",
                "response_types_supported": ["id_token", "code", "code id_token"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "scopes_supported": ["openid", "profile", "email", "groups"],
                "claims_supported": [
                    "sub", "aud", "iss", "repository", "repository_owner",
                    "ref", "workflow", "environment", "actor", "sha", "run_id",
                ],
            }
            return self._send(200, json.dumps(doc).encode())

        if url.path == TOKEN_PATH:
            now = int(time.time())
            aud = (q.get("audience") or ["openbao"])[0]
            repo = (q.get("repository") or ["your-org/your-repo"])[0]
            ref = (q.get("ref") or ["refs/heads/main"])[0]
            workflow = (q.get("workflow") or ["deploy.yml"])[0]
            environment = (q.get("environment") or ["production"])[0]
            actor = (q.get("actor") or ["octocat"])[0]
            owner = repo.split("/")[0]

            claims = {
                "iss": ISSUER,
                "aud": aud,
                "sub": f"repo:{repo}:ref:{ref}",
                "repository": repo,
                "repository_owner": owner,
                "ref": ref,
                "workflow": workflow,
                "environment": environment,
                "actor": actor,
                "run_id": str(now),
                "run_number": "42",
                "repository_visibility": "private",
                "ref_type": "branch",
                "sha": "a1b2c3d4e5f6" + "0" * 50,
                "iat": now,
                "nbf": now,
                "exp": now + 600,
            }
            return self._send(200, json.dumps({"value": mint_jwt(claims)}).encode())

        self._send(404, b'{"error":"not found"}')


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True   # don't die on a quick restart


def main() -> None:
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()

    KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    print(f"[jwks-server] listening on :{args.port}", flush=True)
    print(f"[jwks-server] issuer = {ISSUER}", flush=True)
    Server(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
