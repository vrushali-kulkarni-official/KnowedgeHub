# Modern Python Engineering for Production AI Applications
### A 51-module, beginner-to-advanced course on uv, pyproject.toml, packaging, dependency management, typing, and production tooling

**Design logic:** Each module is deliberately small (30–60 minutes of AI-taught content) so the teaching AI can go deep on every bullet instead of skimming. Modules are sequential — each one assumes only what came before. You'll build everything inside one persistent practice repo that slowly evolves into your AI harness application.

---

## How to use each module

Paste this **master prompt** along with the module text into your AI:

> *"You are my expert Python tooling instructor. Teach me the module below in full detail. Rules: (1) Cover every listed topic — never summarize or skip. (2) For every concept give a concrete runnable example using uv and modern Python (3.12+). (3) Show real file contents and real commands with expected output. (4) Explain common errors, gotchas, and anti-patterns for each topic. (5) End the module with a hands-on exercise and 5 self-check questions. (6) If any command, flag, or best practice has changed since your training data, say so explicitly and tell me how to verify it against official docs (docs.astral.sh/uv, pypi.org, peps.python.org, pypa.io). (7) Use only modern, non-deprecated practices. Module: [PASTE MODULE HERE]"*

**Freshness protocol baked into the course:** uv and this ecosystem move fast. The master prompt forces the AI to flag anything outdated — always trust `--help` output and official docs over any single answer (including mine).

---

## Course map

| Part | Modules | Theme |
|---|---|---|
| 1 | 1–2 | Orientation & setup |
| 2 | 3–6 | Python & environment foundations |
| 3 | 7–13 | pyproject.toml mastery |
| 4 | 14–20 | The uv daily workflow |
| 5 | 21–23 | Versioning & release engineering |
| 6 | 24–30 | Static typing (incl. py.typed) |
| 7 | 31–33 | Linting, formatting, hooks (Ruff, pre-commit) |
| 8 | 34–39 | Testing & coverage (pytest, coverage.py, .coverage) |
| 9 | 40–47 | Production engineering (Docker, CI/CD, security, monorepo) |
| 10 | 48–49 | LangChain-specific dependency strategy + capstone |
| 11 | 50–51 | Legacy literacy, internals, staying current |

---

# PART 1 — Orientation & Setup

**Module 1 — The modern Python tooling landscape (the big picture)**
- *Goal:* Know what problem each tool solves and how they fit together before touching any of them.
- The four problem domains: interpreter management, environment isolation, dependency resolution/reproducibility, build & distribution.
- One-line role of each: Python (runtime), `pyproject.toml` (single config file for everything), `uv.lock` (reproducibility), `.python-version` (interpreter pinning), uv (the tool that orchestrates all of the above), `py.typed` (type-information opt-in), `.coverage` (test coverage data), pytest, mypy/pyright, Ruff, pre-commit.
- Legacy → modern translation table: `pip` → `uv`/`uv pip`, `venv` → automatic via uv, `requirements.txt` → `pyproject.toml` + `uv.lock`, `setup.py`/`setup.cfg` → `[project]` table, `pyenv` → `uv python`, `pipx` → `uvx`, `poetry` → `uv`, `black`+`flake8`+`isort`+`pyupgrade` → `ruff`, `.coveragerc`/`pytest.ini`/`mypy.ini` → `[tool.*]` tables in `pyproject.toml`.
- The most important distinction in the whole course: **application vs. library** (your harness app is mostly an *application*) and how that changes every decision later.
- Why uv displaced the old stack: single Rust binary, global cache, universal lockfile, replaces ~6 tools.

**Module 2 — Workstation setup & how you'll study**
- Install uv (official curl/PowerShell/brew method), `uv self update`, verify with `uv --version`.
- VS Code + Python extension (or your editor of choice); terminal comfort checklist.
- Git minimum checklist: init, clone, add, commit, branch, tag, remote, log — used constantly later.
- Create your permanent practice repo: `git init`, `uv init`, first commit.
- Establish the habit: never run bare `python`/`pytest` in a uv project — always `uv run`.

---

# PART 2 — Python & Environment Foundations

**Module 3 — How Python actually executes and finds code**
- What "Python" is: the interpreter binary; CPython vs PyPy vs freethreaded builds.
- `python file.py` vs `python -m package.module`; `__name__ == "__main__"`.
- The import machinery: `sys.path` (script dir → `PYTHONPATH` → site-packages), stdlib vs site-packages, `sys.modules` cache.
- What's inside `site-packages`: package dirs + `*.dist-info` metadata (RECORD, METADATA, entry_points).
- `__pycache__`, `.pyc` files, and bytecode compilation.
- Why this matters: this is the machinery venvs, editable installs, and "ModuleNotFoundError" all manipulate — the mental model everything else in the course builds on.

**Module 4 — Virtual environments & isolation (and how uv automates them)**
- The problem: conflicting global installs; one interpreter, many projects.
- Anatomy of a venv: `pyvenv.cfg`, interpreter symlink, its own `site-packages`, `bin/` (or `Scripts/`) — and the key uv detail: **uv-created venvs contain no pip by default**.
- Manual creation with `uv venv` (and `--python 3.12` selection) — for understanding only.
- The uv way: `.venv` is created and managed automatically inside your project on first `uv sync`/`uv run`; `UV_PROJECT_ENVIRONMENT` to relocate it.
- Activation vs `uv run`: why the modern pattern is *never activate, always `uv run`* — but know `source .venv/bin/activate` / `deactivate` (and the PowerShell variant) for when you see it.
- Proving which interpreter is used: `uv run python -c "import sys; print(sys.prefix)"`.
- `.venv` is disposable and never committed; recreate with delete + `uv sync`.

**Module 5 — Managing Python versions with uv**
- `uv python list` (installed vs available), `uv python install 3.13`, `uv python uninstall`, `uv python dir`; note PyPy and freethreaded (`3.13t`) variants exist.
- `uv python pin 3.12` → writes `.python-version`; file format (e.g., `3.12` or `3.12.7`).
- Interpreter selection order/precedence: `.python-version` → `UV_PYTHON` env var → any `requires-python`-compatible installed Python → auto-download.
- The classic confusion, explained precisely: **`.python-version` (your local runtime preference) vs `requires-python` in `pyproject.toml` (the compatibility you declare to the world)** — different purposes, both needed.
- Managed Pythons (python-build-standalone builds) vs system Pythons.
- Team consistency: commit `.python-version`; CI reads it.
- Deciding your baseline for the harness app (3.12+ recommended; check current LangChain/FastAPI support).

**Module 6 — `uv init` in depth: anatomy of a new project**
- `uv init demo` (default = unpackaged application): line-by-line walkthrough of every generated file — `pyproject.toml`, `.python-version`, `main.py`, `README.md`, `.git`, `.gitignore` — and what appears later (`.venv`, `uv.lock` after first sync).
- `uv init --package`: adds `src/` layout, `[build-system]`, `[project.scripts]` — the app installs itself.
- `uv init --lib`: the library layout — `src/<name>/`, and **`py.typed` included** (your first sighting of it).
- `uv init --script` (PEP 723 single-file projects) and `--bare`, `--no-readme`, `--vcs none`, `--python 3.12`.
- What to commit vs ignore; what "delete and re-init" safely means.
- Exercise: create all three project types side by side and diff them.

---

# PART 3 — pyproject.toml Mastery

**Module 7 — TOML syntax crash course**
- *Goal:* Read and write any `pyproject.toml`/`uv.lock` snippet fluently.
- Scalars, strings (basic/literal/multiline), arrays, inline tables, comments.
- `[table]` headers, dotted keys (`tool.uv.index`), arrays of tables (`[[tool.uv.index]]`).
- Rules that bite: duplicate table errors, key uniqueness, quote escaping.
- Why Python chose TOML (PEP 518) over INI/YAML/JSON.
- Bonus: enough YAML to read `.pre-commit-config.yaml` and GitHub Actions files later.

**Module 8 — `[project]` metadata I: identity & description**
- `name` (normalization rules, PyPI uniqueness), `version` (static, PEP 440), `description`, `readme`.
- `authors`/`maintainers` — the modern list-of-tables form.
- `license` — the modern SPDX string form (e.g., `license = "MIT"`) and `license-files`; the legacy `license = {file=...}`/classifier approach and why it's deprecated for new releases.
- `keywords`, `classifiers` (what they still do), `urls` (Homepage/Repository/Changelog).
- `requires-python`: what it constrains — installs, *and* how uv.lock resolves your dependency graph.
- `dynamic = [...]` teaser (full treatment in Module 22).

**Module 9 — Writing dependencies: PEP 508 requirement syntax**
- Full grammar: `name[extras] @ url ; markers` combined with version specifiers.
- Specifiers: `==`, `!=`, `<`, `>`, `<=`, `>=`, `~=`, `===`, wildcard `==1.2.*`; commas = AND; **no caret `^` operator in Python** (vs npm/Poetry — a common beginner trap).
- Extras in requirements: `fastapi[standard]`, `langchain-openai>=0.2`.
- Environment markers: `python_version`, `python_full_version`, `sys_platform`, `platform_system`, `extra`; combining with `and`/`or`/`not`.
- Direct URL/Git references — and why libraries should avoid them.
- How `uv add` writes these for you; hand-editing and re-syncing.

**Module 10 — Version specifiers deep dive (PEP 440)**
- Version grammar: epoch, release segments, pre/post/dev releases, local versions; ordering rules.
- `~=` exact behavior (`~=1.4.2` → `>=1.4.2,<1.5.0`; `~=1.4` → `<2.0`).
- Why pre-releases are *excluded* by default and how uv's `--prerelease` flag changes that.
- Pinning philosophy: **applications** effectively pin via the lockfile; **libraries** declare compatible ranges.
- The upper-cap debate (`>=3.10` vs `>=3.10,<3.14`): current guidance and tradeoffs.
- Exercise: decode 10 real-world requirement strings; write specifiers for 5 scenarios.

**Module 11 — Extras vs dependency groups (the modern split)**
- `[project.optional-dependencies]` (extras): runtime features users opt into, published in metadata, part of resolution — e.g., `openai = ["langchain-openai>=0.3"]`.
- `[dependency-groups]` (PEP 735): developer workflow dependencies, never published — `dev`, `lint`, `type`, `test`, `docs`; the `dev` group syncs by default; `default-groups` in `[tool.uv]`.
- All the flags: `--extra x`, `--all-extras`, `--group g`, `--all-groups`, `--no-group`, `--no-dev`.
- Decision rule: *runtime feature → extra; developer tooling → group* — applied to your harness app (provider extras; pytest/ruff/mypy groups).
- Legacy recognition: `[tool.uv] dev-dependencies` in older uv projects → migrate to `[dependency-groups]`.

**Module 12 — `[build-system]`, build backends, and src layout**
- What building means: sdists and wheels; PEP 517 (build API), PEP 518 (build requirements), PEP 660 (editable installs).
- `[build-system]` `requires` + `build-backend`; backend tour: **hatchling** (uv's default for packaged projects), setuptools (legacy giant), uv's own minimal backend, flit-core; when each is appropriate.
- The app-vs-library decision for an enterprise service: packaging (`package = true/false` in `[tool.uv]`), and why packaging your app is usually still worth it.
- Flat vs `src/` layout: why `src/` prevents accidental imports of unpackaged code; how `uv init --lib`/`--package` structure it.
- Editable installs: how uv installs *your* project into `.venv`; `uv sync --no-editable` for production realism.
- What a wheel of *your* package contains (bridges to Module 23 and `py.typed` in Module 30).

**Module 13 — Entry points & the `[tool.uv]` table orientation**
- `[project.scripts]`: `demo = "demo:main"` → how the executable shim lands in `.venv/bin/`; `project.gui-scripts`; naming conventions.
- Running via `uv run demo`; multiple entry points (CLI + server) in the harness app.
- Guided tour of `[tool.uv]` keys you'll meet: `package`, `required-version`, `default-groups`, `environments`, plus teasers for `[[tool.uv.index]]` and `[tool.uv.sources]` (deep dives in Modules 42–43).

---

# PART 4 — The uv Daily Workflow

**Module 14 — `uv add` / `uv remove` in depth**
- Exactly what `uv add fastapi` mutates: `pyproject.toml` → `uv.lock` → `.venv` — the three-layer update.
- Adding with constraints: `uv add "pydantic>=2.7"`, `"fastapi[standard]"`, exact pins.
- `--dev`, `--group <name>`, `--optional <extra>`; adding from Git URLs and local paths.
- `uv remove` and how the lock prunes transitive orphans.
- Upgrading: `uv add --upgrade-package fastapi` (within your constraints) vs widening the constraint first.
- Failure mode: resolution errors at add time — reading them.
- Hand-editing `pyproject.toml` then `uv sync` (auto re-lock) — legitimate workflow.

**Module 15 — `uv lock` and the `uv.lock` file**
- What locking does: resolves the *full* graph — every transitive dependency, for every platform and Python version in your `requires-python` range (**universal resolution** — one lockfile for Linux/macOS/Windows).
- Guided anatomy of a real `uv.lock`: `[[package]]` entries, sources (registry/git/path/editable), sdist+wheel **hashes** (install-time integrity), marker-split dependencies.
- When the lock changes; `uv lock --check` to detect drift in CI.
- Upgrades: `uv lock --upgrade`, `uv lock --upgrade-package <name>`.
- Commit policy: **always commit the lockfile** (for apps and, in the modern consensus, libraries too).
- Lockfile merge conflicts: the correct resolution strategies (never hand-edit except conflicts).
- Resolution conflict deep-dive: reading the "Because you require X..." report; escape hatches — `[tool.uv]` `constraint-dependencies` and `override-dependencies`.

**Module 16 — `uv sync`: making the environment exactly match the lock**
- Exact-sync semantics: installs missing, **removes extraneous**, upgrades/downgrades to match — "`.venv` == lockfile" as a guarantee.
- What syncs by default (project + `dev` group) vs flags: `--extra`, `--all-extras`, `--group`, `--all-groups`, `--no-dev`, `--only-group`.
- The flagship distinctions, taught precisely: `--frozen` (install from lock, never touch it — **the Docker/CI flag**) vs `--locked` (assert lock is up-to-date, then sync — **the CI guard**) vs default behavior.
- `--inexact`, `--reinstall`/`--reinstall-package`, `--dry-run`, `--compile-bytecode`.
- The canonical deployment one-liner: `uv sync --frozen --no-dev`.

**Module 17 — `uv run`: the modern way to execute everything**
- Implicit sync before execution; PATH injection *without* activation.
- `uv run python`, `uv run pytest`, `uv run demo` (your entry point), `uv run uvicorn src.harness.main:app`.
- Environment-selection flags: `--no-sync`, `--frozen`, `--locked`, `--group/--extra/--no-dev` variants.
- Ephemeral layers: `uv run --with <pkg>` / `--with-requirements`; `--isolated`.
- Why `uv run` beats manual activation: reproducibility, scripting, CI, git hooks.
- Exit codes and scripting; running Makefile targets and pre-commit hooks through it.

**Module 18 — The `uv pip` interface & requirements.txt interop**
- The escape hatch: `uv pip install/list/show/freeze/check` — pip-compatible commands inside uv projects.
- `uv pip compile` (pip-tools-style resolution to requirements.txt) and `uv pip sync`.
- `uv export --format requirements-txt`: `--no-dev`, `--all-extras`, `--frozen`, hashes on/off.
- When requirements files are still genuinely needed: some PaaS/platforms, Airflow-style constraint systems, security scanners.
- Constraint files vs requirements files; caution with `--system`.

**Module 19 — PEP 723 scripts, `uv tool` and `uvx`**
- Inline script metadata: the `# /// script` block (`dependencies`, `requires-python`); `uv run script.py` builds an ephemeral env; `uv add --script` manages script deps.
- Use cases: ops scripts, reproducible one-off tools, shareable single files.
- `uvx <tool>` / `uv tool run` for ephemeral tools; pinned versions (`uvx ruff@<version>`).
- `uv tool install/list/upgrade/uninstall`; where tools live; why uvx replaced pipx.
- Keeping CI tools (ruff, etc.) out of your project env via uvx.

**Module 20 — Inspecting, troubleshooting, and the uv cache**
- Inspection: `uv tree` (dependency tree), `uv pip list --outdated`, `uv pip check`, `uv pip show`.
- Anatomy of resolution failures: backtracking reports, "no solution" cases, transitive conflicts; the fix patterns (upgrade pairs together, loosen specifiers, constraints/overrides).
- Cache management: `uv cache dir/clean/prune`; what's cached (wheels, sdists, git, HTTP); hardlinks vs copies (`UV_LINK_MODE`) — and the Docker cross-filesystem gotcha.
- Offline/air-gapped work: `--offline`, export + local wheel directory patterns.
- Teaser on *why* uv is fast (full internals in Module 51).

---

# PART 5 — Versioning & Release Engineering

**Module 21 — Versioning strategy**
- SemVer semantics vs Python-ecosystem reality; `0.x` rules; when to hit `1.0`.
- Pre (`a/b/rc`), post, and dev release usage; local versions.
- CalVer (`2025.10.0`) as an option for dated app releases.
- Policies: version lives in exactly one place (pyproject); changelogs (Keep a Changelog format); deprecation windows; breaking-change process.
- Choosing/maintaining `requires-python` and syncing classifiers as Pythons EOL.

**Module 22 — Dynamic versioning from Git**
- The problem: version duplicated in pyproject vs Git tags.
- `dynamic = ["version"]`; `hatch-vcs` and `setuptools-scm` configured with uv; generated `_version.py` files; dirty-tree suffixes.
- Tagging discipline: annotated `vX.Y.Z` tags; tag prefixes for workspace members later.
- The full release checklist (tag → build → publish → GitHub Release → changelog).
- Optional automation with python-semantic-release.

**Module 23 — `uv build` & `uv publish`**
- `uv build` → sdist + wheel; wheel anatomy: METADATA, RECORD, entry_points, and where `py.typed` must appear; `py3-none-any` tags for pure Python.
- sdist vs wheel: who consumes each, why you publish both.
- `uv publish`: tokens vs **Trusted Publishing (OIDC)** — the modern, secret-less method via GitHub Actions; TestPyPI dry runs; PEP 740 attestations.
- Verifying artifacts before upload.
- The enterprise reality check: your app may never hit PyPI — your artifact is often the Docker image (bridges to Module 45); publishing matters for your *internal shared libraries*.

---

# PART 6 — Static Typing

**Module 24 — Modern type hints fundamentals**
- Why types: correctness, IDE intelligence, documentation — and FastAPI/Pydantic turn them into *runtime* behavior.
- Syntax: parameters, returns, variable annotations; `x: int | None = None` pattern.
- Modern built-in generics: `list[int]`, `dict[str, Any]`, `tuple[int, ...]`; `X | Y` unions (3.10+); `from __future__ import annotations` for older runtimes.
- `Any` vs `object`; `type X = ...` aliases (3.12+).
- The deprecation map: `typing.List/Dict/Optional/Union` → builtins/`|`; `collections.abc` for `Sequence/Iterable/Mapping`.
- Practice: fully annotate a small FastAPI handler + Pydantic model.

**Module 25 — Domain types: TypedDict, dataclasses, Literal, Annotated**
- `TypedDict`: class syntax, `Required`/`NotRequired`, when it beats a Pydantic model (static shape vs runtime validation — the decision matrix).
- `@dataclass`: `frozen`, `slots`, `kw_only`, `field(default_factory=...)` — vs Pydantic models (validation!).
- `NamedTuple`, `Literal`, `Final`, `StrEnum` (3.11+), `datetime`/`Path` typing.
- `Annotated[str, Field(max_length=50)]` — how FastAPI and Pydantic consume annotation metadata.
- `Callable[[int], str]`.

**Module 26 — Protocols, structural typing, and stubs**
- `typing.Protocol`: formalized duck typing; `@runtime_checkable` and its limits; builtin protocols (`Iterable`, `Sequence`).
- ABC vs Protocol — choosing.
- Typing *untyped* third-party code: per-module ignores, stub packages (`types-*`), `TYPE_CHECKING` guard + local stub classes, `Any` firewalls.
- `cast`, `reveal_type` debugging, `assert_type`, `typing_extensions` for new features on older Pythons.
- Where stubs come from: typeshed (concept).

**Module 27 — Generics & advanced typing**
- Motivation via a realistic `Repository`/`Result` example.
- `TypeVar` (classic), `bound=`, constraints; **PEP 695 syntax** `def first[T](items: list[T]) -> T` and `class Repo[T]` (3.12+) — old vs new side by side.
- `@overload`; `@override` (3.12+) and `final`.
- Typing generators, async iterators/awaitables, context managers.
- Variance intuition: why `list[Dog]` is not `list[Animal]`.
- Discipline: when generics are worth it in application code vs over-engineering.

**Module 28 — mypy in practice**
- Install into the `type` group; run `uv run mypy src`.
- `[tool.mypy]`: `python_version`, `strict = true`, per-module `[[tool.mypy.overrides]]` (relaxing `tests.*`), `ignore_missing_imports` scoping, `plugins = ["pydantic.mypy"]`.
- The src-layout gotcha (`mypy_path = "src"`).
- Top-10 error tour with fixes: `import-untyped`, `arg-type`, `assignment`, `return-value`, `union-attr`, `no-any-return`, etc.
- Narrowing tools: `isinstance`, `assert`, `match`, `TypeGuard`/`TypeIs`.
- Gradual adoption strategy; `.mypy_cache` and gitignore; mypy's boundary vs Pydantic's runtime validation.

**Module 29 — pyright & the editor experience**
- pyright (CLI) vs Pylance (VS Code); speed/strictness differences vs mypy; when teams run one vs both.
- Install & run (note its Node runtime quirk); `[tool.pyright]`: `include`, `exclude`, `typeCheckingMode`, venv discovery of `.venv`.
- The editor loop: hover types, inline errors, quick fixes, format-on-save — pointing VS Code at the uv interpreter.
- Choosing your CI gate checker and keeping one canonical config.

**Module 30 — `py.typed` & PEP 561: shipping types**
- The contract: a package opts into inline types by including the `py.typed` marker file.
- Exactly where it goes (package root beside `__init__.py`) and how each backend includes it in the wheel (hatchling vs setuptools config).
- Verifying: inspect the built wheel; consume your own package from a second project and confirm mypy sees the types.
- Applying this to your future internal shared libraries.
- Cleaning typing legacy with Ruff's `UP` rules (bridges to Part 7).

---

# PART 7 — Linting, Formatting, Quality Gates

**Module 31 — Ruff linter deep dive**
- Setup in the `lint` group; `ruff check .`, `--fix`, `--unsafe-fixes` (what "unsafe" means), `ruff rule E501` for in-terminal docs.
- `[tool.ruff]`: `target-version`, `line-length`; `[tool.ruff.lint]`: `select`/`ignore`/`per-file-ignores`.
- Rule-family tour with one example each: `E/W`, `F` (unused imports — the daily one), `I` (import sorting), `N`, `UP` (modernize — your deprecation-killer), `B` (bugbear), `SIM`, `C4`, `PT` (pytest style), **`ASYNC` (critical for FastAPI)**, `S` (security subset), `RUF`.
- CI mode: `ruff check --no-fix` fails the build.
- Why one Rust tool replaced flake8+isort+pyupgrade+pydocstyle+most-of-bandit.

**Module 32 — Ruff formatter & hygiene**
- `ruff format .` / `--check` / `--diff`; Black-compatible philosophy; config (`quote-style`, magic trailing comma); what it deliberately doesn't do (docstring interiors, import order — that's `I` rules).
- The canonical pipeline order: `ruff format` → `ruff check --fix` → mypy → pytest.
- `# noqa` discipline, `RUF100` (unused noqa), `--statistics`, `--add-noqa`.
- Format-on-save setup; pinning the ruff version for a team.

**Module 33 — pre-commit: enforcing quality before commits**
- `.pre-commit-config.yaml` structure: `repos`/`rev`/`hooks`/`args`.
- The standard set for this stack: `pre-commit/pre-commit-hooks` (end-of-file-fixer, trailing-whitespace, check-toml, check-yaml, check-merge-conflict), Ruff's official hooks, **mypy as a `local` hook running through `uv run`**, gitleaks/detect-secrets.
- `pre-commit install`; `pre-commit run --all-files`; `pre-commit autoupdate`.
- Running the *same* config in CI (single source of truth); why `--no-verify` is a code smell.

---

# PART 8 — Testing & Coverage

**Module 34 — pytest fundamentals & modern config**
- Install into the `test` group; discovery rules (`test_*.py`, `Test*` classes, `test_*` functions) and naming pitfalls.
- Plain `assert`, `pytest.approx`, `pytest.raises(..., match=...)`.
- `[tool.pytest.ini_options]` in pyproject (the modern location): `testpaths`, `addopts` (`-q --strict-markers`), marker registration, `filterwarnings`, `pythonpath`.
- `conftest.py` introduction; running: `uv run pytest`, `-v`, `-x`, `-k`, `-m`, `--lf`, `--tb=short`.
- The test pyramid for your app: unit → service/API → e2e.

**Module 35 — Fixtures, parametrize, and markers**
- `@pytest.fixture`: scopes (function/class/module/session), `yield` teardown, `autouse`, fixture factories.
- Built-ins you'll use constantly: `tmp_path`, `monkeypatch` (`setattr`, `delenv`, `setenv`), `capsys`, `caplog`.
- `conftest.py` hierarchy and sharing fixtures across the repo.
- `@pytest.mark.parametrize`: stacking, `ids=`, `pytest.param(..., id=..., marks=...)`.
- Custom markers (`slow`), `skipif`/`xfail`, `-m "not slow"` CI policy.

**Module 36 — Testing FastAPI applications**
- `TestClient` (sync, httpx-based): requests, `json=`, status asserts; `with TestClient(app) as client:` to trigger lifespan.
- Native async: `httpx.AsyncClient` + `ASGITransport`; **anyio vs pytest-asyncio** — tradeoffs and configuring one (`asyncio_mode = "auto"`).
- App fixtures; `dependency_overrides` for auth, settings, and provider dependencies.
- Testing streaming responses; where handler tests vs client-level tests belong.

**Module 37 — Mocking LLMs & external services**
- The seam-first design: a `Protocol` for your LLM provider; real LangChain-backed implementation + deterministic fake; swap via `dependency_overrides`.
- `unittest.mock`/pytest-mock vs `monkeypatch.setattr` — when each is appropriate.
- Fakes you'll build: deterministic hash-based embeddings, scripted chat models (LangChain ships fake chat models for exactly this — locate the current utilities in `langchain_core`), in-memory vector store.
- `respx` for httpx-level provider API interception; golden/snapshot testing of prompts.
- Time freezing (`time-machine`/`freezegun`) for token accounting and date logic.
- Policy: unit tests always offline; real-API tests behind a marker excluded from CI.

**Module 38 — coverage.py fundamentals & the `.coverage` file**
- How coverage works: tracing executed lines/branches; **the `.coverage` SQLite data file — what it is, why it appears, gitignore it**.
- Run modes: `coverage run -m pytest` vs pytest-cov; when you need raw coverage (subprocesses).
- `[tool.coverage.run]` in pyproject (modern location, vs legacy `.coveragerc`): `branch = true`, `source`, `omit`, `parallel`, `relative_files = true` (CI!).
- `[tool.coverage.report]`: `fail_under`, `show_missing`, `skip_covered`, and an honest `exclude_also` list (`if TYPE_CHECKING:`, `@overload`, `raise NotImplementedError`, `__main__` guard).
- Line vs branch coverage; realistic targets (80–90%); the anti-gaming policy.

**Module 39 — pytest-cov, thresholds, parallel runs, and CI reporting**
- pytest-cov in the `test` group; `--cov` flags wired into `addopts`; threshold gates that fail the build.
- Parallel testing with pytest-xdist + coverage combining (`.coverage.*` files → `coverage combine`).
- Reports: terminal `term-missing`, `htmlcov/`, `cobertura.xml`; artifact upload and services like Codecov; diff/patch coverage on PRs.
- Wiring it all into the `uv run pytest` command your team types daily.

---

# PART 9 — Production Engineering

**Module 40 — Configuration & secrets (12-factor for the harness app)**
- 12-factor principles: config from environment, never in code.
- `pydantic-settings`: `BaseSettings`, nested models, `.env` loading, env prefixes, required keys that fail fast at startup, cached `get_settings()` as a FastAPI dependency.
- `.env` vs `.env.example` (committed) vs real secret managers (Vault/AWS Secrets Manager/Doppler — concept level); env/secrets in Docker & K8s.
- The `.gitignore` master list for this whole course (`.venv/`, `.env`, `.coverage`, `htmlcov/`, caches, `dist/`).
- LLM provider key handling (`OPENAI_API_KEY`, etc.); never logging secrets (ties to gitleaks + logging filters).

**Module 41 — Enterprise repository structure**
- The full tree for your app: `src/harness/` with `core/` (config, logging, errors), `api/` (routes, deps), `services/`, `llm/` (providers, prompts), `schemas/`, `vectordb/`, `workers/`; plus `tests/{unit,integration,e2e}/`, `scripts/`, `docs/`, `.github/workflows/`, `Dockerfile`, `compose.yaml`.
- Import rules that prevent circular imports (api → services → llm, never upward).
- Task runners: a `Makefile` of `uv run` commands (or `poe-the-poet` `[tool.poe.tasks]`) — pick one; the "golden path" README (clone → `uv sync` → `uv run`).
- Where research notebooks and PEP 723 experiment scripts live.

**Module 42 — uv workspaces (monorepos)**
- When to split: shared `harness-core`, provider plugin packages, the API app.
- `[tool.uv.workspace] members`; per-member pyproject; virtual roots.
- Cross-references: `dependencies = ["harness-core"]` + `[tool.uv.sources] harness-core = { workspace = true }`; automatic editable wiring.
- Running/testing per member (`uv run --package <name> ...`); publishing members with tag prefixes.
- Warning against early over-modularization — start single-package, extract later.

**Module 43 — Private indexes & enterprise registries**
- Why: internal packages, compliance, mirrors.
- `[[tool.uv.index]]`: `name`, `url`, `default`, `explicit`; per-dependency index selection via `[tool.uv.sources]`.
- Authentication: per-index env vars, `.netrc`, keyring; the AWS CodeArtifact token-refresh pattern; Google Artifact Registry.
- TLS/cert configuration; `allow-insecure-host` (and its risk).
- Air-gapped mirror strategies; interop with legacy pip CI via `uv export`.

**Module 44 — Dependency security & auditing**
- Supply-chain threat model: typosquatting, compromised transitive deps, malicious versions.
- Auditing: **pip-audit** driven from `uv export --frozen` (the reliable pattern) and uv's built-in `uv audit` on recent versions (verify availability with `uv audit --help`); SBOMs with syft/grype (concept + commands).
- Lockfile hashes as install-time integrity.
- Automated updates: **Renovate** (first-class uv support) vs Dependabot (verify current uv support) — config files, lockfile-maintenance PRs.
- The CVE response playbook: triage → `uv lock --upgrade-package` → ship → document.
- Safe defaults: scoped extras, no untrusted `git+` URLs, `--prerelease` caution.

**Module 45 — Docker with uv**
- Base image strategy: `python:3.12-slim` + copy the uv binary from `ghcr.io/astral-sh/uv` (or uv's images).
- The layer-caching order: `COPY pyproject.toml uv.lock` → `RUN uv sync --frozen --no-dev --compile-bytecode` → `COPY src/`.
- `UV_LINK_MODE=copy` (the container-filesystem gotcha); BuildKit `--mount=type=cache` alternative.
- Multi-stage builds (builder → slim runtime); copying `.venv` and putting it on `PATH`; running as non-root.
- Runtime: `uvicorn --workers` (and the gunicorn+UvicornWorker alternative); `HEALTHCHECK` hitting `/health`.
- `.dockerignore` (`.venv`, `.git`, tests, `.coverage`, caches); image scanning (grype/trivy); why the lockfile makes images reproducible.

**Module 46 — CI/CD with GitHub Actions**
- Workflow-file anatomy (jobs/steps/uses/run) — fast primer.
- `astral-sh/setup-uv`: pin the uv version, `python-version`, `enable-cache` + cache-dependency glob.
- The pipeline: `uv sync --locked` (drift guard) → ruff → mypy → pytest+coverage (matrix over 3.12/3.13, ubuntu [+ mac/win if relevant]) → build image → publish (on tag).
- Coverage artifacts + Codecov upload; pre-commit job; branch protection + required checks; concurrency cancellation.
- Publishing with **Trusted Publishing** (`permissions: id-token: write`); release flow tag → GitHub Release; optional python-semantic-release.

**Module 47 — Production observability essentials**
- Structured logging with structlog (JSON in prod, pretty console in dev); request IDs via contextvars; uvicorn/FastAPI log config interplay; never logging PII/keys.
- `/health` (liveness) vs `/ready` (dependency-aware readiness) — used by Docker/K8s probes.
- Metrics: prometheus-fastapi-instrumentator quickstart (RED metrics).
- Tracing: OpenTelemetry instrumentation for FastAPI/httpx; LangSmith as the LLM-call tracing option — wiring and tradeoffs.
- Sentry SDK init in lifespan; how these deps are grouped/extras'd in pyproject.

---

# PART 10 — LangChain-Specific Dependency Engineering

**Module 48 — The LangChain ecosystem dependency map & strategy**
- The package landscape: `langchain-core` (abstractions: runnables, messages, prompts), `langchain` (orchestration; the 1.x `create_agent` era), `langchain-community`, `langchain-text-splitters`, partner packages (`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`, …) — **prefer partner over community** for the same integration — `langgraph` (the orchestration backbone for a harness), `langsmith`.
- Lockstep versioning: the family releases together; upgrade the set together with multiple `--upgrade-package` flags; watch core↔partner compatibility.
- Pinning strategy for an *app*: floors in pyproject, exactness from `uv.lock`.
- Provider-plugin design with **extras**: `[project.optional-dependencies]` per provider/vector-store, lazy/conditional imports with clear errors.
- Pydantic v2 + FastAPI version alignment; typing LangChain objects in your code (`Runnable[Input, Output]`, message types).
- Heavy-dep discipline (tokenizers, embeddings, torch): extras only; GPU-wheel index configuration with `[[tool.uv.index]]` (light touch).
- Current-state caveat: this ecosystem restructures fast — have the teaching AI verify package names/versions against current docs.

**Module 49 — Capstone: the enterprise AI harness skeleton**
- Spec: FastAPI + LangGraph agent with tool calling; pluggable providers (openai/anthropic extras); optional vector stores; `/health` + `/ready`; structured logs; fake-provider tests at ≥85% branch coverage; strict mypy; clean Ruff; pre-commit; full CI; Docker image; tagged `v0.1.0`.
- Ordered build path with acceptance criteria at each step: scaffold (M6/41) → config (M40) → typed schemas (M24–27) → provider Protocol + fakes (M26/37) → real providers (M48) → API layer (M36) → tests+coverage (M34–39) → quality gates (M31–33, M28) → CI (M46) → Docker (M45) → release (M21–23).
- Final self-audit: a checklist mapping every prior module to a concrete artifact in your repo.
- The onboarding test: a stranger clones, runs `uv sync` + `uv run`, and gets a working server in under 10 minutes.

---

# PART 11 — Legacy Literacy & Internals

**Module 50 — Reading legacy projects & migrating to uv**
- Rosetta stone: `setup.py`/`setup.cfg` → `[project]`; `requirements.txt` → lockfile; `Pipfile`/`poetry.lock`/`environment.yml` recognition; pyenv → `uv python`; pipx → `uvx`; scattered ini configs → `[tool.*]` tables.
- The migration playbook: inventory (`pip freeze`) → `uv init` → translate metadata to PEP 621 → split dev deps into groups → swap CI → verify parity via freeze-diff → rollback plan.
- Organizational constraints (locked-down CI, EOL Pythons) and workarounds.

**Module 51 — uv internals, env vars, and staying current**
- Why uv is fast: Rust, parallel downloads, global cache with hardlinks, no interpreter startup cost; the resolver approach (PubGrub-style, concept level).
- Where things live: cache dir, managed-Python dir, tool dir; inspecting them.
- `UV_*` env var quick reference: `UV_PYTHON`, `UV_PROJECT_ENVIRONMENT`, `UV_CACHE_DIR`, `UV_LINK_MODE`, `UV_OFFLINE`, per-index auth vars.
- `uv self update`; pinning uv's version in CI and pre-commit; reading the uv changelog.
- Following the standard: the relevant PEP index (440, 508, 517/518, 561, 604/585, 621, 660, 695, 723, 735, 740); PyPA guides; Astral blog.
- A maintenance cadence for your app: weekly `uv lock --upgrade`, monthly audit, quarterly Python-version review; Ruff `UP` as your automated deprecation fighter.

---

## Final guidance

1. **Do the modules in order.** Each assumes the previous. Parts 6 and 7 (typing / linting) can be swapped if you prefer.
2. **One repo, always.** Everything from Module 6 onward mutates your practice repo — by Module 49 it *is* your harness app.
3. **Fast track** (if you must start building sooner): 1–2, 5–6, 9, 11–12, 14–20, 24, 28, 31, 34–39, 41, 45–46, 48–49 — then circle back for the rest as the project matures.
4. **Pace:** ~2–4 modules/week ≈ 4–6 months to full mastery; the fast track ≈ 6–8 weeks.
5. **Trust hierarchy when answers conflict:** tool `--help` output → official docs (docs.astral.sh/uv, peps.python.org, pypa.io) → the AI. The ecosystem moves quickly; the master prompt makes your AI verify rather than guess.
