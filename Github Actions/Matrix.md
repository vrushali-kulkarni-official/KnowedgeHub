Absolutely. **Matrix** is one of the most powerful features of GitHub Actions, but the documentation often explains it in a confusing way. Let's build it from scratch.

---

# Step 1: What problem does a matrix solve?

Imagine you wrote a Python program.

You want to make sure it works on:

* Windows
* Linux
* macOS

Without a matrix, you'd have to write **three almost identical jobs**.

Example:

```yaml
jobs:
  test-windows:
    runs-on: windows-latest
    steps:
      - run: python app.py

  test-linux:
    runs-on: ubuntu-latest
    steps:
      - run: python app.py

  test-macos:
    runs-on: macos-latest
    steps:
      - run: python app.py
```

Notice something?

The jobs are almost identical.

Only this changes:

```yaml
runs-on:
```

Everything else is repeated.

This violates one of the biggest programming principles:

> Don't Repeat Yourself (DRY)

GitHub created **matrix** to solve this.

---

# Step 2: What is a matrix?

Think of a matrix as a **list of values**.

Example:

```yaml
matrix:
  os:
    - ubuntu-latest
    - windows-latest
    - macos-latest
```

GitHub reads this and says:

> "I see 3 operating systems."

Then GitHub automatically creates:

Job 1

```
ubuntu-latest
```

Job 2

```
windows-latest
```

Job 3

```
macos-latest
```

You wrote **one job**, but GitHub creates **three jobs**.

---

# Step 3: Your first matrix

```yaml
jobs:
  test:

    strategy:

      matrix:

        os:
          - ubuntu-latest
          - windows-latest
          - macos-latest

    runs-on: ${{ matrix.os }}

    steps:

      - run: echo "Running on ${{ matrix.os }}"
```

---

Let's read it slowly.

## This

```yaml
matrix:
  os:
```

creates a variable called

```
matrix.os
```

Its values are

```
ubuntu-latest
windows-latest
macos-latest
```

---

## Then

```yaml
runs-on: ${{ matrix.os }}
```

becomes

First job

```yaml
runs-on: ubuntu-latest
```

Second job

```yaml
runs-on: windows-latest
```

Third job

```yaml
runs-on: macos-latest
```

GitHub automatically expands it.

---

# Step 4: What actually happens?

Suppose your workflow is

```yaml
jobs:
  test:

    strategy:

      matrix:

        os:
          - ubuntu-latest
          - windows-latest
          - macos-latest

    runs-on: ${{ matrix.os }}

    steps:
      - run: echo Hello
```

GitHub internally behaves **as if** you had written:

```yaml
jobs:

  test-1:
    runs-on: ubuntu-latest
    steps:
      - run: echo Hello

  test-2:
    runs-on: windows-latest
    steps:
      - run: echo Hello

  test-3:
    runs-on: macos-latest
    steps:
      - run: echo Hello
```

You never wrote these jobs.

GitHub generated them.

---

# Step 5: Another example

Suppose you're testing Node.js.

You want to test

* Node 18
* Node 20
* Node 22

Instead of

```yaml
test18:
```

```yaml
test20:
```

```yaml
test22:
```

you write

```yaml
strategy:

  matrix:

    node:
      - 18
      - 20
      - 22
```

Now

```yaml
${{ matrix.node }}
```

will become

```
18
```

then

```
20
```

then

```
22
```

---

Example

```yaml
steps:

  - uses: actions/setup-node@v4

    with:

      node-version: ${{ matrix.node }}

  - run: node --version
```

GitHub runs it three times.

---

# Step 6: Multiple variables

Now it gets interesting.

Suppose you want

Operating systems

```
Ubuntu
Windows
```

AND

Node versions

```
18
20
```

Your matrix becomes

```yaml
matrix:

  os:
    - ubuntu-latest
    - windows-latest

  node:
    - 18
    - 20
```

Most beginners think GitHub makes

```
Ubuntu + 18

Windows + 20
```

No.

GitHub creates **every possible combination**.

---

# Step 7: Cartesian Product

This is called the **Cartesian product**.

Imagine a table.

| OS      | Node |
| ------- | ---- |
| Ubuntu  | 18   |
| Ubuntu  | 20   |
| Windows | 18   |
| Windows | 20   |

GitHub creates **4 jobs**.

---

Job 1

```
Ubuntu + Node18
```

Job 2

```
Ubuntu + Node20
```

Job 3

```
Windows + Node18
```

Job 4

```
Windows + Node20
```

---

# Step 8: Using both variables

```yaml
jobs:

  test:

    strategy:

      matrix:

        os:

          - ubuntu-latest
          - windows-latest

        node:

          - 18
          - 20

    runs-on: ${{ matrix.os }}

    steps:

      - uses: actions/setup-node@v4

        with:

          node-version: ${{ matrix.node }}

      - run: node --version
```

GitHub automatically performs:

| Job | OS      | Node |
| --- | ------- | ---- |
| 1   | Ubuntu  | 18   |
| 2   | Ubuntu  | 20   |
| 3   | Windows | 18   |
| 4   | Windows | 20   |

---

# Step 9: Three variables

Now suppose

```yaml
matrix:

  os:
    - ubuntu
    - windows

  node:
    - 18
    - 20

  database:
    - mysql
    - postgres
```

How many jobs?

Multiply everything.

```
2 OS

×

2 Node

×

2 Database

=
8 jobs
```

The combinations are:

| OS      | Node | Database |
| ------- | ---- | -------- |
| Ubuntu  | 18   | MySQL    |
| Ubuntu  | 18   | Postgres |
| Ubuntu  | 20   | MySQL    |
| Ubuntu  | 20   | Postgres |
| Windows | 18   | MySQL    |
| Windows | 18   | Postgres |
| Windows | 20   | MySQL    |
| Windows | 20   | Postgres |

---

# Step 10: Why is this useful?

Imagine you're developing software used by thousands of people.

Some users use

* Windows
* Linux
* macOS

Some use

* Node 18
* Node 20
* Node 22

You want to know

> Does my project work everywhere?

Instead of manually testing nine environments, the matrix lets GitHub test them automatically.

---

# Step 11: How the `matrix` values are accessed

Inside the job, each matrix variable is available as:

```yaml
${{ matrix.<name> }}
```

For example:

```yaml
matrix:
  os:
    - ubuntu-latest
```

You access it with:

```yaml
${{ matrix.os }}
```

If you have:

```yaml
matrix:
  python:
    - "3.10"
    - "3.11"
```

Then:

```yaml
${{ matrix.python }}
```

will be either:

```
3.10
```

or

```
3.11
```

depending on the job.

---

# Step 12: A real-world example

```yaml
jobs:

  test:

    strategy:

      matrix:

        os:
          - ubuntu-latest
          - windows-latest

        python:
          - "3.10"
          - "3.11"

    runs-on: ${{ matrix.os }}

    steps:

      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}

      - run: python --version
```

GitHub creates these jobs:

| Job | OS      | Python |
| --- | ------- | ------ |
| 1   | Ubuntu  | 3.10   |
| 2   | Ubuntu  | 3.11   |
| 3   | Windows | 3.10   |
| 4   | Windows | 3.11   |

Each job runs independently, often in parallel if runners are available.

---

# Mental Model

Think of a matrix like nested `for` loops.

If you have:

```yaml
matrix:
  os:
    - ubuntu
    - windows

  node:
    - 18
    - 20
```

It's conceptually similar to:

```text
for each os:
    for each node:
        create a new job
```

Which expands to:

```text
Ubuntu + 18
Ubuntu + 20
Windows + 18
Windows + 20
```

GitHub performs this expansion for you, so you write one job definition and it automatically generates all the combinations. This is why matrix builds are a concise and scalable way to test the same workflow across multiple environments.
