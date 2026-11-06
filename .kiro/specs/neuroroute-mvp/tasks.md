# Implementation Plan: NeuroRoute MVP

## Overview

This plan extends the existing React 19 + FastAPI + MySQL stack with six new backend subsystems — Model Registry, Query Intelligence, Routing Engine, Multi-Model Execution, Quality Evaluation, and Feedback — plus an updated Observability Dashboard. The existing `POST /api/requests/`, `GET /api/requests/`, and `GET /api/health` endpoints are preserved unchanged until Phase 9 (Pipeline Integration).

Work follows a strict dependency order: DB models → services → routers → tests. Each phase ends with a checkpoint task that verifies the phase before moving on.

---

## Tasks

- [ ] 1. Phase 1: Backend Foundation and Database Migrations
  - [-] 1.1 Create `backend/requirements.txt` with pinned package versions
    - Create `backend/requirements.txt` with the following pinned versions:
      ```
      fastapi==0.162.0
      uvicorn==0.54.0
      sqlalchemy==2.1.6
      pymysql==1.2.3
      python-dotenv==1.2.4
      pydantic==2.14.2
      httpx==0.28.1
      openai==3.45.0
      hypothesis==6.170.14
      pytest==9.2.0
      pytest-asyncio==1.4.1.post1
    - This file must exist before any new import is added to source code
    - _Requirements: 4.1, 4.4, 4.5_

  - [ ] 1.2 Create `backend/app/exceptions.py` with the full custom exception hierarchy
    - Define `NeuroRouteError(Exception)` as the base
    - Add `ServiceUnavailableError`, `NoEligibleModelError(ServiceUnavailableError)`, `PersistenceError`, `ConfigurationError`, `ValidationError`, `NotFoundError`, `ConflictError` — all inheriting from `NeuroRouteError`
    - Each class must include a docstring stating its mapped HTTP status code
    - _Requirements: 3.6, 3.7, 3.9, 5.3, 6.2, 6.3, 6.4_

  - [ ] 1.3 Create SQLAlchemy ORM models for all new tables
    - Create `backend/app/models/model.py` — `Model` table with: `id`, `identifier` (String 128, UNIQUE), `provider_name` (String 128), `model_name` (String 256), `max_context_length` (Integer), `cost_per_input_token` (Numeric 20,10), `cost_per_output_token` (Numeric 20,10), `capability_tier` (Integer, default=1; 1=LOW, 2=MEDIUM, 3=HIGH), `enabled` (Boolean, default=True), `created_at` (DateTime, default=func.now()); include `routing_decisions` relationship
    - Create `backend/app/models/routing_decision.py` — `RoutingDecision` table with: `id`, `request_id` (FK→requests.id), `model_id` (FK→models.id), `policy` (String 50), `complexity_class` (String 20), `estimated_cost` (Numeric 20,10), `explanation` (String 500), `created_at`; include `request`, `model`, `executions` relationships
    - Create `backend/app/models/execution.py` — `Execution` table with: `id`, `routing_decision_id` (FK→routing_decisions.id), `response_text` (Text(4294967295) — LONGTEXT), `input_token_count` (Integer, nullable), `output_token_count` (Integer, nullable), `latency_ms` (Integer, nullable), `estimated_cost` (Numeric 20,10, nullable), `status` (String 20, default="pending"), `error_message` (String 1000, nullable), `is_escalated` (Boolean, default=False), `created_at`; include `routing_decision`, `evaluation` relationships
    - Create `backend/app/models/evaluation.py` — `Evaluation` table with: `id`, `execution_id` (FK→executions.id, UNIQUE), `quality_score` (Float), `confidence` (Float), `escalation_flag` (Boolean, default=False), `created_at`; include `execution` relationship
    - Create `backend/app/models/feedback.py` — `Feedback` table with: `id`, `request_id` (FK→requests.id, UNIQUE), `rating` (Integer), `comment` (String 500, nullable), `created_at`; include `request` relationship
    - All models import `Base` from `backend/app/database/connection.py`
    - _Requirements: 1.8, 3.8, 4.3, 5.2, 6.7_

  - [ ] 1.4 Extend the existing `Request` model and update `create_tables.py`
    - Modify `backend/app/models/request.py`: add `complexity_class: Mapped[str | None]` (String 20, nullable), `end_to_end_latency_ms: Mapped[int | None]` (Integer, nullable), `created_at: Mapped[datetime]` (DateTime, default=func.now()), `routing_decisions` (relationship list), `feedback` (relationship, uselist=False)
    - Update `backend/testing/create_tables.py` to import all five new model files (`model`, `routing_decision`, `execution`, `evaluation`, `feedback`) before calling `Base.metadata.create_all()`
    - Run `create_tables.py` to verify all six tables are created in MySQL without errors
    - _Requirements: 1.8, 8.1, 8.5_

  - [ ] 1.5 Register custom exception handlers in `backend/app/main.py`
    - Import all custom exception classes from `app.exceptions`
    - Add one `@app.exception_handler` per class: `NotFoundError→404`, `ConflictError→409`, `ValidationError→422`, `ServiceUnavailableError→503`, `NoEligibleModelError→503`, `PersistenceError→500`, `ConfigurationError→500`
    - Each handler returns `JSONResponse({"detail": str(exc)})` with the appropriate status code
    - Do NOT alter existing router registrations, CORS middleware, or the health check endpoint
    - _Requirements: 3.6, 3.7, 3.9, 6.2, 6.3_

  - [ ] 1.6 Scaffold the `backend/tests/` directory and shared pytest fixtures
    - Create `backend/tests/conftest.py` with: an in-memory SQLite engine fixture (`engine`), a test DB session fixture (`db_session`) that creates all tables and tears down after each test, and a `test_client` fixture using FastAPI's `TestClient` with the `db_session` dependency overridden
    - Create `backend/pytest.ini` (or add `[tool.pytest.ini_options]` to `pyproject.toml`) with `asyncio_mode = "auto"` for pytest-asyncio
    - Create `backend/tests/__init__.py` and empty `__init__.py` files in `tests/test_models/`, `tests/test_intelligence/`, `tests/test_routing/`, `tests/test_adapters/`, `tests/test_evaluation/`, `tests/test_feedback/`, `tests/test_pipeline/`
    - _Requirements: 2.8, 3.5, 4.5_

  - [ ] 1.7 Phase 1 Checkpoint — verify foundation is solid
    - Run `python backend/testing/create_tables.py` and confirm all six tables exist in MySQL with correct columns
    - Run `pytest backend/tests/ -q` and confirm zero test failures (only collection, no tests yet)
    - Manually call `POST /api/requests/` via Swagger UI at `http://127.0.0.1:8000/docs` and confirm it still returns `{id, prompt, status}` unchanged
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 2. Phase 2: Model Registry
  - [ ] 2.1 Create Pydantic schemas for the Model Registry
    - Create `backend/app/schemas/models.py`
    - `ModelCreate`: `identifier` (str, max_length=128), `provider_name` (str, max_length=128), `model_name` (str, max_length=256), `max_context_length` (int, gt=0), `cost_per_input_token` (Decimal, ge=0), `cost_per_output_token` (Decimal, ge=0), `capability_tier` (int, ge=1, le=3, default=1), `enabled` (bool, default=True)
    - `ModelResponse`: all fields plus `id` (int) and `created_at` (datetime); `ConfigDict(from_attributes=True)`
    - _Requirements: 1.1, 1.5_

  - [ ] 2.2 Create the Model Registry router and register it in `main.py`
    - Create `backend/app/routers/models.py` with `APIRouter(prefix="/api/models", tags=["Models"])`
    - `GET /` — query all `Model` records ordered by `provider_name` asc, `model_name` asc; return `list[ModelResponse]`
    - `POST /` — insert new `Model`; if `identifier` already exists raise `ConflictError` with message `"Model with identifier '{identifier}' already exists"` and `field="identifier"`; return `ModelResponse` with status 201
    - Add `from app.routers.models import router as models_router` and `app.include_router(models_router)` in `main.py` without touching any existing code
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ] 2.3 Write tests for the Model Registry
    - Create `backend/tests/test_models/test_registry.py`
    - Unit tests: POST creates a model and returns HTTP 201 with all fields; GET returns models ordered by provider_name then model_name; duplicate identifier returns HTTP 409; missing required field returns HTTP 422; disabled model still appears in GET response
    - PBT (Hypothesis, max_examples=100):
      - **Property 1: Model Registry Round-Trip** — for any valid `ModelCreate` dict, POST then GET by identifier returns identical field values; **Validates: Requirements 1.1, 1.3**
      - **Property 2: Model List Ordering** — for any set of models with varying provider/model names, GET returns them sorted ascending by provider_name then model_name; **Validates: Requirements 1.2**
      - **Property 3: Disabled Models Excluded from Routing** — for any mix of enabled/disabled models queried by the routing helper, only enabled=True models are returned; **Validates: Requirements 1.7, 3.3, 3.4**
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7_

  - [ ]* 2.4 Run Model Registry property tests
    - Execute `pytest backend/tests/test_models/ -v --tb=short`
    - **Property 1: Model Registry Round-Trip** — **Validates: Requirements 1.1, 1.3**
    - **Property 2: Model List Ordering** — **Validates: Requirements 1.2**
    - **Property 3: Disabled Models Excluded from Routing** — **Validates: Requirements 1.7**

  - [ ] 2.5 Phase 2 Checkpoint — verify Model Registry endpoints
    - Use Swagger UI to POST two models with different providers and verify GET returns them in correct order
    - Verify POST with a duplicate identifier returns HTTP 409
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Phase 3: Provider Adapters
  - [ ] 3.1 Create the abstract `ProviderAdapter` interface
    - Create `backend/app/adapters/__init__.py`
    - Create `backend/app/adapters/base.py` with:
      - `@dataclass ExecutionResult`: `response_text: str`, `input_token_count: int`, `output_token_count: int`, `latency_ms: int`, `estimated_cost: Decimal`, `status: str` (`"completed"` | `"failed"` | `"timed_out"`), `error_message: str | None`
      - `class ProviderAdapter(ABC)` with `@abstractmethod async def dispatch(self, prompt: str, model_name: str) -> ExecutionResult`
    - _Requirements: 4.1_

  - [ ] 3.2 Create `OpenAIAdapter`
    - Create `backend/app/adapters/openai_adapter.py`
    - `OpenAIAdapter(ProviderAdapter)`:
      - `__init__`: reads `OPENAI_API_KEY` from env; raises `ConfigurationError("OPENAI_API_KEY is not set")` if absent or empty; never stores the raw key in an instance variable named such that it would appear in `repr()`
      - `async dispatch(prompt, model_name) -> ExecutionResult`:
        - Uses `httpx.AsyncClient(timeout=30.0)` to call the OpenAI chat completions endpoint
        - Truncates `response_text` to 1,000,000 characters
        - Calculates `estimated_cost` as `(input_tokens × cost_per_input_token) + (output_tokens × cost_per_output_token)` rounded to 10 decimal places — pricing values passed in from the caller (model record)
        - Returns `ExecutionResult(status="failed", error_message=...)` on non-2xx; `status="timed_out"` on `httpx.TimeoutException`
        - Never propagates unhandled exceptions; never includes the API key substring in any error message or log
    - _Requirements: 4.1, 4.2, 4.4, 4.6, 4.7, 4.9, 4.10_

  - [ ] 3.3 Create `OllamaAdapter`
    - Create `backend/app/adapters/ollama_adapter.py`
    - `OllamaAdapter(ProviderAdapter)`:
      - `__init__`: reads `OLLAMA_BASE_URL` from env; raises `ConfigurationError("OLLAMA_BASE_URL is not set")` if absent or empty
      - `async dispatch(prompt, model_name) -> ExecutionResult`:
        - Uses `httpx.AsyncClient(timeout=30.0)` to POST to `{OLLAMA_BASE_URL}/api/generate`
        - Truncates `response_text` to 1,000,000 characters
        - Calculates `estimated_cost` using same formula as OpenAI adapter
        - Returns `ExecutionResult(status="failed")` on non-2xx; `status="timed_out"` on `httpx.TimeoutException`
        - Never propagates unhandled exceptions
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 4.9_

  - [ ] 3.4 Write tests for provider adapters
    - Create `backend/tests/test_adapters/test_base.py` — verify `ProviderAdapter` cannot be instantiated directly; verify `ExecutionResult` fields are accessible by name
    - Create `backend/tests/test_adapters/test_openai_adapter.py` — use `httpx` mock (`respx` or `unittest.mock`) for all HTTP calls:
      - Missing `OPENAI_API_KEY` raises `ConfigurationError`
      - Happy path returns `ExecutionResult(status="completed")` with correct fields
      - Non-2xx response returns `status="failed"` without raising
      - Simulated timeout returns `status="timed_out"` without raising
      - **Property 9: Cost Calculation Invariant** — for any token counts and pricing, `estimated_cost == (input × cost_in) + (output × cost_out)` rounded to 10dp; **Validates: Requirements 4.2**
      - **Property 10: Execution Latency Non-Negativity** — for any dispatch result, `latency_ms >= 0`; **Validates: Requirements 4.2**
      - **Property 11: Error Containment** — for any provider error or timeout, result is an `ExecutionResult` not a raised exception; **Validates: Requirements 4.6, 4.7, 4.9**
      - **Property 12: No API Key Exposure** — for any error condition, the `OPENAI_API_KEY` value does not appear as a substring in `error_message` or response fields; **Validates: Requirements 4.10**
    - Create `backend/tests/test_adapters/test_ollama_adapter.py` — mirror structure of OpenAI tests; Properties 9, 10, 11 apply
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.9, 4.10_

  - [ ]* 3.5 Run provider adapter property tests
    - Execute `pytest backend/tests/test_adapters/ -v --tb=short`
    - **Property 9: Cost Calculation Invariant** — **Validates: Requirements 4.2**
    - **Property 10: Execution Latency Non-Negativity** — **Validates: Requirements 4.2**
    - **Property 11: Error Containment** — **Validates: Requirements 4.6, 4.7, 4.9**
    - **Property 12: No API Key Exposure** — **Validates: Requirements 4.10**

  - [ ] 3.6 Phase 3 Checkpoint — verify adapter behaviour with missing env vars
    - In a Python shell, instantiate `OpenAIAdapter()` with `OPENAI_API_KEY` unset and confirm `ConfigurationError` is raised
    - Instantiate `OllamaAdapter()` with `OLLAMA_BASE_URL` unset and confirm `ConfigurationError` is raised
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Phase 4: Query Intelligence
  - [ ] 4.1 Create the Intelligence Service tokeniser module
    - Create `backend/app/intelligence/__init__.py`
    - Create `backend/app/intelligence/complexity.py` with:
      - `tokenise(text: str) -> list[str]` — split on whitespace and punctuation using `re.split(r"[\s\W]+", text)`, filter empty strings
      - `count_tokens(text: str) -> int` — returns `len(tokenise(text))`
    - _Requirements: 2.2_

  - [ ] 4.2 Create the Intelligence Service classifier module
    - Create `backend/app/intelligence/classifier.py`:
      - `ComplexityClass = Literal["simple", "moderate", "complex"]`
      - `ClassificationResult(BaseModel)`: `complexity_class: ComplexityClass`, `explanation: str` (min_length=10, max_length=300)
      - `DOMAIN_KEYWORDS: frozenset[str]` — at least 30 terms covering medical (diagnosis, prognosis, etiology, …), legal (tort, habeas corpus, jurisdiction, …), financial (amortisation, derivatives, arbitrage, …), scientific (photosynthesis, quantum, thermodynamics, …), and engineering (impedance, tensile, torque, …) domains
      - `REASONING_CONNECTIVES: frozenset[str]` — {"first", "then", "therefore", "because", "however", "additionally", "finally", "consequently", "furthermore", "although", "whereas"}
      - `classify_prompt(prompt: str) -> ClassificationResult`:
        - Raises `ValueError("Prompt must not be empty")` if prompt is empty after stripping
        - Rule order: **complex** if token_count ≥ 50 AND (≥2 domain keywords OR ≥3 reasoning connectives OR prompt contains "source" or "research" with multiple distinct topics); **moderate** if token_count < 50 AND has domain keywords, OR token_count ≥ 50 AND has ≥2 reasoning connectives; **simple** otherwise
        - Returns `ClassificationResult` with a human-readable explanation (10–300 chars)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ] 4.3 Write tests for the Intelligence Service
    - Create `backend/tests/test_intelligence/test_tokeniser.py`:
      - Empty string returns empty list
      - Punctuation-only string returns empty list
      - "Hello, world!" returns ["Hello", "world"]
      - Whitespace normalisation is consistent
    - Create `backend/tests/test_intelligence/test_classifier.py`:
      - Unit: "What is 2+2?" → `simple`; a 3-step medical prompt → `complex`; a 2-step coding prompt with domain terms → `moderate`; empty prompt raises `ValueError`; prompt > 1000 tokens raises `ValueError`
      - PBT (Hypothesis, max_examples=100):
        - **Property 4: Classification Returns Valid Output** — for any non-empty prompt ≤ 1000 tokens, result is one of `{"simple","moderate","complex"}` and explanation length is in [10, 300]; **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
        - **Property 5: Classification Idempotence** — for any valid prompt, `classify_prompt(p) == classify_prompt(p)` both times without config change; **Validates: Requirements 2.1**
        - Mutual exclusivity: exactly one of the three classes is returned per call
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 4.4 Run Intelligence Service property tests
    - Execute `pytest backend/tests/test_intelligence/ -v --tb=short`
    - **Property 4: Classification Returns Valid Output** — **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
    - **Property 5: Classification Idempotence** — **Validates: Requirements 2.1**

  - [ ] 4.5 Phase 4 Checkpoint — verify classifier produces expected outputs
    - In a Python shell: `classify_prompt("What is 2+2?")` → `simple`; a medical diagnosis multi-step prompt → `complex`
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Phase 5: Routing Engine
  - [ ] 5.1 Create routing strategies module
    - Create `backend/app/routing/__init__.py`
    - Create `backend/app/routing/strategies.py`:
      - `RoutingPolicy(str, Enum)`: `COST_OPTIMISED = "cost_optimised"`, `QUALITY_OPTIMISED = "quality_optimised"`, `BASELINE = "baseline"`
      - `select_cost_optimised(models: list[Model], complexity: ComplexityClass) -> Model` — filter to enabled models; pick lowest `(prompt_token_count × cost_per_input_token) + (average_output_tokens × cost_per_output_token)` estimate; tie-break: lexicographically first `identifier`; raise `NoEligibleModelError` if list is empty after filtering
      - `select_quality_optimised(models: list[Model], complexity: ComplexityClass) -> Model` — filter to enabled models whose `capability_tier >= complexity_rank` (1 for simple, 2 for moderate, 3 for complex); pick highest `max_context_length`; tie-break: lexicographically first `identifier`; raise `NoEligibleModelError` if none eligible
      - `select_baseline(models: list[Model], baseline_model_id: str) -> Model` — find model by `identifier == baseline_model_id` and `enabled == True`; raise `NoEligibleModelError("Baseline model unavailable")` if not found or disabled
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 5.2 Create the Routing Engine orchestrator
    - Create `backend/app/routing/router.py`:
      - `class RoutingResult(BaseModel)`: `model_id: str`, `model_db_id: int`, `policy: RoutingPolicy`, `explanation: str` (max 500 chars), `estimated_cost: Decimal`
      - `def route_request(request_id: int, complexity: ComplexityClass, db: Session) -> RoutingResult`:
        1. Read `ROUTING_POLICY` env var (default `"cost_optimised"`); if `"baseline"` read `BASELINE_MODEL_ID`
        2. Query `db` for all `Model` records
        3. Call the appropriate strategy function
        4. Build an explanation string (≤500 chars) describing the selection rationale
        5. Persist a `RoutingDecision` record; wrap DB errors in `PersistenceError`
        6. Return `RoutingResult`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ] 5.3 Create Pydantic schemas for routing
    - Create `backend/app/schemas/routing.py`
    - `RoutingDecisionResponse`: `id`, `request_id`, `model_id`, `policy`, `complexity_class`, `estimated_cost`, `explanation`, `created_at`; `ConfigDict(from_attributes=True)`
    - _Requirements: 3.8_

  - [ ] 5.4 Write tests for the Routing Engine
    - Create `backend/tests/test_routing/test_strategies.py`:
      - `select_cost_optimised` with single enabled model → selects it
      - `select_cost_optimised` with two models at equal cost → selects lexicographically first identifier
      - `select_cost_optimised` with all disabled models → raises `NoEligibleModelError`
      - `select_quality_optimised` selects highest context_length model with matching capability_tier
      - `select_baseline` with correct id and enabled=True → selects it; with disabled → raises `NoEligibleModelError`
      - **Property 3: Disabled Models Excluded from Routing** (PBT) — **Validates: Requirements 1.7, 3.3, 3.4**
      - **Property 6: Cost-Optimised Selection Minimises Cost** (PBT, max_examples=100) — for any non-empty list of models, selected model's estimated cost ≤ all other eligible models; **Validates: Requirements 3.3**
      - **Property 8: Baseline Router Determinism** (PBT) — two calls with same BASELINE_MODEL_ID and same model list always select same model; **Validates: Requirements 3.5**
    - Create `backend/tests/test_routing/test_router.py`:
      - `route_request` persists a `RoutingDecision` record with correct fields
      - DB write failure raises `PersistenceError`
      - `ROUTING_POLICY` env var is respected
      - **Property 7: Routing Decision Round-Trip** (PBT) — after `route_request`, retrieve `RoutingDecision` by request_id and confirm `model_id` matches returned result; **Validates: Requirements 3.8**
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 5.5 Run Routing Engine property tests
    - Execute `pytest backend/tests/test_routing/ -v --tb=short`
    - **Property 3: Disabled Models Excluded from Routing** — **Validates: Requirements 1.7, 3.3, 3.4**
    - **Property 6: Cost-Optimised Selection Minimises Cost** — **Validates: Requirements 3.3**
    - **Property 7: Routing Decision Round-Trip** — **Validates: Requirements 3.8**
    - **Property 8: Baseline Router Determinism** — **Validates: Requirements 3.5**

  - [ ] 5.6 Phase 5 Checkpoint — verify routing selects the correct model
    - Seed two models (one cheap, one capable) via `POST /api/models/`; call `route_request()` directly in a Python shell with each policy and confirm expected model is selected
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Phase 6: Execution Engine
  - [ ] 6.1 Create the Execution Engine orchestrator
    - Create `backend/app/adapters/engine.py`:
      - `def resolve_adapter(provider_name: str) -> ProviderAdapter` — maps `"openai"` → `OpenAIAdapter()`, `"ollama"` → `OllamaAdapter()`; raises `ConfigurationError` for unknown providers
      - `async def execute_request(routing_decision_id: int, prompt: str, model: Model, db: Session) -> Execution`:
        1. Record start time with `time.monotonic()`
        2. Resolve adapter via `resolve_adapter(model.provider_name)`
        3. `await adapter.dispatch(prompt, model.model_name)` with the model's pricing passed in
        4. On success: create and persist `Execution(status="completed", latency_ms=elapsed, …)`
        5. On `ExecutionResult(status="failed"|"timed_out")`: persist accordingly
        6. If `FALLBACK_MODEL_ID` env var is set and primary failed/timed-out: resolve fallback model from DB, retry dispatch, persist a second `Execution` record with `is_escalated=False` (fallback records share `routing_decision_id`)
        7. Return the final `Execution` record (fallback result if fallback succeeded)
        8. Never raise unhandled exceptions — wrap all top-level errors in try/except
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [ ] 6.2 Create Pydantic schemas for executions
    - Create `backend/app/schemas/executions.py`
    - `ExecutionResponse`: `id`, `routing_decision_id`, `response_text`, `input_token_count`, `output_token_count`, `latency_ms`, `estimated_cost`, `status`, `error_message`, `is_escalated`, `created_at`; `ConfigDict(from_attributes=True)`
    - _Requirements: 4.2, 4.3_

  - [ ] 6.3 Write tests for the Execution Engine
    - Create `backend/tests/test_adapters/test_engine.py`:
      - Happy path: mocked adapter returns `status="completed"` → one `Execution` record persisted with correct fields
      - Timeout path: mocked adapter returns `status="timed_out"` → `Execution.status == "timed_out"`, no unhandled exception
      - Provider error: mocked adapter returns `status="failed"` → `Execution.status == "failed"`, no unhandled exception
      - Fallback: primary fails, `FALLBACK_MODEL_ID` set → two `Execution` records created for the same `routing_decision_id`
      - No `FALLBACK_MODEL_ID`: primary fails → single `Execution` record, no retry
      - Missing provider name → `ConfigurationError`, no unhandled exception
      - **Property 11: Error Containment** (PBT) — for any error condition, function returns an `Execution` record rather than raising; **Validates: Requirements 4.6, 4.7, 4.9**
    - _Requirements: 4.2, 4.3, 4.6, 4.7, 4.8, 4.9_

  - [ ]* 6.4 Run Execution Engine property tests
    - Execute `pytest backend/tests/test_adapters/test_engine.py -v --tb=short`
    - **Property 11: Error Containment** — **Validates: Requirements 4.6, 4.7, 4.9**

  - [ ] 6.5 Phase 6 Checkpoint — verify execution with a running Ollama instance
    - Register an Ollama model in the registry; call `execute_request()` directly in a Python shell against a running Ollama instance; confirm `Execution.status == "completed"` and `latency_ms >= 0`
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Phase 7: Quality Evaluation and Escalation
  - [ ] 7.1 Create the Evaluation Service
    - Create `backend/app/evaluation/__init__.py`
    - Create `backend/app/evaluation/evaluator.py`:
      - Validate `ESCALATION_CONFIDENCE_THRESHOLD` env var at module import time: read value, convert to float, assert it is in [0.0, 1.0]; raise `ConfigurationError` with a clear message if absent or out-of-range — this must run before any request is served
      - `class EvaluationResult(BaseModel)`: `quality_score: float` (ge=0.0, le=1.0), `confidence: float` (ge=0.0, le=1.0), `escalation_flag: bool`
      - `def evaluate_execution(execution_record: Execution, threshold: float) -> EvaluationResult`:
        - Heuristic quality score: 0.3 × (min(len(response_text), 500) / 500) + 0.4 × (coherence_score) + 0.3 × (overlap_score); all sub-scores clamped to [0.0, 1.0]
        - Coherence score: count coherence markers (e.g. "therefore", "because", "in summary", "as a result") divided by a ceiling constant; clamped to [0.0, 1.0]
        - Overlap score: Jaccard similarity between prompt token set and response token set; clamped to [0.0, 1.0]
        - Confidence: 0.5 × quality_score + 0.5 × (1.0 if status=="completed" else 0.0)
        - `escalation_flag = (confidence < threshold)`
        - For failed/timed_out executions: quality_score=0.0, confidence=0.0, escalation_flag=True if threshold > 0.0
    - _Requirements: 5.1, 5.3, 5.4_

  - [ ] 7.2 Create the escalation handler
    - Create `backend/app/evaluation/escalation.py`:
      - `async def handle_escalation(original_request: Request, evaluation_record: Evaluation, db: Session) -> Execution | None`:
        1. If `evaluation_record.escalation_flag` is False: return None immediately
        2. Check if the current execution's model has a higher-capability_tier model available in the registry (enabled=True, `capability_tier > current_model.capability_tier`)
        3. If no higher tier: set `evaluation_record.escalation_flag = False`, commit, return None
        4. If higher tier found: select model with next higher capability_tier (tie-break: lowest `id`)
        5. Create a new `RoutingDecision` record pointing to the higher-tier model (policy="quality_optimised", escalation context)
        6. Call `execute_request()` for the escalated execution; set `is_escalated=True` on the resulting `Execution` record
        7. Evaluate the new execution with `escalation_flag` forced to `False` (depth cap)
        8. Compare quality scores: persist the `Evaluation` for the escalated execution; return the `Execution` with the higher `quality_score`
        9. Maximum depth is 1 — enforced by checking `execution_record.is_escalated`; if already escalated, skip and return None
    - _Requirements: 5.4, 5.5, 5.6, 5.7_

  - [ ] 7.3 Create Pydantic schemas for evaluations
    - Create `backend/app/schemas/evaluations.py`
    - `EvaluationResponse`: `id`, `execution_id`, `quality_score`, `confidence`, `escalation_flag`, `created_at`; `ConfigDict(from_attributes=True)`
    - _Requirements: 5.1, 5.2_

  - [ ] 7.4 Write tests for the Evaluation Service
    - Create `backend/tests/test_evaluation/test_evaluator.py`:
      - Unit: `evaluate_execution` with a completed execution produces scores in [0.0, 1.0]
      - Unit: `escalation_flag = True` when confidence < threshold; `= False` when confidence ≥ threshold
      - Unit: failed execution → quality_score=0.0, escalation_flag=True
      - Unit: escalation handler skips when no higher-tier model exists (sets flag to False)
      - Unit: escalation handler skips when `is_escalated=True` on the execution (depth cap)
      - Unit: after escalation, the execution with the higher quality score is returned
      - **Property 13: Evaluation Score Bounds** (PBT, max_examples=100) — for any execution record with any response, quality_score and confidence are in [0.0, 1.0]; **Validates: Requirements 5.1**
      - **Property 14: Escalation Flag Rule** (PBT, max_examples=100) — for any confidence value and threshold, `escalation_flag == (confidence < threshold)`; **Validates: Requirements 5.4**
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 7.5 Run Evaluation Service property tests
    - Execute `pytest backend/tests/test_evaluation/ -v --tb=short`
    - **Property 13: Evaluation Score Bounds** — **Validates: Requirements 5.1**
    - **Property 14: Escalation Flag Rule** — **Validates: Requirements 5.4**

  - [ ] 7.6 Phase 7 Checkpoint — verify evaluation and escalation logic
    - In a Python shell: create a mock `Execution` with `status="completed"` and a short response; call `evaluate_execution()` and confirm scores are in [0.0, 1.0] and `escalation_flag` matches the threshold comparison
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Phase 8: Feedback System
  - [ ] 8.1 Create the Feedback Service
    - Create `backend/app/feedback/__init__.py`
    - Create `backend/app/feedback/service.py`:
      - `def create_feedback(request_id: int, rating: int, comment: str | None, db: Session) -> Feedback`:
        - Raise `NotFoundError` if no `Request` with `request_id` exists
        - Raise `ConflictError` if a `Feedback` record already exists for `request_id`
        - Validate `rating` in [1, 5]; raise `ValidationError` if out of range
        - Validate `comment` ≤ 500 chars if provided; raise `ValidationError` if exceeded
        - Persist and return the new `Feedback` record
      - `def get_feedback(request_id: int, db: Session) -> Feedback` — raise `NotFoundError` if none exists
      - `def get_feedback_summary(db: Session) -> FeedbackSummary` — compute mean_rating (round to 2dp), per-value distribution (keys "1"–"5"), total_count; return zeros/empty distribution if no records
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [ ] 8.2 Create Pydantic schemas for feedback
    - Create `backend/app/schemas/feedback.py`
    - `FeedbackCreate`: `rating` (int, ge=1, le=5), `comment` (str | None, max_length=500)
    - `FeedbackResponse`: `id`, `request_id`, `rating`, `comment`, `created_at`; `ConfigDict(from_attributes=True)`
    - `FeedbackSummary`: `mean_rating` (float), `distribution` (dict[str, int] — keys "1" to "5"), `total_count` (int)
    - _Requirements: 6.7, 6.9_

  - [ ] 8.3 Create the Feedback router and register it in `main.py`
    - Create `backend/app/routers/feedback.py` with `APIRouter(prefix="/api", tags=["Feedback"])`:
      - `POST /requests/{request_id}/feedback` → calls `create_feedback()`; return `FeedbackResponse` with status 201
      - `GET /requests/{request_id}/feedback` → calls `get_feedback()`; return `FeedbackResponse`
      - `GET /metrics/feedback-summary` → calls `get_feedback_summary()`; return `FeedbackSummary`
    - Add `from app.routers.feedback import router as feedback_router` and `app.include_router(feedback_router)` in `main.py` without touching any existing code
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.9_

  - [ ] 8.4 Write tests for the Feedback System
    - Create `backend/tests/test_feedback/test_service.py`:
      - Unit: create feedback for valid request → HTTP 201 with correct fields
      - Unit: create feedback for non-existent request_id → HTTP 404
      - Unit: create duplicate feedback for same request_id → HTTP 409
      - Unit: rating < 1 or > 5 → HTTP 422
      - Unit: comment > 500 chars → HTTP 422
      - Unit: GET feedback for request with no feedback → HTTP 404
      - Unit: feedback summary with zero records → mean_rating=0.0, all distribution counts=0, total_count=0
      - **Property 15: Feedback Rating Bounds** (PBT, max_examples=100) — for any created `Feedback_Record`, rating is in [1, 5]; **Validates: Requirements 6.1, 6.2**
      - **Property 16: Feedback Round-Trip** (PBT, max_examples=100) — for any valid submission, GET returns identical rating and comment; **Validates: Requirements 6.1, 6.7**
      - **Property 17: Feedback Uniqueness** (PBT, max_examples=100) — second POST for same request_id always returns HTTP 409 without altering first record; **Validates: Requirements 6.4**
      - **Property 18: Feedback Summary Correctness** (PBT, max_examples=100) — for any set of N feedback records, mean equals arithmetic mean rounded to 2dp, distribution counts sum to total_count; **Validates: Requirements 6.9**
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [ ]* 8.5 Run Feedback Service property tests
    - Execute `pytest backend/tests/test_feedback/ -v --tb=short`
    - **Property 15: Feedback Rating Bounds** — **Validates: Requirements 6.1, 6.2**
    - **Property 16: Feedback Round-Trip** — **Validates: Requirements 6.1, 6.7**
    - **Property 17: Feedback Uniqueness** — **Validates: Requirements 6.4**
    - **Property 18: Feedback Summary Correctness** — **Validates: Requirements 6.9**

  - [ ] 8.6 Phase 8 Checkpoint — verify Feedback endpoints via Swagger UI
    - Submit feedback via `POST /api/requests/{id}/feedback`, retrieve via `GET /api/requests/{id}/feedback`, check `GET /api/metrics/feedback-summary` reflects the submitted rating
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Phase 9: End-to-End Pipeline Integration
  - [ ] 9.1 Expand Pydantic schemas in `backend/app/schemas/requests.py`
    - Add these new schemas while keeping existing `RequestCreate` and `RequestResponse` intact:
      - `PipelineResponse`: `id`, `prompt`, `status`, `complexity_class`, `routing` (RoutingDecisionResponse), `execution` (ExecutionResponse), `evaluation` (EvaluationResponse | None), `end_to_end_latency_ms`, `step_errors` (list[dict])
      - `DegradedResponse`: `id`, `prompt`, `status`, `message`
      - `RequestSummaryResponse`: `id`, `prompt`, `status`, `complexity_class`, `selected_model_name`, `routing_policy`, `latency_ms`, `estimated_cost`, `quality_score`, `created_at`; `ConfigDict(from_attributes=True)`
      - `RequestDetailResponse`: `id`, `prompt`, `status`, `complexity_class`, `end_to_end_latency_ms`, `created_at`, `routing_decision`, `execution`, `evaluation`, `feedback` (each nullable)
      - `AggregateMetricsResponse`: `total_count`, `mean_latency_ms`, `mean_estimated_cost`, `mean_quality_score`, `adaptive_mean_latency_ms`, `adaptive_mean_cost`, `baseline_mean_latency_ms`, `baseline_mean_cost`
    - _Requirements: 8.2, 8.4, 7.8, 7.9_

  - [ ] 9.2 Implement the pipeline orchestrator in `backend/app/routers/requests.py`
    - **MODIFY** `POST /` to orchestrate the full pipeline following this sequence:
      1. Validate prompt (Pydantic: min_length=1, max_length=1000) → HTTP 422 on failure
      2. Persist `Request(status="pending")` → HTTP 500 on DB failure
      3. Record pipeline start time
      4. Call `classify_prompt(prompt)`:
         - On `ServiceUnavailableError` AND Routing also unavailable → return HTTP 202 `DegradedResponse`
         - On `ServiceUnavailableError` with Routing still available → use `complexity_class="moderate"` (fallback, no 202)
         - On `ValueError` (empty prompt) → already caught by Pydantic
      5. Call `route_request(request.id, complexity, db)`:
         - On `NoEligibleModelError` → HTTP 503
         - On `PersistenceError` → HTTP 500
         - On `ServiceUnavailableError` → return HTTP 202 `DegradedResponse`
      6. `await execute_request(routing_decision.id, prompt, model, db)`:
         - On error: append to `step_errors`, continue to evaluation
      7. Call `evaluate_execution(execution, threshold)`:
         - On `ServiceUnavailableError`: append to `step_errors`, evaluation=None
         - If `escalation_flag=True`: call `handle_escalation()`, use returned execution if better
      8. Update `Request.status = "completed"` (or `"partial"` if step_errors non-empty); set `complexity_class`, `end_to_end_latency_ms`
      9. Return HTTP 200 `PipelineResponse`
    - **MODIFY** `GET /` to return `list[RequestSummaryResponse]` (50 most recent by `created_at` desc), joining to get `selected_model_name` and `routing_policy` from the latest `RoutingDecision`; preserve backward-compatible JSON shape for existing fields
    - **ADD** `GET /{request_id}` returning `RequestDetailResponse` with all linked records (null for unset); raise `NotFoundError` if not found
    - **ADD** `GET /metrics` returning `AggregateMetricsResponse` computed with `func.count()` and `func.avg()` on completed executions; distinguish adaptive vs baseline by `RoutingDecision.policy`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 5.8, 5.9_

  - [ ] 9.3 Write integration and pipeline tests
    - Create `backend/tests/test_pipeline/test_orchestrator.py`:
      - Full pipeline smoke test with mocked adapters: POST valid prompt → HTTP 200 with all required fields populated
      - Mocked Routing unavailable → HTTP 202 with `status="pending"` and degraded message
      - Mocked Intelligence unavailable, Routing available → HTTP 200, complexity_class="moderate" in response
      - Execution failure with Routing/Intelligence available → HTTP 200 with `step_errors` populated and execution status="failed"
      - Evaluation unavailable → HTTP 200, evaluation=None in response, step_errors populated
      - `GET /api/requests/` returns results ordered by `created_at` desc
      - `GET /api/requests/{id}` returns full detail; missing id → HTTP 404
      - **Property 19: Pipeline Latency Composition** (PBT) — for any completed pipeline, `end_to_end_latency_ms >= execution.latency_ms`; **Validates: Requirements 8.5**
      - **Property 20: Pipeline Response Completeness** (PBT) — for any successful pipeline run, response contains all required top-level fields; **Validates: Requirements 8.2**
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 9.4 Run pipeline integration property tests
    - Execute `pytest backend/tests/test_pipeline/ -v --tb=short`
    - **Property 19: Pipeline Latency Composition** — **Validates: Requirements 8.5**
    - **Property 20: Pipeline Response Completeness** — **Validates: Requirements 8.2**

  - [ ] 9.5 Phase 9 Checkpoint — CRITICAL: verify existing behaviour is preserved and pipeline works end-to-end
    - Confirm `POST /api/requests/` still accepts a plain `{"prompt": "..."}` body
    - Confirm `GET /api/requests/` still returns a list of requests
    - Confirm `GET /api/health` still returns `{"status": "healthy", ...}`
    - With a running Ollama instance: submit a real prompt and verify HTTP 200 with routing/execution/evaluation blocks
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Phase 10: Observability Dashboard
  - [ ] 10.1 Extract `PromptForm` and create `ErrorBanner` components
    - Create `frontend/src/components/PromptForm.jsx` — extract the prompt `<input>` and `<button>` from `App.jsx`; accept `onSubmit(prompt)` and `isLoading` props
    - Create `frontend/src/components/ErrorBanner.jsx` — accepts `error: { status, message } | null` prop; displays HTTP status code and plain-language message; renders nothing when error is null
    - _Requirements: 7.6, 7.7_

  - [ ] 10.2 Create request list and detail components
    - Create `frontend/src/components/RequestListItem.jsx` — displays: truncated prompt (100 chars + `…`), `complexity_class`, `selected_model_name`, `estimated_cost` formatted with `toFixed(4)` + " USD", `quality_score` formatted with `toFixed(2)`; calls `onSelect(id)` prop on click
    - Create `frontend/src/components/RequestList.jsx` — accepts `requests[]` and `onSelect` props; renders a list of `RequestListItem`; shows "No requests have been submitted." when list is empty
    - Create `frontend/src/components/RequestDetail.jsx` — accepts `detail: RequestDetailResponse | null` prop; displays full prompt, routing explanation, response text, token counts, latency, estimated cost (4dp), quality score (2dp), confidence (2dp), feedback rating if submitted; renders nothing when detail is null
    - _Requirements: 7.1, 7.2_

  - [ ] 10.3 Create metrics and comparison panel components
    - Create `frontend/src/components/MetricsSummary.jsx` — accepts `metrics: AggregateMetricsResponse | null`; displays: total request count, mean latency (integer), mean estimated cost (4dp USD), mean quality score (2dp); shows "0" / "0.0000" / "0.00" for each metric when metrics is null or all counts are zero
    - Create `frontend/src/components/ComparisonPanel.jsx` — accepts `metrics: AggregateMetricsResponse | null`; displays two columns (Adaptive Routing / Baseline Router) each showing mean latency and mean cost; shows "Insufficient data" for a column when the respective mean is null or absent (fewer than one execution for that mode)
    - _Requirements: 7.3, 7.4_

  - [ ] 10.4 Expand `frontend/src/services/api.js` with all new API functions
    - Replace any hardcoded `"http://localhost:8000"` with `import.meta.env.VITE_API_URL`
    - Update `createRequest(prompt)` to handle both HTTP 200 (`PipelineResponse`) and HTTP 202 (`DegradedResponse`); return `{ status: response.status, data: body }`
    - Update `getRequests()` to map `RequestSummaryResponse[]`
    - Add: `getRequestDetail(id)`, `submitFeedback(requestId, rating, comment)`, `getFeedback(requestId)`, `getAggregateMetrics()`, `getComparisonMetrics()`, `getFeedbackSummary()`
    - All functions throw `new Error(...)` with `{ status, message }` shape on non-OK responses
    - _Requirements: 7.5, 7.6, 7.7, 7.8_

  - [ ] 10.5 Update `frontend/src/App.jsx` to wire all components
    - Add state variables: `selectedId`, `detail`, `metrics`, `comparison`, `lastSubmission`, `error`, `isPartiallyUnavailable`
    - On mount: fetch requests, aggregate metrics, and comparison metrics
    - On new submission: if HTTP 202 → set `isPartiallyUnavailable=true`, display degraded message; if HTTP 200 → set `lastSubmission` with complexity, model name, response text
    - On `selectedId` change: fetch full detail via `getRequestDetail(selectedId)` and store in `detail`
    - After each submission: re-fetch `getRequests()`, `getAggregateMetrics()`, `getComparisonMetrics()`
    - Render all sub-components with correct props; on any API error set `error` state for `ErrorBanner`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8_

  - [ ] 10.6 Configure `VITE_API_URL` environment variable
    - Create `frontend/.env.local` if it does not exist; add `VITE_API_URL=http://localhost:8000`
    - Verify `vite.config.js` does not need changes (Vite loads `.env.local` automatically)
    - _Requirements: 7.6_

  - [ ] 10.7 Phase 10 Checkpoint — verify the full Observability Dashboard
    - Start backend and frontend dev servers; submit a prompt via the UI
    - Confirm the request appears in the list with complexity_class and model name
    - Click the request to open the detail panel; confirm routing explanation and response text are shown
    - Confirm MetricsSummary shows non-zero values after at least one completed request
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Phase 11: Testing, Benchmarking, and Deployment Prep
  - [ ] 11.1 Full integration test with a real Ollama instance
    - Create `backend/tests/test_pipeline/test_integration.py`:
      - Skip (with `pytest.mark.skipif`) if `OLLAMA_BASE_URL` is not set
      - Register an Ollama model via the in-process DB session
      - Call `POST /api/requests/` with a short prompt
      - Assert `Execution.status == "completed"`, `latency_ms >= 0`, `Evaluation.quality_score` in [0.0, 1.0]
      - Assert response body contains `complexity_class`, routing block, execution block
    - _Requirements: 8.1, 8.2, 4.5_

  - [ ] 11.2 Benchmarking: adaptive vs. baseline routing comparison
    - Create `backend/tests/test_pipeline/test_benchmark.py` (skipped unless `RUN_BENCHMARK=true` env var is set):
      - Register two Ollama models with different capability_tiers
      - Submit 10 prompts of varying length under `ROUTING_POLICY=cost_optimised`
      - Re-submit the same 10 prompts under `ROUTING_POLICY=baseline` with `BASELINE_MODEL_ID` set to the capable model
      - Fetch `GET /api/requests/metrics` and assert adaptive mean_estimated_cost ≤ baseline mean_estimated_cost
    - Document results (mean latency and mean cost per mode) in `README.md` under a "Benchmarking Results" section
    - _Requirements: 3.5, 8.5_

  - [ ] 11.3 Full PBT suite run and shrinking documentation
    - Run `pytest backend/tests/ -v --tb=short -k "hypothesis" --hypothesis-seed=0`
    - For any falsifying example found: fix the source code, then add a comment in the test file recording the shrunk counterexample
    - Achieve zero failures across all 20 properties
    - _Requirements: 1.1–8.6 (all)_

  - [ ]* 11.4 Security audit
    - Scan all source files in `backend/app/` and `frontend/src/` to confirm: no API key appears as a string literal; `allow_origins` in `main.py` is `["http://localhost:5173"]` not `["*"]`; `RequestCreate.prompt` has `min_length=1, max_length=1000`; no `text()` raw SQL is called without bound parameters
    - _Requirements: 1.6, 4.10, 7.7_

  - [ ] 11.5 Deployment preparation and documentation
    - Create `backend/requirements.txt` install instructions in `README.md` (if not already present): `cd backend && python -m venv .venv && .venv\Scripts\Activate.ps1 && pip install -r requirements.txt`
    - Document all required `backend/.env` variables: `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`, `ROUTING_POLICY`, `BASELINE_MODEL_ID` (optional), `FALLBACK_MODEL_ID` (optional), `ESCALATION_CONFIDENCE_THRESHOLD`
    - Document `frontend/.env.local` required variable: `VITE_API_URL`
    - Verify `python backend/testing/create_tables.py` creates all six tables cleanly on a fresh `neuroroute` database
    - _Requirements: 1.6, 4.4, 4.5, 5.3_

  - [ ] 11.6 Final Checkpoint — full end-to-end demo run
    - Starting from a fresh database (drop and recreate tables with `create_tables.py`):
      1. Register two models via `POST /api/models/` (one Ollama cheap, one Ollama capable)
      2. Submit 5 prompts of varying complexity via the frontend UI
      3. Confirm each shows correct complexity_class, selected model, and response text in the detail panel
      4. Submit feedback for 3 of the 5 requests
      5. Verify `GET /api/metrics/feedback-summary` reflects the 3 submitted ratings
      6. Verify ComparisonPanel shows adaptive vs. baseline metrics after running both modes
    - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP, but property tests should be run at least once before the final checkpoint
- Each task references specific requirements for traceability
- The existing `POST /api/requests/`, `GET /api/requests/`, and `GET /api/health` endpoints must not be modified until Task 9.2
- `capability_tier` integer mapping: 1 = LOW (simple queries), 2 = MEDIUM (moderate queries), 3 = HIGH (complex queries)
- Use in-memory SQLite for unit and property tests; use the real MySQL `neuroroute` database only for integration tests (Tasks 11.1 and 11.2)
- OpenAI calls incur real per-token costs — use Ollama locally during development and register it with `capability_tier=2` to handle most test prompts without cost
- `ESCALATION_CONFIDENCE_THRESHOLD` is validated at application startup (module import time in `evaluator.py`), not per-request
- `response_text` must use `Text(4294967295)` (LONGTEXT) to support responses up to 1,000,000 characters
- All Hypothesis property tests are tagged with their property number and the requirements clause they validate

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["1.5", "1.6"] },
    { "id": 4, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 5, "tasks": ["2.2", "3.2", "3.3", "4.2", "5.3"] },
    { "id": 6, "tasks": ["2.3", "3.4", "4.3", "5.1"] },
    { "id": 7, "tasks": ["2.4", "3.5", "4.4", "5.2"] },
    { "id": 8, "tasks": ["5.4", "6.2"] },
    { "id": 9, "tasks": ["5.5", "6.1", "7.3"] },
    { "id": 10, "tasks": ["6.3", "7.1"] },
    { "id": 11, "tasks": ["6.4", "7.2"] },
    { "id": 12, "tasks": ["7.4", "8.2"] },
    { "id": 13, "tasks": ["7.5", "8.1"] },
    { "id": 14, "tasks": ["8.3"] },
    { "id": 15, "tasks": ["8.4"] },
    { "id": 16, "tasks": ["8.5", "9.1"] },
    { "id": 17, "tasks": ["9.2"] },
    { "id": 18, "tasks": ["9.3"] },
    { "id": 19, "tasks": ["9.4", "10.1", "10.2", "10.3"] },
    { "id": 20, "tasks": ["10.4"] },
    { "id": 21, "tasks": ["10.5", "10.6"] },
    { "id": 22, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5"] }
  ]
}
```
