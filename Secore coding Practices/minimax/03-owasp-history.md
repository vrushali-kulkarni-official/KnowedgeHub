# Part 3 — The OWASP Top 10 across the years
### How the list evolved, and what it teaches us

The OWASP Top 10 isn't a fixed truth. It's a *prioritization* that reflects which bugs are hurting the most people in a given era. By reading every version, you'll see two things:

1. **The same bugs keep coming back**, just renamed.
2. **New categories appear when an attack pattern gets too common to ignore** (deserialization in 2017, SSRF in 2021).

This file has all six historical lists with the CWE mapping, the *why-it-was-on-the-list* story, and a note on what each tells us today.

---

## Timeline at a glance

```
2003 ─── 2004 ─── 2007 ─── 2010 ─── 2013 ─── 2017 ─── 2021 ───► 2025?
 (10)    (10)     (10)     (10)     (10)     (10)     (10)     (?)
```

| Era | Theme | What was new |
|-----|-------|--------------|
| 2003 | "Web 1.0" — CGI scripts, PHP, classic LAMP | First list. SQLi, XSS, buffer overflows, CGI. |
| 2004 | Mostly the same, with broader scope | Added "Insecure Cryptographic Storage" and "Insecure Communications" |
| 2007 | AJAX era — JSON and JS clients | Added "Cross-Site Request Forgery", "Information Leakage" |
| 2010 | Cloud + APIs | Refactored: introduced "Injection" as a super-category. Added "Security Misconfiguration" |
| 2013 | API economy | Refactored again. CSRF moved down, API issues rising |
| 2017 | Frameworks & APIs | "Insecure Deserialization" added. XXE promoted |
| 2021 | Cloud-native, supply chain | "Insecure Design" added, "XXE" folded in, "SSRF" added. "Broken Auth" → "Identification and Authentication Failures" |
| 2025? | AI, supply chain | Possibly "Insufficient Software Supply Chain Security" |

> **Memorize this:** the list changes; the bugs don't. A SQLi in 2003 is the same SQLi in 2025. The list is a *nudge* to focus on what hurts the most.

---

## 2003 — the original list

| # | Title | CWE(s) | Modern equivalent |
|---|-------|--------|-------------------|
| 1 | Unvalidated Input | CWE-20, CWE-79, CWE-89, CWE-120, CWE-345 | A01, A03 |
| 2 | Broken Access Control | CWE-22, CWE-285, CWE-639 | A01 |
| 3 | Broken Authentication & Session Management | CWE-287, CWE-300, CWE-384 | A07 |
| 4 | Cross-Site Scripting (XSS) | CWE-79 | A03 |
| 5 | Buffer Overflow | CWE-120 | (not in top 10 — Python is safe; C/Rust still worry) |
| 6 | Injection Flaws | CWE-77, CWE-78, CWE-89, CWE-91 | A03 |
| 7 | Improper Error Handling | CWE-209, CWE-755 | A05 |
| 8 | Insecure Storage | CWE-311, CWE-312, CWE-326 | A02 |
| 9 | Denial of Service | CWE-400 | A04, A05 |
| 10 | Insecure Configuration Management | CWE-16 | A05 |

**What it teaches us in 2025:**
- "Unvalidated Input" as a single category had to be split — XSS, SQLi, command injection, and path traversal are *different* bugs with *different* fixes, and lumping them hid patterns.
- Buffer overflows were a *top-10 item* in 2003. Python made that category disappear. The lesson: **language choice is a security control.**
- "Insecure Storage" and "Insecure Configuration Management" both evolved into the modern A02 (crypto) and A05 (misconfig).

---

## 2004 — "Top Ten" released publicly

The first version officially branded as the "OWASP Top Ten". The list was nearly identical to 2003 but with these notable changes:

| # | Title | Note |
|---|-------|------|
| A1 | Unvalidated Input | unchanged |
| A2 | Broken Access Control | unchanged |
| A3 | Broken Authentication and Session Management | unchanged |
| A4 | Cross-Site Scripting (XSS) | unchanged |
| A5 | Buffer Overflows | unchanged |
| A6 | Injection Flaws | unchanged |
| A7 | Improper Error Handling | unchanged |
| A8 | Insecure Storage | **renamed from "Insecure Cryptographic Storage"** |
| A9 | Denial of Service | unchanged |
| A10 | Insecure Configuration Management | unchanged |

**What it teaches us in 2025:**
- 2004 was the year the list went "official". It's the oldest list you can still find a lot of material about.
- The same year introduced the **OWASP Testing Guide** and the **OWASP Code Review Guide** — the practical side.

---

## 2007 — the AJAX era

Major refactor. The list introduced categories that are still with us:

| # | Title | CWE(s) | Note |
|---|-------|--------|------|
| A1 | Cross-Site Scripting (XSS) | CWE-79 | **moved to #1** because XSS was exploding with AJAX |
| A2 | Injection Flaws | CWE-77, CWE-78, CWE-89, CWE-91 | |
| A3 | Malicious File Execution | CWE-434, CWE-78 | (file upload, file include) |
| A4 | Insecure Direct Object Reference | CWE-639 | **first appearance of IDOR by name** |
| A5 | Cross-Site Request Forgery (CSRF) | CWE-352 | **first appearance** |
| A6 | Information Leakage and Improper Error Handling | CWE-209, CWE-200, CWE-203 | merged two old items |
| A7 | Broken Authentication and Session Management | CWE-287, CWE-300 | |
| A8 | Insecure Cryptographic Storage | CWE-311, CWE-326 | |
| A9 | Insecure Communications | CWE-319 | **first appearance** (HTTPS) |
| A10 | Failure to Restrict URL Access | CWE-285, CWE-22 | |

**What it teaches us in 2025:**
- **IDOR** was first named in 2007 and is still A01 in 2021 — that's 18 years of being the #1 most-reported bug. It doesn't go away.
- **CSRF** first appeared in 2007 and stayed in the list until 2021 (when it was absorbed into A01). Today, CSRF is still very much a thing — just less so in pure-API apps using Bearer tokens, and very much so in cookie-auth apps.
- **Insecure Communications** (HTTPS) was new in 2007. The list *finally* dropped it in 2021 because TLS-by-default (Let's Encrypt) made it nearly universal. The lesson: **when a control becomes default, the list drops it.**

---

## 2010 — the API era, the first big refactor

This is when the list was substantially reorganized:

| # | Title | CWE(s) | Note |
|---|-------|--------|------|
| A1 | Injection | CWE-77, CWE-78, CWE-89, CWE-91, CWE-94 | **SQLi, command, LDAP, XPath all merged** |
| A2 | Cross-Site Scripting (XSS) | CWE-79 | |
| A3 | Broken Authentication and Session Management | CWE-287, CWE-300, CWE-384 | |
| A4 | Insecure Direct Object References | CWE-639 | |
| A5 | Cross-Site Request Forgery (CSRF) | CWE-352 | |
| A6 | Security Misconfiguration | CWE-16, CWE-260, CWE-732 | **first appearance of the modern A05** |
| A7 | Insecure Cryptographic Storage | CWE-311, CWE-326 | |
| A8 | Failure to Restrict URL Access | CWE-285, CWE-22 | |
| A9 | Insufficient Transport Layer Protection | CWE-319 | renamed from "Insecure Communications" |
| A10 | Unvalidated Redirects and Forwards | CWE-601 | **first appearance** |

**What it teaches us in 2025:**
- "Injection" became a *supercategory*. This is a model for the rest of the list — categories get broader over time.
- **Unvalidated Redirects** (A10) was new. Today, we call it "open redirect" and it's still a real bug (used in phishing chains).
- "Security Misconfiguration" entered the list — a sign that cloud and ops misconfigurations were starting to be a *bigger* source of breaches than code-level bugs. By 2021, that hypothesis was proven.

---

## 2013 — the API-economy refactor

| # | Title | CWE(s) | Note |
|---|-------|--------|------|
| A1 | Injection | CWE-77, 78, 89, 91, 94 | held at #1 |
| A2 | Broken Authentication and Session Management | CWE-287, 300, 384 | |
| A3 | Cross-Site Scripting (XSS) | CWE-79 | **moved down** because frameworks started mitigating it by default |
| A4 | Insecure Direct Object References | CWE-639 | **merged with A7 from 2010** ("Failure to Restrict URL Access") to form... |
| A4 | **Insecure Direct Object References** (now broader — incl. function-level) | | |
| A5 | Security Misconfiguration | CWE-16, 260, 732 | |
| A6 | Sensitive Data Exposure | CWE-200, 311, 312, 319, 359 | **first appearance** — merged crypto, comms, info disclosure |
| A7 | Missing Function Level Access Control | CWE-285, 862 | **split off from 2010's A8** |
| A8 | Cross-Site Request Forgery (CSRF) | CWE-352 | moved down |
| A9 | Using Components with Known Vulnerabilities | CWE-937, 1035, 1104 | **first appearance** — now A06 |
| A10 | Unvalidated Redirects and Forwards | CWE-601 | held |

**What it teaches us in 2025:**
- "Sensitive Data Exposure" (A6 in 2013) **became "Cryptographic Failures" (A02) in 2021** — the rename reflects a deeper understanding: it's not just that data was exposed, it's that the crypto was wrong.
- **Vulnerable Components (A9 in 2013, A06 in 2021)** was a major prediction. The Equifax breach (2017) was exactly this — a known Struts CVE. The list predicted the breach.
- CSRF moved down because Bearer-token APIs became common, but it didn't disappear. Any cookie-auth app today still needs CSRF protection.

---

## 2017 — frameworks, deserialization, and XXE

| # | Title | CWE(s) | Note |
|---|-------|--------|------|
| A1 | Injection | CWE-77, 78, 89, 91, 94 | held at #1 |
| A2 | Broken Authentication | CWE-287, 297, 384, 521, 613 | **renamed** ("and Session Management" removed) |
| A3 | Sensitive Data Exposure | CWE-200, 220, 311, 312, 319, 359, 532 | |
| A4 | XML External Entities (XXE) | CWE-611, 776 | **first appearance** |
| A5 | Broken Access Control | CWE-22, 284, 285, 639 | **A4 + A7 from 2013 merged here** |
| A6 | Security Misconfiguration | CWE-2, 16, 209, 260, 311, 434, 611, 643, 651, 732, 1004 | |
| A7 | Cross-Site Scripting (XSS) | CWE-79 | **moved down** dramatically — frameworks now auto-escape |
| A8 | Insecure Deserialization | CWE-502, 915 | **first appearance** — see Part 4 for the deep dive |
| A9 | Using Components with Known Vulnerabilities | CWE-937, 1035, 1104 | held |
| A10 | Insufficient Logging & Monitoring | CWE-223, 778, 117 | **first appearance** — now A09 |

**What it teaches us in 2025:**
- **XXE** was its own item in 2017. By 2021, it was *folded back* into A05 (Security Misconfiguration) and A03 (Injection). Lesson: a category that becomes a default-mitigated by every framework (most JSON APIs don't parse XML) gets folded in.
- **Insecure Deserialization** (A8 in 2017, A08 in 2021) was a banner year — `pickle.load` and `yaml.load` were causing real CVEs. This category is *not* going away; see Part 4.
- **XSS** moved from #3 (2013) to #7 (2017). Why? **React/Vue/Angular auto-escape by default.** The lesson: **frameworks are security controls**, and you can measure a framework's quality by where it moves the OWASP list.

---

## 2021 — the current list (deep-dive was in Part 2)

Recap of 2021 for the historical context:

| # | Title | Came from | Note |
|---|-------|-----------|------|
| A01 | Broken Access Control | A5 in 2017 | **moved up to #1** for the first time since 2010 |
| A02 | Cryptographic Failures | A3 in 2017 | renamed |
| A03 | Injection | A1 since forever | held |
| A04 | Insecure Design | (new) | brand new — design, not code |
| A05 | Security Misconfiguration | A6 in 2017 | held |
| A06 | Vulnerable & Outdated Components | A9 in 2017 (since 2013) | held |
| A07 | Identification & Auth Failures | A2 in 2017 | renamed |
| A08 | Software & Data Integrity Failures | (new) | mostly deserialization + supply chain |
| A09 | Security Logging & Monitoring Failures | A10 in 2017 | moved up |
| A10 | SSRF | (new) | first time |

**What it teaches us in 2025:**
- **A04 (Insecure Design)** is the new addition. It's *not* a code bug — it's a missing control. The 2021 list acknowledged that the industry has gotten better at code review and worse at architecture review.
- **A10 (SSRF)** is the new addition. SSRF was barely mentioned in 2017; by 2021 it was everywhere because of cloud-native architectures and the Capital One breach (2019) which was an SSRF against the AWS metadata service.
- **A08 (Integrity Failures)** swallowed 2017's deserialization. The rename is interesting: it's not about *deserialization specifically*, it's about *trusting unverified data*. This is why the SolarWinds and Codecov attacks get cited under A08.

---

## Putting the lists in order — what changed and why

```
2003: A1 unvalidated input ──────► 2021: A03 injection
       A2 broken access control ► 2021: A01 broken access control
       A6 injection ────────────► 2021: A03 injection
       A8 insecure storage ────► 2021: A02 cryptographic failures
       (no A09 until 2017) ────► 2021: A06 vulnerable components (since 2013)
       (no logging) ───────────► 2021: A09 logging/monitoring
       (no design) ────────────► 2021: A04 insecure design
       (no SSRF) ──────────────► 2021: A10 SSRF
```

**The four most enduring categories:**

1. **Injection** — 2003 to 2025, never out of the top 3. Even with ORM, devs still write `f"..."` into queries.
2. **Broken Access Control / IDOR** — 2003 to 2025, never out of the top 5. The most-reported bug, every year.
3. **Broken Auth** — 2003 to 2025, never out of the top 3. Because auth is hard.
4. **Crypto / Sensitive Data** — 2003 to 2025, evolving names. Because devs reach for the wrong tool.

**The five categories that came and went:**

- **Buffer Overflow (2003, 2004)** — gone, thanks to memory-safe languages.
- **Malicious File Execution (2007)** — gone, folded into misconfig + upload.
- **CSRF (2007–2017)** — gone from top 10, still real in cookie-auth apps.
- **XXE (2017)** — gone from top 10, still real in legacy XML APIs.
- **Unvalidated Redirects (2010–2013)** — gone from top 10, still real in phishing chains.

> **The pattern:** a category *leaves* the list when (a) most frameworks mitigate it by default, (b) developers understand the fix, and (c) the industry as a whole got collectively better. A category *enters* the list when a new pattern becomes common enough to deserve attention.

---

## What was on the lists but isn't anymore — and is still relevant

These are the categories that *left* the top 10 but are still very real:

| Exited | Why it left | Why it still matters |
|--------|-------------|----------------------|
| **CSRF** | Bearer tokens in pure APIs are immune | Any cookie-auth app, especially SSR |
| **XXE** | Most APIs are JSON | Legacy XML, SOAP, document parsers |
| **XSS** | React/Vue/Angular auto-escape | `dangerouslySetInnerHTML`, server-rendered HTML, email templates |
| **Buffer overflow** | Python/Java/Go | C/C++ code in dependencies, native extensions, WASM |
| **Unvalidated redirect** | Lower impact | Phishing chains, OAuth callback abuse |
| **Insufficient transport (HTTPS)** | Let's Encrypt made it free | Internal services, misconfigured TLS, missing HSTS |

---

## What was never on the list but is still important

The list is not exhaustive. Some things are too new, too rare, or too infrastructure-specific. We cover them in Part 4 and beyond:

- Race conditions / TOCTOU
- ReDoS (regex denial of service)
- Server-Side Template Injection (SSTI)
- JWT algorithm confusion
- OAuth misconfigurations
- Business-logic flaws
- Side-channel timing attacks
- Prototype pollution (JS) / class confusion
- Type juggling (PHP)
- HTTP smuggling
- Cache poisoning
- Clickjacking
- Tabnabbing
- Mixed-content issues
- DNS rebinding
- HTTP desync
- Web cache deception
- Subdomain takeover
- MFA bypass
- Deepfake/social engineering

---

## Takeaway

> The list is a *symptom*, not the *disease*. The disease is the ten principles in Part 1. Master the principles, and the list is just a checklist to keep you honest.

Now open `04-beyond-owasp.md` — the vulnerabilities that don't fit neatly in the Top 10, but that you'll see in real code reviews.
