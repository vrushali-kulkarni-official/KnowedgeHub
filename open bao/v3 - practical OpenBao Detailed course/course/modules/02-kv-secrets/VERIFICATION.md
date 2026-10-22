> **What this file is.** It is the verification record for this module:
> what was checked against a live OpenBao 2.7.1 server, what was changed as
> a result, and what could **not** be verified here. It is a reviewer's
> record, not a set of instructions — the module README is the lesson.
>
> The commands below are the ones that were actually run. Where the
> authoring environment differed from yours (a private instance on its own
> port rather than the shared lab on `8200`), that is noted in the text.

# Module 02 — KV v2 Secrets: Final Review Sweep (round 2)

**Reviewer:** General (task `r1`) · **Date:** 2026-10-21
**Target:** OpenBao **v2.7.1** (`a5db72cef75c24b920ade02065b18dd8eb666bac`,
committed 2026-10-01T15:32:54Z)

Second (and final) review sweep. Round 1 re-executed ~55 high-risk claims
and fixed two defects. The verifier then found **three further defects**
that round 1 had missed — all of them internal-consistency failures in the
module's own step-by-step transcripts. All three are fixed here, and each
fix is backed by a fresh live run of the module's own command sequence.

---

## 1. Summary

| | |
|---|---|
| Claims re-executed against a live server (round 1) | ~55 |
| Claims re-executed against a live server (round 2, this file) | ~30 |
| Defects fixed in round 1 | 2 (§11.3 payload drift, §15 GUI labels) |
| Defects fixed in round 2 | **3** (version counters, §10 transcript drift, §15 grep evidence) |
| Structural changes | none |
| Authoring-environment paths in the module | none (grep clean) |
| Placeholder values | only the deliberate "Bad" column in the naming-rules table (§2) |

> **Correction to the round-1 deliverable.** Round 1 claimed "everything
> else reproduced exactly". That was **not accurate**. Round 1 checked each
> command *in isolation* against a live server, but it did **not** replay
> the module's commands **as an ordered sequence** and then read the
> resulting state back. Three of the defects the verifier found are exactly
> the failures that an isolated, out-of-order check cannot see.

---

## 2. Defects fixed in round 2

### F3 — §6.2: both version counters were wrong

The module's "two version series, not one" paragraph said:

> In section 9 you attach an owner label to the Gemini key — come back and
> look at this block afterwards. `current_version` will still be 1, and
> `current_metadata_version` will be 1 as well.

**Live replay of the module's own sequence** (§4 seed → §8.4 data write →
§8.6 ignored per-secret write → §8.7 `metadata_cas` write → §9 `metadata
put`) gives:

```bash
$ bao kv metadata get -format=json ai/platform/llm/gemini \
    | jq -r '.data | "current_version=\(.current_version) current_metadata_version=\(.current_metadata_version)"'
current_version=2 current_metadata_version=3
```

Measured step by step on the live server:

| After | `current_version` | `current_metadata_version` |
|---|---|---|
| §4 seed | 1 | 0 |
| §8.4 `kv put -cas=1` (data) | **2** | 0 |
| §8.6 `write …/metadata/llm/gemini cas_required=false` | 2 | **1** |
| §8.7 raw `metadata_cas` write | 2 | **2** |
| §9 `kv metadata put -custom-metadata=…` | 2 | **3** |
| §9.2 `kv metadata patch …` | 2 | **4** |

**Fixed:** §6.2 now states the real numbers — `current_version` **2** and
`current_metadata_version` **3** at the end of §9, with the counter
progression shown in a table, and notes that §9.2's patch takes the
metadata counter to **4**. A ⚠️ callout was added for a subtlety the
replay exposed: **a metadata write that the server *ignores* still counts**
— §8.6's `cas_required=false` is warned about and ignored as a *value*,
but it still creates a metadata version. The counter tracks write
*attempts*, not value changes.

### F4 — §10 contradicted §9.2: five transcripts showed pre-patch metadata

§9.2's own patch output is:

```
custom_metadata             map[last_rotated:2026-10-21 owner:platform-team]
```

but five later transcripts in §10 (the §10.1 write, the §10.2 rollback,
the §10.2 "get current", the §10.2 "get -version=3", and the §10.3 write)
all still showed the pre-patch `map[owner:platform-team rotation:90d]`.
A reader replaying the module would hit a different `custom_metadata` in
§10 than the module shows.

**Fixed:** §10 was **re-captured live** against the post-§9.2 state. All
five occurrences now read `map[last_rotated:2026-10-21 owner:platform-team]`.
The §9 transcript (§9's own `metadata put` result) correctly still shows the
pre-patch `map[owner:platform-team rotation:90d]` and was left alone.

The re-capture also confirmed the rest of §10 unchanged: §10.1 → version 3,
§10.2 rollback → version 4, §10.2 `get -version=3` → version 3 still
readable, §10.3 `-cas=4` → version 5 with a `deletion_time` of +168h, and
both rollback refusals (`Cannot roll back to a version that has been
deleted`).

### F5 — §15: the "how I verified it" output was unreproducible

The module claimed:

```console
$ grep -o '"vault.cluster.secrets[^"]*","[^"]*"' all.js | sort -u
"vault.cluster.secrets","Secrets engines"
```

That literal string **does not exist in the bundle**. The real output is
**eight** lines, the first of which is:

```console
$ grep -o '"vault.cluster.secrets[^"]*","[^"]*"' all.js | sort -u
"vault.cluster.secrets","vault.cluster.secrets vault.cluster.settings.mount-secret-backend vault.cluster.settings.configure-secret-backend"
"vault.cluster.secrets.backend","policy-show"
"vault.cluster.secrets.backend","secrets-cert"
"vault.cluster.secrets.backend.","credentials"
"vault.cluster.secrets.backend.create-root","connection"
"vault.cluster.secrets.backend.create-root","role"
"vault.cluster.secrets.backend.list","show"
"vault.cluster.secrets.backend.show","show"
```

The **conclusion** was right — the nav item really is called
**Secrets engines** — but the **evidence** was wrong: the grep shows
*routes*, and the label lives in a *different* array in the nav template.

**Fixed:** §15 now shows the real eight-line grep output, explains *why* it
is the wrong tool for this job (the route array is a three-element list —
"current route, plus the sibling routes that also light up the nav item" —
and the human-readable label is a separate array), and gives the grep that
actually finds the label:

```console
$ grep -oE '.{0,60}"Secrets engines".{0,60}' all.js
et-backend vault.cluster.settings.configure-secret-backend","Secrets engines"]],null],[1,"\\n"],[41,[28,[37,2],["access"],null],[[[1,"
```

The surrounding sentence was also corrected: it used to say "I pulled the
route → label pairs out of the UI's own JavaScript bundle"; it now says "I
pulled the nav templates out of the UI's own JavaScript bundle", which is
what the evidence actually shows.

---

## 3. What was checked in round 2 and confirmed correct (no edit)

| Claim | Section | Result |
|---|---|---|
| the `metadata_cas` write in §8.7 uses `current_metadata_version` as its CAS value | §8.7 | ✅ the live replay read `1` and used it |
| §9's `metadata put` produces `map[owner:platform-team rotation:90d]` | §9 | ✅ |
| §9.2's `metadata patch` produces `map[last_rotated:2026-10-21 owner:platform-team]` and bumps the metadata counter | §9.2 | ✅ |
| §10.1 → version 3, §10.2 rollback → version 4, the bad version 3 still readable | §10.1, §10.2 | ✅ re-captured live |
| §10.3 `-cas=4` → version 5 with `deletion_time` = created_time + 168h; both rollback refusals | §10.3 | ✅ re-captured live |
| §16.9's final state on a fresh mount: `current_version 4`, `current_metadata_version 1`, `custom_metadata map[owner:platform-team rotation:90d ticket:MER-1841]`, the `<mount>/config` read, `kv list ai/platform`, and the `kv get` of the Gemini key | §16.9 | ✅ **replayed the whole §16 lab live** — every line matches |
| §16.7's `metadata_cas=0` on a fresh secret, §16.10's `put -cas=1` + `patch -cas=2` → version 3 | §16.7, §16.10 | ✅ (round 1) |
| the `default` `delete_version_after` / `max_versions` / `cas_required` reads | §7, §10.4 | ✅ (round 1) |
| the four CAS error messages | §8.2, §8.3, §8.7 | ✅ (round 1) |
| `delete_version_after` → HTTP 200 then HTTP 404 with `data.data: null` | §12.1 | ✅ (round 1) |
| `max_versions=3` pruning progression (`oldest_version` 0→4) | §10.4 | ✅ (round 1) |
| `kv` vs `kv-v2` proof, `enable-versioning` upgrade, the three v1 errors | §3.1–§3.4 | ✅ (round 1) |
| `<mount>/config` vs `sys/mounts/…/tune` silent no-op | §7.1, §7.2 | ✅ (round 1) |
| `kv delete -version=1` → `flag provided but not defined: -version` | §11.1 | ✅ (round 1) |
| `kv undestroy` → the `Usage: bao kv <subcommand>` help | §11.4 | ✅ (round 1) |
| the real GUI version-menu labels: **Undelete**, **Delete**, **Destroy**; no rollback button | §15 | ✅ (round 1, fixed there) |
| `sys/internal/ui/mounts/ai/platform` → `options.version = "2"` | §15 | ✅ (round 1) |
| `GET /ui/` → HTTP 200 | §15 | ✅ (round 1) |
| the `Invalid path for a versioned K/V secrets engine…` warning on a wrong-path LIST | §14.1 | ✅ (round 1) |
| the audit log HMACs the *key names* on a list | §9.1, §14.1 | ✅ (round 1) |

---

## 4. Commands actually run in round 2 (verbatim)

```bash
# start a private OpenBao 2.7.1 instance on its own port and data dir
# with BAO_ADDR / BAO_TOKEN / BAO_BIN exported for that instance
bao secrets disable ai/platform
bao secrets enable -path=ai/platform kv-v2
bao kv put ai/platform/llm/gemini api_key=… model=… project_id=…          # §4
bao kv put -cas=0 ai/platform/db/postgres …                                # §4.2
bao kv put -cas=0 ai/platform/cache/redis …                                # §4.2
bao kv put -cas=0 ai/platform/oidc/keycloak …                              # §4.2
bao write ai/platform/config cas_required=true max_versions=10 delete_version_after=0s   # §7.2
bao kv put -cas=1 ai/platform/llm/gemini …                                 # §8.4
bao write ai/platform/metadata/llm/gemini cas_required=false               # §8.6
bao write ai/platform/config metadata_cas_required=true                    # §8.7
mc=$(bao kv metadata get -format=json ai/platform/llm/gemini | jq -r '.data.current_metadata_version')
echo "{\"metadata_cas\":$mc,\"custom_metadata\":{\"owner\":\"platform-team\"}}" \
  | bao write ai/platform/metadata/llm/gemini -                            # §8.7
bao write ai/platform/config metadata_cas_required=false
bao kv metadata put -custom-metadata="owner=platform-team" \
  -custom-metadata="rotation=90d" ai/platform/llm/gemini                    # §9
bao kv metadata patch -custom-metadata="last_rotated=2026-10-21" \
  -remove-custom-metadata="rotation" ai/platform/llm/gemini                 # §9.2

# read the counters back at every step
bao kv metadata get -format=json ai/platform/llm/gemini \
  | jq -r '.data | "current_version=\(.current_version) current_metadata_version=\(.current_metadata_version)"'

# --- re-capture §10 against the post-§9.2 state ---
bao kv put -cas=2 ai/platform/llm/gemini … model="gemini-1.0-pro" …        # §10.1
bao kv rollback -version=2 ai/platform/llm/gemini                            # §10.2
bao kv get ai/platform/llm/gemini
bao kv get -version=3 ai/platform/llm/gemini
bao write ai/platform/config delete_version_after=168h
bao kv put -cas=4 ai/platform/llm/gemini … model="gemini-1.0-pro" …        # §10.3
bao kv rollback -version=5 ai/platform/llm/gemini                            # -> "deleted"
bao write ai/platform/config delete_version_after=0s
bao kv rollback -version=5 ai/platform/llm/gemini                            # -> still "deleted"

# --- replay the whole §16 lab on a fresh mount ---
bao secrets disable ai/platform && bao secrets enable -path=ai/platform kv-v2
bao write ai/platform/config cas_required=true max_versions=10 \
  delete_version_after=0s metadata_cas_required=true
bao kv put -cas=0 … (four secrets)
echo '{"metadata_cas":0,"custom_metadata":{…}}' | bao write ai/platform/metadata/<path> -   (×4)
bao kv put -cas="$v" … ; bao kv put -cas=2 … ; bao kv rollback -version=1 …
bao read ai/platform/config ; bao kv list ai/platform ; bao kv get ai/platform/llm/gemini
bao kv metadata get -format=json ai/platform/llm/gemini | jq -r '.data | …'

# --- the GUI evidence ---
cd the UI bundle chunks
grep -o '"vault.cluster.secrets[^"]*","[^"]*"' all.js | sort -u
grep -oE '.{0,60}"Secrets engines".{0,60}' all.js
```

---

## 5. What I could NOT verify — stated plainly

1. **The rendered GUI.** The label strings and the API behind each screen
   were verified against the shipped bundle; the browser UI was not
   clicked through. §15 says so.
2. **Whether the bundle's byte layout is stable.** The eight-line grep
   output in §15 is a real capture, but the bundle is a build artefact —
   a future OpenBao release will re-minify it and the exact strings will
   move. The *labels* are the stable thing; the greps are how to find them
   again.
3. **`§10.4`'s `max_versions` progression and `§12.1`'s 10-second expiry**
   were verified in round 1 and not re-run in round 2; nothing in round 2
   touched those code paths.
4. **The claim that `delete_version_after` does not physically erase the
   ciphertext.** §12.2 already labels this as explicitly *not verified*;
   I confirmed only the read-time 404.
5. **The `9185` port and every timestamp / `created_time` / accessor in the
   transcripts** are captures from the author's instance and are not
   reproducible. The module does not claim otherwise.
6. **The §16.9 final state is reproduced from a replay of the §16 lab, not
   from the author's original run.** The *values* match; the timestamps and
   accessors do not, and the module does not claim they would.
