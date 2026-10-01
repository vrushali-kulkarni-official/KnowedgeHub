Given your background, I've designed this as **~100 micro-modules** — each one is sized to be a *single AI teaching session* (the AI can go deep on every sub-topic without summarizing). Each module lists the exact topics to demand, so paste the module text directly into your teaching AI.

---

## How to use this curriculum

**Version policy (tell every teaching AI this):**
> "Teach using current stable versions: React 19, Next.js 15+, Tailwind CSS v4, TypeScript 5.x, React Query v5, zod. Many tutorials online use older versions (Pages Router, Tailwind v3, React Query v4) — flag differences when they appear."

**Prompt template for each module:**
> "You are my frontend instructor. I'm an experienced Python backend dev (FastAPI, Pydantic, async, Docker, Keycloak) new to frontend. Teach me the module below topic-by-topic in order. For each topic: explain the concept, show runnable code, show at least one common mistake/gotcha, and relate it to Python/backend concepts where possible. End with 3 exercises with solutions. Do NOT summarize — go deep on every bullet. Module: [paste module]"

**Structure:** 9 parts → ~100 modules. Order matters within parts 1–5. Parts 6–8 assume everything before.

---

## PART 0 — The Frontend Landscape & Tooling (4 modules)

**0.1 — How the frontend world actually works** *(build the mental model before syntax)*
- How a browser renders: HTML → DOM tree, CSS → CSSOM, layout/paint/composite
- Role of each piece you'll learn: JS (logic), TS (types), React (UI components), Next.js (framework/SSR), Tailwind (styling), shadcn/ui (components)
- Translation table from your stack: `package.json` ≈ `pyproject.toml`, pnpm ≈ uv, `node_modules` ≈ `.venv`, npm scripts ≈ task runner, `tsconfig.json` ≈ settings
- Node.js vs browser: two different runtimes; Node exists for tooling/builds, browser runs your app
- SPA vs MPA vs SSR vs streaming rendering (concepts only, deep detail in Next part)
- What a bundler/dev server is (Vite, Turbopack), HMR, sourcemaps, tree-shaking, minification
- What "the build step" means and why frontend code is compiled at all

**0.2 — Development environment setup**
- Installing Node.js LTS via a version manager (fnm or nvm); verifying `node -v`, `npm -v`
- pnpm: why (speed, disk, strictness); installing via corepack; pnpm vs npm vs yarn vs bun
- VS Code setup: ESLint, Prettier, Tailwind CSS IntelliSense, Error Lens, TypeScript Vue/JS plugins
- Browser extensions: React Developer Tools; tour of Chrome DevTools (Elements, Console, Network, Sources)
- npx / `pnpm dlx` for one-off commands
- WSL2 vs native (if on Windows); `.gitignore` for Node projects
- First check: run a dev server and edit a file to see HMR

**0.3 — package.json, pnpm & the dependency ecosystem**
- `package.json` anatomy: name, scripts, dependencies, devDependencies, engines, `"type": "module"`
- Semantic versioning: `^` vs `~`, why the lockfile (`pnpm-lock.yaml`) must be committed
- `pnpm add`, `add -D`, `remove`, `install --frozen-lockfile`; how `node_modules` + pnpm's symlink store work
- Peer dependencies: what they are, what those React warnings mean
- npm scripts conventions: `dev`, `build`, `lint`, `typecheck`; pre/post hooks
- Security: `pnpm audit`, overrides; Renovate/Dependabot awareness
- The config-file landscape of a frontend repo (tsconfig, eslint, prettier, vite/next config)

**0.4 — Modules, ESLint & Prettier**
- ESM (`import`/`export`) vs CommonJS (`require`) — why both exist, which you'll use
- Path aliases (`@/` → `src/`) setup in tsconfig + bundler config
- ESLint 9 flat config: what it catches; `typescript-eslint`; the `react-hooks` rules (these will save you)
- Prettier vs ESLint (formatting vs correctness), format-on-save setup
- `.env` files: Vite's `VITE_` prefix / `import.meta.env` vs Next's `NEXT_PUBLIC_` — build-time vs runtime (a critical distinction you'll hit in Docker later)

---

## PART 1 — Modern JavaScript (15 modules)

*Reference: MDN + javascript.info. You can speedrun 1.1–1.2 (1 session), but do NOT skip the rest — JS-specific behavior (closures, the event loop, references, async) is where backend devs get burned.*

**1.1 — Values, variables & types (experienced-dev refresher)**
- `let`/`const`/`var`, block scope, hoisting, temporal dead zone
- Primitives vs objects; `typeof` quirks (`typeof null === "object"`)
- `===` vs `==`; implicit coercion gotchas; truthiness table
- Template literals, multiline strings
- Numbers: floating point (`0.1+0.2`), `NaN`, `Number()` vs `parseInt`, `toFixed`, BigInt
- String methods: `includes`, `slice`, `replace`, `replaceAll`, `split`, `padStart`, `at`
- `null` vs `undefined`; nullish coalescing `??`; optional chaining `?.`
- Map to Python: no int/float split, dynamic typing, `undefined` has no Python equivalent

**1.2 — Control flow & operators (quick pass)**
- if/else/switch, early-return style
- Loops: `for`, `while`, `do...while`, and critically `for...of` vs `for...in`
- `break`/`continue`; labeled loops (read-only awareness)
- Logical operators `&&`/`||` returning values (not booleans!) — and how this enables JSX patterns
- Logical assignment operators `||=` `&&=` `??=`

**1.3 — Functions & closures (the most important JS module)**
- Declarations vs expressions vs arrow functions; what arrows don't have (`this`, `arguments`)
- Default params, rest params
- First-class functions, passing callbacks
- **Closures in depth**: definition, counters, memoization, `once`, why React hooks depend on them
- `this` and its 4 binding rules; `call`/`apply`/`bind`; why arrows fixed everything
- Pure vs impure functions, side effects — vocabulary you need for React
- IIFEs (legacy, for reading old code)

**1.4 — Objects in depth & reference semantics**
- Literal syntax, computed keys, method shorthand
- Dot vs bracket access; dynamic keys
- `Object.keys/values/entries/assign/fromEntries/hasOwn/freeze`
- **References vs values**: assignment copies references; the shared-mutation bug class
- Shallow copy (spread) vs deep copy (`structuredClone`); JSON round-trip limits
- `JSON.stringify/parse`: replacer/reviver, what gets lost (undefined, functions, Map/Set), circular errors
- `Symbol` keys (awareness)

**1.5 — Arrays deep dive**
- Mutators vs non-mutators — **the critical distinction**: `push/pop/splice/sort/reverse` mutate vs `map/filter/concat/slice` and ES2023 `toSorted/toReversed/toSpliced/with`
- `forEach`, `map`, `filter`, `find`, `findIndex`, `findLast`, `some`, `every`, `flat`, `flatMap`
- `reduce` properly: accumulator, seed, when to avoid it
- `sort` with comparators (the numeric sort gotcha), `localeCompare`
- `includes`, `indexOf`, `at`, `Array.from`, `Array.isArray`
- Array destructuring, skipping elements, rest elements
- Everyday patterns: array-of-objects from APIs, grouping, counting

**1.6 — Map, Set, Date & RegExp**
- `Set`: add/has/delete, dedupe pattern, set operations
- `Map`: any keys, insertion order, size, iteration; when Map beats object
- `WeakMap`/`WeakSet` use cases (caching, metadata)
- `Date`: UTC vs local, `toISOString`, timestamps; formatting with `Intl.DateTimeFormat` (never hand-roll dates)
- `RegExp` fundamentals: `test`, `match`, `replace`, capture groups, flags — enough to read validation code
- `Intl` number/currency formatting

**1.7 — Destructuring, spread & immutable update patterns**
- Object destructuring: rename, defaults, nested
- Destructuring function params (this is how every React component reads props)
- Spread for objects/arrays/functions; merge order matters
- Rest-in-destructuring (omit-key pattern)
- **Immutable update recipes you'll use daily in React**: update nested field, add/remove/replace array item, toggle, upsert — drill these until automatic
- `structuredClone`, frozen objects, immutability mindset

**1.8 — Classes, prototypes & iterators**
- Class syntax: fields, methods, static, getters/setters, `#private`
- `constructor`, `new`, `extends`/`super`, `instanceof`
- Prototype chain (conceptual — you need it to read stack traces)
- Map to Python: `__init__` vs constructor, `self` vs `this`, no multiple inheritance
- When a class is overkill: factory functions + closures
- Iterators & generators: `Symbol.iterator`, `for...of`, `function*`, `yield` — needed to understand streaming later

**1.9 — Errors & exceptions**
- `throw` accepts anything (but always throw `Error`); `message`/`name`/`stack`/`cause`
- try/catch/finally semantics
- Custom error classes, `instanceof` checks, wrapping/rethrowing
- Browser hooks: `window.onerror`, `unhandledrejection`
- Designing error shapes that survive an API boundary (maps to FastAPI's `{"detail": ...}`)
- Never swallow errors; logging etiquette

**1.10 — ES Modules in practice**
- Named vs default exports; why defaults hurt tooling; mixing
- Import forms: named, default, namespace, side-effect-only
- Re-exports, barrels (`index.ts`) pros/cons
- Dynamic `import()` → returns a promise; code splitting preview
- Module resolution: relative, node_modules, extension rules, aliases
- Circular imports pitfall

**1.11 — The event loop & timers**
- Single thread; call stack; Web APIs; task (macrotask) vs **microtask** queues
- `setTimeout`/`setInterval`/`clearInterval`; `setTimeout(fn, 0)`
- `queueMicrotask`; render timing, `requestAnimationFrame`
- Predict-the-output exercises (this module should be heavy on drills)
- Long tasks block the UI — jank, and why this matters for streaming token display later
- Concurrency ≠ parallelism; Web Workers (awareness)

**1.12 — Promises, AbortController & async iterators**
- Why promises exist (callback hell, inversion of control)
- Creating/resolving/rejecting; the executor runs synchronously
- `then`/`catch`/`finally`; chaining; values flow down the chain
- Combinators: `all`, `allSettled`, `race`, `any` — differences and use cases
- Unhandled rejections
- **AbortController/AbortSignal**: aborting, listening, `AbortSignal.timeout()` — you will use this for canceling LLM generations
- `for await...of` and async generators — the exact mechanism behind consuming streaming APIs

**1.13 — async/await & fetch in depth**
- `async` functions always return promises; `await` semantics
- try/catch around await; **sequential vs parallel awaits** (the classic mistake)
- `await` inside loops: `for...of` yes, `forEach` no
- `fetch`: method, headers, JSON body, `FormData`, `URLSearchParams`
- Response: `ok`, `status`, `json()`, `text()` — **fetch does NOT reject on 404/500**
- Timeout pattern with AbortController
- Credentials/cookies options; CORS from the client's view: preflight, reading errors
- **Streaming a response**: `response.body` (ReadableStream), `getReader()`, `TextDecoder` — foundation of LLM streaming; SSE wire format (`data:` lines) preview

**1.14 — DOM manipulation & events (yes, even for React devs)**
- Document tree; `querySelector(All)`, `getElementById`, `closest`, `matches`
- Creating/inserting/removing nodes; `textContent` vs `innerHTML` (XSS!)
- `classList`, `style`, `dataset`, `getBoundingClientRect`
- Events: `addEventListener`, event object, `target` vs `currentTarget`
- Bubbling/capturing, `stopPropagation`, `preventDefault`, delegation pattern
- Forms: submit event, `FormData`, native validation (`checkValidity`)
- Script loading: `defer`, `async`, `DOMContentLoaded`
- Which 10% of this React replaces — and which 10% you still need daily

**1.15 — Browser storage, cookies & survival-kit APIs**
- localStorage/sessionStorage: JSON serialization, size limits, sync blocking
- Cookies: attributes (`Expires`, `Secure`, `HttpOnly`, `SameSite`, `Path`) — and that **`HttpOnly` cookies are invisible to JS** (central to your auth design)
- `navigator.clipboard`, `navigator.onLine`
- `window.location` anatomy; `URL`/`URLSearchParams` parsing
- `history.pushState` (how SPA routing works under the hood)
- `visibilitychange`, `resize`; `ResizeObserver`/`IntersectionObserver` (what UI libraries use)
- `WebSocket` & `EventSource` APIs overview
- **Milestone project**: vanilla JS app — notes app with localStorage + fetch a public JSON API + render/filter list. ~2 days.

---

## PART 2 — TypeScript (10 modules)

*You know Pydantic — you'll move fast here. The single most important lesson of the whole part: **TS types are erased at runtime; they validate nothing.** Runtime validation = zod (module 2.9).*

**2.1 — TS orientation, setup & mental model**
- Compile-to-JS; types erased at runtime; typecheck ≠ runtime validation
- Where TS runs in the toolchain: editor, `tsc --noEmit`, and the fact that Vite/Next transpile without checking (CI must typecheck)
- tsconfig core options: `strict`, `target`, `moduleResolution: "bundler"`, `jsx`, `paths`, `noEmit`
- The react-ts Vite template; `tsc` watch mode
- Reading TS error messages (long generic chains — a learned skill)

**2.2 — Annotations, inference & the type landscape**
- Primitives, arrays, objects, functions; return types; `void`
- Inference rules; when to annotate (public API) vs infer (locals)
- `any` (escape hatch, avoid), `unknown` (safe), `never`
- Type aliases vs interfaces — when each
- Literal unions (`"pending" | "done"`); optional `?`, `readonly`
- Tuples, `as const`, `satisfies` (modern best-practice operator)
- Assertions (`as`), non-null `!` — when legitimate vs smell

**2.3 — Narrowing & control-flow analysis (TS's superpower)**
- `typeof`, truthiness, equality narrowing
- `in`, `instanceof`
- **Discriminated unions** (tag fields) — directly analogous to Pydantic tagged unions; exhaustiveness via `never`
- Type predicates (`x is T`), assertion functions
- End-to-end pattern for `unknown` (e.g., handling `JSON.parse`)
- Exercise: model API errors as `{kind: "network"|"http"|"validation"}` and narrow correctly

**2.4 — Interfaces, type operators & modeling real data**
- `extends`, `implements`, declaration merging
- Index signatures vs `Record` vs mapped types
- `keyof`, `typeof` (from a value), indexed access `T["key"]`
- Recursive/JSON-like types
- Modeling: pagination envelope, list responses, entity relations — your FastAPI response shapes

**2.5 — Generics**
- Generic functions/types; inference from arguments
- Constraints (`extends`), defaults, multiple params
- Build for real: `Result<T, E>`, typed event emitter map, typed fetch wrapper
- Where generics appear in React (`useState<FormState>`)
- Judgment: when a union beats a generic

**2.6 — Utility & mapped types**
- The full toolbox: `Partial`, `Required`, `Readonly`, `Pick`, `Omit`, `Record`, `Exclude`, `Extract`, `NonNullable`, `ReturnType`, `Parameters`, `Awaited`
- `keyof` + mapped types `{ [K in keyof T]: ... }`; modifiers; key remapping `as`
- Template literal types (`` `${string}-${number}` ``)
- Exercise: reimplement `Pick` and `Omit` from scratch

**2.7 — Conditional types & infer (advanced, capped)**
- `T extends U ? X : Y`; distributivity and how to suppress it
- `infer` in conditional positions
- Reading the source of built-ins (`Awaited`, `ReturnType`)
- Complexity budget: when advanced types hurt the team (and your AI agents)

**2.8 — Config, declarations & project conventions**
- `@types/*`, `.d.ts` files, `declare module` for untyped deps
- `import type` / `verbatimModuleSyntax`
- Extra strictness worth enabling: `noUncheckedIndexedAccess`
- Enums and why the community avoids them: const objects + `as const` + union literals
- Colocating types vs `types.ts`; barrel files
- Organizing shared types across frontend/backend (preview: OpenAPI generation in 5.13)

**2.9 — zod (your Pydantic for the frontend)**
- Why: validate at boundaries — API responses, form inputs, env vars, localStorage
- Schema basics: string/number/boolean/object/array/enum/literal/union/optional/nullable/record/tuple
- `z.infer<T>` — one source of truth for type + validation
- `parse` vs `safeParse`; `.issues` error handling
- Refinements, transforms, `coerce`, defaults, discriminated unions, `z.lazy` recursion
- `.extend/.pick/.omit/.partial` composition
- Pydantic → zod vocabulary mapping (Field≈describe, validators≈refine)
- **Milestone project**: typed API client for a public API — zod-validated fetch wrapper returning `data | ApiError`.

**2.10 — Generating TS types from your FastAPI backend**
- `openapi-typescript` against FastAPI's `/openapi.json` — free end-to-end types
- Alternative: `orval` (generates React Query hooks + zod schemas)
- Script + CI regeneration workflow; drift detection
- What generated types don't give you (runtime validation — still zod at edges)

---

## PART 3 — CSS Foundations + Tailwind (10 modules)

*You know "a bit" of CSS — that's not enough for Tailwind competence (Tailwind is CSS knowledge expressed as class names). This part is deliberately thorough but moves fast.*

**3.1 — Semantic HTML essentials**
- Document anatomy; head/meta/viewport
- Semantic sections (`header/nav/main/section/article/aside/footer`); heading hierarchy
- Links, images (alt, `loading`, width/height)
- **Form markup**: input types, `label[for]`, select, textarea, checkbox/radio, button types, `fieldset`, `autocomplete`, native validation attributes
- `data-*` attributes; div/span when and why
- Semantics → free accessibility (tab order, focus, screen readers)
- View-source habit; what valid HTML looks like

**3.2 — CSS core mechanics**
- Selectors: type/class/id/attribute/combinators (` `, `>`, `+`, `~`)/pseudo-classes/pseudo-elements
- Specificity, the cascade, inheritance; `!important` (avoid)
- **Box model**: content/padding/border/margin; `box-sizing: border-box` and why everyone sets it
- display: block/inline/inline-block/flex/grid/none
- Units: px/rem/em/%/vw/vh/dvh; `clamp()`/`min()`/`max()`
- Colors: hex/rgb/hsl/oklch
- Fonts: family stacks, size, weight, line-height
- CSS variables (`--var`, `var()` with fallbacks, `:root`)
- DevTools: inspect, computed, box model overlay, force states

**3.3 — Flexbox mastery**
- Container: `flex-direction`, `flex-wrap`, `justify-content`, `align-items`, `gap`
- Items: `flex-grow/shrink/basis`, `flex: 1`, `align-self`, `order`
- The `min-width: 0` overflow classic bug
- Recipes: perfect centering, navbar, sidebar+content, card rows, input+button row
- Debugging flex layouts

**3.4 — CSS Grid mastery**
- `grid-template-columns/rows`, `fr`, `repeat()`, `auto-fill/auto-fit` + `minmax()` (responsive cards without media queries)
- Line placement, `span`, `grid-template-areas`
- `gap`, alignment
- Grid vs flex: the decision table
- Recipes: app shell (sidebar/header/main), dashboard, form grid

**3.5 — Positioning, stacking & overflow**
- relative/absolute pairs, containing block; fixed vs sticky (and sticky-in-overflow gotcha)
- `z-index` and stacking contexts
- `overflow` options; `overscroll-behavior`; scroll snapping; `scroll-margin`
- Every centering technique, ranked
- Why real products use floating-ui for popovers (you'll get it for free via shadcn)

**3.6 — Responsive design**
- Viewport meta; media queries; mobile-first thinking
- Breakpoints; container queries (modern `@container`)
- Fluid sizing (`clamp`), `aspect-ratio`, `object-fit`; `srcset` concept
- Touch targets, safe-area insets
- Recipes: stacked→sidebar at `lg:`, grid re-flow, hide/show
- Testing: DevTools emulation + real devices over LAN (you self-host — this is easy for you)

**3.7 — Transitions, motion & state styling**
- `transition` (property/duration/easing); animate transform/opacity (cheap) vs layout props (expensive)
- `transform`: translate/scale/rotate
- `@keyframes`; `prefers-reduced-motion` respect
- `:hover`, **`:focus-visible`**, `:active`, `:disabled` — the states every button needs
- Dark mode via `prefers-color-scheme` + class-toggle pattern with CSS variables
- `backdrop-filter` (the modern blur staple), skeleton-shimmer recipe
- `:has()` and native nesting (modern CSS you'll meet in Tailwind output)

**3.8 — Tailwind CSS: philosophy, setup & core utilities**
- Utility-first: what it is, honest pros/cons; when you still write CSS
- **v4 vs v3 awareness**: v4 is CSS-first (`@import "tailwindcss"`, `@theme`, the `@tailwindcss/vite` plugin, no `tailwind.config.js` by default); most tutorials online are v3 — learn to translate
- Setup in both Vite and Next
- Core utilities: display, position, flex/grid, spacing scale (p/m/gap), sizing (w/h/min/max)
- Typography (`text-*`, `font-*`, `leading`, `tracking`), color scales (50–950), opacity modifiers
- borders, `rounded`, `shadow`, `ring`, `divide`
- Editor: Tailwind IntelliSense; reading what a class generates

**3.9 — Tailwind: variants, responsive & state**
- Responsive prefixes `sm:/md:/lg:` (mobile-first semantics!)
- State variants: `hover:`, `focus:`, `focus-visible:`, `active:`, `disabled:`, `checked:`
- `dark:` and dark-mode strategy setup
- `group`/`group-hover`, `peer`/`peer-checked`
- Arbitrary values `w-[17px]`; arbitrary variants `[&[data-state=open]]`
- Transition/animation utilities; `truncate`, `line-clamp`; `aspect-*`, `object-cover`, `sr-only`
- Container query variants (`@container`, `@sm:`)

**3.10 — Tailwind: theming & the `cn()` pattern (shadcn groundwork)**
- `@theme`: custom colors (oklch), fonts, radii; CSS-variable-driven theming
- **The shadcn variable pattern**: `--background/--foreground/--primary/...` semantic vars remapped under `.dark` — understand this deeply now, shadcn will make sense instantly
- The class-conflict problem → `tailwind-merge`; conditionals → `clsx`; build `cn()` = `twMerge(clsx(...))`
- Custom utilities with `@utility`; when `@apply` is acceptable
- Extracting repeated utilities into components (components, not CSS abstractions)
- **Milestone**: rebuild a real dashboard screenshot pixel-close from scratch, no framework.

---

## PART 4 — React (24 modules)

*Reference: react.dev/learn (current, excellent). Do parts 4.1–4.9 before anything ambitious — the render/mental model modules are where 90% of bugs originate.*

**4.1 — React mental model & ecosystem**
- What React is/isn't (library, not framework); declarative: UI = f(state)
- Component tree, unidirectional data flow
- Render → reconcile → commit; why React exists
- SPA model: one HTML file, JS renders the DOM
- Why React for your product: shadcn, TanStack Query/Table, AI-chat libraries are React-first
- "Thinking in components": decompose a screenshot into a component tree
- Ignore class-component-era material entirely

**4.2 — Project setup with Vite**
- `pnpm create vite` (react-ts); template anatomy (`main.tsx`, `App.tsx`, `index.css`, configs)
- Dev server, HMR, build, preview
- ESLint (flat config) with react-hooks rules; Prettier
- React DevTools: component tree, props, state, highlight re-renders
- Folder conventions: `components/`, `hooks/`, `lib/`, `types/`

**4.3 — JSX rules & expressions**
- JSX compiles to function calls (not HTML, not templates)
- One root, fragments `<></>`; `className`, `htmlFor`, `colSpan`; `style={{}}` object
- Embedding expressions; the `0 && <X/>` trap; `||` vs `??` in JSX
- Conditional patterns: ternary, early return, variables
- **Lists & keys**: why keys, stable IDs, why index keys corrupt state
- Spreading props; `dangerouslySetInnerHTML` (danger — sanitization comes in 7.2)

**4.4 — Components, props & composition**
- Function components; capitalization rule
- Props: read-only; destructured params; TS prop types
- `children`; passing JSX/components as props; slot props (`sidebar={<X/>}`)
- Composition over prop-explosion
- File-per-component; prop drilling — spot it now, fix in 4.11

**4.5 — State with useState**
- State = memory between renders; `useState`; lazy initialization
- Typed state; union states
- setState triggers re-render; batching
- **State snapshots**: reading state in a closure gives the render's value (root of all stale bugs)
- Updater form `setX(prev => …)` and when it's mandatory
- Immutable update recipes from 1.7 applied live
- Derived data: compute in render, never store
- Lifting state; state-ownership decision tree

**4.6 — Events & controlled forms**
- Synthetic events; typing (`React.ChangeEvent`, `React.FormEvent`, `React.MouseEvent`)
- Controlled inputs for every type: text, number, checkbox, radio, select, textarea, file
- Build a full form: fields, validation, errors, submit, disabled-while-submitting
- `FormData` uncontrolled alternative and when it's simpler
- Focus/UX details; Enter-to-submit

**4.7 — Rendering behavior: re-renders, snapshots & keys**
- Render phase vs commit phase
- What triggers a re-render: own state, parent re-render, context
- Children re-render when parent does (even with "unchanged" props)
- Stale closures in event handlers — cause and three fixes
- Keys and reconciliation: state following elements when lists reorder
- Profiler in DevTools; why premature optimization is wasted here
- StrictMode double-render: what and why

**4.8 — useEffect I: effects & cleanup**
- Effects = escape hatch to the outside world, NOT lifecycle
- The dependency array's exact meaning ("re-run if changed by Object.is")
- Cleanup function: runs before re-run and on unmount
- eslint `exhaustive-deps` — trust it
- Use cases: subscriptions, timers, DOM listeners
- StrictMode double-invocation of effects: design idempotent effects
- Common mistakes: setState loops, effects for derived data

**4.9 — useEffect II: data fetching & async pitfalls**
- The loading/error/success pattern with a discriminated-union status
- **Race conditions**: fast typing → stale response wins; fix with cleanup flag / AbortController
- Dependent fetching (params in deps); refetch on change
- Why libraries exist: caching, dedupe, retry (React Query motivation)
- Mini-app: debounced search + list + detail

**4.10 — useRef & imperative DOM**
- Ref = mutable, render-persistent, invisible to renders
- Use cases: focus, scroll, measure, latest-value, holding AbortControllers, render counting
- `useRef<T | null>(null)` + null-check; callback refs
- React 19: `ref` as a normal prop; legacy `forwardRef` (shadcn internals still show it)
- `useImperativeHandle` (awareness)
- ref vs state decision table

**4.11 — Context API**
- Prop drilling → context; the costs
- `createContext`, provider, `useContext`; typing and undefined-handling patterns
- **The memoized value requirement**: new object every render re-renders all consumers
- Splitting state/dispatch into two contexts
- Good fits: theme, current user, locale. Bad fits: high-frequency data
- React 19 `<Context>` shorthand

**4.12 — useReducer & state machines**
- Reducer pattern: `(state, action) => state`; dispatch; discriminated-union actions
- Purity, exhaustiveness with `never`
- useReducer vs several useStates — heuristics
- Context + reducer = a mini store (build one)
- Formal state-machine thinking (great for agent-run states: queued/running/awaiting-input/failed/done)

**4.13 — Custom hooks**
- Rules of hooks and *why* (call order)
- Extracting state+effects+handlers into a hook; return API design
- Build the library: `useToggle`, `useDebouncedValue`, `useLocalStorage`, `useMediaQuery`, `useOnClickOutside`, `useInterval`, `usePrevious`, a typed `useFetch` with abort
- Typing hooks; generics in hooks
- Reading OSS hooks source (react-use, ahooks) as study material

**4.14 — Talking to your FastAPI backend**
- Architecture decision: browser → FastAPI directly vs via a Next proxy (CORS + auth implications of each)
- CORS end-to-end: simple vs preflighted requests, credentials, the exact `CORSMiddleware` config FastAPI needs
- Typed fetch wrapper: generics, JSON, `ApiError` class carrying status/detail
- Timeout with `AbortSignal.timeout`
- File upload/download; bearer-token patterns
- **First streaming lab**: consume a FastAPI `StreamingResponse` (SSE lines) with `fetch` + ReadableStream and render it live
- `openapi-typescript` types from 2.10 in daily use

**4.15 — TanStack Query I: queries**
- What it replaces from 4.9: cache, dedupe, staleness, background refetch, retries
- QueryClient + Provider; DevTools
- `useQuery`: `queryKey` semantics (arrays, serialization), `queryFn`, `staleTime`, `gcTime`, `refetchOnWindowFocus`
- `isPending/isError/data`; `placeholderData` for pagination
- Dependent queries (`enabled`)
- Invalidation: `queryClient.invalidateQueries`
- Query-key factory convention

**4.16 — TanStack Query II: mutations & optimistic updates**
- `useMutation`: `mutationFn`, `onSuccess/onError`, invalidation after mutation
- **Optimistic updates with rollback** — the chat-sent-message UX, in detail
- `useInfiniteQuery` (message history, infinite scroll)
- Prefetching on hover
- Next.js integration preview (hydration in 5.x)
- Full conversation-CRUD lab against FastAPI

**4.17 — react-hook-form I**
- Uncontrolled performance model; `register`
- `handleSubmit`; form state: `isSubmitting`, `isDirty`, `errors`
- `zodResolver` + `z.infer` — schema is the single source of truth
- `Controller` for custom components (needed for shadcn inputs)
- `reset`, `setValue`, `watch` vs `useWatch` (perf)

**4.18 — react-hook-form II: real-world forms**
- Complete form: zod schema → fields → FastAPI submit → map 422 errors back with `setError`
- `useFieldArray` (dynamic rows)
- Multi-step wizards; dirty-check leave confirmation
- `FormProvider` for deep trees
- A11y wiring: `aria-invalid`, `aria-describedby` (shadcn's Form does this — understand it)

**4.19 — Component patterns & variant styling (read shadcn's source code)**
- `class-variance-authority` (cva): variants, compound variants, defaults
- `Slot` / `asChild` (how Radix merges props)
- Build your own Button/Alert/Modal with: cva + `cn()` + ref forwarding + `className` merge — the exact anatomy of every shadcn component
- Controlled/uncontrolled dual API pattern (`value`/`defaultValue`)
- Compound components; escape-hatch props (`...props`)

**4.20 — Performance & code splitting**
- Measure first: Profiler, re-render highlighting
- `React.memo`, `useMemo`, `useCallback` — referential equality, when they help, when they're noise
- The children-as-JSX trick to skip re-renders
- **Virtualization**: react-virtuoso/react-window — build a 10,000-message list (your chat history)
- `React.lazy` + `Suspense`
- `useTransition`/`useDeferredValue` for type-as-you-search UX
- Bundle analysis; swapping heavy deps (moment → date-fns)

**4.21 — Error boundaries, Suspense & React 19 APIs**
- Error boundaries (class API + `react-error-boundary` lib): fallbacks, reset, placement per feature
- Suspense for lazy components
- React 19 in practice: `useActionState` (with server actions), `useOptimistic` (perfect for chat), `use()`, ref-as-prop, Context shorthand
- React Compiler awareness (auto-memoization — changes the perf habits debate)

**4.22 — Client-side routing with React Router 7** *(short, concept-focused — a stepping stone to Next's router)*
- History API + URL-as-state; nested layout routes, `<Outlet>`
- Dynamic params; search params as state
- Client-side route guards
- Do one small lab; then understand what Next moves server-side

**4.23 — Client state management with Zustand**
- State taxonomy: server state (React Query owns it) vs UI state
- `create`, actions, selectors, `shallow` to prevent extra re-renders
- `persist` middleware (localStorage, `partialize`)
- **Transient updates** (`subscribe`) for high-frequency data — the streaming-tokens technique
- Devtools middleware; slice pattern
- Build: harness UI store (sidebar open, modals, draft text)

**4.24 — Testing React with Vitest + Testing Library**
- Test behavior, not implementation
- Setup (jsdom); queries by role/label; `findBy` for async
- `userEvent` realistic interactions
- Test: state changes, forms, custom hooks (`renderHook`)
- **MSW** to mock your FastAPI at the network level — deterministic, realistic tests
- What not to test; CI integration
- **Milestone**: full mini-dashboard against your FastAPI — React Query, RHF+zod form, Zustand, tests. This is the app you'll port to Next.

---

## PART 5 — Next.js App Router (18 modules)

*Reference: nextjs.org docs (App Router sections only). Tell the teaching AI: "App Router, current version, flag anything that changed in Next 15 (async request APIs, fetch not cached by default)."*

**5.1 — Why Next.js & how it works**
- What Next adds over a Vite SPA: SSR/SSG/ISR/streaming, file routing, server-first architecture
- App Router vs legacy Pages Router (recognize it in old tutorials — half the internet's answers are Pages Router)
- The RSC model at 10,000 feet: server components render, a payload streams, client components hydrate
- Project tour: `app/`, `public/`, `next.config.ts`, `middleware.ts`
- Where Next fits your architecture: frontend + optional BFF in front of FastAPI

**5.2 — File-based routing & layouts**
- `page.tsx`, `layout.tsx` (nesting, persistence across navigation), root layout (html/body)
- `loading.tsx`, `error.tsx`, `not-found.tsx`
- Route groups `(marketing)`; private folders `_lib`; colocation rules
- Dynamic segments `[id]`, catch-all `[...slug]`
- `generateStaticParams`; `Link` and prefetching; `redirect()`, `notFound()`
- Metadata export, favicon, robots

**5.3 — Server vs Client components (the core mental model — spend extra time)**
- `'use client'` is a **boundary**, not "SSR off": client components still SSR then hydrate
- What server components can do (async, secrets, direct data) and can't (no hooks/state/events/browser APIs)
- What client components do and can't import (no server-only code)
- **Serialization rules** for props crossing the boundary
- The children pattern: server layout renders client islands
- Split by interactivity, not by page
- Decoding the classic error: "useState in a server component"

**5.4 — Data fetching on the server**
- Async components + `await`; waterfalls and `Promise.all`
- `fetch` with `revalidate`/`no-store`; Next 15's defaults
- Calling FastAPI server-to-server: internal Docker URL, **no CORS involved** — this will delight you
- `server-only` package; `process.env` vs `NEXT_PUBLIC_`
- Wrapping data components in Suspense for streamed sections
- try/catch + `error.tsx`; `notFound()`
- When to fetch client-side instead (authed/interactive/live data)

**5.5 — Caching & revalidation (App Router)**
- The four caches: request memoization, Data Cache, Full Route Cache, Router Cache
- Static vs dynamic detection (dynamic APIs opt in)
- `revalidateTag` / `revalidatePath`; `router.refresh()`
- Reading build output symbols (static/dynamic markers)
- Practical stance for an auth-gated dashboard: mostly dynamic; how to verify

**5.6 — Client components in practice**
- Interactive leaves: filter bars, chat composer
- URL as state: `useSearchParams` + `router.replace` (shareable filter URLs)
- **Hydration mismatch errors**: causes (window access, `Date.now()` in render, invalid nesting) and debugging drill
- Pushing the `'use client'` boundary down; context providers in a client shell inside root layout

**5.7 — Route Handlers (your BFF layer)**
- `route.ts`, method exports; request/params/body parsing
- Returning JSON, headers, cookies
- **Streaming a `Response` with ReadableStream** — the LLM-proxy pattern: browser → route handler → FastAPI, attaching auth server-side
- Auth-check pattern: read session cookie → forward with Authorization to FastAPI
- When to use route handlers vs browser-direct-to-FastAPI (decision matrix: cookie auth, hiding endpoints, aggregation)

**5.8 — Server Actions**
- `'use server'`; they're POST endpoints — **always authorize**
- Forms with `action={fn}`; `useActionState`, `useFormStatus`
- zod validation inside the action; returning typed error objects
- `revalidatePath/Tag` after mutation; `redirect()`
- Actions vs route handlers vs direct API — the decision matrix for your app

**5.9 — Auth with Keycloak (OIDC), the full picture**
- OIDC vocabulary: issuer, client, scopes, ID/access/refresh tokens, **PKCE**; Keycloak client setup (public vs confidential)
- The authorization-code flow mapped onto Next: login route → Keycloak → callback route handler → session
- Session strategy: refresh+access tokens in an **httpOnly cookie** (Next acts as confidential client) — vs alternatives and trade-offs
- Reading the user server-side (`cookies()` → verify → pass down); typed user context for client components
- Route protection: layout-level checks, middleware role gating (with edge-runtime crypto caveats)
- Token refresh scheduling; logout with revocation; state/nonce/CSRF
- Auth.js v5 with the Keycloak provider — when it's worth it vs your own ~150 lines
- How this coexists with your existing FastAPI resource-server JWT verification

**5.10 — Middleware & runtime concepts**
- `middleware.ts`, matcher config, edge runtime limitations
- Use cases: auth gate, redirects, rewrites, headers
- Why business logic never lives in middleware
- Node vs edge runtime selection for route handlers

**5.11 — Streaming UX & Suspense orchestration**
- How streaming SSR actually flushes; nested Suspense boundaries
- `loading.tsx` per segment; skeleton design
- Slow-FastAPI demo: shell renders instantly, panels stream in
- Error boundaries + reset in streamed trees; `useTransition` for navigation

**5.12 — Metadata, SEO & app polish**
- `metadata`/`generateMetadata`; title templates; OpenGraph
- `sitemap.ts`, `robots.ts`, manifest, theme color
- **Auth-gated app = `noindex`** — when SEO matters and when it doesn't
- Dynamic OG images with `ImageResponse` (optional nice-to-have)

**5.13 — Tailwind v4 + shadcn + theming inside Next**
- `globals.css`; `next/font` (self-hosted fonts — no Google requests, fits your FOSS/self-host rules)
- `shadcn init`: `components.json`, aliases, CSS-var theme
- Dark mode with `next-themes`: provider, `suppressHydrationWarning`, flash prevention
- App shell build: sidebar + header + main + right panel (the harness layout)

**5.14 — Real-time AI streaming, browser side (your killer feature — heavy module)**
- Recap: fetch + ReadableStream + TextDecoder; parsing SSE `data:` lines and JSON-lines
- Managing a stream in React: status machine (idle/streaming/done/error), appending tokens, buffering + rAF-batched flushes for smooth re-renders
- Stop button with AbortController; regenerate flow
- EventSource vs fetch-streaming: reconnect semantics, when each wins
- Streaming through the Next route-handler proxy (auth) vs direct to FastAPI (CORS + credentials)
- Full lab: FastAPI `StreamingResponse` → proxy → live-updating chat box

**5.15 — Project architecture for a growing app**
- Feature-based structure: `features/chat/{components,hooks,api,schemas}`
- `lib/server` vs `lib/client` isolation (`server-only`/`client-only` packages)
- API layer: fetch wrappers + query-key/option factories + zod schemas per feature
- Env validation module (zod, fail-fast at boot)
- Import discipline; path aliases; when to consider pnpm workspaces later

**5.16 — next.config, images, fonts & optimization**
- The options you'll actually set: **`output: 'standalone'`** (Docker!), `images.remotePatterns`, `typedRoutes`, headers/redirects/rewrites
- `next/image` self-hosted: sharp, optimizer behind the proxy, `unoptimized` trade-offs in Docker
- Bundle analyzer; dynamic import of heavy widgets (markdown, charts)
- Prefetching config

**5.17 — Testing Next apps**
- Client components: Vitest + RTL as before
- Server components: extract logic, test functions/hooks; integration via rendered route
- Playwright with `webServer` config; `storageState` for one-time Keycloak login in tests
- CI stage layout: lint → typecheck → unit → build → e2e → image

**5.18 — Advanced App Router & gotchas compendium**
- Intercepting routes for modals (conversation settings modal); parallel routes
- Async dynamic APIs in Next 15: `cookies()`, `headers()`, `params`, `searchParams`
- `redirect()` vs `router.push`
- The classic build failures: prerendering crashed on dynamic code; hydration mismatch; `window is not defined`
- Upgrade checklist habit, codemods, reading release notes

---

## PART 6 — shadcn/ui & Component Craft (9 modules)

**6.1 — Headless UI & the shadcn model**
- Styled vs headless; accessibility as a first-class feature
- Radix primitives: behavior, keyboard nav, ARIA, focus trapping — what you'd otherwise build wrong
- shadcn's philosophy: **code copied into your repo**, not an npm dependency; own and modify freely; registry concept
- Anatomy of the generated `Button`: cva variants, `cn()`, ref handling, `asChild`/Slot — now you know every piece from 4.19
- `components.json`; the deps it installs (radix-ui, lucide-react, cva, tailwind-merge, clsx); updating/diffing later

**6.2 — Form controls in depth**
- Button: variants, sizes, loading state, `asChild` with links
- Input, Textarea, Label — controlled usage
- Select (Radix, not native): `value/onValueChange`, grouped, searchable via Combobox
- Checkbox, RadioGroup, **Switch**; RHF `Controller` integration quirks
- **Slider** (temperature/top_p controls); Combobox recipe (Command + Popover)
- Calendar/date pickers; validation-state wiring

**6.3 — Overlays: dialogs, menus, popovers**
- Dialog: controlled, forms inside, focus trap, Esc, scroll lock
- **Sheet** — mobile chat-history drawer
- DropdownMenu: items, groups, checkbox items, submenus
- Popover (filters), HoverCard, ContextMenu, Tooltip (placement, delay, touch caveat)
- Portals and z-index — why it all "just works"

**6.4 — Command palette & search (cmdk)**
- Command API: groups, items, filtering, keywords
- `CommandDialog` as global ⌘K — the power-user signature of your harness
- Full Combobox build; nested command navigation
- Registering global keyboard shortcuts

**6.5 — Data display & the data-table recipe**
- Card, Badge, Avatar, Alert, Separator, Skeleton, ScrollArea, Tabs, Accordion, Collapsible
- **TanStack Table + shadcn table** full build: sorting, global filter, faceted filters, pagination (URL state), row selection, column visibility, sticky header
- Empty/error state design patterns

**6.6 — Feedback & async UX**
- Sonner toasts: variants, action buttons, `promise()` toast
- Progress (determinate/indeterminate); confirmation dialogs for destructive actions
- Optimistic-update demo with undo
- Toast vs in-app inbox for long-running agent jobs

**6.7 — Navigation & the app shell**
- shadcn **Sidebar**: collapsible, icon mode, mobile sheet, grouped items, active state; persist collapse in Zustand
- Breadcrumbs; user dropdown (profile/logout → Keycloak)
- **Resizable panels** (chat + inspector) via react-resizable-panels
- Assemble the complete harness shell: sidebar (conversations) + header (model picker, user) + main (chat) + inspector panel; responsive rules

**6.8 — Theming, dark mode & design tokens**
- Full CSS-variable anatomy: background/foreground/card/popover/primary/…/chart/sidebar
- Building a brand theme: oklch color picking, contrast checking, radius scale
- next-themes: system detection, toggle, flash prevention
- Multiple themes via `data-theme`; adding your own variant to a component
- Font pairing, spacing rhythm

**6.9 — Building custom components beyond the registry**
- Recipe: Radix primitive + cva + `cn()` + ref — build a TagInput, KeyBadge, MessageBubble (compose registry parts)
- Testing your components
- **Documenting component APIs for your AI coding agents** (a conventions file agents must follow — this multiplies your agent productivity)

---

## PART 7 — AI-Harness UI Patterns (5 modules)

*The modules that make your product feel professional. Assume everything before this.*

**7.1 — Chat interface architecture**
- Message data model: id, role, parts[] (text/tool/image), status, timestamps — designed to evolve
- Streaming message component: partial markdown, cursor, append-vs-typewriter
- **react-virtuoso**: dynamic heights, stick-to-bottom (follow output unless the user scrolled up), scroll-to-message
- Composer: auto-growing textarea, Enter/Shift+Enter, attachments, model/params popover
- Actions: copy, regenerate, edit-and-rerun; optimistic user message with rollback
- Conversation state: React Query cache + Zustand for drafts

**7.2 — Markdown, code & rich content**
- react-markdown pipeline (remark/rehype) + component overrides
- remark-gfm (tables, task lists); **rehype-sanitize with a custom schema (XSS!)**
- Code blocks: **shiki** (accurate, async — debounce re-highlight while streaming) vs rehype-highlight (lighter); copy button, wrap toggle
- Streaming-markdown pitfalls: unclosed code fences, partial tables
- Tool-call cards (name, args, collapsible result), JSON tree view, KaTeX (optional)

**7.3 — Agent/automation UX patterns**
- Run-state model: queued/running/awaiting-input/failed/done; supervisor indicators
- Step timeline (vertical stepper, status icons, durations); retry visualization
- Human-in-the-loop approval dialogs; notification inbox
- **Diff views** for agent file edits; xterm.js for terminal-style logs
- Token/cost meters (recharts); audit log view

**7.4 — Real-time beyond one chat**
- Architecture: FastAPI SSE/WebSocket hub → browser (direct or via Next proxy)
- WebSocket reconnection with backoff (own hook vs socket.io — when each)
- React Query + realtime: **invalidate-on-event** vs direct `setQueryData` cache patching
- Auth on websockets; heartbeats; batching high-frequency events; offline banner

**7.5 — Product-grade details for AI apps**
- Latency UX: optimistic echo, "thinking" states, streaming cursor
- Model/provider switchers; rate-limit error mapping with retry-after
- `aria-live` for streaming content (screen readers); keyboard-first UX (⌘K everything)
- Empty states that teach; mobile chat behavior; i18n readiness (next-intl, optional)

---

## PART 8 — Production, Docker & Operations (12 modules)

*Everything here is tuned to your exact stack: Ubuntu server, Docker Compose, Cloudflare Tunnel, no Vercel, FOSS tooling.*

**8.1 — Production builds & standalone output**
- What `next build` does; **`output: 'standalone'`** and `.next/standalone` anatomy
- Running: `node server.js` with `PORT`/`HOSTNAME`; the copy step for `.next/static` + `public` (the classic standalone gotcha)
- **`NEXT_PUBLIC_` vars are inlined at build time** — the #1 Docker gotcha; runtime-config strategies (config route handler, server-injected values)
- Dev-vs-prod behavior differences; sourcemaps decisions

**8.2 — Production Dockerfile for Next.js**
- Multi-stage: deps (pnpm fetch) → builder → runner (`node:22-alpine`, non-root user, `tini`/`dumb-init` for signals)
- Copying standalone + static + public; `HEALTHCHECK`; `.dockerignore`
- Layer caching for CI (lockfile-first, BuildKit cache mounts)
- Image tags by git SHA; size inspection (dive)
- The same pattern for a pure-Vite SPA (nginx:alpine + dist) — for comparison

**8.3 — The full Compose stack**
- Services: frontend, backend (FastAPI), postgres, redis, keycloak, cloudflared — one private bridge network, **only cloudflared exposed**
- Internal DNS: frontend reaches FastAPI at `http://backend:8000`; the internal vs public API URL distinction
- Healthchecks + `depends_on: condition: service_healthy`
- Volumes, restart policies, log limits; dev override file with bind mounts + hot reload
- **Watchtower** service for image auto-updates (your preference) + pinning strategy

**8.4 — Cloudflare Tunnel & traffic flow**
- `cloudflared` as a compose service; token vs config auth; ingress rules: `app.example.com→frontend`, `api.example.com→backend`, `id.example.com→keycloak`
- WebSockets through the tunnel (needed for your realtime features)
- Optional zero-trust layer: Cloudflare Access in front of internal tools
- Static-asset caching rules (immutable hashed files) and **never caching app HTML**
- Troubleshooting: 502/521, CORS resurfacing, cookie domain/Secure flags through the proxy

**8.5 — Env, config & secrets management**
- Classification: build-time (`NEXT_PUBLIC_`), server runtime, container runtime, secrets
- zod env validation at boot (fail fast, typed)
- Runtime public config via `/api/config`; `.env.example` discipline
- Keycloak client secret placement; Docker secrets vs env

**8.6 — Security hardening**
- XSS audit: `dangerouslySetInnerHTML`, markdown sanitization policy, CSP headers (nonce intro)
- CSRF: SameSite cookies + POST-only mutations; token-storage trade-offs (httpOnly cookie vs memory)
- Headers via `next.config`: HSTS, frame-ancestors, referrer-policy
- Dependency supply chain: lockfiles, `pnpm audit`, Renovate, trivy image scans
- The rule that saves you: **no secret ever in a `NEXT_PUBLIC_` var** — grep the bundle

**8.7 — Observability, all FOSS/self-hosted**
- **GlitchTip** (lightweight, Sentry-protocol-compatible, self-hosted) + its SDK; error boundaries and `onerror`/`unhandledrejection` reporting; sourcemap upload in CI
- **Uptime Kuma** for external monitoring of tunnel routes
- **Umami** for privacy-first analytics (or none for internal tools)
- Release tags = image SHA, correlated with backend logs; never log tokens/prompts

**8.8 — Production performance audits**
- Lighthouse; Core Web Vitals meaning (LCP/CLS/INP)
- Bundle analyzer in CI with size budgets; dynamic-import review for markdown/highlight/charts
- Self-hosted `next/image` (sharp), caching headers, font loading
- The tunnel's effect on TTFB; what's worth optimizing and what isn't

**8.9 — CI/CD with GitHub Actions (your stack)**
- Workflow: pnpm+node with cache → lint/typecheck/vitest in parallel → build → docker build & push to GHCR (buildx cache, SHA tags)
- E2E job spinning the compose stack + Playwright; artifact upload on failure
- Deploy: SSH action running `docker compose pull && up -d`, or Watchtower auto-pull; GitHub Environments with manual approval for prod
- Branch protection requiring status checks; rollback = redeploy older SHA tag

**8.10 — Playwright E2E deep-dive**
- Config with `webServer` against your built app; `storageState` for Keycloak login-once
- Locators philosophy (`getByRole`), auto-waiting, traces/videos on failure
- **Testing streaming**: mock a slow SSE endpoint and assert progressive rendering
- Route interception to mock FastAPI for deterministic suites vs full-stack runs

**8.11 — Maintenance & the long run**
- Upgrade cadence and codemods (Next majors, Tailwind v3→v4 migration experience, React 19 changes)
- shadcn component updates via CLI diff; keep customizations in variants, not edits
- Renovate grouping + automerge patches; lockfile hygiene
- A light runbook: deploy, rollback (image pinning), and a decisions log

**8.12 — Capstone: the AI harness frontend (integration project)**
- 10 milestones: scaffold → app shell (6.7) → Keycloak auth (5.9) → conversations CRUD (React Query) → streaming chat (5.14 + 7.1) → markdown/tool-cards (7.2–7.3) → settings forms (RHF+zod → FastAPI) → ⌘K palette → theme/dark mode → Dockerize + tunnel + CI (Part 8)
- Acceptance criteria per milestone; performance/security/a11y review checklist
- A conventions file (CLAUDE.md-style) so your AI coding agents build against your components correctly
- Final deploy-day runbook with rollback

---

## Suggested execution notes

- **Pacing at ~10 hrs/week:** Parts 0–1: ~4 weeks · Part 2: ~2 weeks · Part 3: ~3 weeks · Part 4: ~6 weeks · Part 5: ~5 weeks · Part 6: ~2 weeks · Part 7: ~2 weeks · Part 8: ~3 weeks → **~6–7 months to production-ready**, faster with your AI-assisted style.
- **Speedrun allowed:** 1.1–1.2 in one sitting (you know loops). Do not compress 1.3, 1.11–1.13, 4.5, 4.7, 5.3 — these are where the real bugs in your future app will come from.
- **Interleave projects with learning**, never consume modules passively — each milestone exists to force retrieval.
- Parts 7 and 8 are what most tutorials never teach and what your self-hosted, Docker-based deployment actually needs — give them full weight.

Want me to expand any single module into a fully-written-out deep syllabus (with per-sub-module learning objectives and exercise specs) to test the format before you start?
