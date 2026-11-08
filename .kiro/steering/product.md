# NeuroRoute — Product Overview

## Purpose

NeuroRoute is an adaptive AI inference architecture that intelligently routes user queries to the most appropriate language model and execution strategy, based on the complexity, cost, latency, and quality requirements of each request.

Rather than sending every query to the same large language model, NeuroRoute analyses each request and selects the optimal inference path dynamically.

---

## Problem Statement

Traditional LLM applications use a fixed model for every query regardless of its complexity. This creates four concrete problems:

- **Unnecessary cost** — simple queries consume the same compute budget as complex ones.
- **Higher latency** — powerful models are slower; lightweight queries do not need them.
- **Inefficient resource utilisation** — GPU/token capacity is wasted on over-provisioned responses.
- **No feedback loop** — response quality is never measured, so routing never improves.

NeuroRoute addresses all four by interposing an adaptive routing layer between the user and the model pool.

---

## Target Users

- **AI/ML engineers** building cost-sensitive inference pipelines.
- **Researchers** benchmarking multi-model routing strategies.
- **Developers** who need a self-optimising backend for LLM-powered products.
- **Hackathon evaluators** assessing adaptive inference architectures.

---

## Planned Adaptive Inference Workflow

This is the intended end-to-end flow once all components are built. **None of the steps below the FastAPI backend currently exist in code.**

```
User
  │
  ▼
React Frontend          ← Implemented
  │  (REST / JSON)
  ▼
FastAPI Backend         ← Implemented
  │
  ▼
Query Intelligence      ← Planned: complexity estimation, intent classification
  │
  ▼
Adaptive Router         ← Planned: model selection based on cost / latency / quality
  │
  ├──────────────────┐
  ▼                  ▼
Model A            Model B  ← Planned: LLM client adapters (e.g. Gemini, Llama 3)
  │                  │
  └────────┬─────────┘
           ▼
  Response Evaluation       ← Planned: quality scoring against ground truth or heuristics
           │
           ▼
  Feedback & Optimisation   ← Planned: routing table updates, cost/latency learning
           │
           ▼
      User Response
```

### Core Objectives (all planned)

1. Analyse incoming user queries.
2. Estimate query complexity.
3. Select suitable LLMs and execution strategies.
4. Monitor inference latency and token usage.
5. Evaluate response quality.
6. Learn from execution feedback.
7. Optimise the balance between cost, latency, and quality.

---

## Feature Status

### Implemented

| Feature | Detail |
|---|---|
| React frontend | Single-page UI for submitting prompts and viewing saved requests |
| FastAPI backend | REST API with CORS, health check, and request endpoints |
| MySQL database | `neuroroute` database with the `requests` table |
| SQLAlchemy ORM | Full connection, session management, and model definition |
| `POST /api/requests/` | Accepts a prompt, saves it with `status="pending"` |
| `GET /api/requests/` | Returns all saved requests ordered newest-first |
| `GET /api/health` | Backend health check endpoint |
| Database scripts | `create_tables.py`, `test_db.py`, `test_crud.py` |

### Planned

| Feature | Detail |
|---|---|
| Kiro spec & steering setup | Formal spec-driven development workflow |
| Query complexity estimation | Classify queries by difficulty before routing |
| Multi-model execution engine | Invoke multiple LLMs based on routing decisions |
| Adaptive model router | Dynamic selection of Model A vs Model B |
| Response quality evaluation | Score and compare responses |
| Feedback-driven optimisation | Update routing weights from outcome data |
| MCP integration | Model Context Protocol tooling |
| Observability dashboard | Real-time latency, cost, and quality metrics |
| Performance benchmarking | Comparison against fixed-model and static-routing baselines |
| Deployment | Production environment setup |

---

## Development Approach

NeuroRoute is built incrementally using Kiro's spec-driven workflow:

1. Define requirements in a spec.
2. Design the architecture.
3. Break the feature into tasks.
4. Implement and test each component.
5. Evaluate against reproducible benchmarks.

**Expected outcome:** A demonstrable adaptive inference architecture that balances cost, latency, response quality, and resource utilisation — measured against fixed-model baselines.
