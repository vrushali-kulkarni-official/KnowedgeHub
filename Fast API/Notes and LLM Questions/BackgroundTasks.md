Excellent topic. **Background Tasks** are one of FastAPI's most useful features, but many beginners misunderstand what they actually do.

I'll teach it exactly how FastAPI executes it internally.

---

# Step 1: The Problem

Imagine you have an API endpoint.

```python
@app.post("/register")
def register():
    create_user()
    send_email()
    return {"success": True}
```

Suppose

```
create_user()  -> 100 ms
send_email()   -> 5 seconds
```

The browser waits...

```
Request
   │
   ▼
Create user (100ms)
   │
   ▼
Send email (5 sec)
   │
   ▼
Return Response
```

The user waits **5.1 seconds**.

That's terrible.

The user doesn't actually care whether the email has already been sent.

They just want

> "Registration Successful"

immediately.

---

# Step 2: What if we return first?

Instead we want

```
Request
   │
   ▼
Create user
   │
   ▼
Return Response Immediately
   │
   ▼
Send Email
```

Now the response comes back in

```
100 ms
```

while the email is sent afterward.

That is exactly what **BackgroundTasks** does.

---

# Step 3: What is BackgroundTasks?

`BackgroundTasks` is simply a container that stores functions to execute **after the response has already been sent**.

Think of it like a TODO list.

```
BackgroundTasks

Task 1
Task 2
Task 3
```

When your endpoint finishes...

FastAPI says

> "Now execute everything in this list."

---

# Step 4: Looking at your code

```python
from fastapi import BackgroundTasks
```

This imports FastAPI's background task manager.

---

Endpoint

```python
@app.post("/send-notification/{email}")
```

Suppose we call

```
POST

/send-notification/john@gmail.com
```

---

FastAPI creates

```
BackgroundTasks()

(empty)
```

and injects it here

```python
def send_notification(
    email: str,
    background_tasks: BackgroundTasks
):
```

So before your function runs

```
background_tasks

↓

[]
```

No tasks yet.

---

# Step 5: First background task

```python
background_tasks.add_task(write_log, f"Notified {email}")
```

Notice something.

You are **NOT calling** the function.

Wrong:

```python
write_log(...)
```

Correct:

```python
background_tasks.add_task(write_log, ...)
```

You are saying

> "Run this later."

Internally FastAPI stores

```
Task

Function:
write_log

Arguments:
"Notified john@gmail.com"
```

Now the list becomes

```
Task List

1.
write_log(
    "Notified john@gmail.com"
)
```

---

# Step 6: Second task

```python
background_tasks.add_task(send_email, email, "Hello!")
```

Now the list becomes

```
Task List

1.
write_log(...)

2.
send_email(...)
```

Nothing has executed yet.

Only stored.

---

# Step 7: Return response

```python
return {"message": "Notification queued"}
```

FastAPI immediately sends

```json
{
    "message": "Notification queued"
}
```

The client receives this instantly.

At this moment

The request is finished from the client's perspective.

---

# Step 8: Now FastAPI executes the tasks

After sending the response,

FastAPI starts executing

```
write_log(...)
```

This function

```python
def write_log(message):
```

runs

```python
time.sleep(2)
```

Pretend writing the log is slow.

After 2 seconds

```
log.txt

Notified john@gmail.com
```

gets written.

---

Next

FastAPI runs

```python
send_email("john@gmail.com", "Hello!")
```

which prints

```
Sending to john@gmail.com: Hello!
```

---

Timeline

```
Client
   │
   │ Request
   ▼

FastAPI

Store Task #1
Store Task #2

Return Response
        │
        │
Client gets response immediately
        │
        ▼

Run Task #1

Run Task #2
```

---

# Step 9: Why not just call the function?

If you wrote

```python
write_log(...)
send_email(...)
return {...}
```

Execution becomes

```
write_log

↓

2 sec

↓

send_email

↓

return response
```

The client waits.

With BackgroundTasks

```
Store task

↓

Store task

↓

Return response

↓

Run task
```

Much better user experience.

---

# Step 10: Understanding add_task()

Syntax

```python
background_tasks.add_task(function, arg1, arg2, arg3)
```

Example

```python
background_tasks.add_task(send_email, "john@gmail.com", "Hello")
```

Later FastAPI executes

```python
send_email("john@gmail.com", "Hello")
```

Exactly as if you had called it yourself.

---

# Step 11: Execution order

Tasks execute in the order they were added.

```
Task 1

↓

Task 2

↓

Task 3
```

In your example

```
write_log()

↓

send_email()
```

---

# Step 12: Can BackgroundTasks return values?

No.

Example

```python
result = background_tasks.add_task(...)
```

This makes no sense.

The function runs later.

Its return value is ignored.

Background tasks are intended for **side effects**, such as:

* Sending an email
* Writing logs
* Saving analytics
* Sending push notifications
* Cleaning temporary files
* Updating caches

---

# Step 13: Are they asynchronous?

This is where many people get confused.

Consider

```python
background_tasks.add_task(write_log)
```

This **does not** mean:

> "Create a new worker process."

It also **does not** mean:

> "Send this task to another machine."

Instead:

* The HTTP response is sent first.
* After the response is finished, FastAPI (through Starlette) runs the queued background tasks within the application's process.
* The client doesn't wait for them, but they are still executed by the same application, not by a separate distributed job system.

So they are **background relative to the client request**, not a full-fledged background job queue.

---

# Step 14: When should you use BackgroundTasks?

Good use cases:

* ✅ Send welcome email
* ✅ Write audit logs
* ✅ Store analytics
* ✅ Update cache
* ✅ Delete uploaded temp files
* ✅ Notify another service if a slight delay is acceptable

---

Bad use cases:

* ❌ Video processing (minutes)
* ❌ Machine learning training
* ❌ Large report generation
* ❌ Image rendering
* ❌ Long-running ETL jobs

For long-running or mission-critical work, use a dedicated task queue such as Celery, RQ, or Dramatiq, where jobs can be retried, monitored, and processed by separate workers.

---

# Step 15: Visual Summary

```
                Request
                   │
                   ▼

        Endpoint Starts
                   │
                   ▼

   background_tasks.add_task(...)
                   │
                   ▼

   background_tasks.add_task(...)
                   │
                   ▼

        return response
                   │
        Client receives response
                   │
                   ▼

     FastAPI runs Task 1
                   │
                   ▼

     FastAPI runs Task 2
                   │
                   ▼

             Finished
```

# Mental Model

Think of `BackgroundTasks` as leaving sticky notes for FastAPI:

```
Endpoint:

✓ Return response now

Sticky Notes:

[ ] Write log

[ ] Send email

After the customer leaves...

FastAPI reads the sticky notes one by one and performs each task.
```

The key idea is that the work is **deferred until after the HTTP response is sent**, improving the user's perceived response time, but it still runs inside the same FastAPI application rather than in an external job-processing system.
