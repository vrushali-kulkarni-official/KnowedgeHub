"""Validate the built course: HTML tags, local links, inline JS syntax, lab wiring."""

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

problems = []
checked = {"files": 0, "links": 0, "scripts": 0, "labs": 0}

html_files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    if "/tools" in dirpath or dirpath.endswith("/tools"):
        continue
    for fn in filenames:
        if fn.endswith(".html"):
            html_files.append(os.path.join(dirpath, fn))


def tag_balance(path, text):
    """Walk tags, ignoring script/style content."""
    text = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", text, flags=re.S | re.I)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", text, flags=re.S | re.I)
    stack = []
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(/?)>", text):
        closing, name, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name in VOID or selfclose:
            continue
        if closing:
            if not stack:
                problems.append("%s: stray </%s>" % (rel(path), name))
                return
            top = stack.pop()
            if top != name:
                problems.append("%s: </%s> closes <%s>" % (rel(path), name, top))
                return
        else:
            stack.append(name)
    if stack:
        problems.append("%s: unclosed tags %s" % (rel(path), stack))


def rel(p):
    return os.path.relpath(p, ROOT)


def check_links(path, text):
    for m in re.finditer(r'(?:href|src)="([^"]+)"', text):
        url = m.group(1)
        if url.startswith(("http://", "https://", "#", "mailto:", "data:")):
            continue
        target = url.split("#")[0]
        if not target:
            continue
        checked["links"] += 1
        full = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if not os.path.exists(full):
            problems.append("%s: broken link -> %s" % (rel(path), url))


def check_scripts(path, text):
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", text, flags=re.S | re.I)
    for i, code in enumerate(blocks):
        if not code.strip():
            continue
        checked["scripts"] += 1
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(code)
            tmp = f.name
        res = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        if res.returncode != 0:
            problems.append("%s: script #%d syntax error:\n%s"
                            % (rel(path), i + 1, res.stderr.strip()[:600]))


def check_labs(path, text):
    """Every lab textarea must have a matching output pre and a script that wires it."""
    for m in re.finditer(r'<textarea id="([^"]+)-code"', text):
        sid = m.group(1)
        checked["labs"] += 1
        if 'id="%s-out"' % sid not in text:
            problems.append("%s: lab %s has no output element" % (rel(path), sid))
        if 'data-run="%s"' % sid not in text:
            problems.append("%s: lab %s has no Run button" % (rel(path), sid))
        if not re.search(r"getElementById\(['\"]%s-out['\"]\)" % re.escape(sid), text):
            problems.append("%s: lab %s output is never wired up" % (rel(path), sid))
    for m in re.finditer(r'<textarea id="([^"]+)-code"', text):
        sid = m.group(1)
        if not re.search(r"getElementById\(['\"]%s-code['\"]\)" % re.escape(sid), text):
            problems.append("%s: lab %s textarea is never found by the script" % (rel(path), sid))


for path in sorted(html_files):
    checked["files"] += 1
    text = open(path, encoding="utf-8").read()
    tag_balance(path, text)
    check_links(path, text)
    check_scripts(path, text)
    check_labs(path, text)

print("checked %d html files, %d links, %d inline scripts, %d labs"
      % (checked["files"], checked["links"], checked["scripts"], checked["labs"]))

if problems:
    print("\n%d PROBLEM(S):\n" % len(problems))
    for p in problems:
        print(" - " + p)
    sys.exit(1)
print("all good ✓")
