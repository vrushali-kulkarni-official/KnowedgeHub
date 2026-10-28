"""Rendering engine for the Frontend Journey course.

Course content lives in Python data structures (content_*.py) and is rendered
to static HTML pages.  Every page gets:
  - the shared shell (CSS, top bar, nav)
  - code blocks with lightweight syntax highlighting
  - a live "lab" block (textarea + Run + output) that behaves like a REPL
  - localStorage progress tracking
"""

import html
import re

# ---------------------------------------------------------------- highlighting

JS_KW = {
    "const", "let", "var", "function", "return", "if", "else", "for", "while",
    "new", "class", "this", "null", "undefined", "true", "false", "typeof",
    "async", "await", "of", "in", "do", "switch", "case", "break", "continue",
    "try", "catch", "throw", "delete", "instanceof",
}

PY_KW = {
    "def", "return", "if", "elif", "else", "for", "while", "import", "from",
    "as", "class", "try", "except", "finally", "raise", "with", "None", "True",
    "False", "and", "or", "not", "in", "is", "pass", "lambda", "global",
    "nonlocal", "yield", "assert", "del", "break", "continue", "print",
}

def _token_re(lang):
    js_comment = r"//[^\n]*|/\*[\s\S]*?\*/"
    py_comment = r"[#][^\n]*"   # '#' must be escaped in a VERBOSE regex
    comment = js_comment if lang == "js" else py_comment
    return re.compile(
        r"(?P<comment>" + comment + r")"
        r"|(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)"
        r"|(?P<number>\b\d+(?:\.\d+)?\b)"
        r"|(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)"
        r"|(?P<other>.)",
        re.VERBOSE | re.DOTALL,
    )

def hl(code, lang="js"):
    """Tiny syntax highlighter -> safe HTML."""
    kw = JS_KW if lang == "js" else PY_KW
    rx = _token_re(lang)
    out = []
    for m in rx.finditer(code):
        kind = m.lastgroup
        text = m.group(0)
        if kind == "comment":
            out.append('<span class="tok-com">' + html.escape(text) + "</span>")
        elif kind == "string":
            out.append('<span class="tok-str">' + html.escape(text) + "</span>")
        elif kind == "number":
            out.append('<span class="tok-num">' + html.escape(text) + "</span>")
        elif kind == "word":
            if text in kw:
                out.append('<span class="tok-kw">' + html.escape(text) + "</span>")
            else:
                # function call?  look ahead for '('
                nxt = code[m.end():m.end() + 40].lstrip()
                if nxt.startswith("("):
                    out.append('<span class="tok-fn">' + html.escape(text) + "</span>")
                elif text[:1].isupper() and lang == "js":
                    out.append('<span class="tok-cls">' + html.escape(text) + "</span>")
                else:
                    out.append(html.escape(text))
        else:
            out.append(html.escape(text))
    return "".join(out)

# ---------------------------------------------------------------- block types

def render_block(b, step):
    t = b.get("type")
    if t == "raw":
        return '<section class="card">' + b["html"] + "</section>"
    if t == "idea":
        return (
            '<section class="card idea">'
            '<h3>' + html.escape(b.get("title", "The idea")) + "</h3>"
            + b["html"]
            + "</section>"
        )
    if t == "note":
        return (
            '<section class="card note">'
            '<h3>' + html.escape(b.get("title", "Note")) + "</h3>"
            + b["html"]
            + "</section>"
        )
    if t == "bridge":
        rows = ""
        for pair in b["pairs"]:
            rows += (
                '<div class="bridge-row">'
                '<div class="bridge-col">'
                '<div class="bridge-head py">' + html.escape(pair["py_label"]) + "</div>"
                '<pre class="code"><code>' + hl(pair["py"], "py") + "</code></pre>"
                "</div>"
                '<div class="bridge-arrow">&#8594;</div>'
                '<div class="bridge-col">'
                '<div class="bridge-head js">' + html.escape(pair["js_label"]) + "</div>"
                '<pre class="code"><code>' + hl(pair["js"], "js") + "</code></pre>"
                "</div>"
                "</div>"
            )
        return (
            '<section class="card bridge">'
            '<h3>' + html.escape(b.get("title", "Python &#8594; JavaScript")) + "</h3>"
            + (b["html"] if b.get("html") else "")
            + rows
            + "</section>"
        )
    if t == "code":
        return (
            '<section class="card">'
            '<h3>' + html.escape(b.get("title", "Example")) + "</h3>"
            + (b["html"] if b.get("html") else "")
            + '<pre class="code"><code>' + hl(b["code"], b.get("lang", "js")) + "</code></pre>"
            + "</section>"
        )
    if t == "demo":
        return (
            '<section class="card demo">'
            '<h3>&#9654; Live demo: ' + html.escape(b.get("title", "")) + "</h3>"
            + (b["html"] if b.get("html") else "")
            + '<div class="demo-stage">' + b["html_demo"] + "</div>"
            + "</section>"
        )
    if t == "lab":
        sid = b.get("id", step["id"] + "-lab")
        hints = ""
        for i, h in enumerate(b.get("hints", []), 1):
            hints += (
                '<details class="hint"><summary>Hint ' + str(i) + "</summary><p>"
                + h + "</p></details>"
            )
        return (
            '<section class="card lab">'
            '<h3>&#9998; Your turn: ' + html.escape(b.get("title", "Try it")) + "</h3>"
            + (b["html"] if b.get("html") else "")
            + '<div class="lab-grid">'
            + '<textarea id="' + sid + '-code" spellcheck="false" aria-label="Your code"></textarea>'
            + '<div class="lab-side">'
            + '<div class="lab-buttons">'
            + '<button class="btn" data-run="' + sid + '">Run &#9654;</button>'
            + '<button class="btn ghost" data-clear="' + sid + '">Clear output</button>'
            + "</div>"
            + '<pre class="out" id="' + sid + '-out" aria-live="polite"></pre>'
            + "</div>"
            + "</div>"
            + '<div class="hints">' + hints + "</div>"
            + "</section>"
        )
    if t == "try":
        checks = ""
        for c in b.get("checks", []):
            checks += "<li>" + c + "</li>"
        return (
            '<section class="card try">'
            '<h3>&#127919; Tiny challenge</h3>'
            + (b["html"] if b.get("html") else "")
            + "<ul class=\"checks\">" + checks + "</ul>"
            + (('<p class="muted">' + b["html2"] + "</p>") if b.get("html2") else "")
            + "</section>"
        )
    if t == "checkpoint":
        items = "".join("<li>" + i + "</li>" for i in b["items"])
        return (
            '<section class="card checkpoint">'
            "<h3>&#9989; Checkpoint &mdash; you now know</h3>"
            "<ul>" + items + "</ul>"
            "</section>"
        )
    return ""

# ---------------------------------------------------------------- page shell

CSS = """
:root{
  --bg:#0f1115; --panel:#171a21; --panel2:#1d212a; --line:#2a2f3a;
  --text:#e7e9ee; --muted:#9aa3b2; --accent:#7dd3fc; --accent2:#a78bfa;
  --green:#4ade80; --amber:#fbbf24; --red:#fb7185; --pink:#f472b6;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
  font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code,pre,textarea{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* top bar */
.topbar{position:sticky;top:0;z-index:50;background:rgba(15,17,21,.92);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:980px;margin:0 auto;padding:10px 18px;display:flex;
  align-items:center;gap:14px;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.2px}
.brand span{color:var(--accent)}
.crumb{color:var(--muted);font-size:14px}
.spacer{flex:1}
.pill{font-size:12px;color:var(--muted);border:1px solid var(--line);
  border-radius:999px;padding:3px 10px}

/* layout */
.wrap{max-width:980px;margin:0 auto;padding:26px 18px 90px}
h1{font-size:clamp(28px,4vw,40px);line-height:1.15;margin:.2em 0 .35em}
h2{font-size:22px;margin:0 0 .6em}
h3{font-size:17px;margin:0 0 .7em;color:var(--accent2);
  letter-spacing:.2px;text-transform:none}
p{margin:.6em 0}
.lede{font-size:18px;color:var(--muted);margin:0 0 1.4em}
.muted{color:var(--muted)}
.eyebrow{color:var(--accent);font-size:13px;letter-spacing:.12em;
  text-transform:uppercase;margin:0}

/* cards */
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px;margin:16px 0}
.card.idea{border-left:4px solid var(--accent)}
.card.note{border-left:4px solid var(--amber)}
.card.bridge{border-left:4px solid var(--green)}
.card.demo{border-left:4px solid var(--pink)}
.card.lab{border-left:4px solid var(--accent2)}
.card.try{border-left:4px solid var(--amber);background:#1a1a16}
.card.checkpoint{border-left:4px solid var(--green);background:#151d18}
.card ul,.card ol{padding-left:1.2em}
.card li{margin:.3em 0}

/* code */
pre.code{background:#0b0d11;border:1px solid var(--line);border-radius:10px;
  padding:13px 15px;overflow:auto;font-size:13.5px;line-height:1.6;margin:.6em 0}
pre.code code{white-space:pre}
.tok-kw{color:#c792ea}
.tok-str{color:#c3e88d}
.tok-num{color:#f78c6c}
.tok-com{color:#5f6b7a;font-style:italic}
.tok-fn{color:#82aaff}
.tok-cls{color:#ffcb6b}

/* bridge */
.bridge-row{display:grid;grid-template-columns:1fr 34px 1fr;gap:8px;
  align-items:center;margin:.8em 0}
.bridge-col{min-width:0}
.bridge-head{font-size:12px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--muted);margin-bottom:4px}
.bridge-head.py{color:var(--green)}
.bridge-head.js{color:var(--amber)}
.bridge-arrow{text-align:center;color:var(--muted)}
@media(max-width:640px){
  .bridge-row{grid-template-columns:1fr}
  .bridge-arrow{transform:rotate(90deg)}
}

/* demo stage */
.demo-stage{background:#0b0d11;border:1px dashed var(--line);border-radius:10px;
  padding:14px;margin-top:.6em}
.demo-stage button{font:inherit;background:var(--panel2);color:var(--text);
  border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}
.demo-stage button:hover{border-color:var(--accent)}
.demo-stage input{font:inherit;background:#0f1115;color:var(--text);
  border:1px solid var(--line);border-radius:8px;padding:7px 10px}
.demo-stage ul{margin:.4em 0;padding-left:1.2em}
.demo-stage li.done{text-decoration:line-through;opacity:.55}
.demo-stage .del{margin-left:.5em;padding:1px 7px;line-height:1.2}
.demo-stage .todo-foot{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  margin-top:10px}
.demo-stage .ghostbtn{background:transparent}
.demo-stage .label{cursor:pointer}

/* lab */
.lab-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:12px;margin-top:.6em}
@media(max-width:760px){.lab-grid{grid-template-columns:1fr}}
textarea#lab, .lab-grid textarea{width:100%;min-height:210px;background:#0b0d11;
  color:var(--text);border:1px solid var(--line);border-radius:10px;padding:12px;
  font-size:13.5px;line-height:1.6;resize:vertical}
.lab-side{display:flex;flex-direction:column;gap:8px}
.lab-buttons{display:flex;gap:8px}
.btn{font:inherit;background:var(--accent);color:#06222e;border:0;border-radius:8px;
  padding:8px 14px;font-weight:600;cursor:pointer}
.btn:hover{filter:brightness(1.08)}
.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--line);font-weight:500}
pre.out{background:#0b0d11;border:1px solid var(--line);border-radius:10px;
  padding:12px;margin:0;flex:1;min-height:210px;overflow:auto;font-size:13px;
  white-space:pre-wrap;word-break:break-word}
pre.out:empty::after{content:"(output shows up here)";color:#4b5563}
.hints{margin-top:10px}
details.hint{border:1px solid var(--line);border-radius:9px;padding:8px 12px;margin:6px 0;
  background:var(--panel2)}
details.hint summary{cursor:pointer;color:var(--accent);font-size:14px}
details.hint p{margin:.5em 0 0;color:var(--muted)}
.checks li{list-style:none;position:relative;padding-left:26px}
.checks li::before{content:"\2610";position:absolute;left:0;color:var(--muted)}

/* nav */
.stepnav{display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap;
  margin-top:26px;padding-top:18px;border-top:1px solid var(--line)}
.btn-nav{display:inline-block;background:var(--panel2);border:1px solid var(--line);
  color:var(--text);border-radius:10px;padding:10px 14px;font-size:14px}
.btn-nav:hover{border-color:var(--accent);text-decoration:none}
.done{margin-top:18px;display:flex;align-items:center;gap:10px;color:var(--muted);
  font-size:14px}
.done input{width:18px;height:18px;accent-color:var(--green)}

/* index */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px}
.act{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.act h3{margin:0 0 6px;font-size:18px;color:var(--text)}
.act .n{font-size:12px;color:var(--accent);letter-spacing:.1em;text-transform:uppercase}
.act ol{margin:.6em 0 0;padding-left:1.2em}
.act li{margin:.25em 0}
.act li a{font-size:14.5px}
.done-mark{color:var(--green);font-weight:700;margin-left:6px}
.bar{height:6px;background:var(--panel2);border-radius:99px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--green))}
.small{font-size:13px;color:var(--muted)}
.footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:13px}
"""

PAGE_JS = r"""
// progress tracking
(function () {
  var KEY = 'fj-progress';
  function get() {
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); }
    catch (e) { return []; }
  }
  function set(a) { localStorage.setItem(KEY, JSON.stringify(a)); }
  function mark(id, on) {
    var a = get();
    var i = a.indexOf(id);
    if (on && i === -1) a.push(id);
    if (!on && i !== -1) a.splice(i, 1);
    set(a);
    paint();
  }
  function paint() {
    var a = get();
    document.querySelectorAll('[data-step]').forEach(function (el) {
      var on = a.indexOf(el.getAttribute('data-step')) !== -1;
      el.classList.toggle('is-done', on);
      var m = el.querySelector('.done-mark');
      if (m) m.textContent = on ? '\u2714' : '';
    });
    document.querySelectorAll('[data-progress]').forEach(function (el) {
      var act = el.getAttribute('data-progress');
      var steps = document.querySelectorAll('[data-act="' + act + '"]');
      var done = 0;
      steps.forEach(function (s) {
        if (a.indexOf(s.getAttribute('data-step')) !== -1) done++;
      });
      var pct = steps.length ? Math.round((done / steps.length) * 100) : 0;
      var bar = el.querySelector('.bar i');
      if (bar) bar.style.width = pct + '%';
      var lbl = el.querySelector('.pct');
      if (lbl) lbl.textContent = pct + '%';
    });
  }
  window.fjPaint = paint;

  // done checkbox on step pages
  var box = document.querySelector('.done input[type=checkbox]');
  if (box) {
    box.checked = get().indexOf(box.getAttribute('data-step')) !== -1;
    box.addEventListener('change', function () {
      mark(box.getAttribute('data-step'), box.checked);
    });
  }

  // lab runner (a tiny REPL, like python >>> )
  function runCode(code, outEl) {
    var logs = [];
    var origLog = console.log;
    console.log = function () {
      logs.push(Array.prototype.map.call(arguments, function (x) {
        if (typeof x === 'string') return x;
        try { return JSON.stringify(x); } catch (e) { return String(x); }
      }).join(' '));
    };
    try {
      var fn = new Function('"use strict";\n' + code + '\n//# sourceURL=lab.js');
      fn();
    } catch (err) {
      logs.push('Error: ' + err.message);
    } finally {
      console.log = origLog;
    }
    outEl.textContent = logs.join('\n');
  }

  document.querySelectorAll('textarea[id$="-code"]').forEach(function (ta) {
    var id = ta.id.replace(/-code$/, '');
    var out = document.getElementById(id + '-out');
    var runBtn = document.querySelector('[data-run="' + id + '"]');
    var clearBtn = document.querySelector('[data-clear="' + id + '"]');
    if (runBtn) runBtn.addEventListener('click', function () {
      runCode(ta.value, out);
    });
    if (clearBtn) clearBtn.addEventListener('click', function () {
      out.textContent = '';
    });
    ta.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        runCode(ta.value, out);
      }
    });
  });

  // copy buttons on code blocks
  document.querySelectorAll('pre.code').forEach(function (pre) {
    var b = document.createElement('button');
    b.className = 'copy';
    b.textContent = 'copy';
    b.style.cssText = 'position:absolute;right:8px;top:8px;font-size:11px;' +
      'background:#1d212a;color:#9aa3b2;border:1px solid #2a2f3a;border-radius:6px;' +
      'padding:2px 7px;cursor:pointer;opacity:0;transition:opacity .12s';
    pre.addEventListener("mouseenter", function () { b.style.opacity = '.55'; });
    pre.addEventListener("mouseleave", function () {
      if (b.textContent !== 'copied') b.style.opacity = '0';
    });
    b.addEventListener('click', function () {
      var code = pre.querySelector('code').innerText;
      navigator.clipboard && navigator.clipboard.writeText(code);
      b.textContent = 'copied';
      setTimeout(function () { b.textContent = 'copy'; }, 1200);
    });
    pre.style.position = 'relative';
    pre.appendChild(b);
  });

  paint();
})();
"""

def page(step, act, prev_step, next_step, index):
    """Render one step page."""
    blocks = "".join(render_block(b, step) for b in step["blocks"])
    labs = [b for b in step["blocks"] if b["type"] == "lab"]
    demos = [b for b in step["blocks"] if b["type"] == "demo"]

    # demo + lab bootstrap scripts
    scripts = []
    for d in demos:
        did = d.get("id", step["id"] + "-demo")
        scripts.append(
            "(function(){\nvar out=document.getElementById('%s-out');\n"
            "function s(x){if(typeof x==='string')return x;try{return JSON.stringify(x)}"
            "catch(e){return String(x)}}\n"
            "console.log=function(){var a=Array.prototype.slice.call(arguments)\n"
            ".map(s).join(' ');\n"
            "if(out){out.textContent+=a+'\\n'}};\n" % did
            + d.get("js", "") + "\n})();"
        )
    for r in step["blocks"]:
        if r.get("type") == "raw" and r.get("js"):
            scripts.append("(function(){\n" + r["js"] + "\n})();")
    for lb in labs:
        lid = lb.get("id", step["id"] + "-lab")
        scripts.append(
            "(function(){\nvar ta=document.getElementById('%s-code');\n"
            "var out=document.getElementById('%s-out');\n"
            "if(ta&&!ta.value){ta.value=%s;}\n"
            "if(ta&&out){\nvar logs=[];var orig=console.log;\n"
            "console.log=function(){logs.push(Array.prototype.slice.call(arguments)\n"
            ".map(function(x){if(typeof x==='string')return x;try{return JSON.stringify(x)}"
            "catch(e){return String(x)}}).join(' '))};\n"
            "try{new Function('\"use strict\";\\n'+ta.value+'\\n//# sourceURL=starter.js')();}\n"
            "catch(e){logs.push('Error: '+e.message)}\n"
            "console.log=orig;out.textContent=logs.join('\\n');}\n})();" % (
                lid, lid, _js_string(lb.get("starter", "")))
        )

    script_block = "\n".join(scripts)

    prev_html = ""
    if prev_step:
        prev_html = ('<a class="btn-nav" href="%s">&#8592; %s</a>'
                     % (prev_step["href"], html.escape(prev_step["title"])))
    next_html = ""
    if next_step:
        next_html = ('<a class="btn-nav" href="%s">%s &#8594;</a>'
                     % (next_step["href"], html.escape(next_step["title"])))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(step['title'])} &middot; {html.escape(act['title'])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <div class="brand">frontend<span>.journey</span></div>
  <div class="crumb">{html.escape(act['title'])} &middot; Step {step['no']} of {act['count']}</div>
  <div class="spacer"></div>
  <span class="pill">No frameworks. Vanilla JS + DOM.</span>
  <a class="pill" href="../../index.html">Map</a>
</div></div>

<div class="wrap">
  <p class="eyebrow">{html.escape(act['title'])} &middot; Step {step['no']}</p>
  <h1>{html.escape(step['title'])}</h1>
  <p class="lede">{step['lede']}</p>

  {blocks}

  <label class="done">
    <input type="checkbox" data-step="{step['id']}">
    <span>I finished this step &mdash; tick me off</span>
  </label>

  <div class="stepnav">
    {prev_html}
    <a class="btn-nav" href="../lesson.html">&#9776; {html.escape(act['title'])} overview</a>
    {next_html}
  </div>

  <p class="footer">Stuck? Re-read the idea block, then peek at one hint.
  Everything here is plain HTML + CSS + JavaScript. Open the file in your browser.</p>
</div>

<script>{PAGE_JS}</script>
<script>
{script_block}
</script>
</body>
</html>
"""

def _js_string(s):
    """Escape a python string so it can be a JS double-quoted literal."""
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\r", "")
    out = out.replace("\t", "\\t")
    return '"' + out + '"'

def act_page(act, steps):
    rows = ""
    for s in steps:
        rows += (
            '<li data-step="%s"><a href="steps/%s">%s</a>'
            '<span class="done-mark"></span>'
            '<div class="small">%s</div></li>' % (s["id"], s["href"], html.escape(s["title"]), s["lede"])
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(act['title'])} &middot; Frontend Journey</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <div class="brand">frontend<span>.journey</span></div>
  <div class="crumb">Act overview</div>
  <div class="spacer"></div>
  <a class="pill" href="../index.html">Map</a>
</div></div>
<div class="wrap">
  <p class="eyebrow">Act</p>
  <h1>{html.escape(act['title'])}</h1>
  <p class="lede">{act['lede']}</p>
  <div class="card">
    <h3>What you will build up to</h3>
    <ul>{act['outcome']}</ul>
  </div>
  <div class="card">
    <h3>Steps in this act</h3>
    <ol>{rows}</ol>
  </div>
  <div class="stepnav">
    <a class="btn-nav" href="../index.html">&#9776; Back to the map</a>
  </div>
</div>
<script>{PAGE_JS}</script>
</body>
</html>
"""

def index_page(acts):
    total_steps = sum(len(a["steps"]) for a in acts)
    cards = ""
    for a in acts:
        items = ""
        for s in a["steps"]:
            items += (
                '<li data-step="%s"><a href="%s/steps/%s">%s</a>'
                '<span class="done-mark"></span></li>'
                % (s["id"], a["dir"], s["href"], html.escape(s["title"]))
            )
        cards += f"""<div class="act" data-progress="{a['dir']}">
  <div class="n">{html.escape(a['tag'])}</div>
  <h3>{html.escape(a['title'])}</h3>
  <p class="small">{a['lede']}</p>
  <ol>{items}</ol>
  <div class="bar"><i></i></div>
  <p class="small pct" style="margin:.4em 0 0">0%</p>
  <p style="margin:.6em 0 0"><a href="{a['dir']}/lesson.html">Open act overview &#8594;</a></p>
</div>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Frontend Journey &middot; DOM Manipulation</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <div class="brand">frontend<span>.journey</span></div>
  <div class="crumb">Course map</div>
  <div class="spacer"></div>
  <span class="pill">Ticked steps are saved in your browser</span>
</div></div>
<div class="wrap">
  <p class="eyebrow">Start here</p>
  <h1>From zero JavaScript to a working DOM</h1>
  <p class="lede">You already know HTML and CSS, and you know Python.
  That is more than enough. This path teaches you the JavaScript you actually
  need, then shows you how to use it to grab and change the page &mdash;
  the DOM. {total_steps} small steps, one project, no frameworks.</p>

  <div class="card idea">
    <h3>How to walk this path</h3>
    <ul>
      <li>Do the steps in order. Each one only uses what came before it.</li>
      <li>Every step has a <strong>live demo</strong> (watch it work) and a
      <strong>lab</strong> (type code, press Run, see output &mdash; like the
      Python REPL).</li>
      <li>Each step ends with a <strong>tiny challenge</strong>. Small on purpose.</li>
      <li>Tick the box at the bottom of a step to mark it done.</li>
      <li>Never move on while something is still a mystery. Ask.</li>
    </ul>
  </div>

  <div class="grid">{cards}</div>

  <div class="footer">
    <p>Built as static HTML &mdash; open any file in your browser, no server needed.
    Progress is stored in your browser&rsquo;s localStorage.</p>
  </div>
</div>
<script>{PAGE_JS}</script>
</body>
</html>
"""
