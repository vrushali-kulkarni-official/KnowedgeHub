Perfect. Since you're a beginner, let's build the concept from the ground up.

---

# What is an Artifact in GitHub Actions?

Imagine you are baking a cake.

You have:

* Ingredients (flour, eggs, sugar)
* Recipe
* Oven
* Finished cake

The **finished cake** is something you want to keep after cooking is done.

An **artifact** is exactly like that.

It is a **file or folder produced during a workflow that GitHub saves for you after the workflow finishes.**

Examples:

* Compiled application
* Test reports
* Log files
* Screenshots
* Coverage reports
* ZIP files
* PDF reports

---

# Why do artifacts exist?

Remember something important:

A GitHub Actions runner is **temporary**.

When a workflow starts

```
GitHub creates a fresh machine
```

After the workflow finishes

```
GitHub destroys the machine
```

Everything inside it disappears.

Imagine this.

```
Workflow starts

Runner
--------------------
project
build/
logs/
report.html

Workflow ends

Runner deleted ❌
```

Everything is gone.

If you want to keep something...

GitHub lets you upload it as an **artifact**.

---

# Think of an artifact like cloud storage

Suppose your workflow creates

```
build/
    app.exe
```

Before the runner disappears

GitHub uploads

```
build/
```

to GitHub's storage.

Later you can download it.

---

# What kinds of files become artifacts?

Anything.

For example

```
project/

src/
tests/

dist/
    app.exe

logs/
    build.log

coverage/
    report.html
```

You can save

* dist
* logs
* coverage

as artifacts.

---

# Real-world example

Imagine your workflow builds a React application.

After running

```
npm run build
```

you get

```
dist/

index.html
assets/
logo.png
main.js
```

Normally...

```
Workflow ends

dist/

gets deleted.
```

Instead

Upload

```
dist/
```

as an artifact.

Now anyone can download the built website.

---

# Another example

Suppose your tests fail.

```
pytest
```

creates

```
test-results.xml
```

Instead of losing it

Upload

```
test-results.xml
```

Now developers can inspect it.

---

# Another example

Suppose your workflow creates screenshots.

```
screenshots/

home.png
login.png
checkout.png
```

Save them as artifacts.

Even if the runner disappears

You can still download the screenshots.

---

# Where are artifacts stored?

Inside your GitHub repository.

Go to

```
Repository
    ↓

Actions

    ↓

Select workflow run

    ↓

Artifacts
```

Example

```
Build React App

✔ Success

Artifacts

build-files
```

Click

```
build-files
```

Download

```
build-files.zip
```

---

# How do you upload artifacts?

GitHub provides an action.

```yaml
uses: actions/upload-artifact@v4
```

Notice

```
actions/upload-artifact
```

is just another GitHub Action.

Exactly like

```yaml
uses: actions/checkout@v4
```

---

# Simplest example

```yaml
steps:

- uses: actions/checkout@v4

- run: npm install

- run: npm run build

- uses: actions/upload-artifact@v4
  with:
    name: website
    path: dist/
```

Let's understand every line.

---

## Step 1

```yaml
- uses: actions/upload-artifact@v4
```

Run the Upload Artifact Action.

---

## Step 2

```yaml
with:
```

Provide settings.

---

## Step 3

```yaml
name: website
```

Artifact name.

GitHub will show

```
Artifacts

website
```

---

## Step 4

```yaml
path: dist/
```

Upload

```
dist/
```

folder.

---

# Visual explanation

Runner

```
project/

dist/

index.html
main.js
```

Upload

```
dist/
```

↓

GitHub Storage

```
website.zip
```

↓

Workflow ends

Runner destroyed

↓

Artifact still exists.

---

# Uploading multiple files

Suppose

```
logs/

build.log

coverage/

report.html
```

You can upload both.

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: reports
    path: |
      logs/
      coverage/
```

Everything becomes one artifact.

---

# Uploading a single file

```yaml
path: report.pdf
```

Only

```
report.pdf
```

gets uploaded.

---

# Uploading multiple paths

```yaml
path: |
  dist/
  logs/
  report.html
```

Uploads all three.

---

# Wildcards

Suppose

```
logs/

build.log
error.log
debug.log
```

Upload only log files.

```yaml
path: logs/*.log
```

Uploads

```
build.log

error.log

debug.log
```

---

# Excluding files

```yaml
path: |
  dist/
  !dist/*.map
```

Uploads everything except

```
*.map
```

files.

---

# Artifact retention

Artifacts are not stored forever.

GitHub deletes them after a retention period.

Example

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: build
    path: dist/
    retention-days: 7
```

GitHub keeps it for

```
7 days
```

then deletes it.

If omitted, GitHub uses the repository's default retention period (subject to GitHub's limits and repository settings).

---

# Downloading artifacts

Another workflow can download them.

GitHub provides another action.

```yaml
uses: actions/download-artifact@v4
```

Example

```yaml
steps:

- uses: actions/download-artifact@v4
  with:
    name: website
```

GitHub downloads

```
website
```

into the runner.

---

# Complete example

```yaml
name: Build

on:
  push:

jobs:
  build:

    runs-on: ubuntu-latest

    steps:

    - uses: actions/checkout@v4

    - run: npm install

    - run: npm run build

    - uses: actions/upload-artifact@v4
      with:
        name: website
        path: dist/
```

Workflow

```
Checkout

↓

Install

↓

Build

↓

Create dist/

↓

Upload dist/

↓

Runner deleted

↓

Artifact remains
```

---

# A real CI/CD example

Suppose your application is built in one job and deployed in another.

```
Build Job
----------
Compile code
↓

Create executable

↓

Upload executable
```

Then

```
Deploy Job
-----------
Download executable

↓

Deploy to server
```

Without artifacts, the second job would have no access to the executable because each job runs on a fresh runner.

```
Job 1

Runner A

build.exe

↓

Upload Artifact

↓

Job ends

Runner A deleted
```

```
Job 2

Runner B

↓

Download Artifact

↓

build.exe available again
```

Artifacts are one of the main ways to pass generated files between jobs in a workflow.

---

# Artifacts vs Cache (Very Important)

Many beginners confuse these.

| Artifact                                   | Cache                                                             |
| ------------------------------------------ | ----------------------------------------------------------------- |
| Stores files you want to keep              | Stores files to speed up future runs                              |
| Purpose is preservation and sharing        | Purpose is performance                                            |
| Usually downloaded by people or later jobs | Usually restored automatically by workflows                       |
| Examples: build output, reports, logs      | Examples: `node_modules`, Maven cache, Gradle cache, pip packages |
| Treated as the output of a workflow        | Treated as reusable dependencies                                  |

Think of it this way:

* **Artifact = "This is something I produced."**
* **Cache = "This is something I don't want to download or rebuild every time."**

---

# When should you use artifacts?

Use artifacts whenever your workflow produces something valuable that should survive after the runner is destroyed, such as:

* Build outputs (`dist/`, compiled binaries, JAR files)
* Test reports
* Code coverage reports
* Log files
* Screenshots from UI tests
* Generated documentation
* Files that another job needs to use later

---

## Beginner-friendly summary

Think of a GitHub Actions runner as a **temporary computer**.

```
Workflow starts
        │
        ▼
 Temporary Runner
        │
   Build project
   Run tests
   Generate reports
        │
        ▼
Upload important files as Artifacts
        │
        ▼
 Runner is deleted
        │
        ▼
Artifacts remain safely stored on GitHub
```

If you **don't** upload a file as an artifact, it disappears when the workflow ends. If you **do** upload it, you (or another job) can download it later. This makes artifacts essential for preserving build outputs, reports, and other generated files in GitHub Actions.
