"""Act 1 - JavaScript basics, only the parts DOM work needs."""

STEPS = [

# ---------------------------------------------------------------- step 1
{
 "id": "js-variables",
 "title": "Variables: giving names to things",
 "lede": "Before you can change a page you need to be able to hold a value. "
         "That is all a variable is: a name you stick on a value so you can use it later.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>Your HTML describes the <em>shape</em> of a page. Your CSS describes how it "
   "looks. JavaScript describes what <em>happens</em>.</p>"
   "<p>And to do anything at all, JS needs to hold stuff: a name, a number, a piece of text, "
   "an element from the page. A <strong>variable</strong> is just a name sticker for a value.</p>"
   "<pre class=\"code\"><code>let score = 10;\nconst name = \"Ada\";</code></pre>"
   "<p>Read it like Python: <code>score</code> is a box. You put <code>10</code> inside it, "
   "and later you can take it back out by writing <code>score</code>.</p>"
   "<p><strong>Why two keywords?</strong> JavaScript lets you protect yourself from typos:</p>"
   "<ul>"
   "<li><code>const</code> &mdash; this name is locked forever. You cannot reassign it. "
   "Use this by default.</li>"
   "<li><code>let</code> &mdash; this name <em>may</em> change later. Use this only when you "
   "really do plan to change it.</li>"
   "</ul>"
   "<p>If you try to do <code>const x = 1; x = 2;</code> JavaScript stops you with an error. "
   "That is a feature. It turns a silent typo into a loud one.</p>"
   "<p><strong>Strings vs numbers:</strong> text needs quotes (<code>\"Ada\"</code>, "
   "<code>'Ada'</code>), numbers do not (<code>10</code>). If you write <code>const x = 10</code> "
   "you get the number ten; <code>const x = \"10\"</code> you get the text ten. They look the "
   "same on screen and behave completely differently.</p>"},

  {"type": "bridge", "title": "Same idea, different spelling", "html":
   "<p>You already know all of this from Python. The concepts are identical, "
   "only the keywords changed.</p>",
   "pairs": [
     {"py_label": "Python", "js_label": "JavaScript",
      "py": "score = 10\nname = \"Ada\"",
      "js": "let score = 10;\nconst name = \"Ada\";"},
     {"py_label": "Python (locked)", "js_label": "JavaScript (locked)",
      "py": "# there is no real const, but the idea exists\nSCORE = 10  # by convention only",
      "js": "const score = 10;\n// score = 20;  // <- Error!"},
     {"py_label": "Python f-string", "js_label": "JavaScript template literal",
      "py": "greeting = f\"Hi {name}, you have {score} points\"",
      "js": "const greeting = `Hi ${name}, you have ${score} points`;"},
   ]},

  {"type": "note", "title": "The one new trick: backticks", "html":
   "<p>Python has <code>f\"...{name}...\"</code>. JavaScript does the same thing with "
   "<strong>backticks</strong> and <code>${}</code>:</p>"
   "<pre class=\"code\"><code>const name = \"Ada\";\nconst score = 10;\n"
   "const msg = `Hi ${name}, score: ${score}`;\n"
   "console.log(msg);   // Hi Ada, score: 10</code></pre>"
   "<p>Rule of thumb: use <code>+</code> to glue two short strings together, "
   "use backticks whenever a sentence contains a value. Backticks also let you break a long "
   "string across lines, which <code>\"</code> cannot do.</p>"},

  {"type": "lab", "id": "js-variables-lab", "title": "Your first lines of JavaScript",
   "html": "<p>This box is a <strong>lab</strong>. It works like the Python REPL: type code, "
           "press <strong>Run</strong>, read the output. Nothing here can break your page.</p>",
   "starter": "// Change me, then press Run\nconst name = \"Ada\";\nlet score = 10;\n\n"
              "console.log(`Hi ${name}, you have ${score} points`);\n\nscore = score + 5;\n"
              "console.log(`After the bonus: ${score}`);",
   "hints": [
     "Use <code>console.log(\"...\")</code> to print. It is the browser's <code>print()</code>.",
     "Backticks around the text, and <code>${name}</code> to drop a variable inside it.",
     "Inside a template literal, <code>${score + 5}</code> works too &mdash; anything goes "
     "between <code>${</code> and <code>}</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Inside the lab, finish these three lines:</p>",
   "checks": [
     "Declare a <code>const</code> called <code>city</code> holding the text <code>\"Bengaluru\"</code>.",
     "Declare a <code>let</code> called <code>tickets</code> holding the number <code>3</code>, "
     "then change it to <code>5</code> using <code>=</code> (not <code>const</code> &mdash; "
     "you will get an error if you do).",
     "Print one sentence using a template literal that shows both, like "
     "<code>\"3 tickets in Bengaluru\"</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>const</code> locks a name forever, <code>let</code> allows a later change.",
     "Text needs quotes, numbers do not.",
     "Backticks + <code>${value}</code> is JavaScript's f-string.",
     "<code>console.log()</code> prints to the browser console (F12).",
  ]},
 ],
},

# ---------------------------------------------------------------- step 2
{
 "id": "js-functions",
 "title": "Functions: a named box of steps",
 "lede": "A function is a piece of code you give a name, so you can run it whenever you want, "
         "as many times as you want. You already know this from Python.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>You will write the same three lines over and over if you have no functions. "
   "A function lets you write them once and call them by name.</p>"
   "<pre class=\"code\"><code>function greet(name) {\n"
   "  return \"Hi \" + name + \"!\";\n}\n\n"
   "console.log(greet(\"Ada\"));   // Hi Ada!\n"
   "console.log(greet(\"Alan\"));  // Hi Alan!</code></pre>"
   "<p>Three parts, exactly like Python:</p>"
   "<ul>"
   "<li><code>function</code> + name + <code>(</code>parameters<code>)</code> = the "
   "<strong>header</strong>.</li>"
   "<li>the <code>{ }</code> block = the <strong>body</strong> (Python uses indentation "
   "instead of braces).</li>"
   "<li><code>return</code> = hand a value back out. If a function has no <code>return</code>, "
   "it gives back <code>undefined</code> &mdash; which is JavaScript's version of Python's "
   "<code>None</code>.</li>"
   "</ul>"
   "<p>You call it by writing its name with parentheses: <code>greet(\"Ada\")</code>. "
   "The values you pass in are <strong>arguments</strong>.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Literally the same thing.</p>",
   "pairs": [
     {"py_label": "Python", "js_label": "JavaScript",
      "py": "def greet(name):\n    return \"Hi \" + name + \"!\"",
      "js": "function greet(name) {\n  return `Hi ${name}!`;\n}"},
     {"py_label": "Python (one-liner style)", "js_label": "JavaScript (arrow function)",
      "py": "greet = lambda name: \"Hi \" + name + \"!\"",
      "js": "const greet = (name) => `Hi ${name}!`;"},
     {"py_label": "Python default arg", "js_label": "JavaScript default arg",
      "py": "def greet(name=\"friend\"):\n    return \"Hi \" + name",
      "js": "function greet(name = \"friend\") {\n  return `Hi ${name}`;\n}"},
   ]},

  {"type": "note", "title": "Arrow functions: the short form you will see everywhere", "html":
   "<p>JavaScript has a second way to write functions, called an <strong>arrow function</strong>. "
   "It is shorter and it behaves slightly differently (you will meet that difference in Step 6).</p>"
   "<pre class=\"code\"><code>const add = (a, b) => a + b;          // one-line body\n"
   "const add = (a, b) => {\n  return a + b;\n};               // block body\n"
   "const shout = s => s.toUpperCase();                     // one arg, no parens needed</code></pre>"
   "<p>Rule of thumb: <code>function</code> for named functions you define yourself, "
   "arrow functions for short inline callbacks. Both are 100% interchangeable for "
   "everything we do in this course &mdash; except one case we will hit in Step 6.</p>"},

  {"type": "idea", "title": "Why functions matter for the DOM", "html":
   "<p>Two reasons, and both are about staying organised:</p>"
   "<ul>"
   "<li><strong>Naming a behaviour.</strong> A function called "
   "<code>addTodo(text)</code> tells you what it does without you reading the body.</li>"
   "<li><strong>One job, one place.</strong> When a button is clicked you will often need the "
   "same three lines of code in two different places. Put them in a function, call it twice.</li>"
   "</ul>"},

  {"type": "lab", "id": "js-functions-lab", "title": "Write a function",
   "html": "<p>Finish the function so it works, then press Run.</p>",
   "starter": "function add(a, b) {\n  return a + b;\n}\n\n"
              "console.log(add(2, 3));      // prints 5\n"
              "console.log(add(10, 0.5));    // prints 10.5\n\n"
              "// now break it on purpose: delete the `return` and run it again.\n"
              "// what does the function return now?",
   "hints": [
     "A function only sends a value back if it says <code>return</code>.",
     "Make sure you <code>return a + b;</code> &mdash; if you only write <code>a + b;</code> "
     "without <code>return</code>, the function gives back <code>undefined</code>.",
     "You can also write it as <code>const add = (a, b) =&gt; a + b;</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Write a function <code>isEven(n)</code> that returns <code>true</code> if "
           "<code>n</code> is even and <code>false</code> otherwise. Test it with "
           "<code>isEven(4)</code> and <code>isEven(7)</code>.</p>",
   "checks": [
     "The function returns the boolean <code>true</code> / <code>false</code>, not the string "
     "<code>\"true\"</code>.",
     "Bonus: check <code>isEven(0)</code> too. (It is even. Do not overthink it.)",
   ]},

  {"type": "checkpoint", "items": [
     "A function = a named, reusable box of steps.",
     "Parameters go in the parentheses; <code>return</code> sends a value back out.",
     "No <code>return</code> means the function hands back <code>undefined</code> (like "
     "Python's <code>None</code>).",
     "Arrow functions are the short form: <code>(a) =&gt; a * 2</code>.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 3
{
 "id": "js-arrays-objects",
 "title": "Lists and dictionaries (arrays and objects)",
 "lede": "You need two containers before you touch the DOM: a list of things, and a thing with "
         "named properties. In Python you call them list and dict. In JavaScript: array and object.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>Two shapes you will use constantly:</p>"
   "<pre class=\"code\"><code>// array = an ordered list\nconst fruits = [\"apple\", \"mango\", \"kiwi\"];\n\n"
   "// object = a set of named properties\nconst user = { name: \"Ada\", age: 36, admin: true };</code></pre>"
   "<p>Reading from them:</p>"
   "<pre class=\"code\"><code>fruits[0]        // \"apple\"   (index starts at 0)\n"
   "fruits.length    // 3\n"
   "user.name        // \"Ada\"\n"
   "user[\"age\"]    // 36</code></pre>"
   "<p>JavaScript lets you use dot notation for objects (<code>user.name</code>) as long as the "
   "key is a normal word with no spaces. If the key has a dash or a space you must use square "
   "brackets: <code>user[\"first-name\"]</code>.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Your brain already has this model. Just rename the boxes.</p>",
   "pairs": [
     {"py_label": "Python", "js_label": "JavaScript",
      "py": "fruits = [\"apple\", \"mango\", \"kiwi\"]\nlength = len(fruits)\nfirst = fruits[0]",
      "js": "const fruits = [\"apple\", \"mango\", \"kiwi\"];\nconst length = fruits.length;\n"
            "const first = fruits[0];"},
     {"py_label": "Python dict", "js_label": "JavaScript object",
      "py": "user = {\"name\": \"Ada\", \"age\": 36}",
      "js": "const user = { name: \"Ada\", age: 36 };"},
     {"py_label": "Python loop", "js_label": "JavaScript forEach",
      "py": "for f in fruits:\n    print(f)",
      "js": "fruits.forEach(function (f) {\n  console.log(f);\n});"},
     {"py_label": "Python list comprehension", "js_label": "JavaScript map",
      "py": "big = [f.upper() for f in fruits]",
      "js": "const big = fruits.map(function (f) {\n  return f.toUpperCase();\n});"},
   ]},

  {"type": "note", "title": "Three array methods that will do most of the work", "html":
   "<p>These three replace almost every loop you would write in Python:</p>"
   "<pre class=\"code\"><code>const nums = [1, 2, 3, 4, 5];\n\n"
   "// forEach: do something with each item (no return needed)\n"
   "nums.forEach(n => console.log(n * 2));\n\n"
   "// map: build a NEW array from each item\n"
   "const doubled = nums.map(n => n * 2);   // [2,4,6,8,10]\n\n"
   "// filter: keep only the items that pass a test\n"
   "const big = nums.filter(n => n > 3);     // [4,5]</code></pre>"
   "<p>Mental model: <code>map</code> and <code>filter</code> always give you a <strong>new "
   "array</strong>. They never change the original. That is why you usually write "
   "<code>const doubled = nums.map(...)</code> and use <code>doubled</code> afterwards.</p>"
   "<p>One important difference from Python: <code>map</code> and <code>filter</code> need a "
   "<strong>function</strong> as their argument. In Python you write <code>f.upper</code>, "
   "in JavaScript you write <code>f =&gt; f.toUpperCase()</code> (note the arrow).</p>"},

  {"type": "lab", "id": "js-arrays-lab", "title": "Lists of objects",
   "html": "<p>This is the shape you will meet constantly in the DOM: a list of objects, "
           "one object per row in a list.</p>",
   "starter": "const users = [\n  { name: \"Ada\", age: 36 },\n  { name: \"Alan\", age: 41 },\n"
              "  { name: \"Grace\", age: 45 },\n];\n\n"
              "// 1. print each name\nusers.forEach(u => console.log(u.name));\n\n"
              "// 2. build a new array of just the names\n"
              "const names = users.map(u => u.name);\nconsole.log(names);\n\n"
              "// 3. keep only the ones over 40\n"
              "const seniors = users.filter(u => u.age > 40);\nconsole.log(seniors.map(u => u.name));",
   "hints": [
     "Inside <code>forEach</code> or <code>map</code>, the arrow function's parameter "
     "(<code>u</code>) is one item from the array.",
     "<code>u.name</code> gets the <code>name</code> property off that item.",
     "You can chain: <code>users.filter(...).map(...)</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Using the same <code>users</code> array:</p>",
   "checks": [
     "Print <code>\"Ada is 36\"</code> for every user using <code>forEach</code> and a "
     "template literal.",
     "Build a new array of numbers: <code>[36, 41, 45]</code> using <code>map</code>.",
     "Find the total age with <code>reduce</code> or by adding up a <code>map</code> result. "
     "If <code>reduce</code> is new, do it with a plain <code>let total = 0</code> and "
     "<code>forEach</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "Array = list, Object = dict.",
     "<code>arr.length</code> replaces <code>len(arr)</code>.",
     "<code>forEach</code> (do), <code>map</code> (transform), <code>filter</code> (select).",
     "<code>map</code> and <code>filter</code> return a <strong>new</strong> array.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 4
{
 "id": "js-dom-tree",
 "title": "The DOM: your HTML, alive in memory",
 "lede": "This is the big one. When the browser reads your HTML it does not leave it as text. "
         "It builds a live tree of objects in memory. That tree is the DOM, and JavaScript "
         "talks to that tree.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>Open your browser's developer console (press <strong>F12</strong>) and type this in "
   "the Console tab:</p>"
   "<pre class=\"code\"><code>document</code></pre>"
   "<p>You will see a huge object. That is the entire page, as data. Every tag you wrote is "
   "now an object with properties you can read and change.</p>"
   "<p>It is called the <strong>DOM</strong> &mdash; <em>Document Object Model</em>. "
   "\"Model\" just means \"a structure that describes something\". The DOM is the model of your "
   "document.</p>"
   "<p>Three things to internalise:</p>"
   "<ul>"
   "<li><strong>It is a tree.</strong> The <code>&lt;body&gt;</code> is the root, tags are "
   "branches, text is the leaves.</li>"
   "<li><strong>It is live.</strong> Change it and the screen updates immediately. You never "
   "re-read the HTML file; you edit the tree that is already in memory.</li>"
   "<li><strong>Every element is an object</strong> with properties (<code>tagName</code>, "
   "<code>id</code>, <code>className</code>, <code>textContent</code>) and methods you can "
   "call on it.</li>"
   "</ul>"
   "<p>So the workflow is always the same two beats:</p>"
   "<ol>"
   "<li><strong>Find</strong> the element you want.</li>"
   "<li><strong>Change</strong> it.</li>"
   "</ol>"
   "<p>And you find elements with the same CSS selectors you already know, because "
   "<code>document.querySelector(\".card\")</code> is literally \"give me the first element "
   "matching this CSS selector\".</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Python has BeautifulSoup / lxml for HTML trees. JavaScript has this, built into the "
   "browser, always present, zero install.</p>",
   "pairs": [
     {"py_label": "Python (bs4)", "js_label": "JavaScript (browser)",
      "py": "soup = BeautifulSoup(html, \"html.parser\")\nh1 = soup.find(\"h1\")\nprint(h1.text)",
      "js": "const h1 = document.querySelector(\"h1\");\nconsole.log(h1.textContent);"},
     {"py_label": "Python (all matches)", "js_label": "JavaScript (browser)",
      "py": "for el in soup.select(\".item\"):\n    print(el.text)",
      "js": "document.querySelectorAll(\".item\").forEach(el => {\n  console.log(el.textContent);\n});"},
   ]},

  {"type": "demo", "id": "js-dom-tree-demo", "title": "find it, then change it",
   "html": "<p>Press the button. JavaScript finds the <code>&lt;h1&gt;</code> and rewrites its "
           "text &mdash; the page changes without reloading.</p>",
   "html_demo": """
     <h1 id="demo-title">I am the original heading</h1>
     <button id="demo-btn">Rewrite the heading</button>
     <pre class="out" id="js-dom-tree-demo-out"></pre>
   """,
   "js": """
     const btn = document.querySelector("#demo-btn");
     const title = document.querySelector("#demo-title");
     let count = 0;
     btn.addEventListener("click", function () {
       count = count + 1;
       title.textContent = "I was rewritten " + count + " time(s)";
       console.log("new heading:", title.textContent);
     });
   """},

  {"type": "lab", "id": "js-dom-tree-lab", "title": "Try to find elements yourself",
   "html": "<p>The demo area above is part of this page, so the lab can reach it too. "
           "Use <code>document.querySelector(...)</code> and <code>console.log(...)</code> to "
           "inspect it.</p>",
   "starter": "// The page has an h1#demo-title and a button#demo-btn\n\n"
              "const title = document.querySelector(\"#demo-title\");\n\n"
              "console.log(\"tag name:\", title.tagName);\n"
              "console.log(\"text:\", title.textContent);\n"
              "console.log(\"all headings:\", document.querySelectorAll(\"h1\").length);",
   "hints": [
     "<code>querySelector(\"#id\")</code> for an id, <code>querySelector(\".class\")</code> for a "
     "class, <code>querySelector(\"tag\")</code> for a tag name.",
     "<code>document.querySelectorAll(...)</code> finds <em>all</em> matches and gives you "
     "something with a <code>.length</code>.",
     "Try <code>document.body</code> and <code>document.title</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>In the lab:</p>",
   "checks": [
     "Find the <code>&lt;h1&gt;</code> and change its text with "
     "<code>textContent = \"something new\"</code>.",
     "Find the button and log its <code>textContent</code>.",
     "Log how many elements on the page match <code>\".card\"</code> "
     "(there may be none &mdash; that is a valid answer).",
   ]},

  {"type": "checkpoint", "items": [
     "The DOM is a live in-memory tree of the page, and JavaScript edits it directly.",
     "The pattern is always: <strong>find</strong> the element, then <strong>change</strong> it.",
     "<code>document</code> is the root of the tree.",
     "<code>querySelector</code> uses the same CSS selectors you already write.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 5
{
 "id": "js-events",
 "title": "Events: code that runs when something happens",
 "lede": "A page is not static. You click, you type, you scroll. Events are how the browser "
         "tells your code that something happened.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>The pattern in one line:</p>"
   "<pre class=\"code\"><code>element.addEventListener(\"click\", function (event) {\n"
   "  // this code runs every time the element is clicked\n});</code></pre>"
   "<p>Three pieces, all of them familiar:</p>"
   "<ul>"
   "<li><strong>Which element</strong> &mdash; the thing the user interacts with.</li>"
   "<li><strong>Which event</strong> &mdash; a name in quotes. <code>\"click\"</code>, "
   "<code>\"submit\"</code>, <code>\"input\"</code>, <code>\"keydown\"</code>, "
   "<code>\"mouseover\"</code>, <code>\"load\"</code>, <code>\"scroll\"</code>.</li>"
   "<li><strong>What to do</strong> &mdash; a function. The browser calls it for you, later, "
   "when the event actually happens.</li>"
   "</ul>"
   "<p>That third piece is a <strong>callback</strong>: you hand the browser a function and it "
   "keeps it, then calls it at the right moment. This is the single most important pattern in "
   "front-end work, so slow down and read the demo below.</p>"},

  {"type": "note", "title": "The event object", "html":
   "<p>When the browser calls your function it passes in an <strong>event object</strong> &mdash; "
   "a snapshot of what happened. You can use it:</p>"
   "<pre class=\"code\"><code>button.addEventListener(\"click\", function (event) {\n"
   "  console.log(event.type);              // \"click\"\n"
   "  console.log(event.target);            // the element clicked\n"
   "  console.log(event.clientX);           // mouse x position\n"
   "});</code></pre>"
   "<p><code>event.target</code> is the one you will use most. When you listen on a parent "
   "but the user actually clicked a child, <code>event.target</code> tells you the child. "
   "(More on that in Act 2.)</p>"
   "<p><code>event.preventDefault()</code> stops the browser's built-in behaviour. The one you "
   "will need: forms. By default, submitting a form reloads the whole page. One call to "
   "<code>preventDefault()</code> stops that.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Python has callbacks too (tkinter, asyncio). Same idea, different spelling.</p>",
   "pairs": [
     {"py_label": "Python (tkinter)", "js_label": "JavaScript (browser)",
      "py": "button.bind(\"<Button-1>\", on_click)\n\ndef on_click(event):\n    print(\"clicked!\")",
      "js": "button.addEventListener(\"click\", function (event) {\n  console.log(\"clicked!\");\n});"},
     {"py_label": "Python (no event object)", "js_label": "JavaScript (event object)",
      "py": "def on_click():\n    print(\"clicked!\")",
      "js": "function onClick(event) {\n  console.log(event.target);\n}"},
   ]},

  {"type": "demo", "id": "js-events-demo", "title": "A click counter",
   "html": "<p>Click the button a few times. The counter text updates live.</p>",
   "html_demo": """
     <p>You clicked <strong id="js-events-count">0</strong> times.</p>
     <button id="js-events-btn">Click me</button>
     <pre class="out" id="js-events-demo-out"></pre>
   """,
   "js": """
     const btn = document.getElementById("js-events-btn");
     const counter = document.getElementById("js-events-count");
     let clicks = 0;
     btn.addEventListener("click", function (event) {
       clicks = clicks + 1;
       counter.textContent = clicks;
       console.log("click #", clicks, "on", event.target.tagName);
     });
   """},

  {"type": "lab", "id": "js-events-lab", "title": "Attach your own listener",
   "html": "<p>The demo button is on the page with id <code>js-events-btn</code>. "
           "Attach your own listener and see what happens.</p>",
   "starter": "const btn = document.getElementById(\"js-events-btn\");\n\n"
              "btn.addEventListener(\"click\", function (event) {\n"
              "  // this runs on every click, on top of the demo's own listener\n"
              "  console.log(\"you clicked\", event.target.id);\n});\n\n"
              "console.log(\"listener attached\");",
   "hints": [
     "You can attach as many listeners as you like to the same element &mdash; they all run.",
     "<code>event.target</code> is the element the click landed on.",
     "Try <code>btn.addEventListener(\"mouseover\", ...)</code> as well.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Add a second button to the demo area (or use the existing one) and handle both "
           "with <strong>one</strong> listener attached to a shared parent.</p>",
   "checks": [
     "The parent listener uses <code>event.target</code> to work out <em>which</em> button "
     "was clicked.",
     "Log something different for each button.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>addEventListener(\"eventName\", function)</code> is the trigger pattern.",
     "The function you pass in is a callback &mdash; the browser stores it and calls it later.",
     "<code>event.target</code> = the element the event happened on.",
     "<code>event.preventDefault()</code> cancels the browser's default behaviour.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 6
{
 "id": "js-this-callbacks",
 "title": "this: the element that called you",
 "lede": "One small JavaScript rule that causes a lot of confusion: inside a callback, "
         "<code>this</code> means \"the element this event came from\". It is the closest thing "
         "JavaScript has to Python's <code>self</code>.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>When you attach a <strong>regular</strong> function with "
   "<code>function (event) { }</code>, JavaScript sets <code>this</code> for you: it points at "
   "the element the event came from.</p>"
   "<pre class=\"code\"><code>btn.addEventListener(\"click\", function (event) {\n"
   "  this.classList.add(\"clicked\");   // `this` === btn\n"
   "});</code></pre>"
   "<p>That is why you can write <code>this</code> instead of "
   "<code>document.querySelector(\"#btn\")</code>. Same thing, less typing.</p>"
   "<p><strong>But:</strong> arrow functions do <em>not</em> get their own <code>this</code>. "
   "An arrow function uses the <code>this</code> of the code around it. So this breaks:</p>"
   "<pre class=\"code\"><code>btn.addEventListener(\"click\", () => {\n"
   "  this.classList.add(\"clicked\");   // `this` is NOT btn here\n"
   "});</code></pre>"
   "<p>What to do about it? Two safe habits:</p>"
   "<ol>"
   "<li>Use <code>event.target</code> (or <code>event.currentTarget</code>) inside arrow "
   "functions.</li>"
   "<li>Or use a regular <code>function</code> when you want <code>this</code>.</li>"
   "</ol>"
   "<p>My advice for this course: <strong>prefer arrow functions + <code>event.target</code>"
   "</strong>. It is the most predictable style, and it is what React-style code looks like.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Same idea as <code>self</code>, different rules.</p>",
   "pairs": [
     {"py_label": "Python", "js_label": "JavaScript",
      "py": "class Button:\n    def on_click(self, event):\n        self.classList.add(\"clicked\")",
      "js": "btn.addEventListener(\"click\", function (event) {\n  this.classList.add(\"clicked\");\n});"},
     {"py_label": "Python (always bound)", "js_label": "JavaScript (arrow = not bound)",
      "py": "# self is always the instance\nself.do_thing()",
      "js": "btn.addEventListener(\"click\", () => {\n  // no `this` here -- use event.target\n  event.target.classList.add(\"clicked\");\n});"},
   ]},

  {"type": "demo", "id": "js-this-demo", "title": "this vs event.target",
   "html": "<p>Both buttons work. The first uses <code>this</code>, the second uses "
           "<code>event.target</code>. Try both &mdash; then try to break the arrow version.</p>",
   "html_demo": """
     <button id="this-btn-a">Regular function + this</button>
     <button id="this-btn-b">Arrow function + event.target</button>
     <button id="this-btn-c">Arrow function + this (broken)</button>
     <pre class="out" id="js-this-demo-out"></pre>
   """,
   "js": """
     const a = document.getElementById("this-btn-a");
     const b = document.getElementById("this-btn-b");
     const c = document.getElementById("this-btn-c");

     a.addEventListener("click", function () {
       this.classList.add("clicked");
       console.log("A: this ===", this.tagName, this.id);
     });

     b.addEventListener("click", (event) => {
       event.target.classList.add("clicked");
       console.log("B: target ===", event.target.tagName, event.target.id);
     });

     c.addEventListener("click", () => {
       console.log("C: is `this` the window?", this === window);
       console.log("C: is `this` the button?", this === event.currentTarget);
       console.log("C: this.classList is", this.classList, "<- arrow fn: no own `this`");
     });
   """},

  {"type": "note", "title": "A rule of thumb that will save you hours", "html":
   "<p>In browser code at the top level, <code>this</code> is basically the "
   "<code>window</code> object. Inside a normal callback it is the element. Inside an arrow "
   "function it is whatever it was outside. So:</p>"
   "<ul>"
   "<li>Normal function + <code>this</code> &rarr; the element. Useful.</li>"
   "<li>Arrow function + <code>this</code> &rarr; the window. Almost never what you want.</li>"
   "<li>Either way, <code>event.target</code> always works and always means the element the "
   "user touched.</li>"
   "</ul>"},

  {"type": "lab", "id": "js-this-lab", "title": "Compare the two styles",
   "html": "<p>Use the button <code>this-btn-a</code> from the demo area.</p>",
   "starter": "const a = document.getElementById(\"this-btn-a\");\n\n"
              "// style 1: regular function, use `this`\n"
              "a.addEventListener(\"click\", function () {\n"
              "  console.log(\"style 1, this is:\", this.id);\n"
              "});\n\n"
              "// style 2: arrow function, use event.target\n"
              "a.addEventListener(\"click\", (event) => {\n"
              "  console.log(\"style 2, target is:\", event.target.id);\n"
              "});\n\n"
              "console.log(\"two listeners attached - click the button above\");",
   "hints": [
     "Both listeners are attached to the same button, so both run on every click.",
     "Try <code>console.log(this === event.target)</code> inside the regular function.",
     "Then replace the regular function with an arrow function and see what breaks.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Attach one listener to <code>#this-btn-b</code> with an arrow function, and log "
           "the id of the button that was clicked. Then attach a second listener with a regular "
           "function and log <code>this.id</code>. Both should print the same id.</p>",
   "checks": [
     "Your arrow-function version uses <code>event.target.id</code>.",
     "Your regular-function version uses <code>this.id</code>.",
     "You can explain in one sentence why the arrow version cannot use <code>this</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "In a regular callback, <code>this</code> = the element the event came from.",
     "Arrow functions inherit <code>this</code> from the surrounding scope &mdash; so no "
     "element.",
     "<code>event.target</code> always works, regardless of function type.",
     "Default style for this course: arrow functions + <code>event.target</code>.",
  ]},
 ],
},
]
