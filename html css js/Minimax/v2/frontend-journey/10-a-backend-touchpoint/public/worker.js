/* Act 6 Step 6.6 — a Web Worker.
   Runs on its own thread, so the main thread stays responsive.
   It has NO access to the DOM (no document, no window) — but it does have
   self, postMessage, fetch, setTimeout and IndexedDB. */
self.onmessage = function (event) {
  const n = event.data.n || 1_000_000;
  const t0 = performance.now();

  let sum = 0;
  for (let i = 0; i < n; i++) {
    sum += Math.sqrt(i) * Math.sin(i);
  }

  self.postMessage({
    ms: Math.round(performance.now() - t0),
    result: sum,
    n: n,
  });
};
