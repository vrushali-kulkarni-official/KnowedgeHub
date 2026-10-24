# Part 3: Tailwind CSS

---

# Lesson 9: What is Tailwind and why does everyone use it?

In plain CSS you invent class names (`.card`, `.big-btn`), switch to the CSS file, write rules, switch back. Tailwind removes the switching. It gives you **tiny ready-made classes**, each doing exactly one thing, and you stack them directly in the HTML.

```html
<!-- Plain CSS -->
<button class="big-btn">Click</button>
<!-- plus a CSS file with .big-btn { background: blue; color: white; padding: 8px 16px; border-radius: 8px; } -->

<!-- Tailwind -->
<button class="bg-blue-500 text-white px-4 py-2 rounded-lg">Click</button>
```

> **Python comparison:** plain CSS is writing a custom function for every need. Tailwind is a library of small utility functions that you compose.

It is not magic: `bg-blue-500` is literally `background-color: ...blue...;`. You already understand CSS, so Tailwind is just **shorthand names for CSS you know**. Next.js, shadcn/ui and most modern React projects use it, so this matters.

## Try it with zero setup
Add this in your `<head>` (the quick CDN way, good for learning):
```html
<script src="https://cdn.tailwindcss.com"></script>
```
Real projects install it via npm, but the classes are identical.

---

# Lesson 10: The vocabulary (learn the pattern, not every class)

Almost every class follows **property-value** naming. Learn these families and you can guess the rest.

## Spacing: scale of 4px per unit
| Class | CSS |
|---|---|
| `p-4` | `padding: 16px` (4 × 4px) |
| `px-4` / `py-2` | padding left+right / top+bottom |
| `pt-2`, `pb-2`, `pl-2`, `pr-2` | padding top/bottom/left/right |
| `m-4`, `mx-auto`, `mt-8` | margin variants (`mx-auto` centres a block) |
| `gap-4` | `gap: 16px` |

## Sizing
`w-64` (256px), `w-full` (100%), `h-screen` (100vh), `max-w-md`, `min-h-screen`.

## Colors
`bg-red-500`, `text-gray-700`, `border-blue-300`. The number is the shade (50 light … 900 dark).

## Text
`text-sm`, `text-xl`, `text-3xl`, `font-bold`, `text-center`.

## Borders and shadows
`border`, `border-2`, `rounded`, `rounded-lg`, `rounded-full` (circle), `shadow`, `shadow-lg`.

## Layout
| Class | CSS |
|---|---|
| `flex` | `display: flex` |
| `flex-col` | `flex-direction: column` |
| `justify-center` | `justify-content: center` |
| `items-center` | `align-items: center` |
| `grid grid-cols-3` | 3-column grid |
| `fixed`, `absolute`, `relative` | position |
| `hidden` | `display: none` |

## States as prefixes
```html
<button class="bg-blue-500 hover:bg-blue-700 transition">Hover me</button>
```
`hover:` applies the class only on hover. Other prefixes: `focus:`, `active:`, `disabled:`.

## Responsive as prefixes
```html
<div class="grid grid-cols-1 md:grid-cols-3">
```
Tailwind is **mobile-first**: the plain class applies to all sizes, and `md:` means "from 768px and wider". Other breakpoints: `sm` (640), `lg` (1024), `xl` (1280). No media queries to write.

## Custom one-off values
`w-[350px]`, `bg-[#ff6600]`: square brackets let you use any value.

---

# Lesson 11: Rebuild your projects in Tailwind

## Counter
```html
<body class="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-100">
  <h1 id="count" class="text-6xl font-bold">0</h1>
  <div class="flex gap-2">
    <button id="minus" class="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600">-</button>
    <button id="plus"  class="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">+</button>
  </div>
  <script src="script.js"></script>
</body>
```
The JS file is **unchanged**. Tailwind only touches the styling.

## Progress bar
```html
<div class="w-72 h-5 bg-gray-300 rounded-full overflow-hidden">
  <div id="fill" class="h-full w-0 bg-green-500 transition-all duration-300"></div>
</div>
```
The JS still sets `fill.style.width`.

## Sidebar (JS toggles Tailwind classes)
```html
<aside id="sidebar"
  class="fixed top-0 left-0 w-60 h-screen bg-gray-900 text-white p-5
         -translate-x-full transition-transform duration-300">
  ...
</aside>
```
```js
sidebar.classList.toggle("-translate-x-full");
```
The negative prefix `-` means negative value. Hidden = has `-translate-x-full`; visible = remove it.

## Dark mode in Tailwind
Tailwind has a built-in `dark:` prefix:
```html
<body class="bg-white text-black dark:bg-gray-900 dark:text-white">
```
```js
document.documentElement.classList.toggle("dark");   // put "dark" on <html>
```
With the CDN, enable class mode first:
```html
<script>tailwind.config = { darkMode: "class" }</script>
```
(placed after the CDN script).

---

# Lesson 12: Tailwind habits and the road to React

1. **Long class lists are normal.** In React you'll wrap repeated blocks into **components**, so you only write the long list once.
2. **Don't memorise.** Keep the Tailwind docs search open. Learn the families above and search the rest.
3. **Order doesn't matter** in the class attribute; the stylesheet decides.
4. **Never build class names dynamically** like `` `bg-${color}-500` ``. Tailwind scans for complete class names in your code, so the full string must appear. Use `isRed ? "bg-red-500" : "bg-blue-500"`.
5. **shadcn/ui** is a collection of pretty components (buttons, dialogs, etc.) built from Tailwind classes, whose code gets copied into your project. Since you now read Tailwind fluently, you can read and edit it.

## Practice: a profile card
```html
<div class="max-w-sm mx-auto mt-10 p-6 bg-white rounded-2xl shadow-lg text-center">
  <img class="w-24 h-24 rounded-full mx-auto" src="https://i.pravatar.cc/150" alt="avatar">
  <h2 class="mt-4 text-xl font-bold">Your Name</h2>
  <p class="text-gray-500">Frontend learner</p>
  <button class="mt-4 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">Follow</button>
</div>
```
Read each class aloud and translate it to CSS in your head. That's your Tailwind test.

---

# Checkpoint

You can now style fast. Next, **Part 4**, the big one: your pages start **talking to servers**, which is where real apps begin.
