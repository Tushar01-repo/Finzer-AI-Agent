PHASE 1   Tool / MCP Foundation
              ↓
PHASE 2   RAG Tool Integration
              ↓
PHASE 3   Agent State + Context
              ↓
PHASE 4   Core ReAct Loop
              ↓
PHASE 5   Tool Governance + HITL
              ↓
PHASE 6   Evidence + Final Response
              ↓
PHASE 7   E2E Evaluation + Production Hardening


ReAct_agent/
└── app/
    └── agent/
        ├── __init__.py
        ├── state.py        ← FIRST
        ├── context.py
        ├── entities.py
        └── graph.py        ← Later 