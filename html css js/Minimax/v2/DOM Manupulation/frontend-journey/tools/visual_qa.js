// Visual QA: exercises the real interactions in a real browser and screenshots blocks.
//   node tools/visual_qa.js
// Requires playwright-core + a chromium binary (see README in tools/).

const pw = (() => {
  try { return require("playwright-core"); }
  catch (e) { return require("/tmp/domtest/node_modules/playwright-core"); }
})();
const { chromium } = pw;

const EXE = process.env.CHROME ||
  "/root/.cache/ms-playwright/chromium-1243/chrome-linux/chrome";
const ROOT = "file:///workspace/frontend-journey/";
const OUT = "/workspace/.shots/";

let failures = 0;
function check(label, actual, expected) {
  const ok = String(actual) === String(expected);
  if (!ok) failures++;
  console.log((ok ? "  ok   " : "  FAIL ") + label + ": " + JSON.stringify(actual) +
              (ok ? "" : " (expected " + JSON.stringify(expected) + ")"));
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ["--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

  // --- 1. the lab: type code, press Run, read the output
  await page.goto(ROOT + "02-dom/steps/08-dom-events-deep.html");
  await page.locator('textarea[id$="-code"]').first()
    .fill('const nums = [1,2,3];\nconsole.log(nums.map(n => n * 2));');
  await page.locator("[data-run]").first().click();
  await page.waitForTimeout(250);
  check("lab Run prints the result",
    await page.locator("#dom-events-deep-lab-out").innerText(), "[2,4,6]");
  await page.locator(".card.demo").first().screenshot({ path: OUT + "qa_demo.png" });
  await page.locator(".card.lab").first().screenshot({ path: OUT + "qa_lab.png" });

  // --- 2. a live demo really filters
  await page.fill("#filter-input", "an");
  await page.waitForTimeout(200);
  check("filter demo hides non-matching rows",
    await page.locator("#filter-list li:visible").count(), 1);

  // --- 3. the project app: add / toggle / delete / count
  await page.goto(ROOT + "03-project/steps/01-project-todo.html");
  await page.fill("#todo-input", "learn the DOM");
  await page.click("#todo-add");
  await page.fill("#todo-input", "build something");
  await page.click("#todo-add");
  await page.waitForTimeout(200);
  check("todo app adds rows", await page.locator("#todo-list li").count(), 2);
  check("todo counter", await page.locator("#todo-count").innerText(), "2 left");
  await page.locator("#todo-list li .label").first().click();
  await page.waitForTimeout(150);
  check("toggling updates the counter", await page.locator("#todo-count").innerText(), "1 left");
  check("toggling marks the row done", await page.locator("#todo-list li.done").count(), 1);
  await page.locator("#todo-list li .del").first().click();
  await page.waitForTimeout(150);
  check("deleting removes the row", await page.locator("#todo-list li").count(), 1);
  await page.locator(".card.demo").first().screenshot({ path: OUT + "qa_todo.png" });

  // --- 4. progress tracking across pages
  await page.goto(ROOT + "01-js-basics/steps/01-js-variables.html");
  await page.locator(".done input").check();
  await page.waitForTimeout(200);
  check("progress is saved",
    await page.evaluate(() => localStorage.getItem("fj-progress")), '["js-variables"]');
  await page.goto(ROOT + "index.html");
  await page.waitForTimeout(250);
  check("the map shows the tick",
    (await page.locator(".act .done-mark").allInnerTexts()).filter(Boolean).length, 1);

  console.log(errors.length ? "JS ERRORS:\n" + errors.join("\n") : "no JS errors");
  console.log(failures ? failures + " FAILURES" : "all browser checks passed");
  await browser.close();
  process.exit(failures || errors.length ? 1 : 0);
})();
