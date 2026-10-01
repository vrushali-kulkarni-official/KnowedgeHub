This module is important because almost every later Python decision becomes easier once you understand **which problem each tool is solving**.

The biggest idea I want you to leave with is this:

> **Python itself runs your code.
> uv manages the Python environment around your code.
> pyproject.toml describes the project.
> uv.lock records a resolved dependency graph.
> Type checkers analyze types.
> Ruff analyzes and formats code.
> pytest runs tests.
> pre-commit automates checks before commits.
> Coverage.py measures which code your tests actually executed.**

There are also a few important corrections to the wording in your original list. For example, `pyproject.toml` is extremely important, but it is **not literally a configuration file for everything**, and `.coverage` is data rather than configuration.

---

# PART 1 — Orientation & Setup

# Module 1 — The Modern Python Tooling Landscape

## 1. The goal of this module

Before learning commands such as:

```bash
uv add
uv sync
uv run
uv lock
uv python install
pytest
ruff check
mypy
pre-commit
```

you should understand **why these commands exist**.

Otherwise Python tooling feels like a collection of unrelated commands.

You might learn:

```text
uv
venv
pip
pyproject.toml
uv.lock
pytest
ruff
mypy
pre-commit
```

but still not understand:

> "Which one owns what?"

The correct way to learn this is to divide the Python ecosystem into **problem domains**.

---

# 2. The four major problem domains

At the highest level, modern Python project tooling is solving four different problems.

```text
                    PYTHON PROJECT
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
  1. Interpreter     2. Environment    3. Dependencies
     management          isolation       & reproducibility
          │               │                │
          ▼               ▼                ▼
       Python             .venv       pyproject.toml
       uv python                        uv.lock
                                          uv
                          │
                          ▼
                  4. Build & distribution
                          │
                          ▼
                 pyproject.toml
                 build backend
                 wheel / sdist
```

Then around these are the **development-quality tools**:

```text
                         YOUR CODE
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
       pytest          mypy/pyright          Ruff
       testing         type checking       lint/format
          │                 │                  │
          └─────────────────┼──────────────────┘
                            ▼
                       pre-commit
                  automatic local enforcement
```

And:

```text
pytest + coverage.py
          │
          ▼
     .coverage
          │
          ▼
     coverage report
```

---

# 3. First: understand what "Python" actually means

When we say:

> "I am using Python 3.x"

we're talking about much more than a command called `python`.

A Python installation consists broadly of:

```text
Python distribution
       │
       ├── python executable
       │
       ├── standard library
       │
       └── supporting files
```

uv's documentation explicitly describes a Python version this way: interpreter + standard library + supporting files. ([Astral Docs][1])

The executable is what actually executes your code.

For example:

```bash
python app.py
```

means approximately:

```text
shell
 │
 ▼
python executable
 │
 ▼
Python interpreter
 │
 ▼
parse source
 │
 ▼
execute Python program
```

This is why **uv is not Python**.

uv does not replace the Python language/runtime.

Instead:

```text
Python = runtime

uv = tooling around the runtime
```

This distinction is fundamental.

---

# 4. Domain 1 — Interpreter management

## What problem does interpreter management solve?

Suppose your system contains:

```text
Python 3.12
Python 3.13
Python 3.14
```

and your project requires:

```text
Python >=3.13
```

Which Python should the project use?

That's an **interpreter management problem**.

Another example:

You develop using:

```text
Python 3.14.1
```

but someone else has:

```text
Python 3.13.9
```

Your code may behave differently.

So we need mechanisms for:

```text
finding Python
installing Python
selecting Python
pinning Python
switching Python
```

---

# 5. Python vs `.python-version` vs `uv python`

These are three different things.

## Python

Python is the actual runtime.

Example:

```bash
python --version
```

might produce:

```text
Python 3.14.x
```

That executable performs the actual execution.

---

## `.python-version`

`.python-version` is **not the Python interpreter**.

It is a small file expressing:

> "This is the Python version this project should default to."

For example:

```text
3.14
```

uv searches for `.python-version` files when determining the default Python request, and `uv python pin` can create one. ([Astral Docs][1])

Think of:

```text
.python-version
```

as:

> **project preference/pinning**

rather than:

> **the interpreter itself**

---

## `uv python`

`uv python` is the mechanism for managing Python installations and discovery.

For example:

```bash
uv python list
```

```bash
uv python install 3.14
```

```bash
uv python pin 3.14
```

uv can discover existing system interpreters and can also install/manage Python versions itself. ([Astral Docs][1])

Conceptually:

```text
                    uv python
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
      discover Python       install Python
             │                   │
             └─────────┬─────────┘
                       ▼
                 choose interpreter
```

---

# 6. `.python-version` vs `requires-python`

This is a very important distinction.

You will eventually have something like:

```toml
[project]
requires-python = ">=3.13"
```

and possibly:

```text
.python-version
```

containing:

```text
3.14
```

They serve different purposes.

## `.python-version`

Answers:

> Which Python should I normally use for this project?

## `requires-python`

Answers:

> Which Python versions does this project support?

For example:

```toml
requires-python = ">=3.13"
```

could mean:

```text
3.13 → supported
3.14 → supported
3.15 → potentially supported
```

while:

```text
.python-version = 3.14
```

means:

> My development environment defaults to Python 3.14.

So:

```text
.python-version
       │
       ▼
development/default interpreter

requires-python
       │
       ▼
project compatibility requirement
```

Do not confuse them.

---

# 7. Domain 2 — Environment isolation

Now suppose you have:

```text
Project A → FastAPI 0.x
Project B → FastAPI 1.x
```

If both use the same global Python environment:

```text
global Python
     │
     ├── fastapi 0.x
     └── fastapi 1.x   ← impossible to satisfy cleanly
```

You have a conflict.

So Python projects generally use **virtual environments**.

---

# 8. What is a virtual environment?

A virtual environment is an isolated Python environment containing its own:

```text
Python interpreter
site-packages
installed libraries
executables
```

Python's standard library provides the `venv` module for creating these isolated environments. ([Python documentation][2])

For example:

```bash
python -m venv .venv
```

creates:

```text
project/
├── .venv/
└── ...
```

You can conceptually think of it as:

```text
system Python
    │
    ├── Project A → .venv
    │
    ├── Project B → .venv
    │
    └── Project C → .venv
```

Each environment has its own installed packages.

---

# 9. `venv` vs uv

This needs an important correction to your proposed translation.

It is **not** really:

```text
venv → automatic via uv
```

A better description is:

```text
venv = standard-library mechanism for making virtual environments

uv = higher-level project manager that automatically creates/manages
     a project .venv as part of the project workflow
```

uv can also explicitly create a virtual environment:

```bash
uv venv
```

and its project workflow automatically creates `.venv` when needed. ([Astral Docs][3])

So `venv` hasn't become obsolete.

Rather:

```text
venv
  ↓
still valid low-level Python mechanism

uv
  ↓
higher-level workflow that manages it for you
```

---

# 10. The `.venv` directory

In a modern uv project you commonly see:

```text
project/
├── .venv/
├── .python-version
├── pyproject.toml
└── uv.lock
```

uv's current project documentation shows `.venv`, `.python-version`, `pyproject.toml`, and `uv.lock` as the normal project structure. ([Astral Docs][4])

The `.venv` directory is normally:

```text
local
temporary-ish
machine-specific
not committed to Git
```

You generally put it in `.gitignore`.

You commit:

```text
pyproject.toml
.python-version
uv.lock
```

not:

```text
.venv/
```

---

# 11. Why environment isolation matters

Consider:

```text
Project A
Python 3.14
FastAPI 1.x
Pydantic 2.x

Project B
Python 3.13
FastAPI another-version
Pydantic another-version
```

With isolated environments:

```text
Project A
   │
   └── .venv
        ├── Python environment
        ├── FastAPI
        └── Pydantic

Project B
   │
   └── .venv
        ├── Python environment
        ├── FastAPI
        └── Pydantic
```

They don't need to fight with each other.

---

# 12. Domain 3 — Dependency resolution and reproducibility

This is where things become more interesting.

Suppose your application depends on:

```text
fastapi
```

FastAPI itself might depend on:

```text
starlette
pydantic
typing-extensions
...
```

And those packages have dependencies of their own.

You therefore don't really have:

```text
your app → fastapi
```

You have:

```text
your app
   │
   └── fastapi
        ├── starlette
        │    └── ...
        ├── pydantic
        │    ├── ...
        │    └── ...
        └── typing-extensions
```

This is a **dependency graph**.

---

# 13. Dependency resolution

Suppose:

```text
Your app:
    pydantic >=2.8

Library A:
    pydantic >=2.7,<3

Library B:
    pydantic >=2.9,<3

Library C:
    pydantic >=2.10
```

The resolver needs to find a version satisfying all constraints.

Potential result:

```text
pydantic 2.12.x
```

The job of a dependency resolver is therefore roughly:

```text
input:
    requirements + constraints

        ↓

dependency graph solving

        ↓

compatible versions

        ↓

resolved dependency set
```

That's different from merely installing packages.

---

# 14. `pyproject.toml`

This is the central standardized project configuration file in modern Python packaging.

The PyPA specification currently defines three major standardized tables:

```toml
[build-system]

[project]

[tool.*]
```

`[build-system]` defines how the project is built, `[project]` describes standard project metadata, and `[tool]` contains tool-specific configuration. ([Python Packaging][5])

So:

```text
pyproject.toml
│
├── [build-system]
│
├── [project]
│
└── [tool.*]
```

---

# 15. Why `pyproject.toml` is so important

Historically, Python projects scattered configuration across many files:

```text
setup.py
setup.cfg
requirements.txt
requirements-dev.txt
pytest.ini
mypy.ini
.flake8
isort.cfg
.black
...
```

Modern Python lets many of those concerns converge into:

```text
pyproject.toml
```

For example:

```toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi",
    "pydantic",
]

[dependency-groups]
dev = [
    "pytest",
    "ruff",
    "mypy",
]

[tool.ruff]
...

[tool.mypy]
...

[tool.pytest]
...

[tool.coverage.run]
...

[tool.uv]
...
```

This is why people often call it the:

> **modern central configuration file for Python projects**

But don't turn that into:

> "`pyproject.toml` replaces every other file."

It doesn't.

---

# 16. Things that still legitimately live outside `pyproject.toml`

For example:

```text
.python-version
uv.lock
.pre-commit-config.yaml
Dockerfile
compose.yaml
.github/workflows/*.yml
.gitignore
README.md
LICENSE
```

And:

```text
.coverage
```

isn't configuration at all.

It's generated coverage data.

So a much better mental model is:

> **`pyproject.toml` is the central declarative configuration/metadata file for the Python project, but it is not the one file containing literally everything in the repository.**

---

# 17. `[project]` vs `[tool.*]`

This distinction is extremely important.

## `[project]`

This is standardized project metadata.

Example:

```toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.13"

dependencies = [
    "fastapi",
    "pydantic",
]
```

This information has standardized meaning across Python packaging tools.

---

## `[tool.*]`

This is where tools put tool-specific configuration.

For example:

```toml
[tool.ruff]
line-length = 100
```

means something to Ruff.

```toml
[tool.mypy]
strict = true
```

means something to mypy.

```toml
[tool.uv]
...
```

means something to uv.

This extensibility is deliberate. The PyPA specification defines `[tool]` specifically for tool-specific subtables. ([Python Packaging][6])

---

# 18. `uv.lock`

Now we arrive at one of the most important files in your future projects.

`pyproject.toml` says approximately:

> "These are the dependencies I require."

`uv.lock` says:

> "This is the dependency solution that was actually resolved."

Example conceptually:

```text
pyproject.toml

fastapi >= X
pydantic >= Y
httpx >= Z
```

versus:

```text
uv.lock

fastapi = exact resolved version
pydantic = exact resolved version
httpx = exact resolved version
starlette = exact resolved version
...
```

uv describes `uv.lock` as a cross-platform lockfile containing exact resolved dependency information and recommends committing it to version control. ([Astral Docs][4])

---

# 19. Why do we need both `pyproject.toml` and `uv.lock`?

Because they answer different questions.

### `pyproject.toml`

```text
"What does my project require?"
```

### `uv.lock`

```text
"What exact dependency graph did we resolve?"
```

This is similar to:

```text
recipe
   vs
actual shopping list
```

The recipe:

```text
flour >= X
milk >= Y
```

doesn't tell you exactly what version/combination was selected.

The lockfile records the actual resolution.

---

# 20. Why reproducibility matters

Imagine:

### Monday

You install:

```text
FastAPI 1.x
Pydantic 2.x
Starlette X
```

Everything works.

### Friday

A new release happens.

You run installation again.

Without a lockfile you might get:

```text
FastAPI newer
Pydantic newer
Starlette newer
```

and suddenly:

```text
tests fail
behavior changes
build breaks
```

With a lockfile:

```text
pyproject.toml
       +
uv.lock
       ↓
same resolved dependency graph
```

This is one of the central reasons applications should normally commit their lockfile.

uv automatically locks and syncs its project environment and provides `--locked` / `--frozen` modes when you want CI or another environment to refuse lockfile changes. ([Astral Docs][7])

---

# 21. Important distinction: reproducibility is not absolute immortality

A lockfile dramatically improves reproducibility.

But:

```text
same uv.lock
```

doesn't mean:

> "Every possible aspect of the universe will be identical."

There can still be differences caused by:

```text
operating system
CPU architecture
Python interpreter
system libraries
native extensions
environment variables
external services
database versions
OS behavior
hardware
```

The important thing is that the **Python dependency graph** is intentionally controlled.

uv's lockfile is cross-platform and can encode platform-specific dependency requirements where necessary. ([Astral Docs][8])

---

# 22. A major 2026 update: `pylock.toml`

There is an important modern development that your original legacy table doesn't account for.

PEP 751 standardized a Python lockfile format called:

```text
pylock.toml
```

It is intended to be a standardized, tool-agnostic Python lockfile format. ([Python Enhancement Proposals (PEPs)][9])

But:

> **This does not mean `uv.lock` has become obsolete.**

uv's current documentation explicitly says that its project interface continues to use `uv.lock` because it can represent functionality that `pylock.toml` cannot currently express. uv can export to `pylock.toml` when interoperability is needed. ([Astral Docs][8])

So for a normal uv-managed application:

```text
pyproject.toml
        +
uv.lock
```

remains the important project workflow.

And:

```text
pylock.toml
```

is the standardized interoperability format to know about.

---

# 23. Dependency declaration vs dependency locking

Do not mix these two concepts.

### Declaration

```toml
[project]
dependencies = [
    "fastapi>=..."
]
```

means:

> What my application needs.

### Resolution

```text
uv lock
```

means:

> Solve the dependency graph.

### Installation/synchronization

```bash
uv sync
```

means:

> Make my environment match the locked project state.

This distinction is extremely important.

---

# 24. `uv`

Now we can finally explain uv properly.

uv is not simply:

> "a faster pip."

That is too simplistic.

The current uv project/tooling ecosystem includes functionality for:

```text
Python versions
virtual environments
dependency management
dependency resolution
locking
running commands
tool isolation
building packages
publishing packages
pip-compatible workflows
workspaces
caching
```

Its CLI exposes interfaces including `uv python`, `uv pip`, `uv venv`, `uv build`, `uv publish`, `uv tool`, and project commands such as `uv add`, `uv sync`, `uv lock`, and `uv run`. ([Astral Docs][3])

That's why uv can serve as the **orchestrator** for your Python project.

---

# 25. What does "orchestrator" mean?

Think of a conductor in an orchestra.

The conductor doesn't play:

```text
violin
piano
drums
flute
```

himself.

Instead, the conductor coordinates them.

Similarly:

```text
                     uv
                      │
        ┌─────────────┼──────────────┐
        │             │              │
        ▼             ▼              ▼
     Python        .venv         dependencies
        │             │              │
        ▼             ▼              ▼
   interpreter     isolation      resolution
                      │
                      ▼
                   uv.lock
```

Then:

```text
uv run pytest
uv run ruff
uv run mypy
```

lets uv execute those tools inside the project's environment.

---

# 26. Why uv feels like it replaces many tools

The old ecosystem might look like:

```text
pyenv        → Python versions

venv         → environments

pip          → installation

pip-tools    → dependency compilation

pipx         → CLI tool isolation

poetry       → project/dependency management

build        → building packages
```

Modern uv can cover large portions of those workflows.

For example:

```text
old                         modern uv
────────────────────────────────────────
pyenv                       uv python
venv / virtualenv           uv venv / project .venv
pip                         uv add / uv pip
pip-tools                   uv lock
pipx                        uvx / uv tool
build                       uv build
```

But be careful:

> **"uv replaces these tools" does not mean those tools are deprecated.**

The Python ecosystem still supports them.

It means:

> uv provides a unified alternative that can consolidate many workflows.

For example, uv's `uv pip` interface intentionally provides pip-compatible low-level commands, but uv does **not** invoke pip internally. ([Astral Docs][10])

---

# 27. Why uv is fast

One major reason is architecture.

uv is implemented in Rust and ships as a native executable rather than a Python package requiring a Python environment just to start the package manager.

But speed isn't merely:

```text
Rust = fast
```

There is more involved.

uv also uses aggressive caching.

Its cache avoids repeatedly downloading and rebuilding dependencies that have already been accessed. ([Astral Docs][11])

Conceptually:

```text
First project
     │
     ▼
download package
     │
     ▼
cache

Second project
     │
     ▼
reuse cached artifact
```

That becomes particularly useful when you have many projects.

---

# 28. The global cache

This is one of the architectural ideas that makes uv useful.

Imagine:

```text
Project A
   │
   └── requires pydantic

Project B
   │
   └── requires pydantic

Project C
   │
   └── requires pydantic
```

You don't want to repeatedly download/build the same package artifacts unnecessarily.

uv maintains a cache containing dependency artifacts and other reusable data. ([Astral Docs][11])

This is separate from:

```text
project/.venv
```

Very important:

```text
cache ≠ virtual environment
```

The cache is reusable storage.

The `.venv` is the actual environment your project executes in.

---

# 29. `uvx`

You specifically mentioned:

```text
pipx → uvx
```

This is a useful translation.

`pipx` is traditionally used for installing Python CLI applications into isolated environments.

uv provides:

```bash
uvx
```

which is an alias for:

```bash
uv tool run
```

and runs Python CLI tools in isolated environments. ([Astral Docs][12])

For example, conceptually:

```bash
uvx some-cli
```

means:

```text
download/install tool environment
        ↓
run CLI
        ↓
keep it isolated
```

For repeated use, you can also:

```bash
uv tool install some-cli
```

which keeps the tool environment around. ([Astral Docs][12])

---

# 30. `uv run` vs `uvx`

This distinction is very important later.

### `uv run`

Means:

> Run this command in **my project environment**.

Example:

```bash
uv run pytest
```

or:

```bash
uv run mypy .
```

### `uvx`

Means:

> Run this standalone Python CLI tool in an **isolated tool environment**.

Example:

```bash
uvx ruff
```

You generally don't want your project's pytest to be isolated from your project dependencies.

That's why:

```bash
uv run pytest
```

is the appropriate project workflow.

uv explicitly distinguishes these two use cases in its tool documentation. ([Astral Docs][12])

---

# 31. `py.typed`

This is one of the most commonly misunderstood files.

Your original description:

> "type-information opt-in"

is close but incomplete.

The precise idea comes from PEP 561.

`py.typed` is a marker file that a **Python package distributes** to tell type checkers:

> "This installed package provides type information intended for type checking."

PEP 561 says package maintainers supporting type checking should add a `py.typed` marker to their package. ([Python Enhancement Proposals (PEPs)][13])

---

# 32. Why does `py.typed` exist?

Imagine you're writing:

```python
from some_library import calculate
```

The type checker wants to know:

```text
calculate(
    value: int
) -> str
```

Where does that information come from?

Possible sources include:

```text
1. Inline annotations in .py
2. .pyi stub files
3. Stub distribution such as foo-stubs
4. Package marked with py.typed
5. Typeshed
```

PEP 561 defines the lookup relationship and gives `py.typed` an important role in saying that a third-party package's bundled type information should be used. ([Python Enhancement Proposals (PEPs)][13])

---

# 33. `py.typed` isn't required for your own mypy run

This distinction matters.

Suppose your application contains:

```text
src/
└── myapp/
    ├── __init__.py
    └── service.py
```

and you run:

```bash
mypy src
```

You don't add:

```text
py.typed
```

just to make mypy type-check your own source.

`py.typed` matters primarily when your Python code is being **distributed as an installable package for other projects**.

This is another reason the:

```text
application vs library
```

distinction is so important.

We'll return to this later.

---

# 34. Coverage and `.coverage`

Now let's correct another common misunderstanding.

`.coverage` is **not a configuration file**.

It is generated measurement data produced by Coverage.py.

Coverage.py records execution information in a file typically called:

```text
.coverage
```

and current Coverage.py uses a SQLite-based data file. ([Coverage][14])

Conceptually:

```text
your code
   │
   ▼
pytest
   │
   ▼
coverage measurement
   │
   ▼
.coverage
   │
   ├── statement coverage
   └── branch coverage
```

---

# 35. What does code coverage actually mean?

Suppose your code is:

```python
def divide(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("cannot divide by zero")

    return a / b
```

Your tests only test:

```python
divide(10, 2)
```

Then you executed:

```text
return a / b
```

but did not execute:

```python
raise ValueError(...)
```

Your coverage report may therefore show that the error path isn't covered.

This can expose:

```text
untested branches
untested lines
```

---

# 36. Coverage does NOT prove quality

Very important.

Suppose you have:

```text
100% coverage
```

That does **not** automatically mean:

```text
excellent tests
```

You could execute every line with terrible assertions.

Coverage answers roughly:

> "Which code paths did the tests execute?"

It doesn't answer:

> "Were the tests logically correct?"

That's why:

```text
testing
+
assertions
+
edge cases
+
coverage
```

are separate concepts.

---

# 37. pytest

pytest answers:

> **How do I execute and organize my tests?**

Example:

```python
def add(a: int, b: int) -> int:
    return a + b
```

Test:

```python
def test_add():
    assert add(2, 3) == 5
```

pytest discovers and runs tests.

So:

```text
pytest
   ↓
test execution
```

Coverage is different:

```text
coverage.py
   ↓
measure which code was executed
```

They frequently work together:

```text
pytest
   +
coverage.py
```

---

# 38. pytest configuration in modern projects

There is an important modern update here.

Historically you often saw:

```text
pytest.ini
```

or:

```toml
[tool.pytest.ini_options]
```

In current pytest 9, pytest supports native TOML configuration:

```toml
[tool.pytest]
```

For example:

```toml
[tool.pytest]
minversion = "9.0"
addopts = ["-ra", "-q"]
testpaths = ["tests"]
```

The older:

```toml
[tool.pytest.ini_options]
```

remains supported, but `[tool.pytest]` is the native TOML model. ([pytest][15])

Also, pytest 9 introduced `pytest.toml` / `.pytest.toml` as dedicated configuration files that take precedence over other pytest configuration files. ([pytest][15])

So your mental model should be:

```text
Modern centralized configuration:
    pyproject.toml
        [tool.pytest]

Alternative dedicated modern pytest config:
    pytest.toml
```

---

# 39. mypy and pyright

Now we move to static type checking.

Python is dynamically typed at runtime.

For example:

```python
def greet(name):
    return name.upper()
```

Python itself doesn't require:

```python
name: str
```

But static type checkers can analyze the code before runtime.

---

# 40. Runtime vs static analysis

This distinction is extremely important.

### Python runtime

Actually executes:

```python
greet(123)
```

and you might get an error.

### Type checker

Can potentially tell you **before running the program**:

```text
greet expects str
but int was supplied
```

So:

```text
Python
   ↓
"What actually happens when code runs?"

Type checker
   ↓
"What does the code appear to mean according to its types?"
```

Neither replaces the other.

---

# 41. mypy

mypy is a static type checker for Python.

Example:

```python
def add(a: int, b: int) -> int:
    return a + b
```

Then:

```python
add("hello", 10)
```

can be identified as a type error by mypy.

Modern mypy can be configured from:

```toml
[tool.mypy]
```

inside `pyproject.toml`. ([Mypy][16])

---

# 42. Pyright

Pyright is another static type checker.

Conceptually it solves the same broad problem:

```text
Python source
      │
      ▼
type analysis
      │
      ▼
potential type errors
```

It also has strong editor/LSP integration.

Pyright-family tooling supports configuration in `pyproject.toml`; basedpyright, for example, documents `[tool.basedpyright]` and recommends project-committed configuration so CLI and editor behavior stay consistent. ([BasedPyright][17])

---

# 43. Do you need both mypy and pyright?

Usually, no.

They overlap heavily.

You can absolutely have:

```text
mypy
+
pyright
```

but you now have:

```text
two type systems
two sets of diagnostics
two configurations
two CI checks
potentially different opinions
```

For most projects, choose one primary type checker.

Both are legitimate modern choices.

Your course can teach both so you understand the ecosystem, but later your project should generally establish one authoritative type-checking workflow.

---

# 44. Ruff

Ruff is a particularly interesting modern tool because it combines jobs traditionally handled by several Python tools.

Historically you might have:

```text
flake8
black
isort
pyupgrade
```

Today Ruff can provide:

```text
linting
formatting
import sorting
many rule families
Python modernization checks
```

Ruff itself documents configuration through:

```text
pyproject.toml
ruff.toml
.ruff.toml
```

and can act as both linter and formatter. ([Astral Docs][18])

---

# 45. Linter vs formatter

Do not confuse them.

## Formatter

Changes the appearance of code.

Example:

```python
x={   "name":"Bhargav"   }
```

might become:

```python
x = {"name": "Bhargav"}
```

A formatter answers:

> "How should the code be formatted?"

---

## Linter

Looks for possible problems or undesirable patterns.

For example:

```python
unused_variable = 123
```

might produce a warning.

A linter asks:

> "Does this code have a suspicious or undesirable pattern?"

---

# 46. Ruff vs Black

Black primarily answered:

> How should Python source be formatted?

Ruff includes a formatter designed around Black compatibility. ([Astral Docs][19])

So modern projects can often simplify:

```text
black
flake8
isort
pyupgrade
```

into:

```text
ruff
```

for large portions of those responsibilities.

Again:

> replacement does not mean the older tools are "deprecated by Python."

It means the newer tool consolidates their functionality.

---

# 47. pre-commit

pre-commit solves a different problem.

It isn't:

```text
the formatter
```

or:

```text
the linter
```

or:

```text
the test runner
```

Instead it is an **automation/orchestration layer for Git hooks**.

For example:

```text
git commit
    │
    ▼
pre-commit
    │
    ├── Ruff
    ├── formatting checks
    ├── secret detection
    ├── whitespace checks
    └── other hooks
         │
         ▼
      pass/fail
```

The configuration convention is:

```text
.pre-commit-config.yaml
```

with repositories and hooks specified there. ([pre-commit.com][20])

---

# 48. Why doesn't pre-commit usually go into `pyproject.toml`?

This is another example of why:

> "pyproject.toml = single configuration file for everything"

is slightly too strong.

pre-commit has its own configuration model:

```text
.pre-commit-config.yaml
```

So a realistic repository can have:

```text
pyproject.toml
.pre-commit-config.yaml
.python-version
uv.lock
```

each with a distinct purpose.

---

# 49. What pre-commit actually does

Suppose you try:

```bash
git commit
```

pre-commit can automatically run:

```text
Ruff
type checks
private-key detection
trailing whitespace checks
YAML validation
etc.
```

If something fails:

```text
git commit
     │
     ▼
pre-commit
     │
     └── hook fails
            │
            ▼
       commit rejected
```

That provides a local safety net.

Then CI provides a second safety net.

---

# 50. pre-commit vs CI

These are complementary.

### pre-commit

Runs locally.

```text
developer laptop
     ↓
git commit
     ↓
checks
```

### CI

Runs on the shared server/platform.

```text
push / PR
     ↓
GitHub Actions
     ↓
tests/lint/type/security
```

Why both?

Because developers can bypass local automation.

CI is the authoritative enforcement layer.

---

# 51. The most important distinction: Application vs Library

This is the single most important conceptual distinction in this module.

You specifically called out your AI harness as:

> mostly an application

That changes a huge number of later decisions.

---

# 52. What is a library?

A library is primarily written **for other Python programs to consume**.

Examples:

```python
import requests
import pydantic
import fastapi
```

A library exposes an API.

Conceptually:

```text
library
   │
   ▼
other people's applications
```

You care heavily about:

```text
public API
backward compatibility
versioning
packaging
published artifacts
type information
documentation
compatibility ranges
PyPI
```

---

# 53. What is an application?

An application is primarily written to **perform a job for users or a system**.

For example:

```text
FastAPI backend
        │
        ▼
AI enterprise harness
        │
        ├── authentication
        ├── agents
        ├── RAG
        ├── MCP
        ├── databases
        ├── APIs
        └── integrations
```

The user runs your application.

They typically don't write:

```python
import your_harness
```

as the primary use case.

Instead:

```text
Docker
   ↓
application
   ↓
HTTP API
```

---

# 54. Why this distinction changes dependency strategy

For a **library**, you generally shouldn't lock consumers into your exact dependency versions.

You may say:

```toml
dependencies = [
    "pydantic>=2.10,<3"
]
```

because you are saying:

> "My library works with a compatible range."

For an **application**, you control the entire deployed environment.

You can say:

```text
I want THIS exact resolved dependency graph.
```

Therefore:

```text
application
   ↓
commit lockfile
   ↓
reproducible deployment
```

This is one reason uv's lockfile is especially valuable for applications. uv specifically notes that its lockfile allows the exact dependency set used when deploying an application to be known. ([Astral Docs][8])

---

# 55. Application dependencies vs library dependencies

Think about these differently.

## Application

```text
My application
     │
     ├── FastAPI  → exact resolved version
     ├── Pydantic → exact resolved version
     ├── LangChain → exact resolved version
     ├── LangGraph → exact resolved version
     └── ...
```

Your lockfile controls the deployed environment.

---

## Library

Suppose you create:

```text
vb-ai-client
```

Another developer might install:

```bash
pip install vb-ai-client
```

You shouldn't necessarily force their project to use:

```text
Pydantic exactly version X
```

unless your compatibility requirements genuinely demand it.

Your library communicates a compatibility range.

Their resolver ultimately resolves the complete graph.

---

# 56. This also changes `py.typed`

For your **application**, `py.typed` generally isn't a major deployment concern.

For a **library**, it can be important.

Suppose you publish:

```text
vb-ai-client
```

and have carefully typed APIs:

```python
def create_agent(
    config: AgentConfig,
) -> Agent:
    ...
```

Downstream developers want type checkers to consume those annotations.

That's where PEP 561 and:

```text
py.typed
```

come into play. ([Python Enhancement Proposals (PEPs)][13])

---

# 57. Application vs library: build/distribution difference

Another major distinction.

A library typically needs:

```text
build wheel
build sdist
publish to PyPI/private index
```

An application may instead simply be:

```text
Docker image
     ↓
container registry
     ↓
deployment
```

Your AI harness is very likely to have:

```text
source code
    ↓
uv dependency management
    ↓
Docker
    ↓
GHCR
    ↓
production
```

rather than:

```text
PyPI
    ↓
users pip install your whole application
```

You might still build packages internally, but the deployment artifact is likely a container.

---

# 58. Domain 4 — Build & distribution

Now let's define another major concept.

Source code isn't necessarily the thing you publish.

Python packaging has concepts such as:

```text
source distribution
sdist
wheel
```

The Python Packaging User Guide describes a wheel as a built distribution that can generally be installed without going through the source build step, while an sdist contains source and may require building when installed. ([Python Packaging][21])

---

# 59. Wheel

Typical example:

```text
my_project-1.0.0-py3-none-any.whl
```

A wheel is a built distribution.

For pure Python:

```text
py3-none-any
```

may mean:

```text
Python 3 compatible
not platform-specific
```

Compiled packages can have platform-specific wheels.

---

# 60. Source distribution

Typical:

```text
my_project-1.0.0.tar.gz
```

This contains source.

Installation may need a build step.

---

# 61. What is a build backend?

This is where modern packaging architecture becomes more sophisticated.

The project says:

```toml
[build-system]
requires = [...]
build-backend = "..."
```

This tells the packaging ecosystem:

> "This is the mechanism responsible for building my project."

The PyPA specification says `[build-system]` is the table for build-system requirements and that it should be present in `pyproject.toml`. ([Python Packaging][5])

So:

```text
pyproject.toml
       │
       ▼
[build-system]
       │
       ▼
build backend
       │
       ├── wheel
       └── sdist
```

---

# 62. uv is not the build backend itself in every project

This is another important distinction.

uv provides:

```bash
uv build
```

but the project still has a build backend.

Modern uv projects can use:

```toml
[build-system]
...
```

and uv can build sdist and wheel artifacts. ([Astral Docs][22])

Therefore:

```text
uv
   = project/tooling frontend

build backend
   = mechanism that knows how to build the project
```

This distinction will matter later when we study packaging.

---

# 63. Legacy → Modern translation

Now let's translate your list carefully.

| Old / traditional approach    | Modern approach                            | Important nuance                                      |
| ----------------------------- | ------------------------------------------ | ----------------------------------------------------- |
| `pip`                         | `uv add`, `uv sync`, `uv run`, or `uv pip` | pip is still valid; uv offers a unified alternative   |
| `venv`                        | project-managed `.venv` via uv             | `venv` itself is still valid stdlib                   |
| `requirements.in` + pip-tools | `pyproject.toml` + uv resolver/lock        | PEP 751 `pylock.toml` is now standardized too         |
| `requirements.txt`            | `uv.lock` for uv project workflow          | `requirements.txt` remains widely interoperable       |
| `setup.py` metadata           | `[project]` in `pyproject.toml`            | build backend still matters                           |
| `setup.cfg` metadata          | `[project]` in `pyproject.toml`            | modern standard                                       |
| `pytest.ini`                  | `[tool.pytest]` in `pyproject.toml`        | pytest 9 has native TOML config                       |
| `mypy.ini`                    | `[tool.mypy]`                              | supported modern configuration                        |
| `.coveragerc`                 | `[tool.coverage.*]` in `pyproject.toml`    | Coverage.py supports pyproject config                 |
| Black                         | Ruff formatter                             | Ruff aims for Black-compatible formatting             |
| Flake8                        | Ruff linter/rules                          | Ruff covers many linting rules                        |
| isort                         | Ruff import sorting                        | Ruff includes import sorting                          |
| pyupgrade                     | Ruff modernization rules                   | many pyupgrade-style checks                           |
| pyenv                         | `uv python`                                | pyenv still exists; uv provides integrated management |
| pipx                          | `uvx` / `uv tool`                          | isolated CLI-tool environments                        |
| Poetry                        | uv project workflow                        | not a literal deprecation/replacement                 |
| `setup.cfg`                   | `pyproject.toml`                           | modern centralized metadata/config                    |

The important word in this table is:

> **modern alternative**

not necessarily:

> **deprecated tool**

---

# 64. A particularly important modern update: dependency groups

Your original mental model may be:

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",
]
```

For modern development dependencies, uv now uses the standardized:

```toml
[dependency-groups]
dev = [
    "pytest",
    "ruff",
]
```

uv documents dependency groups as the standardized mechanism for local development dependencies, based on PEP 735. ([Astral Docs][23])

This is important because you may encounter older uv projects containing:

```toml
[tool.uv]
dev-dependencies = [...]
```

That is now considered legacy.

uv's current documentation says the old `tool.uv.dev-dependencies` field is no longer recommended and is expected eventually to be deprecated/removed in favor of `[dependency-groups]`. ([Astral Docs][23])

So for your course:

```text
OLD:
[tool.uv]
dev-dependencies = [...]

CURRENT:
[dependency-groups]
dev = [...]
```

Remember this.

---

# 65. One complete mental model

Here is the architecture I want you to memorize.

```text
                         YOUR PYTHON PROJECT
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
             ▼                    ▼                    ▼
        Python runtime       Project metadata       Dependency
             │                    │                 resolution
             │                    │                    │
             ▼                    ▼                    ▼
       uv python          pyproject.toml           uv.lock
             │                    │                    │
             └──────────────┬─────┴──────────────┬─────┘
                            │                    │
                            ▼                    ▼
                         .venv                dependency
                        environment             graph
                            │
                            ▼
                         uv run
                            │
              ┌─────────────┼──────────────┐
              │             │              │
              ▼             ▼              ▼
            pytest         Ruff       mypy/pyright
              │             │              │
              ▼             ▼              ▼
         tests execute   lint/format    type analysis
              │
              ▼
         coverage.py
              │
              ▼
          .coverage

And around all of this:

        .pre-commit-config.yaml
                    │
                    ▼
             Git hook automation
```

---

# 66. The complete lifecycle of a modern application

Let's walk through what happens from empty directory to running application.

---

## Step 1 — Select Python

```text
.python-version
```

says:

```text
3.x
```

uv finds or installs an appropriate interpreter.

```text
uv python
     ↓
Python interpreter
```

---

## Step 2 — Define project

You create:

```text
pyproject.toml
```

containing:

```toml
[project]
name = "my-app"
requires-python = ">=3.13"
```

and dependencies.

---

## Step 3 — Create project environment

uv creates:

```text
.venv/
```

for the project.

---

## Step 4 — Resolve dependencies

You have:

```text
FastAPI
Pydantic
httpx
...
```

uv builds the dependency graph.

---

## Step 5 — Lock

```bash
uv lock
```

produces:

```text
uv.lock
```

containing the resolved dependency state. ([Astral Docs][3])

---

## Step 6 — Sync

```bash
uv sync
```

makes `.venv` match the project lock state.

uv's project synchronization is exact by default, including removing extraneous packages that aren't part of the locked environment. ([Astral Docs][7])

---

## Step 7 — Run

Instead of:

```bash
source .venv/bin/activate
python ...
```

you can simply do:

```bash
uv run python ...
```

uv handles the project environment.

---

## Step 8 — Test

```bash
uv run pytest
```

---

## Step 9 — Type-check

```bash
uv run mypy .
```

or:

```bash
uv run pyright
```

---

## Step 10 — Lint/format

```bash
uv run ruff check .
```

and:

```bash
uv run ruff format .
```

---

## Step 11 — Coverage

Conceptually:

```bash
uv run coverage run -m pytest
uv run coverage report
```

or use the pytest coverage integration once configured.

The resulting `.coverage` file is measurement data. ([Coverage][14])

---

## Step 12 — Git commit

```bash
git commit
```

triggers:

```text
pre-commit
    │
    ├── formatting
    ├── linting
    ├── security hooks
    └── other checks
```

---

# 67. What each major file means

This is worth memorizing.

| File                      | Think of it as                                                   |
| ------------------------- | ---------------------------------------------------------------- |
| `pyproject.toml`          | Project definition + dependency declaration + tool configuration |
| `uv.lock`                 | Resolved dependency graph                                        |
| `.python-version`         | Default/project Python version request                           |
| `.venv/`                  | Actual isolated local environment                                |
| `py.typed`                | Package marker saying distributed type information is available  |
| `.coverage`               | Coverage measurement database                                    |
| `.pre-commit-config.yaml` | Git hook automation configuration                                |
| `pytest.toml`             | Dedicated pytest configuration                                   |
| `Dockerfile`              | Container build instructions                                     |
| `compose.yaml`            | Container orchestration configuration                            |
| `.github/workflows/*.yml` | CI/CD automation                                                 |

---

# 68. The most important "don't confuse these" table

| Concept           | What it answers                                                                   |
| ----------------- | --------------------------------------------------------------------------------- |
| Python            | How is Python code executed?                                                      |
| `.python-version` | Which Python should this project default to?                                      |
| `requires-python` | Which Python versions does this project support?                                  |
| `.venv`           | Where are this project's isolated runtime/dependencies?                           |
| `pyproject.toml`  | What is this project and what does it require?                                    |
| `uv.lock`         | What exact dependency resolution should be used?                                  |
| `uv`              | How do I manage these workflows?                                                  |
| `pytest`          | Did my tests pass?                                                                |
| Coverage.py       | Which code did my tests execute?                                                  |
| `.coverage`       | Where is coverage measurement data stored?                                        |
| mypy / Pyright    | Are the types statically consistent?                                              |
| Ruff              | Are the code style/lint rules satisfied?                                          |
| pre-commit        | Did configured checks pass before commit?                                         |
| `py.typed`        | Should downstream type checkers consume this package's supplied type information? |

---

# 69. Your preferred modern stack

For the kind of **application** you're building, a very sensible modern baseline is:

```text
Python
    │
    ├── uv
    │    ├── Python management
    │    ├── environments
    │    ├── dependencies
    │    ├── locking
    │    ├── running
    │    └── building
    │
    ├── pyproject.toml
    │
    ├── uv.lock
    │
    ├── .python-version
    │
    ├── pytest
    │
    ├── coverage.py
    │
    ├── Ruff
    │
    ├── mypy OR Pyright
    │
    └── pre-commit
```

This minimizes the amount of separate infrastructure you have to understand and maintain while remaining aligned with current Python packaging and tooling conventions.

---

# 70. What I would *not* call "deprecated"

This is important because tutorials often exaggerate modernization.

### `pip`

Not deprecated.

It remains an important Python package installer and compatibility interface.

uv provides an alternative and also provides its own pip-compatible interface. ([Astral Docs][10])

### `venv`

Not deprecated.

It is part of the Python standard library. ([Python documentation][2])

### `pytest.ini`

Not globally deprecated.

pytest supports it.

But modern pytest also supports native TOML configuration, and for a centralized project configuration strategy, `pyproject.toml` is attractive. ([pytest][15])

### `requirements.txt`

Not deprecated.

It remains one of the most interoperable formats in Python.

uv still supports importing/exporting it, and current uv documentation describes it as the most widely supported dependency-file format. ([Astral Docs][24])

### Poetry

Not deprecated.

It remains a legitimate Python project manager.

uv is an alternative.

---

# 71. What actually *is* legacy in the things you listed?

There are some cases where modern tooling has a clear preferred successor.

For example:

```text
setup.py
```

as the primary place for project metadata/configuration is legacy compared with standardized:

```toml
[project]
```

Similarly, old uv projects using:

```toml
[tool.uv]
dev-dependencies = [...]
```

should migrate toward:

```toml
[dependency-groups]
dev = [...]
```

because dependency groups are now standardized and uv no longer recommends the old field. ([Astral Docs][23])

---

# 72. Why the application/library distinction will matter throughout your course

This will affect later modules involving:

```text
dependency version constraints
lockfiles
build systems
publishing
semantic versioning
API compatibility
py.typed
optional dependencies
extras
dependency groups
Docker
CI
security
```

For your **application**, the mindset is:

```text
I control the deployment environment.

Therefore:
    lock aggressively
    reproduce exactly
    keep the deployment graph known
    optimize operational reliability
```

For a **library**:

```text
Other people control the deployment environment.

Therefore:
    define compatibility carefully
    avoid unnecessarily tight dependency requirements
    maintain public APIs
    package type information
    think about backward compatibility
```

That difference will repeatedly come back throughout this course.

---

# 73. One subtle but very important point about uv

You will often hear:

> "uv replaces six tools."

Treat that as a shorthand, not a strict technical statement.

A more accurate description is:

```text
uv consolidates many historically separate Python-development
workflows into one tool.
```

It can manage:

```text
Python
virtual environments
project dependencies
dependency resolution
lockfiles
CLI tools
running commands
builds
publishing
pip-compatible workflows
```

The current uv CLI exposes these responsibilities directly. ([Astral Docs][3])

That consolidation is the real reason the ecosystem feels simpler.

---

# 74. A modern application repository

For the kind of project you're building, you may eventually arrive at something conceptually like:

```text
ai-harness/
│
├── src/
│   └── ai_harness/
│       ├── __init__.py
│       ├── main.py
│       ├── domains/
│       ├── infrastructure/
│       └── ...
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── ...
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── .pre-commit-config.yaml
├── .gitignore
├── README.md
├── LICENSE
├── Dockerfile
├── compose.yaml
│
└── .github/
    └── workflows/
```

You normally **do not commit**:

```text
.venv/
.coverage
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

because these are generated/local artifacts.

---

# 75. A conceptual `pyproject.toml`

Don't memorize this yet. Just understand the architecture.

```toml
[build-system]
# How this project is built

[project]
# Standard project metadata
name = "ai-harness"
version = "0.1.0"
requires-python = ">=3.13"

dependencies = [
    "fastapi",
    "pydantic",
]

[dependency-groups]
dev = [
    "pytest",
    "ruff",
    "mypy",
]

[tool.uv]
# uv-specific settings

[tool.ruff]
# Ruff configuration

[tool.ruff.lint]
# Ruff lint rules

[tool.mypy]
# mypy configuration

[tool.pytest]
# pytest configuration

[tool.coverage.run]
# coverage measurement configuration
```

The exact configuration will be taught later. The important thing right now is understanding **who owns each section**.

---

# 76. The entire ecosystem in one picture

This is probably the most useful diagram in the whole module:

```text
                              GIT REPOSITORY
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
          .python-version      pyproject.toml          uv.lock
                 │                    │                    │
                 ▼                    │                    ▼
          Python version              │              exact dependency
                                      │                  graph
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
             [project]       [dependency-groups]      [tool.*]
                    │                 │                 │
                    │                 │          ┌──────┼─────────┐
                    │                 │          │      │         │
                    │                 │          ▼      ▼         ▼
                    │                 │        Ruff   mypy      pytest
                    │                 │
                    └─────────────────┼──────────────────────────┐
                                      │                          │
                                      ▼                          ▼
                                   uv sync                    uv run
                                      │                          │
                                      ▼                          ▼
                                   .venv                     commands
                                                                 │
                                           ┌─────────────────────┼───────────────┐
                                           │                     │               │
                                           ▼                     ▼               ▼
                                        pytest                Ruff          type checker
                                           │
                                           ▼
                                      coverage.py
                                           │
                                           ▼
                                      .coverage

                           Git commit
                                │
                                ▼
                        .pre-commit-config.yaml
                                │
                                ▼
                             hooks
```

---

# 77. The mental model I want you to memorize

Don't memorize commands yet.

Memorize this:

```text
Python
    = executes Python

.python-version
    = selects/defaults the Python version

.venv
    = isolated environment

pyproject.toml
    = project definition + dependency declarations +
      standardized metadata + tool configuration

uv.lock
    = resolved dependency graph

uv
    = manages/orchestrates the workflow

pytest
    = runs tests

coverage.py
    = measures executed code

.coverage
    = coverage data

mypy / Pyright
    = static type analysis

Ruff
    = linting + formatting + many code-quality checks

pre-commit
    = automatically runs selected checks around Git commits

py.typed
    = package-level marker for distributing usable type information
```

And the most important architectural distinction:

```text
                    Python ecosystem
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
        APPLICATION                 LIBRARY
             │                         │
       controls its               consumed by
       own environment             other projects
             │                         │
       uv.lock very useful        compatibility important
             │                         │
       deployment focus           packaging/API focus
             │                         │
       Docker often key           wheel/sdist/PyPI important
```

---

# 78. Current vs legacy: the version I want you to carry forward

For **your application-oriented course**, use this mental mapping:

```text
                  MODERN DEFAULT MENTAL MODEL

Python
  +
uv
  +
pyproject.toml
  +
uv.lock
  +
.python-version
  +
project .venv
  +
pytest
  +
coverage.py
  +
Ruff
  +
one primary type checker
  +
pre-commit
```

With these caveats:

```text
pip
    still valid

venv
    still valid

requirements.txt
    still valid/interoperable

pytest.ini
    still valid

Poetry
    still valid

setup.py
    legacy approach for project metadata,
    not the modern default

tool.uv.dev-dependencies
    legacy uv development-dependency mechanism

pylock.toml
    newly standardized interoperability lockfile format,
    while uv projects still use uv.lock
```

The modern Python ecosystem is therefore **not**:

> "Everything old is dead."

It is much more accurately:

> **"Python has standardized around `pyproject.toml`, and tools such as uv and Ruff have consolidated workflows that previously required several separate tools."**

The current PyPA and uv documentation supports that overall architecture. ([Python Packaging][5])

---

## Final takeaway

Before touching any command, ask:

> **Which problem is this command solving?**

For example:

```text
uv python install
    → interpreter management

uv venv / uv sync
    → environment management

uv add
    → dependency declaration

uv lock
    → dependency resolution/locking

uv run
    → execution inside the managed environment

uv build
    → build/distribution

pytest
    → testing

coverage
    → coverage measurement

mypy / pyright
    → static type checking

ruff
    → linting/formatting

pre-commit
    → Git-hook automation
```

Once you understand that map, the later modules stop feeling like a collection of commands and start looking like **one coherent engineering system**.

For your AI enterprise harness, the most important architectural principle to carry into the next modules is:

```text
              APPLICATION
                  │
       ┌──────────┴──────────┐
       │                     │
   pyproject.toml          uv.lock
       │                     │
 "what we require"       "what we resolved"
       │                     │
       └──────────┬──────────┘
                  ▼
                .venv
                  │
                  ▼
                uv
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
    pytest       Ruff    type checker
```

That is the foundation on which the rest of this course should be built.

[1]: https://docs.astral.sh/uv/concepts/python-versions/?utm_source=chatgpt.com "Python versions | uv"
[2]: https://docs.python.org/3.12/library/venv.html?utm_source=chatgpt.com "venv — Creation of virtual environments — Python 3.12.14 documentation"
[3]: https://docs.astral.sh/uv/reference/cli/?utm_source=chatgpt.com "Commands | uv"
[4]: https://docs.astral.sh/uv/guides/projects/?utm_source=chatgpt.com "Working on projects | uv"
[5]: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/?highlight=2023&utm_source=chatgpt.com "Writing your pyproject.toml - Python Packaging User Guide"
[6]: https://packaging.python.org/en/latest/specifications/pyproject-toml/?utm_source=chatgpt.com "pyproject.toml specification - Python Packaging User Guide"
[7]: https://docs.astral.sh/uv/concepts/projects/sync/?utm_source=chatgpt.com "Locking and syncing | uv"
[8]: https://docs.astral.sh/uv/concepts/projects/layout/?trk=article-ssr-frontend-pulse_little-text-block&utm_source=chatgpt.com "Structure and files | uv"
[9]: https://peps.python.org/pep-0751/?utm_source=chatgpt.com "PEP 751 – A file format to record Python dependencies for installation reproducibility | peps.python.org"
[10]: https://docs.astral.sh/uv/pip/?utm_source=chatgpt.com "The pip interface | uv"
[11]: https://docs.astral.sh/uv/concepts/cache/?utm_source=chatgpt.com "Caching | uv"
[12]: https://docs.astral.sh/uv/concepts/tools/?utm_source=chatgpt.com "Tools | uv"
[13]: https://peps.python.org/pep-0561/?utm_source=chatgpt.com "PEP 561 – Distributing and Packaging Type Information | peps.python.org"
[14]: https://coverage.readthedocs.io/en/latest/commands/cmd_run.html?utm_source=chatgpt.com "Execution: coverage run — Coverage.py 7.16.2 documentation"
[15]: https://docs.pytest.org/en/stable/reference/customize.html?utm_source=chatgpt.com "Configuration - pytest documentation"
[16]: https://mypy.readthedocs.io/en/latest/config_file.html?highlight=allow_redefinition&utm_source=chatgpt.com "The mypy configuration file - mypy 2.5.0+dev.b5b279fe60739f2b98ba86ef29d709ae1dd1cfff documentation"
[17]: https://docs.basedpyright.com/latest/configuration/language-server-settings/?utm_source=chatgpt.com "Language Server Settings - basedpyright"
[18]: https://docs.astral.sh/ruff/configuration/?utm_source=chatgpt.com "Configuring Ruff | Ruff"
[19]: https://docs.astral.sh/ruff/formatter/?utm_source=chatgpt.com "The Ruff Formatter | Ruff"
[20]: https://pre-commit.com/?trk=public_post_share-update_update-text&utm_source=chatgpt.com "pre-commit"
[21]: https://packaging.python.org/en/latest/guides/distributing-packages-using-setuptools/?highlight=versioning&utm_source=chatgpt.com "Packaging and distributing projects - Python Packaging User Guide"
[22]: https://docs.astral.sh/uv/concepts/projects/build/?utm_source=chatgpt.com "Building distributions | uv"
[23]: https://docs.astral.sh/uv//concepts/projects/dependencies/?utm_source=chatgpt.com "Managing dependencies | uv"
[24]: https://docs.astral.sh/uv/concepts/projects/export/?utm_source=chatgpt.com "Exporting a lockfile | uv"

