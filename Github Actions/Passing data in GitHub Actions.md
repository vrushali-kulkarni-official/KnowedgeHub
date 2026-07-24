Perfect. This is one of the most important concepts in GitHub Actions, and it confuses almost every beginner.

I'll start from **why this problem exists**, because once you understand that, everything else becomes easy.

---

# First, understand how GitHub Actions works

Imagine your workflow looks like this:

```yaml
jobs:
  build:
    steps:
      - Step 1
      - Step 2
      - Step 3
```

Execution:

```
Workflow
└── Job: build
      │
      ├── Step 1
      │
      ├── Step 2
      │
      └── Step 3
```

Each step runs one after another.

---

# But here's the problem...

Suppose Step 1 calculates something.

Example:

```text
Today's version = 1.4.7
```

Now Step 2 wants to use that version.

How does it know?

Step 2 starts as a **new process**.

It doesn't automatically know what happened inside Step 1.

Think of it like this:

```
Step 1
---------
version = 1.4.7

Step ends
```

Now Step 2 starts.

```
Step 2
---------
Where is version?
```

It's gone.

Because every `run:` starts a new shell process.

---

# Example

Step 1

```yaml
- run: |
    VERSION=1.4.7
    echo $VERSION
```

Output

```
1.4.7
```

Now Step 2

```yaml
- run: |
    echo $VERSION
```

Output

```
```

Nothing.

Why?

Because that variable only existed inside Step 1.

---

# So GitHub provides ways to share data.

There are different ways depending on where the data needs to go.

```
Within same step
↓

Between steps

↓

Between jobs

↓

Between workflows
```

Today we'll cover the first three.

---

# Method 1 — Environment Variables

Suppose Step 1 creates something.

```yaml
- name: Create version
  run: |
    echo "VERSION=1.4.7" >> $GITHUB_ENV
```

Notice this line:

```text
$GITHUB_ENV
```

This is a special file provided by GitHub.

You're not modifying Linux itself.

You're writing into a file that GitHub reads after the step finishes.

Think of it like this:

```
Step 1

Writes:

VERSION=1.4.7

↓

GITHUB_ENV file
```

After Step 1 ends,

GitHub reads that file.

Then it injects those variables into Step 2.

Now Step 2 becomes

```yaml
- run: echo $VERSION
```

Output

```
1.4.7
```

---

## Visual

```
Step 1
    │
    │ writes
    ▼
GITHUB_ENV
    │
GitHub reads it
    │
    ▼
Step 2 gets VERSION
```

---

# Why not just export?

Many beginners try

```yaml
export VERSION=1.4.7
```

This only affects the current shell.

When Step 1 ends,

the shell dies.

```
Shell
│
├─ export VERSION
│
└─ shell exits

Variable gone
```

---

# Method 2 — Step Outputs

Sometimes a step generates a value that later steps need.

Example:

```
Docker image tag

Latest release

Random password

Git SHA

Current branch
```

Instead of environment variables,

GitHub has **outputs**.

---

Suppose

Step 1 calculates

```
IMAGE=v1.5.0
```

Give the step an ID.

```yaml
- name: Generate tag
  id: tag

  run: |
    echo "image=v1.5.0" >> $GITHUB_OUTPUT
```

Notice

```
id: tag
```

Every step can have an ID.

Like this

```
Step 1
ID = tag
```

GitHub stores

```
image=v1.5.0
```

as that step's output.

---

Now Step 2

```yaml
- run: echo "${{ steps.tag.outputs.image }}"
```

Output

```
v1.5.0
```

---

Visual

```
Step
 ID=tag

     │
writes
     │
GITHUB_OUTPUT
     │
GitHub stores
     │
steps.tag.outputs.image
```

---

# Difference between GITHUB_ENV and GITHUB_OUTPUT

`GITHUB_ENV`

```
Creates environment variables.

Used like

$VERSION
```

`GITHUB_OUTPUT`

```
Creates outputs.

Used like

steps.build.outputs.version
```

---

# Which should I use?

If every later step simply needs an environment variable,

use

```
GITHUB_ENV
```

If one step is producing a specific result,

use

```
GITHUB_OUTPUT
```

Outputs are generally cleaner because they clearly show where the value came from.

---

# Passing data between Jobs

Now comes the interesting part.

Suppose you have

```
Job A

↓

Job B
```

Like

```yaml
jobs:

  build:

  deploy:
```

Can Job B access Step outputs directly?

No.

Why?

Because jobs run on different runners.

Imagine

```
Job A

Ubuntu VM #1
```

and

```
Job B

Ubuntu VM #2
```

These are different machines.

Job A disappears after finishing.

So Job B cannot see its files or variables.

---

# Then how do we pass data?

We create

```
Step Output

↓

Job Output

↓

Next Job
```

---

Step 1

```yaml
- id: version
  run: |
    echo "number=1.4.7" >> $GITHUB_OUTPUT
```

Now expose it as a job output.

```yaml
jobs:

  build:

    outputs:
      version: ${{ steps.version.outputs.number }}
```

Notice

```
outputs:
```

at the job level.

Now the job publishes

```
version=1.4.7
```

---

Job 2

Must depend on Job 1.

```yaml
needs: build
```

Now access it.

```yaml
${{ needs.build.outputs.version }}
```

---

Visual

```
Step

↓

Step Output

↓

Job Output

↓

needs.build.outputs.version

↓

Job 2
```

---

# Complete Example

```yaml
jobs:

  build:

    runs-on: ubuntu-latest

    outputs:
      version: ${{ steps.create.outputs.version }}

    steps:

      - id: create

        run: |
          echo "version=2.0.1" >> $GITHUB_OUTPUT

  deploy:

    needs: build

    runs-on: ubuntu-latest

    steps:

      - run: |
          echo "Deploying version ${{ needs.build.outputs.version }}"
```

Output

```
Deploying version 2.0.1
```

---

# Passing Files Between Jobs

Suppose build creates

```
app.zip
```

Can Job 2 access it?

No.

Remember

```
Different runner

Different filesystem
```

Instead,

Job 1 uploads an artifact.

```
Build

↓

Upload Artifact

↓

GitHub Storage

↓

Download Artifact

↓

Deploy
```

Artifacts are the correct way to transfer files between jobs.

You've already started learning artifacts, so think of them as "packages" stored temporarily by GitHub for other jobs (or later download).

---

# Summary Table

| Need                                     | Use                     | Example                                |
| ---------------------------------------- | ----------------------- | -------------------------------------- |
| Variable for later steps in the same job | `GITHUB_ENV`            | `echo "VERSION=1.0" >> $GITHUB_ENV`    |
| Value produced by a specific step        | `GITHUB_OUTPUT`         | `echo "sha=abc123" >> $GITHUB_OUTPUT`  |
| Share a value with another job           | Job `outputs` + `needs` | `${{ needs.build.outputs.version }}`   |
| Share files between jobs                 | Artifacts               | Upload in one job, download in another |

---

# A Real-World CI/CD Example

Imagine you're building and deploying a Docker image.

```
Workflow
│
├── Build Job
│     │
│     ├── Build image
│     ├── Generate image tag (e.g., 2.3.5)
│     ├── Push image to registry
│     └── Expose image tag as a job output
│
└── Deploy Job
      │
      ├── Waits for Build (`needs: build`)
      ├── Reads the image tag
      └── Deploys exactly that image version
```

The build job might produce:

```text
image_tag=2.3.5
```

using `GITHUB_OUTPUT`, expose it as a job output, and the deploy job retrieves it with:

```yaml
${{ needs.build.outputs.image_tag }}
```

This ensures the deploy job uses the exact image that was built, rather than trying to recalculate or guess the tag.

---

# Beginner's Rule of Thumb

When you're deciding how to pass data, ask yourself these questions in order:

1. **Do I only need this value inside the current `run:` script?**
   Just use a normal shell variable:

   ```bash
   VERSION=1.2.3
   ```

2. **Do later steps in the same job need it?**
   Write it to `GITHUB_ENV`:

   ```bash
   echo "VERSION=1.2.3" >> $GITHUB_ENV
   ```

3. **Is this a specific result produced by one step that other steps should reference explicitly?**
   Write it to `GITHUB_OUTPUT` and access it through:

   ```yaml
   ${{ steps.<step-id>.outputs.<output-name> }}
   ```

4. **Does another job need the value?**
   Expose it as a **job output**, make the downstream job depend on it with `needs`, and access it with:

   ```yaml
   ${{ needs.<job-id>.outputs.<output-name> }}
   ```

5. **Do I need to transfer files (not just text values) between jobs?**
   Use **artifacts** to upload the files in one job and download them in another.

Once you understand these five cases, you'll be able to follow the vast majority of production GitHub Actions workflows.
