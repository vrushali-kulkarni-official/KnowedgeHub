# Part 4: Talking to Servers (the 10 Advanced Topics)

---

# Lesson 13: The foundation, what is a server request?

A **server** is another computer running a program that answers requests. Your page sends an **HTTP request**, and the server sends back a **response**.

> **Python comparison:** like calling `requests.get(url)`. Same idea, same words.

A request has:
- **URL**: where to send it
- **Method**: `GET` (give me data), `POST` (here's new data), `PUT`/`PATCH` (update), `DELETE`
- **Headers**: extra info (e.g. `Content-Type`, `Authorization`)
- **Body**: the data you send (for POST etc.)

A response has a **status code** (`200` OK, `201` created, `400` bad request, `401` not logged in, `404` not found, `500` server error), headers, and a body (usually **JSON**).

**JSON** looks just like a Python dict/list:
```json
{ "name": "Asha", "skills": ["html", "css"] }
```

## Promises and async/await (the one scary idea, made simple)

Network calls take time. JS can't freeze the page while waiting, so these functions return a **Promise**: "I'll give you the result later."

Think of ordering food: you get a **token number** (the promise) immediately, and the food arrives later. `await` means "wait here for my food, but let other things on the page keep running."

```js
async function getUser() {
  const response = await fetch("https://jsonplaceholder.typicode.com/users/1");
  const data = await response.json();   // parsing is async too
  console.log(data.name);
}
getUser();
```
Rules: `await` only works inside a function marked `async`. `jsonplaceholder.typicode.com` is a free fake API for practice.

---

# Topic 1: Taking Input and Calling an API

Build a **user lookup**: type an ID, show the name.

```html
<input id="user-id" type="number" placeholder="Enter 1-10">
<button id="search">Search</button>
<p id="result"></p>
```
```js
const input = document.querySelector("#user-id");
const result = document.querySelector("#result");

document.querySelector("#search").addEventListener("click", async () => {
  const id = input.value;                         // DOM: read input
  result.textContent = "Loading...";
  const res = await fetch(`https://jsonplaceholder.typicode.com/users/${id}`);
  if (!res.ok) {                                   // status 404 etc.
    result.textContent = "User not found";
    return;
  }
  const user = await res.json();
  result.textContent = `${user.name} (${user.email})`;
});
```
Steps: read the input value, call `fetch`, check `res.ok`, parse JSON, update DOM. Memorise this shape; every API call looks like this.

Important: `fetch` does **not** throw on 404/500. It only throws on network failure. Always check `res.ok`.

---

# Topic 2: Submitting a Form and Sending Data

By default a form submit **reloads the page**. We intercept it.

```html
<form id="signup">
  <input name="username" placeholder="Username">
  <input name="email" type="email" placeholder="Email">
  <button type="submit">Sign up</button>
</form>
```
```js
document.querySelector("#signup").addEventListener("submit", async (e) => {
  e.preventDefault();                       // stop page reload

  const formData = new FormData(e.target);  // collects all inputs by their `name`
  const body = Object.fromEntries(formData);   // {username: "...", email: "..."}

  const res = await fetch("https://jsonplaceholder.typicode.com/posts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)              // object -> JSON string
  });
  const saved = await res.json();
  console.log("Server replied:", saved);
});
```
Mapping to Python: `JSON.stringify(obj)` is `json.dumps(obj)`, and `JSON.parse(str)` is `json.loads(str)`. The `fetch` options object is like keyword args to `requests.post(url, headers=..., data=...)`.

Why `submit` and not button `click`? The submit event also covers pressing Enter, and gives free validation (`required`, `type="email"`).

---

# Topic 3: Uploading Images

```html
<input type="file" id="photo" accept="image/*">
<img id="preview" class="w-40">
<button id="upload">Upload</button>
```
```js
const fileInput = document.querySelector("#photo");

// Bonus: preview before upload
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];            // FileList -> File
  document.querySelector("#preview").src = URL.createObjectURL(file);
});

document.querySelector("#upload").addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) return alert("Choose a file");

  const formData = new FormData();
  formData.append("photo", file);             // field name the server expects

  const res = await fetch("https://your-server.com/upload", {
    method: "POST",
    body: formData                            // NO Content-Type header here!
  });
  console.log(await res.json());
});
```
Why no `Content-Type`? For files the browser sends `multipart/form-data`, which includes a special **boundary** string separating the parts. The browser generates it automatically. If you set the header yourself, the boundary goes missing and the upload breaks.

`file.name`, `file.size`, `file.type` let you validate (e.g. reject files over 5MB) before sending.

---

# Topic 4: Parsing Data and Updating the Page

API returns an array, you turn it into HTML.

```html
<ul id="list"></ul>
```
```js
async function loadPosts() {
  const res = await fetch("https://jsonplaceholder.typicode.com/posts?_limit=5");
  const posts = await res.json();            // already parsed: array of objects

  const list = document.querySelector("#list");
  list.innerHTML = "";                        // clear old content
  posts.forEach(post => {
    const li = document.createElement("li");  // create element
    li.textContent = post.title;              // safe text
    list.appendChild(li);                     // attach to the tree
  });
}
loadPosts();
```
Create, fill, attach: the DOM-building pattern.

`JSON.parse` is used only when you hold JSON **as a string** (e.g. from `localStorage`). `res.json()` does the parse for you.

**`textContent` vs `innerHTML`**: `textContent` treats everything as plain text (safe). `innerHTML` parses it as HTML, which is dangerous with user data (see XSS in Part 6). Prefer `textContent`.

Shortcut with map and join (fine for **trusted** data only):
```js
list.innerHTML = posts.map(p => `<li>${p.title}</li>`).join("");
```

---

# Topic 5: Showing Conversation Messages (Chat UI)

Remember **state then render** from the counter? Same pattern, now with an array.

```html
<div id="chat" class="..."></div>
<form id="chat-form">
  <input id="msg" placeholder="Type a message" autocomplete="off">
  <button>Send</button>
</form>
```
```js
const messages = [
  { role: "assistant", content: "Hi! Ask me anything." }
];

function render() {
  const chat = document.querySelector("#chat");
  chat.innerHTML = "";
  messages.forEach(m => {
    const div = document.createElement("div");
    div.className = m.role === "user" ? "text-right" : "text-left";
    div.textContent = m.content;
    chat.appendChild(div);
  });
  chat.scrollTop = chat.scrollHeight;     // keep newest message in view
}

document.querySelector("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.querySelector("#msg");
  if (!input.value.trim()) return;
  messages.push({ role: "user", content: input.value });   // 1. change state
  input.value = "";
  render();                                                // 2. repaint
});
render();
```
The `{ role, content }` array is the exact format AI chat APIs use, so this transfers directly. (React just automates the render step.)

---

# Topic 6: SSE Streaming for AI Chat Responses

AI replies arrive token by token. The server keeps the connection open and **streams** pieces. Two ways to read it.

## Way 1: EventSource (simple, GET only)
```js
const source = new EventSource("/stream");
source.onmessage = (event) => {
  console.log(event.data);       // each chunk the server sends
};
source.onerror = () => source.close();
```
The wire format (SSE, Server-Sent Events) is plain text: `data: hello\n\n`. The browser reconnects automatically. Limits: GET only, no custom headers, so no `Authorization` header and no POST body.

## Way 2: fetch + ReadableStream (what AI apps actually use)
Because you must POST the conversation and send an auth header:
```js
async function ask(messages) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages })
  });

  const reader = res.body.getReader();        // a stream reader
  const decoder = new TextDecoder();          // bytes -> text
  let reply = "";

  while (true) {
    const { done, value } = await reader.read();   // wait for next chunk
    if (done) break;
    reply += decoder.decode(value, { stream: true });
    updateAssistantBubble(reply);                  // repaint as it grows
  }
}
```
Analogy: a Python generator. `reader.read()` is like calling `next()`. Each chunk may hold part of an SSE line (`data: {...}`), so real code splits the text on newlines and parses each `data:` line (buffer incomplete lines until the next chunk arrives).

Typical flow: push an empty assistant message into `messages`, then keep updating its `content` and re-rendering as chunks arrive.

---

# Topic 7: Async Updates of Page Components

Putting it together: a component that loads data and shows three states, **loading, error, success**.

```js
async function loadUser(id) {
  const box = document.querySelector("#box");
  box.textContent = "Loading...";                    // state 1
  try {
    const res = await fetch(`https://jsonplaceholder.typicode.com/users/${id}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const user = await res.json();
    box.textContent = user.name;                     // state 2: success
  } catch (err) {
    box.textContent = "Something went wrong";        // state 3: error
    console.error(err);
  }
}
```

## Running things in parallel
```js
const [users, posts] = await Promise.all([
  fetch("/users").then(r => r.json()),
  fetch("/posts").then(r => r.json())
]);
```
Both requests start at once; `await` resumes when **both** finish. Much faster than awaiting one after another. (Python's `asyncio.gather` is the same idea.)

## Why the page doesn't freeze
JS runs on **one thread**. `await` hands control back so the browser can handle clicks and painting, then resumes your function later via a queue. The mechanism is the **event loop**, explained fully in Part 6 and Part 5.

---

# Topic 8: Receiving Data via Webhooks

A **webhook** is the reverse of an API call: instead of *you* asking the server, *another service* (Stripe, GitHub, a payment gateway) sends an HTTP POST to **your server's URL** when something happens.

Browser JS **cannot** receive webhooks: a browser tab has no public address and can't listen for incoming connections. You need a backend. In Node.js with Express:

```js
// server.js  (run with: node server.js)
import express from "express";
const app = express();
app.use(express.json());

const clients = [];   // connected browsers (SSE)

app.post("/webhook", (req, res) => {
  console.log("Event received:", req.body);
  clients.forEach(c => c.write(`data: ${JSON.stringify(req.body)}\n\n`)); // push to browsers
  res.sendStatus(200);                // always reply quickly
});

app.get("/events", (req, res) => {
  res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
  clients.push(res);
  req.on("close", () => clients.splice(clients.indexOf(res), 1));
});

app.listen(3000);
```
Flow: **Stripe, then your server (`/webhook`), then SSE/WebSocket, then the browser** updates live.

Python comparison: this is Flask/FastAPI with `@app.post("/webhook")`.

Real-world rules:
- **Verify the signature** the service sends (a secret-based hash header), otherwise anyone can fake events.
- Reply `200` fast, do heavy work afterwards.
- For local testing, a tunnel tool (ngrok, cloudflared) gives your laptop a temporary public URL.

---

# Topic 9: Sessions and Cookies

HTTP is **stateless**: the server forgets you after every request. To stay logged in, something must identify you each time.

## Cookies
A small piece of text the server asks the browser to store; the browser then **automatically attaches it to every request** to that site.
```
Server response:  Set-Cookie: session_id=abc123; HttpOnly; Secure; SameSite=Lax
Next requests:    Cookie: session_id=abc123
```
The server maps `abc123` to your user (the **session**). Important flags:
- `HttpOnly`: JS **cannot** read it (blocks theft via XSS). Best for auth.
- `Secure`: HTTPS only.
- `SameSite`: limits sending on cross-site requests (helps against CSRF).

## Client-side access
```js
document.cookie = "theme=dark; max-age=86400; path=/";   // set
console.log(document.cookie);                             // "theme=dark; other=..." (not HttpOnly ones)
```
For cookies set by your server with `credentials`:
```js
fetch("/api/me", { credentials: "include" });   // send cookies on cross-origin requests too
```

## localStorage and sessionStorage
```js
localStorage.setItem("lang", "en");        // survives closing the browser
sessionStorage.setItem("draft", "hello");  // dies when the tab closes
localStorage.getItem("lang");              // "en"
localStorage.removeItem("lang");
// Only strings! Objects need JSON:
localStorage.setItem("user", JSON.stringify({ name: "Asha" }));
const user = JSON.parse(localStorage.getItem("user"));
```
| | Sent to server automatically? | JS can read? | Good for |
|---|---|---|---|
| Cookie (HttpOnly) | Yes | No | Auth sessions |
| Cookie (normal) | Yes | Yes | Small prefs |
| localStorage | No | Yes | Preferences, UI state |
| sessionStorage | No | Yes | Per-tab temp data |

---

# Topic 10: Managing JWTs

A **JWT** (JSON Web Token) is a signed string the server gives you after login, proving who you are without the server keeping a session list.

Shape: three Base64 parts joined by dots: `header.payload.signature`

```js
const token = "eyJhbGci...";                         // from login response
const payload = JSON.parse(atob(token.split(".")[1]));   // decode the middle part
// { sub: "42", name: "Asha", exp: 1735689600 }
```
`atob` decodes Base64. (For tokens using URL-safe Base64, replace `-` with `+` and `_` with `/` first.) **Decoding is not verifying**: anyone can read the payload (never put secrets in it), and only the server, which knows the secret key, can verify the signature. Never trust the client's reading of a token for security decisions; it's only good for UI hints like "show the user's name."

## Logging in and using the token
```js
// 1. Log in
const res = await fetch("/api/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password })
});
const { token } = await res.json();
localStorage.setItem("token", token);

// 2. Call a protected API
const data = await fetch("/api/profile", {
  headers: { Authorization: `Bearer ${localStorage.getItem("token")}` }
});

// 3. Check expiry (UI convenience)
function isExpired(token) {
  const { exp } = JSON.parse(atob(token.split(".")[1]));
  return Date.now() / 1000 > exp;   // exp is in seconds
}
```
## Where to store it? (a real trade-off)
- **localStorage**: easy, but any XSS script can steal it.
- **Memory (a JS variable)**: safest from theft, but lost on refresh.
- **HttpOnly cookie** set by the server: JS can't read it, so XSS can't steal it (but then you need CSRF protection). Most security-minded apps prefer this for the long-lived token, often with a short-lived access token kept in memory.

On a `401` response, the token is missing or expired: clear it and redirect to login.

---

# Checkpoint

You can now: fetch data, submit forms, upload files, render lists, build a chat, stream AI replies, understand webhooks, and handle cookies and JWTs. That's the working toolkit of most real frontends.

Next: **Part 5**, the deeper JavaScript concepts that explain *why* things behave as they do.
