Yes. Before coding Phase 3, this is worth designing carefully because **Agent State and Context Manager are different things**, and mixing them tends to make ReAct agents messy.

For Finzer, I’d structure it like this:

```text
                         USER MESSAGE
                              │
                              ▼
                    ┌───────────────────┐
                    │  Context Manager  │
                    │                   │
                    │ Resolve what this │
                    │ message means in  │
                    │ conversation      │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │    Agent State    │
                    │                   │
                    │ Current execution │
                    │ state of the turn │
                    └─────────┬─────────┘
                              │
                              ▼
                       ReAct Agent
                              │
              ┌───────────────┼──────────────┐
              ▼               ▼              ▼
             Tool          Clarify         Answer
              │
              ▼
          Observation
              │
              └──────────────► Agent State
```

## 1. What exactly is `AgentState`?

Think of `AgentState` as the **working memory / execution record of one agent run**.

It answers:

> “What does the agent currently know, what has it done, and what should happen next?”

It should **not itself perform retrieval, call an LLM, resolve entities, or execute tools**.

For example, suppose the conversation is:

> User: Tell me about SBI Small Cap Fund.

The state might become conceptually:

```python
user_query = "Tell me about SBI Small Cap Fund"

current_entity = {
    "type": "MUTUAL_FUND",
    "name": "SBI Small Cap Fund",
    "scheme_code": "125497",
}

intent = "GET_MUTUAL_FUND_DETAILS"

next_action = "TOOL"

selected_tool = "get_mutual_fund_details"

tool_arguments = {
    "scheme_code": "125497"
}

step_count = 1
tool_call_count = 0
```

After executing the tool:

```python
tool_call_count = 1

observations = [
    {
        "tool": "get_mutual_fund_details",
        "status": "success",
        "data": {...}
    }
]

evidence = [...]
```

The ReAct agent gets the updated state and decides what happens next.

---

# 2. What should our AgentState contain?

I would divide it into **seven logical areas** rather than making one giant unstructured dictionary.

```text
AgentState
│
├── 1. Request
│     ├── user_query
│     └── user_id
│
├── 2. Conversation Context
│     ├── messages
│     ├── conversation_summary
│     └── current_entity
│
├── 3. Reasoning / Routing
│     ├── intent
│     ├── next_action
│     ├── selected_tool
│     └── tool_arguments
│
├── 4. Execution
│     ├── observations
│     ├── errors
│     ├── step_count
│     └── tool_call_count
│
├── 5. Evidence
│     └── evidence[]
│
├── 6. Governance / HITL
│     ├── approval_required
│     ├── approval_status
│     └── pending_tool_call
│
└── 7. Output
      ├── evidence_validation
      └── final_answer
```

There are a few things here I would change from our earlier rough design.

For example, instead of:

```python
selected_tool: str
tool_arguments: dict
```

I'd prefer:

```python
pending_tool_call: ToolCall | None
```

where:

```python
ToolCall(
    tool_name="wishlist_add",
    arguments={
        "asset_type": "MUTUAL_FUND",
        "asset_id": "125497",
        ...
    }
)
```

That becomes much cleaner when we introduce the execution gate.

---

# 3. Observations are especially important

In ReAct, an observation should not simply be a giant blob returned from a tool.

We want something like:

```python
ToolObservation(
    tool_name="news_rag",
    status="success",
    data={...},
    error=None,
    retryable=False,
)
```

Another example:

```python
ToolObservation(
    tool_name="gold_price_history",
    status="error",
    data=None,
    error={
        "type": "PLAN_RESTRICTION",
        "message": "Historical data unavailable..."
    },
    retryable=False,
)
```

The agent can then reason:

```text
Thought/Decision:
Gold history unavailable.

Should I:
    retry?       ❌
    use another tool? 
    clarify? 
    answer with limitation?
```

This is much better than throwing an exception all the way into the agent.

---

# 4. Evidence should be separate from observations

This distinction will become important later.

An **observation** means:

> What happened when I called a tool?

**Evidence** means:

> What information am I allowed to use to support the answer?

For example:

```text
Observation
────────────────────────────
news_rag executed successfully
returned 5 articles
```

From it we derive:

```text
Evidence
────────────────────────────
Article 1
source = Financial Express
published_at = ...
title = ...
summary = ...
similarity = ...

Article 2
...
```

Likewise:

```text
get_latest_nav
      │
      ▼
Observation
      │
      ▼
Evidence
NAV = 205.754
Date = 2026-10-01
Provider = MFAPI
```

This is exactly why we already added:

```python
returns_evidence=True
```

to the relevant registry contracts. Your registry's evidence filtering already gives us a clean way of identifying such tools. Pasted markdown

Then later:

```text
observations
      │
      ▼
evidence
      │
      ▼
Evidence Validator
      │
      ├── sufficient? 
      ├── fresh?
      ├── correct entity?
      ├── conflicting?
      └── attributable?
      │
      ▼
Response Composer
```

---

# 5. What is the Context Manager then?

This is where the distinction matters.

The **Context Manager is not storage**.

It's a component that **constructs the useful conversational context for the current turn**.

Consider:

> User: Tell me about SBI Small Cap Fund.

Then:

> User: What's its latest NAV?

Then:

> User: Add it to my wishlist.

The second and third questions don't contain enough information independently.

The Context Manager needs to understand:

```text
"its"
 ↓
SBI Small Cap Fund
 ↓
scheme_code = 125497
```

So I see the Context Manager as:

```text
Raw conversation
       +
Current user message
       +
Previous resolved entity
       +
Conversation summary
       │
       ▼
┌──────────────────────────┐
│     Context Manager      │
│                          │
│ resolve references       │
│ maintain active entity   │
│ compact conversation     │
│ identify missing context │
└────────────┬─────────────┘
             │
             ▼
       Prepared Context
```

---

# 6. Entity tracking is probably the most important part

For Finzer, I would make entity tracking explicit.

We have several entity types already:

```text
MUTUAL_FUND
GOLD
COMPANY
IPO_DOCUMENT
NEWS_TOPIC
```

Possibly later:

```text
STOCK
ETF
INDEX
```

An entity object might conceptually contain:

```python
ResolvedEntity(
    entity_type="MUTUAL_FUND",
    name="SBI Small Cap Fund",
    canonical_id="125497",
    metadata={
        "plan": "Direct",
        "option": "Growth",
    },
)
```

For IPO:

```python
ResolvedEntity(
    entity_type="IPO_DOCUMENT",
    name="Hi-Tech Flow Solutions Limited",
    canonical_id="<document_key>",
    metadata={
        "document_type": "DRHP"
    },
)
```

This solves something we've intentionally postponed.

The LLM should **never have to know**:

```text
3adccc083d26e3b574fb187d92c87e80...
```

Instead:

```text
User:
"What are the objects of offer for
Hi-Tech Flow Solutions?"

            ↓

Context / Entity Resolver

            ↓

Hi-Tech Flow Solutions
document_type = DRHP
document_key = 3adccc...

            ↓

document_rag
```

That's much cleaner.

---

# 7. Context Manager shouldn't send the whole chat to the LLM

This is another important architectural decision.

We don't want:

```text
Message 1
Message 2
Message 3
...
Message 173
        ↓
LLM
```

Eventually that gets expensive and noisy.

Instead:

```text
Recent messages
        +
Conversation summary
        +
Active entity
        +
Relevant observations
        +
Current request
        ↓
Prepared Agent Context
```

For example:

```python
PreparedContext(
    user_query="What about its last 30 days?",
    conversation_summary=(
        "User is investigating SBI Small Cap Fund."
    ),
    active_entities=[
        {
            "type": "MUTUAL_FUND",
            "name": "SBI Small Cap Fund",
            "id": "125497",
        }
    ],
    recent_messages=[...],
)
```

The ReAct LLM sees **this**, not necessarily the complete conversation.

---

# 8. Don't put every tool result back into LLM context forever

Suppose News RAG returns 10 long articles.

We don't want:

```text
Tool call 1 → 8K tokens
Tool call 2 → 6K tokens
Tool call 3 → 9K tokens
```

and then send all 23K tokens into every subsequent reasoning step.

I'd make the Context Manager enforce a budget:

```text
System instructions
        ~1500 tokens

Conversation summary
        ~500

Recent messages
        ~1500

Entity context
        ~300

Relevant observations/evidence
        ~3000

Current user query
        ~200
────────────────────
Agent context
        bounded
```

Those numbers are illustrative, not hard requirements yet.

---

# 9. Context Manager vs DocumentContextBuilder

We should also keep these two concepts separate.

We already have the ingestion-side:

```text
DocumentContextBuilder
```

Its responsibility is:

> Take retrieved IPO chunks and construct RAG context.

The new:

```text
Agent Context Manager
```

has a broader responsibility:

> Decide what information from the conversation and agent execution should be presented to the reasoning model.

So:

```text
DocumentContextBuilder
        ↓
RAG-specific context

ContextManager
        ↓
Agent-specific context
```

We should **not reuse one as the other**.

---

# 10. Where conversation memory should live

I wouldn't make `AgentState` itself the permanent conversation database.

Think of three layers:

```text
                    MEMORY MODEL

┌──────────────────────────────────────┐
│ Long-term / persistent context       │
│                                      │
│ user preferences                     │
│ wishlist                             │
│ maybe saved interests later          │
└─────────────────┬────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────┐
│ Conversation context                 │
│                                      │
│ summary                              │
│ active entities                      │
│ recent turns                         │
└─────────────────┬────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────┐
│ AgentState                           │
│                                      │
│ execution state for current run      │
│ pending tool                         │
│ observations                         │
│ evidence                             │
│ counters                             │
│ approval                             │
└──────────────────────────────────────┘
```

For v1, conversation context can still be in-memory. We don't need Redis/checkpointing yet.

Later LangGraph persistence/checkpointing can sit underneath this without forcing us to redesign the state semantics.

---

# 11. One tricky example: follow-up query

Imagine:

> **User:** Tell me about SBI Small Cap Fund.

The agent resolves:

```text
active_entity
    MUTUAL_FUND
    SBI Small Cap Fund
    scheme_code=125497
```

Then user:

> **User:** Compare its recent performance with gold.

Context Manager produces:

```text
Current query:
Compare its recent performance with gold.

Resolved references:
"its" → SBI Small Cap Fund / 125497

Entities:
1. SBI Small Cap Fund
2. Gold

Relevant prior context:
User was discussing SBI Small Cap Fund.
```

Then ReAct can decide:

```text
Step 1
get_nav_history(
    scheme_code=125497,
    ...
)

Step 2
gold_price_history(
    ...
)

Step 3
compare observations

Step 4
answer
```

Notice the Context Manager did **not** choose those tools.

That's the ReAct agent's job.

This separation is important:

```text
Context Manager
    "What does the user mean?"

ReAct Agent
    "What should I do?"

Tool Registry / Execution Gate
    "Am I allowed to do it?"

Tool
    "Perform it."

Evidence Validator
    "Do I have enough trustworthy information?"

Response Composer
    "How should I answer?"
```

That is the architecture I'd keep.

---

# 12. Approval also belongs in state

Suppose:

> User: I like SBI Small Cap Fund.

The agent should **not** infer:

```text
wishlist_add
```

But:

> Add SBI Small Cap Fund to my wishlist.

can become:

```python
pending_tool_call = {
    "tool": "wishlist_add",
    ...
}

approval_required = True/False
```

Whether explicit wording itself satisfies the conditional approval policy will be decided by the Execution Gate/HITL layer later.

If the workflow pauses for approval, AgentState retains:

```text
pending_tool_call
active entity
observations
step count
approval status
```

Then execution can resume rather than restarting the entire agent.

---

## The state model I'd build

Conceptually, I'd aim for:

```text
AgentState
│
├── run_id
├── user_id
├── user_query
│
├── messages
├── conversation_summary
├── active_entities[]
│
├── intent
├── next_action
├── pending_tool_call
│
├── observations[]
├── evidence[]
├── errors[]
│
├── approval
│
├── step_count
├── tool_call_count
│
├── evidence_validation
└── final_answer
```

And Context Manager:

```text
ContextManager
│
├── prepare_context()
├── resolve_references()
├── select_recent_messages()
├── select_relevant_observations()
├── maintain_active_entities()
└── enforce_context_budget()
```

I would **not implement intent classification inside the Context Manager**. Intent should be part of the ReAct reasoning decision because queries can require multiple tools and multiple intents.

The most important design principle for Finzer is therefore:

> **AgentState stores what is happening. Context Manager determines what context matters. ReAct decides what to do.**

That separation will make the upcoming LangGraph much easier to reason about and test.