# HOUSE STYLE — Meridian AI OpenBao Course

Every module is written by a different agent. This guide is what makes them
read like one course taught by one teacher. Follow it exactly.

---

## 1. Audience and voice

- **Reader:** a total beginner who is smart, has never used OpenBao, and is
  building an enterprise AI platform (FastAPI + LangChain + Gemini +
  Postgres + Redis + Keycloak). They know Python and Docker. They do NOT
  know secret management, PKI, HSM, KMS, or Shamir's Secret Sharing.
- **Tone:** a senior engineer sitting next to them at the screen. Warm,
  direct, never condescending, never breathless.
- **Second person, imperative.** "Run this", "Notice what happened", "Now
  here's why that matters." Not "one might consider" or "it could be argued".
- **No filler.** Delete every sentence that doesn't teach something.
- **Emoji: essentially none.** Use them only for a single ✅/❌ marker in a
  table, never in prose.

---

## 2. The story

Everything happens inside one company:

> **Meridian AI** sells an enterprise AI assistant platform. A previous
> engineer left secrets in a `.env` file that was committed to Git. You are
> the first platform engineer hired since. You're building the secret store
> properly, from zero, and doing it in a way that would survive a security
> review.

Use this framing constantly. Every module opens with **where we are now** in
that story and closes with **what the company can now do that it couldn't
before**. Concrete Meridian AI artifacts to reuse consistently:

| Artifact | Value to use |
|---|---|
| Gemini API key | `AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr` |
| Postgres password | `Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK` |
| Redis password | `Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU` |
| Keycloak client secret | `meridian-ai-harness-client-secret-rotate-me` |
| Mount layout | `ai/platform/` (kv-v2), `ai/transit/` (transit), `ai/pki/`, `ai/ssh/`, `ai/database/` |
| Secret paths | `ai/platform/llm/gemini`, `ai/platform/db/postgres`, `ai/platform/cache/redis`, `ai/platform/oidc/keycloak` |
| Services | `ai-harness` (FastAPI), `data-pipeline`, `secret-rotation-bot`, `platform-operator`, `platform-admin` |
| Keycloak realm | `meridian-ai`, client `ai-harness`, users `aisha.rahman`, `dev.kapoor` |
| DB | `meridian_ai` / user `meridian_app` |

**NEVER use `foo`, `bar`, `baz`, `test`, `hello`, `mysecret`, `changeme`,
`your-secret-here`, or `random-string`.** Realistic values only. A learner
must be able to imagine pasting them into a real system.

---

## 3. Module structure (required skeleton)

```markdown
# Module NN — <Title>

> **Where we are.** 2–4 sentences: the story position, what the previous
> module left us with, what this module unlocks.

**Status:** what this module covers (or omit if fully written).

---

## 0. The 60-second version        ← table of every concept, one line each
## 1. <Why this matters>            ← the problem, concretely
## 2. <Core concept>                ← teach the idea before the command
## 3. <Do it>                       ← commands + real output
...
## N. What you learned              ← checkbox list
## N+1. What's next                 ← 2–3 sentences pointing to the next module
## N+2. Homework                    ← 3–5 concrete, runnable tasks
```

Adapt the middle sections to the topic, but keep: **the 60-second version,
a "why" before every "how", a "what you learned" checklist, a "what's next",
and homework.**

---

## 4. The core-concept rule (non-negotiable)

**Teach the concept BEFORE the command. Every time.**

The user's explicit ask is: *"I want you to teach me like I am a total
beginner… At each level I want you to teach me the core concepts and explain
everything in details but in an easy to understand way while giving all
practical commands."*

So for every non-obvious concept, use this four-beat shape:

1. **The concept in one plain sentence** (no jargon)
2. **Why it exists** (the problem it solves)
3. **What breaks if you don't use it** (concrete consequence)
4. **The command** (with real output)

Example shape:

> **What is a mount?** A mount is a named, isolated place inside OpenBao where
> one kind of secret lives.
>
> *Why it exists:* so that "the Gemini key" and "the database password"
> aren't just strings in one undifferentiated pile. Each engine enforces its
> own rules about how things are stored, leased, and revoked.
>
> *What if you skipped it:* everything would be in one generic bucket, and
> you could never give the AI harness access to the Gemini key without also
> giving it the database password.
>
> ```bash
> bao secrets enable -path=ai/platform kv-v2
> ```

---

## 5. Output blocks must be REAL

Every fenced block that shows terminal output must be **actual output you
captured by running the command**. Format it the way the terminal shows it.

Rules:
- Use the real key/value column layout of `bao` where applicable.
- If the output depends on values you generated (secrets, tokens, IDs), use
  the realistic Meridian AI values from the table above so the learner sees
  something that looks like their future reality.
- **Never** present output you did not observe. If a command's output
  depends on a random value, show a representative one and make clear it
  differs per run.
- When showing an **error**, show the **exact** error text. This is
  high-value: learners can pattern-match the real error. A wrong error
  message teaches them to distrust the material.

---

## 6. The "what breaks" / production angle

The user asked for *"what happens if we don't, how to do it, when to do it"*
and *"what is recommended for production, what are the security best
practices"*.

So each major practice gets a short, opinionated note. Use a consistent
visual marker:

> **Production:** *What you should actually do, and why.*

And for trade-offs, be honest — a course that only says "X is good" is not
teaching judgment:

> **Trade-off:** *What you gain, what you give up, and when to choose each.*

---

## 7. Version awareness

The course is pinned to **OpenBao 2.7.1**. Where behavior changed, call it
out explicitly with a marker like:

> ⚠️ **Changed in 2.7:** *What it used to do, what it does now, and what to
> do if you meet the old behavior.*

And when a Vault-era tutorial would mislead the reader, say so directly:

> **If you find a tutorial saying X:** *it is describing HashiCorp Vault.
> OpenBao 2.7 does Y.*

---

## 8. CLI gotcha callouts

Several OpenBao CLI behaviors reliably trip people up. When your module
touches one, include a short callout with the exact error text. The
recurring ones:

- Flags before positionals
- `-format=json`, not `-f=json`
- `<mount>/config` vs `sys/mounts/<path>/tune`
- `kv` vs `kv-v2`
- `text=` vs `-text=` in wrapping
- `token=` is a data field, not a flag

---

## 9. GUI coverage

The user explicitly wants to be comfortable in **both the GUI and the CLI**.
Every module that touches a GUI surface must include a section like:

> ### The GUI for this module
>
> Open <http://127.0.0.1:8200/ui> → **…path…** and you will see …
>
> | GUI | CLI equivalent |
> |---|---|
> | … | `bao …` |

Include the real menu path (e.g. **Secrets → ai/platform → llm → gemini**)
and note anything the GUI does *not* expose — those are the reasons the CLI
is primary.

---

## 10. Formatting rules

- **Tables** for comparisons. Tables are the fastest way to teach a beginner.
- **Fenced code blocks** with a language tag: `bash`, `hcl`, `json`, `python`.
- **Bold** for the term being defined the first time.
- **Callouts** use `>` blockquote with a bold lead-in.
- **Checklists** use `- [ ]` for homework and "what you learned".
- No emoji in prose. No "Let's dive in!" No "Trust me, this is exciting."
- Do not use the word "simply", "just", or "obviously" when something is
  actually subtle — that word teaches people to skip the part that matters.

---

## 11. Length and depth

Target **600–1000 lines** of markdown per module. That is deep, not padded.
A module is done when a beginner could follow it top to bottom and end up
with a working, explained, production-shaped setup — not when it hits a
line count.

Depth means:
- Multiple real exercises, not one demo.
- Failure modes demonstrated, not just happy paths.
- The "why" behind every default.
- A homework section that requires real thought.

---

## 12. Cross-linking

Link to the previous and next module by relative path, e.g.
`[Module 02 — KV v2 Secrets](../modules/02-kv-secrets/README.md)`.

---

## 13. Honesty rules

- If you did not verify something, don't state it as fact — either verify it
  or omit it.
- If OpenBao's behavior is surprising, say that it's surprising and explain
  the design reason.
- If something is genuinely a judgment call with no single right answer,
  present both sides and recommend one.
