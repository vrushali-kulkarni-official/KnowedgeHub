"""
L13 - langgraph dev & LangSmith Studio.

This one is mostly about SETUP, because the tooling is a local server plus a
hosted UI. What we can verify here:
  1. The langgraph.json config is valid and points at a real graph.
  2. The graph the config points at imports cleanly and compiles.
  3. The CLI is installed and its flags are what the lesson claims.
  4. The Agent Server can be started (we start it, hit /ok, and stop it).

To actually SEE the Studio UI you need a free LangSmith account:
  https://smith.langchain.com  ->  then `langgraph dev` prints a Studio URL.

Run:  uv run python examples/L13_dev_and_studio.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
ROOT = Path(__file__).resolve().parents[1]

from lgc.printing import section


def cli_path() -> list[str]:
    """Find the langgraph CLI next to the running interpreter first."""
    cand = Path(sys.executable).parent / "langgraph"
    if cand.exists():
        return [str(cand)]
    return ["langgraph"]


def main() -> None:
    section("1. THE CONFIG FILE")
    cfg_path = ROOT / "langgraph.json"
    cfg = json.loads(cfg_path.read_text())
    print(json.dumps(cfg, indent=2))
    print("\n  every key, and what it means:")
    print("    python_version : the Python version for the runtime")
    print("    dependencies   : local paths to install ('.' = this project)")
    print("    graphs         : graph id -> 'path/to/file.py:variable'")
    print("    env            : a .env file path (or an inline dict)")

    section("2. THE GRAPH THE CONFIG POINTS AT")
    for graph_id, target in cfg["graphs"].items():
        path, var = target.split(":")
        print(f"  graph id : {graph_id}")
        print(f"  target   : {path} -> {var}")
        mod_path = ROOT / path
        print(f"  file exists: {mod_path.exists()}")
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"cfg_{graph_id}", mod_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        graph = getattr(mod, var)
        print(f"  imported : {type(graph).__name__}")
        print(f"  nodes    : {list(graph.get_graph().nodes.keys())}")

    section("3. THE CLI")
    try:
        out = subprocess.run(
            cli_path() + ["--version"], capture_output=True, text=True, timeout=60
        )
        print("  ", (out.stdout or out.stderr).strip())
    except FileNotFoundError:
        print("   langgraph CLI not installed.")
        print("   Install it with:  pip install -U 'langgraph-cli[inmem]'")

    section("4. STARTING THE AGENT SERVER (dev mode)")
    print("  Starting `langgraph dev --no-browser --port 2024` ...")
    print("  (this needs the project installed; skipping if it is not)")
    proc = None
    try:
        proc = subprocess.Popen(
            cli_path() + ["dev", "--no-browser", "--port", "2024"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                import urllib.request

                with urllib.request.urlopen("http://127.0.0.1:2024/ok", timeout=2) as r:
                    body = r.read().decode()
                    print(f"  GET /ok -> {r.status} {body}")
                    ok = True
                    break
            except Exception:
                if proc.poll() is not None:
                    break
        if not ok:
            print("  (server did not become ready in time - check the output above)")
    except FileNotFoundError:
        print("   langgraph CLI not installed; skipping the live server check.")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                out, _ = proc.communicate(timeout=10)
                print("\n  --- server output (first 30 lines) ---")
                for line in (out or "").splitlines()[:30]:
                    print("   ", line)
            except Exception:
                proc.kill()

    section("5. THE STUDIO URL")
    print("  langgraph dev prints:")
    print("    API:       http://127.0.0.1:2024")
    print("    Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024")
    print("    API docs:  http://127.0.0.1:2024/docs")
    print("\n  NOTE the current product names:")
    print("    LangGraph Studio   -> LangSmith Studio   (renamed late 2025)")
    print("    LangGraph Platform -> LangSmith Deployment")
    print("    the API server     -> Agent Server")
    print("  The CLI is still `langgraph`.")


if __name__ == "__main__":
    main()
