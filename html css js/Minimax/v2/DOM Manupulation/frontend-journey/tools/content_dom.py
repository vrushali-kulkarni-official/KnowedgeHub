"""Act 2 - DOM Manipulation: find it, read it, build it, change it."""

STEPS = [

# ---------------------------------------------------------------- step 1
{
 "id": "dom-select",
 "title": "Finding elements: your CSS selectors, now useful",
 "lede": "You already know CSS selectors. Now they become a way of finding things on the page "
         "and holding on to them.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>JavaScript needs a <strong>reference</strong> to an element before it can change it. "
   "You get that reference with a query:</p>"
   "<pre class=\"code\"><code>document.querySelector(\"#my-id\")      // first match, or null\n"
   "document.querySelectorAll(\".my-class\") // ALL matches (a NodeList)\n"
   "document.getElementById(\"my-id\")    // by id only (fastest)</code></pre>"
   "<p>The selectors are exactly the ones from your CSS file:</p>"
   "<ul>"
   "<li><code>\"p\"</code> &mdash; tag name</li>"
   "<li><code>\".card\"</code> &mdash; class</li>"
   "<li><code>\"#header\"</code> &mdash; id</li>"
   "<li><code>\"nav a.active\"</code> &mdash; descendant (a tag inside nav, with class "
   "<code>active</code>)</li>"
   "<li><code>\"input[type='text']\"</code> &mdash; attribute</li>"
   "<li><code>\".card:first-child\"</code> &mdash; pseudo-classes work too</li>"
   "</ul>"
   "<p><strong>One match vs many.</strong> <code>querySelector</code> returns the "
   "<em>first</em> match, or <code>null</code> if there is none. "
   "<code>querySelectorAll</code> returns a <em>NodeList</em> &mdash; a list-like object with "
   "<code>.length</code> and index access.</p>"
   "<p><strong>The null trap.</strong> If you ask for something that is not there you get "
   "<code>null</code>, and <code>null.something</code> throws an error. If you write code "
   "before the element exists in your HTML, you get a blank page and a red error. "
   "<strong>Put your script at the end of the body</strong>, or wrap it in "
   "<code>DOMContentLoaded</code>. We will do the second one properly in Step 7.</p>"},

  {"type": "note", "title": "Turn a NodeList into a real array", "html":
   "<p>A NodeList is array-like but it does not have every array method. When you want "
   "<code>.map</code>, <code>.filter</code> or <code>.forEach</code> on it, convert it:</p>"
   "<pre class=\"code\"><code>const items = document.querySelectorAll(\".item\");\n\n"
   "items.forEach(el => { ... });          // forEach exists, fine\n\n"
   "const arr = Array.from(items);        // now it is a real Array\n"
   "arr.map(el => el.textContent);</code></pre>"
   "<p>Good news: <code>forEach</code>, <code>map</code> and <code>filter</code> all work "
   "directly on a NodeList in modern browsers, so you will rarely need to convert it.</p>"},

  {"type": "demo", "id": "dom-select-demo", "title": "Three ways to find the same thing",
   "html": "<p>There is one card with id <code>only-card</code> and class "
           "<code>card highlight</code>, and three plain <code>.item</code> list rows. "
           "Press a button to query each way.</p>",
   "html_demo": """
     <ul id="dom-select-list">
       <li class="item">Item one</li>
       <li class="item">Item two</li>
       <li class="item">Item three</li>
     </ul>
     <div id="only-card" class="card highlight">I am the only card.</div>
     <button id="dom-select-btn">Run queries</button>
     <pre class="out" id="dom-select-demo-out"></pre>
   """,
   "js": """
     const btn = document.getElementById("dom-select-btn");
     btn.addEventListener("click", function () {
       console.log("by id:", document.getElementById("only-card").textContent);
       console.log("by class (first):", document.querySelector(".card").textContent);
       console.log("count of .item:", document.querySelectorAll(".item").length);

       const texts = Array.from(document.querySelectorAll(".item")).map(li => li.textContent);
       console.log("all item texts:", texts);

       const missing = document.querySelector(".does-not-exist");
       console.log("missing element is:", missing);
     });
   """},

  {"type": "lab", "id": "dom-select-lab", "title": "Query the demo area",
   "html": "<p>The demo list has id <code>dom-select-list</code> and its rows have class "
           "<code>item</code>.</p>",
   "starter": "// 1. how many .item rows are there?\n"
              "console.log(document.querySelectorAll(\".item\").length);\n\n"
              "// 2. what is the text of the SECOND row?\n"
              "const rows = document.querySelectorAll(\".item\");\n"
              "console.log(rows[1].textContent);\n\n"
              "// 3. find the <ul> by id and log its tagName\n"
              "console.log(document.getElementById(\"dom-select-list\").tagName);",
   "hints": [
     "A NodeList behaves like an array: <code>rows[0]</code>, <code>rows.length</code>.",
     "Indexes start at <code>0</code>. So the second row is <code>rows[1]</code>.",
     "To get every row's text at once, use "
     "<code>Array.from(rows).map(r => r.textContent)</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Using the demo area:</p>",
   "checks": [
     "Log the text of the <strong>last</strong> <code>.item</code> row.",
     "Log the tag name of the first row, like <code>\"LI\"</code>.",
     "Find every element inside the list and log how many there are "
     "(hint: <code>document.querySelectorAll(\"#dom-select-list li\")</code>).",
   ]},

  {"type": "checkpoint", "items": [
     "<code>querySelector</code> = first match or <code>null</code>. "
     "<code>querySelectorAll</code> = a list of matches.",
     "The selectors are the same CSS selectors you already write.",
     "Always check for <code>null</code> if the element might not be there.",
     "<code>getElementById</code> is the fast path for ids.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 2
{
 "id": "dom-read-write",
 "title": "Reading and writing what is on the page",
 "lede": "Three properties do most of the talking: <code>textContent</code> for text, "
         "<code>innerHTML</code> for HTML inside, and <code>value</code> for what the user typed.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<pre class=\"code\"><code>const h1 = document.querySelector(\"h1\");\n\n"
   "h1.textContent          // READ: the text inside it\n"
   "h1.textContent = \"New\"  // WRITE: replaces the text\n\n"
   "h1.innerHTML            // READ/WRITE: the HTML inside it\n\n"
   "const input = document.querySelector(\"input\");\n"
   "input.value             // what the user has typed right now</code></pre>"
   "<p>Each one is a different door into the same element:</p>"
   "<ul>"
   "<li><code>textContent</code> &mdash; plain text only. Tags in the string come out as literal "
   "characters. <strong>This is your default tool.</strong></li>"
   "<li><code>innerHTML</code> &mdash; real HTML. If you write <code>\"<b>hi</b>\"</code> into "
   "it, you get bold text. If the string came from a user, that is a security hole "
   "(more on that in Act 3).</li>"
   "<li><code>value</code> &mdash; only for <code>&lt;input&gt;</code>, "
   "<code>&lt;textarea&gt;</code> and <code>&lt;select&gt;</code>. This is the live value the "
   "user is editing.</li>"
   "</ul>"
   "<p>Also worth knowing: <code>textContent</code> is <em>fast</em> and safe. "
   "<code>innerText</code> exists too but it depends on layout (it reflects what is visually "
   "visible) which makes it slow and surprising. Use <code>textContent</code>.</p>"},

  {"type": "note", "title": "The rule that saves you from bugs", "html":
   "<p><strong>Read with <code>textContent</code>, write with <code>textContent</code>, "
   "unless you genuinely need HTML inside.</strong></p>"
   "<p>Why? <code>innerHTML</code> re-parses the string as HTML every single time you set it. "
   "That is slower, it wipes out any event listeners you attached to the children, and it "
   "opens the door to XSS.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Same job, different tool.</p>",
   "pairs": [
     {"py_label": "Python (bs4)", "js_label": "JavaScript (DOM)",
      "py": "text = h1.get_text()\nh1.string = \"New\"",
      "js": "const text = h1.textContent;\nh1.textContent = \"New\";"},
     {"py_label": "Python (raw html)", "js_label": "JavaScript (raw html)",
      "py": "html = h1.decode_contents()",
      "js": "const html = h1.innerHTML;"},
     {"py_label": "Python (form value)", "js_label": "JavaScript (form value)",
      "py": "value = request.form[\"name\"]",
      "js": "const value = input.value;"},
   ]},

  {"type": "demo", "id": "dom-read-write-demo", "title": "Copy text from one place to another",
   "html": "<p>Press the button: it reads the heading's text and writes it into the paragraph "
           "below, then updates the heading too.</p>",
   "html_demo": """
     <h2 id="rw-source">Original heading</h2>
     <p id="rw-target">Nothing here yet.</p>
     <input id="rw-input" placeholder="type something..." />
     <button id="rw-btn">Copy heading into paragraph</button>
     <pre class="out" id="dom-read-write-demo-out"></pre>
   """,
   "js": """
     const btn = document.getElementById("rw-btn");
     const source = document.getElementById("rw-source");
     const target = document.getElementById("rw-target");
     const input = document.getElementById("rw-input");

     btn.addEventListener("click", function () {
       const text = source.textContent;          // read
       target.textContent = text;                // write
       source.textContent = text + " (edited)";  // write again
       console.log("copied:", text);
       console.log("input currently holds:", input.value);
     });
   """},

  {"type": "lab", "id": "dom-read-write-lab", "title": "Read and write",
   "html": "<p>Use the demo elements: <code>rw-source</code>, <code>rw-target</code>, "
           "<code>rw-input</code>.</p>",
   "starter": "const source = document.getElementById(\"rw-source\");\n"
              "const target = document.getElementById(\"rw-target\");\n\n"
              "// read the heading and print it\n"
              "console.log(\"source says:\", source.textContent);\n\n"
              "// now write your own text into the paragraph\n"
              "target.textContent = \"I wrote this from JavaScript\";\n\n"
              "console.log(\"target now says:\", target.textContent);",
   "hints": [
     "You can read and write the same property: <code>target.textContent</code> on the right "
     "of <code>=</code> is a write, on the left it is a read.",
     "To read what the user typed: <code>document.getElementById(\"rw-input\").value</code>.",
     "Try <code>source.innerHTML</code> as well and compare with <code>textContent</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Make the paragraph show the heading text, and then make it show the heading text "
           "plus whatever is in the input box.</p>",
   "checks": [
     "You read the heading into a variable first (you did not read it twice).",
     "You read the input with <code>.value</code> and use a template literal to join the two "
     "pieces.",
     "Bonus: if the input is empty, the paragraph should still show the heading text.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>textContent</code> = plain text, safe, fast. Your default.",
     "<code>innerHTML</code> = raw HTML. Slow, wipes listeners, XSS risk.",
     "<code>value</code> = what the user typed (inputs, textareas, selects).",
     "Reading and writing use the same property name.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 3
{
 "id": "dom-create-append",
 "title": "Building new elements",
 "lede": "So far we only changed things that already existed. Now we make new ones. "
         "It is always a two-step dance: create the element, then insert it.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>Step one &mdash; create. This makes a brand new element in memory. "
   "<strong>It is not on the screen yet.</strong></p>"
   "<pre class=\"code\"><code>const li = document.createElement(\"li\");\n"
   "li.textContent = \"Buy milk\";\n"
   "li.className = \"todo\";</code></pre>"
   "<p>Step two &mdash; insert. You say <em>where</em> it should go.</p>"
   "<pre class=\"code\"><code>const ul = document.querySelector(\"#list\");\n"
   "ul.append(li);            // add at the end (inside ul)\n"
   "ul.prepend(li);           // add at the start\n"
   "li.before(other);         // add as a sibling, before me\n"
   "li.after(other);          // add as a sibling, after me\n\n"
   "ul.appendChild(li);       // older way, same result as append</code></pre>"
   "<p>Only after the insert does the element appear on the page. Until then it exists in "
   "memory but is invisible. This is called a <strong>detached</strong> element.</p>"
   "<p><strong>Why do it in two steps?</strong> Because it lets you build the whole element "
   "&mdash; set its text, its class, its attributes, even attach a listener to it &mdash; "
   "before it goes anywhere near the screen. Then it appears fully formed, in one move.</p>"},

  {"type": "bridge", "title": "Python &#8594; JavaScript", "html":
   "<p>Same two-step idea, different words.</p>",
   "pairs": [
     {"py_label": "Python (bs4)", "js_label": "JavaScript (DOM)",
      "py": "li = soup.new_tag(\"li\")\nli.string = \"Buy milk\"\nul.append(li)",
      "js": "const li = document.createElement(\"li\");\nli.textContent = \"Buy milk\";\n"
            "ul.append(li);"},
     {"py_label": "Python (lxml)", "js_label": "JavaScript (DOM)",
      "py": "li = etree.Element(\"li\")\nli.text = \"Buy milk\"\nul.append(li)",
      "js": "const li = document.createElement(\"li\");\nli.textContent = \"Buy milk\";\n"
            "ul.append(li);"},
   ]},

  {"type": "demo", "id": "dom-create-append-demo", "title": "Add list items",
   "html": "<p>Type a task, press the button (or Enter). Each task is created as a new "
           "<code>&lt;li&gt;</code> and appended to the list. Notice the list lives in "
           "<code>ul#demo-list</code>.</p>",
   "html_demo": """
     <ul id="demo-list"></ul>
     <input id="demo-task" placeholder="a task..." />
     <button id="demo-add">Add task</button>
     <pre class="out" id="dom-create-append-demo-out"></pre>
   """,
   "js": """
     const input = document.getElementById("demo-task");
     const list = document.getElementById("demo-list");
     const addBtn = document.getElementById("demo-add");

     function addTask() {
       const text = input.value.trim();
       if (text === "") return;

       const li = document.createElement("li");   // 1. create
       li.textContent = text;                     //    dress it
       li.className = "task";                     //    dress it
       list.append(li);                           // 2. insert

       input.value = "";
       console.log("added:", li.textContent, "| children now:", list.children.length);
     }

     addBtn.addEventListener("click", addTask);
     input.addEventListener("keydown", function (e) {
       if (e.key === "Enter") addTask();
     });
   """},

  {"type": "lab", "id": "dom-create-append-lab", "title": "Create one yourself",
   "html": "<p>The demo list is <code>demo-list</code>. Create an element and insert it.</p>",
   "starter": "const list = document.getElementById(\"demo-list\");\n\n"
              "// 1. create a paragraph element\n"
              "const p = document.createElement(\"p\");\n\n"
              "// 2. put some text in it\n"
              "p.textContent = \"I was created by JavaScript\";\n\n"
              "// 3. add it to the end of the list\n"
              "list.append(p);\n\n"
              "console.log(\"list children:\", list.children.length);",
   "hints": [
     "<code>document.createElement(\"p\")</code> creates it, but it stays invisible until you "
     "insert it.",
     "<code>list.append(p)</code> puts it inside the list at the end.",
     "Try <code>list.prepend(p)</code> instead to see the difference.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Write a function <code>addItem(text)</code> that creates a list item and appends "
           "it to <code>#demo-list</code>. Then call it three times.</p>",
   "checks": [
     "The function takes the text as a parameter (not a hard-coded string).",
     "Each new <code>&lt;li&gt;</code> has its text set with <code>textContent</code>.",
     "Bonus: give every item the class <code>\"task\"</code> using <code>className</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>document.createElement(\"tag\")</code> makes a detached element.",
     "It is invisible until you insert it with <code>append</code> / <code>prepend</code> / "
     "<code>before</code> / <code>after</code>.",
     "Dress the element fully <em>before</em> inserting it.",
     "<code>parent.children</code> gives you the child elements.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 4 (new)
{
 "id": "dom-remove-replace",
 "title": "Removing and replacing elements",
 "lede": "Things have to be able to leave. Learn to delete an element, swap one for another, "
         "duplicate a row, and wipe a whole container.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<pre class=\"code\"><code>el.remove();                 // delete it\n"
   "el.replaceWith(other);       // swap it for something else\n"
   "el.replaceChildren(a, b, c); // replace all its children\n"
   "el.innerHTML = \"\";          // wipe the inside (leaves el itself)\n\n"
   "const copy = el.cloneNode(true);  // duplicate (true = with children)\n"
   "el.after(copy);                   // put the copy next to it</code></pre>"
   "<p>The difference between <code>remove()</code> and <code>innerHTML = \"\"</code> is worth "
   "being precise about:</p>"
   "<ul>"
   "<li><code>el.remove()</code> deletes <strong>the element itself</strong> from its parent.</li>"
   "<li><code>el.innerHTML = \"\"</code> deletes everything <strong>inside</strong> it, but "
   "<code>el</code> stays.</li>"
   "</ul>"
   "<p><code>cloneNode(true)</code> copies an element <em>with</em> its children; "
   "<code>cloneNode(false)</code> copies only the empty shell. The copy is detached until you "
   "insert it.</p>"
   "<p><strong>One warning about <code>innerHTML = \"\"</code>:</strong> it destroys every "
   "child element, including any listeners you attached to them. If you have a row with a "
   "click handler and you wipe the list with <code>innerHTML = \"\"</code>, the handler is gone. "
   "That is exactly why the state-and-render pattern from the last step uses "
   "<code>render()</code> &mdash; it rebuilds everything from scratch each time.</p>"},

  {"type": "note", "title": "Why removing things is a skill, not a detail", "html":
   "<p>Two real reasons to get good at this:</p>"
   "<ul>"
   "<li><strong>Memory.</strong> A removed element that is still referenced somewhere keeps "
   "its listeners and data alive. Remove it properly and let it go.</li>"
   "<li><strong>Correctness.</strong> If you delete a row from the screen but not from your "
   "data array, the next render brings it back. Delete from the data, then render.</li>"
   "</ul>"},

  {"type": "demo", "id": "dom-remove-replace-demo", "title": "Add, duplicate, delete",
   "html": "<p>Add rows, duplicate one, delete one. Every operation is visible in the console.</p>",
   "html_demo": """
     <ul id="rr-list"></ul>
     <button id="rr-add">Add row</button>
     <button id="rr-dup">Duplicate last row</button>
     <button id="rr-del">Delete last row</button>
     <button id="rr-clear">Clear all</button>
     <pre class="out" id="dom-remove-replace-demo-out"></pre>
   """,
   "js": """
     const list = document.getElementById("rr-list");
     let n = 0;

     document.getElementById("rr-add").addEventListener("click", function () {
       n = n + 1;
       const li = document.createElement("li");
       li.textContent = "Row " + n;
       list.append(li);
       console.log("added row", n);
     });

     document.getElementById("rr-dup").addEventListener("click", function () {
       const last = list.lastElementChild;
       if (!last) { console.log("nothing to duplicate"); return; }
       const copy = last.cloneNode(true);
       copy.textContent = last.textContent + " (copy)";
       last.after(copy);                     // insert the copy next to it
       console.log("duplicated:", last.textContent);
     });

     document.getElementById("rr-del").addEventListener("click", function () {
       const last = list.lastElementChild;
       if (!last) { console.log("nothing to delete"); return; }
       last.remove();
       console.log("deleted. rows left:", list.children.length);
     });

     document.getElementById("rr-clear").addEventListener("click", function () {
       list.innerHTML = "";                 // wipe the inside, keep the <ul>
       console.log("cleared. the <ul> is still here:", !!list);
     });
   """},

  {"type": "lab", "id": "dom-remove-replace-lab", "title": "Try removing things",
   "html": "<p>The demo list is <code>rr-list</code>.</p>",
   "starter": "const list = document.getElementById(\"rr-list\");\n\n"
              "// add a row\n"
              "const li = document.createElement(\"li\");\n"
              "li.textContent = \"first row\";\n"
              "list.append(li);\n\n"
              "// now remove it again\n"
              "li.remove();\n"
              "console.log(\"rows left:\", list.children.length);\n\n"
              "// try replaceWith: swap the <ul>'s only child for a <p>\n"
              "const p = document.createElement(\"p\");\n"
              "p.textContent = \"I replaced the list\";\n"
              "list.replaceWith(p);\n"
              "console.log(\"the ul is gone?\", !document.getElementById(\"rr-list\"));",
   "hints": [
     "<code>remove()</code> takes the element out of the DOM but the variable still points at "
     "it.",
     "<code>replaceWith</code> puts the new element exactly where the old one was.",
     "<code>cloneNode(true)</code> copies children too &mdash; try cloning a row that has a "
     "class.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Write a function <code>deleteRow(index)</code> that removes the row at that "
           "position from the list.</p>",
   "checks": [
     "You find the row with <code>list.children[index]</code>.",
     "You check that it exists before removing it (otherwise you get "
     "<code>undefined.remove()</code> and a red error).",
     "Bonus: use <code>cloneNode(true)</code> to duplicate a row before deleting it.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>el.remove()</code> deletes the element; <code>el.innerHTML = \"\"</code> empties it.",
     "<code>el.replaceWith(other)</code> swaps one element for another.",
     "<code>cloneNode(true)</code> copies an element with its children.",
     "Removing from the DOM is not the same as removing from your data array. Do both.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 5
{
 "id": "dom-attributes-classes-styles",
 "title": "Attributes, classes and inline styles",
 "lede": "Changing text is only half of it. Often you need to change how an element looks or "
         "what it means to a screen reader. Three tools: attributes, classList, style.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<h4>1. Attributes</h4>"
   "<p>Any HTML attribute can be read or written:</p>"
   "<pre class=\"code\"><code>el.getAttribute(\"src\")        // read\n"
   "el.setAttribute(\"src\", \"cat.jpg\")   // write\n"
   "el.hasAttribute(\"disabled\")          // true / false\n"
   "el.removeAttribute(\"disabled\")\n\n"
   "// shortcuts for the common ones:\n"
   "el.id = \"main\";\nel.title = \"a tooltip\";\n"
   "el.src = \"cat.jpg\";</code></pre>"
   "<p><strong>data- attributes</strong> have their own shortcut, <code>dataset</code>:</p>"
   "<pre class=\"code\"><code>// HTML: &lt;div data-user-id=\"42\"&gt;\n"
   "el.dataset.userId        // \"42\"   (camelCase in JS, dashes in HTML)</code></pre>"
   "<h4>2. Classes &mdash; use classList</h4>"
   "<pre class=\"code\"><code>el.classList.add(\"active\");\n"
   "el.classList.remove(\"active\");\n"
   "el.classList.toggle(\"active\");   // add if absent, remove if present\n"
   "el.classList.contains(\"active\");  // true / false</code></pre>"
   "<p>You could do <code>el.className = \"a b c\"</code>, but that <strong>replaces</strong> "
   "the whole class list. <code>classList.add()</code> changes one class and leaves the others "
   "alone. Always use <code>classList</code>.</p>"
   "<h4>3. Inline styles</h4>"
   "<pre class=\"code\"><code>el.style.color = \"red\";\n"
   "el.style.backgroundColor = \"#111\";\n"
   "el.style.display = \"none\";</code></pre>"
   "<p><code>style</code> only touches the <em>inline</em> style. It cannot read your CSS file's "
   "rules. For anything visual, prefer adding a class and letting CSS decide what that class "
   "looks like &mdash; that keeps the styling in one place.</p>"},

  {"type": "note", "title": "Why classes beat inline styles", "html":
   "<p>Compare these two:</p>"
   "<pre class=\"code\"><code>// the DOM way\n"
   "el.style.backgroundColor = \"coral\";\n\n"
   "// the CSS way (much better)\n"
   "el.classList.add(\"is-highlighted\");\n\n"
   "// CSS file:\n"
   "/* .is-highlighted { background-color: coral; } */</code></pre>"
   "<p>The second version lets you restyle everything from one place, supports hover states and "
   "animations, and keeps JavaScript focused on <em>what</em> is happening rather than "
   "<em>how</em> it looks. Your CSS brain will thank you.</p>"},

  {"type": "demo", "id": "dom-attributes-demo", "title": "Toggle a class, change an attribute",
   "html": "<p>The button toggles the <code>active</code> class on the box and swaps a "
           "<code>data-state</code> attribute. The box is styled by CSS classes in this page.</p>",
   "html_demo": """
     <div id="attr-box" class="box" data-state="idle">I am a box</div>
     <button id="attr-btn">Toggle</button>
     <pre class="out" id="dom-attributes-demo-out"></pre>
   """,
   "js": """
     const box = document.getElementById("attr-box");
     const btn = document.getElementById("attr-btn");

     btn.addEventListener("click", function () {
       box.classList.toggle("active");
       box.setAttribute("data-state", box.classList.contains("active") ? "active" : "idle");
       console.log("class list:", box.className);
       console.log("data-state:", box.getAttribute("data-state"));
       console.log("dataset.state:", box.dataset.state);
     });
   """},

  {"type": "lab", "id": "dom-attributes-lab", "title": "Try the tools",
   "html": "<p>Use the demo box <code>attr-box</code> and button <code>attr-btn</code>.</p>",
   "starter": "const box = document.getElementById(\"attr-box\");\n\n"
              "console.log(\"current classes:\", box.className);\n"
              "console.log(\"contains active?\", box.classList.contains(\"active\"));\n\n"
              "// try each of these, then log the results\n"
              "box.classList.add(\"active\");\n"
              "box.setAttribute(\"data-user-id\", \"42\");\n"
              "box.style.color = \"coral\";\n\n"
              "console.log(\"classes now:\", box.className);\n"
              "console.log(\"dataset:\", box.dataset);",
   "hints": [
     "<code>box.className</code> reads all classes as one space-separated string.",
     "<code>box.dataset</code> gives you an object of all <code>data-*</code> attributes.",
     "Watch <code>classList.toggle</code> flip the class on and off each time you run it.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Make the demo button change the box's text to show its state, and give the box a "
           "<code>title</code> attribute (that is the little tooltip in the browser).</p>",
   "checks": [
     "You use <code>classList.toggle</code> (not <code>className =</code>) so other classes "
     "survive.",
     "The box's text updates to match its state.",
     "The <code>title</code> attribute changes too &mdash; read it back with "
     "<code>getAttribute(\"title\")</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>getAttribute</code> / <code>setAttribute</code> for any attribute; "
     "<code>dataset</code> for <code>data-*</code>.",
     "<code>classList.add / remove / toggle / contains</code> for classes.",
     "<code>el.style.x = y</code> for inline styles &mdash; prefer classes in CSS.",
     "Never overwrite <code>className</code> with <code>=</code> unless you mean to wipe every "
     "class.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 4.5 (bridge)
{
 "id": "dom-xss",
 "title": "The innerHTML trap (and how to stay safe)",
 "lede": "A short, important detour. This is the one rule that separates a working page from a "
         "vulnerable one.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>Look at these two lines. They look similar. They are not.</p>"
   "<pre class=\"code\"><code>el.textContent = userInput;   // SAFE: the input is treated as text\n"
   "el.innerHTML = userInput;     // RISKY: the input is parsed as HTML</code></pre>"
   "<p>If <code>userInput</code> is <code>\"&lt;img src=x onerror=alert('hacked')&gt;\"</code>:</p>"
   "<ul>"
   "<li>With <code>textContent</code> the user literally sees that text on the page. Boring, "
   "safe.</li>"
   "<li>With <code>innerHTML</code> the browser builds a real <code>&lt;img&gt;</code> element "
   "and fires the <code>onerror</code> handler. The script runs. That is a cross-site scripting "
   "(XSS) attack.</li>"
   "</ul>"
   "<p><strong>The rule:</strong> whenever the string came from a user (or from a server, or "
   "from anywhere you did not write yourself), use <code>textContent</code>. Only use "
   "<code>innerHTML</code> with HTML you authored yourself.</p>"},

  {"type": "note", "title": "There is a safe middle path", "html":
   "<p>Sometimes you really do want to insert HTML you built from trusted pieces. Then build "
   "the elements instead of parsing a string:</p>"
   "<pre class=\"code\"><code>const span = document.createElement(\"span\");\n"
   "span.textContent = userInput;      // safe\n"
   "span.className = \"user-name\";     // safe\n"
   "container.append(span);            // safe</code></pre>"
   "<p>That is exactly what <code>innerHTML</code> does internally, minus the risk.</p>"},

  {"type": "demo", "id": "dom-xss-demo", "title": "See the difference",
   "html": "<p>Type a tag into the box and press the buttons. One is safe, one is not.</p>",
   "html_demo": """
     <input id="xss-input" value="&lt;b&gt;hello&lt;/b&gt;" />
     <button id="xss-safe">textContent (safe)</button>
     <button id="xss-raw">innerHTML (risky)</button>
     <div id="xss-target">target</div>
     <pre class="out" id="dom-xss-demo-out"></pre>
   """,
   "js": """
     const input = document.getElementById("xss-input");
     const target = document.getElementById("xss-target");

     document.getElementById("xss-safe").addEventListener("click", function () {
       target.textContent = input.value;
       console.log("safe write done");
     });

     document.getElementById("xss-raw").addEventListener("click", function () {
       target.innerHTML = input.value;
       console.log("raw write done (only safe because this page has no script that an "
         + "injected tag could call)");
     });
   """},

  {"type": "checkpoint", "items": [
     "User data goes in through <code>textContent</code>, never <code>innerHTML</code>.",
     "<code>innerHTML</code> parses HTML. <code>textContent</code> does not.",
     "Building elements with <code>createElement</code> is the safe way to insert rich content.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 6
{
 "id": "dom-traverse",
 "title": "Walking the tree: parents, children, siblings",
 "lede": "Sometimes you do not know the selector &mdash; you only know where the click happened. "
         "The DOM gives you ways to move up, down and sideways.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<pre class=\"code\"><code>el.parentElement        // the element's parent\n"
   "el.children            // list of child ELEMENTS (not text nodes)\n"
   "el.firstElementChild   // first child element\n"
   "el.lastElementChild    // last child element\n"
   "el.nextElementSibling  // the next element after me\n"
   "el.previousElementSibling\n"
   "el.closest(\".card\")   // the nearest ancestor (or me) matching this selector</code></pre>"
   "<p>Two words to be careful about:</p>"
   "<ul>"
   "<li><code>children</code> vs <code>childNodes</code>. <code>children</code> gives you only "
   "<em>elements</em>. <code>childNodes</code> also gives you text nodes (the whitespace "
   "between your tags!), which is almost never what you want.</li>"
   "<li><code>parentElement</code> vs <code>parentNode</code>. Same idea: "
   "<code>parentElement</code> skips the <code>&lt;body&gt;</code> / <code>&lt;html&gt;</code> "
   "special case. Prefer <code>parentElement</code>.</li>"
   "</ul>"
   "<p><code>closest()</code> is the star of this step. It walks <em>up</em> the tree from the "
   "element you give it until it finds one that matches your selector. You will use it for "
   "event delegation in the next step.</p>"},

  {"type": "demo", "id": "dom-traverse-demo", "title": "Click anywhere in a card",
   "html": "<p>Each card has a title, a body and a small tag. Click the tag, the body or the "
           "title &mdash; the whole card reacts, because we walk <em>up</em> from the click.</p>",
   "html_demo": """
     <div class="card" id="card-1">
       <h4>Card title</h4>
       <p>Some body text.</p>
       <span class="tag">a tag</span>
     </div>
     <div class="card" id="card-2">
       <h4>Another card</h4>
       <p>More body text.</p>
       <span class="tag">a tag</span>
     </div>
     <pre class="out" id="dom-traverse-demo-out"></pre>
   """,
   "js": """
     document.querySelectorAll(".card").forEach(function (card) {
       card.addEventListener("click", function (event) {
         const target = event.target;          // what was clicked
         const owner = target.closest(".card"); // walk up to the card

         owner.classList.toggle("selected");
         console.log("clicked <" + target.tagName.toLowerCase() + ">",
                     "inside card #" + owner.id);
       });
     });
   """},

  {"type": "lab", "id": "dom-traverse-lab", "title": "Explore the tree",
   "html": "<p>Use the demo cards. Card 1 has id <code>card-1</code>.</p>",
   "starter": "const card = document.getElementById(\"card-1\");\n"
              "const title = card.querySelector(\"h4\");\n\n"
              "console.log(\"children of card:\", card.children.length);\n"
              "console.log(\"first child tag:\", card.firstElementChild.tagName);\n"
              "console.log(\"parent of title:\", title.parentElement.id);\n"
              "console.log(\"closest .card from title:\", title.closest(\".card\").id);\n\n"
              "// who is my next sibling?\n"
              "console.log(\"next sibling:\", title.nextElementSibling.tagName);",
   "hints": [
     "<code>children</code> is a live list &mdash; it is an HTMLCollection, not a plain array.",
     "<code>closest()</code> starts at the element itself and walks up, so "
     "<code>title.closest(\".card\")</code> finds the card that contains the title.",
     "Try <code>card.querySelectorAll(\"*\")</code> to list every descendant element.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Without using <code>closest</code>, find the <code>&lt;h4&gt;</code> text of the "
           "card that a clicked element belongs to.</p>",
   "checks": [
     "You start from the clicked element and walk <strong>up</strong> with "
     "<code>parentElement</code> until you hit a card.",
     "Then you read the card's title.",
     "Then confirm the <strong>short</strong> way with <code>closest(\".card\")</code>.",
   ]},

  {"type": "checkpoint", "items": [
     "<code>parentElement</code>, <code>children</code>, <code>nextElementSibling</code> &mdash; "
     "move around the tree.",
     "<code>closest(selector)</code> walks up until it finds a match. Super useful.",
     "<code>children</code> = elements only. <code>childNodes</code> includes text.",
     "<code>querySelector</code> on an element searches that element's subtree only.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 7
{
 "id": "dom-events-deep",
 "title": "Event delegation, forms and the keyboard",
 "lede": "Three practical event patterns: listening on the parent instead of every child, "
         "handling form submit without reloading the page, and reacting to Enter.",
 "blocks": [
  {"type": "idea", "title": "1. Event delegation", "html":
   "<p>Clicking a button makes the event travel <strong>up</strong> the tree, from the button "
   "to its parent, to its grandparent, all the way to <code>document</code>. This is called "
   "<strong>bubbling</strong>.</p>"
   "<p>So you can listen on the <em>parent</em> once, and catch clicks on every child:</p>"
   "<pre class=\"code\"><code>list.addEventListener(\"click\", function (event) {\n"
   "  const item = event.target.closest(\"li\");\n"
   "  if (!item) return;          // clicked something that is not an li\n"
   "  item.remove();\n"
   "});</code></pre>"
   "<p><strong>Why bother?</strong> Three reasons:</p>"
   "<ul>"
   "<li>One listener instead of fifty. Cleaner and faster.</li>"
   "<li>It keeps working when new children are added later. If you attached a listener to "
   "each <code>&lt;li&gt;</code>, a new <code>&lt;li&gt;</code> would have no listener.</li>"
   "<li>It is exactly what React does under the hood &mdash; one listener at the root.</li>"
   "</ul>"
   "<p><code>event.target</code> is the element clicked. <code>event.currentTarget</code> is the "
   "element you attached the listener to. With delegation you need both: "
   "<code>target</code> to know <em>what</em> was clicked, and you already know "
   "<code>currentTarget</code> because it is the parent you attached to.</p>"},

  {"type": "idea", "title": "2. Forms", "html":
   "<p>A form has a special <code>submit</code> event. By default the browser sends the data "
   "to a server and reloads the page. For a single-page app you do not want that.</p>"
   "<pre class=\"code\"><code>form.addEventListener(\"submit\", function (event) {\n"
   "  event.preventDefault();          // stop the page reload\n\n"
   "  const text = form.querySelector(\"input\").value;\n"
   "  // ... do something with text\n"
   "  form.reset();                    // clear the fields\n"
   "});</code></pre>"
   "<p>Two details that trip everyone up:</p>"
   "<ul>"
   "<li>Without <code>preventDefault()</code>, the page reloads and your JavaScript state is "
   "gone.</li>"
   "<li>The <code>submit</code> event fires when the user presses Enter in a text field too, "
   "not only when they click the button. So you get Enter for free.</li>"
   "</ul>"
   "<p>Also useful: <code>form.elements.nameInput.value</code> to read a field by its "
   "<code>name</code> attribute. That is the classic way to read form data.</p>"},

  {"type": "idea", "title": "3. The keyboard", "html":
   "<pre class=\"code\"><code>input.addEventListener(\"keydown\", function (event) {\n"
   "  if (event.key === \"Enter\") {\n"
   "    // act\n"
   "  }\n"
   "  if (event.key === \"Escape\") {\n"
   "    // cancel\n"
   "  }\n"
   "});</code></pre>"
   "<p><code>event.key</code> is the key that was pressed (\"Enter\", \"a\", \"ArrowDown\", "
   "\"Escape\"). <code>event.key</code> is the character; <code>event.code</code> is the physical "
   "key (<code>\"KeyA\"</code>). For text input, use <code>event.key</code>.</p>"
   "<p><strong>input vs change:</strong> <code>\"input\"</code> fires on every single keystroke. "
   "<code>\"change\"</code> fires when the value is committed (blur or Enter). For a live "
   "search box, use <code>\"input\"</code>.</p>"},

  {"type": "note", "title": "Wait, when does my script run?", "html":
   "<p>Here is a real problem. If your script is in the <code>&lt;head&gt;</code>, it runs "
   "<em>before</em> the body exists, so <code>document.querySelector(\"#app\")</code> returns "
   "<code>null</code>.</p>"
   "<p>Three ways to fix it:</p>"
   "<pre class=\"code\"><code>// 1. Put the &lt;script&gt; right before &lt;/body&gt;  (simplest)\n\n"
   "// 2. Use the DOMContentLoaded event\n"
   "document.addEventListener(\"DOMContentLoaded\", function () {\n"
   "  // everything is ready now\n"
   "});\n\n"
   "// 3. async / await at the top of a module\n"
   "// (you will meet this when you meet npm)</code></pre>"
   "<p>Option 2 is the habit to build, because it survives being moved into a separate "
   "<code>.js</code> file later. And in a real app, your script usually lives in a separate "
   "file &mdash; in which case option 2 (or <code>defer</code> on the script tag) is the only "
   "option.</p>"},

  {"type": "demo", "id": "dom-events-deep-demo", "title": "A filterable list",
   "html": "<p>Type in the box: the list filters as you type. Note the <strong>one</strong> "
           "listener on the list, not one per row.</p>",
   "html_demo": """
     <input id="filter-input" placeholder="filter the list..." />
     <ul id="filter-list">
       <li>Apples</li>
       <li>Bananas</li>
       <li>Cherries</li>
       <li>Dates</li>
       <li>Elderberries</li>
     </ul>
     <pre class="out" id="dom-events-deep-demo-out"></pre>
   """,
   "js": """
     const input = document.getElementById("filter-input");
     const list = document.getElementById("filter-list");

     // ONE listener on the list -- not one per <li>
     list.addEventListener("click", function (event) {
       const item = event.target.closest("li");
       if (!item) return;
       item.classList.toggle("done");
       console.log("toggled:", item.textContent);
     });

     input.addEventListener("input", function (event) {
       const q = event.target.value.toLowerCase();
       const rows = list.querySelectorAll("li");

       rows.forEach(function (row) {
         const match = row.textContent.toLowerCase().includes(q);
         row.style.display = match ? "list-item" : "none";
       });

       console.log("filtered with:", q);
     });
   """},

  {"type": "lab", "id": "dom-events-deep-lab", "title": "Delegation and forms",
   "html": "<p>The demo list is <code>filter-list</code>. Add a click handler on the "
           "<strong>list</strong> (not on each row) and a form handler on a form you create.</p>",
   "starter": "const list = document.getElementById(\"filter-list\");\n\n"
              "// delegation: one listener, catches clicks on any <li>\n"
              "list.addEventListener(\"click\", function (event) {\n"
              "  const item = event.target.closest(\"li\");\n"
              "  if (!item) return;\n"
              "  console.log(\"delegated click on:\", item.textContent);\n"
              "});\n\n"
              "// build a form, and handle submit without a page reload\n"
              "const form = document.createElement(\"form\");\n"
              "form.innerHTML = '<input name=\"task\" placeholder=\"new task\">';\n"
              "document.body.append(form);\n\n"
              "form.addEventListener(\"submit\", function (event) {\n"
              "  event.preventDefault();\n"
              "  console.log(\"submitted:\", form.elements.task.value);\n"
              "  form.reset();\n"
              "});\n\n"
              "console.log(\"listeners attached - click a row, or press Enter in the new box\");",
   "hints": [
     "The form is appended to the page, so it is visible below the demo.",
     "<code>form.elements.task.value</code> reads the input named <code>task</code>.",
     "Without <code>preventDefault()</code>, the page reloads when you press Enter &mdash; try "
     "removing it and see.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Make the delegated handler <strong>remove</strong> the clicked row from the list "
           "(instead of just logging it).</p>",
   "checks": [
     "You call <code>item.remove()</code> inside the handler.",
     "The handler is on the list, not on each row.",
     "Clicking the list's blank space (not a row) does nothing &mdash; your "
     "<code>if (!item) return;</code> handles that.",
   ]},

  {"type": "checkpoint", "items": [
     "Events bubble up. Listen on the parent, use <code>event.target.closest(...)</code>.",
     "<code>target</code> = what was clicked. <code>currentTarget</code> = where you listened.",
     "<code>form.addEventListener(\"submit\", e =&gt; { e.preventDefault(); ... })</code> "
     "stops the reload.",
     "<code>\"input\"</code> fires per keystroke, <code>\"change\"</code> on commit.",
     "Scripts in <code>&lt;head&gt;</code> need <code>DOMContentLoaded</code>.",
  ]},
 ],
},

# ---------------------------------------------------------------- step 8
{
 "id": "dom-data-flow",
 "title": "Data first, DOM second",
 "lede": "The mindset shift that separates hobby DOM code from professional front-end code. "
         "Keep the truth in JavaScript, and let the DOM be a picture of it.",
 "blocks": [
  {"type": "idea", "title": "The idea", "html":
   "<p>There are two ways to build a list in the browser.</p>"
   "<h4>Way A: edit the DOM as things happen</h4>"
   "<pre class=\"code\"><code>// add a row\nlist.append(makeRow(\"milk\"));\n\n"
   "// delete row 2\nrows[1].remove();\n\n"
   "// mark row 3 as done\nrows[2].classList.add(\"done\");</code></pre>"
   "<p>This works, but the DOM is now the only place the data lives. Ask \"how many items are "
   "left?\" and the only way to find out is to count elements. Change one thing in one place "
   "and another place silently drifts out of sync. It gets messy fast.</p>"
   "<h4>Way B: keep the data, redraw from it</h4>"
   "<pre class=\"code\"><code>let items = [\"milk\", \"bread\"];      // the truth\n\n"
   "function render() {                // the DOM is a picture of the truth\n"
   "  list.innerHTML = \"\";           // 1. clear\n"
   "  items.forEach(function (text) {  // 2. rebuild from data\n"
   "    const li = document.createElement(\"li\");\n"
   "    li.textContent = text;\n"
   "    list.append(li);\n"
   "  });\n"
   "}\n\n"
   "render();   // draw it</code></pre>"
   "<p>Now:</p>"
   "<ul>"
   "<li>To delete an item you change the <code>items</code> array and call <code>render()</code> "
   "again.</li>"
   "<li>To count what is left you ask the array: <code>items.length</code>. No DOM counting "
   "needed.</li>"
   "<li>There is exactly one place that knows how a row looks: the <code>render()</code> "
   "function.</li>"
   "</ul>"
   "<p><strong>This is React's whole idea.</strong> React does exactly this, but it runs "
   "<code>render()</code> for you and only patches the differences. When you meet React in a "
   "few days, this step will already be familiar.</p>"},

  {"type": "note", "title": "The three parts of every little app", "html":
   "<p>Once you see it, every front-end app has the same three parts:</p>"
   "<ol>"
   "<li><strong>State</strong> &mdash; the data. <code>let items = [...]</code></li>"
   "<li><strong>Actions</strong> &mdash; functions that change the state. "
   "<code>function add(text) { items.push(text); render(); }</code></li>"
   "<li><strong>Render</strong> &mdash; the function that draws the state onto the page.</li>"
   "</ol>"
   "<p>Your job as a developer is mostly to keep those three in sync. When something looks "
   "wrong, ask: is the state right? is render() right? is the action calling render()?</p>"},

  {"type": "demo", "id": "dom-data-flow-demo", "title": "Same list, two ways",
   "html": "<p>Both buttons do the same thing: add the word \"apple\". The left one patches the "
           "DOM, the right one changes the data and redraws. Watch the console.</p>",
   "html_demo": """
     <ul id="dfa-list"></ul>
     <button id="dfa-patch">Patch the DOM directly</button>
     <button id="dfa-render">Change data, then render</button>
     <pre class="out" id="dom-data-flow-demo-out"></pre>
   """,
   "js": """
     // --- Way A: patch the DOM
     const list = document.getElementById("dfa-list");
     document.getElementById("dfa-patch").addEventListener("click", function () {
       const li = document.createElement("li");
       li.textContent = "apple";
       list.append(li);
       console.log("patched. rows on screen:", list.children.length);
       console.log("but how many items do we HAVE? unknown -- the DOM is the only source");
     });

     // --- Way B: data first
     let items = [];
     function render() {
       list.innerHTML = "";
       items.forEach(function (text) {
         const li = document.createElement("li");
         li.textContent = text;
         list.append(li);
       });
       console.log("rendered. rows on screen:", list.children.length);
       console.log("items in state:", items.length, "->", items);
     }
     document.getElementById("dfa-render").addEventListener("click", function () {
       items.push("apple");
       render();
     });
   """},

  {"type": "lab", "id": "dom-data-flow-lab", "title": "Build the state + render pattern",
   "html": "<p>Try this with the demo list <code>dfa-list</code>.</p>",
   "starter": "const list = document.getElementById(\"dfa-list\");\n\n"
              "// 1. state\nlet items = [\"milk\"];\n\n"
              "// 2. render\n"
              "function render() {\n"
              "  list.innerHTML = \"\";\n"
              "  items.forEach(function (text) {\n"
              "    const li = document.createElement(\"li\");\n"
              "    li.textContent = text;\n"
              "    list.append(li);\n"
              "  });\n"
              "  console.log(\"state:\", items);\n"
              "}\n\n"
              "// 3. an action that changes the state and redraws\n"
              "function add(text) {\n"
              "  items.push(text);\n"
              "  render();\n"
              "}\n\n"
              "render();\n"
              "add(\"bread\");\n"
              "add(\"eggs\");",
   "hints": [
     "The order matters: change the data, then call <code>render()</code>.",
     "If the screen and the data ever disagree, <code>render()</code> was probably not called.",
     "Now add a <code>remove(text)</code> action: filter the array and call <code>render()</code>.",
   ]},

  {"type": "try", "title": "Tiny challenge",
   "html": "<p>Add a <code>done</code> state to each item, so clicking an item marks it and "
           "re-renders.</p>",
   "checks": [
     "Your state holds objects, not just strings: "
     "<code>[{ text: \"milk\", done: false }]</code>.",
     "Clicking a row updates the object in the array and calls <code>render()</code>.",
     "The rendered row shows the done state (a class like <code>\"done\"</code>).",
     "Bonus: a counter at the top showing how many items are not done &mdash; computed from "
     "the array, not by counting DOM nodes.",
   ]},

  {"type": "checkpoint", "items": [
     "State (the data) is the source of truth. The DOM is a picture of it.",
     "Pattern: change state &rarr; call render().",
     "Every app = state + actions + render.",
     "This is the idea React automates. You are already thinking in React terms.",
  ]},
 ],
}
]
