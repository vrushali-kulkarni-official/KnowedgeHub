This is one of the first things that surprises people coming from Windows. **GNOME (the desktop environment used by Fedora Workstation) does not show "New Text File" or "New File" by default.** This is intentional. Instead, it uses **Templates**. ([GNOME Discourse][1])

## Method 1 (Recommended): Enable "New Document" using Templates

### Step 1: Open your Home folder

Open **Files** and go to your **Home** folder.

You should see a folder named:

```
Templates
```

If it doesn't exist, create it.

---

### Step 2: Create an empty text file inside Templates

Open **Text Editor**.

Create a blank document.

Save it as:

```
Empty Text File.txt
```

inside

```
~/Templates
```

Your folder should look like:

```
Home
└── Templates
    └── Empty Text File.txt
```

---

### Step 3: Try it

Now go to **any folder**.

Right-click on empty space.

You should now see:

```
New Folder
New Document →
    Empty Text File.txt
```

Click **Empty Text File.txt** and GNOME will create a copy in the current folder. ([GNOME Discourse][1])

---

## You can create templates for anything

This is actually more powerful than Windows.

For example, put these inside `~/Templates`:

```
Python.py
main.cpp
README.md
Dockerfile
docker-compose.yml
index.html
style.css
script.js
```

Then your right-click menu becomes:

```
New Document →
    README.md
    Dockerfile
    Python.py
    index.html
    style.css
```

GNOME simply copies whichever template you choose into the current folder. ([GNOME Discourse][1])

---

## Method 2: Create a file from the Terminal

For an empty file:

```bash
touch filename.txt
```

Examples:

```bash
touch README.md
touch main.py
touch Dockerfile
```

---

## Method 3: Create it from an application

For example:

* Open Text Editor
* Press **Ctrl+S**
* Navigate to the folder
* Save the file

---

# For someone learning Linux

Since you've mentioned you're new to Fedora, I recommend setting up a useful `Templates` folder once. For example:

```
Templates
├── Empty Text File.txt
├── README.md
├── .gitignore
├── main.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── index.html
├── style.css
└── script.js
```

Then you can create any of these files with just a right-click, which is very convenient for development.

[1]: https://discourse.gnome.org/t/create-new-file-from-file-manager-current-folder/22172?utm_source=chatgpt.com "Create new file from File Manager current folder - Applications - GNOME Discourse"

