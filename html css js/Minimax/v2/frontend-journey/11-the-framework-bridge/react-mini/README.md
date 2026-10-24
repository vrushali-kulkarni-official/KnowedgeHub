# React mini-app — no build step

A real React app that runs in the browser with **zero tooling**. No Vite, no JSX
compiler, no `npm install`.

## Run it

```bash
cd 11-the-framework-bridge/react-mini
python3 -m http.server 8000
# open http://localhost:8000
```

A server is required because ES modules (`import`) can't be loaded from a
`file://` page — the browser blocks them (CORS). Any static server works; VS Code's
"Live Server" extension is the easiest.

Internet access is required on first load: React and `htm` come from the
`esm.sh` CDN.

## Why `htm` instead of JSX

JSX has to be compiled before the browser can run it — that's what Vite/Next.js do.
`htm` gives you the same "HTML-ish template" ergonomics as a tagged template
literal, with **zero compilation**:

```jsx
// JSX
<Counter count={count} onClick={() => setCount(count + 1)} />

// htm — exactly the same thing, no build step
html`<${Counter} count=${count} onClick=${() => setCount(count + 1)} />`
```

JSX is sugar over `React.createElement(...)`. `htm` is sugar over
`React.createElement(...)` too. Same runtime, same mental model — you just don't
need a compiler to read it.

## What's in here

| File | What's in it |
|---|---|
| `index.html` | the page, loads `app.js` as a module |
| `app.js` | the whole app: `Counter`, `Clock`, `Users`, `App` |
| `app.css` | plain CSS, no Tailwind |

## What to look at

1. **`Counter`** — `useState` is Act 5's `let count = 0`, scoped to the component.
   Each `Counter` gets its own.
2. **`Clock`** — `useEffect` with a cleanup function (Act 11 Step 11.3).
3. **`Users`** — the three states: loading / error / data (Act 6 Step 6.2).
4. **`App`** — state lives here, props flow down, events flow up.

## Then move to the real thing

```bash
npx create-next-app@latest my-app
```

The only real difference is that JSX replaces `html\`...\`` — everything else
(components, props, state, effects, the data flow) is identical to what you see
here. Read `app.js` first; it'll make the Next.js code feel familiar.
