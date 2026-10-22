#!/usr/bin/env python3
"""Meridian AI PII column demo — Transit encryption in front of a database.

Stdlib only: `urllib` for HTTP, `sqlite3` for storage. The point of the
demo is the *crypto path*, and the crypto path does not care whether the
row store is Postgres or SQLite — Transit never sees your database.

Run it with a token that carries the `data-pipeline` policy (read on
`ai/platform/data/db/postgres`, encrypt + decrypt on the transit key, and
NOTHING on the transit key itself):

    export BAO_ADDR=http://127.0.0.1:8200
    export BAO_TOKEN=s.xxxxxxxxxxxxxxxxxxxxxxxx
    python3 pii_demo.py

Optional environment:

    PII_DB_PATH   where to write the demo database (default: ./pii_demo.sqlite)
    PII_EMAIL     the address to protect (default: aisha.rahman@meridian-ai.com)
"""

import base64
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BAO_ADDR = os.environ["BAO_ADDR"].rstrip("/")
BAO_TOKEN = os.environ["BAO_TOKEN"]

KV_MOUNT = "ai/platform"
KV_KEY = "db/postgres"
TRANSIT_MOUNT = "ai/transit"
TRANSIT_KEY = "pii-column-encryption"

DB_PATH = os.environ.get("PII_DB_PATH", "pii_demo.sqlite")
EMAIL = os.environ.get("PII_EMAIL", "aisha.rahman@meridian-ai.com")


def bao(method, path, payload=None):
    """One HTTP call to OpenBao. Returns the parsed JSON body."""
    url = f"{BAO_ADDR}/v1/{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Vault-Token", BAO_TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"OpenBao {method} {path} -> HTTP {exc.code}: {exc.read().decode()}"
        )
    return json.loads(body) if body else {}


def b64(text):
    return base64.b64encode(text.encode()).decode()


def unb64(text):
    return base64.b64decode(text).decode()


def transit_encrypt(plaintext):
    resp = bao("POST", f"{TRANSIT_MOUNT}/encrypt/{TRANSIT_KEY}", {"plaintext": b64(plaintext)})
    return resp["data"]["ciphertext"]


def transit_decrypt(ciphertext):
    resp = bao("POST", f"{TRANSIT_MOUNT}/decrypt/{TRANSIT_KEY}", {"ciphertext": ciphertext})
    return unb64(resp["data"]["plaintext"])


def main():
    # (1) The app's only secret from OpenBao is the database password.
    creds = bao("GET", f"{KV_MOUNT}/data/{KV_KEY}")["data"]["data"]
    print(
        f"[1] pulled DB creds from OpenBao KV: "
        f"db={creds['db_name']} user={creds['db_user']}"
    )

    # (2) The app sends plaintext to OpenBao. It never holds a key.
    ciphertext = transit_encrypt(EMAIL)
    print(f"[2] transit_encrypt -> {ciphertext[:32]}...")

    # (3) Only ciphertext is written to the row store.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE users ("
        " id INTEGER PRIMARY KEY,"
        " email_ciphertext TEXT NOT NULL,"
        " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO users (email_ciphertext) VALUES (?)", (ciphertext,)
    )
    conn.commit()
    print("[3] inserted row with ciphertext only")

    # (4) The round trip works, because the app can decrypt.
    stored = conn.execute("SELECT email_ciphertext FROM users").fetchone()[0]
    recovered = transit_decrypt(stored)
    assert recovered == EMAIL, "round trip failed"
    print(f"[4] read row -> transit_decrypt -> {recovered}")
    print("    round trip OK")
    conn.close()

    # (5) The raw storage file does not contain the email. That is the
    #     property you were buying.
    with open(DB_PATH, "rb") as fh:
        raw = fh.read()
    print(f"[5] raw DB file contains plaintext email? {EMAIL.encode() in raw}")
    print(f"    raw DB file contains the ciphertext? {stored.encode() in raw}")

    # (6) The app cannot read the key. It can use it; it cannot steal it.
    req = urllib.request.Request(
        f"{BAO_ADDR}/v1/{TRANSIT_MOUNT}/keys/{TRANSIT_KEY}", method="GET"
    )
    req.add_header("X-Vault-Token", BAO_TOKEN)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(f"[6] reading the transit key -> HTTP {resp.status}: {body}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(
            f"[6] reading the transit key from the app's token -> "
            f"OpenBao GET {TRANSIT_MOUNT}/keys/{TRANSIT_KEY} -> "
            f"HTTP {exc.code}: {body}"
        )


if __name__ == "__main__":
    sys.exit(main())
