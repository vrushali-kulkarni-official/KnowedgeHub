# Q1: explain if conditions in github actions 
go step by step 
and explain in detail
but note i am a beginner


# A1:
Great topic. GitHub Actions `if` conditions are one of the most useful features because they let you decide **whether a job or step should run**.

I'll explain this from the beginning, assuming you've never used it before.

---

# Step 1: What is an `if` condition?

An `if` condition is simply a **decision**.

It asks a question.

If the answer is **true**, GitHub runs the step or job.

If the answer is **false**, GitHub skips it.

Exactly like real life.

Example:

> If it is raining,
> take an umbrella.

If it is **not** raining,
don't take an umbrella.

Programming works the same way.

```
if (it is raining)
    take umbrella
else
    don't
```

GitHub Actions does the same.

---

# Step 2: Why do we need it?

Imagine your workflow:

```
Build Project
Run Tests
Deploy
```

You only want deployment when code is pushed to `main`.

When someone pushes to `feature-login`, deployment should NOT happen.

Without `if`

```
Build
↓

Tests
↓

Deploy
```

Deploy happens every time.

With `if`

```
Build
↓

Tests
↓

Is branch == main ?

        Yes
         ↓
      Deploy

        No
         ↓
      Skip Deploy
```

---

# Step 3: Where can `if` be used?

There are two places.

## 1. Job level

```
jobs:
  deploy:
    if: ...
```

Entire job runs or doesn't run.

Example

```
jobs:

  build:
    ...

  deploy:
    if: ...
```

If condition is false

```
Build
✓

Deploy
✗ skipped
```

Entire deploy job disappears.

---

## 2. Step level

Inside a job

```
steps:

- Build

- Test

- Deploy
```

You can make only one step conditional.

Example

```
steps:

- Build

- Test

- Deploy
      if: ...
```

Then

```
Build
✓

Test
✓

Deploy
Skipped
```

The job still runs.

Only that step is skipped.

---

# Step 4: Basic syntax

```
if: condition
```

Example

```
if: github.ref == 'refs/heads/main'
```

GitHub checks

```
Is current branch equal to
refs/heads/main ?
```

If yes

```
Run
```

Otherwise

```
Skip
```

---

# Step 5: What is `github.ref`?

GitHub provides lots of information during a workflow.

This information is called **context**.

One context is

```
github
```

Inside it,

```
github.ref
```

contains the branch or tag that triggered the workflow.

Suppose you push

```
main
```

Then

```
github.ref

↓

refs/heads/main
```

Suppose you push

```
dev
```

Then

```
github.ref

↓

refs/heads/dev
```

Suppose

```
feature/login
```

Then

```
github.ref

↓

refs/heads/feature/login
```

---

# Step 6: First real example

```
jobs:

  deploy:

    if: github.ref == 'refs/heads/main'
```

Suppose someone pushes

```
main
```

GitHub checks

```
github.ref

↓

refs/heads/main

==

refs/heads/main

TRUE
```

Job runs.

---

Someone pushes

```
dev
```

GitHub checks

```
refs/heads/dev

==

refs/heads/main

FALSE
```

Job skipped.

---

# Step 7: `==`

This means

> "is equal to"

Example

```
5 == 5
```

True

```
5 == 10
```

False

Strings also work.

```
"main" == "main"

True
```

```
"main" == "dev"

False
```

---

# Step 8: `!=`

Means

> "is NOT equal to"

Example

```
github.ref != 'refs/heads/main'
```

Now

Branch

```
main
```

Result

```
False
```

Branch

```
dev
```

Result

```
True
```

---

# Step 9: Event type

GitHub also tells you

"What event started this workflow?"

```
github.event_name
```

Possible values

```
push

pull_request

workflow_dispatch

schedule

release

issues
```

Example

```
if: github.event_name == 'push'
```

Workflow runs only for pushes.

---

# Step 10: AND operator

```
&&
```

Means

> BOTH conditions must be true.

Example

```
if:
github.ref == 'refs/heads/main'
&&
github.event_name == 'push'
```

Imagine

```
Branch = main

Event = push
```

Result

```
TRUE

AND

TRUE

↓

TRUE
```

Runs.

---

Now

```
Branch = dev

Event = push
```

```
FALSE

AND

TRUE

↓

FALSE
```

Skipped.

---

Now

```
Branch = main

Event = pull_request
```

```
TRUE

AND

FALSE

↓

FALSE
```

Skipped.

---

# Step 11: OR operator

```
||
```

Means

At least one condition must be true.

Example

```
if:

github.ref == 'refs/heads/main'

||

github.ref == 'refs/heads/dev'
```

Branch

```
main
```

Runs.

Branch

```
dev
```

Runs.

Branch

```
feature/login
```

Skipped.

---

# Step 12: NOT operator

```
!
```

Means

Reverse the answer.

Example

```
!true
```

becomes

```
false
```

```
!false
```

becomes

```
true
```

---

Example

```
if: !cancelled()
```

If workflow was cancelled

```
cancelled()

↓

true

↓

!true

↓

false
```

Step skipped.

---

# Step 13: Functions

GitHub has useful helper functions.

## success()

```
if: success()
```

Run only if everything before succeeded.

---

Example

```
Build
↓

Tests
↓

Deploy
```

If build fails

```
Build
❌

Tests skipped

Deploy skipped
```

---

## failure()

```
if: failure()
```

Run only if something failed.

Useful for notifications.

```
Build
↓

Failed

↓

Send Slack Message
```

---

## always()

Runs no matter what.

```
Build
↓

Tests

↓

Upload logs
```

Even if build failed,

logs still upload.

---

## cancelled()

Runs only when workflow was cancelled.

---

# Step 14: Combining conditions

Example

```
if:

success()

&&

github.ref == 'refs/heads/main'
```

Meaning

```
Did build succeed?

AND

Are we on main?
```

Both must be true.

---

# Step 15: Parentheses

Parentheses let you group conditions, just like in math.

```
if:
(
github.ref == 'refs/heads/main'
||
github.ref == 'refs/heads/dev'
)
&&
success()
```

This means:

1. Is the branch either `main` or `dev`?
2. And did previous steps succeed?

Only if both are true will the step or job run.

---

# Step 16: A practical example

```yaml
name: CI

on:
  push:
    branches:
      - main
      - dev

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build
        run: echo "Building..."

      - name: Run Tests
        run: echo "Testing..."

      - name: Deploy
        if: github.ref == 'refs/heads/main'
        run: echo "Deploying..."
```

If you push to `main`:

```
Checkout     ✓
Build        ✓
Run Tests    ✓
Deploy       ✓
```

If you push to `dev`:

```
Checkout     ✓
Build        ✓
Run Tests    ✓
Deploy       Skipped
```

---

# Step 17: `on.branches` vs `if`

Beginners often confuse these, but they work at different stages.

Suppose you have:

```yaml
on:
  push:
    branches:
      - main
      - dev
```

This answers the question:

> **Should the workflow start at all?**

If you push to `feature/login`, the workflow never starts.

```
Push to feature/login
        ↓
Does "feature/login" match main or dev?
        ↓
No
        ↓
Workflow is never created
```

Now suppose you push to `dev`.

The workflow **does** start because `dev` is allowed.

Then, inside the workflow, you have:

```yaml
- name: Deploy
  if: github.ref == 'refs/heads/main'
```

This answers a different question:

> **Now that the workflow is running, should this specific step run?**

Since the branch is `dev`, the answer is no, so only the Deploy step is skipped.

This distinction is important:

* `on:` controls **whether the workflow starts**.
* `if:` controls **what happens after the workflow has started**.

---

## Summary

Think of a GitHub Actions workflow like entering a building:

1. **`on:`** is the security guard at the entrance. If your event and branch don't match, you never get inside.
2. **`if:`** is the decision made inside each room. Once you're in the building, each job or step can decide whether to execute based on conditions.

Once you're comfortable with these basics, the next topics to learn are GitHub **contexts** (`github`, `env`, `runner`, `matrix`, `needs`, `steps`) and **expression syntax** (`${{ ... }}`), because `if` conditions are built from those pieces.




# Q2: what about else if conditions ?
and  what is the point of using 
if: always()
I mean it I don't put if: always() that is if I don't put any condition then also it will always run 
right??

# A2:

These are excellent questions. They highlight two important differences between GitHub Actions and programming languages like Python or JavaScript.

---

# 1. Does GitHub Actions have `else if`?

**Short answer: No.**

GitHub Actions **does not** have:

```text
if
else if
else
```

like normal programming languages.

For example, this is **NOT valid**:

```yaml
steps:
  - name: Build
    if: github.ref == 'refs/heads/main'

  else if: github.ref == 'refs/heads/dev'   ❌ Invalid

  else:                                     ❌ Invalid
```

GitHub Actions simply doesn't support this syntax.

---

## So how do we achieve the same thing?

Instead of one `if-else` block, every step gets its own `if`.

Example:

```yaml
steps:
  - name: Deploy to Production
    if: github.ref == 'refs/heads/main'
    run: echo "Deploying to Production"

  - name: Deploy to Development
    if: github.ref == 'refs/heads/dev'
    run: echo "Deploying to Development"

  - name: Deploy to Staging
    if: github.ref == 'refs/heads/staging'
    run: echo "Deploying to Staging"
```

Imagine you're on the `dev` branch.

GitHub checks each step independently:

```
Step 1
Is branch == main?
❌ No
Skip

↓

Step 2
Is branch == dev?
✅ Yes
Run

↓

Step 3
Is branch == staging?
❌ No
Skip
```

It doesn't think in terms of "else if." It simply evaluates each step's condition.

---

## Can we mimic an `else`?

Yes.

Suppose you want:

```
if main
    Deploy Production

else
    Deploy Development
```

You can write:

```yaml
- name: Production
  if: github.ref == 'refs/heads/main'
  run: echo "Production"

- name: Development
  if: github.ref != 'refs/heads/main'
  run: echo "Development"
```

If you're on `main`:

```
Production
✅

Development
❌
```

If you're on `dev`:

```
Production
❌

Development
✅
```

That's effectively an `else`.

---

# 2. Why does `if: always()` exist?

This is probably the most confusing part for beginners.

At first glance, you might think:

> If I don't write any `if`, doesn't the step always run anyway?

It seems like it should—but **not exactly**.

---

## Case 1 — No `if`

```yaml
steps:
  - name: Build
    run: ...

  - name: Test
    run: ...

  - name: Upload Logs
    run: ...
```

Suppose the Build step fails.

```
Build
❌ Failed

↓

Test
❌ Skipped

↓

Upload Logs
❌ Skipped
```

Notice something important:

The last step did **not** run.

Why?

Because GitHub's default behavior is:

> Run this step **only if all previous steps succeeded**.

Internally, it's similar to:

```yaml
if: success()
```

even though you didn't write it.

---

## Case 2 — `if: always()`

Now:

```yaml
steps:
  - name: Build
    run: ...

  - name: Upload Logs
    if: always()
    run: ...
```

Suppose Build fails.

```
Build
❌ Failed

↓

Upload Logs
✅ Runs anyway
```

`always()` overrides the default behavior.

---

## Why is this useful?

Imagine you're running automated tests.

```text
Run Tests

↓

Save Test Report

↓

Upload Report

↓

Notify Team
```

The tests fail.

Without `always()`:

```
Run Tests
❌

↓

Save Report
Skipped

↓

Upload Report
Skipped

↓

Notify
Skipped
```

Now you have no report explaining what went wrong.

With `always()`:

```
Run Tests
❌

↓

Save Report
✅

↓

Upload Report
✅

↓

Notify
✅
```

You still get the logs and reports, which are often the most valuable part when debugging failures.

---

## Another common use

Cleaning up resources.

Suppose your workflow creates a temporary server.

```
Create Server

↓

Run Tests

↓

Delete Server
```

If tests fail:

```
Create Server
✅

↓

Run Tests
❌

↓

Delete Server
❌ Skipped
```

Now you've left the temporary server running, which may waste money or resources.

Instead:

```yaml
- name: Delete Server
  if: always()
  run: ./delete-server.sh
```

Now:

```
Create Server
✅

↓

Run Tests
❌

↓

Delete Server
✅
```

Cleanup always happens.

---

# Summary

* GitHub Actions **does not support** `else if` or `else`. Instead, each job or step has its own `if` condition.
* A missing `if` does **not** mean "always run." It means "run only if all previous steps succeeded" (the default behavior is effectively `if: success()`).
* `if: always()` is used when you want a step to run **even if earlier steps failed or were skipped**, such as uploading logs, sending notifications, or cleaning up temporary resources.


# Q3:

so only the if: always() step run or will all steps below /after if: always() will also run

- name: Always run (e.g., cleanup)
if: always()
run: echo "Cleanup tasks here"

- name: next step after always
run: echo "next step after always"

# A3:

This is another excellent question. The answer surprises many beginners.

## Short answer

**Only the step that has `if: always()` is guaranteed to run.**

The steps after it **do not automatically inherit** `always()`.

---

Consider your example:

```yaml
steps:
  - name: Build
    run: exit 1

  - name: Always run (e.g., cleanup)
    if: always()
    run: echo "Cleanup tasks here"

  - name: Next step after always
    run: echo "Next step after always"
```

### What happens?

```
Build
❌ Failed

↓

Always run
✅ Runs

↓

Next step after always
❌ Skipped
```

Why is the last step skipped?

Because it has **no `if` condition**, so GitHub uses the default:

```yaml
if: success()
```

Since the Build step failed, `success()` is **false**, so the last step is skipped.

---

## If you want the next step to also run

You must give **that step** an `if: always()` as well.

```yaml
steps:
  - name: Build
    run: exit 1

  - name: Cleanup
    if: always()
    run: echo "Cleaning..."

  - name: Notify Team
    if: always()
    run: echo "Sending notification..."
```

Result:

```
Build
❌ Failed

↓

Cleanup
✅ Runs

↓

Notify Team
✅ Runs
```

---

## Think of each step independently

GitHub evaluates each step one by one.

```
Step 1
Should I run?
↓

Step 2
Should I run?
↓

Step 3
Should I run?
↓

Step 4
Should I run?
```

Each step checks **its own** `if` condition.

There is **no inheritance** like:

```
Step 2 has always()

↓

Therefore Step 3 also has always()

❌ This is NOT how GitHub Actions works.
```

---

## Rule to remember

* **No `if`** → behaves like `if: success()`
* **`if: always()`** → only **that specific step** runs regardless of previous failures.
* Every step decides independently whether to run based on **its own** `if` condition.



# q4: so which steps will run if error occurs

jobs: 
build:
runs-on: ubuntu-latest
steps:- uses: actions/checkout@v4- name: Only run on main branch
if: github.ref == 'refs/heads/main'   
run: echo "This only runs on main"- name: Only run if previous step failed
if: failure()                          - name: Always run (e.g., cleanup)
if: always()                           
# Conditional execution
# Built-in function
run: echo "Something broke — sending alert"
# Runs even if earlier steps failed
run: echo "Cleanup tasks here"- name: Access context info
run: |
          echo "Branch: ${{ github.ref_name }}"
          echo "Actor who triggered this: ${{ github.actor }}"
          echo "Commit SHA: ${{ github.sha }}"
          echo "Event name: ${{ github.event_name }}"


          
# A4:

Let's first format your workflow correctly, because the formatting got mixed together.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Only run on main branch
        if: github.ref == 'refs/heads/main'
        run: echo "This only runs on main"

      - name: Only run if previous step failed
        if: failure()
        run: echo "Something broke — sending alert"

      - name: Always run (e.g., cleanup)
        if: always()
        run: echo "Cleanup tasks here"

      - name: Access context info
        run: |
          echo "Branch: ${{ github.ref_name }}"
          echo "Actor: ${{ github.actor }}"
          echo "Commit SHA: ${{ github.sha }}"
          echo "Event: ${{ github.event_name }}"
```

Now let's go through different scenarios.

---

# Scenario 1: Everything succeeds on the `main` branch

```
Checkout
✅

↓

Only run on main
✅

↓

failure()
❌ false → Skipped

↓

always()
✅

↓

Access context info
✅
```

Result:

| Step                | Runs? |
| ------------------- | ----- |
| Checkout            | ✅     |
| Only run on main    | ✅     |
| failure()           | ❌     |
| always()            | ✅     |
| Access context info | ✅     |

---

# Scenario 2: Push to the `dev` branch

The second step has:

```yaml
if: github.ref == 'refs/heads/main'
```

Since you're on `dev`, that condition is **false**.

A skipped step is **not considered a failure**.

Execution becomes:

```
Checkout
✅

↓

Only run on main
⏭️ Skipped

↓

failure()
❌ false

↓

always()
✅

↓

Access context info
✅
```

Notice:

The skipped step does **not** make `failure()` true.

---

# Scenario 3: Checkout fails

Suppose this happens:

```
Checkout
❌ Failed
```

Now GitHub checks every remaining step.

---

### Step 2

```yaml
if: github.ref == 'refs/heads/main'
```

Although the branch may be `main`, GitHub's normal step behavior is still to stop after a failure unless the condition explicitly overrides it. This step will **not run** after the failed checkout.

```
Skipped
```

---

### Step 3

```yaml
if: failure()
```

Now:

```
failure()

↓

true
```

So this runs.

```
✅ Sending alert
```

---

### Step 4

```yaml
if: always()
```

Always means always.

```
✅ Cleanup
```

---

### Step 5

No `if`.

Which means GitHub behaves like

```yaml
if: success()
```

But success is now false.

So

```
Skipped
```

---

The final result is:

| Step                | Runs?     |
| ------------------- | --------- |
| Checkout            | ❌ Failed  |
| Only run on main    | ❌ Skipped |
| failure()           | ✅         |
| always()            | ✅         |
| Access context info | ❌ Skipped |

---

# Visual Flow

```
Checkout
❌ Failed

↓

Only run on main
❌ Skipped

↓

failure()
✅ Runs

↓

always()
✅ Runs

↓

Access context
❌ Skipped
```

---

# The important rule

Think of GitHub checking every remaining step after a failure:

```
Did something fail earlier?

↓

Yes

↓

This step has...

if: failure()   → ✅ Run

if: always()    → ✅ Run

No if           → ❌ Skip (defaults to success())

if: success()   → ❌ Skip

if: github.ref == ... → ❌ Skip because it doesn't override the failure state
```

The key idea is that **ordinary `if` conditions (like checking the branch) don't automatically continue execution after a previous step has failed**. Only conditions such as `always()`, `failure()`, or (in another case) `cancelled()` are designed to override the default "stop after failure" behavior. That's why `failure()` and `always()` are so commonly used for notifications and cleanup.
