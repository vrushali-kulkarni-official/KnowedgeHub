/**
 * Frontend Journey — Act 10 backend touchpoint
 * =============================================
 * A single small server that gives the course everything it needs:
 *
 *   GET    /api/items          -> JSON list
 *   POST   /api/items          -> create one
 *   DELETE /api/items/:id      -> remove one
 *   GET    /events             -> Server-Sent Events stream (Act 9.2)
 *   GET    /ws                 -> WebSocket echo (Act 9.4, needs `npm i ws`)
 *   POST   /webhooks/demo      -> fake webhook (Act 10.3)
 *   GET    /                   -> the demo front end in ./public
 *
 * Run:  npm install && npm start
 * Then: http://localhost:3000
 */
const path = require("path");
const crypto = require("crypto");
const express = require("express");

const app = express();
const PORT = process.env.PORT || 3000;

/* ------------------------------------------------------------------ *
 * 1. Middleware
 * ------------------------------------------------------------------ */

// CORS — see Act 10 Step 10.2. `*` + credentials is illegal, so we name origins.
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || "http://localhost:3000,http://localhost:5173")
  .split(",")
  .map((s) => s.trim());

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
  }
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
  if (req.method === "OPTIONS") return res.sendStatus(204); // answer the preflight
  next();
});

app.use(express.json());

// Cache headers + ETag — see Act 8 Step 8.7
app.set("etag", "strong");
app.use((req, res, next) => {
  if (req.path.startsWith("/api/")) {
    res.setHeader("Cache-Control", "no-cache"); // revalidate every time
  } else {
    res.setHeader("Cache-Control", "public, max-age=3600");
  }
  next();
});

// Serve the static front end from the SAME origin -> no CORS needed for it
app.use(express.static(path.join(__dirname, "public")));

/* ------------------------------------------------------------------ *
 * 2. A tiny in-memory data store (a real one would be a database)
 * ------------------------------------------------------------------ */
let items = [
  { id: 1, name: "Notebook", price: 6.5 },
  { id: 2, name: "Laptop", price: 1299 },
  { id: 3, name: "Monitor", price: 249 },
];

/* ------------------------------------------------------------------ *
 * 3. REST API
 * ------------------------------------------------------------------ */
app.get("/api/items", (req, res) => {
  res.json(items);
});

app.post("/api/items", (req, res) => {
  const item = {
    id: crypto.randomUUID(),
    name: String(req.body.name || "Untitled"),
    price: Number(req.body.price || 0),
  };
  items.push(item);
  res.status(201).json(item);
});

app.delete("/api/items/:id", (req, res) => {
  const before = items.length;
  // compare as strings: req.params.id is always a string, seeded ids are numbers
  items = items.filter((i) => String(i.id) !== String(req.params.id));
  if (items.length === before) return res.status(404).json({ error: "Not found" });
  res.status(204).end();
});

// A route that intentionally fails, so you can see the error path in the browser
app.get("/api/boom", (req, res) => res.status(500).json({ error: "Intentional failure" }));

/* ------------------------------------------------------------------ *
 * 4. Server-Sent Events  (Act 9.2)
 * ------------------------------------------------------------------ */
const sseClients = new Set();

app.get("/events", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });
  res.write("retry: 2000\n\n");
  res.write(`data: ${JSON.stringify({ type: "hello", at: Date.now() })}\n\n`);
  sseClients.add(res);
  req.on("close", () => sseClients.delete(res));
});

function broadcast(payload) {
  const frame = `data: ${JSON.stringify(payload)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(frame);
    } catch {
      sseClients.delete(client);
    }
  }
}

const ticker = setInterval(() => {
  broadcast({ type: "tick", n: Math.floor(Math.random() * 100), at: Date.now() });
}, 2000);
if (ticker.unref) ticker.unref();

/* ------------------------------------------------------------------ *
 * 5. Webhooks  (Act 10.3)
 * ------------------------------------------------------------------ */
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "dev-secret";

function sign(payload) {
  return crypto.createHmac("sha256", WEBHOOK_SECRET).update(payload).digest("hex");
}

app.post("/webhooks/demo", (req, res) => {
  const raw = JSON.stringify(req.body);
  const provided = req.get("x-webhook-signature") || "";

  // A real provider signs the RAW body; we re-sign what we received.
  if (provided && provided !== sign(raw)) {
    return res.status(400).json({ error: "Invalid signature" });
  }

  // Acknowledge FAST — real providers retry if you're slow.
  res.status(200).json({ ok: true });

  // ...then do the real work.
  broadcast({ type: "webhook", payload: req.body, at: Date.now() });
});

/* ------------------------------------------------------------------ *
 * 6. Boot
 * ------------------------------------------------------------------ */
const httpServer = app.listen(PORT, () => {
  console.log(`Frontend Journey server running at http://localhost:${PORT}`);
  console.log(`  allowed origins: ${ALLOWED_ORIGINS.join(", ")}`);
  console.log(`  try: curl localhost:${PORT}/api/items`);
  console.log(`  SSE:  curl -N localhost:${PORT}/events`);
});

// WebSocket (Act 9.4) — optional, needs `npm i ws`.
// Set up AFTER the server exists so we can attach to it.
try {
  const { WebSocketServer } = require("ws");
  const wss = new WebSocketServer({ server: httpServer, path: "/ws" });
  wss.on("connection", (socket) => {
    socket.send(JSON.stringify({ type: "welcome", at: Date.now() }));
    socket.on("message", (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        msg = { type: "raw", data: raw.toString() };
      }
      socket.send(JSON.stringify({ type: "echo", received: msg, at: Date.now() }));
    });
  });
  console.log("  WebSocket ready at ws://localhost:" + PORT + "/ws");
} catch {
  console.log("  (ws package not installed — WebSocket demo skipped. Run: npm i ws)");
}
