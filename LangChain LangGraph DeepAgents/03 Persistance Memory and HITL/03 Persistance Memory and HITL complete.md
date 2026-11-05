Phase 8 — Human-in-the-Loop, Memory, and Multi-Tenant Data
These five lessons fit together well, and I recommend keeping their overall order:
Lesson	Topic	The central question
L18	Human-in-the-Loop: Interrupts	How can a running graph pause and wait for a person?
L19	Production Approval Flows	How do we turn that pause into a secure, auditable business approval process?
L20	Short-Term Memory	How does an agent manage its conversation history and limited context window?
L21	Long-Term Memory	How can an agent remember useful information across separate conversations?
L22	Multi-Tenant Memory and Data Lifecycle	How do we isolate, expire, and delete data safely when many customers use the same system?

The sequence moves from workflow control → business process → conversation context → persistent memory → enterprise data isolation.

A prerequisite for L18 is understanding LangGraph threads, thread_id, and checkpointing. An interrupt does not magically keep a Python process alive: LangGraph saves a checkpoint, pauses the graph, and later resumes it using the same thread and a checkpointer. That distinction is foundational to understanding everything that follows.

I’ll use modern LangGraph/LangChain patterns and explain older approaches separately, rather than mixing legacy examples into the main implementation.

Before L18: three concepts you must understand
These concepts are the foundation of the entire phase.
1. Checkpointer
A checkpointer saves the execution state of a graph.

Suppose you have a conversation:
User: My name is Alex.
Agent: Nice to meet you, Alex.
User: Help me book a flight.
Agent: Where would you like to go?


LangGraph can save the graph's state after execution steps. A checkpointer stores snapshots of that state so execution can be continued later.

Common checkpointer implementations include:
Checkpointer	Purpose
InMemorySaver	Development and testing
PostgresSaver	Persistent production storage in PostgreSQL
AsyncPostgresSaver	Async applications using PostgreSQL
MongoDB checkpointer	Persistent checkpointing using MongoDB

The checkpointer is not your general-purpose memory database. It is primarily responsible for persisting workflow execution state.
2. Thread ID
A thread identifies one ongoing conversation or workflow execution history.
config = {    "configurable": {        "thread_id": "conversation-123"    }}



Consider these two requests:
graph.invoke(    {"messages": [("user", "My name is Alex")]},    config={"configurable": {"thread_id": "thread-1"}},)graph.invoke(    {"messages": [("user", "What is my name?")]},    config={"configurable": {"thread_id": "thread-1"}},)



Because both calls use the same thread, the second execution can access the conversation state saved by the first execution.

Using another thread ID creates another independent execution history.

An important distinction:
- thread_id identifies the conversation/workflow execution history.
- user_id identifies the application user.
- tenant_id identifies the organization or customer.
These identifiers serve different purposes. We will use all three in L22.
3. Checkpointer versus Store
This is probably the most important architectural distinction in the memory lessons.
Checkpointer — thread-specific persistence
Thread A
Checkpointer

Conversation messages, current graph state, pending tasks, execution progress.
Thread B
Checkpointer

A separate conversation and workflow state.

Store — cross-thread persistence
User memory
Store

Preferences, important facts, reusable knowledge, user profile.
Both Thread A and Thread B can access the same appropriately scoped user memory.

For example:
- Thread A: Alex says they prefer Python.
- Thread A ends.
- Thread B: Alex starts a new conversation.
- The agent retrieves Alex's Python preference from the Store.
The checkpointer remembers the conversation's execution state. The Store remembers information that should be available across conversations.

LangGraph deliberately separates these two persistence responsibilities. 

GitHub+1


L18 — Human-in-the-Loop Part 1: Interrupts
0. The mechanism in 30 seconds
Let's first understand why Human-in-the-Loop (HITL) exists.

Imagine you build an AI agent that can:
- Send emails.
- Delete files.
- Execute SQL queries.
- Transfer money.
- Create invoices.
- Modify employee records.
- Make purchases.
- Update customer information in Salesforce.
You don't necessarily want an AI agent to perform every operation automatically.

Consider this request:
User:
Send an email to the entire company announcing
that we are changing our pricing.


Your agent might:
1. Understand the request.
2. Draft an email.
3. Identify the recipients.
4. Decide to call send_email().
5. Execute the email tool.
But sending an email to 2,000 employees is a significant action.

You might want a human to inspect the proposed email before it is actually sent.

This is where HITL comes in.

The desired execution becomes:
User request
     |
     v
AI agent
     |
     v
Prepare email
     |
     v
Request approval
     |
     v
[PAUSE]
     |
     | Human reviews email
     |
     v
Human approves / rejects / edits
     |
     v
[RESUME]
     |
     v
Execute approved action
     |
     v
Return result


The important feature is that the graph does not need to keep running while waiting for the human.

It can stop execution, persist its state, and resume later.

A person might respond after a few seconds, several hours, or even several days.
What actually happens internally?
LangGraph provides the interrupt() primitive.
from langgraph.types import interruptdef approval_node(state):    decision = interrupt(        "Do you approve this operation?"    )    return {        "approved": decision    }



The first time this node executes:
1. LangGraph encounters interrupt().
2. It raises an internal graph interruption signal.
3. Execution stops.
4. The checkpointer saves the graph's state.
5. The interruption information is made available to the caller.
6. The application can show an approval interface to a human.
Later, the application resumes the graph using:
from langgraph.types import Commandgraph.invoke(    Command(resume=True),    config=config,)



The value True is returned by the original interrupt() call.

That means:
decision = interrupt("Do you approve?")



effectively receives:
decision = True



The node can then continue executing.

Important: interrupt() is not an ordinary function that blocks a Python thread waiting for someone to answer. It is a checkpointed workflow-control mechanism. 

Docs by LangChain+1

1. What a paused run looks like
Let's build an actual example.
1.1 The modern shape: version="v2"
First, create a basic graph.
from typing_extensions import TypedDictfrom langgraph.checkpoint.memory import InMemorySaverfrom langgraph.graph import START, END, StateGraphfrom langgraph.types import interruptclass State(TypedDict):    amount: int    approved: booldef request_approval(state: State):    decision = interrupt(        {            "question": "Approve this payment?",            "amount": state["amount"],        }    )    return {"approved": decision}def execute_payment(state: State):    if not state["approved"]:        return {"approved": False}    print(f"Executing payment: {state['amount']}")    return {"approved": True}



Let's execute it:
config = {    "configurable": {        "thread_id": "payment-001"    }}result = graph.invoke(    {        "amount": 5000,        "approved": False,    },    config,    version="v2",)



The graph encounters interrupt() and pauses.

With the v2 result format, you receive a GraphOutput object.

Conceptually:
result.value



Contains the graph's current state.
result.interrupts



Contains the interruptions that occurred.

You can inspect them:
for interruption in result.interrupts:    print(interruption.id)    print(interruption.value)    print(interruption.response_schema)



An Interrupt object contains information about the pending interruption, including:
Attribute	Meaning
id	Unique identifier of the interrupt
value	Payload passed to interrupt()
resumable	Whether the interrupt can be resumed
ns	Execution namespace, useful for nested graph context
when	When the interrupt occurred
response_schema	Optional schema describing the expected human response

Some fields are optional depending on the interruption and API version.

The important distinction is:
- value is the information you want to present to the human.
- id identifies a particular interruption.
- response_schema describes the expected response.
Interrupt is not the same thing as your graph's application state. It is metadata describing a paused execution. 

LangChain Reference+1

1.2 The legacy shape: __interrupt__
Before the v2 result format, applications commonly inspected:
result["__interrupt__"]



For example:
result = graph.invoke(inputs, config)interruptions = result["__interrupt__"]



The old result might look conceptually like this:
{    "amount": 5000,    "approved": False,    "__interrupt__": [        {            "value": {                "question": "Approve this payment?",                "amount": 5000,            },            "id": "abc123"        }    ]}



There are two different migration considerations here.

The __interrupt__ mechanism itself is not simply removed. It remains available through compatibility paths such as the default invoke() result.

However, when using version="v2", prefer:
result.valueresult.interrupts



rather than dictionary-style access to the GraphOutput.

The v2 documentation marks dictionary-style compatibility access as deprecated. 

GitHub+1

1.3 The Interrupt object
Let's understand the difference between the following objects:
interrupt(...)



Interrupt(...)



Command(...)



Object	Responsibility
interrupt()	Pauses execution and requests external input
Interrupt	Represents the interruption that occurred
Command	Controls execution when resuming

A useful mental model:
interrupt()
    |
    | Creates a pending interruption
    v
Interrupt object
    |
    | Sent to application
    v
Human reviews request
    |
    | Human decides
    v
Command(resume=...)
    |
    v
Graph resumes


You generally call interrupt() yourself, inspect the resulting Interrupt, and submit a Command.
1.4 The paused thread from the outside
Something particularly important happens here.

Suppose your FastAPI backend calls the graph:
result = graph.invoke(    inputs,    config,    version="v2",)



The graph reaches an interrupt.

The Python function call finishes by returning the paused result to your application.

It does not sit there waiting for the human.

Your FastAPI endpoint can now return a response:
{
    "status": "approval_required",
    "thread_id": "payment-001",
    "approval": {
        "amount": 5000,
        "question": "Approve this payment?"
    }
}


Your frontend displays an approval screen.

Meanwhile, the saved checkpoint provides the information needed to resume the workflow.

This is why a persistent checkpointer is necessary for production HITL.

InMemorySaver is excellent for learning, but its contents disappear when its process terminates. For production, use a persistent implementation such as AsyncPostgresSaver.

2. Resuming
2.1 Command(resume=...)
This is the central operation for continuing an interrupted graph.
from langgraph.types import Commandgraph.invoke(    Command(resume=True),    config,)



The value passed to resume becomes the return value of the corresponding interrupt() call.

Consider:
def approval_node(state):    approved = interrupt("Approve payment?")    if approved:        return {"status": "approved"}    return {"status": "rejected"}



When the application resumes using:
Command(resume=True)



The execution continues as:
approved = True



When it resumes using:
Command(resume=False)



The execution continues as:
approved = False



You can also pass structured data:
Command(    resume={        "decision": "approved",        "reason": "Verified by finance",        "reviewer_id": "employee-123",    })



This is particularly useful in approval applications.

A security point: the graph must not trust a client-supplied reviewer_id or approval decision. Your backend must authenticate the reviewer, authorize the action, record the decision, and only then resume the graph with trusted data.
2.2 Answer by ID or by order
This becomes important when multiple interruptions occur.

There are two situations.

Situation A: One interrupt

You can simply provide:
Command(resume=True)



Situation B: Multiple interrupts

Imagine a graph launches three parallel tasks:
                 START
                   |
          +--------+--------+
          |        |        |
          v        v        v
       Task A   Task B   Task C
          |        |        |
       Pause    Pause    Pause
          |        |        |
        Human    Human    Human


Each task produces its own interrupt.

Conceptually:
Interrupt(    id="int-a",    value="Approve task A?")Interrupt(    id="int-b",    value="Approve task B?")Interrupt(    id="int-c",    value="Approve task C?")



You need to make sure each answer is delivered to the correct interrupt.

Use the interrupt IDs:
resume_values = {    "int-a": True,    "int-b": False,    "int-c": True,}graph.invoke(    Command(resume=resume_values),    config,)



This is safer than assuming the order of results will always match the order in which your frontend displays its forms.

Important distinction: parallel interrupts can be resumed by ID. For repeated sequential interrupts in the same execution path, their call order must also remain stable across replay. Don't change the order of interrupt() calls while a thread is paused.

The official documentation specifically recommends mapping interrupt IDs to responses for parallel interrupts. 

GitHub+1

2.3 The most important warning: the node restarts from the top
This is one of the most important LangGraph concepts to understand.

Consider:
def approval_node(state):    print("Step 1: Starting")    print("Step 2: Creating database record")    create_database_record()    decision = interrupt(        "Approve this operation?"    )    print("Step 3: Continuing")    return {        "approved": decision    }



What happens?

First execution:
Starting
   |
   v
Create database record
   |
   v
interrupt()
   |
   v
PAUSED


Now a human approves.

What happens when you resume?

LangGraph re-executes the node from its beginning.
Starting
   |
   v
Create database record AGAIN
   |
   v
interrupt()
   |
   v
Returns previously provided human response
   |
   v
Continuing


Notice something important:

create_database_record() executes twice.

This could create duplicate database records.

The reason is that LangGraph checkpoints graph execution at node boundaries, not at every Python statement.

It does not automatically remember which ordinary Python statements inside your node already ran.

The correct approach is to make pre-interrupt side effects idempotent or separate them into other nodes.

Option 1: Make the operation idempotent.
def approval_node(state):    create_record_if_not_exists(        idempotency_key=state["request_id"]    )    approved = interrupt(        "Approve this operation?"    )    return {        "approved": approved    }



Calling the database operation again will not create another record.

Option 2: Put the side effect after the interrupt.
def approval_node(state):    approved = interrupt(        "Approve this operation?"    )    if not approved:        return {"approved": False}    create_database_record()    return {"approved": True}



Now the database operation only executes following approval. You still need idempotency because nodes can also be retried after failures.

Option 3: Separate the workflow into nodes.
START
  |
  v
Create pending request
  |
  v
Request approval
  |
  v
Execute operation
  |
  v
END


This is usually the cleanest approach for important business workflows.

LangGraph's own guidance recommends separating side effects where possible and ensuring that operations before interrupts are idempotent. 

GitHub+1

2.4 Multiple interrupts in one node
You can have more than one interrupt inside a node.
def approval_node(state):    finance_approval = interrupt(        "Does finance approve?"    )    legal_approval = interrupt(        "Does legal approve?"    )    return {        "finance_approved": finance_approval,        "legal_approved": legal_approval,    }



The execution is:
Node starts
    |
    v
Finance interrupt
    |
    v
Pause
    |
    | Resume with finance decision
    v
Legal interrupt
    |
    v
Pause
    |
    | Resume with legal decision
    v
Node completes


The same node is replayed from the top on each resume.

LangGraph matches previously supplied resume values to the corresponding interrupt calls.

This means your interrupt calls must be deterministic.

Do not do this:
def approval_node(state):    if random.choice([True, False]):        first = interrupt("Approve A?")    second = interrupt("Approve B?")



A new execution might follow a different path and mismatch resume values.

Instead, use stable inputs and stable execution order.

For complex approvals, separate nodes are often easier to maintain:
Finance Approval Node
          |
          v
Legal Approval Node
          |
          v
Manager Approval Node


2.5 Structured answers: response_schema
Until now, we have returned simple values:
True



But actual approval applications need structured input.

A human might need to submit:
{
    "decision": "approved",
    "reason": "All documents verified",
    "approved_amount": 5000
}


You can describe the expected response using a Pydantic model.
from typing import Literalfrom pydantic import BaseModel, Fieldfrom langgraph.types import interruptclass ApprovalResponse(BaseModel):    decision: Literal["approved", "rejected"]    reason: str = Field(min_length=3)    approved_amount: int | None = Nonedef approval_node(state):    response = interrupt(        {            "question": "Review this payment",            "amount": state["amount"],        },        response_schema=ApprovalResponse,    )    return {        "decision": response.decision,        "reason": response.reason,        "approved_amount": response.approved_amount,    }



When a human submits the response, LangGraph validates it against the Pydantic schema and returns a validated object.

For example:
graph.invoke(    Command(        resume={            "decision": "approved",            "reason": "Documents verified",            "approved_amount": 5000,        }    ),    config,)



Why is this useful?

Without a schema, the application might receive:
"yes"



Or:
{"approved": True}



Or:
{"decision": "approved"}



Different responses require different validation and handling.

With a schema, you establish a clear contract between your graph and the human-facing application.

An important version requirement: Python interrupt response schemas require langgraph >= 1.2.12 according to the current documentation.

Also note that a JSON Schema dictionary passed directly to response_schema is exposed to the client but does not itself validate the resume value. Use a Pydantic model, TypedDict, or dataclass when you want LangGraph to validate the response. 

LangChain Reference+1


3. Editing state before resuming
Sometimes you want to modify the graph state before continuing.

For example:
Agent prepares a payment
        |
        v
Human reviews payment
        |
        v
Human requests a change
        |
        v
Application modifies graph state
        |
        v
Graph resumes


There is a difference between:
1. Changing the graph's saved state.
2. Returning a value from an interrupt.
The first is done using update_state().

For example:
graph.update_state(    config,    {        "amount": 4500    },)



This creates a state update in the checkpoint history.

Then you can resume:
graph.invoke(    Command(        resume={            "decision": "approved",            "reason": "Revised amount accepted",            "approved_amount": 4500,        }    ),    config,)



Why would you use both?

Suppose your state contains:
{    "amount": 5000,    "currency": "INR",    "approved": False,}



A human asks to reduce the amount to ₹4,500.

You might update the state first and then resume with the structured approval response.

However, do not confuse state editing with approval authorization.

A user should not be able to directly submit:
{
  "approved": true
}


to an endpoint that blindly invokes update_state().

The backend must decide which state fields a particular user is allowed to modify.

Also, consider using as_node with update_state() when you intentionally need to control which node LangGraph treats as the source of the update and therefore the subsequent routing behavior.

For most business workflows, keeping approval data in a dedicated application database and passing the trusted decision through Command(resume=...) is easier to audit.

4. The Functional API works the same way
LangGraph offers two programming styles.

Graph API:
StateGraph(...)



You explicitly define nodes and edges.

Functional API:
@entrypoint@task



You write ordinary Python functions while LangGraph manages persistence, task results, and execution.

The interrupt primitive is shared.

Example:
from langgraph.func import entrypoint, taskfrom langgraph.types import interrupt@taskdef prepare_payment(amount: int) -> dict:    print("Preparing payment")    return {        "amount": amount,        "status": "pending",    }@taskdef execute_payment(amount: int) -> str:    print(f"Executing payment: {amount}")    return "Payment executed"@entrypoint(checkpointer=checkpointer)def payment_workflow(amount: int):    payment = prepare_payment(amount).result()    decision = interrupt(        {            "question": "Approve payment?",            "amount": payment["amount"],



Here, checkpointer represents a previously configured checkpointer.
4.1 The subtle and important difference
This is where you need to pay attention.

In the Graph API, an interrupted node restarts from the beginning when resumed.

The Functional API also replays the entrypoint function from the beginning.

However, completed @task results are retrieved from the checkpointer rather than needlessly recomputed.

Consider:
payment = prepare_payment(amount).result()decision = interrupt("Approve?")result = execute_payment(    payment["amount"]).result()



On resume:
1. The entrypoint starts executing again.
2. prepare_payment() is encountered again.
3. LangGraph restores its previously checkpointed task result.
4. It continues to the interrupt.
5. The saved resume value is supplied.
6. Execution continues to execute_payment().
Therefore, prepare_payment() does not perform its previous completed work again.

This is one of the main benefits of the Functional API.

But there is a crucial condition: side effects and nondeterministic operations should be encapsulated in tasks.

Bad:
@entrypoint(checkpointer=checkpointer)def workflow(inputs):    write_to_file()  # Re-executes on resume.    approved = interrupt("Approve?")    return approved



Better:
@taskdef write_to_file():    # Side effect is persisted as a task result.    ...@entrypoint(checkpointer=checkpointer)def workflow(inputs):    write_to_file().result()    approved = interrupt("Approve?")    return approved



Another important rule: maintain the order of task and interrupt calls across replays. LangGraph uses checkpointed execution history to match prior results and resume values.

This is a different replay model from simply thinking of a Python function as a coroutine that continues from the exact line where it paused. 

GitHub+2


5. Static breakpoints: interrupt_before and interrupt_after
We have discussed dynamic interrupts:
interrupt("Approve this action?")



Now let's understand static breakpoints.

Static breakpoints allow you to pause execution at a predefined node.

Example:
graph = builder.compile(    checkpointer=checkpointer,    interrupt_before=["execute_payment"],)



This tells LangGraph:
Whenever execution is about to enter execute_payment, pause first.

You can also do:
graph = builder.compile(    checkpointer=checkpointer,    interrupt_after=["prepare_payment"],)



This means:
Execute prepare_payment, then pause before the next node.

Conceptually:
interrupt_before
prepare_payment

PAUSE HERE

execute_payment


interrupt_after
prepare_payment

PAUSE HERE

execute_payment


These are particularly useful for debugging.

For example, you may want to inspect the output of every node in a complex graph.

You can step through it with breakpoints.

The important distinction:
Feature	Dynamic interrupt	Static breakpoint
Function	interrupt()	interrupt_before / interrupt_after
Placement	Inside node logic	At predefined nodes
Conditional	Yes	No, at the configured breakpoint
Human approval	Recommended	Not recommended
Debugging	Possible	Primary use

For real HITL approval workflows, use interrupt().

LangGraph explicitly recommends dynamic interrupts rather than static breakpoints for human approval. 

GitHub+1


6. Deprecated: NodeInterrupt
Earlier LangGraph implementations included:
from langgraph.errors import NodeInterruptraise NodeInterrupt(    "Approval required")



This is the old approach.

The modern implementation is:
from langgraph.types import interruptdecision = interrupt(    "Approval required")



What changed?

Previously, developers explicitly raised an interruption exception.

The newer approach provides a dedicated interrupt function with a clearer mechanism for capturing the payload and retrieving the resume value.

You should not manually raise internal graph interruption exceptions either.

Use the public interrupt() API.
6.1 Current versus deprecated
Implementation	Status	Recommendation
interrupt()	Current	Use this
Command(resume=...)	Current	Use this
Interrupt objects	Current	Inspect interrupt metadata
response_schema	Current	Use for typed human responses
NodeInterrupt	Deprecated	Replace with interrupt()
result["__interrupt__"]	Legacy access	Prefer v2 .interrupts when using v2
interrupt_before / interrupt_after	Current	Primarily for debugging

NodeInterrupt has an explicit deprecation marker in the LangGraph source code. 

GitHub+1


7. HITL for agents: HumanInTheLoopMiddleware
So far, we have written our own interrupt logic.

But what happens when you are building an agent with many tools?

Imagine this agent has:
tools = [    search_documents,    read_customer,    update_customer,    send_email,    delete_file,    transfer_money,]



You might want:
Tool	Human approval
search_documents	Not required
read_customer	Not required
update_customer	Required
send_email	Required
delete_file	Required
transfer_money	Required

You could manually add an interrupt inside each tool.

But this produces repetitive code and makes approval policy difficult to maintain.

LangChain offers:
HumanInTheLoopMiddleware



It integrates HITL into the agent's tool-execution lifecycle.
7.1 The two modes
There are two ways middleware can pause an agent.

Mode 1: Batched

The default documented mode.

Suppose an agent generates three tool calls:
Model
  |
  +--> search_documents()
  |
  +--> update_customer()
  |
  +--> send_email()


If the last two tools require approval, batched mode presents those approval requests together in one interruption.

The reviewer responds with an ordered list of decisions.

Mode 2: Per-call

Each gated tool call gets its own interruption.

This is useful when tool executions have different reviewers, approval requirements, or latency.

For new agents, the current documentation recommends considering per-call mode. It also documents per-call as the intended default in a future major release. Its Python implementation requires langchain >= 1.5.18 according to the current guide. 

GitHub+1

7.2 The four decision types
HITL middleware supports four decisions.
Decision	Meaning	Example
approve	Execute the proposed tool call	Send the email as drafted
edit	Modify the tool call and execute the revised call	Change the recipient
reject	Do not execute the tool call	Reject deleting a file
respond	Supply a tool result directly	Human answers an ask_user tool

Let's understand the distinction between reject and respond.

Suppose the agent wants to execute:
transfer_money(    recipient="John",    amount=50000,)



A reviewer rejects it.

The tool should not run.

The model may then reconsider the operation or explain the rejection.

But consider:
ask_user(    question="Which city do you want to visit?")



Here the human is actually providing the answer that the tool was intended to collect.

This is a respond decision.

Do not use respond as a substitute for rejecting a side-effecting tool. A supplied response is treated as a successful tool result. 

GitHub+1

7.3 Worked example
Here is the main implementation pattern.
from langchain.agents import create_agentfrom langchain.agents.middleware import HumanInTheLoopMiddlewarefrom langgraph.checkpoint.memory import InMemorySaver# Example application tools.tools = [    search_documents,    update_customer,    send_email,    delete_file,]agent = create_agent(    model="google_genai:gemini-2.5-flash",    tools=tools,    middleware=[        HumanInTheLoopMiddleware(            interrupt_on={                "search_documents": False,                "update_customer": True,                "send_email": True,                "delete_file": {                    "allowed_decisions": [



The model identifier here is illustrative; select a currently supported Gemini model for your installed langchain-google-genai integration.

In production, replace InMemorySaver with a persistent checkpointer.

When the middleware interrupts, the tool call has not yet been executed. The application receives the review request and presents it to the human.

Once the decision is authorized, the application resumes the agent using Command(resume=...).

Also remember that tool approval is not a substitute for ordinary tool security. Even an approved tool needs its own validation, permission checks, and safe execution logic.
7.4 Finding paused agents from your API
Suppose you have a FastAPI backend:
Frontend
   |
   v
FastAPI
   |
   v
LangChain Agent
   |
   v
LangGraph Checkpointer


Your application needs to know whether the agent paused for approval.

For a version="v2" invocation:
result = agent.invoke(    inputs,    config,    version="v2",)if result.interrupts:    for item in result.interrupts:        print(item.id)        print(item.value)



For the newer event-streaming API, you can use stream_events(..., version="v3") and inspect stream.interrupted and stream.interrupts.

Keep the distinction between a paused agent and a completed agent in your API response.

8. Putting it together: a minimal HITL API
Now let's connect everything.

Imagine an AI-powered expense management application.

An employee requests:
Please reimburse ₹25,000 for my business travel.


The agent checks the policy and prepares a reimbursement action.

The architecture:
                  Frontend
                     |
                     v
                   FastAPI
                     |
             Authenticate user
                     |
                     v
               LangGraph Agent
                     |
              Check expense policy
                     |
                     v
              Prepare reimbursement
                     |
                     v
                 interrupt()
                     |
                     v
           Persist checkpoint in DB
                     |
                     v
             Return approval_required
                     |
                     v
              Manager's frontend
                     |
              Review + approve
                     |
                     v
               FastAPI endpoint
                     |
          Verify manager permission
                     |
                     v
             Record decision
                     |
                     v
             Command(resume=...)
                     |
                     v
              LangGraph Agent
                     |
                     v
             Execute reimbursement


A simplified API structure:
POST /expenses



Creates the request and starts the graph.
GET /approvals



Returns the approvals assigned to the authenticated reviewer.
GET /approvals/{approval_id}



Returns details for an approval.
POST /approvals/{approval_id}/decision



Records the decision and resumes the relevant graph.

Notice that the frontend never needs direct access to the LangGraph checkpointer.

It communicates with your backend. The backend owns authorization, the checkpoint reference, and the resume operation.

This separation becomes extremely important in L19.
9. Common mistakes
Mistake	Why it is a problem	Correct approach
Forgetting a checkpointer	Cannot persist a resumable execution	Compile with a checkpointer
Changing the thread ID	Cannot resume the original thread	Reuse the original ID
Treating interrupt as normal blocking I/O	Misunderstands execution lifecycle	Treat it as a durable pause
Creating duplicate DB records before interrupt	Node replays those operations	Idempotency or separate nodes
Using NodeInterrupt	Deprecated API	Use interrupt()
Using static breakpoints for approvals	Primarily a debugging feature	Use dynamic interrupts
Trusting a frontend approval value	Authorization vulnerability	Verify and authorize server-side
Changing interrupt order during replay	Resume values may be mismatched	Keep execution deterministic

10. Checkpoint yourself
Try answering these before proceeding to L19.
L18 knowledge check
0/5 answered

1. What is the primary job of a LangGraph checkpointer?

Generate embeddings

Persist graph execution state

Call an LLM

Manage tool permissions



2. What does Command(resume=True) do?

Starts a new thread

Returns True from the matching interrupt() call

Updates every graph state field

Deletes the checkpoint



3. What happens to the node containing interrupt() after resume?

It continues from the exact Python line

It restarts from the beginning of the node

It is skipped

It executes in another thread automatically



4. Which mechanism is recommended for real human approvals?

Static interrupt_before

NodeInterrupt

Dynamic interrupt()

print()



5. What does HumanInTheLoopMiddleware control?

Model temperature

Whether selected tool calls require human decisions

Database connection pooling

Conversation summarization


Check answers

L19 — Human-in-the-Loop Part 2: Production Approval Flows
L18 taught us how to pause and resume a graph.

But there is a big difference between:
approved = interrupt("Approve?")



and building an enterprise approval system that handles hundreds or thousands of requests safely.

L19 is about the second problem.
0. From a paused graph to a company approving refunds
Imagine you are building an enterprise AI platform.

An employee asks:
Refund ₹75,000 to customer CUST-123.


The AI agent:
1. Authenticates the request context.
2. Retrieves the customer information.
3. Checks the refund policy.
4. Prepares the proposed refund.
5. Determines that manager approval is required.
6. Pauses the workflow.
A manager subsequently approves the refund.

There are several questions:
- Where is the approval request stored?
- How does the manager find pending requests?
- How do we prevent two managers from approving the same request?
- How do we ensure an unauthorized employee cannot approve it?
- What happens if the application crashes after recording approval but before resuming LangGraph?
- How do we maintain a permanent audit record?
- What happens when nobody responds?
These are application architecture problems, not just LangGraph problems.

The most important architectural decision is:

LangGraph manages workflow execution. Your application database manages business approval records and authorization.

Do not try to use the graph checkpoint as your entire approval management database.
1. Where does the pending state live?
You have two separate persistence requirements.
System 1: LangGraph checkpoint database
Workflow persistence
Stores:
- Current graph state.
- Conversation history.
- Execution progress.
- Pending interrupts.
- Information needed to resume.
  
  System 2: Application PostgreSQL database
  Business persistence
  Stores:
- Approval request ID.
- Requesting employee.
- Tenant and organization.
- Requested action and parameters.
- Assigned reviewers.
- Approval status.
- Deadline.
- Decision and audit information.

Both systems can use PostgreSQL, but they have different responsibilities.

For example, a paused graph might have this checkpoint reference:
thread_id = "thread-abc-123"



Your application database should have an approval record associated with it:
{
    "approval_id": "approval-1001",
    "tenant_id": "company-001",
    "thread_id": "thread-abc-123",
    "requester_id": "employee-123",
    "action": "refund_customer",
    "status": "pending",
    "amount": 75000,
    "currency": "INR"
}


The approval record allows your backend to answer questions such as:
- Show all pending approvals for the finance department.
- Show approvals assigned to this manager.
- Show requests expiring today.
- Show requests submitted by a particular employee.
The checkpointer is not intended to provide all these business queries.
1.1 A production approval schema
A useful starting point:
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY,

    tenant_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    reviewer_id UUID,

    thread_id TEXT NOT NULL,
    interrupt_id TEXT,

    action TEXT NOT NULL,
    action_payload JSONB NOT NULL,

    status TEXT NOT NULL,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,

    decided_at TIMESTAMPTZ,
    decision_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


You would also create an audit table.
CREATE TABLE approval_audit_events (
    id UUID PRIMARY KEY,

    approval_id UUID NOT NULL,
    tenant_id UUID NOT NULL,

    actor_id UUID NOT NULL,
    event_type TEXT NOT NULL,

    previous_status TEXT,
    new_status TEXT,

    event_data JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


Notice that we are storing the original action payload.

This matters because a reviewer must know precisely what they are approving.

For example, approving:
{
    "amount": 75000,
    "customer_id": "CUST-123"
}


is different from approving:
{
    "amount": 175000,
    "customer_id": "CUST-123"
}


The approved operation should be tied to the exact action parameters that were reviewed.

For high-value operations, store a canonical payload hash as well. That helps detect changes between the reviewed action and the action eventually executed.
2. The state machine
An approval system should have an explicit state machine.

Do not rely on arbitrary boolean fields such as:
approved = True



A Boolean cannot represent the full lifecycle.

A better state machine:
PENDING

Waiting for a reviewer


CLAIMED

A reviewer has claimed the decision


APPROVED


REJECTED


EXPIRED



The final decision is terminal. A retry or resume failure should be tracked separately rather than changing the recorded decision.

You might also need additional states:
- RESUME_PENDING: decision recorded, graph resume not yet completed.
- EXECUTING: graph has resumed and is executing the approved action.
- COMPLETED: business operation completed.
- FAILED: business operation failed.
- CANCELLED: the requester cancelled the request before a decision.
Keep approval status separate from workflow execution status.

For example:

An approval may be APPROVED, while the refund is still EXECUTING.

This is a perfectly valid situation.
3. Submitting a request
The workflow should be:
Employee submits refund request
             |
             v
FastAPI validates request
             |
             v
Agent prepares refund operation
             |
             v
LangGraph reaches interrupt
             |
             v
Application creates approval record
             |
             v
API returns approval ID


The client should receive something like:
{
    "status": "approval_required",
    "approval_id": "approval-1001",
    "thread_id": "thread-abc-123",
    "action": "refund_customer"
}


One implementation detail is especially important.

If you need a reliable link between the LangGraph interrupt and your application's approval record, capture the interrupt information on the server and persist its ID along with the thread ID.

Do not make the frontend responsible for maintaining the authoritative checkpoint reference.
4. Deciding — with authorization
Now a manager clicks Approve.

Your endpoint might be:
POST /approvals/approval-1001/decision


Request:
{
    "decision": "approved",
    "reason": "Verified the refund request"
}


The backend has to do much more than call:
graph.invoke(    Command(resume=True),    config,)



4.1 Authorization rules
Before accepting the decision:

Authentication

Who is making the request?

Verify their access token/session and obtain their authenticated identity.

Tenant isolation

Does the approval belong to the same tenant as the authenticated user?

Reviewer authorization

Is this person permitted to approve refunds?

Assignment

Is the reviewer assigned to this approval, or do their role permissions allow them to approve it?

Separation of duties

Is the requester prohibited from approving their own request?

Request validity

Is the request still pending and within its deadline?

Payload integrity

Are the approved action parameters identical to the ones originally reviewed?

These checks must be performed by your application backend, not delegated to the LLM.
4.2 The atomic claim
Consider two managers.

Both open the same pending request.
Manager A                    Manager B
    |                            |
    v                            v
Reads PENDING                Reads PENDING
    |                            |
    v                            v
Clicks APPROVE                Clicks REJECT


Without proper concurrency control, both requests could attempt to decide the same approval.

This creates a race condition.

You need an atomic operation.

One simple PostgreSQL pattern is a conditional update:
UPDATE approval_requests
SET
    status = 'claimed',
    reviewer_id = :reviewer_id,
    updated_at = now()
WHERE
    id = :approval_id
    AND tenant_id = :tenant_id
    AND status = 'pending'
    AND expires_at > now()
RETURNING *;


What happens?
- If one reviewer claims it first, that update succeeds.
- The second reviewer attempts the same update.
- The status is no longer pending.
- The second update returns no row.
Therefore only one reviewer can win the claim.

For a production implementation, use a transaction and a lease on the claim:
PENDING
   |
   v
CLAIMED
   |
   | Reviewer finishes
   v
DECIDED


A lease prevents an approval from becoming permanently stuck when a reviewer claims it and then disappears.
4.3 Audit BEFORE resuming
This is a critical design decision.

Consider the following implementation:
graph.invoke(    Command(resume=True),    config,)save_audit_record()



What happens if the graph successfully resumes and executes the refund, but the application crashes before saving the audit record?

You have performed a financial operation without a corresponding approval audit record.

That is unacceptable.

The order should be:
Authenticate reviewer
       |
       v
Authorize reviewer
       |
       v
Atomically record decision
       |
       v
Persist audit event
       |
       v
Queue graph resume
       |
       v
Resume graph


Ideally, record the decision, immutable audit event, and an outbox message in the same SQL transaction.

For example:
Database transaction
    |
    +-- Update approval status
    |
    +-- Insert audit event
    |
    +-- Insert resume-outbox event
    |
    v
COMMIT


A separate worker reads the outbox and resumes LangGraph.

Why use an outbox?

Because PostgreSQL and LangGraph's checkpoint system do not automatically participate in one distributed ACID transaction.

There is no guarantee that two separate operations will succeed together.

The outbox gives you a recoverable record that graph resumption still needs to happen.

The resume worker must also handle duplicate delivery safely. Give each decision or resume operation a durable idempotency key, and ensure the business operation itself cannot execute twice.
4.4 Verified output
After the graph is resumed:
result = graph.invoke(    Command(        resume={            "decision": "approved",            "reason": "Verified by finance",        }    ),    config,    version="v2",)



The workflow receives the decision and continues.

The backend updates its business execution status based on the result.

Do not mark a refund as completed merely because the graph accepted the resume command.

An approval is not the same as a successful refund.
5. The timeout sweeper
What if the manager never responds?

LangGraph interrupts wait for a response indefinitely unless your application implements a timeout policy.

For example:
Approval created
      |
      v
Expires in 24 hours
      |
      v
No decision received
      |
      v
Mark EXPIRED


This is where a timeout sweeper comes in.

A sweeper is a background process that periodically finds expired approval records.

Example SQL:
SELECT *
FROM approval_requests
WHERE status = 'pending'
  AND expires_at <= now();


But a production sweeper needs concurrency safety.
5.1 The sweeper must be safe to run concurrently
Imagine you run three backend replicas:
API Replica A
API Replica B
Worker Replica C


All three may run the sweeper.

You do not want all three to process the same expired request.

Use row locking or an atomic conditional update.

A common PostgreSQL technique is:
SELECT id
FROM approval_requests
WHERE status = 'pending'
  AND expires_at <= now()
ORDER BY expires_at
FOR UPDATE SKIP LOCKED
LIMIT 100;


Inside the transaction, claim and update the selected rows.

SKIP LOCKED allows concurrent workers to process different rows without waiting on rows already claimed by another worker.
5.2 Where should the sweeper run?
For a production application, use a durable background-processing mechanism.

Examples:
- A dedicated Python worker.
- Celery.
- Dramatiq.
- A database-backed job queue.
- A scheduled Kubernetes job.
- Another reliable scheduler.
Avoid relying on a single FastAPI process's in-memory background task for business-critical timeouts.

A restart could lose that work.
5.3 Should a timeout resume the graph?
This is a design decision.

Option A: Resume with an expired decision.
Command(    resume={        "decision": "expired",        "reason": "Approval deadline exceeded",    })



The graph can then execute its rejection/expiry path and finish cleanly.

Option B: Terminate the workflow.

If your workflow does not need further processing, mark it as expired, cancel it using your application's workflow lifecycle, and clean up its checkpoint according to retention policy.

Option A is usually better when the graph has explicit expiry logic, notifications, or compensating actions.

The most important point: do not leave expired requests indefinitely pending in your application database.
6. API surface
A good initial API design:
Method	Endpoint	Purpose
POST	/requests	Create a business request
GET	/approvals	Retrieve reviewer's pending queue
GET	/approvals/{id}	View an approval
POST	/approvals/{id}/claim	Claim a request, when applicable
POST	/approvals/{id}/decision	Approve or reject
POST	/approvals/{id}/cancel	Cancel an eligible request
GET	/approvals/{id}/status	Inspect workflow status

6.1 The reviewer's queue query
For example:
SELECT *
FROM approval_requests
WHERE tenant_id = :tenant_id
  AND status = 'pending'
  AND reviewer_id = :reviewer_id
ORDER BY requested_at DESC;


In your real authorization model, the reviewer might receive approvals assigned directly to them, approvals assigned to their team, or approvals permitted by their role.

Do not expose all tenant approvals just because someone has a valid login.
7. The audit trail
An approval system should be able to answer:
- Who requested this operation?
- Who approved or rejected it?
- When was it approved?
- What exact operation was approved?
- What were its original parameters?
- Were the parameters modified?
- Why did the reviewer make the decision?
- Did the graph execute successfully?
- Was the action retried?
- Was the operation ultimately completed?
You should distinguish between an approval event and a workflow execution event.

Example:
{
    "approval_id": "approval-1001",
    "event": "APPROVAL_GRANTED",
    "actor": "manager-123",
    "timestamp": "2026-11-02T10:30:00Z"
}


Then separately:
{
    "approval_id": "approval-1001",
    "event": "REFUND_EXECUTED",
    "actor": "refund-service",
    "timestamp": "2026-11-02T10:31:10Z"
}


Use append-only audit events or an appropriately protected audit system.

An ordinary application table that updates and overwrites its previous state is not, by itself, an immutable audit trail.
8. Full lifecycle, end to end
#chatgpt-mermaid-_r_2bl_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_2bl_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_2bl_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_2bl_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_2bl_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_2bl_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_2bl_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_2bl_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_2bl_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_2bl_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_2bl_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_2bl_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_2bl_ p{margin:0;}#chatgpt-mermaid-_r_2bl_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .cluster-label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .cluster-label span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_2bl_ .label text,#chatgpt-mermaid-_r_2bl_ span{fill:rgb(13, 13, 13);color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .node rect,#chatgpt-mermaid-_r_2bl_ .node circle,#chatgpt-mermaid-_r_2bl_ .node ellipse,#chatgpt-mermaid-_r_2bl_ .node polygon,#chatgpt-mermaid-_r_2bl_ .node path{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .rough-node .label text,#chatgpt-mermaid-_r_2bl_ .node .label text,#chatgpt-mermaid-_r_2bl_ .image-shape .label,#chatgpt-mermaid-_r_2bl_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_2bl_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .rough-node .label,#chatgpt-mermaid-_r_2bl_ .node .label,#chatgpt-mermaid-_r_2bl_ .image-shape .label,#chatgpt-mermaid-_r_2bl_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_2bl_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_2bl_ .root .anchor path{fill:rgb(143, 143, 143)!important;stroke-width:0;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_2bl_ .arrowheadPath{fill:rgb(143, 143, 143);}#chatgpt-mermaid-_r_2bl_ .edgePath .path{stroke:rgb(143, 143, 143);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .flowchart-link{stroke:rgb(143, 143, 143);fill:none;}#chatgpt-mermaid-_r_2bl_ .edgeLabel{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_2bl_ .edgeLabel p{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-_r_2bl_ .edgeLabel rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_2bl_ .labelBkg{background-color:rgba(252, 252, 252, 0.5);}#chatgpt-mermaid-_r_2bl_ .cluster rect{fill:rgb(243, 243, 243);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .cluster text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ .cluster span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(243, 243, 243);border:1px solid rgba(0, 0, 0, 0.1);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_2bl_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_2bl_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_2bl_ .icon-shape,#chatgpt-mermaid-_r_2bl_ .image-shape{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_2bl_ .icon-shape p,#chatgpt-mermaid-_r_2bl_ .image-shape p{background-color:rgb(252, 252, 252);padding:2px;}#chatgpt-mermaid-_r_2bl_ .icon-shape .label rect,#chatgpt-mermaid-_r_2bl_ .image-shape .label rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_2bl_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_2bl_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_2bl_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_2bl_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_2bl_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_2bl_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_2bl_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_2bl_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_2bl_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_2bl_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_2bl_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_2bl_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_2bl_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_2bl_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_2bl_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .node rect,#chatgpt-mermaid-_r_2bl_ .node circle,#chatgpt-mermaid-_r_2bl_ .node ellipse,#chatgpt-mermaid-_r_2bl_ .node polygon,#chatgpt-mermaid-_r_2bl_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_2bl_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_2bl_ .mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_2bl_ .edgePaths .flowchart-link{stroke:rgb(143, 143, 143);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_2bl_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_2bl_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Employee requests refundFastAPI validates requestLangGraph evaluates requestPrepare refund actioninterruptSave LangGraph checkpointCreate PENDING approvalrecordManager reviews requestAuthorized decision?Reject API requestAtomic claim and decisionInsert audit and outbox eventCommit database transactionResume LangGraphDecisionExecute refundEnd as rejectedEnd as expiredRecord execution outcomeNoYesApprovedRejectedExpired





9. Production checklist
Before deploying this architecture, verify:
- [ ] Persistent checkpointer is configured.
- [ ] Every thread has an authenticated owner.
- [ ] Approval requests have tenant ownership.
- [ ] Only authorized reviewers can decide.
- [ ] Self-approval rules are enforced.
- [ ] Decisions use atomic database updates.
- [ ] Audit events are written before graph resumption.
- [ ] Outbox processing supports retries.
- [ ] Business tools have idempotency protection.
- [ ] Timeout processing is concurrent-safe.
- [ ] Expired workflows are handled explicitly.
- [ ] Approved operations are tied to immutable reviewed parameters.
- [ ] Application logs do not expose unnecessary sensitive information.
10. Common mistakes
The most dangerous mistakes are using LangGraph checkpoints as your sole approval database, allowing a frontend to submit trusted approval decisions, failing to prevent concurrent decisions, and assuming that a successful resume means that the underlying business operation succeeded.

Remember the architecture:

LangGraph owns execution. PostgreSQL owns the approval lifecycle. FastAPI owns authorization and business access control.

That separation is what makes this suitable for enterprise applications.

L20 — Short-Term Memory
Now we move from workflow control to memory.

Before discussing long-term memory, let's understand how an agent remembers an ongoing conversation.
0. What short-term memory means in LangGraph
Consider this conversation:
User: My name is Alex.

Agent: Nice to meet you, Alex.

User: I am building an AI application.

Agent: What technologies are you using?

User: Python, FastAPI, PostgreSQL and LangGraph.

Agent: Excellent.

User: Which database am I using?


The agent needs the previous conversation to answer correctly.

Where does that conversation live?

In LangGraph, the common implementation is a graph state containing messages.

For example:
from langgraph.graph import MessagesState



MessagesState provides a standard message-history state.

You can build an agent that persists this state using a checkpointer.

Conceptually:
New user message
       |
       v
Update MessagesState
       |
       v
Send messages to LLM
       |
       v
Generate response
       |
       v
Save updated graph state


This is short-term memory.

It is closely associated with the current conversation thread.
Short-term memory versus long-term memory
Short-term memory	Long-term memory
Current conversation context	Information across conversations
Usually associated with a thread	Associated with a user, tenant, or application
Often contains messages	Usually contains selected facts or knowledge
Persisted through checkpointing	Persisted through a LangGraph Store
Can become very large	Should be curated and selective

A common misunderstanding is that storing the complete conversation indefinitely is the same as building good memory.

It is not.

A conversation might contain 100,000 tokens of information, while only 20 important facts should actually be remembered.

You need strategies to control how much context reaches the LLM.

1. The context-window budget
Every LLM has a maximum context capacity.

Suppose your chosen model supports a context window of 200,000 tokens.

It does not mean you should necessarily send 200,000 tokens on every call.

The input contains several things:
System prompt
      +
Conversation messages
      +
Tool definitions
      +
Tool results
      +
Retrieved documents
      +
Memory
      +
Other instructions


And the model also needs room for its output.

The actual budget is approximately:
\[
T_{\text{input}} + T_{\text{output}} \leq T_{\text{model limit}}
\]

For an illustrative 200,000-token context window:
Component	Tokens
System instructions	5,000
Tool descriptions	10,000
Conversation	70,000
Retrieved documents	50,000
Memory	5,000
Other overhead	5,000
Reserved output	10,000
Total	155,000

You still have some room, but it is not unlimited.

Also, larger context does not automatically mean better answers.

Too much irrelevant information can make it harder for the model to locate the information that matters.

This is why short-term memory management is important.
2. Technique 1: trim_messages (manual)
The first method is to trim conversation history manually.

LangChain Core provides:
from langchain_core.messages import trim_messages



Consider an existing conversation:
messages = [    ("system", "You are a helpful assistant."),    ("human", "My name is Alex."),    ("ai", "Nice to meet you."),    ("human", "Explain Python."),    ("ai", "Python is a programming language."),    ("human", "Explain PostgreSQL."),    ("ai", "PostgreSQL is a database."),    ("human", "What is LangGraph?"),]



Suppose you only want to send the most recent messages within a particular token budget.

You can use:
trimmed_messages = trim_messages(    messages,    max_tokens=2000,    token_counter=model,    strategy="last",    include_system=True,    allow_partial=False,    start_on="human",)



Let's understand the parameters.
Parameter	Purpose
messages	Original history
max_tokens	Maximum target budget
token_counter	Determines token usage
strategy="last"	Preserves recent conversation
include_system=True	Retains system instructions
allow_partial=False	Avoids splitting messages
start_on="human"	Starts the retained sequence with a human message

The model argument should be a chat model with an appropriate token-counting capability. For models without one, provide a compatible custom token counter.
Why strategy="last"?
Consider this history:
Message 1: User introduces themselves.
Message 2: Assistant responds.
Message 3: User asks about Python.
Message 4: Assistant explains Python.
Message 5: User asks about databases.
Message 6: Assistant explains databases.
Message 7: User asks about LangGraph.


If you preserve the latest messages, you retain the most recent context.

But you lose older information, including the user's name.

This shows why simple trimming can cause information loss.

That is one reason we eventually need summarization and long-term memory.
When is manual trimming useful?
Use it when:
- You want full control over which messages are included.
- You are building a custom graph.
- You have a specific context budget.
- You want to implement custom retention rules.
- You want predictable behavior.
The drawback is that you must decide when and how to trim the history.

3. Technique 2: ContextEditingMiddleware
Now imagine you build an agent that frequently calls tools.

For example:
User
 |
 v
Agent
 |
 +--> Search web
 |
 +--> Search database
 |
 +--> Retrieve documents
 |
 +--> Execute SQL
 |
 +--> Generate report


Every tool can return a large result.

A web search tool might return 20,000 tokens.

A document retrieval tool might return another 30,000 tokens.

If you keep every previous result, the conversation context grows rapidly.

Would you really need the original output of every tool forever?

Usually not.

You might need to remember that a search happened and that it returned useful information, without sending the entire original result to the LLM again.

This is the problem solved by ContextEditingMiddleware.
3.1 What it does, exactly
Modern import:
from langchain.agents.middleware import (    ContextEditingMiddleware,    ClearToolUsesEdit,)



The middleware can clear older tool results when the input context becomes too large.

Example:
agent = create_agent(    model=model,    tools=tools,    middleware=[        ContextEditingMiddleware(            edits=[                ClearToolUsesEdit(                    trigger=4000,                    keep=3,                    exclude_tools=["important_database_query"],                )            ],            token_count_method="approximate",        )    ],)



Conceptually:

Before editing:
User: Find information about LangGraph.

AI: I will search.

Tool result:
[20,000 tokens of search results]

AI: Here is the explanation.

User: Now compare it with LangChain.

AI: I will search again.

Tool result:
[15,000 tokens of additional search results]

AI: Here is the comparison.


Eventually, the earlier tool responses might no longer be useful.

After context editing:
User: Find information about LangGraph.

AI: I will search.

Tool result:
[Older result cleared]

AI: Here is the explanation.

User: Now compare it with LangChain.

AI: I will search again.

Tool result:
[Recent result preserved]

AI: Here is the comparison.


The middleware reduces the amount of historical tool output sent into future model requests.
3.2 Very important: it edits the request, not the state
This is an important distinction.

Suppose your persistent conversation state contains:
messages = [    HumanMessage(content="Search for LangGraph"),    AIMessage(content="I will search"),    ToolMessage(        content="A very large search result",        tool_call_id="call-123",    ),]



Context editing changes the messages supplied to a particular model request.

It does not simply delete the original conversation record from your checkpointer.

Conceptually:
Persistent graph state
          |
          v
Model request preparation
          |
          v
Count tokens
          |
          v
Too large?
          |
     Yes  |
          v
Edit request messages
          |
          v
Send reduced request to LLM


This is extremely useful because:
- You preserve execution history.
- You reduce the model's input size.
- You do not have to permanently destroy the original tool results.
- You can still access the original persisted state when required.
Remember the distinction:

Context editing is not equivalent to deleting historical data.

The middleware alters the model request context. 

LangChain Reference+1

3.3 token_count_method
Current documented choices include:
Value	Meaning
"approximate"	Estimate token usage
"model"	Use the model's token-counting capability when supported

Example:
ContextEditingMiddleware(    edits=[        ClearToolUsesEdit(            trigger=4000,            keep=3,        )    ],    token_count_method="approximate",)



Approximate counting is convenient and generally cheaper.

Model-based counting can be more accurate when the configured model supports it.

However, remember that input size may include provider-specific overhead and multimodal content.
3.4 exclude_tools
Suppose you have three tools:
tools = [    search_web,    search_documents,    retrieve_customer_contract,]



You might want to clear old web searches but preserve customer contract results.

Use:
ContextEditingMiddleware(    edits=[        ClearToolUsesEdit(            trigger=4000,            keep=3,            exclude_tools=[                "retrieve_customer_contract"            ],        )    ],)



The important detail is that exclude_tools belongs to ClearToolUsesEdit, not the outer middleware constructor.

It specifies which tool outputs should not be cleared.

You can also use clear_tool_inputs to control whether the original tool-call parameters are removed along with the tool result.

The current ClearToolUsesEdit API exposes trigger, clear_at_least, keep, clear_tool_inputs, exclude_tools, and placeholder. 

LangChain Reference+1


4. Technique 3: SummarizationMiddleware
Now we reach a very important technique.

Consider a conversation that has been going on for several days.

It contains:
- The user's identity.
- Technical preferences.
- Several projects.
- Many questions and answers.
- Tool results.
- Multiple decisions.
- Changes to earlier requirements.
Trimming simply removes older information.

Context editing primarily reduces bulky tool outputs.

But summarization tries to preserve the important information in a much smaller representation.

This is the purpose of SummarizationMiddleware.
4.1 How it works
Modern import:
from langchain.agents.middleware import (    SummarizationMiddleware,)



Example:
agent = create_agent(    model=model,    tools=tools,    middleware=[        SummarizationMiddleware(            model=summarization_model,            trigger=("tokens", 8000),            keep=("messages", 20),        )    ],)



The model parameter is the model used for summarization.

The middleware monitors the conversation context.

When the configured trigger is reached:
1. It identifies older messages.
2. It preserves the recent messages specified by keep.
3. It summarizes the older conversation.
4. It replaces the old history in the working conversation context with a summary.
5. It continues with the reduced message history.
Example:

Original conversation:
User: I am developing an AI application.
Assistant: What technology are you using?

User: Python and FastAPI.
Assistant: What database?

User: PostgreSQL.

User: I am also using LangGraph.
Assistant: What type of application?

User: Multi-tenant enterprise AI platform.

User: I prefer open-source solutions.
Assistant: Understood.


A generated summary might become:
Conversation summary:

The user is developing a multi-tenant enterprise AI
platform using Python, FastAPI, PostgreSQL and LangGraph.

The user prefers open-source technologies.


The model does not need to receive all the original messages to retain the essential context.
4.2 The trigger
You can configure the middleware to trigger based on token count:
SummarizationMiddleware(    model=summary_model,    trigger=("tokens", 8000),    keep=("messages", 20),)



This means summarization happens when the context reaches the configured threshold.

Other possible triggers:
trigger=("messages", 30)



Trigger based on message count.

Or:
trigger=[    ("tokens", 8000),    ("messages", 30),]



This uses OR logic: either threshold can trigger summarization.

For combined AND logic:
trigger={    "tokens": 8000,    "messages": 30,}



Both conditions must be met.
4.3 The fractional trigger and model profile
You can also configure fractional thresholds.
SummarizationMiddleware(    model=summary_model,    trigger=("fraction", 0.8),    keep=("fraction", 0.3),)



Conceptually:
- Start summarizing when approximately 80% of the context capacity is consumed.
- Preserve approximately 30% of the context capacity after summarization.
But there is an important requirement.

Fractional limits require the model's maximum input size to be known.

The model profile needs to provide information such as:
profile={    "max_input_tokens": 200000}



The actual value must match the model you are using.

If the model doesn't have the necessary profile information, the fractional configuration can fail.

For that reason, absolute token limits are often easier to configure predictably.
4.4 Which model should summarize?
The summarization model does not have to be the same as the main agent model.

For example:
Main agent:
Gemini model with stronger reasoning capabilities

Summarization:
Smaller, faster Gemini model


This can reduce latency and cost.

Because you prefer Gemini through the LangChain ecosystem, you can initialize the models with the Google GenAI integration:
from langchain.chat_models import init_chat_modelmain_model = init_chat_model(    "google_genai:<supported-gemini-model>")summary_model = init_chat_model(    "google_genai:<supported-faster-gemini-model>")



Choose model IDs supported by your installed integration rather than hardcoding an old model generation.
4.5 The default summary prompt
The middleware has a default summary-generation prompt.

You can also provide a custom summary prompt to control what information should be preserved.

For an enterprise assistant, you might prioritize:
Preserve:

1. User preferences.
2. Project requirements.
3. Important decisions.
4. Current task progress.
5. Unresolved questions.
6. Constraints and limitations.

Avoid:

1. Repetitive explanations.
2. Irrelevant historical tool results.
3. Temporary information that has expired.
4. Speculative assumptions.


Why is this important?

A summary is not a perfect copy of the conversation.

It is a compressed interpretation.

If your summarization instructions are poor, the system could accidentally lose critical information.

For example:
Original:
The user wants PostgreSQL, but only if it can be
self-hosted and used with an open-source license.

Bad summary:
The user wants PostgreSQL.


The summary lost the constraint.

A good summary must preserve important qualifications, not merely keywords.

The current middleware supports custom summary prompts and different trigger/keep configurations. 

LangChain Reference+2


5. Choosing a technique
Let's compare the three approaches.
Technique	What it does	Main advantage	Limitation
trim_messages	Removes messages	Full control	Historical detail can disappear
ContextEditingMiddleware	Clears old tool outputs in model requests	Reduces bulky tool context	Does not summarize knowledge
SummarizationMiddleware	Compresses older messages	Preserves important context	Summary can lose details

5.1 You can combine them
These techniques are complementary.

For example:
agent = create_agent(    model=main_model,    tools=tools,    middleware=[        ContextEditingMiddleware(            edits=[                ClearToolUsesEdit(                    trigger=4000,                    keep=3,                    exclude_tools=[                        "retrieve_critical_contract"                    ],                )            ],        ),        SummarizationMiddleware(            model=summary_model,            trigger=("tokens", 12000),            keep=("messages", 20),        ),    ],)



This gives you two levels of context management:
1. Clear old, bulky tool results.
2. Summarize older conversation history when context still gets too large.
The execution order of your middleware is important. Test the combination with representative tool-heavy conversations and inspect the resulting model requests.

Don't assume adding more middleware automatically improves an agent.

6. Manual budgeting: the low-level version
For an advanced implementation, you should understand context budgeting yourself.

A useful approach:
MAX_CONTEXT = 200_000RESERVED_OUTPUT = 10_000SYSTEM_BUDGET = 5_000TOOLS_BUDGET = 10_000MEMORY_BUDGET = 5_000RETRIEVAL_BUDGET = 20_000CONVERSATION_BUDGET = (    MAX_CONTEXT    - RESERVED_OUTPUT    - SYSTEM_BUDGET    - TOOLS_BUDGET    - MEMORY_BUDGET    - RETRIEVAL_BUDGET)



This is an illustrative budget, not an actual model-specific limit.

Your application can calculate token usage before constructing the final model request.

Why do this?

Suppose your system receives:
- A large retrieved document.
- A large conversation history.
- Several tool outputs.
- Long system instructions.
You may want to prioritize:
1. System and security instructions.
2. Current user request.
3. Necessary recent conversation.
4. Relevant memory.
5. Relevant retrieved documents.
6. Optional historical details.
Never blindly truncate the beginning of a prompt. Important instructions may be there.

Also account for provider-specific constraints, structured output, images, audio, and other multimodal inputs.
7. What short-term memory is NOT
This is important for L21.

Short-term memory does not automatically mean:
- Permanent user memory.
- Semantic retrieval.
- A knowledge base.
- A vector database.
- User profile storage.
- A complete record of every interaction.
A checkpointer persists graph state.

A short-term memory strategy manages which parts of that state are useful to supply to the model.

This difference is fundamental.
8. Common mistakes
Mistake	Better approach
Sending the entire conversation indefinitely	Budget context
Trimming without protecting system messages	Preserve required instructions
Clearing all tool results	Exclude critical tool outputs
Assuming summaries preserve every detail	Preserve important structured data separately
Using a fractional trigger without a model profile	Provide a profile or use absolute token limits
Treating context editing as database deletion	Understand its request-level behavior
Using only summarization for every problem	Combine context management methods appropriately


L21 — Long-Term Memory: Store and LangMem
This is one of the most important lessons for building genuine AI assistants.

Short-term memory allows an agent to understand the current conversation.

Long-term memory allows an agent to remember useful information across separate conversations.
0. Two persistence systems, two questions
Let's revisit our earlier example.

Conversation A:
User:
I prefer Python over JavaScript.

Agent:
Understood.


Conversation B, a few days later:
User:
Which programming language should I use
for the new backend?


The agent should ideally remember the user's preference.

But what if Conversation B has a completely different thread_id?

A checkpointer alone won't solve this.

You need a shared, persistent memory mechanism.

This is the role of the LangGraph Store.
The architecture
                    USER
                      |
                +-----+-----+
                |           |
                v           v
             Thread A    Thread B
                |           |
                v           v
           Checkpointer Checkpointer
                |           |
                |           |
                +-----+-----+
                      |
                      v
                 Long-term
                   Store
                      |
                      v
              User's memories


Each thread has its own graph execution history, but both can access the same authorized long-term memory namespace.

GitHub+1
1. The Store API
LangGraph offers a generic storage interface:
from langgraph.store.base import BaseStore



The Store is a key-value persistence system.

It also supports semantic search when indexing and embeddings are configured.

Think of it as:
Namespace
   |
   +--> Item 1
   |
   +--> Item 2
   |
   +--> Item 3


1.1 Namespaces are tuples of strings
A namespace is how you organize stored information.

Example:
namespace = (    "memories",    "tenant-001",    "user-123",)



This says:
memories
   |
   +-- tenant-001
          |
          +-- user-123


Another valid example:
namespace = (    "users",    "user-123",    "preferences",)



Why a tuple?

It provides hierarchical organization and makes prefix searches possible.

For example:
store.search(    ("memories", "tenant-001"))



Can search under that namespace prefix, depending on the store implementation.

The order of elements matters.

We will study the security implications in L22.
1.2 Items
An item is an individual record inside a namespace.

Example:
store.put(    namespace,    "preference-001",    {        "category": "programming",        "value": "Prefers Python",    },)



Conceptually, the item contains:
Field	Meaning
Namespace	Where the item belongs
Key	Unique item identifier within that namespace
Value	Stored JSON-compatible mapping
created_at	Creation time
updated_at	Last update time

You can retrieve it:
item = store.get(    namespace,    "preference-001",)print(item.value)



Update it:
store.put(    namespace,    "preference-001",    {        "category": "programming",        "value": "Prefers Python and Go",    },)



Delete it:
store.delete(    namespace,    "preference-001",)



Search it:
results = store.search(    namespace,)



And perform semantic search if indexing is enabled:
results = store.search(    namespace,    query="What programming language does the user prefer?",)



This is a major distinction.

A normal key lookup retrieves an item by identifier.

A semantic search finds items related to a natural-language query.
1.3 Using the Store from inside a node
The modern recommended approach is to use the Runtime object.

For example:
from dataclasses import dataclassfrom langgraph.graph import StateGraphfrom langgraph.runtime import Runtimefrom langgraph.store.memory import InMemoryStore@dataclassclass Context:    user_id: strstore = InMemoryStore()def remember_preference(    state,    runtime: Runtime[Context],):    user_id = runtime.context.user_id    namespace = (        "memories",        user_id,    )    runtime.store.put(        namespace,        "programming-language",        {            "value": "Python",        },



The important part:
runtime.context.user_id



Provides the trusted runtime context.

And:
runtime.store



Provides access to the configured Store.

The modern Runtime-based access pattern is preferable to building your own global storage object or passing storage dependencies around manually.

For async applications, use the corresponding asynchronous methods:
await runtime.store.aput(...)



1.4 batch()
Suppose you want to create 100 memory records.

You could make 100 independent store calls.

That can create unnecessary network and database overhead.

The Store API supports batch operations.

Conceptually:
100 operations
      |
      v
One batch request
      |
      v
Store processes operations
      |
      v
Results returned


This is useful for:
- Bulk memory insertion.
- Deleting multiple memories.
- Fetching multiple records.
- Updating records during migrations.
- Data lifecycle operations.
The API uses typed operation objects for batch operations. Consult the installed version's BaseStore API for the exact operation constructors and sync/async methods.

2. PostgresStore — production
InMemoryStore is convenient, but there is a problem.

What happens if the Python process restarts?

All in-memory data disappears.

For production, you need persistent storage.

One natural choice for your architecture is PostgreSQL.

LangGraph provides:
PostgresStore



and:
AsyncPostgresStore



Why PostgreSQL?
It gives you:
- Durable records.
- Transactions.
- Structured metadata.
- Indexes.
- Concurrent access.
- Integration with existing enterprise databases.
- Vector search through pgvector.
2.1 Requirements
Install the appropriate packages:
uv add langgraph langgraph-checkpoint-postgres
uv add "psycopg[binary,pool]"


Also ensure your PostgreSQL instance has the vector extension available if you intend to use semantic search.
Async setup example
from langgraph.store.postgres.aio import AsyncPostgresStoreDATABASE_URL = (    "postgresql://user:password"    "@localhost:5432/ai_database")async with AsyncPostgresStore.from_conn_string(    DATABASE_URL,) as store:    # Run migrations / create required tables.    await store.setup()    await store.aput(        ("memories", "user-123"),        "memory-001",        {            "text": "User prefers Python.",        },    )    result = await store.asearch(        ("memories", "user-123"),        query="Programming language preference",    )    print(result)



2.2 The tables
The PostgresStore manages its own persistence schema.

You do not need to manually create its internal tables.

Call:
await store.setup()



before using a new production store.

This runs the required database setup and migrations.

Think of the storage model as:
PostgreSQL
    |
    +-- Store items
    |      |
    |      +-- namespace
    |      +-- key
    |      +-- value
    |      +-- created_at
    |      +-- updated_at
    |
    +-- Vector indexing data
           |
           +-- Embeddings
           +-- Similarity search


The actual internal schema is implementation-managed and should not be treated as a schema your application owns.
2.3 Semantic search
This is particularly important for AI memory.

Suppose you save:
{    "text": "The user prefers Python for backend development."}



Later, the user asks:
Which programming language do I usually prefer?


The wording is different.

A traditional database query might look for an exact text match.

Semantic search converts information into vector representations and retrieves information based on similarity in meaning.

Conceptually:
Memory text
    |
    v
Embedding model
    |
    v
Vector
    |
    v
Store vector representation


Then:
User query
    |
    v
Embedding model
    |
    v
Query vector
    |
    v
Similarity search
    |
    v
Relevant memories


The Store uses an indexing configuration to enable vector search.

For example:
store = AsyncPostgresStore.from_conn_string(    DATABASE_URL,    index={        "embed": embedding_model,        "dims": EMBEDDING_DIMENSIONS,        "fields": ["text"],    },)



The example illustrates the indexing configuration; use the appropriate async construction context and configured dimensions in your actual implementation.

The fields parameter tells the store which fields should be embedded.

This is useful because you might have:
{    "text": "Prefers Python",    "source": "explicit_user_statement",    "category": "technical_preference",    "created_at": "2026-11-02",}



You may want to embed only text, rather than the entire serialized record.

One important warning:

Semantic search is not automatically enabled simply because you use PostgreSQL.

You must configure indexing and the required embedding model and database extension. 

LangChain Reference+1

2.4 Metadata filtering
Semantic similarity alone is not enough.

Suppose a tenant has:
User A: Prefers Python.
User B: Prefers Java.
User C: Prefers Go.


You do not want a query from User A to retrieve User B's preferences.

You need both:
1. Namespace isolation.
2. Appropriate metadata filtering.
For example, store structured information:
{    "text": "Prefers Python",    "category": "programming",    "source": "explicit",    "tenant_id": "tenant-001",}



And apply the relevant filters when searching.

Namespace isolation should be the primary boundary, with metadata filters providing additional selection.

Metadata filtering does not replace authorization.
2.5 The production embedding model
You requested Gemini as your preferred LLM ecosystem.

You can use Gemini for the memory extraction and reasoning operations and a supported Google embedding model for vector generation.

The important point is that the model used for semantic search must produce vectors with dimensions matching the Store's configured index.

Don't confuse:
- Chat model: generates language and reasons about memories.
- Embedding model: transforms text into vectors.
- Vector database: stores/searches those vectors.
They are three distinct responsibilities.

3. LangMem — automatic memory
Now we reach LangMem.

LangGraph gives you the persistence infrastructure.

But how does an agent decide what should be remembered?

Consider:
User:
I prefer concise answers and Python examples.


You don't necessarily want to save the entire conversation as a memory.

You want the system to extract something useful:
{
    "category": "response_preference",
    "preference": "Prefers concise answers and Python examples"
}


This requires memory extraction, consolidation, and updating.

This is where LangMem helps.

LangMem provides memory-management components that work with LangGraph's Store.

Official project: LangMem documentation.
3.1 Approach A — Tool-based (explicit)
The first approach gives the agent memory-management tools.

The important tools include:
from langmem import (    create_manage_memory_tool,    create_search_memory_tool,)



The agent can use them to:
- Create memories.
- Update memories.
- Delete memories.
- Search existing memories.
Conceptually:
User says something important
             |
             v
Agent understands statement
             |
             v
Agent decides to save it
             |
             v
manage_memory tool
             |
             v
LangGraph Store


Example:
from langchain.agents import create_agentfrom langchain.chat_models import init_chat_modelfrom langgraph.store.memory import InMemoryStorefrom langmem import (    create_manage_memory_tool,    create_search_memory_tool,)model = init_chat_model(    "google_genai:<supported-gemini-model>")store = InMemoryStore()tools = [    create_manage_memory_tool(        namespace=("memories", "{langgraph_user_id}"),    ),    create_search_memory_tool(        namespace=("memories", "{langgraph_user_id}"),    ),]agent = create_agent(    model=model,    tools=tools,



The user says:
Remember that I prefer Python.


The agent can call manage_memory.

Later:
Which language do I prefer?


The agent can call search_memory to retrieve the information.

The important feature is that memory becomes an explicit tool capability.

The LLM decides when to use it, subject to the instructions and tool permissions.
3.2 Approach B — Manager-based (automatic)
Instead of asking the active agent to manage memory through explicit tool calls, you can use a memory manager.

The key API is:
from langmem import create_memory_store_manager



Unlike the tool-based approach, this component is designed to automatically:
1. Search for relevant existing memories.
2. Analyze conversation messages.
3. Extract new information.
4. Update memories when required.
5. Maintain a versioned history of changes.
Example:
from langmem import create_memory_store_managermanager = create_memory_store_manager(    model=model,    namespace=(        "memories",        "{langgraph_user_id}",    ),)



Then invoke it with conversation data:
await manager.ainvoke(    {        "messages": [            {                "role": "user",                "content": "I prefer Python.",            },            {                "role": "assistant",                "content": "I'll take that into account.",            },        ]    },    config=config,)



The manager uses the configured Store.

You can also customize the memory schemas using Pydantic models.

For example:
from pydantic import BaseModelclass PreferenceMemory(BaseModel):    category: str    preference: str    context: str



Then:
manager = create_memory_store_manager(    model=model,    schemas=[PreferenceMemory],    namespace=(        "memories",        "{langgraph_user_id}",    ),)



This creates a much more structured memory system.

The documentation also offers create_memory_manager, which is a related but different API: it produces a list of extracted memory objects (ExtractedMemory) rather than being the Store-integrated manager. You can use it when you want to control how extracted results are persisted yourself.

That distinction is important because the two APIs do not return the same kind of output. 

LangChain+1

3.3 The two APIs use different value shapes
Let's summarize.
API	Input	Output / effect
create_manage_memory_tool	Tool arguments such as content, ID and action	Creates a memory-management tool
create_search_memory_tool	Search query	Creates a memory-search tool
create_memory_manager	Messages and optionally existing memories	Extracted memory objects
create_memory_store_manager	Messages and runtime configuration	Searches and manages stored memories

Don't assume that the output from create_memory_manager is an ordinary LangGraph Store Item.

An extracted memory is a memory-management result. A Store item is a persisted storage record.

They represent different stages of the memory lifecycle.
3.4 The manager's tool contract
A memory-management tool generally operates around the following concepts:
manage_memory(    content=...,    id=...,    action="create",)



Possible actions:
"create""update""delete"



For example:
manage_memory(    content="User prefers Python",    action="create",)



To update an existing record, the operation needs the appropriate memory identifier.

This is important because memory management should not repeatedly create duplicates when a fact has already been recorded.
3.5 Hot path versus background
This is one of the most important architectural decisions.

Hot path

Memory operations happen during the active agent execution.
User message
    |
    v
Agent
    |
    v
Search memory
    |
    v
Use memory for response
    |
    v
Possibly update memory
    |
    v
Respond


Advantages:
- Memory is immediately available.
- The agent can explicitly retrieve and update facts.
- You can make memory use part of the agent's decision process.
Disadvantages:
- Additional tool calls.
- More latency.
- More model interactions.
- More opportunities for memory-tool failures.
Background path

The agent answers the user first, and memory extraction runs separately.
User message
     |
     v
Agent responds
     |
     +----------------------+
     |                      |
     v                      v
Return answer        Schedule memory update
                            |
                            v
                      Memory manager
                            |
                            v
                         Store


Advantages:
- Lower conversational latency.
- Memory extraction can be performed independently.
- Memory consolidation can be more thorough.
Disadvantages:
- The memory may not be available immediately.
- Background execution must be durable.
- Retries and failures must be handled.
For production, do not rely on an untracked asyncio.create_task() for important memory writes.

Use a durable background worker or job queue.

LangMem also provides ReflectionExecutor for scheduling memory enrichment outside the main interaction path. 

LangChain+1


4. Memory design
Having a database full of extracted text does not automatically create good memory.

You must decide what information is actually useful.
4.1 Three kinds of memory
A useful conceptual classification is:

1. Semantic memory

Facts and knowledge.

Examples:
User works with Python.
User uses PostgreSQL.
Company's backend uses FastAPI.


2. Episodic memory

Information about specific past events.

Examples:
On November 1, the user approved a deployment.

Last week, the user requested a database migration review.


3. Procedural memory

Information about how tasks should be performed.

Examples:
Always produce Python examples.

Prefer open-source frameworks.

Use Pydantic for API validation.

Follow the organization's coding standards.


These categories help you design separate schemas and retrieval strategies.

For an enterprise agent platform, procedural memory is especially useful because it helps maintain consistent behavior.
4.2 What to store versus what to re-derive
Not every fact should be stored.

Suppose the user asks:
What is the current time?


There is no reason to remember the answer.

The time changes.

You should retrieve it when needed.

But:
I prefer PostgreSQL over MongoDB.


is potentially useful across many future conversations.

A practical rule:
Information	Store?
Stable preferences	Yes
Project architecture	Yes
Important decisions	Yes
User instructions to remember something	Yes
Current weather	Usually no
Current exchange rate	No
One-time calculations	Usually no
Temporary access token	No
Passwords or secrets	Never use memory for this
Large documents	Store in a proper document/RAG system

4.3 Conflicting memories
What happens when the user changes their preference?

First:
I prefer Python.


Later:
Actually, I want to use Go for the new backend.


Your memory system should not blindly retain both as equally valid preferences.

There are several possible strategies:
- Update an existing memory.
- Store a newer preference with a timestamp.
- Keep historical records while marking the latest record as current.
- Ask for clarification when the scope of a change is ambiguous.
A useful structured schema:
class UserPreference(BaseModel):    category: str    value: str    scope: str    source: str    updated_at: str    confidence: float



Notice the scope field.

The user may prefer Python for data engineering but Go for a particular microservice.

Those preferences do not necessarily conflict.
4.4 Memory hygiene
Good memory systems should be selective.

For every memory, consider:
- Is it accurate?
- Is it still relevant?
- Is it useful?
- Where did it originate?
- Is it user-confirmed?
- Could it be sensitive?
- Does it need an expiration date?
- Can the user inspect or delete it?
Also, remember that an LLM-extracted memory is not automatically a verified fact.

For enterprise systems, preserve provenance and distinguish user-provided information from model-generated inference.
4.5 Retrieval is as important as storage
You can have a perfect memory database and still build a poor agent if retrieval is bad.

Imagine storing 1,000 memories for a user.

The current question is:
How should I structure my FastAPI application?


You should retrieve relevant technical preferences and architecture decisions, not the user's travel preferences or unrelated historical events.

Useful retrieval mechanisms include:
- Semantic similarity.
- Metadata filters.
- Namespace scoping.
- Recency.
- Relevance ranking.
- Limits on retrieved memories.
You should also inspect the results before adding them to the model's system context.

5. Do you even need LangMem?
No. LangMem is useful, but it is not mandatory.

You can create your own memory implementation using:
LangGraph Store
       +
Pydantic schemas
       +
Your own extraction logic
       +
Your own update logic


When should you use LangMem?

When you want existing capabilities for:
- Memory extraction.
- Memory consolidation.
- Updating existing memories.
- Memory-management tools.
- Semantic retrieval integration.
- Background memory enrichment.
When should you implement your own?

When you have specialized business rules, strict governance requirements, or a memory lifecycle that does not fit its existing abstractions.

My recommendation is to understand the Store API first, then use LangMem for higher-level memory management rather than replacing the Store with an entirely custom subsystem.
6. Common mistakes
Mistake	Better approach
Saving every message as a memory	Extract useful facts
Confusing checkpointer and Store	Keep thread and cross-thread persistence separate
Using only semantic search	Combine semantic search with scope and metadata filters
Creating duplicates	Update existing memory records
Trusting all extracted statements	Preserve provenance and validate
Storing sensitive secrets	Use proper secrets management
Using in-memory storage in production	Use a persistent Store
Assuming the agent automatically recalls every memory	Explicitly implement retrieval


L22 — Multi-Tenant Memory and Data Lifecycle
This lesson brings everything together and is particularly important for your enterprise AI integration platform.

You are not building an AI application for just one user.

You want multiple companies, each with multiple employees, using the same AI infrastructure.

That creates two significant engineering challenges:
1. Prevent one company's data from leaking into another company's conversations.
2. Manage data throughout its lifecycle, including expiration and deletion.
0. Two hard problems
Imagine your AI SaaS has three customers:
                  AI SaaS Platform
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Company A      Company B      Company C
          |              |              |
       Users          Users          Users
          |              |              |
       Memory         Memory         Memory


Each company has separate employees.

For example:
Company A
    |
    +-- Employee A1
    +-- Employee A2
    +-- Employee A3

Company B
    |
    +-- Employee B1
    +-- Employee B2


Employee A1 should never access Employee B1's private information.

Similarly, Company A should not access Company B's organization-wide memories.

You need to enforce isolation at several layers:
- Conversation checkpoints.
- Long-term memory.
- Vector search.
- RAG documents.
- File storage.
- Approval records.
- Application database.
- Langfuse traces.
- Background jobs.
This is a multi-tenant data-isolation problem.

A multi-tenant AI platform must treat tenant isolation as a security boundary, not just a storage organization convention.

1. The two scoping mechanisms
Let's distinguish two identifiers.
Thread scoping
A thread represents one ongoing conversation or workflow.

Example:
thread_id = "thread-123"



Its checkpointer stores conversation state and workflow execution information.
Store namespace scoping
The Store namespace defines which persistent memory records are accessible.

Example:
namespace = (    "memories",    "tenant-001",    "user-123",)



These mechanisms solve different problems.
Mechanism	Controls
thread_id	Which workflow/conversation checkpoint is accessed
Store namespace	Which long-term memory records are searched or accessed
tenant_id	Which customer organization owns the data
user_id	Which application user owns the data

A unique thread ID is not, by itself, an authorization mechanism.

Your backend must verify that the authenticated user actually owns or has access to that thread.

2. Namespace design
Let's design an appropriate namespace hierarchy.

For an enterprise system, I recommend:
memories/
    |
    +-- tenant-001/
    |       |
    |       +-- user-001/
    |       |       |
    |       |       +-- profile
    |       |       +-- preferences
    |       |       +-- episodic
    |       |
    |       +-- user-002/
    |               |
    |               +-- profile
    |               +-- preferences
    |
    +-- tenant-002/
            |
            +-- user-101/
                    |
                    +-- profile
                    +-- preferences


Corresponding namespaces:
user_namespace = (    "memories",    "tenant-001",    "user-001",)profile_namespace = (    "memories",    "tenant-001",    "user-001",    "profile",)preferences_namespace = (    "memories",    "tenant-001",    "user-001",    "preferences",)



This gives you a hierarchy.

You can also have organization-wide memories:
organization_namespace = (    "memories",    "tenant-001",    "organization",)



For example:
Company-wide policy:
All outgoing invoices must be reviewed by finance.


This should be available to authorized users of Company A but not Company B.
2.1 The order is the meaning
Consider these two namespaces:
("memories", "tenant-001", "user-001")



("memories", "user-001", "tenant-001")



Both are valid.

But they have different hierarchical meanings.

Remember that namespace prefix matching is important.

For example:
store.search(    ("memories", "tenant-001"))



This could retrieve memories from multiple users within tenant-001.

But:
store.search(    (        "memories",        "tenant-001",        "user-001",    ))



restricts the search to that user's namespace and its descendants.
2.2 The mistake that causes a leak
Suppose you implement:
def get_namespace(user_id: str):    return ("memories", user_id)



This has two issues.

First, there is no tenant boundary.

Second, you have assumed that a user ID is globally sufficient for the access policy you want to enforce.

Now imagine an organization wants to share some memories with all its employees.

Your namespace design does not clearly express that organization-level ownership.

More importantly, consider code that accidentally searches:
store.search(("memories",))



That namespace prefix can cover the entire memory hierarchy.

If you then put the results into an LLM prompt, you may expose multiple tenants' information.
2.3 The fix: a namespacing helper nobody can bypass
Create one centralized namespace factory.
def user_memory_namespace(    tenant_id: str,    user_id: str,) -> tuple[str, ...]:    return (        "memories",        tenant_id,        "user",        user_id,    )



And for organizations:
def organization_memory_namespace(    tenant_id: str,) -> tuple[str, ...]:    return (        "memories",        tenant_id,        "organization",    )



Use these helpers everywhere.

Do not allow random application components to construct namespaces manually.

This establishes a consistent convention.
2.4 The template approach
LangMem supports dynamic namespace templates.

Example:
from langmem import create_manage_memory_toolmanage_memory = create_manage_memory_tool(    namespace=(        "memories",        "{tenant_id}",        "user",        "{user_id}",    ))



The placeholders are populated using configured runtime values.

However, there is a very important security consideration:

The values used to populate tenant and user namespaces must come from trusted server-side authentication context.

Do not blindly populate them using arbitrary values supplied by the user.

For your architecture, the preferred flow is:
Incoming HTTP request
       |
       v
Authentication middleware
       |
       v
Verify identity and tenant membership
       |
       v
Construct trusted Context
       |
       v
Pass Context to LangGraph
       |
       v
Access Store through trusted namespace


2.5 The same rule for checkpoints
You must enforce the same isolation for graph checkpoints.

A client might submit:
{
    "thread_id": "another-company-thread"
}


Your application must not simply trust that ID.

Before reading or resuming the graph:
1. Verify the authenticated user.
2. Verify the tenant.
3. Find the thread's ownership record.
4. Verify the user has access to it.
5. Only then access or resume the graph.
You can maintain your own thread registry:
CREATE TABLE conversation_threads (
    thread_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


This gives your application a reliable ownership mapping.

You may use random UUIDs for thread IDs, but randomness is not a replacement for authorization.

3. Test your isolation
You should have automated tests for tenant isolation.

For example:
def test_tenant_namespace_isolation(store):    tenant_a = (        "memories",        "tenant-a",        "user",        "user-1",    )    tenant_b = (        "memories",        "tenant-b",        "user",        "user-2",    )    store.put(        tenant_a,        "memory-1",        {"text": "Company A secret"},    )    store.put(        tenant_b,        "memory-1",        {"text": "Company B secret"},    )    results = store.search(        tenant_a,        query="company secret",    )    assert all(        item.value["text"] != "Company B secret"



For more reliable testing, also verify exact namespace and key lookups, semantic searches, metadata filters, and access through real authenticated API requests.

Test both successful access and attempted unauthorized access.

A good security test should establish that a user cannot access another tenant's information even when they know the other user's ID or thread ID.

4. TTL: making state expire on its own
Now let's move to data retention.

Imagine you store thousands of short-lived pieces of memory.

Examples:
- Temporary project context.
- Temporary conversation summaries.
- Short-lived agent observations.
- Expiring application session information.
You might not want to retain these forever.

You need TTL.

TTL stands for Time To Live.

For example:
Memory created:
November 2, 2026

TTL:
30 days

Expiration:
December 2, 2026


The Store supports TTL configurations when the underlying implementation supports expiration.
4.1 The Store has TTL built in
You can use:
store.put(    namespace,    "temporary-memory",    {        "text": "Temporary project context",    },    ttl=60,)



The TTL argument is expressed in minutes.

Therefore:
ttl=60



means approximately 60 minutes, not 60 seconds.

You can also configure default TTL behavior.

Conceptually:
from langgraph.store.base import TTLConfigttl_config = TTLConfig(    default_ttl=60 * 24 * 30,    refresh_on_read=True,    omit_expired=True,)



This gives new items a default retention period of 30 days, with refresh-on-read enabled and expired items omitted from reads where supported.

The important settings:
Setting	Meaning
default_ttl	Default expiry duration, in minutes
refresh_on_read	Whether reads refresh the expiration
omit_expired	Whether expired items are hidden from reads
sweep_interval_minutes	How frequently expired records are physically cleaned up

4.2 Three unit and semantics traps
Trap 1: Minutes, not seconds
ttl=60



is one hour.

For one day:
ttl=60 * 24



For 30 days:
ttl=60 * 24 * 30



Trap 2: Sliding expiration

When refresh-on-read is enabled, expiration may be refreshed when the item is accessed.

For example:
Day 1: Memory created
Day 10: Memory read; TTL refreshed
Day 20: Memory read; TTL refreshed


It may remain available longer than the original 30-day period.

This is called sliding expiration.

Sometimes you want this behavior for frequently used sessions.

Sometimes you don't.

For a fixed retention policy, you must ensure that reads do not extend the intended retention period.

Trap 3: Expiration versus physical deletion

There is an important distinction between:
- An item being expired.
- An item no longer being returned in searches.
- An item physically being deleted from storage.
These are not necessarily simultaneous.

The sweeper is responsible for deleting expired records.

The current Store documentation describes TTL as best-effort expiration and includes controls for refreshing, omitting expired items, and periodic cleanup. 

GitHub+1

For PostgreSQL, the async Store requires explicit sweeper startup when using its TTL feature.

Conceptually:
await store.start_ttl_sweeper()



And during shutdown:
await store.stop_ttl_sweeper()



Use the appropriate lifecycle methods for your installed version.

The sweeper should be managed by your application lifecycle rather than started and stopped for every individual request. 

LangChain Reference+1


5. Checkpoint threads have no universal TTL — sweep them yourself
This is an important distinction.

You may configure TTL for Store memories.

But you should not assume that every checkpointer automatically deletes old threads using the same TTL mechanism.

For example:
Long-term Store
     |
     +-- Memory 1: 30-day TTL
     +-- Memory 2: 60-day TTL

Checkpoint database
     |
     +-- Thread 1
     +-- Thread 2
     +-- Thread 3


These systems have different lifecycle responsibilities.

For threads, maintain a separate registry:
CREATE TABLE conversation_threads (
    thread_id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,

    status TEXT NOT NULL,

    last_activity_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ
);


Your sweeper can identify expired threads and delete their checkpoints using the deletion capabilities of the configured checkpointer, such as its delete_thread or async equivalent where supported.

Do not assume an arbitrary checkpointer adapter exposes identical retention and deletion behavior.
5.1 Or trim instead of delete
Sometimes you should retain the workflow but reduce its data.

For example:
Active conversation
       |
       v
Conversation completed
       |
       v
Archive state
       |
       v
Remove unnecessary messages
       |
       v
Retain required records


You might need to retain:
- Important approval outcomes.
- Business decisions.
- Required compliance records.
- Selected conversation summaries.
But remove:
- Temporary tool outputs.
- Unnecessary intermediate state.
- Expired session information.
- Irrelevant historical messages.
This is different from deleting the thread completely.

Also be careful: checkpoint state is not necessarily an ordinary message list. State editing and checkpoint deletion must respect the persistence adapter's actual API and the audit requirements of your application.

6. "Delete this user" — the complete data-deletion problem
This is arguably the most important part of the lesson for a commercial AI SaaS.

Suppose an employee requests deletion of their account.

What should happen?

You cannot simply delete their account from PostgreSQL and declare the work complete.

Your AI application may have stored that person's information in multiple systems.

Consider the architecture:
                  User Data
                      |
       +--------------+--------------+
       |              |              |
       v              v              v
    Postgres        LangGraph       Vector DB
    App DB          Checkpoints     RAG
       |
       +--------------+--------------+
                      |
                      v
                   LangMem
                      |
                      v
                    Store

                  Other systems
                      |
           +----------+----------+
           |                     |
           v                     v
        Langfuse             Object Storage


A correct deletion operation needs to understand every place where personal data is stored.
6.1 Threads and memories
First, identify the user's threads.

Your application database should provide this mapping:
SELECT thread_id
FROM conversation_threads
WHERE tenant_id = :tenant_id
  AND user_id = :user_id;


You can then delete those thread checkpoints through the configured checkpointer's supported deletion API.

Next, identify the user's memory namespaces:
namespace = (    "memories",    tenant_id,    "user",    user_id,)



Delete the associated Store items.

Important: deleting items requires identifying the full namespace hierarchy, including any sub-namespaces.

You also need to consider memory records in other namespaces if the user contributed information to an organization-wide shared memory.

Deleting an employee must not accidentally delete legitimate organization-owned records, but it must address personal data that has been embedded in those records.
6.2 Vector rows: your RAG collection
Suppose your RAG system contains:
Qdrant
   |
   +-- Document 1
   +-- Document 2
   +-- Document 3


Some documents may contain personal information associated with the deleted user.

You need to identify records using metadata such as:
{
    "tenant_id": "tenant-001",
    "user_id": "user-123",
    "source_id": "document-456"
}


Then delete those records or redact the relevant personal information.

However, be careful.

A shared organizational document may contain information about multiple employees.

Deleting one user should not automatically remove an entire shared document if it is still legitimately needed.

Your application needs a data-ownership policy.

Also consider:
- Original uploaded files.
- Extracted document text.
- Chunk records.
- Embeddings.
- Cached retrieval results.
- Derived summaries.
Deleting only the vector does not necessarily delete the original document.
6.3 Langfuse traces
Because you are also learning Langfuse, this is especially important.

Your LLM observability system may store:
- User messages.
- Model prompts.
- Model outputs.
- Tool inputs.
- Tool outputs.
- Execution metadata.
- User identifiers.
- Session identifiers.
For example:
User asks a question
       |
       v
LangGraph
       |
       v
Gemini
       |
       v
Langfuse trace


Deleting LangGraph's checkpoint does not automatically delete the corresponding Langfuse trace.

You need to maintain a correlation strategy between your application's user records and observability data.

For current Langfuse documentation, trace deletion supports individual deletion and batch deletion through its public API:
DELETE /api/public/traces/{traceId}


and:
DELETE /api/public/traces


Deleting traces also deletes related observations and scores. However, other objects, such as independent dataset items, require separate consideration.

Importantly, Langfuse trace deletion is asynchronous. You should verify deletion rather than treating the API request as proof that every underlying record has already been physically removed. 

Langfuse

An important additional distinction:

Data access is not data retention.

Just because old Langfuse traces are no longer visible within a particular account's access window does not mean that they have been deleted.

For self-hosted deployments, review your Langfuse version and edition's retention capabilities. The current documentation describes project retention as an Enterprise Edition feature for self-hosted deployments. 

Langfuse+1

6.4 Your own tables
You must also delete the user's data from your application database.

Potential tables:
users
user_profiles
conversation_threads
approval_requests
approval_audit_events
user_preferences
uploaded_files
integration_connections
agent_sessions


But there is a distinction between deleting personal data and deleting business audit records.

For example:
An employee requested a refund.
A manager approved it.
The refund was executed.


You may have a legal or business requirement to preserve the transaction and its audit history.

That does not necessarily mean retaining all personal information indefinitely.

Use your organization's retention and deletion policy to decide what can be deleted, what must be anonymized, and what must be retained.
6.5 Return counts and log them
A deletion operation should produce a report.

For example:
{
    "user_id": "user-123",
    "deletion_request_id": "delete-1001",
    "status": "completed",
    "deleted": {
        "threads": 5,
        "memories": 18,
        "vector_records": 42,
        "langfuse_traces": 120,
        "application_records": 12,
        "uploaded_files": 3
    }
}


These figures are illustrative.

You should also record:
- Started timestamp.
- Completed timestamp.
- Systems processed.
- Number of records deleted.
- Number of records anonymized.
- Number of failures.
- Retry status.
- Verification status.
Do not put unnecessary personal details into the deletion audit itself.

For production, deletion should be a durable, retryable workflow rather than one enormous HTTP request that tries to delete everything synchronously.

One more important point: consider backups, replicas, caches, exported datasets, and third-party integrations. A live database deletion does not automatically erase every historical backup or exported copy.

7. The complete lifecycle checklist
Let's combine all the concepts.
The AI user's data lifecycle
1. Data creation
   
   User creates conversations, approvals, memories, and uploads documents.
2. Data persistence
   
   Checkpointer stores workflow state. Store persists long-term memory. PostgreSQL stores business records.
3. Data retrieval
   
   Application authenticates the user, scopes namespaces and thread access, and retrieves relevant information.
4. Data maintenance
   
   Memory consolidation, summaries, TTL processing, and checkpoint cleanup.
5. Data expiration
   
   Temporary information expires according to the retention policy.
6. Data deletion
   
   Delete or anonymize associated data across all systems.
7. Verification
   
   Verify deletion and record the outcome.

For your enterprise platform, I recommend treating the deletion process as its own state machine.

For example:
REQUESTED
    |
    v
IN_PROGRESS
    |
    +--> Delete checkpoints
    |
    +--> Delete long-term memories
    |
    +--> Delete RAG records
    |
    +--> Delete observability traces
    |
    +--> Delete application data
    |
    v
VERIFYING
    |
    v
COMPLETED


If one system fails:
IN_PROGRESS
    |
    v
PARTIAL_FAILURE
    |
    v
RETRY FAILED STEPS
    |
    v
VERIFYING


This is much more reliable than assuming that a single database transaction can delete data across every subsystem.
8. Common mistakes
Mistake	Correct approach
Using user_id without tenant scoping	Include tenant and user in the namespace
Trusting user-supplied namespace values	Derive scopes from authenticated context
Treating thread IDs as authorization	Verify thread ownership
Using broad namespace searches	Use tightly scoped namespaces
Assuming TTL means immediate physical deletion	Manage expiration and sweeper execution
Assuming checkpoints expire with Store items	Manage thread retention separately
Deleting only embeddings	Delete original and derived data as required
Deleting only LangGraph data	Include Langfuse and other systems
Treating data visibility as data deletion	Verify actual deletion
Running deletion only once	Use durable, retryable workflows


9. Modern versus deprecated: consolidated reference
Here is the important API reference for this entire phase.
Area	Modern implementation	Old / legacy approach or caution
Dynamic HITL	interrupt()	NodeInterrupt — deprecated
Resume	Command(resume=...)	Manually raising interruption exceptions
v2 graph result	result.value, result.interrupts	result["__interrupt__"] compatibility access
Static breakpoints	interrupt_before, interrupt_after	Do not use as your main business approval system
Agent HITL	HumanInTheLoopMiddleware	Reimplementing approval interception in every tool
Agent creation	create_agent	Older create_react_agent examples in older tutorials should be checked against the current migration documentation
Short-term context	trim_messages, context/summarization middleware	Sending the entire history indefinitely
Context editing	ContextEditingMiddleware, ClearToolUsesEdit	Treating all tool outputs as permanently required
Summarization	SummarizationMiddleware(trigger=..., keep=...)	Older constructor parameter names marked deprecated in the current documentation
Runtime Store access	runtime.store	Unnecessary global Store access
Long-term persistence	LangGraph BaseStore implementations	Using InMemoryStore as permanent production storage
Memory management	LangMem tools and memory managers	Saving every message without extraction
Production Store	PostgreSQL, MongoDB, Redis and other persistent stores	In-memory-only storage
TTL	Store TTLConfig and supported sweeper	Assuming every Store adapter has identical TTL support
Tenant isolation	Trusted context plus tenant-scoped namespaces	Unrestricted, client-controlled namespace construction

A clarification about the versioned APIs:
- version="v2" provides the unified GraphOutput and StreamPart style.
- stream_events(..., version="v3") is a newer typed streaming interface that exposes projections such as messages, state, and interrupts.
- They have different purposes and are not interchangeable version numbers.
For interrupt-heavy applications, the newer event-streaming API is particularly useful when you want to stream model tokens and detect human interruptions through one interface. 

GitHub+1


10. The complete architecture: how L18–L22 work together
Now imagine building your enterprise AI assistant.

It has:
- FastAPI backend.
- LangChain agents.
- LangGraph workflows.
- Gemini models.
- Langfuse observability.
- PostgreSQL.
- Redis.
- Qdrant.
- Long-term memory.
- Human approval.
- Multiple companies and users.
This is how everything fits together.







medium.com


Component	Responsibility
FastAPI	Authentication, authorization, APIs
LangChain	Models, prompts, tools, middleware
LangGraph	Workflow execution, state, interrupts, checkpointing
Gemini	Reasoning, extraction, generation
PostgreSQL checkpointer	Thread and execution persistence
LangGraph Store	Cross-thread long-term memory
LangMem	Memory extraction and management
Qdrant	RAG document and vector retrieval
Redis	Caching and suitable transient coordination
Langfuse	Tracing, evaluations and observability
Approval database tables	Business approval lifecycle
Background workers	Memory processing, expiry, deletion, reliable resume

The entire architecture works together like this:
                         USER
                          |
                          v
                       FRONTEND
                          |
                          v
                        FASTAPI
                          |
                Authentication / Tenant
                     Authorization
                          |
                          v
                   LANGCHAIN AGENT
                          |
              +-----------+-----------+
              |           |           |
              v           v           v
            GEMINI       TOOLS      MEMORY
              |           |           |
              |           |           v
              |           |        LANGMEM
              |           |           |
              |           |           v
              |           |       LANGGRAPH STORE
              |           |
              +-----------+
                          |
                          v
                      LANGGRAPH
                          |
           +--------------+--------------+
           |              |              |
           v              v              v
       Checkpoint      interrupt      Summarization
           |              |
           v              v
       PostgreSQL     Approval API
                          |
                          v
                    Approval Database
                          |
                     Human Review
                          |
                     Command(resume)
                          |
                          v
                   Resume Workflow
                          |
                          v
                    Execute Action
                          |
                          v
                       LANGFUSE


The important thing is that these are separate responsibilities connected through well-defined interfaces.

You should not treat LangGraph as your complete application backend, LangMem as your only database, or Langfuse as your business audit system.

Each component solves a specific problem.

11. Final knowledge check — Phase 8
You've now covered a substantial amount of material. Test your understanding with these questions.
Phase 8 assessment
0/9 answered

1. What is the main difference between a checkpointer and a LangGraph Store?

Both do exactly the same thing

Checkpointer saves thread execution state; Store persists cross-thread information

Store manages model tokens

Checkpointer only stores embeddings



2. Why must a graph node be idempotent around interrupt()?

Because the model has a limited context window

Because the node re-executes from its beginning when resumed

Because PostgreSQL cannot update rows

Because interrupts delete state



3. What is the main purpose of ContextEditingMiddleware?

Permanently delete conversation history

Reduce tool-result context sent to the model

Generate embeddings

Create user accounts



4. What does SummarizationMiddleware do?

Summarizes older conversation context when a trigger is reached

Deletes every old checkpoint

Creates approval requests

Automatically updates all user profiles



5. Which LangMem component manages memories directly in a BaseStore?

create_memory_store_manager

interrupt

trim_messages

InMemorySaver



6. Why is a namespace such as ('memories', tenant_id, user_id) important?

It increases model intelligence

It provides a tenant/user organization and retrieval boundary

It changes the thread ID

It creates a model profile



7. What is the correct way to prevent two managers deciding the same approval concurrently?

Add a sleep statement

Use an atomic conditional database update or transaction

Trust the frontend

Generate a new thread ID



8. Does Store TTL automatically delete every LangGraph checkpoint?

Yes

No, checkpoint retention requires separate lifecycle management



9. Is deleting a LangGraph thread sufficient for a complete user-data deletion?

Yes

No, consider Store, RAG, Langfuse, application databases, files and backups


Submit assessment

🎓 Phase 8 complete
You have now covered five major areas:
Lesson	What you learned
L18	Dynamic interrupts, resuming, structured responses, agent HITL
L19	Production approvals, authorization, atomic claims, audit trails
L20	Context windows, message trimming, context editing, summarization
L21	Store API, PostgresStore, LangMem, semantic and structured memory
L22	Tenant isolation, TTL, expiration, deletion and data lifecycle

The biggest architectural lessons to remember:
1. An interrupt is a durable workflow pause, not a blocking Python function.
2. Approval decisions belong to your application's authorization and business layer.
3. Short-term memory and long-term memory solve different problems.
4. Summarization and context editing help control what goes into the LLM.
5. A LangGraph Store provides persistent, cross-thread memory.
6. LangMem provides higher-level memory extraction and management.
7. Namespace isolation and authorization are essential for multi-tenant systems.
8. Data deletion must cover every system that stores or derives user data.
For further reference, these are the primary documentation resources:
- LangGraph — Interrupts
- LangGraph — Add Memory
- LangGraph — Stores
- LangChain — Human-in-the-Loop
- LangChain — Built-in Middleware
- LangMem
- Langfuse — Data Deletion
My recommendation for the next practical step: build one integrated project implementing a multi-tenant AI assistant with Gemini, LangGraph, PostgreSQL checkpointing, LangGraph Store, LangMem, an approval workflow, and Langfuse tracing. That will connect all five lessons into one working enterprise architecture.
