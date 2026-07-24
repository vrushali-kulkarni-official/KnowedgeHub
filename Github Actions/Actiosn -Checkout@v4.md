The `@v4` in:

```yaml
uses: actions/checkout@v4
```

specifies **which version of the GitHub Action to use**.

Think of it like installing a specific version of a package.

For example:

```text
npm install react@19
pip install django==5.2
docker pull nginx:1.29
uses: actions/checkout@v4
```

In all four cases, you're saying **"use this version."**

---

# General syntax

Every GitHub Action follows this format:

```yaml
uses: owner/repository@version
```

Example:

```yaml
uses: actions/checkout@v4
```

Breakdown:

```
actions      -> GitHub organization (owner)
checkout     -> Repository containing the action
v4           -> Version (Git tag)
```

So GitHub downloads the **version 4** release of the `actions/checkout` action.

---

# Why specify a version?

Imagine you wrote this:

```yaml
uses: actions/checkout
```

Which version should GitHub use?

* version 1?
* version 2?
* latest?
* tomorrow's latest?

Nobody knows.

If GitHub automatically used the latest version, your workflow could suddenly break after an update.

Instead, you explicitly choose the version.

```yaml
uses: actions/checkout@v4
```

This makes your workflow more stable and reproducible.

---

# What exactly is `v4`?

It is a **Git tag** in the `actions/checkout` repository.

For example, the repository may contain tags like:

```
v1
v2
v3
v4
```

Each tag points to a particular version of the action's code.

So when your workflow runs, GitHub fetches the code associated with the `v4` tag.

---

# Can I use more specific versions?

Yes.

Instead of the major version:

```yaml
uses: actions/checkout@v4
```

you can specify an exact release tag, for example:

```yaml
uses: actions/checkout@v4.2.2
```

Or even a specific commit SHA:

```yaml
uses: actions/checkout@8ade135a41bc03ea155e62e844d188df1ea18608
```

This is the most secure option because the code can never change.

---

# Why do most examples use `v4` instead of `v4.2.2`?

GitHub maintains the major-version tag.

For example:

```
v4
 │
 ├── v4.0.0
 ├── v4.1.0
 ├── v4.2.0
 └── v4.2.2
```

When a new **backward-compatible** release is published, GitHub updates the `v4` tag to point to the latest v4.x release.

So if today:

```
v4 → v4.2.2
```

and next month:

```
v4 → v4.2.3
```

your workflow automatically gets bug fixes and security patches **without jumping to version 5**, where breaking changes might exist.

---

# What happens when `v5` is released?

Your workflow:

```yaml
uses: actions/checkout@v4
```

**will continue using the latest v4.x release.**

It **will not** automatically switch to v5.

To use v5, you must explicitly update your workflow:

```yaml
uses: actions/checkout@v5
```

This protects your workflow from unexpected breaking changes.

---

# Summary

| Version         | Meaning                                           | Updates automatically?                           |
| --------------- | ------------------------------------------------- | ------------------------------------------------ |
| `@v4`           | Latest compatible release in the v4 major version | ✅ Yes (only within v4.x)                         |
| `@v4.2.2`       | Exact release                                     | ❌ No                                             |
| `@<commit-SHA>` | Exact commit                                      | ❌ No (most reproducible and secure)              |
| `@main`         | Latest code on the `main` branch                  | ✅ Yes (not recommended for production workflows) |

For most projects, **`@v4` (or the latest major version such as `@v5` when you intentionally upgrade)** is the recommended balance between stability and receiving bug fixes and security updates automatically.
