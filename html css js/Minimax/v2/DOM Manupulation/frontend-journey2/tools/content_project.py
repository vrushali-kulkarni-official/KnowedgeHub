"""Act 3 - The project: build a todo app with zero libraries, then review it."""

STEPS = [

# ---------------------------------------------------------------- step 1
{
 "id": "project-todo",
 "title": "Project: a todo app with zero libraries",
 "lede": "Everything so far, combined into one thing you can actually use. No framework, no "
         "npm, no build step. Just HTML, CSS and the DOM.",
 "blocks": [
  {"type": "idea", "title": "The spec", "html":
   "<p>Build a todo list that has:</p>"
   "<ul>"
   "<li>an input + button that adds a task</li>"
   "<li>clicking a task toggles it between done and not done</li>"
   "<li>each task has a delete button</li>"
   "<li>a footer that says how many tasks are left</li>"
   "<li>the list survives a page refresh (localStorage)</li>"
   "</ul>"
   "<p>Nothing here needs a library. Every single feature above is something you already "
   "know how to do.</p>"},

  {"type": "idea", "title": "Milestones - do them in this order", "html":
   "<p>Do <strong>not</strong> try to write it all at once. Each milestone is a runnable "
   "version. Stop at each one and check it works before continuing.</p>"
   "<ol>"
   "<li><strong>State + render.</strong> Make a <code>todos</code> array and a <code>render() "
   "function</code> that draws it into a <code>&lt;ul&gt;</code>. Start with two hard-coded "
   "todos in the array. Check: do two rows appear?</li>"
   "<li><strong>Add.</strong> Wire up the button. Read the input's <code>value</code>, push a "
   "new object into the array, call <code>render()</code>, clear the input. Check: can you add "
   "five tasks?</li>"
   "<li><strong>Toggle + delete.</strong> Use <strong>event delegation</strong>: one click "
   "listener on the <code>&lt;ul&gt;</code>, using <code>event.target.closest(...)</code> to "
   "work out what was clicked. Check: can you toggle one row and delete another?</li>"
   "<li><strong>Counter.</strong> Show <code>todos.filter(t =&gt; !t.done).length</code> in the "
   "footer. Computed from the array, not by counting DOM nodes.</li>"
   "<li><strong>Persistence.</strong> Save with <code>localStorage.setItem(\"todos\", "
   "JSON.stringify(todos))</code> and load it back on start-up with "
   "<code>JSON.parse(localStorage.getItem(\"todos\"))</code>. Guard against it being "
   "<code>null</code>.</li>"
   "</ol>"
   "<p><strong>Shape of the data:</strong></p>"
   "<pre class=\"code\"><code>let todos = [\n"
   "  { id: 1, text: \"Learn the DOM\", done: false },\n"
   "  { id: 2, text: \"Build something\", done: false },\n"
   "];</code></pre>"
   "<p>Give every task an <code>id</code>. You need it to delete the right one, because the "
   "index in the DOM is not the same as the index in your array once you start filtering or "
   "deleting.</p>"},

  {"type": "note", "title": "The id trick", "html":
   "<p>Give each item a unique id, and put it in the DOM as a <code>data-id</code> attribute:</p>"
   "<pre class=\"code\"><code>li.dataset.id = todo.id;      // writes data-id=\"1\"\n\n"
   "// later, in your delegated handler:\n"
   "const id = Number(item.dataset.id);\n"
   "todos = todos.filter(t =&gt; t.id !== id);</code></pre>"
   "<p>Then <code>dataset.id</code> tells you exactly which task in your array to change. "
   "No index maths, no bugs when the list reorders.</p>"},

  {"type": "raw", "html":
   "<div class=\"card demo\">\n"
   "  <h3>&#9654; Reference app (spoilers - peek only after you have built it)</h3>\n"
   "  <div class=\"demo-stage\">\n"
   "    <ul id=\"todo-list\"></ul>\n"
   "    <div class=\"todo-foot\">\n"
   "      <input id=\"todo-input\" placeholder=\"What needs doing?\" />\n"
   "      <button id=\"todo-add\">Add</button>\n"
   "      <span id=\"todo-count\">0 left</span>\n"
   "      <button id=\"todo-clear\" class=\"ghostbtn\">Clear done</button>\n"
   "    </div>\n"
   "  </div>\n"
   "</div>",
   "js": """
     // ---------- state ----------
     let todos = [];
     let nextId = 1;

     const listEl = document.getElementById("todo-list");
     const inputEl = document.getElementById("todo-input");
     const countEl = document.getElementById("todo-count");

     // ---------- render ----------
     function render() {
       listEl.innerHTML = "";
       todos.forEach(function (todo) {
         const li = document.createElement("li");
         li.className = todo.done ? "done" : "";
         li.dataset.id = todo.id;

         const label = document.createElement("span");
         label.className = "label";
         label.textContent = todo.text;

         const del = document.createElement("button");
         del.className = "del";
         del.textContent = "x";
         del.dataset.action = "delete";

         li.append(label, del);
         listEl.append(li);
       });

       const left = todos.filter(t => !t.done).length;
       countEl.textContent = left + " left";

       localStorage.setItem("todos", JSON.stringify(todos));
     }

     // ---------- actions ----------
     function addTodo(text) {
       todos.push({ id: nextId++, text: text, done: false });
       render();
     }
     function toggleTodo(id) {
       todos = todos.map(function (t) {
         if (t.id === id) t.done = !t.done;
         return t;
       });
       render();
     }
     function deleteTodo(id) {
       todos = todos.filter(t => t.id !== id);
       render();
     }
     function clearDone() {
       todos = todos.filter(t => !t.done);
       render();
     }

     // ---------- events (one delegated listener) ----------
     listEl.addEventListener("click", function (event) {
       const delBtn = event.target.closest('[data-action="delete"]');
       if (delBtn) {
         deleteTodo(Number(delBtn.parentElement.dataset.id));
         return;
       }
       const row = event.target.closest("li");
       if (row) toggleTodo(Number(row.dataset.id));
     });

     document.getElementById("todo-add").addEventListener("click", function () {
       const text = inputEl.value.trim();
       if (text === "") return;
       addTodo(text);
       inputEl.value = "";
       inputEl.focus();
     });

     document.getElementById("todo-clear").addEventListener("click", clearDone);

     inputEl.addEventListener("keydown", function (e) {
       if (e.key === "Enter") document.getElementById("todo-add").click();
     });

     // ---------- start up ----------
     const saved = localStorage.getItem("todos");
     if (saved) {
       todos = JSON.parse(saved);
       nextId = todos.length ? Math.max.apply(null, todos.map(t => t.id)) + 1 : 1;
     }
     render();
   """},

  {"type": "code", "lang": "js", "title": "The full solution (read it AFTER you build yours)",
   "html": "<p>This is one way to do it. Yours will look different &mdash; that is fine. "
           "Compare the <em>shape</em>, not the letters.</p>",
   "code": """// ---------- state ----------
let todos = [];
let nextId = 1;

const listEl = document.getElementById("todo-list");
const inputEl = document.getElementById("todo-input");
const countEl = document.getElementById("todo-count");

// ---------- render ----------
function render() {
  // 1. clear the list
  listEl.innerHTML = "";

  // 2. draw one row per todo
  todos.forEach(function (todo) {
    const li = document.createElement("li");
    li.className = todo.done ? "done" : "";
    li.dataset.id = todo.id;

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = todo.text;

    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "x";
    del.dataset.action = "delete";

    li.append(label, del);
    listEl.append(li);
  });

  // 3. update the counter (computed from data, not from the DOM)
  const left = todos.filter(t => !t.done).length;
  countEl.textContent = left + " left";

  // 4. save
  localStorage.setItem("todos", JSON.stringify(todos));
}

// ---------- actions ----------
function addTodo(text) {
  todos.push({ id: nextId++, text: text, done: false });
  render();
}

function toggleTodo(id) {
  todos = todos.map(t => t.id === id ? { ...t, done: !t.done } : t);
  render();
}

function deleteTodo(id) {
  todos = todos.filter(t => t.id !== id);
  render();
}

function clearDone() {
  todos = todos.filter(t => !t.done);
  render();
}

// ---------- events (delegation) ----------
listEl.addEventListener("click", function (event) {
  const delBtn = event.target.closest('[data-action="delete"]');
  if (delBtn) {
    deleteTodo(Number(delBtn.parentElement.dataset.id));
    return;
  }

  const row = event.target.closest("li");
  if (row) toggleTodo(Number(row.dataset.id));
});

document.getElementById("todo-add").addEventListener("click", function () {
  const text = inputEl.value.trim();
  if (text === "") return;
  addTodo(text);
  inputEl.value = "";
  inputEl.focus();
});

document.getElementById("todo-clear").addEventListener("click", clearDone);

// ---------- start up ----------
const saved = localStorage.getItem("todos");
if (saved) {
  todos = JSON.parse(saved);
  nextId = todos.length ? Math.max(...todos.map(t => t.id)) + 1 : 1;
}
render();"""},

  {"type": "note", "title": "Two things in there you have not seen yet", "html":
   "<p>You will not understand every line yet, and that is fine. Two highlights:</p>"
   "<ul>"
   "<li><code>todos.map(t =&gt; t.id === id ? { ...t, done: !t.done } : t)</code> &mdash; "
   "the <code>...</code> is called <strong>spread</strong>. It copies an object, so you change "
   "the copy and not the original. (We will study it properly in the advanced JavaScript act.)</li>"
   "<li><code>Math.max(...todos.map(t =&gt; t.id))</code> &mdash; the <code>...</code> there "
   "spreads an array into separate arguments. Same symbol, different job.</li>"
   "</ul>"
   "<p>Both exist to make &ldquo;change one item in an array&rdquo; painless. You can also "
   "write it the long way:</p>"
   "<pre class=\"code\"><code>todos = todos.map(function (t) {\n"
   "  if (t.id === id) {\n"
   "    t.done = !t.done;   // same object, mutated\n"
   "  }\n"
   "  return t;\n"
   "});</code></pre>"},

  {"type": "try", "title": "Tiny challenge (extend it)",
   "html": "<p>Once your todo app works, add one of these:</p>",
   "checks": [
     "<strong>Edit:</strong> double-click a task's text and change it.",
     "<strong>Filter:</strong> three buttons &mdash; All / Active / Done &mdash; that show "
     "different subsets.",
     "<strong>Countdown:</strong> show &ldquo;2 of 5 done&rdquo; as well as &ldquo;2 left&rdquo;.",
     "<strong>Keyboard:</strong> pressing Enter in the input adds the task (you already know "
     "how &mdash; <code>keydown</code> + <code>e.key === \"Enter\"</code>).",
   ]},

  {"type": "checkpoint", "items": [
     "You combined state, actions and render into one working app.",
     "You used event delegation instead of one listener per row.",
     "You compute the counter from the array, not from the DOM.",
     "You persisted with <code>localStorage</code> + <code>JSON</code>.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 2
{
 "id": "project-review",
 "title": "Code review + how React thinks",
 "lede": "We review your app together, look for the parts that should change, and then see how "
         "much smaller the same app becomes in React.",
 "blocks": [
  {"type": "idea", "title": "The questions I will ask about any DOM code", "html":
   "<ol>"
   "<li><strong>Where is the truth?</strong> If I asked &ldquo;how many tasks are left?&rdquo; "
   "could you answer from the data alone? If the answer is &ldquo;count the DOM nodes&rdquo;, "
   "the truth is split in two places.</li>"
   "<li><strong>Does every change go through render()?</strong> If you ever change the DOM "
   "directly somewhere, you have two sources of truth again.</li>"
   "<li><strong>What happens if the element is missing?</strong> Any <code>querySelector</code> "
   "result used without a null check is a crash waiting to happen.</li>"
   "<li><strong>Is the listener attached to something that might be replaced?</strong> If "
   "<code>render()</code> rebuilds the list, a listener attached to an old row is gone. That is "
   "why delegation wins.</li>"
   "<li><strong>Is user data going into innerHTML?</strong> If yes, that is a bug waiting to "
   "happen.</li>"
   "</ol>"},

  {"type": "idea", "title": "The refactor", "html":
   "<p>If your code grew a bit messy while building, these are the three moves that clean up "
   "almost any DOM app:</p>"
   "<ol>"
   "<li><strong>Group by role, not by feature.</strong> Three labelled sections &mdash; "
   "<em>state</em>, <em>actions</em>, <em>render</em> &mdash; beat a pile of mixed functions.</li>"
   "<li><strong>One function per action.</strong> <code>addTodo</code>, "
   "<code>toggleTodo</code>, <code>deleteTodo</code>. Each one changes the state and calls "
   "<code>render()</code>. That is the whole pattern.</li>"
   "<li><strong>Get elements once at the top.</strong> "
   "<code>const listEl = document.getElementById(\"todo-list\")</code> near the top, then use "
   "<code>listEl</code> everywhere. Do not query the same element inside every function.</li>"
   "</ol>"},

  {"type": "code", "lang": "js", "title": "The same app in React (JSX - do not worry, just look)",
   "html": "<p>This is <strong>not</strong> JavaScript you can run in a browser tab. JSX is a "
           "syntax extension that React compiles. But look at the size of it &mdash; and at how "
           "close it is to the state + render pattern you already built.</p>",
   "code": """import { useState } from "react";

export default function TodoApp() {
  // state -- exactly like your `let todos = []`
  const [todos, setTodos] = useState([]);
  const [text, setText] = useState("");

  // action
  function addTodo() {
    if (!text.trim()) return;
    setTodos([...todos, { id: Date.now(), text, done: false }]);
    setText("");
  }

  function toggle(id) {
    setTodos(todos.map(t => (t.id === id ? { ...t, done: !t.done } : t)));
  }

  function remove(id) {
    setTodos(todos.filter(t => t.id !== id));
  }

  // render -- React calls this for you
  return (
    <div>
      <ul>
        {todos.map(todo => (
          <li key={todo.id} className={todo.done ? "done" : ""} onClick={() => toggle(todo.id)}>
            {todo.text}
            <button onClick={() => remove(todo.id)}>x</button>
          </li>
        ))}
      </ul>
      <input value={text} onChange={e => setText(e.target.value)} />
      <button onClick={addTodo}>Add</button>
      <span>{todos.filter(t => !t.done).length} left</span>
    </div>
  );
}"""},

  {"type": "note", "title": "What React actually took off your hands", "html":
   "<p>Compare the two versions line by line and you will find three things React gave you:</p>"
   "<ol>"
   "<li><strong>No manual rendering.</strong> You change the state, React works out which parts "
   "of the page changed and patches only those. You never write "
   "<code>list.innerHTML = \"\"</code> again.</li>"
   "<li><strong>No manual event delegation.</strong> React already listens once at the root. "
   "You write <code>onClick</code> on an element and it just works &mdash; including on elements "
   "that did not exist yet when the page loaded.</li>"
   "<li><strong>No manual keys.</strong> You still write <code>key={todo.id}</code> &mdash; but "
   "that is the same idea you already learned with <code>data-id</code>.</li>"
   "</ol>"
   "<p>Everything else &mdash; state, actions, events, ids, <code>filter</code>, <code>map</code> "
   "&mdash; is <strong>exactly the JavaScript you just learned</strong>. React is not a new "
   "language. It is a new way of running the code you can already write.</p>"},

  {"type": "idea", "title": "Where you are now", "html":
   "<p>Look at that list again:</p>"
   "<ul>"
   "<li>You know the JavaScript you need: variables, functions, arrays, objects, callbacks.</li>"
   "<li>You know how to find elements, read and write them, create them, style them, delete "
   "them.</li>"
   "<li>You know the pattern every modern front-end framework is built on: state &rarr; "
   "render.</li>"
   "</ul>"
   "<p><strong>Next stop:</strong> TypeScript (types for your data), then React, then "
   "Next.js. All three sit on top of what you just built with your own hands. You are further "
   "along than it feels right now.</p>"},

  {"type": "try", "title": "Tiny challenge (proof you own this)",
   "html": "<p>Without looking at the reference solution, rebuild the todo app from an empty "
           "file in under 20 minutes.</p>",
   "checks": [
     "State, actions and render are clearly separated.",
     "One delegated listener on the list.",
     "The counter is computed from the array.",
     "It survives a refresh (localStorage).",
     "Bonus: send me the code and I will review it line by line.",
   ]},

  {"type": "checkpoint", "items": [
     "State + actions + render is the pattern React automates.",
     "DOM code smells: split truth, missing null checks, listeners on replaced elements, "
     "innerHTML with user data.",
     "You are ready for TypeScript and React.",
  ]},
 ],
}
]
