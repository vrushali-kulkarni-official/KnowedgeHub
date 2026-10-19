`uv` does not currently provide a native single command (like `uv upgrade` or an equivalent to `npm-check-updates`) to bump constraint bounds in `pyproject.toml`. Native `uv` by design separates project requirements (`pyproject.toml`) from locked versions (`uv.lock`).

To bump the versions declared inside `pyproject.toml`, use one of the following approaches:

---

### Option 1: Use `uv-bump` (Recommended)

`uv-bump` syncs your lockfile and automatically bumps the lower bounds in your `pyproject.toml` to match. You don't need to install anything permanently—run it with `uvx`:

```bash
uvx uv-bump

```

* It inspects your project, resolves to the latest feasible versions via `uv`, and updates specifications (like changing `foo>=1.0.0` to `foo>=2.1.0`) while preserving comments and TOML formatting.
* Respects pinned versions (e.g., `==` or strict ranges like `<6.0`) unless you loosen them.

---

### Option 2: Use `uv-upx` / `uv-upgrade`

Another dedicated CLI tool tailored for `uv` projects is `uv-upx`:

```bash
# Run non-interactively
uvx uv-upx

# Or run interactively to approve each version bump individually
uvx uv-upx --interactive

```

To also bump strictly pinned dependencies (`==`):

```bash
uvx uv-upx --profile with_pinned

```

---

### Option 3: Built-in `uv add` (Per-package or scripted)

Re-running `uv add <package>` queries PyPI and overwrites the entry in `pyproject.toml` with the latest version constraint:

```bash
# Updates httpx to the latest compatible lower-bound (e.g., >=0.28.1)
uv add httpx

```

To update all root dependencies in one command without external tools, pipe your current dependencies back into `uv add`:

```bash
# Extract package names from project dependencies and re-add them
python -c "import tomllib, subprocess; f = tomllib.load(open('pyproject.toml', 'rb')); pkgs = [d.split('>=')[0].split('==')[0].split('<')[0].strip() for d in f.get('project', {}).get('dependencies', [])]; subprocess.run(['uv', 'add'] + pkgs)"

```
