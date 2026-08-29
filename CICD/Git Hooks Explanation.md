Absolutely. Since you are already using **`pre-commit`**, the next step is to understand how the other Git hooks fit around it.

A useful mental model is:

```text
                    YOU
                     │
                     ▼
              git commit
                     │
          ┌──────────┴──────────┐
          │                     │
     pre-commit             commit-msg
          │                     │
          ▼                     ▼
   Check the files        Check the commit
   being committed        message itself
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
                  COMMIT
                     │
                     ▼
                  git push
                     │
                     ▼
                pre-push
                     │
              ┌──────┴──────┐
              │             │
           checks          BLOCK
              │
              ▼
           remote
```

And `post-checkout` lives somewhere else:

```text
git switch feature/my-feature
          │
          ▼
    post-checkout
          │
          ▼
   run branch-specific
   setup / checks / tasks
```

The important distinction is:

> **`pre-commit` protects the code before a commit.**
> **`commit-msg` protects the commit message.**
> **`pre-push` protects what leaves your machine.**
> **`post-checkout` reacts after you switch branches or check out files.**

---

# 1. First: what exactly is a Git hook?

A **Git hook** is a script that Git automatically executes when a particular Git event occurs.

For example:

```bash
git commit
```

can cause Git to execute:

```text
pre-commit
commit-msg
```

before the commit is created.

Similarly:

```bash
git push
```

can cause:

```text
pre-push
```

to execute.

Hooks are normally stored inside:

```text
.git/hooks/
```

For example:

```text
your-project/
├── .git/
│   └── hooks/
│       ├── pre-commit
│       ├── commit-msg
│       ├── pre-push
│       └── post-checkout
├── src/
├── tests/
└── ...
```

One important thing:

**`.git/hooks/` is local to your clone.**

It is not normally committed to GitHub.

That means if you clone your repository on another machine, your hooks don't automatically come with the repository.

This is one reason tools such as **pre-commit** are useful: the hook itself can be installed into each developer's clone from configuration stored in the repository.

---

# 2. Where your current `pre-commit` fits

You said you are already using `pre-commit`.

You probably have something similar to:

```text
.pre-commit-config.yaml
```

and:

```bash
pre-commit install
```

which installs:

```text
.git/hooks/pre-commit
```

Then when you run:

```bash
git commit -m "some message"
```

Git executes:

```text
pre-commit
```

before creating the commit.

For example, your `pre-commit` configuration might run:

```text
trailing-whitespace
end-of-file-fixer
ruff
gitleaks
```

Conceptually:

```text
git commit
    │
    ▼
pre-commit
    │
    ├── formatting
    ├── linting
    ├── secret scanning
    └── other checks
    │
    ▼
commit-msg
    │
    └── validate commit message
    │
    ▼
commit created
```

So `commit-msg` complements `pre-commit very nicely.

---

# 3. `commit-msg` hook

## What is it?

The `commit-msg` hook runs **after Git has prepared the commit message but before the commit is finalized**.

Its job is to inspect:

```text
the commit message
```

rather than the source code.

For example:

```bash
git commit -m "fix calculator bug"
```

The hook can inspect:

```text
fix calculator bug
```

and decide:

```text
GOOD → allow commit
BAD  → reject commit
```

---

# 4. Why would you want `commit-msg`?

This becomes extremely useful when you establish a consistent commit-message policy.

For example, you could require:

```text
feat: add calculator endpoint
fix: handle division by zero
docs: update README
test: add calculator tests
refactor: simplify calculator service
chore: update dependencies
security: harden authentication
```

Then reject:

```text
fixed stuff
changes
update
asdf
test
hello
```

This gives your repository a predictable history.

---

# 5. Conventional Commits

A common convention is **Conventional Commits**.

The general format is:

```text
type(scope): description
```

For example:

```text
feat(calculator): add addition endpoint
```

or:

```text
fix(auth): prevent invalid JWT algorithm
```

or:

```text
docs(readme): explain local development
```

Common types:

| Type       | Meaning                 |
| ---------- | ----------------------- |
| `feat`     | New functionality       |
| `fix`      | Bug fix                 |
| `docs`     | Documentation           |
| `test`     | Tests                   |
| `refactor` | Code restructuring      |
| `perf`     | Performance             |
| `build`    | Build system            |
| `ci`       | CI/CD                   |
| `chore`    | Maintenance             |
| `security` | Security-related change |

For your projects, this can be especially useful because you are building applications with FastAPI, Docker and GitHub Actions.

---

# 6. How `commit-msg` works technically

Git creates a temporary file containing the commit message.

Conceptually:

```text
.git/COMMIT_EDITMSG
```

Git then invokes:

```text
.git/hooks/commit-msg
```

and passes the message-file path as an argument.

For example:

```bash
.git/hooks/commit-msg .git/COMMIT_EDITMSG
```

Your script can read:

```bash
$1
```

which is the commit-message file.

---

# 7. Let's implement `commit-msg`

Since you are already using `pre-commit`, I recommend **not manually maintaining a complicated shell script** unless you're learning Git hooks themselves.

First, let's understand the raw Git hook.

Go into your repository:

```bash
cd /path/to/your/project
```

Check your hooks:

```bash
ls -la .git/hooks/
```

Create:

```bash
nano .git/hooks/commit-msg
```

Put:

```bash
#!/usr/bin/env bash

set -e

commit_msg_file="$1"
commit_msg=$(head -n 1 "$commit_msg_file")

pattern='^(feat|fix|docs|test|refactor|perf|build|ci|chore|security)(\([a-zA-Z0-9._/-]+\))?: .+'

if [[ ! "$commit_msg" =~ $pattern ]]; then
    echo
    echo "ERROR: Invalid commit message."
    echo
    echo "Expected:"
    echo "  type: description"
    echo "  type(scope): description"
    echo
    echo "Examples:"
    echo "  feat: add calculator endpoint"
    echo "  fix(auth): validate JWT algorithm"
    echo "  docs: update README"
    echo "  test: add calculator tests"
    echo

    exit 1
fi

echo "✓ Commit message is valid."
```

Save it.

Then:

```bash
chmod +x .git/hooks/commit-msg
```

---

# 8. Test it

Try:

```bash
git commit -m "fixed stuff"
```

You should get something like:

```text
ERROR: Invalid commit message.
```

The commit should be rejected.

Now:

```bash
git commit -m "fix: fix calculator addition"
```

The hook should allow it.

Try:

```bash
git commit -m "feat(calculator): add addition endpoint"
```

That should also pass.

---

# 9. Very important: hook exit codes

This is one of the most important concepts to understand.

A Git hook is essentially a program.

If it exits with:

```bash
exit 0
```

Git interprets that as:

> Everything is okay. Continue.

If it exits with:

```bash
exit 1
```

Git interprets that as:

> Something failed. Stop.

So:

```text
Hook
 │
 ├── exit 0 → Git continues
 │
 └── exit non-zero → Git stops
```

This principle applies to `pre-commit`, `commit-msg`, and `pre-push`.

---

# 10. `pre-push`

Now we reach a **very important security hook**.

`pre-push` executes when you run:

```bash
git push
```

before Git actually sends the objects to the remote repository.

Conceptually:

```text
git push
   │
   ▼
pre-push
   │
   ├── run tests
   ├── scan secrets
   ├── run security checks
   ├── run type checks
   └── check repository state
   │
   ▼
PASS?
 ┌─┴─┐
YES  NO
 │    │
 ▼    ▼
PUSH  BLOCK
```

This is extremely useful.

---

# 11. Why `pre-push` is different from `pre-commit`

Suppose you make a commit:

```bash
git commit
```

Your `pre-commit` hook checks:

```text
changed files
```

But later you might have:

```text
10 commits
```

that haven't been pushed.

`pre-push` gives you a final local checkpoint before those commits leave your machine.

For example:

```text
Developer
   │
   ▼
git push
   │
   ▼
pre-push
   │
   ├── tests
   ├── security scanning
   ├── dependency checks
   └── build verification
   │
   ▼
GitHub
```

---

# 12. What should you put in `pre-push`?

Be careful here.

You don't want:

```text
pre-commit → 10 seconds
pre-push   → 15 minutes
```

because you'll hate using Git.

A good strategy is:

### `pre-commit`

Fast checks:

```text
formatting
linting
secret detection
basic validation
```

### `commit-msg`

Commit policy:

```text
Conventional Commits
```

### `pre-push`

More expensive checks:

```text
unit tests
type checking
security tests
build validation
```

### GitHub Actions

Full authoritative CI:

```text
full test suite
dependency scanning
SAST
container scanning
integration tests
etc.
```

---

# 13. Implement a basic `pre-push`

Create:

```bash
nano .git/hooks/pre-push
```

Use:

```bash
#!/usr/bin/env bash

set -e

echo "Running pre-push checks..."
echo

echo "→ Running tests..."
pytest

echo
echo "→ Running Ruff..."
ruff check .

echo
echo "✓ All pre-push checks passed."
```

Then:

```bash
chmod +x .git/hooks/pre-push
```

Now:

```bash
git push
```

will execute:

```text
pre-push
   │
   ├── pytest
   │
   └── ruff
   │
   ▼
push
```

If:

```bash
pytest
```

fails:

```text
pre-push
   │
   ▼
pytest
   │
   ▼
FAIL
   │
   ▼
exit non-zero
   │
   ▼
PUSH BLOCKED
```

---

# 14. `post-checkout`

This hook is different.

`post-checkout` runs **after you check out/switch to another branch or restore files**.

Since you prefer modern Git commands, you'll generally use:

```bash
git switch
```

rather than:

```bash
git checkout
```

For example:

```bash
git switch develop
```

Git changes your working tree.

Then:

```text
post-checkout
```

can execute.

---

# 15. Why would `post-checkout` be useful?

Imagine:

```text
main
develop
feature/calculator
```

You switch:

```bash
git switch feature/calculator
```

Your project might need branch-specific actions.

For example:

```text
check Python version
check environment
display current branch
install dependencies if requirements changed
generate development files
```

Another common use is detecting whether you've switched:

```text
branch → branch
```

versus:

```text
commit → files
```

---

# 16. `post-checkout` arguments

This is important.

Git invokes:

```text
post-checkout <old-head> <new-head> <branch-flag>
```

So inside the script:

```bash
$1 = old HEAD
$2 = new HEAD
$3 = branch flag
```

`$3` tells you whether the operation involved switching branches.

Conceptually:

```text
$3 == 1
```

means:

```text
branch checkout/switch
```

while:

```text
$3 == 0
```

means:

```text
file checkout
```

---

# 17. Implement a simple `post-checkout`

Create:

```bash
nano .git/hooks/post-checkout
```

Put:

```bash
#!/usr/bin/env bash

set -e

branch=$(git branch --show-current)

echo
echo "✓ Switched to branch: $branch"
echo
```

Then:

```bash
chmod +x .git/hooks/post-checkout
```

Now:

```bash
git switch develop
```

will produce something similar to:

```text
✓ Switched to branch: develop
```

---

# 18. A more useful `post-checkout`

For your development environment, I would make it slightly smarter.

```bash
#!/usr/bin/env bash

set -e

old_head="$1"
new_head="$2"
branch_flag="$3"

if [[ "$branch_flag" != "1" ]]; then
    exit 0
fi

branch=$(git branch --show-current)

echo
echo "======================================"
echo " Switched to branch: $branch"
echo "======================================"
echo

if [[ -f ".python-version" ]]; then
    echo "Python version file detected."
fi

if [[ -f "pyproject.toml" ]]; then
    echo "Python project detected."
fi

if [[ -f "docker-compose.yml" || -f "compose.yml" ]]; then
    echo "Docker Compose project detected."
fi

echo
```

This doesn't modify anything. It simply gives you useful information.

That's a good philosophy for a beginner:

> Start with hooks that **observe and validate** before creating hooks that automatically modify your environment.

---

# 19. How all four hooks work together

Now let's put everything together.

Suppose you execute:

```bash
git commit -m "feat(calculator): add addition endpoint"
```

The flow is approximately:

```text
                  git commit
                      │
                      ▼
                 pre-commit
                      │
              ┌───────┴────────┐
              │                │
           PASS              FAIL
              │                │
              ▼                ▼
          commit-msg          STOP
              │
       ┌──────┴──────┐
       │             │
     PASS           FAIL
       │             │
       ▼             ▼
    COMMIT          STOP
```

Then later:

```bash
git push
```

```text
                 git push
                    │
                    ▼
                pre-push
                    │
          ┌─────────┴─────────┐
          │                   │
        PASS                 FAIL
          │                   │
          ▼                   ▼
       PUSH TO              STOP
       REMOTE
```

And when you switch branches:

```bash
git switch develop
```

```text
             git switch develop
                    │
                    ▼
             working tree
               changes
                    │
                    ▼
             post-checkout
                    │
                    ▼
              branch setup
              / information
```

---

# 20. One major problem with our manual hooks

There is an important problem.

These:

```text
.git/hooks/pre-commit
.git/hooks/commit-msg
.git/hooks/pre-push
.git/hooks/post-checkout
```

are **not tracked by Git**.

Therefore:

```bash
git clone ...
```

doesn't give another developer your hooks.

You could manually copy them:

```bash
cp ...
```

but that's not a good team workflow.

And this is especially relevant to your security-hardening goal.

You want your security checks to be:

```text
repeatable
version-controlled
reviewable
automatically installed
```

---

# 21. Better approach: use `pre-commit`

Since you are **already using pre-commit**, I recommend letting it manage your Git hooks where possible.

Your repository can contain:

```text
.pre-commit-config.yaml
```

which is version controlled.

Then developers run:

```bash
pre-commit install
```

and the hooks are installed locally.

You can have `pre-commit` install:

```text
pre-commit
commit-msg
pre-push
```

This is much better than manually editing `.git/hooks`.

---

# 22. Install multiple hook stages

First check your current version:

```bash
pre-commit --version
```

Then you can install the hooks.

For example:

```bash
pre-commit install
```

installs the normal:

```text
pre-commit
```

Then:

```bash
pre-commit install --hook-type commit-msg
```

installs:

```text
commit-msg
```

And:

```bash
pre-commit install --hook-type pre-push
```

installs:

```text
pre-push
```

You can also install all three:

```bash
pre-commit install
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push
```

---

# 23. Why I recommend this architecture for you

For your current GitHub security-hardening work, I'd structure things like this:

```text
                    LOCAL MACHINE
                         │
             ┌───────────┴───────────┐
             │                       │
        git commit                git push
             │                       │
             ▼                       ▼
        pre-commit               pre-push
             │                       │
       ┌─────┴─────┐           ┌─────┴──────┐
       │           │           │            │
    format       secrets     tests      security
    lint          scan       typing       checks
       │           │           │            │
       └─────┬─────┘           └─────┬──────┘
             │                       │
             ▼                       ▼
         commit                   GitHub
             ▲
             │
         commit-msg
             │
      commit convention
```

And:

```text
git switch
     │
     ▼
post-checkout
     │
     ▼
local development setup
```

---

# 24. But don't duplicate expensive checks

This is a very important design principle.

Don't do this:

```text
pre-commit:
    pytest
    ruff
    mypy
    bandit
    gitleaks
    semgrep
    docker build
```

Then:

```text
pre-push:
    pytest
    ruff
    mypy
    bandit
    gitleaks
    semgrep
    docker build
```

You'll end up waiting forever.

Instead:

### Pre-commit

Fast:

```text
formatting
linting
secret detection
YAML validation
basic checks
```

### Commit-msg

Fast:

```text
commit message validation
```

### Pre-push

Moderate:

```text
unit tests
type checking
security tests
```

### GitHub Actions

Comprehensive:

```text
SAST
dependency scanning
secret scanning
container scanning
full test suite
integration tests
Docker build
SBOM
image signing
deployment
```

---

# 25. One important security warning

Hooks are **not a security boundary**.

A developer can bypass a hook:

```bash
git commit --no-verify
```

and push hooks can also be bypassed.

Therefore:

```text
Local hooks
     ↓
Developer convenience + early detection
```

but:

```text
GitHub Actions + branch protection
     ↓
Actual repository enforcement
```

For example:

```text
Developer
   │
   ▼
pre-commit
   │
   ▼
commit-msg
   │
   ▼
pre-push
   │
   ▼
GitHub
   │
   ▼
GitHub Actions
   │
   ├── tests
   ├── SAST
   ├── dependency scanning
   ├── secrets scanning
   ├── container scanning
   └── security checks
   │
   ▼
Protected branch
```

That distinction is **extremely important** for the GitHub security-hardening project you're working through.

---

# 26. Recommended implementation for your project

Because you're already using `pre-commit`, I would implement these in this order:

### Step 1 — Keep your existing `pre-commit`

Don't replace it.

Check:

```bash
pre-commit --version
```

Then:

```bash
pre-commit run --all-files
```

---

### Step 2 — Add `commit-msg`

Install:

```bash
pre-commit install --hook-type commit-msg
```

Then configure a commit-message check.

---

### Step 3 — Add `pre-push`

Install:

```bash
pre-commit install --hook-type pre-push
```

Then configure tests/security checks that aren't appropriate for every commit.

---

### Step 4 — Add `post-checkout`

This one is different because `pre-commit` isn't primarily intended to manage arbitrary `post-checkout` automation.

For learning, create:

```text
.git/hooks/post-checkout
```

and start with a harmless informational hook.

---

### Step 5 — Later make hooks reproducible

Once you understand them, move toward a repository-managed structure such as:

```text
project/
├── .git/
├── .pre-commit-config.yaml
├── .githooks/
│   ├── post-checkout
│   └── ...
├── src/
├── tests/
├── pyproject.toml
└── README.md
```

and configure Git to use that hooks directory.

For example:

```bash
git config core.hooksPath .githooks
```

This is a very useful concept to learn because `.githooks/` can then be version controlled.

---

# 27. The four hooks in one table

| Hook            | Runs                       | Main purpose             | Should block? |
| --------------- | -------------------------- | ------------------------ | ------------- |
| `pre-commit`    | Before commit              | Validate staged code     | Yes           |
| `commit-msg`    | Before commit is finalized | Validate commit message  | Yes           |
| `pre-push`      | Before push                | Run broader tests/checks | Yes           |
| `post-checkout` | After branch/file checkout | React to checkout/switch | Usually no    |

Think of them as:

```text
pre-commit
    ↓
"Is my code okay?"

commit-msg
    ↓
"Is my commit message okay?"

pre-push
    ↓
"Is everything I'm about to send okay?"

post-checkout
    ↓
"I just switched branches. Do I need to react?"
```

---

# 28. Your next practical exercise

Since you're learning this as a beginner, **don't install everything blindly at once**.

I'd do this sequence in your repository:

```bash
# 1. Check existing hooks
ls -la .git/hooks/

# 2. Check pre-commit
pre-commit --version

# 3. Run existing pre-commit
pre-commit run --all-files

# 4. Install commit-msg
pre-commit install --hook-type commit-msg

# 5. Install pre-push
pre-commit install --hook-type pre-push

# 6. Check installed hooks
ls -la .git/hooks/
```

You should eventually see hooks corresponding to:

```text
pre-commit
commit-msg
pre-push
```

Then we'll add:

```text
post-checkout
```

and test each one deliberately.

**One thing I would not do yet:** copy the sample shell scripts above into your production repository without looking at your existing `.pre-commit-config.yaml`. Since you're already using `pre-commit`, the cleanest implementation is to integrate `commit-msg` and `pre-push` into your existing configuration rather than creating conflicting independent systems.
