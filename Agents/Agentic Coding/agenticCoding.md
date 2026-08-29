# Building Agentic AI Systems: A Complete Framework

I'll teach you this in layers — the same way you should learn it. By the end, you'll have a mental model you can apply to any project, not just this one.

---

## Part 0: The Mental Model (learn this first, everything else follows)

Every agentic system — no matter the framework — is just **4 things** wired together:

| Component  | What it is                                                | File(s) that implement it       |
| ---------- | --------------------------------------------------------- | ------------------------------- |
| **Brain**  | LLM + instructions (prompt) that *decides* what to do     | `prompts.py`, agent definitions |
| **Hands**  | Tools that let it *act* (run code, read files, call APIs) | `tools/`                        |
| **Memory** | State — what it knows so far                              | `state.py`, checkpointers       |
| **Loop**   | Keep acting until the task is done                        | `graph.py` (LangGraph)          |

**The best analogy is a company.** Memorize this mapping:

- **Supervisor agent** = manager. Doesn't do everything — routes work, checks results.
- **Sub-agents** = specialists (coder, researcher, DBA). Deep but narrow.
- **Tools** = software they use (IDE, browser, terminal).
- **Skills** = SOP binders / playbooks. Knowledge, loaded only when needed.
- **Reviewer agent** = QA. Never the same person who built the thing.
- **State** = the project tracker / meeting notes everyone shares.

Every file you'll ever write in an agentic project configures one of these roles. If you can answer *"which company role does this file define?"* you can design any agent system.

---

## Level 1: The Atom — A Single Agent with Tools

Before orchestrating agents, you must understand **one** agent deeply.

### The agentic loop (this is THE fundamental)

Every agent ever built runs this loop:

```python
# pseudocode — this is what ALL agent frameworks do under the hood
def agent(task):
    context = [system_prompt, task]
    while True:
        response = llm(context)           # 1. THINK: LLM decides next action
        if response.tool_calls:            # 2. ACT: it wants to use a tool
            for call in response.tool_calls:
                result = execute_tool(call)
                context.append(result)     # 3. OBSERVE: feed result back
        else:
            return response.text           # 4. DONE: no more tool calls
```

**Think → Act → Observe → repeat.** LangGraph just wraps this loop in a graph. In LangGraph it's one line:

```python
from langgraph.prebuilt import create_react_agent

coder = create_react_agent(model, tools=[read_file, write_file, run_tests], prompt=CODER_PROMPT)
```

### Anatomy of a system prompt — the 8-section template

This template works for **any** agent in **any** project. Internalize it:

```
1. IDENTITY      — who you are (1-2 sentences)
2. MISSION       — your ONE job
3. CONTEXT       — project background, tech stack, conventions
4. TOOLS         — what you have, and WHEN to use each
5. RULES         — hard constraints (must / must not)
6. PROCEDURE     — numbered steps: how you work
7. OUTPUT FORMAT — exact shape of your final answer
8. ESCALATION    — when to stop and hand back / give up
```

Example — a coder sub-agent prompt:

```python
CODER_PROMPT = """You are a senior Python engineer on a FastAPI + LangGraph SaaS project.

## Mission
Implement exactly the task you are given. Nothing more, nothing less.

## Context
- Stack: Python 3.12, FastAPI, LangGraph, SQLAlchemy, PostgreSQL
- Layout: app/api (routes), app/agents (agents), app/tools (tools), tests/
- All new endpoints need Pydantic schemas and tests.

## Tools
- read_file: use FIRST to understand existing code before changing it
- write_file: create/modify files
- run_tests: run after every change; tests must pass before you finish

## Rules
- Never modify files outside the scope of your task
- Never invent APIs — read the actual code first
- Follow existing project conventions (naming, imports, structure)

## Procedure
1. Restate the task requirements as a checklist
2. read_file everything relevant
3. Write a plan (files to create/change)
4. Implement
5. run_tests; fix failures
6. Report

## Output format
End with a report: files changed, what was done, test results, anything unclear.

## Escalation
If requirements are contradictory or a dependency is missing, STOP and report
the blocker instead of guessing.
"""
```

Notice the prompt is an **operating manual**, not a wish list. Imperative, specific, procedural.

### Anatomy of a tool

```python
from langchain_core.tools import tool

@tool
def run_tests(path: str) -> str:
    """Run pytest on the given path. Use after every code change to verify
    nothing is broken.

    Args:
        path: file or directory to test, e.g. "tests/test_api/"

    Returns:
        Pass/fail summary with failing test names and error messages.
    """
    result = subprocess.run(["pytest", path, "--tb=short"], capture_output=True, text=True)
    # Return RICH errors — the agent can't self-correct from "error occurred"
    return result.stdout[-4000:]  # bounded! never dump unbounded output
```

**Tool design rules:**

1. Name = one verb (`read_file`, not `file_utils`)
2. The docstring is a **contract**: what it does, *when* to use it, args, returns
3. Errors must be descriptive (agent reads them to self-correct)
4. **Bound the output** — context is your scarcest resource

---

## Level 2: Sub-Agents — Splitting the Company

### When to create a sub-agent (and when NOT to)

Create a sub-agent only when at least one of these is true:

| Reason                  | Example                                                          |
| ----------------------- | ---------------------------------------------------------------- |
| **Different toolset**   | Coder needs file+terminal tools; researcher needs web search     |
| **Different expertise** | Different prompt, different conventions, different model         |
| **Context isolation**   | Specialist burns 50k tokens working; returns a 500-token summary |

**Do NOT** create a sub-agent per task ("agent for login page", "agent for signup page"). Create them per **domain** ("coder", "researcher", "reviewer"). Over-decomposition is the #1 beginner mistake.

### The key insight: sub-agents communicate through typed contracts

A sub-agent is just an agent with a strict **input contract** and **output contract** — like a good work ticket in, structured report out:

```python
from pydantic import BaseModel, Field
from typing import Literal

class TaskResult(BaseModel):
    """Every sub-agent returns this — its report to the supervisor."""
    summary: str = Field(description="What was done, 2-4 sentences")
    files_changed: list[str] = Field(default_factory=list)
    status: Literal["success", "partial", "failed"]
    notes_for_reviewer: str = Field(
        description="Anything the reviewer should pay attention to"
    )
```

### Critical rule: context hygiene

The #1 performance killer in multi-agent systems:

```python
# agents/coder/agent.py
coder_graph = create_react_agent(model, tools=CODER_TOOLS, prompt=CODER_PROMPT)

def coder_node(state: State) -> dict:
    result = coder_graph.invoke({
        "messages": [{"role": "user", "content": state["task"]}]
    })
    # ❌ WRONG: return result — dumps the ENTIRE transcript into shared state
    # ✅ RIGHT: extract only the final report
    return {
        "task_history": [{
            "agent": "coder",
            "task": state["task"],
            "result": result["messages"][-1].content,
        }]
    }
```

Sub-agents work in their **own** context and hand back a **summary**. That's the entire point of delegation — the supervisor's context stays clean.

---

## Level 3: The Supervisor — Delegation vs. Doing It Yourself

This answers your first big question. Here's the trick that makes it elegant:

> **Make "handle it myself" a first-class route.** The supervisor is an LLM call that returns a structured routing decision — and one of the legal destinations is `direct` (answer it yourself).

### The routing decision schema

```python
# agents/supervisor/schemas.py
class RouteDecision(BaseModel):
    """How to handle the user's request."""
    reasoning: str = Field(description="One sentence: why this route")
    destination: Literal["coder", "researcher", "direct"] = Field(
        description="Pick a specialist for complex/specialized work. "
                    "Pick 'direct' for simple questions, chat, or anything "
                    "needing no specialist tools — handle it yourself."
    )
    task_spec: str = Field(
        description="Self-contained instructions for the handler: goal, "
                    "constraints, files involved, definition of done."
    )
```

### The decision logic the LLM learns (put it in the router prompt)

| Signal                                     | → Delegate | → Handle directly |
| ------------------------------------------ | ---------- | ----------------- |
| Multi-step, multi-file work                | ✓          |                   |
| Needs specialist tools (terminal, search)  | ✓          |                   |
| Single factual answer / explanation        |            | ✓                 |
| Trivial (greeting, small talk, formatting) |            | ✓                 |
| **No sub-agent exists for it**             |            | ✓                 |

### Hybrid routing (pro move: rules first, LLM second)

LLM routing costs tokens. Handle the obvious cases with code first:

```python
import re

def is_trivial(state) -> bool:
    last = state["messages  "][-1].content
    return (
        len(last) < 80
        and not re.search(r"\b(code|fix|test|implement|refactor|bug|api)\b", last.lower())
    )
```

### The supervisor node

```python
# agents/supervisor/agent.py
from langgraph.graph import END
from langgraph.types import Command

router_llm = small_model.with_structured_output(RouteDecision)  # cheap model for routing!

def supervisor(state: State) -> Command[Literal["coder", "researcher", "direct", END]]:
    # Layer 0: rule-based shortcut (free)
    if is_trivial(state):
        return Command(goto="direct", update={"task": state["messages"][-1].content})

    # Layer 1: LLM routing
    decision = router_llm.invoke([
        {"role": "system", "content": ROUTER_PROMPT},
        *state["messages"],
        {"role": "user", "content": f"Task history so far: {state['task_history']}"},
    ])
    return Command(goto=decision.destination, update={"task": decision.task_spec})
```

Two things to notice:

1. **`Command(goto=..., update=...)`** — routes AND passes the task spec in one move. This is LangGraph's handoff pattern.
2. **Use a small/cheap model for routing** — it's a classification task, not a reasoning task. Save the strong (expensive) model for the specialists.

### The `task_spec` discipline — "write tickets, not vibes"

The `task_spec` field is where supervisor quality lives. A good spec is a good Jira ticket: **goal, constraints, files in scope, definition of done**. Bad specs produce drifting sub-agents. This is a skill you develop by reading the specs your router writes and fixing the router prompt when they're vague.

---

## Level 4: Verification — Who Checks the Work?

This is your second big question, and it has a definitive answer. Learn the principle first:

> **Prefer objective checks over opinions. Prefer fresh eyes over invested ones.**

### The verification ladder (always climb from the bottom)

| Level                | Check                                                           | Who/What           | Trustworthy? | Cost   |
| -------------------- | --------------------------------------------------------------- | ------------------ | ------------ | ------ |
| 1. **Deterministic** | Run tests, lint, type-check, execute the code, validate schemas | Code, no LLM       | ★★★★★        | Free   |
| 2. **Structural**    | Did output match the typed contract?                            | Pydantic           | ★★★★★        | Free   |
| 3. **Rubric review** | LLM checks against a concrete checklist                         | Reviewer sub-agent | ★★★          | Medium |
| 4. **Adversarial**   | Second pass / builder must defend choices                       | Another agent      | ★★★          | High   |

**Level 1 always runs first.** A test suite's verdict is infinitely more reliable than any LLM opinion, and it's free. LLM reviewers should only judge what machines *can't* (does it actually meet the requirement?).

### Who verifies? The definitive answer

**Rule: the builder never signs off their own work.** Same reason a PR author can't approve their own PR — confirmation bias. The builder "believes" it's done; that's why it submitted.

**Rule: the supervisor *orchestrates* verification but doesn't *perform* the deep review.** Three reasons:

1. **Context pollution** — line-by-line review would bloat the supervisor's context, defeating the purpose of delegation
2. **It's a generalist** — the reviewer can be a specialist
3. **Investment bias** — the supervisor wrote the task spec; it's motivated to believe the work matches it

**So the answer is: a dedicated reviewer sub-agent, with fresh context, receiving three things:**

1. The **original requirement** (source of truth — not the builder's summary of it!)
2. The **builder's result**
3. The **deterministic check outputs** (so it doesn't waste effort on what machines already know)

This mirrors a real PR review: the reviewer reads the ticket, the diff, and the CI results — not just the author's "this is done, trust me."

### The reviewer's contract

```python
class Issue(BaseModel):
    severity: Literal["blocker", "warning", "nit"]
    location: str = Field(description="File + function/line")
    description: str
    suggested_fix: str

class ReviewVerdict(BaseModel):
    verdict: Literal["pass", "fail"]
    issues: list[Issue]
    summary: str
```

### The reviewer prompt — the rubric IS the reviewer

A vague reviewer ("is this good?") passes everything. The prompt must demand specificity:

```python
REVIEWER_PROMPT = """You are a strict code reviewer. You did NOT write this code — find what's wrong.

You will receive: the original requirement, the implementation report, and
machine check results (tests/lint). The machine results are ground truth —
never contradict them.

## Review checklist (in order)
1. Does the work satisfy EVERY requirement in the original task? List each
   requirement and mark it met/unmet.
2. Do the machine checks actually cover the requirement? (Tests passing for
   the wrong thing = unverified, not correct.)
3. Any bugs, edge cases, security issues, or convention violations?

## Rules
- verdict "fail" if ANY blocker exists, even if tests pass
- Every issue needs a location and a suggested fix — no vague feedback
- Never review against requirements the builder invented beyond the task
"""
```

### The full verify→fix loop, orchestrated by the supervisor

```
START
  │
  ▼
supervisor ── trivial? ──► direct answer ──► END
  │ ▲
  │ └──────────── verdict ◄─────────────┐
  ▼                                    │
sub-agent (coder/researcher)            │
  │                                    │
  ▼                                    │
machine checks (tests, lint)           │
  │                                    │
  ▼                                    │
reviewer ── pass ──► supervisor ──► END │
  │                                    │
  └── fail AND retries < MAX ──────────┘   (feedback goes back to builder)
  └── fail AND retries = MAX ──► escalate to human / report failure honestly
```

Three orchestration rules encoded in that diagram:

1. **Proportionality** — trivial tasks (`direct`) skip LLM review. Don't spend a reviewer on "what's 2+2". Match verification rigor to task risk.
2. **Bounded retries** — `MAX_RETRIES = 2`, always. Unbounded retry loops are how you burn $200 at 3 AM. After max retries: escalate or report failure honestly.
3. **Feedback must be specific** — when retrying, the builder receives the reviewer's `issues` list, so it *fixes*, not redoes blindly.

The supervisor handles this logic:

```python
MAX_RETRIES = 2

def supervisor(state: State) -> Command[Literal["coder", "researcher", "direct", "reviewer", END]]:
    # 1. Did we just get a review back? Consume its verdict.
    review = state.get("review")
    if review:
        if review["verdict"] == "pass":
            return Command(goto=END, update={
                "messages": [AIMessage(f"✅ Done: {review['summary']}")],
                "review": None, "retries": 0,
            })
        if state["retries"] < MAX_RETRIES:
            failed_agent = state["task_history"][-1]["agent"]
            feedback = "\n".join(f"- [{i['severity']}] {i['location']}: {i['description']}"
                                 for i in review["issues"])
            return Command(goto=failed_agent, update={
                "task": f"Previous attempt failed review. Fix these issues:\n{feedback}",
                "retries": state["retries"] + 1, "review": None,
            })
        return Command(goto=END, update={
            "messages": [AIMessage("⚠️ Task failed after retries. Issues: ...")],
            "review": None, "retries": 0,
        })

    # 2. Otherwise, route as normal (trivial check → LLM router)
    ...
```

The reviewer node itself:

```python
def reviewer_node(state: State) -> dict:
    last = state["task_history"][-1]
    machine_results = run_machine_checks(last)          # tests, lint — Level 1
    verdict = review_llm.with_structured_output(ReviewVerdict).invoke([
        {"role": "system", "content": REVIEWER_PROMPT},
        {"role": "user", "content": f"""
ORIGINAL TASK:\n{last['task']}

BUILDER REPORT:\n{last['result']}

MACHINE CHECK RESULTS:\n{machine_results}
"""},
    ])
    return {"review": verdict.model_dump()}
```

Note what the reviewer does **not** receive: the whole conversation history. Fresh context, just the facts. That's what makes it a real check instead of an echo.

**Bonus (cheap layer): self-check.** Before submitting, the builder runs its own checklist ("re-read requirements, confirm tests pass"). Catches obvious misses for free — but never your *only* layer.

---

## Level 5: Skills — Packaged Expertise

### The problem skills solve

Your coder prompt can't contain everything about FastAPI best practices, your project's conventions, migration procedures, auth patterns... Context is finite, and giant prompts degrade performance.

### The solution: progressive disclosure

A **skill** = a folder containing an `SKILL.md` (procedure + knowledge) plus optional templates/scripts. Only the **name + description (~50 tokens)** is always visible to the agent. The **full body (~1000+ tokens)** loads only when relevant:

```
skills/
├── fastapi-endpoints/
│   ├── SKILL.md
│   └── templates/route_template.py
├── alembic-migrations/
│   └── SKILL.md
└── pydantic-schemas/
    └── SKILL.md
```

```markdown
# skills/fastapi-endpoints/SKILL.md
---
name: fastapi-endpoints
description: Use when creating or modifying FastAPI routes — covers dependency
  injection, auth, response models, and THIS project's routing conventions.
---

## Project conventions
- Routes live in app/api/routes/<domain>.py
- Every endpoint: Pydantic request/response models in app/api/schemas/
- Auth via `Depends(get_current_user)`
...

## Procedure
1. Check if a route for this resource already exists...
2. Define schemas first, then the route
...
```

The `description` is the most important line you'll write — write it as **WHEN to use** ("Use when creating or modifying FastAPI routes"), not what it is.

Implementation is just two tools:

```python
@tool
def list_skills() -> str:
    """List available skills with descriptions. Call first when starting a task
    to see if relevant expertise exists."""
    ...

@tool
def load_skill(name: str) -> str:
    """Load full instructions for a skill. Only call after list_skills showed
    a relevant match."""
    return (SKILLS_DIR / name / "SKILL.md").read_text()
```

### Tool vs. Skill vs. Sub-agent — the decision table

|                 | Tool                    | Skill                                      | Sub-agent                                  |
| --------------- | ----------------------- | ------------------------------------------ | ------------------------------------------ |
| **Is**          | An executable action    | Knowledge/procedure, injected just-in-time | An autonomous worker with its own loop     |
| **Analogy**     | Hammer                  | Carpentry manual                           | Carpenter                                  |
| **Create when** | You need a new *action* | Prompt is bloated with *how-to knowledge*  | You need isolation, own tools, or own loop |

---

## Level 6: Assembling Your FastAPI + LangGraph SaaS Project

### The full file structure

```
project/
├── app/
│   ├── main.py                      # FastAPI app factory
│   ├── api/
│   │   └── routes/
│   │       └── agents.py            # POST /chat — entry point to the graph
│   ├── core/
│   │   ├── config.py                # model names, MAX_RETRIES, API keys
│   │   └── llm.py                   # model factory (cheap router model, strong worker model)
│   ├── graph/
│   │   ├── state.py                 # shared State (TypedDict)
│   │   └── builder.py               # assembles the StateGraph → compiled app
│   ├── agents/
│   │   ├── supervisor/
│   │   │   ├── agent.py             # routing + review verdict handling
│   │   │   ├── prompts.py           # ROUTER_PROMPT
│   │   │   └── schemas.py           # RouteDecision
│   │   ├── coder/
│   │   │   ├── agent.py             # coder_node (wraps sub-graph)
│   │   │   ├── prompts.py
│   │   │   └── tools.py             # read_file, write_file, run_tests
│   │   ├── researcher/
│   │   │   └── ...                  # same shape as coder/
│   │   └── reviewer/
│   │       ├── agent.py             # reviewer_node
│   │       ├── prompts.py           # REVIEWER_PROMPT (the rubric)
│   │       └── schemas.py           # ReviewVerdict, Issue
│   ├── tools/                       # shared tools
│   ├── skills/                      # SKILL.md folders
│   └── services/                    # non-AI business logic
└── tests/
```

**Every agent folder has the same shape: `agent.py` + `prompts.py` + `schemas.py` (+ `tools.py` if private tools).** That consistency is the framework — you can now add a `dba` agent tomorrow by copying the folder shape.

### The shared state

```python
# graph/state.py
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # conversation with the USER
    task: str                                  # current task spec for a worker
    task_history: list[dict]                   # completed work (summaries only!)
    review: dict | None                        # latest ReviewVerdict
    retries: int                               # bounded retry counter
```

### Graph assembly

```python
# graph/builder.py
from langgraph.graph import StateGraph, START, END

def build_app():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    g.add_node("coder", coder_node)
    g.add_node("researcher", researcher_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("direct", direct_node)          # supervisor answering personally

    g.add_edge(START, "supervisor")
    # supervisor navigates via Command(goto=...) — no explicit edges FROM it
    g.add_edge("coder", "reviewer")            # specialists get reviewed
    g.add_edge("researcher", "reviewer")
    g.add_edge("reviewer", "supervisor")       # verdict goes back to the boss
    g.add_edge("direct", END)                  # trivial tasks skip review

    return g.compile(checkpointer=checkpointer)
```

Notice how the graph structure *encodes the policy*: specialists → reviewer → supervisor; direct → END. The architecture IS the decision logic.

### FastAPI wiring (with per-user memory)

```python
# api/routes/agents.py
graph = build_app()   # with AsyncPostgresSaver checkpointer in production

@router.post("/chat")
async def chat(req: ChatRequest):
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": req.message}]},
        config={"configurable": {"thread_id": req.thread_id}},  # ← per-conversation memory
    )
    return {"reply": result["messages"][-1].content}
```

The `thread_id` + checkpointer gives you durable, resumable conversations per user — essential for SaaS. For UX, stream with `astream_events`; for safety on risky actions (file deletion, payments), use LangGraph `interrupt` for human-in-the-loop approval.

### Production concerns (the real advanced level)

- **Tracing**: LangSmith (or Langfuse) on day one — you cannot debug multi-agent systems without seeing every hop
- **Evals**: a small test set per agent ("router sends *this* message to *that* agent"; "reviewer catches *this* seeded bug"). Test prompts like code.
- **Model routing**: cheap model for router/reviewer triage, strong model for builders
- **Temperatures**: 0 for router and reviewer (determinism), low for builders

---

## The Universal Framework — Your Transferable Checklist

This is what you asked for: the thing that works for **any** project. Before writing any agent file, answer these 8 questions:

1. **Role** — Can I state its mission in ONE sentence? (If not, split it.)
2. **Inputs** — What exactly does it receive, and typed how?
3. **Outputs** — What exactly does it return, and typed how? (Contract!)
4. **Tools** — What's the MINIMUM toolset? Is each description a contract (what + when + returns)?
5. **Boundaries** — What must it refuse / never touch?
6. **Procedure** — The numbered steps it follows
7. **Stop conditions** — When is it done? When does it give up? Who does it escalate to?
8. **Failure mode** — What happens when it fails: retry, degrade, or report?

And the system-level decisions:

| Symptom                                                             | Add a...                                        |
| ------------------------------------------------------------------- | ----------------------------------------------- |
| Prompt bloated with how-to knowledge                                | **Skill**                                       |
| Need a new action the agent can't do                                | **Tool**                                        |
| Context exploding / different toolsets / different expertise needed | **Sub-agent**                                   |
| Failures are costly                                                 | **Reviewer + bounded retry loop**               |
| Router misrouting simple stuff                                      | **Rule-based pre-filter before the LLM router** |

### The mistakes that will cost you weeks (avoid these)

1. **The god-agent** — one prompt does everything. Split by domain.
2. **Unbounded loops** — no `MAX_RETRIES` → infinite `agent → reviewer → agent` cycles at 3 AM.
3. **Vague reviewer** — "is this good?" always passes. Rubrics or nothing.
4. **Reviewer sees the builder's summary, not the original requirement** — it can then only check "looks reasonable," not "does what was asked."
5. **Dumping full sub-agent transcripts into shared state** — kills the whole point of delegation.
6. **Tool descriptions that say what, not when** — agents misuse tools.
7. **Over-decomposition** — a sub-agent per task instead of per domain.
8. **Testing prompts by vibes** — write 5 eval cases per agent minimum.

---

## Your learning path (do it in this order)

1. **Week 1**: Build ONE agent (coder) with 3 tools. Hand-write the think-act-observe loop once *without* a framework — you'll understand everything after.
2. **Week 2**: Add the supervisor with `RouteDecision` structured routing, including the `direct` route.
3. **Week 3**: Add the reviewer + bounded retry loop. Seed deliberate bugs and verify the reviewer catches them.
4. **Week 4**: Extract skills from your fattest prompt. Add checkpointer + FastAPI streaming.
5. **Ongoing**: Add one sub-agent per real need — never speculatively.

Start with the single-agent version this week — every principle above (contracts, rubrics, bounded loops, context hygiene) already applies to it, and you'll feel each pain point that justifies the next layer.

Want me to go deeper on any single layer — e.g., the full working router prompt, the reviewer rubric for your specific FastAPI/LangGraph stack, or the human-in-the-loop interrupt pattern for your SaaS?
