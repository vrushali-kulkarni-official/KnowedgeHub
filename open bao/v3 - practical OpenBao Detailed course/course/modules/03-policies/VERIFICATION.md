> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Module 03 — Policies & ACLs: Final Review Sweep (round 2)

**Reviewer:** General (task `r1`) · **Date:** 2026-10-21
**Target:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`,
committed 2026-10-01T15:32:54Z)

Second (and final) review sweep. **Module 03 passed every check in both
rounds, so this file records a re-verification, not a set of changes.**

The verifier's instruction for this round was explicit: *"Module 03 PASSED
on every check — do not touch it."* **No file under
`modules/03-policies/README.md` was modified in this round.** This file was
rewritten so that the record is accurate about what was and was not touched.

---

## 1. Summary

| | |
|---|---|
| Claims re-executed against a live server (round 1) | ~60 |
| Claims re-executed against a live server (round 2 spot-check) | ~18 |
| Defects found in round 1 | **1** (§13.1 `broken.hcl` error message) |
| Defects found in round 2 | **0** |
| Changes to `modules/03-policies/README.md` in round 2 | **none** |
| Authoring-environment paths in the module | none (grep clean) |
| Placeholder values | none (grep clean) |

---

## 2. Round-1 change (still in place, not touched in round 2)

### F1 — §13.1: the `bao policy fmt broken.hcl` error message was not reproducible

Round 1 quoted:

```
$ bao policy fmt broken.hcl
failed to parse policy: At 2:1: error parsing list, expected comma or list end, got: EOF
```

No file could be constructed that produced that exact position/message, and
the four broken-policy examples were quoted **without their file contents**,
so a reader had no way to reproduce them (the quoted line numbers — "on
line 3", "on line 6" — depend on the file).

**Fixed in round 1:** the four broken files are now shown in full as `hcl`
blocks immediately before their outputs, and the `broken.hcl` message was
replaced with the observed one:

```
$ bao policy fmt broken.hcl
failed to parse policy: At 3:2: object expected closing RBRACE got: EOF
```

The other three messages were re-verified against the *shown* files
(`invalid capability "reed"`, `invalid key "bogus_key" on line 3`,
`invalid key "bogus" on line 6`).

---

## 3. Round-2 re-verification (no changes required)

A fresh lab instance was started and the highest-risk claims were re-run
to confirm that the module is still correct after round 1's edits and after
the round-2 work on Modules 01 and 02 (which shared the same server).

| Area | Spot-checked live | Result |
|---|---|---|
| `default` policy body | `bao policy read default` | ✅ byte-for-byte identical to the module's §2.4 block (16 self-service paths, nothing under `ai/`) |
| `root` sentinel | `bao policy read root` → `No policy named: root` (exit 2); `bao read sys/policy/root` → `rules n/a` | ✅ exact match |
| AppRole round trip | `bao auth enable approle`, role write, `role-id`, `secret-id`, `bao write -format=json auth/approle/login …` | ✅ exact match, including `lease_duration: 900` and `policies: [ai-harness-service, default]` |
| the quiet flag-order gotcha | `bao write auth/approle/role/…/secret-id -field=secret_id` | ✅ still exits 0, still prints the whole secret-id table, still warns `Endpoint ignored these unrecognized parameters: [-field]` |
| `sudo` table, without `sudo` | seal / policy write / secrets enable / auth enable / audit enable / generate-root / tools random | ✅ all 7 return 403 at the exact URLs the module quotes |
| `sudo` table, with `sudo` | policy write / secrets enable / auth enable / generate-root / tools random | ✅ all succeed as quoted |
| the 2.7 audit-device change | `bao audit enable file file_path=lab/logs/audit.log` with a sudo token | ✅ 400 `* cannot enable audit device via API; use declarative, config-based audit device management instead` |
| `sys/policy` vs `sys/policies/acl` | `bao list sys/policy` (200), `bao read sys/policy/<name>` (403), `bao policy read <name>` (403), capability sweep | ✅ the module's conclusion — the `platform-admin` gap is real — confirmed |
| `deny` across policies | `deny-lab` + `grant-db` on one token | ✅ still `deny`, still 403 on the real read |
| the 7-line wildcard measurement | `wildcard-lab` policy, 7 paths | ✅ all 7 lines match |
| `bao policy fmt` (4 broken files + client-side check) | `bao policy fmt` on each; `BAO_ADDR="http://127.0.0.1:1"` | ✅ all four messages match, still client-side |
| `sys/internal/ui/mounts` special case | service token with no grant | ✅ still readable, simulator still says `deny` |
| GUI labels in §14 | `grep -c -F "<label>"` over the downloaded bundle | ✅ `ACL Policies`, `Create policy`, `Edit policy`, `Secrets engines`, `Authentication methods`, `Entities`, `Groups`, `Leases`, `Copy token`, `Renew token`, `Log out`, `Upload file`, `CodeMirror` all present; **no** "pending approval" string anywhere (the module's "no Control Group screen" claim holds) |

The **Control Group** flow (§9) was not re-run in round 2 — it was
re-verified in full in round 1 (requester receives a 300 s wrapping token
and `data: null`; the approver sees `request_path` / `request_operation` /
`request_entity` but not the value; `authorize` → `approved true`; unwrap
before approval → 400 `wrapping token is not valid or does not exist`;
self-approval → 500 `token owner cannot be approver`; double approval → 500
`approver has already authorized`; wrong group → a *successful* call with
`approved false`; and all six `control_group` parser error messages
verbatim). Round 2 did not touch that code path.

---

## 4. Commands actually run in round 2 (verbatim)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
$BAO_BIN policy read default
$BAO_BIN policy read root
$BAO_BIN read sys/policy/root
$BAO_BIN policy list
$BAO_BIN list sys/policy

$BAO_BIN auth enable approle
$BAO_BIN write auth/approle/role/ai-harness token_policies=… token_ttl=… secret_id_num_uses=…
$BAO_BIN read -field=role_id auth/approle/role/ai-harness/role-id
$BAO_BIN write -field=secret_id -f auth/approle/role/ai-harness/secret-id
$BAO_BIN write auth/approle/role/ai-harness/secret-id -field=secret_id
$BAO_BIN write -format=json auth/approle/login role_id=… secret_id=…
$BAO_BIN write -field=policies -format=yaml auth/token/lookup token=…

for p in ai-harness-service data-pipeline-service secret-rotation-bot \
         platform-operator platform-admin wildcard-lab deny-lab grant-db; do
    $BAO_BIN policy write "$p" - < "$p.hcl"
  done

BAO_TOKEN=$T $BAO_BIN token capabilities <each path>
BAO_TOKEN=$T $BAO_BIN operator seal
BAO_TOKEN=$T $BAO_BIN policy write probe-policy - <<'EOF'
BAO_TOKEN=$T $BAO_BIN secrets enable -path=ai/probe kv-v2
BAO_TOKEN=$T $BAO_BIN auth enable userpass
BAO_TOKEN=$T $BAO_BIN audit enable file file_path=lab/logs/audit.log
$BAO_BIN audit enable file file_path=lab/logs/audit.log
BAO_TOKEN=$T $BAO_BIN operator generate-root -init -otp=…
BAO_TOKEN=$T $BAO_BIN write sys/tools/random bytes=16

$BAO_BIN policy fmt broken.hcl bad-capability.hcl bad-key.hcl bad-control-group.hcl
BAO_ADDR="http://127.0.0.1:1" $BAO_BIN policy fmt bad-capability.hcl

BAO_TOKEN=$T $BAO_BIN read sys/internal/ui/mounts/ai/platform/llm/gemini
BAO_TOKEN=$T $BAO_BIN token capabilities sys/internal/ui/mounts/ai/platform/llm/gemini

# GUI bundle
curl -s http://127.0.0.1:<port>/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
for f in $(…); do curl -s "…/ui/$f" -o "$(basename $f)"; done
cat *.js > all.js
grep -c -F "<label>" all.js
```

---

## 5. What I could NOT verify — stated plainly

1. **The rendered GUI.** Verified via the shipped bundle's literal strings
   and the API behind each screen, not by clicking through the browser.
   §14 says so.
2. **Multi-factor control groups** — the stanza accepts repeated `factor`
   blocks, but only a single factor was exercised. The module's §9.5 says
   the same, and its homework task 5 asks the reader to build one.
3. **Control Groups under HA.** No HA cluster was available. Whether a
   pending wrapped request survives a failover is untested — in the module
   and here.
4. **The `9167` port and every timestamp / UUID in the transcripts** are
   captures from the author's instance. The module notes the port
   difference at the top of §3.
5. **The `sys/unseal` demo in §7.1** — the underlying fact (unsealing needs
   no token and no `sudo`) was confirmed against
   `VERIFIED-FACTS.md` §12c.1 and a seal/unseal cycle was re-run, but the
   exact transcript (a `platform-admin` token submitting a share and the
   server answering `progress 1`) was not re-created with that specific
   policy attached. The module's claim is consistent with the documented and
   verified behaviour.
6. **`control_group` has no documentation.** The syntax in §9.2 is a
   reconstruction from the server's own parser errors. It is accepted by
   2.7.1, but I cannot confirm it is stable across releases — which is
   exactly what the module's §9.5 says.
