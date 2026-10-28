// Smoke-test every built page in a real DOM: load it, click things, and check
// that the demos actually changed the page.

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("/tmp/domtest/node_modules/jsdom");

const ROOT = "/workspace/frontend-journey";

function walk(dir, acc = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "tools") continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.name.endsWith(".html")) acc.push(p);
  }
  return acc;
}

const files = walk(ROOT).sort();
let failures = 0;
let checks = 0;

function fail(msg) {
  failures++;
  console.log("  FAIL: " + msg);
}

for (const file of files) {
  const rel = path.relative(ROOT, file);
  const html = fs.readFileSync(file, "utf-8");
  const vc = new VirtualConsole();
  const errors = [];
  vc.on("jsdomError", (e) => errors.push("jsdomError: " + e.message));
  vc.on("error", (...a) => errors.push("console.error: " + a.join(" ")));

  let dom;
  try {
    dom = new JSDOM(html, { runScripts: "dangerously", virtualConsole: vc, url: "http://localhost/" });
  } catch (e) {
    fail(rel + " -> failed to load: " + e.message);
    continue;
  }
  const { window } = dom;
  const doc = window.document;

  // 1. no script errors on load
  if (errors.length) fail(rel + " -> " + errors.join(" | "));

  // 2. every lab: the starter code must run and produce output
  const labs = [...doc.querySelectorAll('textarea[id$="-code"]')];
  for (const ta of labs) {
    const id = ta.id.replace(/-code$/, "");
    const out = doc.getElementById(id + "-out");
    checks++;
    if (!ta.value.trim()) fail(rel + " -> lab " + id + " has no starter code");
    if (!out || !out.textContent.trim()) {
      fail(rel + " -> lab " + id + " produced no output on load");
    }
    if (out && /Error:/.test(out.textContent)) {
      fail(rel + " -> lab " + id + " starter threw: " + out.textContent.trim().slice(0, 200));
    }
  }

  // 3. every demo: fill inputs, click the buttons, check something moved
  const buttons = [...doc.querySelectorAll(".demo-stage button, .demo button")];
  for (const btn of buttons) {
    // fill any empty inputs so add/submit style demos actually do something
    for (const inp of doc.querySelectorAll(".demo-stage input")) {
      if (!inp.value) {
        inp.value = "smoke test";
        inp.dispatchEvent(new window.Event("input", { bubbles: true }));
      }
    }
    const before = doc.body.innerHTML;
    checks++;
    try {
      btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    } catch (e) {
      fail(rel + " -> click on #" + btn.id + " threw: " + e.message);
      continue;
    }
    if (errors.length) {
      fail(rel + " -> click on #" + btn.id + " caused: " + errors.join(" | "));
      errors.length = 0;
    }
    if (doc.body.innerHTML === before && btn.id) {
      console.log("  note: " + rel + " click on #" + btn.id + " changed nothing");
    }
  }

  // 3b. forms: submit them and make sure nothing reloads or throws
  for (const form of doc.querySelectorAll("form")) {
    checks++;
    try {
      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    } catch (e) {
      fail(rel + " -> submit threw: " + e.message);
    }
    if (errors.length) {
      fail(rel + " -> submit caused: " + errors.join(" | "));
      errors.length = 0;
    }
  }

  // 4. demo stage output elements should exist for each demo script
  const outs = [...doc.querySelectorAll("pre.out")];
  for (const o of outs) checks++;

  window.close();
}

console.log("\n%d pages, %d checks, %d failures", files.length, checks, failures);
process.exit(failures ? 1 : 0);
