# Frontend Journey

A complete, self-contained front-end course — **12 acts, 77 steps, 77 runnable files**.

Built for someone who already knows Python (variables, loops, conditionals, functions,
objects, classes) and has **never seen JavaScript**.

---

## Start here

| | |
|---|---|
| **Start here** | [`index.html`](index.html) — one page linking to every act and every step file |
| **Orientation** | [`00-setup-orientation/orientation.html`](00-setup-orientation/orientation.html) — the 5-minute setup checklist |
| **The board** | [`ROADMAP.md`](ROADMAP.md) — every act, every step, checkboxes |
| **Jump in** | [`01-html-structure/lesson.html`](01-html-structure/lesson.html) |

**No build step. No npm. No server required** (until Act 10). Every file is plain
HTML — double-click it and it runs.

---

## The acts

| Act | What you get | Steps |
|---|---|---|
| [0 — Setup](00-setup-orientation/lesson.html) | Editor, DevTools, the feedback loop | 1 |
| [1 — HTML](01-html-structure/lesson.html) | Structure, semantics, forms, accessibility | 9 |
| [2 — CSS](02-css-presentation/lesson.html) | Cascade, box model, flex, grid, responsive | 10 |
| [3 — Tailwind](03-tailwind-css/lesson.html) | Utility-first thinking, dark mode, tokens | 6 |
| [4 — JavaScript](04-javascript-the-language/lesson.html) | **The whole language, from zero** | 17 |
| [5 — Projects](05-your-five-projects/lesson.html) | bg-changer, counter, progress bar, dark mode, sidebar | 5 |
| [6 — Advanced JS](06-advanced-javascript/lesson.html) | Promises, fetch, forms, uploads, workers, perf | 7 |
| [7 — Browser](07-browser-architecture/lesson.html) | DOM → CSSOM → render tree → layout → paint | 4 |
| [8 — Networking & Security](08-networking-storage-security/lesson.html) | HTTP, storage, CORS, XSS, CSRF, JWT, caching | 7 |
| [9 — Modern APIs](09-modern-apis/lesson.html) | Streaming, SSE, service workers, WebSockets | 4 |
| [10 — Backend](10-a-backend-touchpoint/lesson.html) | Node, Express, webhooks, sessions | 3 |
| [11 — Frameworks](11-the-framework-bridge/lesson.html) | React, Next.js, shadcn — the bridge | 4 |

---

## The five projects (Act 5)

Each one is a complete, working app in a single file, plus a challenge to extend it.

1. **Background-changing button** — find, listen, change
2. **Number counter** — state → render → event
3. **Progress bar** — timers, transitions, not thrashing the layout
4. **Dark mode toggle** — CSS variables, `localStorage`, system preference
5. **Show/hide sidebar** — `aria-expanded`, `inert`, persistence

---

## Run the extras

```bash
# Act 10 — a real backend (REST + SSE + webhooks + a Web Worker)
cd 10-a-backend-touchpoint
npm install
npm start            # http://localhost:3000

# Act 11 — React with no build step (needs internet for the esm.sh CDN)
cd ../11-the-framework-bridge/react-mini
python3 -m http.server 8000    # then open http://localhost:8000
```

---

## How to actually use this

1. Open the act's `lesson.html` — that's the teaching, with code and explanations.
2. Open the step's file in `steps/` — that's the runnable demo, with a challenge at the bottom.
3. **Do the challenge before moving on.** It's the part that teaches.
4. Paste your attempt back to me. I review it like a code reviewer, and we move on.

Every step's file has a **"← Full Act lesson"** link and a **"Next step →"** link, so you
can just click through and never get lost.

---

## One thing to know about the JavaScript act

Act 4 is the biggest (17 steps) because you asked for the language itself — every
keyword, every idiom, all the parts that differ from Python. It's written so that
nothing feels like a mystery:

- `null` vs `undefined` (Python has only `None`)
- `===` vs `==` (Python has only `==`)
- `let` / `const` / `var` and why `var` is banned
- the prototype chain behind `class`
- `this` vs Python's `self`
- the event loop, microtasks vs macrotasks
- every time a JS idea has a Python twin, it says so

---

*Built as a journey, not a reference. Depth over exhaustiveness — the parts that matter
in production, mapped onto what you already know.*
