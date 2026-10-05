# pyproject.toml & uv: The Complete Guide (Beginner → Advanced)

## Part 1: The Big Picture

Before diving in, let's understand **why these tools exist**.

### The old way (and why it was painful)

For years, Python projects managed dependencies like this:

```
requirements.txt          # your dependencies
requirements-dev.txt      # dev-only dependencies
setup.py                  # package metadata + install logic
setup.cfg                 # more metadata
MANIFEST.in               # which files to include
```

Problems with this:
- **requirements.txt has no metadata** — it's just a flat list, no project name, version, or description
- **No separation** between "direct" dependencies (what you asked for) and "transitive" ones (what your dependencies need)
- **pip doesn't lock by default** — `requests` on Monday might install version 2.28, on Friday 2.31, breaking your code
- **Slow** — pip resolves and installs packages serially

### The new way

- **`pyproject.toml`** = one standardized file describing your entire project (metadata + dependencies + tool configs)
- **`uv`** = a blazing-fast, Rust-based package manager (replacement for pip, pip-tools, virtualenv, poetry, pyenv... all in one)

uv is typically **10–100x faster** than pip. It's made by Astral (the team behind Ruff, the popular linter).

---

## Part 2: pyproject.toml Explained, Section by Section

TOML is a simple config format. `[section]` starts a section, `key = value` sets values. Let's build a complete file piece by piece.

### `[project]` — Your project's identity card

```toml
[project]
name = "my-awesome-app"
version = "1.0.0"
description = "A tool that does awesome things"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
    { name = "Your Name", email = "you@example.com" }
]
keywords = ["cli", "automation"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
]
```

**What each field does:**

| Field | Purpose |
|---|---|
| `name` | The package name on PyPI (what people `pip install`) |
| `version` | Your current version (semantic versioning: `MAJOR.MINOR.PATCH`) |
| `description` | One-liner shown on PyPI |
| `readme` | File rendered as your project's PyPI homepage |
| `requires-python` | **Very important** — minimum Python version. uv uses this to pick a Python interpreter AND to resolve compatible dependency versions |
| `authors`, `keywords`, `classifiers` | Metadata for PyPI search/display |

> **Rule of thumb:** always set `requires-python`. Without it, tools can't know which dependency versions are safe to install.

### `project.urls` — Links on your PyPI page

```toml
[project.urls]
Homepage = "https://github.com/you/my-awesome-app"
Documentation = "https://my-awesome-app.readthedocs.io"
Repository = "https://github.com/you/my-awesome-app"
Issues = "https://github.com/you/my-awesome-app/issues"
```

### `dependencies` — What your project needs to RUN

```toml
[project]
dependencies = [
    "requests>=2.31",
    "click>=8.1,<9",
    "pydantic>=2.0",
]
```

**This is the most important section.** These are installed whenever someone installs your package.

**Version specifier syntax (crucial to learn):**

| Specifier | Meaning |
|---|---|
| `requests` | Any version |
| `requests==2.31.0` | Exactly this version ("pinning") |
| `requests>=2.31` | This version or newer |
| `requests>=2.31,<3` | 2.31 or newer, but not 3.x (most common safe pattern) |
| `requests~=2.31.0` | Compatible release — allows 2.31.x patches, not 2.32 |
| `requests[security]` | Install with an optional "extra" of that package |

**Beginner advice:** use `>=` with an upper bound like `,<3` for libraries you depend on. Don't pin exact versions here — that's what the lock file is for (more on that soon).

### `project.optional-dependencies` — "Extras" users can opt into

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]
docs = [
    "sphinx>=7.0",
]
all = [
    "my-awesome-app[dev,docs]",   # yes, extras can reference other extras!
]
```

**How it's used:**

```bash
pip install my-awesome-app          # base only
pip install "my-awesome-app[dev]"   # base + dev extras
pip install "my-awesome-app[all]"   # base + everything
```

**When to use:** when a dependency is only needed for a *specific use case* of your package. Example: `pandas` has an `excel` extra (`pip install "pandas[excel]"`) that pulls in `openpyxl` — users who never touch Excel files don't pay the cost.

### `dependency-groups` — Dependencies for CONTRIBUTORS, not users

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
]
test = [
    "pytest>=8.0",
]
docs = [
    "mkdocs-material>=9.0",
]
```

**This is the key distinction beginners confuse:**

| | `optional-dependencies` (extras) | `dependency-groups` |
|---|---|---|
| Audience | **End users** of your package | **You and your teammates** developing it |
| Shipped to PyPI? | Yes, published as extras | No, stays local |
| Installed via | `pip install pkg[extra]` | `uv sync --group dev` (uv defaults to installing `dev`) |
| Standard | PEP 621 (packaging standard) | PEP 735 (newer, dev-tooling standard) |

**Mental model:**
- Building a **library others will install**? Optional stuff for users → `optional-dependencies`.
- Building an **application** or working on your own library? Tools for development (pytest, linters, formatters) → `dependency-groups`.

> With uv, the `dev` group is installed automatically by `uv sync`. That's why you see `[dependency-groups] dev = [...]` in most modern uv projects.

### `[build-system]` — How to turn your code into an installable package

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**What is this?** When someone runs `pip install your-package`, something has to *build* it — bundle your code into a wheel (`.whl` file). This section declares which tool does that.

Common backends:
- **`hatchling`** — modern, simple, recommended default
- **`setuptools`** — the classic, works everywhere, more verbose
- **`flit-core`** — ultra-minimal, for pure-Python simple packages
- **`maturin`** — if you have Rust extensions
- **`poetry-core`** — if you use Poetry

**Beginner rule:** just use `hatchling` and don't think about it. You only need this section if your project is meant to be *installed as a package*. For a pure application (scripts you run, never publish), you can skip it entirely or mark the project as non-packaged:

```toml
[tool.uv]
package = false
```

### `[project.scripts]` — Create command-line commands

```toml
[project.scripts]
awesome = "my_awesome_app.cli:main"
```

This says: *when the package is installed, create a shell command called `awesome` that runs the `main()` function in `my_awesome_app/cli.py`.*

```python
# my_awesome_app/cli.py
def main():
    print("Hello from my CLI!")
```

```bash
$ awesome
Hello from my CLI!
```

This is how tools like `pytest`, `ruff`, and `uv` itself expose terminal commands. **Use it whenever you build a CLI tool.**

Related: `[project.gui-scripts]` does the same for GUI apps (no console window on Windows), and `[project.entry-points]` is the general mechanism for plugins.

### `[tool.{toolname}]` — Configuration for your dev tools

pyproject.toml doubles as **one config file for all your tools**, replacing a mess of `.flake8`, `pytest.ini`, `mypy.ini`, `.coveragerc` etc.

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers"

[tool.mypy]
strict = true
python_version = "3.10"

[tool.coverage.run]
source = ["src"]

[tool.uv]                    # uv's own configuration
package = true
```

**What goes here:** any tool that supports pyproject.toml configuration (almost all modern ones: ruff, black, mypy, pytest, coverage, uv, hatch, poetry...).

### `[tool.uv]` — uv-specific settings

```toml
[tool.uv]
package = true                          # build this project as a package
dev-dependencies = [...]                # legacy way (prefer dependency-groups now)
default-groups = ["dev", "docs"]        # groups installed by default on uv sync
environments = ["sys_platform == 'linux'"]   # restrict resolution to platforms
```

### `[tool.uv.sources]` — Where a dependency comes from

Normally dependencies come from PyPI. But sometimes you need a git repo, local path, or direct URL:

```toml
[project]
dependencies = ["mylib", "utils"]

[tool.uv.sources]
mylib = { git = "https://github.com/you/mylib", branch = "main" }
utils = { path = "../utils", editable = true }
```

**Use cases:**
- Using an unreleased fix from a git branch
- Local development across multiple packages (monorepos)
- Internal private packages

### `tool.uv.override-dependencies` — Force a version (the escape hatch)

```toml
[tool.uv]
override-dependencies = [
    "numpy>=2.0",
]
```

**What it does:** Sometimes two of your dependencies disagree — package A wants `numpy<2`, package B wants `numpy>=2`, and resolution fails. An override says *"I don't care what they asked for, use this version."*

```toml
[tool.uv]
constraint-dependencies = [
    "urllib3<2",   # softer: keep within these bounds if possible
]
```

**Difference:**
- **constraints** — "try to satisfy this, error if impossible" (safe guardrail)
- **overrides** — "ignore what anyone said, use exactly this" (force, use sparingly — can break packages whose requirements you ignored)

**When to use:** only as a last resort when resolution fails or you know a transitive dependency has a bug/security issue. Don't reach for these first.

### `[tool.uv.workspace]` — Monorepos (advanced)

```toml
# root pyproject.toml
[tool.uv.workspace]
members = ["packages/*"]
```

If you have multiple related packages in one repo, workspaces let them share one lockfile and one venv, with local packages referencing each other.

---

## Part 3: A Complete Real-World Example

```toml
[project]
name = "weather-cli"
version = "0.3.0"
description = "Check the weather from your terminal"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "You", email = "you@example.com" }]
dependencies = [
    "requests>=2.31,<3",
    "rich>=13.0",
]

[project.optional-dependencies]
emoji = ["emoji>=2.0"]        # users: pip install "weather-cli[emoji]"

[project.scripts]
weather = "weather_cli.main:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.uv.sources]
# requests = { git = "https://github.com/psf/requests" }   # if ever needed
```

---

## Part 4: What Is uv.lock?

### The problem it solves

Your pyproject.toml says `requests>=2.31`. Today that installs 2.32.3. Next month, 2.33.0 comes out with a subtle bug. Your CI breaks. Your teammate's machine works, yours doesn't. **"Works on my machine" happens because everyone resolved different versions.**

### The solution: a lock file

`uv.lock` is a **complete, exact snapshot** of your entire dependency tree:

```toml
# uv.lock (simplified view)
[[package]]
name = "requests"
version = "2.32.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "certifi" },
    { name = "charset-normalizer" },
    { name = "idna" },
    { name = "urllib3" },
]
sdist = { url = "...", hash = "sha256:..." }   # integrity hashes!
wheels = [{ url = "...", hash = "sha256:..." }]
```

Key facts:

1. **It's auto-generated** — run `uv lock` (or any command that needs it), never edit by hand.
2. **It pins EVERYTHING** — not just your direct deps, but their deps, and their deps' deps (the full transitive tree), with exact versions and cryptographic hashes.
3. **It's cross-platform** — one lockfile records resolutions for all platforms/Python versions (unlike pip-tools).
4. **It's human-readable TOML** — you can diff it in code review to see exactly what changed.
5. **Commit it to git.** Always. It's how your whole team and CI get byte-identical environments.

**The two-file philosophy:**

| File | Role | Edited by |
|---|---|---|
| `pyproject.toml` | What you *want* (ranges: `requests>=2.31`) | You, by hand |
| `uv.lock` | What you *got* (exact: `requests==2.32.3` + hashes) | uv, automatically |

---

## Part 5: uv Commands — The Ones You'll Actually Use

### Setup

```bash
# Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv / pipx install uv / winget install astral-sh.uv
```

### Starting a project

```bash
uv init my-project        # creates project skeleton (pyproject.toml, .python-version, main.py)
uv init --lib my-lib      # for a library (adds build-system, src/ layout)
uv init --app my-app      # for an application (default)
cd my-project
```

What `uv init` gives you:
```
my-project/
├── .python-version      # which Python to use
├── README.md
├── pyproject.toml       # your config
└── main.py
```

### Managing Python itself (uv replaces pyenv!)

```bash
uv python install 3.12        # download & install Python 3.12
uv python list                # see available/installed versions
uv python pin 3.12            # write .python-version for this project
```

Yes — uv can install Python interpreters for you. No pyenv needed.

### The daily workflow (90% of your usage)

```bash
uv add requests               # add a dependency
uv add "requests>=2.31"       # with a version constraint
uv add --dev pytest ruff      # add to the dev dependency-group
uv add --group docs mkdocs    # add to a custom group
uv add --optional emoji emoji # add to optional-dependencies (extras)

uv remove requests            # remove a dependency

uv sync                       # install everything from the lockfile into .venv
                              # (creates .venv automatically if missing!)

uv run python main.py         # run a script inside the project env
uv run pytest                 # run any command in the env
uv run --with httpx script.py # run with a TEMPORARY extra package (no project change)
```

**Notice: you never manually activate a venv.** `uv run` and `uv sync` handle `.venv` for you. This is the biggest quality-of-life change vs. pip+venv.

If you prefer the classic way, it still works:

```bash
uv venv                       # create .venv manually
source .venv/bin/activate     # activate it
uv pip install requests       # pip-compatible interface (but 10-100x faster)
```

### Locking and upgrading

```bash
uv lock                       # (re)generate uv.lock — usually automatic
uv lock --upgrade             # upgrade ALL dependencies to latest allowed
uv lock --upgrade-package requests   # upgrade just one package
```

### Updating and checking

```bash
uv sync --locked              # fail if lockfile is out of date (great for CI)
uv sync --frozen              # use lockfile as-is, never touch it
uv sync --no-dev              # skip dev groups (for production deploys)
uv tree                       # visualize the dependency tree
uv pip list                   # see what's installed
```

### Running tools without installing (replaces pipx)

```bash
uvx ruff check .              # = uv tool run: run ruff in an ephemeral env
uvx black .                   # no install needed, cached after first run
uv tool install ruff          # install a CLI tool globally, isolated
```

### Single-file scripts with inline dependencies (a killer feature)

```python
# script.py
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "rich"]
# ///
import requests
from rich import print
print(requests.get("https://api.github.com").json())
```

```bash
uv run script.py    # uv reads the comment block, makes a temp env, runs it
```

No project setup at all — perfect for automation scripts, data processing one-offs, sharing code with colleagues.

### Building and publishing (replaces twine)

```bash
uv build                      # build .whl + .tar.gz into dist/
uv publish                    # upload to PyPI
```

---

## Part 6: Putting It All Together — A Day in the Life

```bash
# 1. Start
uv init awesome-cli && cd awesome-cli

# 2. Add what you need
uv add requests rich
uv add --dev pytest ruff

# 3. Write code, run it
uv run python main.py
uvx ruff check .
uv run pytest

# 4. Teammate clones your repo — one command, identical environment
git clone ... && cd awesome-cli
uv sync        # reads uv.lock → exact same versions as you

# 5. Three months later, upgrade safely
uv lock --upgrade
uv run pytest            # still green? commit the new lockfile.
```

---

## Part 7: Quick Reference Cheat Sheet

**pyproject.toml decisions:**

| I want to... | Put it in... |
|---|---|
| Declare runtime needs | `project.dependencies` |
| Offer optional features to users | `project.optional-dependencies` |
| Add pytest/linters for developers | `dependency-groups.dev` |
| Make a terminal command | `project.scripts` |
| Configure ruff/pytest/mypy | `[tool.<name>]` |
| Configure uv itself | `[tool.uv]` |
| Use a git/local dependency | `[tool.uv.sources]` |
| Force a broken resolution to work | `tool.uv.override-dependencies` |
| Make it installable/publishable | `[build-system]` |

**uv commands:**

| Command | Why |
|---|---|
| `uv init` | Start a project |
| `uv add` / `uv remove` | Manage dependencies |
| `uv sync` | Recreate the environment from the lockfile |
| `uv run` | Run anything in the project env (no activation!) |
| `uv lock --upgrade` | Update dependencies |
| `uvx <tool>` | Run a tool without installing |
| `uv python install/pin` | Manage Python versions |
| `uv build` / `uv publish` | Ship your package |

---

## The 5 Mental Models to Remember

1. **pyproject.toml = intent** (ranges), **uv.lock = reality** (exact pins + hashes). Commit both.
2. **`dependencies`** is for users, **`dependency-groups`** is for developers, **`optional-dependencies`** is for optional user features.
3. **Never edit uv.lock by hand** — `uv add`, `uv remove`, and `uv lock` do it for you.
4. **`uv run` replaces venv activation** — this feels weird for one day, then you never go back.
5. **uv is a Swiss army knife** — it replaces pip, pip-tools, virtualenv, pyenv, pipx, and twine with one fast binary.

That's everything you need to be genuinely comfortable with uv. The best next step: run `uv init` on a small idea and just play — the workflow clicks within an hour of real use.
