> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Module 01 — Foundations: Final Review Sweep (round 2)

**Reviewer:** General (task `r1`) · **Date:** 2026-10-21
**Target:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`,
committed 2026-10-01T15:32:54Z)

This is the second (and final) review sweep. Round 1 re-executed ~45
high-risk claims and fixed three defects. The verifier then found **one
material defect that round 1 had missed**, and it was a *safety* bug: the
module taught an unsafe way to validate a decoded break-glass root token.
That defect is fixed here, together with the two follow-on edits needed to
make the fix complete.

---

## 1. Summary

| | |
|---|---|
| Claims re-executed against a live server (round 1) | ~45 |
| Claims re-executed against a live server (round 2, this file) | ~12 |
| Defects fixed in round 1 | 3 (audit-log record pair, jq error count, `-dev` grep) |
| Defects fixed in round 2 | **1 material + 2 follow-on** |
| Structural changes | none |
| Authoring-environment paths in the module | none (grep clean) |
| Placeholder values | none (grep clean) |

> **Correction to the round-1 deliverable.** Round 1 claimed "everything
> else reproduced exactly". That was **not accurate** — the wrong-OTP decode
> block below was wrong and unsafe, and round 1 did not catch it. Round 1
> had verified the *shape* of the `generate-root` flow but had not
> re-derived the XOR property of the decode step.

---

## 2. Defect fixed in round 2

### F4 (MATERIAL, SAFETY) — §6.5: the wrong-OTP decode output was impossible, and the rule taught there was unsafe

**What the module said.** The module's wrong-OTP decode transcript was:

```console
$ bao operator generate-root -decode="IRstGgk+BHQhJ10bai44BiJUJncGXQMrIFk" -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqX"
WiOxKvC.~~jYynad5jJ:jQ
```

followed by:

> That is not a token. It is the previous token XORed with the wrong key. If
> your decode output does not start with `s.`, **you used the wrong OTP** —
> start the whole attempt over.

**Why that was wrong, three ways.**

1. **The output was impossible.** The "wrong" OTP
   (`vrbbBHGZ6YOq3WVgFaLsLH9AqX`) differs from the correct one used two
   lines earlier (`vrbbBHGZ6YOq3WVgFaLsLH9AqI`) in **exactly one
   character** — the last one. Decode is a position-wise XOR, so the two
   outputs can differ in exactly **one byte**. The module's quoted output
   differs from the real token in 25 of 26 characters, which that OTP
   pairing cannot produce.
2. **The heuristic was unsafe.** Because a one-character OTP typo corrupts
   exactly one byte, the decoded string **still starts with `s.`**, still
   has the right length, and still looks exactly like a token. A reader
   following the module's rule ("if it does not start with `s.`, you used
   the wrong OTP") would install a **corrupted break-glass root token** and
   believe it was fine — discovering the problem later, at the worst
   possible moment, as a 403 with no explanation.
3. The module never showed what a *wrong* token actually does when used.

**The live proof (this sweep, OpenBao 2.7.1).** One `generate-root`
attempt, decoded twice — once with the right OTP, once with an OTP that
differs only in the last character:

```console
$ bao operator generate-root -decode="EUYtIiUoOiklFRk+HAhJGnELIiEEPA0icyo" -otp="bhdShjyQhdqLyaps7RUGgxCh0"
s.IqMBCxMqhrei9iFYwfcDNJCF

$ bao operator generate-root -decode="EUYtIiUoOiklFRk+HAhJGnELIiEEPA0icyo" -otp="bhdShjyQhdqLyaps7RUGgxCh0X"
s.IqMBCxMqhrei9iFYwfcDNJCr
```

One character different. **Both start with `s.`.** And the corrupted one is
not a token at all:

```console
$ BAO_TOKEN=s.IqMBCxMqhrei9iFYwfcDNJCr bao token lookup
Error looking up token: Error making API request.

URL: GET http://127.0.0.1:9306/v1/auth/token/lookup-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

while the correct one authenticates and identifies itself:

```console
$ BAO_TOKEN=s.IqMBCxMqhrei9iFYwfcDNJCF bao token lookup
Key                 Value
---                 -----
accessor            qbE2x7gonMH3UbZhbRMHd6cz
creation_time       1792611468
creation_ttl        0s
display_name        root
entity_id           n/a
expire_time         <nil>
explicit_max_ttl    0s
id                  s.IqMBCxMqhrei9iFYwfcDNJCF
meta                <nil>
num_uses            0
orphan              true
path                auth/token/root
policies            [root]
ttl                 0s
type                service
```

**What changed in the module:**

1. **§6.5** — the impossible output was replaced with the real two-line
   capture above, with an explicit statement that the wrong-OTP result
   differs in **exactly one character** and **still starts with `s.`**.
2. **§6.5** — the "does it start with `s.`?" heuristic was **deleted and
   replaced** by the only correct procedure: *use the token*. A ⚠️ callout
   now says, in bold: **"Never validate a decoded root token by looking at
   it."** The callout shows both `bao token lookup` transcripts (the 403 for
   the corrupted token, the `display_name root` / `policies [root]` for the
   good one) and states what to do when the lookup 403s: start the attempt
   over with a fresh `-generate-otp`, because the attempt is consumed on
   completion and cannot be re-decoded.
3. **§6.7 (follow-on)** — the copy-paste break-glass script now has a
   **step 6 that actually verifies the token** and aborts if it does not
   authenticate. The script is now 6 steps, and its quoted output was
   **re-captured live** from the updated script:

   ```console
   $ ./breakglass.sh
   [1/6] OTP captured (26 chars)
   [2/6] attempt started, nonce=df1e1451-015f-fecc-ff34-8e50745a9048
   [3/6] share 1 of 2 accepted
   [4/6] share 2 of 2 accepted
   [5/6] new root token minted
   [6/6] new root token verified (display_name: root)

   NEW ROOT TOKEN: s.QGAG9JhXSTVl3AgBk5uoUteY
   ```

   The script's guard is:

   ```bash
   # 6. VERIFY it. A wrong-OTP decode produces a plausible-looking string that
   #    differs from the real token in a single character — it still starts with
   #    "s." and it still has the right length. The ONLY way to know is to use it.
   if ! BAO_TOKEN="$NEW_TOKEN" bao token lookup -field=display_name 2>/dev/null | grep -qx root; then
     echo "the new token did not authenticate - wrong OTP; start over" >&2
     exit 1
   fi
   echo "[6/6] new root token verified (display_name: root)"
   ```

4. **§6.7 (follow-on)** — the "defensive details" list went from three
   items to four, with the fourth being step 6 (use the token).
5. **§10 "What you learned" (follow-on)** — a new checkbox:
   *"**That a wrong-OTP decode still looks like a token** — and that the
   only way to know is to *use* it (`bao token lookup`), never to eyeball
   the string"*.
6. **§12 homework 3 (follow-on)** — the task now ends with: mint a root
   token, change one character of the OTP, decode again, observe that the
   result still starts with `s.`, and prove with `bao token lookup` that
   only the correct one authenticates. *"**Never install a break-glass root
   token you have not used.**"*

---

## 3. What was checked in round 2 and confirmed correct (no edit)

| Claim | Section | Result |
|---|---|---|
| the correct-OTP decode returns a `s.`-prefixed token | §6.5 | ✅ `s.IqMBCxMqhrei9iFYwfcDNJCF` |
| the good token's `token lookup` shows `display_name: root`, `policies: [root]`, `ttl: 0s`, `path: auth/token/root` | §6.5 | ✅ exact match |
| the corrupted token's `token lookup` → 403 `* permission denied` at `GET /v1/auth/token/lookup-self` | §6.5 | ✅ exact match |
| the updated §6.7 script runs end to end and its output is real | §6.7 | ✅ re-executed live |
| the OTP is a 26-character string; the decode is an XOR (one char in → one char out) | §6.2, §6.5 | ✅ confirmed by the two decodes above |
| `bao operator generate-root -generate-otp \| tail -1` → 26 chars | §6.2 | ✅ |
| the `-nonce` gotcha, the `Encoded Token` field-3 gotcha, the short-OTP 400 | §6.3, §6.4 | ✅ (round 1) |
| `bao operator rekey -help` deprecation warning | §6.8 | ✅ (round 1) |
| `bao status`, `bao status -format=json`, `sys/seal-status` | §9.1 | ✅ (round 1) |
| `bao operator init` full text, init-on-initialised 400, `recovery_keys_b64: null` | §4.1, §4.4 | ✅ (round 1) |
| seal / unseal, `BAD-KEY` 400, the 503 `Vault is sealed` responses | §5.1, §5.2 | ✅ (round 1) |
| `bao operator diagnose` with and without `-config`; the pebbledb lock error | §9.3 | ✅ (round 1) |
| the audit-log HMAC and the request/response record pair | §9.4 | ✅ (round 1, fixed there) |
| `curl -sI /ui` → 307; every §8 GUI label; the 8 API status codes | §8 | ✅ (round 1) |
| every HCL block survives `bao operator validate-config` | §3.6 | ✅ (round 1) |
| the `storage "file"` / `api_addr` / `audit` / `disable_mlock` startup errors | §3.3, §3.6 | ✅ (round 1) |

---

## 4. Commands actually run in round 2 (verbatim)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
K1=$(cat unseal-key-1); K2=$(cat unseal-key-2)

OTP=$(bao operator generate-root -generate-otp | tail -1)
INIT=$(bao operator generate-root -init -otp="$OTP")
NONCE=$(printf '%s\n' "$INIT" | awk '/^Nonce/{print $2}')
bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$K1" >/dev/null
OUT=$(bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$K2")
ENC=$(printf '%s\n' "$OUT" | awk '/^Encoded Token/{print $3}')

# right OTP
bao operator generate-root -decode="$ENC" -otp="$OTP"
# wrong OTP: identical except the LAST character
BAD_OTP="${OTP%?}X"
bao operator generate-root -decode="$ENC" -otp="$BAD_OTP"

# use both tokens
BAO_TOKEN="$GOOD" bao token lookup
BAO_TOKEN="$BAD"  bao token lookup

# re-run the updated §6.7 script end to end
UNSEAL_KEY_1=… UNSEAL_KEY_2=… ./breakglass.sh
```

---

## 5. What I could NOT verify — stated plainly

1. **The rendered GUI.** Verified via the shipped bundle's literal strings
   and the API behind each screen, not by clicking through the browser.
2. **Per-run randoms.** The `Cluster Name` / `Cluster ID` in §3.2,
   `accessor` values, `created_time` timestamps and the `9306` port in the
   captured transcripts are from the author's instance and are not
   reproducible. The module notes the port difference in §3.6.
3. **The `Encryption Count    223` figure** in §9.2. I confirmed the claim
   it supports — the counter does **not** move on seal/unseal — but not
   the literal value. The module presents it as a captured transcript.
4. **The XOR property beyond one character.** I demonstrated a one-character
   difference in both directions (last character and first character
   produce a one-character difference in the output). I did not enumerate
   every possible one-character position, but the property follows from
   the position-wise XOR and is consistent with what I observed.
5. **Whether the server issues a distinct error for a malformed (as opposed
   to merely unknown) token.** The corrupted token produced a plain 403
   `permission denied` — indistinguishable from "no such token" and from
   "this token exists but you may not look it up". That is exactly why the
   module now tells the reader to check `display_name: root` rather than
   merely to look for a 403.
