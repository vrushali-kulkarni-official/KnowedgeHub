# Part 2: JavaScript Basics and Your First 5 Projects

You know Python, so we map everything from Python to JS.

---

# Lesson 7: JavaScript in 15 minutes (for a Python programmer)

JS is the **brain** of the page. Add it before `</body>`:

```html
<script src="script.js"></script>
```

## Side by side

| Idea | Python | JavaScript |
|---|---|---|
| Print | `print("hi")` | `console.log("hi")` |
| Variable | `x = 5` | `let x = 5;` |
| Constant | (convention) | `const PI = 3.14;` |
| If | `if x > 3:` | `if (x > 3) { }` |
| Else if | `elif` | `else if` |
| For loop | `for i in range(3):` | `for (let i = 0; i < 3; i++) { }` |
| For each | `for x in items:` | `for (const x of items) { }` |
| Function | `def add(a, b):` | `function add(a, b) { return a + b; }` |
| List | `[1, 2]` | `[1, 2]` (array) |
| Dict | `{"a": 1}` | `{ a: 1 }` (object) |
| None | `None` | `null` / `undefined` |
| f-string | `f"hi {name}"` | `` `hi ${name}` `` (backticks) |
| and / or / not | `and or not` | `&& \|\| !` |

Key differences to remember:
1. Use `const` by default, `let` if the value will change. Avoid `var`.
2. Use `===` for comparison (strict equality). `"5" == 5` is true (bad!), `"5" === 5` is false (good).
3. Blocks use `{ }`, not indentation. Statements end with `;`.
4. Arrays and objects: `arr.push(4)` (like `append`), `arr.length` (like `len`), `obj.name` (like `d["name"]`).

## Arrow functions (you'll see these everywhere)

```js
const add = (a, b) => a + b;     // like Python lambda, but can be multi-line
const greet = (name) => {
  return `Hello ${name}`;
};
```

## Array methods (like Python comprehensions)

```js
const nums = [1, 2, 3, 4];
nums.map(n => n * 2);        // [2,4,6,8]   like [n*2 for n in nums]
nums.filter(n => n > 2);     // [3,4]       like [n for n in nums if n > 2]
nums.forEach(n => console.log(n));  // loop
```

Open the browser, press `F12`, go to the **Console** tab. You can type JS there and run it instantly.

---

# Lesson 8: The DOM, how JS controls the page

Remember the tree from Lesson 1? When the browser reads your HTML it builds a **tree of objects in memory** called the **DOM** (Document Object Model). JS can read and change this tree, and the screen updates.

> **Python comparison:** the DOM is a big nested object, and `document` is the root variable. Changing its fields changes the screen.

## Step 1: find an element
```js
const btn = document.getElementById("magic-btn");
const box = document.querySelector(".box");       // first match (CSS selector!)
const items = document.querySelectorAll("li");    // all matches
```
`querySelector` accepts the same selectors as CSS (`.class`, `#id`, `tag`). Use it everywhere.

## Step 2: change it
```js
box.textContent = "New text";         // change text
box.style.backgroundColor = "red";    // change inline style
box.classList.add("active");          // add a CSS class
box.classList.remove("active");
box.classList.toggle("active");       // add if missing, remove if present
```
`classList.toggle` is a superstar. Most UI tricks are "toggle a class, let CSS do the styling".

## Step 3: react to the user (events)
```js
btn.addEventListener("click", () => {
  console.log("clicked!");
});
```
Meaning: "When this button is clicked, run this function." The function is a **callback**. Other events: `input`, `submit`, `keydown`, `mouseover`.

You now have the 3-step recipe for **every** interactive feature: **find, listen, change**.

---

# Project 1: Background Changing Button

**index.html**
```html
<!DOCTYPE html>
<html>
<head>
  <title>Color Changer</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <button id="color-btn">Change Color</button>
  <script src="script.js"></script>
</body>
</html>
```

**style.css**
```css
body {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  transition: background 0.4s;
}
button { padding: 12px 24px; font-size: 18px; cursor: pointer; }
```

**script.js** (built in steps)

Step 1: find and listen.
```js
const btn = document.getElementById("color-btn");
btn.addEventListener("click", () => {
  document.body.style.backgroundColor = "tomato";
});
```
Step 2: random colors.
```js
btn.addEventListener("click", () => {
  const r = Math.floor(Math.random() * 256);
  const g = Math.floor(Math.random() * 256);
  const b = Math.floor(Math.random() * 256);
  document.body.style.backgroundColor = `rgb(${r}, ${g}, ${b})`;
});
```
**Challenge:** show the current color's text in the button.

---

# Project 2: Number Counter

```html
<h1 id="count">0</h1>
<button id="minus">-</button>
<button id="plus">+</button>
<button id="reset">Reset</button>
```
```js
let count = 0;
const display = document.querySelector("#count");

function render() {
  display.textContent = count;
}

document.querySelector("#plus").addEventListener("click", () => { count++; render(); });
document.querySelector("#minus").addEventListener("click", () => { count--; render(); });
document.querySelector("#reset").addEventListener("click", () => { count = 0; render(); });
```

## The big lesson: state and render

Notice the pattern: a variable `count` (the **state**) and a function `render()` that paints the state on screen. We change the state, then call render. **This is exactly the idea behind React.** In React, you only change state and the framework calls render for you. Remember this.

**Challenge:** make the number red when negative, green when positive (hint: `classList` or `style.color` inside `render()`).

---

# Project 3: Progress Bar

```html
<div class="bar"><div class="fill" id="fill"></div></div>
<button id="step">+10%</button>
```
```css
.bar  { width: 300px; height: 20px; background: #ddd; border-radius: 10px; overflow: hidden; }
.fill { height: 100%; width: 0%; background: #4caf50; transition: width 0.3s; }
```
```js
let progress = 0;
const fill = document.getElementById("fill");
document.getElementById("step").addEventListener("click", () => {
  progress = Math.min(progress + 10, 100);
  fill.style.width = progress + "%";
});
```
The outer div is the track, the inner div is the fill, and JS only changes the **width**. `Math.min` stops it going above 100.

**Challenge:** show the percentage text and use `setInterval` to fill automatically:
```js
const timer = setInterval(() => {
  progress++;
  fill.style.width = progress + "%";
  if (progress >= 100) clearInterval(timer);
}, 50);
```
`setInterval` runs a function repeatedly every N ms. (This is asynchronous behaviour; we'll fully explain it later.)

---

# Project 4: Dark Mode

The trick: CSS variables + toggling a class.

```css
:root {
  --bg: white;
  --text: #222;
}
body.dark {
  --bg: #121212;
  --text: #eee;
}
body { background: var(--bg); color: var(--text); transition: 0.3s; }
```
```html
<button id="theme">Toggle theme</button>
```
```js
const btn = document.getElementById("theme");
btn.addEventListener("click", () => {
  document.body.classList.toggle("dark");
});
```
That's it: when `.dark` is on `<body>`, the variables get new values, and every element using them changes.

## Remembering the choice (a first taste of storage)
```js
if (localStorage.getItem("theme") === "dark") {
  document.body.classList.add("dark");
}
btn.addEventListener("click", () => {
  const isDark = document.body.classList.toggle("dark");  // toggle returns true/false
  localStorage.setItem("theme", isDark ? "dark" : "light");
});
```
`localStorage` is a tiny key-value store inside the browser that survives refresh. Like a dict that gets saved to disk.

---

# Project 5: Show / Hide Sidebar

```html
<button id="menu">☰ Menu</button>
<aside id="sidebar" class="sidebar">
  <a href="#">Home</a>
  <a href="#">About</a>
</aside>
```
```css
.sidebar {
  position: fixed;
  top: 0; left: 0;
  width: 240px; height: 100vh;
  background: #222; color: white;
  padding: 20px;
  transform: translateX(-100%);   /* pushed off-screen to the left */
  transition: transform 0.3s;
}
.sidebar.open { transform: translateX(0); }   /* slides in */
```
```js
const sidebar = document.getElementById("sidebar");
document.getElementById("menu").addEventListener("click", () => {
  sidebar.classList.toggle("open");
});
```
Same pattern again: toggle a class, let CSS animate it. (`transform` is also the cheap way to animate; we'll see why in the rendering lessons.)

**Challenge:** close the sidebar when the user presses the `Escape` key:
```js
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") sidebar.classList.remove("open");
});
```
`e` is the **event object**, which carries details about what happened.

---

# Checkpoint

Every project followed **find, listen, change**, and the better ones followed **state, render**. You've built 5 working apps. Next: **Part 3, Tailwind CSS**, which lets us write the styling without leaving HTML.
