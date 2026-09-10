# RQ (Redis Queue) — A Complete Beginner's Guide

Great choice! RQ is one of the simplest ways to understand background job processing. Let me build this up from the very beginning, so by the end you'll not only know *how* to use RQ, but *why* it exists and *when* to use it.

---

## 1. The Problem RQ Solves

Imagine you're building a website where users can upload a photo, and your server must:
1. Resize the photo
2. Compress it
3. Generate a thumbnail
4. Email the user "done!"

If you do all this **while the user waits**, here's what happens:

```
User clicks "Upload"
    → Server processes photo (20 seconds)
    → User stares at a loading spinner for 20 seconds 😠
    → Page finally responds
```

This is called **synchronous processing**. The big problems:

- **Bad user experience** — users hate waiting.
- **Server can only handle a few users at a time** — while one photo is being processed, that worker is busy and can't serve anyone else.
- **If the server crashes mid-processing, the work is lost.**
- **Some tasks aren't even user-triggered** — e.g., "send a weekly email every Monday at 9am." There's no user waiting for that.

**The solution: a task queue.** Instead of doing the work immediately, you write a note that says *"hey, do this work later"* and a separate program (a **worker**) picks it up and does it in the background.

---

## 2. The Evolution — How People Solved This Before

Understanding history helps you appreciate RQ. Here's how the industry progressed:

### Stage 1: Do it synchronously (just make the user wait)
```python
@app.route("/upload")
def upload():
    photo = save_photo()
    process_photo(photo)   # blocks for 20 seconds
    return "Done"
```
**Disadvantage:** everything above. Terrible at scale.

### Stage 2: Cron jobs ("do it on a schedule")
Linux `cron` runs scripts at fixed times:
```
0 9 * * 1  python send_weekly_email.py
```
**Disadvantages:**
- ❌ Only time-based, not event-based. "Send email *when user signs up*" is hard.
- ❌ No retry logic — if the script fails at 9:00 AM, too bad.
- ❌ No tracking — did it run? Did it succeed? You must build logging yourself.
- ❌ Can't easily say "process this *specific* photo uploaded by *this* user."

### Stage 3: Threads / multiprocessing (do it "in parallel" in the same app)
```python
import threading
threading.Thread(target=process_photo, args=(photo,)).start()
```
**Disadvantages:**
- ❌ If the server restarts or crashes, the thread dies and the task is **lost forever**.
- ❌ Threads share memory with the web app — a memory-hungry task can crash your whole website.
- ❌ No persistence — you can't have 10 tasks waiting to run.
- ❌ Hard to monitor and no retries.

### Stage 4: Full message brokers + heavy task queues (Celery with RabbitMQ)
Celery is the industry standard task queue. **Disadvantages for beginners / small teams:**
- ❌ **Complex setup** — you need a separate message broker (RabbitMQ), which is itself a beast to install and configure.
- ❌ Steep learning curve — decorators, brokers, backends, exchanges, routing keys...
- ❌ A lot of configuration for simple needs.
- ❌ Overkill for "just run this function in the background."

### Stage 5: **RQ** 🎉
RQ's philosophy: *you already know Python functions. Sending a function to run in the background should be one line.*

```python
q.enqueue(process_photo, photo)
```

That's it. No broker software to install beyond Redis (which you're already learning!), no configuration files, no decorators.

---

## 3. How RQ Works — The Big Picture

```
┌──────────┐   1. enqueue    ┌─────────┐   2. pick up job   ┌─────────┐
│ Your App │ ───────────────→│  Redis  │──────────────────→│ Worker  │
│ (Flask/  │  "do X with Y"  │ (queue:  │   "here's a job!"  │(separate│
│  Django/ │                 │  a list) │                    │ process)│
│  script) │ ←───────────────│         │←───────────────────│         │
└──────────┘   4. result/    └─────────┘    3. store result  └─────────┘
               status stored                 back in Redis
```

**The 4 core pieces:**

| Concept | What it is | Analogy |
|---|---|---|
| **Queue** | A named list stored in Redis where jobs wait | A to-do list on a whiteboard |
| **Job** | One unit of work: a function + its arguments | One item written on the list |
| **Worker** | A separate Python process that watches a queue and executes jobs | An employee who reads the whiteboard and does the tasks |
| **Redis** | The shared memory holding queues, jobs, and results | The whiteboard itself |

**Why is this better than the "old ways"?**

✅ **Persistence** — jobs live in Redis. Worker crashes? Restart it; the job is still there.
✅ **Separation** — heavy work happens in a different process than your web app. Your website stays fast and responsive.
✅ **Retriability** — failed jobs can be retried automatically.
✅ **Scalability** — one worker is slow? Start 5 workers. Need more? Start workers on other machines — Redis is shared.
✅ **Observability** — every job has a status (`queued`, `started`, `finished`, `failed`) you can query.

---

## 4. Getting Started (Hands-On)

### Installation
```bash
pip install rq
```
You also need Redis running. If you don't have it yet:
```bash
# macOS
brew install redis && brew services start redis

# Ubuntu/Debian
sudo apt install redis-server && sudo service redis-server start

# Or with Docker
docker run -p 6379:6379 redis
```

### Your first job

Create a file `tasks.py`:
```python
# tasks.py
import time

def say_hello(name):
    time.sleep(3)          # pretend this is hard work
    return f"Hello, {name}!"
```

Create `main.py`:
```python
# main.py
import redis
from rq import Queue
from tasks import say_hello

# Connect to Redis
conn = redis.Redis()

# Create a queue
q = Queue(connection=conn)

# Enqueue the job — this returns INSTANTLY, doesn't wait 3 seconds!
job = q.enqueue(say_hello, "Alice")

print("Job enqueued! ID:", job.id)
print("Status:", job.get_status())   # probably 'queued'
```

Now **start a worker** in a separate terminal:
```bash
rq worker
```

You'll see output like:
```
*** Listening for work on default...
default: Job OK (say_hello('Alice'))
Result is kept for 500 seconds
```

Now in your main program you can check the result:
```python
from rq.job import Job
job = Job.fetch(job_id, connection=conn)

print(job.get_status())      # 'finished'
print(job.result)            # 'Hello, Alice!'
```

---

## 5. The Core API in Detail

### 5.1 Enqueueing with arguments

Just call the function with its args and kwargs after it:

```python
job = q.enqueue(send_email, "user@example.com", subject="Welcome!", urgent=False)
# equivalent to calling: send_email("user@example.com", subject="Welcome!", urgent=False)
```

**Important beginner gotcha:** the function must be **importable** by the worker. That's why `say_hello` lives in `tasks.py`, not inside `main.py`. The worker needs to do `from tasks import say_hello`. Functions defined in `if __name__ == "__main__":` won't work.

### 5.2 Job status lifecycle

Every job goes through these statuses:

```
queued → started → finished
                  ↘ failed → (optionally retried → queued again)
```

Check them with:
```python
job.get_status()
# 'queued', 'started', 'finished', 'failed', 'deferred', 'canceled'
```

### 5.3 Getting results later

Jobs are identified by a UUID. Store it, and fetch it anytime (even from a different process — this is the power of Redis being shared):

```python
job_id = job.id
# ... save it in your database, session, etc.

# Later, anywhere:
from rq.job import Job
job = Job.fetch(job_id, connection=redis.Redis())
if job.is_finished:
    print(job.result)
elif job.is_failed:
    print("Oh no:", job.exc_info)   # the full Python traceback!
```

### 5.4 Job TTLs (how long things live in Redis)

By default, finished job results are kept for **500 seconds**. Control this:

```python
q.enqueue(say_hello, "Bob", result_ttl=86400)   # keep result for 1 day
q.enqueue(big_job, ttl=300)                      # job expires if not run within 5 min
```

---

## 6. Workers — The Engines of RQ

A worker is a long-running process:

```bash
rq worker                 # listens on the "default" queue
rq worker high default    # listens on "high" first, then "default"
rq worker --burst         # processes all queued jobs, then exits (great for testing)
```

Each worker:
1. Connects to Redis
2. Blocks waiting for a job
3. Runs the function
4. Stores the result/status back in Redis
5. Goes back to waiting

### Running workers in the background (production)

Don't just leave a terminal open. Use a process manager:

**With `systemd`** (Linux servers):
```ini
# /etc/systemd/system/rq-worker.service
[Unit]
Description=RQ Worker
After=network.target

[Service]
WorkingDirectory=/srv/myapp
ExecStart=/srv/myapp/venv/bin/rq worker high default
Restart=always

[Install]
WantedBy=multi-user.target
```

**With Supervisor** (popular, simpler config):
```ini
[program:rq-worker]
command=/srv/myapp/venv/bin/rq worker default
directory=/srv/myapp
autorestart=true
```

**In Docker/Kubernetes**, workers run as their own containers — which is the whole point: web app containers stay light, worker containers do the heavy lifting.

---

## 7. Failure Handling & Retries

Things fail. Networks hiccup, files are missing, APIs time out. RQ has built-in retry:

```python
q.enqueue(unreliable_task, retry=Retry(max=3, interval=10))
```

This means: *if the job raises an exception, retry up to 3 times, waiting 10 seconds between attempts.*

Or with custom backoff:
```python
from rq import Retry

q.enqueue(unreliable_task, retry=Retry(max=5, interval=[10, 30, 60, 300]))
# waits 10s, then 30s, then 60s, then 300s between retries
```

You can also inspect failures:
```python
failed = q.failed_job_registry   # all failed jobs in this queue
for job in failed.get_jobs():
    print(job.id, job.exc_info)  # full traceback
    job.requeue()                # try it again manually
```

### Job timeouts

A job that hangs forever will block a worker forever. Set a timeout:

```python
q.enqueue(slow_task, job_timeout=300)    # 5 minutes, then killed
# or set a default for the whole queue:
q = Queue('default', connection=conn, default_timeout=600)
```

---

## 8. Multiple Queues & Priorities

Not all jobs are equal. Sending a password-reset email matters more than generating a monthly report.

```python
q_high = Queue('high', connection=conn)
q_default = Queue('default', connection=conn)
q_low = Queue('low', connection=conn)

q_high.enqueue(send_password_reset, user_id)
q_low.enqueue(generate_monthly_report)
```

Start a worker that respects priority:
```bash
rq worker high default low
```

The worker always drains queues **left to right**: it finishes everything in `high` before touching `default`, and everything in `default` before `low`.

**When to use which:**
- **One queue** — fine for most small projects. Start here!
- **Multiple queues** — when slow jobs would delay urgent ones, or when you want to run different workers with different configs (e.g., a worker with more memory for image processing).

---

## 9. Scheduled & Delayed Jobs

RQ can run jobs in the future:

```python
from datetime import timedelta, datetime

# Run 10 minutes from now
q.enqueue_in(timedelta(minutes=10), send_reminder_email, user_id)

# Run at a specific time
q.enqueue_at(datetime(2026, 9, 10, 9, 0), send_newsletter)
```

⚠️ **Gotcha:** scheduled jobs need a scheduler running, OR you run a worker with the `--with-scheduler` flag:

```bash
rq worker --with-scheduler
```

(Before RQ 1.x, you needed a separate `rqscheduler` process. Now the worker has one built in — that's the "new approach being better" pattern again: fewer moving parts.)

---

## 10. Callbacks — Run Code When a Job Finishes

```python
def notify_admin(job, connection, result, *args, **kwargs):
    print(f"Job {job.id} finished with result: {result}")

def handle_failure(job, connection, type, value, traceback):
    print(f"Job {job.id} FAILED: {value}")

q.enqueue(
    process_photo, photo,
    on_success=notify_admin,
    on_failure=handle_failure,
)
```

Also `on_stop` for when a job is killed (e.g., timeout). Useful for cleanup.

---

## 11. Monitoring Your Queues

### Command line
```bash
rq info        # shows queues, workers, and job counts at a glance
```

### RQ Dashboard (web UI)
```bash
pip install rq-dashboard
rq-dashboard
```
Then open http://localhost:9181 — you can see queues, workers, job statuses, and even requeue failed jobs from a nice web interface. As a beginner, this is fantastic for building intuition.

---

## 12. RQ vs Celery — When to Use What?

This is the most common "what vs what" question:

| | **RQ** | **Celery** |
|---|---|---|
| Learning curve | Very gentle | Steep |
| Setup | Redis only | Redis/RabbitMQ + more config |
| Performance | Good (~15k jobs/sec) | Higher throughput |
| Features | Core features, clean API | Huge: workflows (chains, chords, groups), many brokers, eventlet, etc. |
| Monitoring | rq info + rq-dashboard | Flower (excellent) |
| Best for | Small–medium apps, beginners, Python-only shops | Large-scale, complex pipelines, thousands of tasks/sec |

**Rule of thumb:**
- 🟢 **Use RQ when:** you're learning, your project is small/medium, you want something running in 10 minutes, you already have Redis.
- 🟡 **Consider Celery when:** you need complex workflows ("task A then B then 50 parallel C's then D"), extremely high throughput, or features like worker pools with greenlets.

And honestly — many production systems happily use RQ for years. "Simple" is a feature.

---

## 13. Common Beginner Mistakes (Learn From Others' Pain)

1. **Defining tasks inside `if __name__ == "__main__":`** → worker can't import them. Put tasks in a module.
2. **Forgetting to start a worker** → jobs sit in `queued` forever. Check `rq info`.
3. **Assuming enqueue runs the function** → `q.enqueue(f)` does *not* call `f`. It stores its name and arguments.
4. **Expecting the result immediately** → the job runs when a worker gets to it. Poll status, use callbacks, or use a framework integration.
5. **Not handling failures** → check the failed registry; set retries for flaky tasks.
6. **Timeouts too low/high** → a job killed at 180s might be 90% done; a job with no timeout might hang your worker forever.
7. **Passing huge objects as arguments** → RQ pickles args into Redis. Pass IDs, not giant objects (e.g., pass `photo_id`, and let the worker re-fetch the photo from the DB).

---

## 14. A Complete Mini-Example

```python
# tasks.py
import time, random
from rq import Retry

def generate_report(user_id):
    time.sleep(5)
    if random.random() < 0.3:
        raise Exception("Simulated flakiness!")
    return f"Report for user {user_id} ready"
```

```python
# app.py
import redis
from rq import Queue, Retry
from rq.job import Job
from tasks import generate_report

conn = redis.Redis()
q = Queue(connection=conn)

job = q.enqueue(
    generate_report, 42,
    retry=Retry(max=3, interval=[5, 15, 60]),
    job_timeout=120,
    result_ttl=3600,
)
print("Enqueued:", job.id)
```

```bash
# Terminal: run the worker
rq worker --with-scheduler
```

---

## TL;DR Cheat Sheet

```python
from redis import Redis
from rq import Queue, Retry
from rq.job import Job

conn = Redis()
q = Queue(connection=conn)

# Enqueue
job = q.enqueue(my_func, arg1, kwarg1="x")

# Enqueue with options
job = q.enqueue(my_func, retry=Retry(max=3, interval=10),
                job_timeout=300, result_ttl=86400, on_success=my_callback)

# Schedule
q.enqueue_in(timedelta(minutes=5), my_func)
q.enqueue_at(datetime(2026, 9, 10, 9, 0), my_func)

# Check status/result
job.get_status()      # queued/started/finished/failed
job.result
job.exc_info          # traceback if failed

# Fetch later by ID
job = Job.fetch(job_id, connection=conn)

# Multiple queues
high = Queue("high", connection=conn)

# Worker (terminal)
# rq worker --with-scheduler high default
```

---

Want me to go deeper on any part next? Good follow-ups:
1. **Building a real Flask/Django app** with RQ (full project structure)
2. **RQ + scheduled jobs in depth** (cron-like patterns)
3. **Deploying workers** (Docker, systemd, Supervisor walkthrough)
4. **A hands-on exercise** where you build and run something yourself

Which one sounds good?
