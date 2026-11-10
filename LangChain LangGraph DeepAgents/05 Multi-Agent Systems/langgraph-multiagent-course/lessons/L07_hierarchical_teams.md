# L07 — Hierarchical Teams: Supervisors of Supervisors

**Module:** M69 (part 1) · **Time:** ~2.5h · **Example:** `examples/ex10_hierarchical.py`

---

## 0. The problem a hierarchy solves

A flat supervisor has a scaling limit, and the limit is **prompt**, not
code.

With 4 specialists, the supervisor's tool list is 4 items — fine.
With 12 specialists, the supervisor's tool list is 12 items, its system
prompt has to describe 12 domains, and its routing accuracy drops. This is
a well-known, measurable effect: as the number of options grows, the
probability that the model picks the *best* one falls.

The hierarchy fixes this by **partitioning the options**:

```
flat supervisor                 hierarchical supervisor
───────────────                 ──────────────────────
supervisor sees 12 options      top supervisor sees 3 options
                                 ├─ content supervisor sees 2
                                 └─ research supervisor sees 2
```

Each router only ever sees its own domain. Routing quality stops degrading
with team size.

**The cost:** one extra hop. Latency and tokens both go up by roughly the
size of one agent.

---

## 1. The modern implementation (it is almost free)

The mid tier is itself a `create_agent`. You wrap it in a tool exactly like
you wrap a leaf worker (L04), and the top tier calls it like any other
tool.

```python
def agent_as_tool(name, description, agent):
    @tool(f"ask_{name}", description=description)
    def ask(task: str) -> str:
        result = agent.invoke({"messages": [HumanMessage(content=task)]})
        return result["messages"][-1].content
    return ask

# --- the mid tier ---
content_mid = create_agent(
    model,
    tools=[ask_writer, ask_reviewer],
    system_prompt="You supervise the content team. Delegate, then summarise.",
    name="content_supervisor",
)

# --- the top tier ---
top = create_agent(
    model,
    tools=[
        agent_as_tool("content_supervisor",  "Delegate ALL writing and reviewing.", content_mid),
        agent_as_tool("research_supervisor", "Delegate ALL research and fact-checking.", research_mid),
    ],
    system_prompt="You are the top supervisor. Pick the right department.",
    name="top_supervisor",
)
```

**That is the whole trick.** The mid tier is just a tool that happens to
contain other agents. No new framework concept, no new API.

Verified in `ex10`:

```
The tree:
  top_supervisor
    +-- content_supervisor  -> ask_writer / ask_reviewer
    +-- research_supervisor -> ask_researcher / ask_fact_checker
```

---

## 2. When to add a tier

Add a hierarchy when:

- **More than ~6 specialists.** Beyond that, partition by domain.
- **The domains are genuinely different** — not "research vs. writing" but
  "billing vs. legal vs. support", where each has its own vocabulary and
  its own escalation path.
- **Different teams own different tiers** — a content team owns the content
  supervisor, a research team owns the research supervisor. The hierarchy
  becomes an org chart.

Do **not** add a tier to "look enterprise". One extra hop for no routing
benefit is pure loss.

---

## 3. The three levels of progress reporting

This is the part hierarchies make genuinely harder, because there are now
three audiences for progress.

### Leaf — writes raw progress into shared state

```python
Command(graph=Command.PARENT, update={"progress": ["researcher done"]})
```

### Mid tier — summarises its leaves' progress into ONE line

```
"Researched 2/2 topics, drafting in progress"
```

### Top tier — shows the user

```
"Researched (2/2), drafting (1/2)..."
```

> **The rule: progress flows UP as summaries, DOWN as tasks.** Never pass
> raw progress lists upward — the top tier does not need to know that
> "researcher finished subsection 3". It needs "research done".

Concretely, the anti-pattern:

```python
# BAD - the top tier receives every raw leaf event
"progress": state["progress"] + ["researcher finished query 1", ...]

# GOOD - the mid tier summarised before passing up
"progress": [f"research team completed {n}/{total} topics"]
```

### Why this matters beyond tidiness

Raw progress lists are **unbounded**. A long-running team's progress list
becomes prompt stuffing at the top tier, and the top tier is the one whose
prompt is already carrying the most options. Summarising at each boundary
is what keeps the hierarchy's context flat.

---

## 4. Failure escalation

In a hierarchy, errors have a **direction**: **upward**.

```
leaf fails  ->  mid tier retries, then summarises the failure
             ->  top tier decides: try another domain? ask a human?
                                   answer with partial results?
```

> **A leaf must never decide to escalate itself.** A leaf that decides to
> escalate has to understand the hierarchy, which breaks its isolation. It
> should just fail, clearly, and let its supervisor handle it.

`ex10` demonstrates the pattern:

```python
def mid_tier(state):
    try:
        result = failing.invoke({"messages": [HumanMessage(content="do it")]})
        return {"artifacts": {"failure": text_of(result["messages"][-1])},
                "status": "running"}
    except Exception as exc:
        # ESCALATION: report upward instead of looping.
        return {"escalation": f"research tier failed: {type(exc).__name__}",
                "status": "escalated",
                "progress": ["research tier escalated"]}

def top_tier(state):
    if state.get("status") == "escalated":
        return {"final_answer": f"Partial answer. Escalation: {state['escalation']}",
                "status": "escalated",
                "progress": ["top tier handled escalation"]}
    return {"final_answer": "ok", "status": "done"}
```

Output:

```
status      : escalated
escalation  : research tier failed: RuntimeError
final_answer: Partial answer. Escalation: research tier failed: RuntimeError
```

### The three escalation levels

| level | what it means | example |
|---|---|---|
| **retry** | transient failure, same work | API 503 → retry with backoff |
| **re-route** | this domain cannot do it, another can | "not a billing question" → support |
| **escalate to human** | nobody can do it | "customer wants a refund of €4,900" |

The **retry** level belongs at the node level (`retry_policy` on the graph
node, L10). The **re-route** level belongs in the mid tier's routing. The
**human** level belongs at the top tier, and it needs a checkpointer +
`interrupt` (Phase 8).

### A rule about partial results

If the team has produced useful work before failing, the top tier should
**return the partial result with a note**, not fail the whole request. Most
users prefer "here is what I found, but X failed" to an error page.

---

## 5. Where the tier boundary should be

The boundary between "mid tier" and "leaf" is a design decision with a
concrete test:

> **Is the mid tier making a decision, or just relaying?**

If the mid tier only passes briefs down and reports up, it is **not** worth
a tier — it is an extra hop for nothing. Make it a leaf or promote it to a
real supervisor.

A mid tier earns its keep when it:
- routes between leaves in its domain,
- summarises leaves' output for the tier above,
- applies domain-specific rules (retry policy, escalation path, PII rules).

---

## 6. The cost of a hierarchy

```
flat supervisor (4 specialists):   supervisor + 1 specialist   = 2 hops
hierarchical (4 specialists):      top + mid + leaf            = 3 hops
```

| | flat | hierarchical |
|---|---|---|
| model calls | 2 | 3 |
| latency | 2L | 3L |
| routing quality at 12 specialists | degrades | stable |

So: **use a hierarchy when routing quality actually matters**, i.e. when
you have many specialists and you can measure the degradation.

---

## 7. Debugging a hierarchy

From L11, but the hierarchy-specific version:

* **Which tier made the bad decision?** The Langfuse tree shows it:
  `top_supervisor → content_supervisor → writer`.
* **Did the mid tier pass the right brief?** Stream `messages` and read
  what the leaf actually received.
* **Is a tier looping?** Count the repeated spans. Add a visit counter at
  each tier boundary (L06).
* **Is a tier silent?** A mid tier that produced no `tools` span and no
  final message is a routing failure, not a model failure.

---

## 8. Run it

```bash
PYTHONPATH=examples .venv/bin/python examples/ex10_hierarchical.py
```

---

## What you should be able to do now

- Explain when a hierarchy beats a flat supervisor, with the cost.
- Build a two-tier team using nothing but `create_agent` and the
  agent-as-tool adapter.
- Implement the three levels of progress reporting, and explain why raw
  progress lists must not flow upward.
- Design an escalation policy (retry / re-route / human) per tier.
- Say which direction failures travel, and why leaves must not escalate.

**Next:** L08 — shared state design at scale: schemas, reducers, artifacts,
and how to stop prompt-stuffing for good.
