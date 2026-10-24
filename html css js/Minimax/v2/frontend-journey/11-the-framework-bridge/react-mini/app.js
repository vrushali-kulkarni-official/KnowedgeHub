/* Act 11 — React with no build step.
 *
 * React 18 from esm.sh + htm for the template syntax.
 * Requires internet access (esm.sh is a CDN).
 */
import React, { useState, useEffect } from "https://esm.sh/react@18";
import { createRoot } from "https://esm.sh/react-dom@18/client";
import htm from "https://esm.sh/htm";

const html = htm.bind(React.createElement);

/* ------------------------------------------------------------------ *
 * 1. A leaf component — props in, UI out. Exactly like Act 4 Step 4.9.
 * ------------------------------------------------------------------ */
function Counter({ label, onRemove }) {
  // useState IS the Act 5 "let count = 0", but scoped to this component.
  const [count, setCount] = useState(0);

  return html`
    <div class="counter">
      <span class="counter-label">${label}</span>
      <div class="counter-row">
        <button onClick=${() => setCount((c) => c - 1)}>-</button>
        <strong>${count}</strong>
        <button onClick=${() => setCount((c) => c + 1)}>+</button>
        <button class="ghost" onClick=${onRemove}>remove</button>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ *
 * 2. A component with an effect — the Act 4 Step 4.13 / Act 6 pattern.
 * ------------------------------------------------------------------ */
function Clock() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id); // cleanup — Act 11 Step 11.3
  }, []);

  return html`<p class="clock">${now.toLocaleTimeString()}</p>`;
}

/* ------------------------------------------------------------------ *
 * 3. Data fetching with all three states — Act 6 Step 6.2.
 * ------------------------------------------------------------------ */
function Users() {
  const [state, setState] = useState({ status: "loading", users: [] });

  useEffect(() => {
    let cancelled = false;
    fetch("https://jsonplaceholder.typicode.com/users?_limit=5")
      .then((r) => r.json())
      .then((users) => {
        if (!cancelled) setState({ status: "done", users });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error", users: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") return html`<p class="muted">Loading users…</p>`;
  if (state.status === "error") return html`<p class="error">Could not load users.</p>`;

  return html`
    <ul class="users">
      ${state.users.map(
        (u) => html`<li key=${u.id}>${u.name} <span class="muted">${u.email}</span></li>`
      )}
    </ul>`;
}

/* ------------------------------------------------------------------ *
 * 4. The root: state lives here, props flow down, events flow up.
 * ------------------------------------------------------------------ */
function App() {
  const [labels, setLabels] = useState(["Alpha", "Beta", "Gamma"]);

  const addCounter = () =>
    setLabels((prev) => [...prev, `Counter ${prev.length + 1}`]);

  const removeCounter = (label) =>
    setLabels((prev) => prev.filter((l) => l !== label));

  return html`
    <div class="app">
      <span class="pill">Act 11</span>
      <h1>React mini-app</h1>
      <p class="lede">
        The same state → render → event loop you built by hand in Act 5, but now
        React re-renders the component and patches the DOM for you.
      </p>

      <section>
        <h2>State → render → event</h2>
        <p class="muted">
          Each counter owns its own state — they are independent, exactly like
          two separate <code>let</code> variables in the vanilla version.
        </p>
        <div class="counters">
          ${labels.map(
            (label) => html`<${Counter} key=${label} label=${label} onRemove=${() => removeCounter(label)} />`
          )}
        </div>
        <button class="primary" onClick=${addCounter}>Add a counter</button>
      </section>

      <section>
        <h2>An effect, with cleanup</h2>
        <${Clock} />
      </section>

      <section>
        <h2>Data fetching: loading / error / data</h2>
        <${Users} />
      </section>

      <section>
        <h2>Try this</h2>
        <ol>
          <li>Click "+" on one counter. Does the other one change? (It shouldn't.)</li>
          <li>Remove one counter, then add a new one. What key does React use?</li>
          <li>Go offline in DevTools → Network. What does the Users list show?</li>
          <li>Compare this file with your Act 5 counter. Same pattern, less code.</li>
        </ol>
      </section>
    </div>`;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
