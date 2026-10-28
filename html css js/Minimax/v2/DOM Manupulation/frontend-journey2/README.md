# Frontend Journey - DOM Manipulation

A self-paced course for someone who already knows **HTML and CSS**, knows **Python**,
and knows **zero JavaScript** - and wants to learn DOM manipulation properly.

## How to use it

Open `index.html` in your browser. That is the map. Everything is static HTML, so no
server, no install, no build step.

Each step page has:

- **The idea** - the concept, explained in plain language, with a Python bridge
- **Live demo** - a working example you can click
- **Your turn (lab)** - a small editor with a Run button, like the Python REPL
- **Tiny challenge** - one small thing to build yourself
- **Checkpoint** - what you should be able to explain now

Tick the box at the bottom of each step. Your progress is saved in the browser
(`localStorage`), and the course map shows it.

## The path

| Act | What it covers | Steps |
|-----|----------------|-------|
| Act 1 | JavaScript basics for the DOM | 6 |

| Act 2 | DOM manipulation | 9 |

| Act 3 | Put it together: a project | 2 |

## The one rule of this course

Never move to the next step while something is still a mystery. Ask, fix it, then move on.

## Rebuilding

Course content lives in Python data files under `tools/`:

```
tools/render.py          page templates + syntax highlighting
tools/content_js.py      Act 1 - JavaScript basics
tools/content_dom.py     Act 2 - DOM manipulation
tools/content_project.py Act 3 - the project
tools/build.py           renders everything to HTML
```

Edit a content file, then:

```bash
python3 tools/build.py
```
