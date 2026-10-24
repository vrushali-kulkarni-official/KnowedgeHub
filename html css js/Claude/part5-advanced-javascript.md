# Part 5: Core Advanced JavaScript

---

# Lesson 14: ES6+ features you'll see in every codebase

## Destructuring: unpacking (like Python tuple unpacking)
```js
const user = { name: "Asha", age: 25, city: "Pune" };
const { name, age } = user;              // pulls out fields by name
const { city: town = "Unknown" } = user; // rename + default value

const [first, second] = [10, 20, 30];    // arrays by position
function greet({ name, age }) { }        // in function parameters (React props!)
```

## Spread `...` (unpack) and Rest `...` (collect)
```js
const a = [1, 2];
const b = [...a, 3];                     // [1,2,3]  copy + add
const user2 = { ...user, age: 26 };      // copy object, override age (immutable update)

function sum(...nums) {                  // rest: collects args into an array
  return nums.reduce((t, n) => t + n, 0);
}
```
Python: `[*a, 3]`, `{**user, "age": 26}`, `def sum(*nums)`. Same ideas. **Copy-then-change with spread** is how React state updates work.

## Optional chaining `?.` and nullish coalescing `??`
```js
const city = user.address?.city;         // undefined instead of crashing if address is missing
const items = data?.items ?? [];         // use [] only if left side is null/undefined
```
`??` differs from `||`: `0 || 10` gives 10 (0 is falsy), but `0 ?? 10` gives 0. Use `??` for defaults.

## Template literals, default params, modules
```js
const msg = `Hello ${name}, 2+2=${2 + 2}`;
function hi(name = "friend") { }

// math.js
export function add(a, b) { return a + b; }
export default function main() { }
// app.js
import main, { add } from "./math.js";     // use <script type="module" src="app.js">
```
Modules are how every framework organises code (like Python `import`).

---

# Lesson 15: Scope and Closures

## Scope: where a variable is visible
```js
const x = "global";
function f() {
  const y = "inside f";          // only visible inside f
  if (true) { let z = 1; }       // let/const are block-scoped; z is gone after the }
}
```
Inner code can see outer variables; not vice versa. (Python has the same "LEGB" idea.)

## Closure: a function that remembers where it was born

```js
function makeCounter() {
  let count = 0;                 // lives inside makeCounter
  return function () {
    count++;
    return count;
  };
}
const c1 = makeCounter();
c1();  // 1
c1();  // 2     count is still alive, remembered!
const c2 = makeCounter();
c2();  // 1     separate count
```
`makeCounter` finished running, yet the inner function still **carries a backpack** with `count` in it. That backpack is a **closure**. Python has identical behaviour with nested functions and `nonlocal`.

## Why it matters
1. **Private variables**: `count` can't be touched from outside, only via the returned function.
2. **Function factories**: `const double = multiplier(2)`.
3. **Callbacks remember context**: event handlers and timers use variables from where they were created.
4. **Debounce/throttle/memoize** (below) are all closures.
5. React hooks (`useState`) rely on them.

Classic gotcha: `var` in loops
```js
for (var i = 0; i < 3; i++) setTimeout(() => console.log(i));   // 3 3 3
for (let i = 0; i < 3; i++) setTimeout(() => console.log(i));   // 0 1 2
```
`let` creates a fresh `i` per iteration, so each closure keeps its own copy.

---

# Lesson 16: `this`

`this` means "the object that is calling me". Unlike Python's `self`, it's **not fixed at definition**; it's decided by **how the function is called**.

Four rules, in priority order:
```js
// 1. new: this is the brand-new object
new Person("Asha");

// 2. explicit: call / apply / bind set this manually
greet.call(user);              // run now with this = user
greet.apply(user, [args]);     // same, args as array
const bound = greet.bind(user); // returns a new function with this locked to user

// 3. method call: this is the object before the dot
user.greet();                  // this = user

// 4. plain call: this is undefined (strict mode) or window
const g = user.greet;
g();                           // this lost!
```
The famous bug: pulling a method out loses `this`.
```js
const user = { name: "Asha", hi() { console.log(this.name); } };
setTimeout(user.hi, 100);              // undefined!  (plain call)
setTimeout(() => user.hi(), 100);      // works
setTimeout(user.hi.bind(user), 100);   // works
```
## Arrow functions are different
An arrow function has **no `this` of its own**; it uses the `this` from where it was written (like a closure).
```js
const timer = {
  seconds: 0,
  start() {
    setInterval(() => { this.seconds++; }, 1000);   // arrow: this = timer
  }
};
```
Practical rules: use arrow functions for callbacks, regular methods for object methods. In event handlers, a regular `function` has `this` as the element, an arrow doesn't (use `e.currentTarget` instead).

---

# Lesson 17: Prototypes, Inheritance and Classes

Python classes: objects get behaviour from their class. JS objects get it from **another object**, their **prototype**. Every object has a hidden link to a parent object; when you access a property not found on the object, JS looks up the chain.

```js
const animal = { eats: true };
const dog = Object.create(animal);   // dog's prototype is animal
dog.barks = true;
dog.eats;                            // true  (not on dog, found on animal)
```
`dog` then `animal` then `Object.prototype` then `null`: that's the **prototype chain**.

## Constructor functions and shared methods
```js
function Person(name) { this.name = name; }
Person.prototype.hello = function () { return `Hi ${this.name}`; };
new Person("Asha").hello();
```
The method lives once on `Person.prototype`, and every instance shares it.

## `class`: the friendly syntax (it's sugar over the above)
```js
class Animal {
  constructor(name) { this.name = name; }     // like __init__
  speak() { return `${this.name} makes a sound`; }
}
class Dog extends Animal {
  constructor(name) {
    super(name);                               // like super().__init__(name)
    this.tricks = [];
  }
  speak() { return `${this.name} barks`; }     // override
}
new Dog("Rex").speak();
```
Python mapping: `constructor` is `__init__`, `this` is `self`, `extends` is `(Parent)`, `super()` the same. Underneath, `Dog.prototype` links to `Animal.prototype`. Knowing this explains why `typeof` classes is `"function"` and why methods lose `this` when detached (Lesson 16).

---

# Lesson 18: Error Handling

```js
try {
  const data = JSON.parse("not json");
} catch (err) {
  console.error(err.name, err.message);    // SyntaxError ...
} finally {
  hideSpinner();                           // always runs
}
```
Throw your own: `throw new Error("Invalid age");`

## Async errors
`try/catch` works with `await`:
```js
async function load() {
  try {
    const res = await fetch("/api");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);   // fetch won't throw by itself
    return await res.json();
  } catch (err) {
    showToast("Could not load");
    return null;
  }
}
```
With raw promises: `fetch(...).then(...).catch(err => ...)`. An error in any `.then` skips down to the nearest `.catch` (that's **error propagation**). An unhandled rejection is silently noisy; always catch or let the caller catch.

Gotcha: `try/catch` does NOT catch errors inside callbacks that run later (e.g. inside `setTimeout`); put the try/catch **inside** the callback.

Pattern: catch where you can do something useful (show a message), and let errors bubble up otherwise.

---

# Lesson 19: Debounce, Throttle, Memoization

All three are closures that control **how often** code runs.

## Debounce: "wait until they stop"
Use for search-as-you-type: don't call the API on every keystroke, only after the user pauses.
```js
function debounce(fn, delay) {
  let timer;                                   // closure variable
  return (...args) => {
    clearTimeout(timer);                       // cancel the previous wait
    timer = setTimeout(() => fn(...args), delay);
  };
}
input.addEventListener("input", debounce(search, 300));
```
## Throttle: "at most once per interval"
Use for scroll/resize handlers.
```js
function throttle(fn, interval) {
  let last = 0;
  return (...args) => {
    const now = Date.now();
    if (now - last >= interval) {
      last = now;
      fn(...args);
    }
  };
}
window.addEventListener("scroll", throttle(onScroll, 200));
```
Elevator analogy: debounce is the lift door waiting for people to stop walking in; throttle is a lift leaving every 10 seconds no matter what.

## Memoization: "remember answers"
```js
function memoize(fn) {
  const cache = new Map();
  return (n) => {
    if (cache.has(n)) return cache.get(n);
    const result = fn(n);
    cache.set(n, result);
    return result;
  };
}
const slowSquare = memoize((n) => { /* heavy work */ return n * n; });
```
Python equivalent: `functools.lru_cache`. Only use it for **pure** functions (same input gives same output, no side effects).

---

# Lesson 20: The Event Loop (concurrency, step by step)

Before the full browser picture in Part 6, here is the core model.

JS has **one thread**: it does one thing at a time. Yet `setTimeout` and `fetch` don't block. How?

The cast:
1. **Call Stack**: where functions run (last in, first out, like a stack of plates).
2. **Web APIs**: browser helpers (timers, network, DOM events) that run **outside** JS.
3. **Task queue (macrotasks)**: callbacks from timers, clicks, I/O.
4. **Microtask queue**: callbacks from Promises (`.then`, `await` continuations), `queueMicrotask`, `MutationObserver`.
5. **Event loop**: a loop that moves callbacks onto the stack **only when the stack is empty**.

Rule of the loop:
1. Run the current script until the stack is empty.
2. Run **all** microtasks (until the microtask queue is empty).
3. (Browser may render.)
4. Take **one** macrotask, run it, then back to step 2.

## Predict the output
```js
console.log("1");
setTimeout(() => console.log("2"), 0);
Promise.resolve().then(() => console.log("3"));
console.log("4");
```
Answer: `1, 4, 3, 2`.
- `1` and `4`: synchronous code runs first.
- `3`: the promise callback is a microtask, so it runs right after the script.
- `2`: `setTimeout` is a macrotask, so it waits for the next loop turn, even with 0ms.

`await` is a promise in disguise: code after `await` becomes a microtask.

Consequence: a long loop (`for` of a billion iterations) **blocks everything**, including clicks and painting, because nothing can run until the stack empties. The cure is workers (Part 6) or chunking the work. Also, an endless chain of microtasks can starve rendering.

---

# Lesson 21: Security Fundamentals (the first look)

Full treatment in Part 6. For now, three ideas that affect how you write JS today:
1. **Never put untrusted text into `innerHTML`.** Use `textContent`.
2. **Never trust the client.** Validation in JS is for convenience; the server must re-check everything.
3. **Never put secrets (API keys) in frontend code.** Everyone can read your JS with DevTools.

---

# Checkpoint

You now understand scope, closures, `this`, prototypes, modern syntax, errors, performance helpers and the event loop. Final stage: **Part 6**, what the browser does behind the scenes.
