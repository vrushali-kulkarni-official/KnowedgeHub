# Glossary

Every term the course uses, in plain language, with a pointer to where it
first appears and why anyone would care.

**How to read a pointer.** `M03 §2.4` means Module 03, section 2.4. The
pointers were located with a word-boundary search across the nine module
files in course order, so "first appears" means the first place a learner
meets the word — not the first place it is defined. A term usually gets its
proper definition a few sections after its first appearance, and the pointer
tells you where to *start* looking.

Terms are ordered alphabetically. Cross-references point to other entries in
this file.

---

## A

**accessor** — A stable, non-secret handle for a token. You can look a token
up by accessor without ever handling the token itself, which is how you
revoke a leaked token without knowing its value.
*First appears:* M01 §6.5. *Why it matters:* accessors are what you put in
an audit log or a revocation job. The token value never leaves the client.

**ACL (Access Control List)** — The set of rules that decide which
operations a token may perform on which paths.
*First appears:* M01 §0 (the 60-second table). *Why it matters:* in
OpenBao, "the ACL" is the policy engine; if you understand the ACL model you
understand every 403 you will ever see.

**allow-list** — A rule that grants access to an explicitly named set of
paths, rather than denying a named set. OpenBao's default posture is
deny-by-default; an allow-list is how you make something readable.
*First appears:* M02 §18. *Why it matters:* the difference between an
allow-list and a deny-list decides whether a typo in a policy opens a
door or does nothing.

**AppRole** — The auth method for machine identities. A workload proves
itself with a `role_id` (identifies *which* role) and a `secret_id`
(proves *this request* is allowed to use it).
*First appears:* M01 §8.3. *Why it matters:* it is how a container gets a
scoped token without a human and without a long-lived credential baked into
the image.

**audit device** — A sink that receives a record of every request the server
handles. In 2.7.1 devices are declared in the server configuration file and
cannot be added at runtime.
*First appears:* M01 §0. *Why it matters:* an audit log is the only
independent evidence of who did what. If your secrets leak, this is what
tells you how.

**audit log** — The stream of records a device writes.
*First appears:* M01 §3.6. *Why it matters:* it records requests, not
responses — the server never writes a secret value into it.

**auto-unseal** — A mode where the server unlocks itself using a key held
by an external system (a KMS, or another OpenBao cluster) instead of human
key shares.
*First appears:* M01 §4.4. *Why it matters:* it removes humans from the
restart path, at the cost of a dependency you now have to keep alive.

---

## B

**barrier** — The encryption boundary around OpenBao's storage. Inside it,
everything is encrypted; outside it (on disk, in a snapshot, in a backup)
you get ciphertext.
*First appears:* M01 §0. *Why it matters:* it is the answer to "what does an
attacker get if they steal the disk?"

**break-glass** — The emergency path for getting a root token when normal
authentication is unavailable. Named after the glass you break to reach a
fire extinguisher: it is for emergencies only, and it is audited.
*First appears:* M01. *Why it matters:* you need one before you need it.

---

## C

**capability** — One operation on one path: `read`, `list`, `create`,
`update`, `patch`, `delete`, `sudo`, `list` on `sys/…`, and so on.
*First appears:* M01 §3.5. *Why it matters:* policies are made of
capabilities, and "can it read?" is always really "which capabilities, on
which path?"

**certificate authority (CA)** — The signer that issues certificates. In
PKI a *root* CA signs an *intermediate*, which signs leaf certificates.
*First appears:* M08 §0. *Why it matters:* you can hand the intermediate to
a team without handing over the root.

**check-and-set (CAS)** — A write that only succeeds if the secret is still
at the version the writer believes it is. It is the compare-and-swap of
secret storage.
*First appears:* M01 §11. *Why it matters:* it is what stops a rotation job
and a human from silently clobbering each other.

**convergent encryption** — Encryption where the same plaintext always
produces the same ciphertext, so you can look a value up without decrypting
the whole store. It requires a per-record nonce.
*First appears:* M06 §7.10. *Why it matters:* it enables searching an
encrypted database — and it leaks equality, which is sometimes not acceptable.

**control group** — New in OpenBao 2.7. A policy can require a *second
person* to approve a sensitive operation before it takes effect.
*First appears:* M03 §0. *Why it matters:* it is a two-person rule for
paths too dangerous for one operator.

**CRL (Certificate Revocation List)** — A signed list of certificates the
CA has revoked.
*First appears:* M04 §5.5. *Why it matters:* certificates expire on a
schedule; a CRL is what tells relying parties that one was revoked *before*
it expired.

---

## D

**datakey** — A key generated by Transit and handed to your application to
encrypt one piece of data. The plaintext key never enters the secret store;
the wrapped form does.
*First appears:* M06 §0. *Why it matters:* it is the envelope-encryption
pattern — the shape you want for data you must encrypt but cannot store.

**deny** — An explicit hole punched in a grant. A `deny` overrides every
other rule on that path.
*First appears:* M03 §0. *Why it matters:* it is the one capability you
cannot grant around. Module 03 §2.3 works through how it interacts with
allow-lists.

**destroy** — Permanently remove a secret version, not just its metadata.
*First appears:* M01 §2.1. *Why it matters:* `delete` hides a version and
can be undone; `destroy` cannot.

---

## E

**entity** — A record in OpenBao's identity store that represents *who
something is*, independent of how it authenticated. One entity can have
several aliases (one per auth method) and belong to several groups.
*First appears:* M03 §2.4. *Why it matters:* it lets you say "this person
or this service must present MFA" once, instead of once per login method.

**external key** — A key whose private half lives outside OpenBao — in an
HSM, a KMS, or another cluster — so OpenBao can use it without ever
holding it.
*First appears:* M06 §7.13. *Why it matters:* it is the difference between
"we encrypt your data" and "we cannot possibly read your data."

---

## G

**group** — A named set of entities in the identity store, used to grant
access or to scope MFA enforcement.
*First appears:* M01 §3.4. *Why it matters:* it is how you grant to a team
rather than to a list of people.

---

## H

**HA (High Availability)** — Running multiple OpenBao nodes that share
storage, so a single node failure does not take the service down.
*First appears:* M01. *Why it matters:* availability is a security
property too — a store that is down is a store people work around.

**HMAC** — A keyed message authentication code. OpenBao uses one to prove a
value was produced by the server and not tampered with, without revealing
the value.
*First appears:* M01 §9.4. *Why it matters:* it is how the audit log
records that a secret was read without recording the secret.

---

## I

**identity store** — The built-in directory of entities, groups and
aliases. It is not a login system — it is the *book of who*.
*First appears:* M02 §3.2. *Why it matters:* it is what lets an OIDC
login and a userpass login end up being the same person.

**init** — The one-time process that turns a fresh, empty server into a
usable one: it creates the root token, the unseal key shares and the
storage barrier key.
*First appears:* M01 §2.2. *Why it matters:* it is the moment the only
moment — you can choose how many people hold a share.

**intermediate CA** — A certificate authority signed by the root CA, which
in turn signs leaf certificates.
*First appears:* M03 §9.5. *Why it matters:* compromise the intermediate
and you rotate one thing, not the root.

---

## K

**key shares** — The pieces a Shamir secret is split into during `init`.
Each share is useless alone; any `threshold` of them unseal the server.
*First appears:* M01 §4.1. *Why it matters:* it is how you split root
authority across people without giving anyone the root.

**key rotation** — Replacing a key with a new one while keeping the old one
usable for decryption.
*First appears:* M01 §9.2. *Why it matters:* you want to change keys on a
schedule, and you want old ciphertext to keep working.

---

## L

**lease** — OpenBao's record that a credential was issued and when it must
be revoked. A lease has a TTL, a max TTL, and a renewal path.
*First appears:* M01 §0. *Why it matters:* it is how a secret store knows
what to clean up — and how it stops handing out credentials that outlive
their purpose.

**least privilege** — Granting exactly the access a workload needs, and
nothing else.
*First appears:* M01 §0. *Why it matters:* it is the entire subject of
Module 03.

**listener** — A network socket the server accepts API requests on.
*First appears:* M01 §3.6. *Why it matters:* where a listener binds is a
security decision — loopback only in the lab.

---

## M

**max_ttl** — The ceiling on how long a credential can be kept alive by
renewal, however many times it is renewed.
*First appears:* M04 §0. *Why it matters:* without it, a renewable
credential is effectively permanent.

**metadata** — The layer of a KV v2 secret that records versions, creation
times, custom metadata and deletion state — but never the secret value.
*First appears:* M01 §11. *Why it matters:* reading metadata is safe to
grant to a lot of people; reading data is not.

**min_decryption_version** — The oldest key version Transit will decrypt
with. Raise it to make old ciphertext permanently unreadable.
*First appears:* M06 §0. *Why it matters:* it is the cryptographic
version of "burn the bridge behind you".

**MFA (Multi-Factor Authentication)** — A second factor on top of a
password.
*First appears:* M01 §8.2. *Why it matters:* it is the control that
survives a leaked password.

---

## N

**namespace** — An isolated slice of the whole OpenBao hierarchy: its own
mounts, its own policies, its own auth methods. Nothing in one namespace can
see another.
*First appears:* M01 §8.2. *Why it matters:* it is multi-tenancy without
running multi-tenancy.

**nonce** — A single-use random value that makes an otherwise repeatable
operation unique.
*First appears:* M01 §5.1. *Why it matters:* it is what makes
authenticated encryption safe to use on the same value twice, and what
makes a one-time password one-time.

**notAfter** — The field in an X.509 certificate that says when it expires.
*First appears:* M04 §5.5. *Why it matters:* it is the certificate's own
expiry, independent of any OpenBao lease that tracks it.

---

## O

**OIDC (OpenID Connect)** — An identity layer on top of OAuth 2.0 that
lets an application delegate login to an existing identity provider and
receive a signed ID token.
*First appears:* M01 §8.2. *Why it matters:* it is how Meridian AI uses
Keycloak for humans instead of maintaining its own password database.

**OTP (one-time password)** — A short code valid for a single use or a
short window.
*First appears:* M01 §6.2. *Why it matters:* it is the mechanism behind
`generate-root`, and it is why a wrong OTP can produce a plausible-looking
but broken token.

---

## P

**path** — The address of a secret or an endpoint in the hierarchy, such as
`ai/platform/llm/gemini`. Policies are written in terms of paths.
*First appears:* M01. *Why it matters:* almost every permission question in
OpenBao is really a question about paths.

**pebbledb** — The default durable storage backend in 2.7.1, used by the
single-node lab.
*First appears:* M01 §0. *Why it matters:* it replaced the `file` backend
that older tutorials still use.

**PKI** — Public Key Infrastructure: the machinery of issuing, distributing
and revoking certificates.
*First appears:* M02 §2. *Why it matters:* it is how you stop shipping
`-----BEGIN PRIVATE KEY-----` blocks around your estate.

**plugin** — An add-on that is not in the base binary. In 2.7.1 the KMS
seals and the Kerberos and LDAP integrations are plugins.
*First appears:* M01 §9.3. *Why it matters:* "it is not in my binary" is
usually the explanation for a feature that seems to be missing.

**policy** — A named set of rules, written in HCL, that grants or denies
capabilities on paths.
*First appears:* M01 §0. *Why it matters:* policies are the only place
access is decided.

**policy name** — The identifier of a policy. Names are global within a
namespace and are what a token references.
*First appears:* M03 §2.1. *Why it matters:* a typo in a policy name is a
silent failure — the token simply has no rules from that policy.

---

## R

**raft** — The integrated storage backend that lets several OpenBao nodes
share one consistent store. The HA option.
*First appears:* M01 §3.3. *Why it matters:* it is the difference between
one server that is highly available and several servers that are.

**recovery key** — A key that can regenerate the root token without
unsealing the server. Shamir mode produces **none**; auto-unseal mode
produces them.
*First appears:* M01 §4.4. *Why it matters:* in 2.7.1, a tutorial that
tells you to save recovery keys from a Shamir init is describing an
older Vault, not this server.

**renewal** — Extending a credential's TTL before it expires.
*First appears:* M04 §5.4. *Why it matters:* renewal is how a short-lived
credential becomes long-lived, which is why `max_ttl` exists.

**response wrapping** — Returning a secret as a single-use token instead of
the value, so it can be passed through a channel that must not see it.
*First appears:* M03 §2.4. *Why it matters:* it is the safe way to hand a
secret to a process that should not have the value in its logs.

**role_id / secret_id** — The two halves of an AppRole credential.
`role_id` names the role and is not secret; `secret_id` is the secret
proof that is rotated per delivery.
*First appears:* M03 §3.2. *Why it matters:* treating them as one thing
leaks the role binding, and treating `role_id` as secret makes delivery
needless painful.

**root token** — An unsandboxed token with the `root` policy: it can do
everything and bypass every ACL check.
*First appears:* M01 §0. *Why it matters:* it is the thing an attacker
wants. Everything else in the course is about not having one lying around.

---

## S

**seal** — The state in which the server's storage is encrypted and locked.
A sealed server answers `503 Vault is sealed` to every request.
*First appears:* M01 §0. *Why it matters:* it is the default state after
every restart, and it is the whole point of the seal/unseal cycle.

**seal status** — The endpoint that reports whether the server is sealed
and how far the unseal process has got. The API returns `t` and `n`;
`bao status` prints `Threshold` and `Total Shares`.
*First appears:* M01 §8.2. *Why it matters:* it is the first thing to check
when the API returns 503, and the two naming schemes will trip up a script.

**secret engine** — A plugin that stores or generates a particular kind of
secret: KV, Transit, PKI, SSH, database.
*First appears:* M01 §8. *Why it matters:* "mount a KV engine" is the
mechanism behind every path you read.

**service token** — A token minted for a machine workload, as opposed to a
human session.
*First appears:* M06 §5.1. *Why it matters:* you can hold service tokens to
different rules — short TTL, no renewal, bound to one path.

**soft delete** — Removing a version's value while keeping its metadata
and the ability to restore it.
*First appears:* M01 §11. *Why it matters:* it is the difference between
"that secret is gone" and "that secret is not in use".

**storage backend** — Where the server keeps its data.
*First appears:* M01 §3.3. *Why it matters:* `file` was removed in 2.7.0;
`pebbledb` and `raft` are what exist now.

**sudo** — A capability that gates a small set of dangerous endpoints, such
as root-token generation.
*First appears:* M01 §6.6. *Why it matters:* it is the last line of
defence between a compromised operator token and total control.

**sys/mounts** — The endpoint that lists every mount and its configuration.
*First appears:* M01 §5.1. *Why it matters:* it is how you find out what
is actually mounted, and which KV version it is.

---

## T

**threshold** — How many key shares are needed to unseal. With 3 shares
and a threshold of 2, any 2 of the 3 holders can unseal the server.
*First appears:* M01 §2.2. *Why it matters:* it is the number that decides
how much of your team can collude without the server being safe.

**token** — A bearer credential. Whoever holds the value can use it; the
server cannot tell who it is beyond what the token's policies and identity
say.
*First appears:* M01 §0. *Why it matters:* it is the unit of everything in
OpenBao.

**token role** — A reusable configuration for tokens: TTLs, allowed
policies, whether renewal is permitted.
*First appears:* M04 §4.2. *Why it matters:* it stops every caller from
inventing their own TTL.

**TOTP (Time-based One-Time Password)** — A six-digit code from an
authenticator app, derived from a shared secret and the current time.
*First appears:* M05 §0. *Why it matters:* it is the second factor
Meridian AI's engineers use, and it is what `identity/mfa/method/totp`
creates.

**transit** — The engine that encrypts, decrypts, signs and generates data
*for* your application, without ever storing the plaintext.
*First appears:* M01 §4.4. *Why it matters:* it is the answer to "this
data cannot go in the secret store, so where does it go?"

**TTL (Time To Live)** — How long a credential stays valid.
*First appears:* M01 §2.3. *Why it matters:* every credential you issue
should have one, and it is the first thing a reviewer asks about.

---

## V

**versioning** — Keeping old copies of a secret so you can read them back
and roll back to them.
*First appears:* M02 §3.3. *Why it matters:* it turns "the secret is
gone" from a disaster into a rollback.

---

## W

**wrapping token** — A single-use token that stands in for a secret. You
unwrap it once and it is spent.
*First appears:* M01 (as "wrap token") and formally M03 §2.4. *Why it
matters:* it lets you hand a secret to a process without the process ever
being trusted with the value.

---

## Terms this course does not use

If you meet these elsewhere and wonder where they are: **SSCS** (a HashiCorp
storage-security comparison framework), **batch tokens** (a Vault token type
this course does not cover — it uses ordinary service tokens), and **root
protection** (Vault's `root_protection` parameter, which has no 2.7.1
equivalent in this course's lab). They are absent deliberately rather than
by oversight.
