# Frontend Journey — your progress board

**Who this is for:** someone who already knows Python and programming
fundamentals, and knows *zero* JavaScript.

**How the course works:** one concept → one small runnable file → one tiny
challenge → you paste your attempt → I review it like a code reviewer →
next concept. No lecture dumps.

**Bridge rule:** every new concept gets mapped to a Python equivalent you
already own.

**12 acts · 77 steps · 77 runnable files.**

---

## Act 0 — [Setup & Orientation](00-setup-orientation/lesson.html)

*Everything you need, nothing you don't. Fifteen minutes, once.*

- [ ] **0.1** [Your Toolkit](00-setup-orientation/steps/0-1-your-toolkit.html) — Get a working editor + browser + DevTools loop, and understand the four DevTools panels you'll actually use.

## Act 1 — [HTML — Structure](01-html-structure/lesson.html)

*HTML is a description of structure. Once this act clicks, the rest of the web makes far more sense.*

- [ ] **1.1** [HTML Describes, It Doesn't Do](01-html-structure/steps/1-1-html-describes-it-doesn-t-do.html) — Lock in the mental model: HTML is a static description of structure, not a program.
- [ ] **1.2** [Anatomy of a Tag](01-html-structure/steps/1-2-anatomy-of-a-tag.html) — Know the four parts of every element, and the one exception to the open/close rule.
- [ ] **1.3** [The Document Skeleton](01-html-structure/steps/1-3-the-document-skeleton.html) — Know what belongs in <head> vs <body>, and why the three meta tags matter.
- [ ] **1.4** [Nesting & the Forgiving Parser](01-html-structure/steps/1-4-nesting-the-forgiving-parser.html) — Understand how the browser builds the tree, and why your source and the DOM can disagree.
- [ ] **1.5** [The Vocabulary of a Page](01-html-structure/steps/1-5-the-vocabulary-of-a-page.html) — Learn the semantic elements, and the one rule that keeps HTML clean forever.
- [ ] **1.6** [Headings, Lists & Text Semantics](01-html-structure/steps/1-6-headings-lists-text-semantics.html) — Use the text-level elements correctly, and keep your heading outline valid.
- [ ] **1.7** [Attributes Are Hooks](01-html-structure/steps/1-7-attributes-are-hooks.html) — Understand id, class and data-* as the interface that CSS and JavaScript will grab onto.
- [ ] **1.8** [Forms & Inputs](01-html-structure/steps/1-8-forms-inputs.html) — Learn the form vocabulary — this is the part that directly feeds your API, form-submit and file-upload work later.
- [ ] **1.9** [Images, Links & Entities](01-html-structure/steps/1-9-images-links-entities.html) — Write accessible images and links, and handle special characters correctly.

## Act 2 — [CSS — Presentation](02-css-presentation/lesson.html)

*The cascade, the box, and the two layout systems (flex and grid) that you will use every single day.*

- [ ] **2.1** [What CSS Is & Where It Lives](02-css-presentation/steps/2-1-what-css-is-where-it-lives.html) — Learn the only syntax CSS has, and the three places a rule can live.
- [ ] **2.2** [Selectors & Specificity](02-css-presentation/steps/2-2-selectors-specificity.html) — Predict which rule wins, every time, without guessing.
- [ ] **2.3** [Inheritance & Custom Properties](02-css-presentation/steps/2-3-inheritance-custom-properties.html) — Control how properties flow down the tree, and build themable values with CSS variables.
- [ ] **2.4** [The Box Model](02-css-presentation/steps/2-4-the-box-model.html) — Predict the size of every element on the page, exactly.
- [ ] **2.5** [Display & the Normal Flow](02-css-presentation/steps/2-5-display-the-normal-flow.html) — Understand the default layout algorithm, and how to take an element out of it.
- [ ] **2.6** [Flexbox](02-css-presentation/steps/2-6-flexbox.html) — Master the one layout system you'll use every single day.
- [ ] **2.7** [CSS Grid](02-css-presentation/steps/2-7-css-grid.html) — Lay out in two dimensions, and stop reaching for nested flex hacks.
- [ ] **2.8** [Positioning & Stacking](02-css-presentation/steps/2-8-positioning-stacking.html) — Take elements out of normal flow deliberately, and control what paints on top.
- [ ] **2.9** [Responsive Design & Units](02-css-presentation/steps/2-9-responsive-design-units.html) — Write layouts that adapt to any screen, and size things in units that respect the user's settings.
- [ ] **2.10** [Transitions, Transforms & Animation](02-css-presentation/steps/2-10-transitions-transforms-animation.html) — Add motion that feels good and stays smooth.

## Act 3 — [Tailwind CSS](03-tailwind-css/lesson.html)

*The same layout knowledge, expressed as small composable utility classes.*

- [ ] **3.1** [The Utility-First Shift](03-tailwind-css/steps/3-1-the-utility-first-shift.html) — Get past the 'this is just inline styles' objection and understand the real trade-off.
- [ ] **3.2** [Reading the Scales](03-tailwind-css/steps/3-2-reading-the-scales.html) — Stop memorising class names individually — learn the scales and the names derive themselves.
- [ ] **3.3** [Layout with Utilities](03-tailwind-css/steps/3-3-layout-with-utilities.html) — Translate Act 2's flexbox and grid knowledge into class lists.
- [ ] **3.4** [Variants](03-tailwind-css/steps/3-4-variants.html) — Master the prefix syntax — responsive, state, group, peer.
- [ ] **3.5** [Dark Mode](03-tailwind-css/steps/3-5-dark-mode.html) — Build dark mode with CSS variables so it doesn't require duplicating every class.
- [ ] **3.6** [Customising & Extracting](03-tailwind-css/steps/3-6-customising-extracting.html) — Make Tailwind yours — custom colours, fonts, and a rule for when to break out of utilities.

## Act 4 — [JavaScript — The Language](04-javascript-the-language/lesson.html)

*You have never seen this language. So we build it from nothing: one idea at a time, each one mapped onto Python.*

- [ ] **4.1** [How JavaScript Runs](04-javascript-the-language/steps/4-1-how-javascript-runs.html) — Understand that JS is a language that needs a host, and that the browser is that host.
- [ ] **4.2** [Values & Variables](04-javascript-the-language/steps/4-2-values-variables.html) — Learn <code>let</code>, <code>const</code>, <code>var</code> — and why one of them is basically banned.
- [ ] **4.3** [Types & <code>typeof</code>](04-javascript-the-language/steps/4-3-types-code-typeof-code.html) — Know every type JavaScript has, and that only one of them is really dynamic.
- [ ] **4.4** [Strings & Template Literals](04-javascript-the-language/steps/4-4-strings-template-literals.html) — Handle text properly, including the quoting rules that trip up Python programmers.
- [ ] **4.5** [Truthiness, Coercion, <code>??</code> & <code>?.</code>](04-javascript-the-language/steps/4-5-truthiness-coercion-code-code-code-code.html) — Understand how JavaScript decides if something is 'true' — and stop being surprised by it.
- [ ] **4.6** [Arrays](04-javascript-the-language/steps/4-6-arrays.html) — Master the workhorse data structure — and the methods that replace most of your Python loops.
- [ ] **4.7** [Objects](04-javascript-the-language/steps/4-7-objects.html) — Understand JS objects as dictionaries, and the reference semantics that surprise everyone.
- [ ] **4.8** [Destructuring, Spread & Rest](04-javascript-the-language/steps/4-8-destructuring-spread-rest.html) — Learn the three ES6 features you will use in literally every modern file.
- [ ] **4.9** [Functions](04-javascript-the-language/steps/4-9-functions.html) — Write functions in all three JS forms and know exactly when to use each.
- [ ] **4.10** [Scope, Hoisting & Closures](04-javascript-the-language/steps/4-10-scope-hoisting-closures.html) — Understand where variables live, and why a function can remember them forever.
- [ ] **4.11** [Control Flow & Loops](04-javascript-the-language/steps/4-11-control-flow-loops.html) — Cover the syntax differences from Python, plus the loop methods that avoid most manual loops.
- [ ] **4.12** [The DOM](04-javascript-the-language/steps/4-12-the-dom.html) — Read and change any page from JavaScript — the core skill of the whole front end.
- [ ] **4.13** [Events](04-javascript-the-language/steps/4-13-events.html) — Make the page respond — and understand bubbling, which explains 80% of event bugs.
- [ ] **4.14** [Modules & npm](04-javascript-the-language/steps/4-14-modules-npm.html) — Split code into files, import what you need, and understand what npm actually is.
- [ ] **4.15** [Errors: try / catch / throw](04-javascript-the-language/steps/4-15-errors-try-catch-throw.html) — Handle failure properly — and stop letting one bad response kill your whole app.
- [ ] **4.16** [Classes, Prototypes & <code>this</code>](04-javascript-the-language/steps/4-16-classes-prototypes-code-this-code.html) — Understand the object model underneath JavaScript's class syntax.
- [ ] **4.17** [The Event Loop](04-javascript-the-language/steps/4-17-the-event-loop.html) — Predict the exact order your code runs in — the skill that separates fluent JavaScript developers from confused ones.

## Act 5 — [Your Five Projects](05-your-five-projects/lesson.html)

*Everything so far, assembled. Each project is small on purpose — the goal is the pattern, not the pixels.*

- [ ] **5.1** [Project 1 — Background-Changing Button](05-your-five-projects/steps/5-1-project-1-background-changing-button.html) — The smallest complete interaction: find an element, listen, change it.
- [ ] **5.2** [Project 2 — Number Counter](05-your-five-projects/steps/5-2-project-2-number-counter.html) — Hold state in a variable, render it, and handle multiple inputs to the same state.
- [ ] **5.3** [Project 3 — Progress Bar](05-your-five-projects/steps/5-3-project-3-progress-bar.html) — Animate a value over time, and learn why you should animate with CSS transitions, not a tight loop.
- [ ] **5.4** [Project 4 — Dark Mode Toggle](05-your-five-projects/steps/5-4-project-4-dark-mode-toggle.html) — Combine CSS variables, a class on the root element, localStorage, and system preference detection.
- [ ] **5.5** [Project 5 — Show / Hide Sidebar](05-your-five-projects/steps/5-5-project-5-show-hide-sidebar.html) — The most common real UI pattern: a toggle that changes layout — and the accessibility details that make it good.

## Act 6 — [Advanced JavaScript](06-advanced-javascript/lesson.html)

*The patterns that separate 'I know the syntax' from 'I can build real things'.*

- [ ] **6.1** [Promises & async/await](06-advanced-javascript/steps/6-1-promises-async-await.html) — Understand asynchronous execution as a value you can wait on.
- [ ] **6.2** [Fetch & Rendering Data](06-advanced-javascript/steps/6-2-fetch-rendering-data.html) — Pull data from an API and render it — the shape of almost every real app.
- [ ] **6.3** [Forms, FormData & File Upload](06-advanced-javascript/steps/6-3-forms-formdata-file-upload.html) — Intercept a form, read its values, and send them — including files.
- [ ] **6.4** [Higher-Order Functions & Functional Patterns](06-advanced-javascript/steps/6-4-higher-order-functions-functional-patterns.html) — Write functions that take and return functions — and use closures for real.
- [ ] **6.5** [Debounce, Throttle & requestAnimationFrame](06-advanced-javascript/steps/6-5-debounce-throttle-requestanimationframe.html) — Keep the UI responsive when the user does things too fast.
- [ ] **6.6** [Web Workers](06-advanced-javascript/steps/6-6-web-workers.html) — Move CPU-heavy work off the main thread so the page never freezes.
- [ ] **6.7** [Performance & Best Practices](06-advanced-javascript/steps/6-7-performance-best-practices.html) — Know the handful of rules that cover most real-world performance wins.

## Act 7 — [Browser Architecture](07-browser-architecture/lesson.html)

*What the browser is actually doing, from the moment you hit Enter to the moment pixels appear.*

- [ ] **7.1** [From Bytes to a Render Tree](07-browser-architecture/steps/7-1-from-bytes-to-a-render-tree.html) — Understand the pipeline: HTML → DOM, CSS → CSSOM, DOM + CSSOM → Render Tree.
- [ ] **7.2** [Layout, Paint & Compositing](07-browser-architecture/steps/7-2-layout-paint-compositing.html) — Know the three rendering stages and which of your CSS choices make each one expensive.
- [ ] **7.3** [The Critical Rendering Path](07-browser-architecture/steps/7-3-the-critical-rendering-path.html) — Learn the checklist for making a page appear fast — the highest-leverage frontend skill.
- [ ] **7.4** [Rendering, Tasks & Responsiveness](07-browser-architecture/steps/7-4-rendering-tasks-responsiveness.html) — Connect the event loop to what the user actually sees, and understand INP.

## Act 8 — [Networking, Storage & Security](08-networking-storage-security/lesson.html)

*How the web talks to servers, where data lives, and how to not let someone else take over your app.*

- [ ] **8.1** [HTTP Fundamentals](08-networking-storage-security/steps/8-1-http-fundamentals.html) — Understand the request/response model well enough to debug any API problem.
- [ ] **8.2** [Client-Side Storage](08-networking-storage-security/steps/8-2-client-side-storage.html) — Choose the right storage mechanism for what you're building.
- [ ] **8.3** [CORS](08-networking-storage-security/steps/8-3-cors.html) — Understand why the browser blocks some requests, and how to fix it.
- [ ] **8.4** [XSS & Content Security Policy](08-networking-storage-security/steps/8-4-xss-content-security-policy.html) — Recognise the three kinds of cross-site scripting and defend against them.
- [ ] **8.5** [CSRF, SameSite & Tokens](08-networking-storage-security/steps/8-5-csrf-samesite-tokens.html) — Understand cross-site request forgery and how modern cookies mostly solve it.
- [ ] **8.6** [JWT & Sessions](08-networking-storage-security/steps/8-6-jwt-sessions.html) — Understand what a JWT is, what it is not, and where to store one safely.
- [ ] **8.7** [HTTP Caching](08-networking-storage-security/steps/8-7-http-caching.html) — Understand how browsers cache, and how to make your app load fast on a second visit.

## Act 9 — [Modern APIs](09-modern-apis/lesson.html)

*Streaming responses, server-sent events, service workers and real-time communication.*

- [ ] **9.1** [Streaming Responses](09-modern-apis/steps/9-1-streaming-responses.html) — Read a response as it arrives, and render it live — the technique behind every AI chat UI.
- [ ] **9.2** [Server-Sent Events (SSE)](09-modern-apis/steps/9-2-server-sent-events-sse.html) — Receive server-pushed updates over one long-lived HTTP connection.
- [ ] **9.3** [Service Workers & PWAs](09-modern-apis/steps/9-3-service-workers-pwas.html) — Understand the proxy between your app and the network, and what it unlocks.
- [ ] **9.4** [WebSockets](09-modern-apis/steps/9-4-websockets.html) — Know when you need full-duplex communication, and the shape of the API.

## Act 10 — [A Backend Touchpoint](10-a-backend-touchpoint/lesson.html)

*Enough Node to make the front end make sense: webhooks, sessions, and CORS you control.*

- [ ] **10.1** [Node.js in 45 Minutes](10-a-backend-touchpoint/steps/10-1-node-js-in-45-minutes.html) — Understand the runtime, the event loop, and enough Express to serve an API.
- [ ] **10.2** [CORS, Env Vars & Serving a Front End](10-a-backend-touchpoint/steps/10-2-cors-env-vars-serving-a-front-end.html) — Configure the things the browser insists on: CORS headers, environment variables, and static hosting.
- [ ] **10.3** [Webhooks, End to End](10-a-backend-touchpoint/steps/10-3-webhooks-end-to-end.html) — See how a server receives a third-party event and pushes it to a browser.

## Act 11 — [The Framework Bridge](11-the-framework-bridge/lesson.html)

*Everything you learned, mapped onto React, Next.js and shadcn — so tomorrow is recognition, not learning.*

- [ ] **11.1** [How React Maps Onto What You Know](11-the-framework-bridge/steps/11-1-how-react-maps-onto-what-you-know.html) — See React as a set of conventions on top of the DOM, not a new paradigm.
- [ ] **11.2** [Components, Props & State](11-the-framework-bridge/steps/11-2-components-props-state.html) — Learn React's three core ideas, and the rules that govern them.
- [ ] **11.3** [Effects & Data Fetching](11-the-framework-bridge/steps/11-3-effects-data-fetching.html) — Understand useEffect — the hook people misuse most — and the modern data-fetching alternative.
- [ ] **11.4** [Next.js & shadcn](11-the-framework-bridge/steps/11-4-next-js-shadcn.html) — See the structure of a modern Next.js app with shadcn/ui, and how it uses everything you know.

---

## Extra files

- `00-setup-orientation/orientation.html` — the 5-minute setup checklist
- `10-a-backend-touchpoint/` — a real Node/Express server (`npm install && npm start`)
- `10-a-backend-touchpoint/public/` — the live demo page (REST + SSE + webhooks + worker)
- `11-the-framework-bridge/react-mini/` — a React app with **no build step**

## Progress log

- 2026-10-22 — Course created. Act 1 Step 1 delivered.
- 2026-10-22 — Full curriculum built: all 12 acts, all steps, all runnable files.
