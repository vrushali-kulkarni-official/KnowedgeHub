This is one of the most important topics in Git. If you understand branches properly, you'll understand how companies with hundreds or even thousands of developers can work on the same codebase without breaking each other's work.

I'll explain this exactly how I teach new software engineers in a company.

---

# Part 1 - Before We Talk About Branches

Let's first understand the problem.

Imagine you are writing a book.

Current book:

```
Book v1

Chapter 1
Chapter 2
Chapter 3
```

Now suppose:

* You want to add Chapter 4
* Your friend wants to fix spelling mistakes
* Another friend wants to redesign the cover

If everyone edits the same file simultaneously...

Chaos.

Someone overwrites someone else's work.

Git solves this problem.

---

# Part 2 - What is Git?

Git is simply a version control system.

Think of Git as a machine that remembers every version of your project.

```
Version 1
↓

Version 2
↓

Version 3
↓

Version 4
```

Every saved version is called a **commit**.

---

# Part 3 - What is a Branch?

Now imagine your project timeline.

```
Commit A
   |
Commit B
   |
Commit C
```

This is just one timeline.

A branch is simply another timeline.

Instead of editing the original timeline...

Git lets you create another timeline.

Example

```
Main

A ---- B ---- C
```

Create a branch called

```
feature-login
```

Now

```
Main

A ---- B ---- C

               \
                D ---- E
```

Notice something.

The new branch starts from C.

Now anything you do stays inside that branch.

Main is untouched.

---

This is the single most important concept.

A branch is NOT a copy of your project.

It is just another pointer moving through commits.

---

# Part 4 - Why Branches Exist

Suppose your website is already live.

Customers are using it.

You now want to build Dark Mode.

Would you write Dark Mode directly inside the production code?

No.

Because halfway through development your code may be broken.

Instead

```
Main (Production)

A ---- B ---- C
```

Create

```
dark-mode
```

Now

```
A ---- B ---- C (main)
               \
                D ---- E ---- F (dark-mode)
```

Customers still use

```
A-B-C
```

You continue working on

```
D-E-F
```

Once finished

Merge

```
A ---- B ---- C ---- G
               \     /
                D-E-F
```

Dark mode is now part of production.

---

# Part 5 - What is Main Branch?

The default branch of a repository.

Usually named

```
main
```

Older repositories may still use

```
master
```

Today almost everyone uses

```
main
```

Think of main as

"The official version of the project."

Example

```
main

Website currently running
```

If someone clones your repository

```
git clone
```

They usually receive the main branch.

---

# Part 6 - Is Main Always Production?

Not necessarily.

This is one of the biggest beginner misunderstandings.

Different companies use different strategies.

Sometimes

```
main = production
```

Sometimes

```
main = latest development
```

Sometimes

```
main = integration branch
```

We'll later see why.

---

# Part 7 - What is HEAD?

Another important concept.

HEAD means

> "Where am I currently working?"

Suppose

```
main

A-B-C
```

HEAD points to

```
C
```

```
HEAD
 ↓

A-B-C
```

Now switch branch

```
git checkout feature-login
```

HEAD moves.

```
feature-login

A-B-C-D-E

         ↑
       HEAD
```

HEAD is simply your current location.

---

# Part 8 - What is Origin?

This confuses everyone.

Let's simplify.

Git has

Local repository

and

Remote repository

Example

Laptop

```
Git Repository
```

GitHub

```
Git Repository
```

Git needs a nickname for GitHub.

By default

```
origin
```

Origin is just the nickname.

Nothing magical.

```
origin

↓

https://github.com/user/project.git
```

You can rename it.

```
origin

↓

mygithub
```

Still works.

---

# Part 9 - What is Remote?

A remote is simply another Git repository.

Your laptop

↓

Remote

GitHub

GitLab

Bitbucket

Azure DevOps

All are remotes.

---

Example

```
Local

↓

Remote 1
GitHub

↓

Remote 2
GitLab
```

Git can push to any remote.

---

# Part 10 - Can You Have Multiple Remotes?

Absolutely.

Example

```
origin
↓

GitHub

backup
↓

GitLab

company
↓

Company Server
```

Commands

```
git remote -v
```

Output

```
origin
backup
company
```

You can push separately.

```
git push origin main

git push backup main

git push company main
```

Very common.

---

# Part 11 - Local Branch vs Remote Branch

Very important.

Suppose GitHub has

```
main
```

You clone.

Now you have

```
Local

main
```

GitHub also has

```
origin/main
```

Notice

```
main
```

and

```
origin/main
```

are different.

```
main
```

is your local branch.

```
origin/main
```

is Git's record of what the remote branch looked like the last time you communicated with the remote (after fetch/pull).

---

# Part 12 - What is origin/main?

Suppose GitHub contains

```
Commit 10
```

Your laptop remembers

```
origin/main

Commit 10
```

Someone else pushes

```
Commit 11
```

GitHub now has

```
Commit 11
```

Your laptop still thinks

```
origin/main

Commit 10
```

Until

```
git fetch
```

Now

```
origin/main

Commit 11
```

Your local `main` doesn't automatically change with `fetch`; it only updates your knowledge of the remote.

---

# Part 13 - Professional Branch Naming

Never create branches like

```
test

new

branch1

final

abc

latest
```

Professionally

```
feature/login

feature/payment

feature/dashboard

bugfix/login-error

hotfix/security

release/v2.0.0

docs/api

refactor/auth

chore/docker

ci/github-actions
```

This immediately tells everyone the purpose of the branch.

---

# Part 14 - Common Branch Types

## Feature

```
feature/user-login
```

New functionality.

---

## Bugfix

```
bugfix/cart-total
```

Fixes a normal bug.

---

## Hotfix

```
hotfix/payment-crash
```

Emergency production fix.

---

## Release

```
release/v2.3.0
```

Preparing software release.

---

## Chore

```
chore/dependencies
```

Maintenance work.

---

## Docs

```
docs/readme
```

Documentation only.

---

## Refactor

```
refactor/database-layer
```

Improving code without changing behavior.

---

## CI

```
ci/github-actions
```

GitHub Actions changes.

---

## Test

```
test/auth-integration
```

Adding or updating tests.

---

# Part 15 - Real Company Workflow (Small Team)

```
main

↓

feature/login

↓

Merge

↓

main

↓

Deploy
```

Very common in startups.

---

# Part 16 - Medium Company Workflow

```
main

↓

develop

↓

feature branches

↓

develop

↓

release branch

↓

main
```

Example

```
main

develop

feature-login

feature-payment

feature-profile

feature-chat
```

All developers merge into

```
develop
```

Once stable

```
release/v2.5
```

Testing

↓

Merge

↓

main

---

# Part 17 - Enterprise Workflow

Large companies often have multiple environments.

```
Developer Laptop

↓

Feature Branch

↓

Develop

↓

QA

↓

UAT

↓

Pre-Production

↓

Production
```

Let's understand each.

---

## Development

Developers write code.

Very unstable.

---

## QA (Quality Assurance)

QA engineers test.

They intentionally try to break the application.

---

## UAT

User Acceptance Testing.

Real business users test.

Example

Bank employees.

Doctors.

Teachers.

Clients.

---

## Pre-Production

Looks almost identical to production.

Same infrastructure.

Same databases (often sanitized copies).

Same Docker containers.

Same Kubernetes cluster size.

Same networking.

Final verification.

---

## Production

Actual customers.

Never directly develop here.

---

# Part 18 - Branches vs Environments

A very common misunderstanding is to think each environment must always have its own branch. Not necessarily.

Many companies map them, for example:

```
feature/*  -> Developer testing
develop    -> Shared development environment
release/*  -> QA/UAT
main        -> Production
```

Others use deployment pipelines where **the same commit** is promoted from Dev to QA to UAT to Production without creating new branches. Modern CI/CD often favors promoting immutable builds rather than copying code between long-lived environment branches.

---

# Part 19 - Merge Request / Pull Request

Suppose you finished

```
feature/login
```

You don't merge directly.

Instead

Create Pull Request.

Manager reviews.

Checks:

* Code quality
* Security
* Style
* Tests
* Performance

Only after approval

Merge.

---

# Part 20 - Git Flow vs Trunk-Based Development

Historically, many companies used **Git Flow**:

```
main
develop
feature/*
release/*
hotfix/*
```

Today, many organizations (especially cloud-native teams) use **Trunk-Based Development**:

* `main` (or `trunk`) is the primary branch.
* Developers create very short-lived feature branches.
* Changes are merged into `main` multiple times a day.
* Feature flags hide incomplete features instead of long-lived branches.

Both approaches are used successfully; the choice depends on team size, release cadence, and product needs.

---

# Part 21 - What You'll Likely Use for Your AI SaaS

Based on the stack you've been building (Docker, GitHub Actions, GHCR, Watchtower, Cloudflare Tunnel), a simple but production-friendly workflow is a great fit:

```
main
│
├── feature/auth
├── feature/rag
├── feature/chat-history
├── bugfix/docker-build
├── chore/dependencies
└── ci/github-actions
```

Workflow:

1. Create a feature branch from `main`.
2. Make commits as you work.
3. Push the feature branch to GitHub.
4. Open a Pull Request.
5. Run GitHub Actions (tests, linting, Docker build).
6. Review and merge into `main`.
7. GitHub Actions builds a versioned Docker image and publishes it to GHCR.
8. Your home server's Watchtower detects the new image and updates the running container.

This gives you a professional workflow without unnecessary complexity. As your project grows and you add teammates, you can introduce release branches or additional environments if they become valuable.

---

# The Mental Model to Remember

Think of Git as a map of roads:

```
                feature/login
               /
A ---- B ---- C ---- D ---- E   main
               \
                feature/payment
```

* **Commit** = a checkpoint on the road.
* **Branch** = a named road (really, a movable pointer to a line of commits).
* **HEAD** = where you are standing.
* **Remote** = another Git repository (GitHub, GitLab, etc.).
* **origin** = the default nickname for your primary remote.
* **origin/main** = your local record of the remote `main` branch's state.
* **Merge** = bringing one road back into another.
* **Pull Request** = a request to review and merge changes.
* **CI/CD** = automated testing, building, and deployment after changes are merged.

Once these concepts click, most Git commands become much easier to understand because they're simply moving between branches, updating pointers, or synchronizing your local repository with remote repositories.
