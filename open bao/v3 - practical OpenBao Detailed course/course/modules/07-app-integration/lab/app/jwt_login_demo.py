#!/usr/bin/env python3
"""Meridian AI — the federated-identity pattern, runnable.

This is the OpenBao side of Pattern C from Module 07 section 8.3: the
container never receives a secret. It receives a *projected token* that
the orchestrator signed, OpenBao validates that token against a JWKS
endpoint, and OpenBao hands back a scoped Vault token.

In a real cluster the projected token comes from the Kubernetes
TokenRequest API, the AWS IAM Roles for Service Accounts, GCP Workload
Identity Federation, or Azure Workload Identity — all of which are the
same shape: an RS256-signed JWT with `iss`, `sub`, `aud` and `exp`.

Here we mint that token ourselves so you can watch the whole exchange on
a laptop. That needs an RSA signer, which is the one thing the standard
library cannot do, so this demo has exactly one dev-only dependency:

    pip install cryptography

Nothing else. The OpenBao side is plain `urllib`.

Run it against a live OpenBao that has the `ai-harness-service` policy:

    export BAO_ADDR=http://127.0.0.1:8200
    export BAO_TOKEN=s.xxxxxxxxxxxxxxxxxxxxxxxx   # a token that can write auth/
    python3 jwt_login_demo.py
"""

import base64
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

BAO_ADDR = os.environ["BAO_ADDR"].rstrip("/")
BAO_TOKEN = os.environ["BAO_TOKEN"]
BAO_BIN = os.environ.get("BAO_BIN", "bao")

JWKS_PORT = int(os.environ.get("JWKS_PORT", "8099"))
KID = "meridian-jwt-1"
ISSUER = "https://meridian-ai.svc.cluster.local"
SUBJECT = "ai-harness"
AUDIENCE = "openbao"
POLICY = "ai-harness-service"
ROLE_NAME = "ai-harness-jwt"


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def bao(method, path, payload=None):
    """One HTTP call to OpenBao. Returns the parsed JSON body."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{BAO_ADDR}/v1/{path}", data=data, method=method)
    req.add_header("X-Vault-Token", BAO_TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"ERROR {method} {path} -> HTTP {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(body) if body else {}


def sh(*args):
    """Run a bao CLI command and show it the way the learner would see it."""
    proc = subprocess.run(
        [BAO_BIN, *args], capture_output=True, text=True,
        env={**os.environ, "BAO_ADDR": BAO_ADDR, "BAO_TOKEN": BAO_TOKEN},
    )
    print(f"$ bao {' '.join(args)}")
    print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    print()
    return proc.stdout


def make_jwks_server(private_key):
    """Serve the public half of the signing key as a JWKS document."""
    numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": KID,
                "n": b64u(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": b64u(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(jwks).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", JWKS_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def sign(private_key, claims):
    header = {"alg": "RS256", "typ": "JWT", "kid": KID}
    signing_input = (
        b64u(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + b64u(json.dumps(claims, separators=(",", ":")).encode())
    )
    signature = private_key.sign(
        signing_input.encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    return signing_input + "." + b64u(signature)


def main():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = make_jwks_server(private_key)

    sh("auth", "disable", "jwt")
    sh("auth", "enable", "jwt")
    sh(
        "write", "auth/jwt/config",
        f"jwks_url=http://127.0.0.1:{JWKS_PORT}/.well-known/jwks.json",
        "jwt_supported_algs=RS256",
        "role_type=jwt",
    )
    print("$ bao read -format=json auth/jwt/config")
    config = bao("GET", "auth/jwt/config")["data"]
    print(json.dumps(
        {k: config[k] for k in ("jwks_url", "jwt_supported_algs", "status")}, indent=2
    ))
    print()

    # `bound_claims` is a map and `bound_audiences` is a list, so the
    # role is written over the HTTP API rather than the CLI.
    print("$ bao write auth/jwt/role/ai-harness-jwt role=ai-harness-service \\")
    print('      user_claim=sub bound_claims=\'{"iss":"...","sub":"ai-harness"}\' \\')
    print('      bound_audiences=["openbao"] token_ttl=15m token_max_ttl=1h')
    bao("POST", f"auth/jwt/role/{ROLE_NAME}", {
        "policies": [POLICY],
        "user_claim": "sub",
        "role_type": "jwt",
        "bound_claims": {"iss": ISSUER, "sub": SUBJECT},
        "bound_audiences": [AUDIENCE],
        "token_ttl": "15m",
        "token_max_ttl": "1h",
    })
    print(f"Success! Data written to: auth/jwt/role/{ROLE_NAME}")
    print()
    role = bao("GET", f"auth/jwt/role/{ROLE_NAME}")["data"]
    print(json.dumps(
        {k: role.get(k) for k in (
            "user_claim", "role_type", "bound_claims", "bound_audiences",
            "token_ttl", "token_max_ttl",
        )}, indent=2
    ))
    print()

    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 900,
        "namespace": "meridian-ai",
    }
    token = sign(private_key, claims)

    print("### present the projected service-account token to OpenBao")
    auth = bao("POST", "auth/jwt/login", {"jwt": token, "role": ROLE_NAME})["auth"]
    print(f"client_token   = {auth['client_token']}")
    print(f"lease_duration = {auth['lease_duration']}")
    print(f"policies       = {auth['policies']}")
    print(f"metadata       = {json.dumps(auth.get('metadata'))}")
    print()

    print("### the token works, and it is scoped exactly like the AppRole token")
    for path in ("ai/platform/data/llm/gemini", "ai/platform/data/db/postgres"):
        req = urllib.request.Request(f"{BAO_ADDR}/v1/{path}")
        req.add_header("X-Vault-Token", auth["client_token"])
        try:
            with urllib.request.urlopen(req) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        print(f"GET /v1/{path} -> {code}")
    print()

    print("### the same token with a WRONG subject is refused")
    bad = dict(claims, sub="someone-else")
    try:
        bao("POST", "auth/jwt/login", {"jwt": sign(private_key, bad), "role": ROLE_NAME})
    except SystemExit:
        print("    refused, as it should be")
        print()

    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
