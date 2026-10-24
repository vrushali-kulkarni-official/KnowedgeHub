# Part 1: HTML and CSS Foundations

(Lesson 1 was the intro: tags, elements, nesting, head vs body. We continue from there.)

---

# Lesson 2: The tags you will use 90% of the time

You already know `<h1>`, `<p>`, `<div>`. Here are the rest of the everyday tools.

```html
<a href="https://example.com">A link</a>
<img src="cat.jpg" alt="A cat">
<button>Click me</button>
<input type="text" placeholder="Type here">
<ul>
  <li>Item one</li>
  <li>Item two</li>
</ul>
```

| Tag | What it is | Python-ish analogy |
|---|---|---|
| `<a>` | Link | A reference/pointer to another page |
| `<img>` | Image (no closing tag, it has no content) | Loading a file |
| `<button>` | Clickable thing | A function waiting to be called |
| `<input>` | Where the user types | `input()` in Python, but always visible |
| `<ul>` / `<li>` | Bulleted list / list item | A Python list |

## Attributes: extra settings on a tag

`href`, `src`, `alt`, `type`, `placeholder` are **attributes**. They are `name="value"` pairs inside the opening tag. Think of them as **keyword arguments**:

```python
img(src="cat.jpg", alt="A cat")
```

```html
<img src="cat.jpg" alt="A cat">
```

## The two most important attributes: `id` and `class`

These are **names** you give elements so that CSS and JavaScript can find them later.

```html
<button id="magic-btn" class="big">Click me</button>
```

- `id` = a **unique** name (one element only). Like a person's national ID.
- `class` = a **group** name (many elements can share it). Like "student" or "teacher".

A tag can have a class like `class="big rounded"` (two classes, separated by a space).

## Semantic tags: boxes with meaning

`<div>` is a generic box. HTML also has boxes with meaning: `<header>`, `<nav>`, `<main>`, `<section>`, `<footer>`, `<aside>`. They behave like `<div>` but tell the browser (and screen readers, and Google) what the box is for. Use them for page layout.

## Forms (we need these later)

```html
<form>
  <label for="name">Name</label>
  <input id="name" type="text" name="name">
  <input type="file" name="photo">
  <button type="submit">Send</button>
</form>
```

`<label for="name">` connects the label to the input with the matching `id`. Clicking the label focuses the input. See how `id` is already useful?

### Practice
Build a page with a heading, a paragraph, a link, a button with `id="magic-btn"`, and a list of 3 hobbies.

---

# Lesson 3: What is CSS?

HTML = **what** is on the page. CSS = **how it looks**.

A CSS rule has the shape: **selector** (who?) + **declarations** (what style?).

```css
p {
  color: blue;
  font-size: 20px;
}
```

Read it as: "For every `<p>`, set color to blue and font size to 20px."

## Connecting CSS to HTML

Make a `style.css` file next to `index.html`, and inside `<head>` add:

```html
<link rel="stylesheet" href="style.css">
```

## Selectors: how CSS finds elements

```css
p { }            /* every <p> (by tag) */
.big { }         /* every element with class="big" (dot = class) */
#magic-btn { }   /* the element with id="magic-btn" (hash = id) */
```

Mnemonic: **dot for class, hash for id**.

## Cascade: when rules fight

If two rules style the same thing, the more specific wins: `#id` beats `.class` beats `tag`. If equal, the **later** one wins. (That's the "Cascading" in CSS.)

## Practice
Style your page: give the button a background color, white text, and larger font.

---

# Lesson 4: The Box Model (the most important CSS idea)

**Every element is a rectangular box.** Each box has 4 layers, from inside out:

```
┌────────── margin ──────────┐
│ ┌─────── border ─────────┐ │
│ │ ┌──── padding ───────┐ │ │
│ │ │      content       │ │ │
│ │ └────────────────────┘ │ │
│ └────────────────────────┘ │
└────────────────────────────┘
```

| Layer | Meaning | Analogy (a framed photo) |
|---|---|---|
| content | The text or image | The photo |
| padding | Space **inside** the border | White matte around the photo |
| border | The edge line | The frame |
| margin | Space **outside** the border | Gap between this frame and the next |

```css
.card {
  width: 300px;
  padding: 16px;
  border: 2px solid black;
  margin: 20px;
  border-radius: 12px;   /* round corners */
}
```

One fix to add to every project, so sizes behave sensibly:

```css
* { box-sizing: border-box; }
```

(This makes `width` include padding and border, which is what your brain expects.)

## Units
- `px` = fixed pixels
- `%` = percent of parent
- `rem` = relative to base font size (1rem = usually 16px). Good for scalable design.
- `vh` / `vw` = percent of screen height / width. `100vh` = full screen height.

## Colors
`red`, `#ff0000`, `rgb(255,0,0)`, `hsl(0,100%,50%)`. Use whichever you like.

---

# Lesson 5: Flexbox, laying things out

By default, block elements stack vertically. To arrange in a row, centre things, space them out, use **Flexbox**. Put `display: flex` on the **parent**:

```html
<div class="row">
  <div>A</div><div>B</div><div>C</div>
</div>
```

```css
.row {
  display: flex;
  gap: 16px;                  /* space between children */
  justify-content: center;    /* along the main axis (horizontal by default) */
  align-items: center;        /* across (vertical by default) */
}
```

Mental model: a flex parent has a **main axis** (row by default) and a **cross axis**.
- `justify-content` = alignment along the main axis
- `align-items` = alignment along the cross axis
- `flex-direction: column;` swaps the axes (stack vertically)

### The famous "centre anything on the screen"
```css
body {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
}
```

---

# Lesson 6: Grid, position, responsiveness (the essentials)

## Grid: rows AND columns
```css
.gallery {
  display: grid;
  grid-template-columns: repeat(3, 1fr);  /* 3 equal columns */
  gap: 16px;
}
```
Use **flex** for one direction (a row of items), **grid** for two (a table-like layout).

## Position: placing things precisely
```css
.parent { position: relative; }
.badge  { position: absolute; top: 0; right: 0; }  /* pinned to parent's corner */
.navbar { position: fixed; top: 0; }               /* stays on screen while scrolling */
```
Rule of thumb: an `absolute` child positions itself relative to the nearest ancestor with `position: relative`. You'll use this for the sidebar project.

## Responsive design
Phones and laptops differ. A **media query** applies styles only on certain widths:
```css
@media (max-width: 600px) {
  .gallery { grid-template-columns: 1fr; }
}
```
"If the screen is 600px or narrower, make it a single column."

## CSS variables (you will use these for dark mode)
```css
:root {
  --bg: white;
  --text: black;
}
body {
  background: var(--bg);
  color: var(--text);
}
```
`:root` is the top of the page. `--bg` is a variable you invent. `var(--bg)` reads it. Change the variable and everything using it changes.

## Transitions: smooth changes
```css
button {
  background: blue;
  transition: background 0.3s;
}
button:hover { background: darkblue; }
```
`:hover` is a **pseudo-class**: "when the mouse is over this".

---

# Checkpoint

You now know enough HTML and CSS to build any of the mini projects. You can:
- Build a page structure with semantic tags
- Name elements with `id` and `class`
- Style with selectors, the box model, flex, grid
- Use CSS variables and transitions

Next: **Part 2, JavaScript**, where the page comes alive.
