# Implementation Plan: NeuroRoute MVP

## Overview

This plan extends the existing React 19 + FastAPI + MySQL stack with six new backend subsystems — Model Registry, Query Intelligence, Routing Engine, Multi-Model Execution, Quality Evaluation, and Feedback — plus an updated Observability Dashboard. The existing `POST /api/requests/`, `GET /api/requests/`, and `GET /api/health` endpoints are preserved unchanged until Phase 9 (Pipeline Integration).

Work follows a strict dependency order: DB models → services → routers → tests. Each phase ends with a checkpoint task that verifies the phase before moving on.

---

## Tasks

- [x] 1. Phase 1: Backend Foundation and Database Migrations
  - [x] 1.1 Create `backend/requirements.txt` with pinned package versions
    - Create `backend/requirements.txt` with the following pinned versions:
      ```
      fastapi==0.162.0
      uvicorn==0.54.0
      sqlalchemy==2.1.6
      pymysql==1.2.3
      python-dotenv==1.2.4
      pydantic==2.14.2
      httpx==0.28.1
      hypothesis==6.170.14
      pytest==9.2.0
      pytest-asyncio==1.4.1.post1
    - This file must exist before any new import is added to source code
    - _Requirements: 4.1, 4.4, 4.5_

  - [x] 1.2 Create `backend/app/exceptions.py` with the full custom exception hierarchy
    - Define `NeuroRouteError(Exception)` as the base
    - Add `ServiceUnavailableError`, `NoEligibleModelError(ServiceUnavailableError)`, `PersistenceError`, `ConfigurationError`, `ValidationError`, `NotFoundError`, `ConflictError` — all inheriting from `NeuroRouteError`
    - Each class must include a docstring stating its mapped HTTP status code
    - _Requirements: 3.6, 3.7, 3.9, 5.3, 6.2, 6.3, 6.4_

  - [x] 1.3 Create SQLAlchemy ORM models for all new tables
    - Create `backend/app/models/model.py` — `Model` table with: `id`, `identifier` (String 128, UNIQUE), `provider_name` (String 128), `model_name` (String 256), `max_context_length` (Integer), `cost_per_input_token` (Numeric 20,10), `cost_per_output_token` (Numeric 20,10), `capability_tier` (Integer, default=1; 1=LOW, 2=MEDIUM, 3=HIGH), `enabled` (Boolean, default=True), `created_at` (DateTime, default=func.now()); include `routing_decisions` relationship
    - Create `backend/app/models/routing_decision.py` — `RoutingDecision` table with: `id`, `request_id` (FK→requests.id), `model_id` (FK→models.id), `policy` (String 50), `complexity_class` (String 20), `estimated_cost` (Numeric 20,10), `explanation` (String 500), `created_at`; include `request`, `model`, `executions` relationships
    - Create `backend/app/models/execution.py` — `Execution` table with: `id`, `routing_decision_id` (FK→routing_decisions.id), `response_text` (Text(4294967295) — LONGTEXT), `input_token_count` (Integer, nullable), `output_token_count` (Integer, nullable), `latency_ms` (Integer, nullable), `estimated_cost` (Numeric 20,10, nullable), `status` (String 20, default="pending"), `error_message` (String 1000, nullable), `is_escalated` (Boolean, default=False), `created_at`; include `routing_decision`, `evaluation` relationships
    - Create `backend/app/models/evaluation.py` — `Evaluation` table with: `id`, `execution_id` (FK→executions.id, UNIQUE), `quality_score` (Float), `confidence` (Float), `escalation_flag` (Boolean, default=False), `created_at`; include `execution` relationship
    - Create `backend/app/models/feedback.py` — `Feedback` table with: `id`, `request_id` (FK→requests.id, UNIQUE), `rating` (Integer), `comment` (String 500, nullable), `created_at`; include `request` relationship
    - All models import `Base` from `backend/app/database/connection.py`
    - _Requirements: 1.8, 3.8, 4.3, 5.2, 6.7_

  - [x] 1.4 Extend the existing `Request` model and update `create_tables.py`
    - Modify `backend/app/models/request.py`: add `complexity_class: Mapped[str | None]` (String 20, nullable), `end_to_end_latency_ms: Mapped[int | None]` (Integer, nullable), `created_at: Mapped[datetime]` (DateTime, `server_default=func.now()`, nullable=False), `routing_decisions` (relationship list), `feedback` (relationship, uselist=False)
    - Update `backend/testing/create_tables.py` to import all five new model files (`model`, `routing_decision`, `execution`, `evaluation`, `feedback`) before calling `Base.metadata.create_all()`
    - Run `python -m testing.create_tables` from `backend/` to verify the five NEW tables (`models`, `routing_decisions`, `executions`, `evaluations`, `feedback`) are created in MySQL without errors. `create_all()` never alters the existing `requests` table; its new columns are added by Task 1.4a
    - _Requirements: 1.8, 8.1, 8.5_

  - [x] 1.4a Controlled `ALTER TABLE` migration for the existing `requests` table
    - Create `backend/testing/migrate_requests_table.py` (and an empty `backend/testing/__init__.py` if needed); run it from `backend/` with `python -m testing.migrate_requests_table` (dry run, the default) or `python -m testing.migrate_requests_table --apply`
    - Pure function `build_migration_statements(existing_columns: set[str]) -> list[str]` returns, in this order, only the statements for columns that are missing:
      - `ALTER TABLE requests ADD COLUMN complexity_class VARCHAR(20) NULL`
      - `ALTER TABLE requests ADD COLUMN end_to_end_latency_ms INT NULL`
      - `ALTER TABLE requests ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP`
    - Statements are static strings executed with `sqlalchemy.text()`; nothing from user input is interpolated. The table name defaults to `requests`; an optional `--table` argument is accepted only if it matches `^[A-Za-z_][A-Za-z0-9_]{0,63}$` (used to rehearse on a scratch copy)
    - Default mode is a dry run: print the row count, the existing columns, and the statements that WOULD run. Execute only when `--apply` is passed
    - Idempotent: existing columns are skipped, so a second run (or a run against a database created by `create_all()`) executes nothing
    - Never issue `DROP`, `TRUNCATE`, `DELETE`, `UPDATE`, or `CREATE TABLE` against `requests`. Legacy rows get NULL `complexity_class` and `end_to_end_latency_ms`, and `created_at` equal to the migration time
    - Before `--apply`, record the row count and a checksum of `(id, prompt, status)`; afterwards assert both are unchanged, all three columns exist, and `created_at` is non-NULL for every legacy row; exit non-zero on any mismatch
    - Take a `mysqldump` backup of `requests` before applying to the live database. Backup files must never be committed (`backups/` and `*.dump` are gitignored)
    - Rehearse on a scratch copy of the table first, then apply to the live `requests` table; drop only the scratch table afterwards
    - Create `backend/tests/test_migration/__init__.py` and `test_migrate_requests_table.py`: unit tests for `build_migration_statements` (all missing -> 3 statements; only `created_at` missing -> 1; none missing -> empty list), a test that no generated statement contains `DROP`, `TRUNCATE`, `DELETE`, or `UPDATE`, and a test that `--table` rejects `requests; DROP TABLE x`. The MySQL apply is verified manually at Checkpoint 1.7 because SQLite cannot add a column with a `CURRENT_TIMESTAMP` default
    - _Requirements: 8.5, 8.6_

  - [x] 1.5 Register custom exception handlers in `backend/app/main.py`
    - Import all custom exception classes from `app.exceptions`
    - Add one `@app.exception_handler` per class: `NotFoundError→404`, `ConflictError→409`, `ValidationError→422`, `ServiceUnavailableError→503`, `NoEligibleModelError→503`, `PersistenceError→500`, `ConfigurationError→500`
    - Each handler returns `JSONResponse({"detail": str(exc)})` with the appropriate status code
    - Do NOT alter existing router registrations, CORS middleware, or the health check endpoint
    - _Requirements: 3.6, 3.7, 3.9, 6.2, 6.3_

  - [x] 1.6 Scaffold the `backend/tests/` directory and shared pytest fixtures
    - Create `backend/tests/conftest.py` with: an in-memory SQLite engine fixture (`engine`), a test DB session fixture (`db_session`) that creates all tables and tears down after each test, and a `test_client` fixture using FastAPI's `TestClient` with the `db_session` dependency overridden
    - Create `backend/pytest.ini` (or add `[tool.pytest.ini_options]` to `pyproject.toml`) with `asyncio_mode = "auto"` for pytest-asyncio
    - Create `backend/tests/__init__.py` and empty `__init__.py` files in `tests/test_models/`, `tests/test_intelligence/`, `tests/test_routing/`, `tests/test_adapters/`, `tests/test_evaluation/`, `tests/test_feedback/`, `tests/test_pipeline/`
    - _Requirements: 2.8, 3.5, 4.5_

  - [x] 1.7 Phase 1 Checkpoint — verify foundation is solid
    - From `backend/`, run `python -m testing.create_tables` and `python -m testing.migrate_requests_table` (dry run); confirm all six tables exist, the dry run reports nothing left to apply, and `requests` has `id, prompt, status, complexity_class, end_to_end_latency_ms, created_at` with the original rows unchanged (same row count and `(id, prompt, status)` checksum)
    - Run `pytest backend/tests/ -q` and confirm zero test failures (only collection, no tests yet)
    - Manually call `POST /api/requests/` via Swagger UI at `http://127.0.0.1:8000/docs` and confirm it still returns `{id, prompt, status}` unchanged
    - Ensure all tests pass, ask the user if questions arise.

- [x] 2. Phase 2: Model Registry
  - [x] 2.1 Create Pydantic schemas for the Model Registry
    - Create `backend/app/schemas/models.py`
    - `ModelCreate`: `identifier` (str, max_length=128), `provider_name` (str, max_length=128), `model_name` (str, max_length=256), `max_context_length` (int, gt=0), `cost_per_input_token` (Decimal, ge=0), `cost_per_output_token` (Decimal, ge=0), `capability_tier` (int, ge=1, le=3, default=1), `enabled` (bool, default=True)
    - `ModelResponse`: all fields plus `id` (int) and `created_at` (datetime); `ConfigDict(from_attributes=True)`
    - _Requirements: 1.1, 1.5_

  - [x] 2.2 Create the Model Registry router and register it in `main.py`
    - Create `backend/app/routers/models.py` with `APIRouter(prefix="/api/models", tags=["Models"])`
    - `GET /` — query all `Model` records ordered by `provider_name` asc, `model_name` asc; return `list[ModelResponse]`
    - `POST /` — insert new `Model`; if `identifier` already exists raise `ConflictError` with message `"Model with identifier '{identifier}' already exists"` and `field="identifier"`; return `ModelResponse` with status 201
    - Add `from app.routers.models import router as models_router` and `app.include_router(models_router)` in `main.py` without touching any existing code
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 2.3 Write tests for the Model Registry
    - Create `backend/tests/test_models/test_registry.py`
    - Unit tests: POST creates a model and returns HTTP 201 with all fields; GET returns models ordered by provider_name then model_name; duplicate identifier returns HTTP 409; missing required field returns HTTP 422; disabled model still appears in GET response
    - PBT (Hypothesis, max_examples=100):
      - **Property 1: Model Registry Round-Trip** — for any valid `ModelCreate` dict, POST then GET by identifier returns identical field values; **Validates: Requirements 1.1, 1.3**
      - **Property 2: Model List Ordering** — for any set of models with varying provider/model names, GET returns them sorted ascending by provider_name then model_name; **Validates: Requirements 1.2**
      - **Property 3: Disabled Models Excluded from Routing** — for any mix of enabled/disabled models queried by the routing helper, only enabled=True models are returned; **Validates: Requirements 1.7, 3.3, 3.4**
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7_

  - [x] 2.4 Run Model Registry property tests
    - Execute `pytest backend/tests/test_models/ -v --tb=short`
    - **Property 1: Model Registry Round-Trip** — **Validates: Requirements 1.1, 1.3**
    - **Property 2: Model List Ordering** — **Validates: Requirements 1.2**
    - **Property 3: Disabled Models Excluded from Routing** — **Validates: Requirements 1.7**

  - [x] 2.5 Phase 2 Checkpoint — verify Model Registry endpoints
    - Use Swagger UI to POST two models with different providers and verify GET returns them in correct order
    - Verify POST with a duplicate identifier returns HTTP 409
    - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 3: Provider Adapters
  - [x] 3.1 Create the abstract `ProviderAdapter` interface
    - Create `backend/app/adapters/__init__.py`
    - Create `backend/app/adapters/base.py` with:
      - `@dataclass ExecutionResult`: `response_text: str`, `input_token_count: int`, `output_token_count: int`, `latency_ms: int`, `estimated_cost: Decimal`, `status: str` (`"completed"` | `"failed"` | `"timed_out"`), `error_message: str | None`
      - `class ProviderAdapter(ABC)` with `@abstractmethod async def dispatch(self, prompt: str, model_name: str) -> ExecutionResult`
    - _Requirements: 4.1_

  - [x] 3.2 Create `GeminiAdapter`
    - Create `backend/app/adapters/gemini_adapter.py`
    - `GeminiAdapter(ProviderAdapter)`:
      - `__init__`: reads `GEMINI_API_KEY` from env; raises `ConfigurationError("GEMINI_API_KEY is not set")` if absent or empty; never stores the raw key in an instance variable named such that it would appear in `repr()`
      - `async dispatch(prompt, model_name) -> ExecutionResult`:
        - Uses `httpx.AsyncClient(timeout=30.0)` to POST `https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent` with body `{"contents": [{"parts": [{"text": prompt}]}]}`
        - Sends the key ONLY in the `x-goog-api-key` header, never as a `?key=` query parameter (httpx errors and logs include the request URL)
        - `response_text` = the text of all parts of `candidates[0].content`
        - `input_token_count` = `usageMetadata.promptTokenCount`; `output_token_count` = `usageMetadata.candidatesTokenCount` + `usageMetadata.thoughtsTokenCount` (a missing field counts as 0; thinking tokens are billed as output)
        - Truncates `response_text` to 1,000,000 characters
        - Calculates `estimated_cost` as `(input_tokens × cost_per_input_token) + (output_tokens × cost_per_output_token)` rounded to 10 decimal places — pricing values passed in from the caller (model record)
        - Returns `ExecutionResult(status="failed", error_message=...)` on non-2xx (including HTTP 429 rate-limit or quota errors) and when the prompt is blocked (`promptFeedback.blockReason` set or no candidates); `status="timed_out"` on `httpx.TimeoutException`
        - Never propagates unhandled exceptions; never includes the API key substring in any error message, log, or request URL
        - The `usageMetadata` field names were checked against the Google `generateContent` reference; confirm the endpoint path and request body against the current Google docs when implementing
    - _Requirements: 4.1, 4.2, 4.4, 4.6, 4.7, 4.9, 4.10_

  - [x] 3.3 Create `OllamaAdapter`
    - Create `backend/app/adapters/ollama_adapter.py`
    - `OllamaAdapter(ProviderAdapter)`:
      - `__init__`: reads `OLLAMA_BASE_URL` from env; raises `ConfigurationError("OLLAMA_BASE_URL is not set")` if absent or empty
      - `async dispatch(prompt, model_name) -> ExecutionResult`:
        - Uses `httpx.AsyncClient(timeout=30.0)` to POST to `{OLLAMA_BASE_URL}/api/generate`
        - Truncates `response_text` to 1,000,000 characters
        - Calculates `estimated_cost` using same formula as Gemini adapter
        - Returns `ExecutionResult(status="failed")` on non-2xx; `status="timed_out"` on `httpx.TimeoutException`
        - Never propagates unhandled exceptions
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 4.9_

  - [x] 3.4 Create `GroqAdapter`
    - Create `backend/app/adapters/groq_adapter.py`
    - Implement `GroqAdapter(ProviderAdapter)` using the existing `httpx` dependency and the verified Groq contract: `POST https://api.groq.com/openai/v1/chat/completions`, `Authorization: Bearer <GROQ_API_KEY>`, and a JSON body containing `model` and a user `messages` entry
    - Read `GROQ_API_KEY` securely from the environment and raise `ConfigurationError` when it is absent or empty; never hardcode, store in a repr-visible field, log, or expose the credential
    - Map `choices[0].message.content`, `usage.prompt_tokens`, and `usage.completion_tokens` into the common `ExecutionResult`
    - Calculate estimated cost from the registered model's input/output pricing, rounded to 10 decimal places; do not hardcode Groq prices
    - Enforce the shared 30-second timeout and 1,000,000-character response truncation
    - Handle HTTP 429 rate limits, other non-2xx responses, timeouts, malformed responses, and unexpected provider failures by returning `ExecutionResult` with the appropriate failed/timed-out status rather than raising unhandled exceptions
    - Preserve the common `ExecutionResult` fields: response text, input/output token counts, latency, estimated cost, status, and error message
    - _Requirements: 4.1, 4.2, 4.6, 4.7, 4.9, 4.10, 4.11_

  - [x] 3.5 Write tests for provider adapters
    - Create `backend/tests/test_adapters/test_base.py` — verify `ProviderAdapter` cannot be instantiated directly; verify `ExecutionResult` fields are accessible by name
    - Create `backend/tests/test_adapters/test_gemini_adapter.py` — use `httpx` mock (`respx` or `unittest.mock`) for all HTTP calls:
      - Missing `GEMINI_API_KEY` raises `ConfigurationError`
      - Happy path returns `ExecutionResult(status="completed")` with correct fields
      - Non-2xx response returns `status="failed"` without raising
      - Simulated timeout returns `status="timed_out"` without raising
      - Token mapping: `input_token_count` equals `promptTokenCount`; `output_token_count` equals `candidatesTokenCount` + `thoughtsTokenCount`, and a missing `thoughtsTokenCount` counts as 0
      - HTTP 429 and a blocked prompt (`promptFeedback.blockReason`, no candidates) return `status="failed"` with a plain-language message
      - The request carries the key only in the `x-goog-api-key` header; the request URL has no `key=` query parameter
      - **Property 9: Cost Calculation Invariant** — for any token counts and pricing, `estimated_cost == (input × cost_in) + (output × cost_out)` rounded to 10dp; **Validates: Requirements 4.2**
      - **Property 10: Execution Latency Non-Negativity** — for any dispatch result, `latency_ms >= 0`; **Validates: Requirements 4.2**
      - **Property 11: Error Containment** — for any provider error or timeout, result is an `ExecutionResult` not a raised exception; **Validates: Requirements 4.6, 4.7, 4.9**
      - **Property 12: No API Key Exposure** — for any error condition, the `GEMINI_API_KEY` value does not appear as a substring in `error_message`, response fields, or the request URL; **Validates: Requirements 4.10**
    - Create `backend/tests/test_adapters/test_ollama_adapter.py` — mirror structure of the Gemini tests; Properties 9, 10, 11 apply
    - Create `backend/tests/test_adapters/test_groq_adapter.py` using mocked HTTP responses:
      - Missing `GROQ_API_KEY` raises `ConfigurationError`
      - Successful response extracts `choices[0].message.content`
      - `usage.prompt_tokens` and `usage.completion_tokens` map correctly
      - Cost uses registered model pricing and is rounded to 10 decimal places
      - HTTP 429, other HTTP errors, timeout, and malformed response return contained failures
      - Response text is truncated to 1,000,000 characters
      - The API key is absent from the request URL, logs, error messages, and response data
      - All failures return `ExecutionResult`, never an unhandled exception
    - Reuse the existing adapter fixtures and shared cost, latency, error-containment, and credential-exposure properties; do not add provider-specific test infrastructure
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.9, 4.10, 4.11_

  - [x]* 3.6 Run provider adapter property tests
    - Execute `pytest backend/tests/test_adapters/ -v --tb=short`
    - **Property 9: Cost Calculation Invariant** — **Validates: Requirements 4.2**
    - **Property 10: Execution Latency Non-Negativity** — **Validates: Requirements 4.2**
    - **Property 11: Error Containment** — **Validates: Requirements 4.6, 4.7, 4.9**
    - **Property 12: No API Key Exposure** — **Validates: Requirements 4.10**

  - [x] 3.7 Phase 3 Checkpoint — verify adapter behaviour with missing env vars
    - In a Python shell, instantiate `GeminiAdapter()` with `GEMINI_API_KEY` unset and confirm `ConfigurationError` is raised
    - Instantiate `OllamaAdapter()` with `OLLAMA_BASE_URL` unset and confirm `ConfigurationError` is raised
    - Instantiate `GroqAdapter()` with `GROQ_API_KEY` unset and confirm `ConfigurationError` is raised
    - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Phase 4: Query Intelligence
  - [x] 4.1 Create the Intelligence Service tokeniser module
    - Create `backend/app/intelligence/__init__.py`
    - Create `backend/app/intelligence/complexity.py` with:
      - `tokenise(text: str) -> list[str]` — split on whitespace and punctuation using `re.split(r"[\s\W]+", text)`, filter empty strings
      - `count_tokens(text: str) -> int` — returns `len(tokenise(text))`
    - _Requirements: 2.2_

  - [x] 4.2 Create the Intelligence Service classifier module
    - Create `backend/app/intelligence/classifier.py`:
      - `ComplexityClass = Literal["simple", "moderate", "complex"]` (tiers: `simple` = LOW, `moderate` = MEDIUM, `complex` = HIGH; the stored and returned labels are unchanged)
      - `ClassificationResult(BaseModel)`: `complexity_class: ComplexityClass`, `explanation: str` (min_length=10, max_length=300)
      - `DOMAIN_KEYWORDS: frozenset[str]` — at least 30 terms covering medical (diagnosis, prognosis, etiology, …), legal (tort, habeas corpus, jurisdiction, …), financial (amortisation, derivatives, arbitrage, …), scientific (photosynthesis, quantum, thermodynamics, …), and engineering (impedance, tensile, torque, …) domains
      - `REASONING_CONNECTIVES: frozenset[str]` — {"first", "then", "therefore", "because", "however", "additionally", "finally", "consequently", "furthermore", "although", "whereas"}
      - `SYNTHESIS_INDICATORS: frozenset[str]` — {"compare", "contrast", "versus", "synthesize", "synthesise", "critique", "evaluate", "literature", "sources", "research", "tradeoffs"}
      - All term lists are matched case-insensitively against the output of `tokenise()`; multi-word entries match consecutive tokens; each distinct entry counts once
      - `classify_prompt(prompt: str) -> ClassificationResult`:
        - Raises `ValueError("Prompt must not be empty")` if the prompt is empty after stripping, and `ValueError("Prompt exceeds the maximum allowed length")` if it has more than 1000 tokens
        - Computes N = token count, D = distinct domain terms found, R = distinct reasoning connectives found, S = distinct synthesis indicators found
        - Applies these rules in order, first match wins (identical to Requirements 2.3-2.5 and design.md):
          1. HIGH / `complex`: R >= 3, OR S >= 2, OR D >= 3, OR N >= 200
          2. LOW / `simple`: N < 50 AND D == 0 AND R < 2 AND S == 0
          3. MEDIUM / `moderate`: every other prompt (the fallback for unclassified prompts)
        - Explanation template: `"Classified as {class} ({tier}): {matched rule}; tokens={N}, domain_terms={D}, reasoning_steps={R}, synthesis_indicators={S}."` (10-300 characters)
        - Pure and deterministic: no randomness, no I/O, no model call
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 4.3 Write tests for the Intelligence Service
    - Create `backend/tests/test_intelligence/test_tokeniser.py`:
      - Empty string returns empty list
      - Punctuation-only string returns empty list
      - "Hello, world!" returns ["Hello", "world"]
      - Whitespace normalisation is consistent
    - Create `backend/tests/test_intelligence/test_classifier.py`:
      - Unit, one test per rule and boundary: "What is 2+2?" → `simple`; 49 plain tokens → `simple`; 50 plain tokens → `moderate` (fallback); 199 plain tokens → `moderate`; 200 plain tokens → `complex`
      - Unit, indicator thresholds: exactly 2 distinct reasoning connectives → `moderate`, exactly 3 → `complex`; exactly 1 domain term → `moderate`, exactly 3 → `complex`; exactly 1 synthesis indicator → `moderate`, exactly 2 → `complex`
      - Unit, counting rules: a repeated term counts once; matching is case-insensitive; a short prompt with 3 distinct reasoning connectives is `complex` regardless of length
      - Unit, errors: empty or whitespace-only prompt raises `ValueError`; 1001 tokens raises `ValueError`, 1000 tokens does not
      - PBT (Hypothesis, max_examples=100):
        - **Property 4: Classification Returns Valid Output** — for any non-empty prompt ≤ 1000 tokens, result is one of `{"simple","moderate","complex"}` and explanation length is in [10, 300]; **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
        - **Property 5: Classification Idempotence** — for any valid prompt, `classify_prompt(p) == classify_prompt(p)` both times without config change; **Validates: Requirements 2.1**
        - Mutual exclusivity and exhaustiveness: exactly one of the three classes is returned per call, and any prompt generated by `short_prompt_strategy()` (under 50 tokens, no listed terms) is `simple`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x]* 4.4 Run Intelligence Service property tests
    - Execute `pytest backend/tests/test_intelligence/ -v --tb=short`
    - **Property 4: Classification Returns Valid Output** — **Validates: Requirements 2.1, 2.3, 2.4, 2.5**
    - **Property 5: Classification Idempotence** — **Validates: Requirements 2.1**

  - [x] 4.5 Phase 4 Checkpoint — verify classifier produces expected outputs
    - In a Python shell: `classify_prompt("What is 2+2?")` → `simple`; a medical diagnosis multi-step prompt → `complex`
    - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 5: Routing Engine
  - [x] 5.1 Create routing strategies module
    - Create `backend/app/routing/__init__.py`
    - Create `backend/app/routing/strategies.py`:
      - `RoutingPolicy(str, Enum)`: `COST_OPTIMISED = "cost_optimised"`, `QUALITY_OPTIMISED = "quality_optimised"`, `BASELINE = "baseline"`
      - `select_cost_optimised(models: list[Model], complexity: ComplexityClass) -> Model` — filter to enabled models; pick lowest `(prompt_token_count × cost_per_input_token) + (average_output_tokens × cost_per_output_token)` estimate; tie-break: lexicographically first `identifier`; raise `NoEligibleModelError` if list is empty after filtering
      - `select_quality_optimised(models: list[Model], complexity: ComplexityClass) -> Model` — filter to enabled models whose `capability_tier >= complexity_rank` (1 for simple, 2 for moderate, 3 for complex); pick highest `max_context_length`; tie-break: lexicographically first `identifier`; raise `NoEligibleModelError` if none eligible
      - `select_baseline(models: list[Model], baseline_model_id: str) -> Model` — find model by `identifier == baseline_model_id` and `enabled == True`; raise `NoEligibleModelError("Baseline model unavailable")` if not found or disabled
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 5.2 Create the Routing Engine orchestrator
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

  - [x] 5.3 Create Pydantic schemas for routing
    - Create `backend/app/schemas/routing.py`
    - `RoutingDecisionResponse`: `id`, `request_id`, `model_id`, `policy`, `complexity_class`, `estimated_cost`, `explanation`, `created_at`; `ConfigDict(from_attributes=True)`
    - _Requirements: 3.8_

  - [x] 5.4 Write tests for the Routing Engine
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

  - [x]* 5.5 Run Routing Engine property tests
    - Execute `pytest backend/tests/test_routing/ -v --tb=short`
    - **Property 3: Disabled Models Excluded from Routing** — **Validates: Requirements 1.7, 3.3, 3.4**
    - **Property 6: Cost-Optimised Selection Minimises Cost** — **Validates: Requirements 3.3**
    - **Property 7: Routing Decision Round-Trip** — **Validates: Requirements 3.8**
    - **Property 8: Baseline Router Determinism** — **Validates: Requirements 3.5**

  - [x] 5.6 Phase 5 Checkpoint — verify routing selects the correct model
    - Seed two models (one cheap, one capable) via `POST /api/models/`; call `route_request()` directly in a Python shell with each policy and confirm expected model is selected
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Phase 6: Execution Engine
  - [ ] 6.1 Create the Execution Engine orchestrator
    - Create `backend/app/adapters/engine.py`:
      - `def resolve_adapter(provider_name: str) -> ProviderAdapter` — maps `"gemini"` → `GeminiAdapter()`, `"ollama"` → `OllamaAdapter()`, `"groq"` → `GroqAdapter()`; raises `ConfigurationError` for unknown providers
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
    - Add these new schemas while keeping `RequestResponse` intact (`RequestCreate` validation is handled by Task 9.1a):
      - `PipelineResponse`: `id`, `prompt`, `status`, `complexity_class`, `routing` (RoutingDecisionResponse), `execution` (ExecutionResponse), `evaluation` (EvaluationResponse | None), `end_to_end_latency_ms`, `step_errors` (list[dict])
      - `DegradedResponse`: `id`, `prompt`, `status`, `message`
      - `RequestSummaryResponse`: `id`, `prompt`, `status`, `complexity_class`, `selected_model_name`, `routing_policy`, `latency_ms`, `estimated_cost`, `quality_score`, `created_at`; `ConfigDict(from_attributes=True)`
      - `RequestDetailResponse`: `id`, `prompt`, `status`, `complexity_class`, `end_to_end_latency_ms`, `created_at`, `routing_decision`, `execution`, `evaluation`, `feedback` (each nullable)
      - `AggregateMetricsResponse`: `total_count`, `mean_latency_ms`, `mean_estimated_cost`, `mean_quality_score`, `adaptive_mean_latency_ms`, `adaptive_mean_cost`, `baseline_mean_latency_ms`, `baseline_mean_cost`
    - _Requirements: 8.2, 8.4, 7.8, 7.9_

  - [] 9.1a Add API-level prompt validation to `RequestCreate`
    - Modify `backend/app/schemas/requests.py`: `RequestCreate.prompt` becomes `str = Field(min_length=1, max_length=1000)` plus a validator that rejects a prompt that is empty after stripping whitespace. The stored prompt stays the original, unmodified text. The 1000 limit is in characters, matching `requests.prompt String(1000)` and `tech.md`
    - Keep `RequestResponse` unchanged; valid requests keep the exact existing request and response shape
    - This is the only change to `RequestCreate`. It must land before Task 9.2 so the pipeline never receives an invalid prompt, and a rejected request must not create a `requests` row
    - Create `backend/tests/test_pipeline/test_prompt_validation.py`: empty prompt -> 422; whitespace-only -> 422; missing `prompt` field -> 422; 1000 characters -> 200; 1001 characters -> 422; none of the 422 cases creates a row; a normal prompt still returns `{id, prompt, status}`
    - PBT (Hypothesis, max_examples=100): any string of 1 to 1000 characters that contains a non-whitespace character is accepted; any string longer than 1000 characters is rejected with 422
    - _Requirements: 8.7_

  - [ ] 9.2 Implement the pipeline orchestrator in `backend/app/routers/requests.py`
    - **MODIFY** `POST /` to orchestrate the full pipeline following this sequence:
      1. Validate prompt (`RequestCreate`, Task 9.1a) → HTTP 422 on failure; nothing is persisted
      2. Persist `Request(status="pending")` → HTTP 500 on DB failure
      3. Record pipeline start time
      4. Call `classify_prompt(prompt)`:
         - On `ServiceUnavailableError` (or any Intelligence failure other than an invalid prompt) → use `complexity_class="moderate"` (MEDIUM fallback), append `{"step": "intelligence", ...}` to `step_errors`, and CONTINUE. Never return 202 for an Intelligence-only failure
         - On `ValueError` (empty or over-length prompt) → HTTP 422 (normally already rejected in step 1)
      5. Call `route_request(request.id, complexity, db)`; catch `NoEligibleModelError` BEFORE `ServiceUnavailableError` because it is a subclass:
         - On `NoEligibleModelError` → HTTP 503
         - On `PersistenceError` → HTTP 500
         - On `ServiceUnavailableError` (Routing Engine unavailable) → leave the request `pending` and return HTTP 202 `DegradedResponse`
      6. `await execute_request(routing_decision.id, prompt, model, db)`:
         - On error: append to `step_errors`, continue to evaluation
      7. Call `evaluate_execution(execution, threshold)` inside a guard:
         - If it fails for any reason after a COMPLETED execution exists → append `{"step": "evaluation", ...}` to `step_errors`, set `evaluation=None`, KEEP the execution record and its response text, and CONTINUE. Do not return 202 and do not set the request to `pending`
         - If `escalation_flag=True`: call `handle_escalation()`, use the returned execution if better
      8. Update `Request.status = "completed"` (or `"partial"` if step_errors non-empty); set `complexity_class`, `end_to_end_latency_ms`
      9. Return HTTP 200 `PipelineResponse` (when `status` is `partial`, `evaluation` may be null and `step_errors` lists the failures)
    - **MODIFY** `GET /` to return `list[RequestSummaryResponse]` (50 most recent, ordered by `created_at` desc then `id` desc), joining to get `selected_model_name` and `routing_policy` from the latest `RoutingDecision`; legacy rows without routing data return null model and quality fields; preserve backward-compatible JSON shape for existing fields
    - **ADD** `GET /{request_id}` returning `RequestDetailResponse` with all linked records (null for unset); raise `NotFoundError` if not found
    - **ADD** `GET /metrics` (full path `GET /api/requests/metrics`) returning `AggregateMetricsResponse` computed with `func.count()` and `func.avg()` on completed executions; distinguish adaptive vs baseline by `RoutingDecision.policy`. Declare this route BEFORE `GET /{request_id}`, otherwise FastAPI treats "metrics" as a request id and returns 422
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 5.8, 5.9_

  - [ ] 9.3 Write integration and pipeline tests
    - Create `backend/tests/test_pipeline/test_orchestrator.py`:
      - Full pipeline smoke test with mocked adapters: POST valid prompt → HTTP 200 with all required fields populated
      - Mocked Routing unavailable → HTTP 202 with `status="pending"` and degraded message
      - Mocked Intelligence unavailable, Routing available → HTTP 200, `complexity_class="moderate"`, an `intelligence` entry in `step_errors`, request status not `pending`, no 202
      - Execution failure with Routing/Intelligence available → HTTP 200 with `step_errors` populated and execution status="failed"
      - Evaluation fails after a completed execution → HTTP 200 (not 202), `evaluation=None`, an `evaluation` entry in `step_errors`, request status `partial` (not `pending`), and the `Execution` row and its `response_text` are preserved and returned
      - `GET /api/requests/` returns results ordered by `created_at` desc then `id` desc (legacy rows that share one timestamp stay newest-first)
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
    - On new submission: if HTTP 202 → set `isPartiallyUnavailable=true`, display degraded message; if HTTP 200 → set `lastSubmission` with complexity, model name, response text; if HTTP 200 with `status` `partial` and `evaluation` null → still show the response text and model name plus the notice "Response generated. Quality evaluation was unavailable for this request." (never the 202 message, never `pending`)
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
    - Document all required `backend/.env` variables: `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`, `GROQ_API_KEY`, `ROUTING_POLICY`, `BASELINE_MODEL_ID` (optional), `FALLBACK_MODEL_ID` (optional), `ESCALATION_CONFIDENCE_THRESHOLD`
    - Document `frontend/.env.local` required variable: `VITE_API_URL`
    - Verify `python -m testing.create_tables` (run from `backend/`) creates all six tables cleanly on a fresh `neuroroute` database, and that `python -m testing.migrate_requests_table` then reports nothing left to apply
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
- The existing `POST /api/requests/`, `GET /api/requests/`, and `GET /api/health` endpoints must not be modified until Task 9.1a (prompt validation only) and Task 9.2
- The existing `requests` table is upgraded only by the controlled migration in Task 1.4a (`ALTER TABLE ... ADD COLUMN`); it is never dropped or recreated and existing rows are preserved
- `capability_tier` integer mapping: 1 = LOW (simple queries), 2 = MEDIUM (moderate queries), 3 = HIGH (complex queries)
- Use in-memory SQLite for unit and property tests; use the real MySQL `neuroroute` database only for integration tests (Tasks 11.1 and 11.2)
- Gemini API calls are free within the free tier's rate limits and billed per token beyond it — use Ollama locally during development and register it with `capability_tier=2` to handle most test prompts without cost
- `ESCALATION_CONFIDENCE_THRESHOLD` is validated at application startup (module import time in `evaluator.py`), not per-request
- `response_text` must use `Text(4294967295)` (LONGTEXT) to support responses up to 1,000,000 characters
- All Hypothesis property tests are tagged with their property number and the requirements clause they validate

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "1.4a"] },
    { "id": 3, "tasks": ["1.5", "1.6"] },
    { "id": 4, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 5, "tasks": ["2.2", "3.2", "3.3", "3.4", "4.2", "5.3"] },
    { "id": 6, "tasks": ["2.3", "3.5", "4.3", "5.1"] },
    { "id": 7, "tasks": ["2.4", "3.6", "4.4", "5.2"] },
    { "id": 8, "tasks": ["3.7", "5.4", "6.2"] },
    { "id": 9, "tasks": ["5.5", "6.1", "7.3"] },
    { "id": 10, "tasks": ["6.3", "7.1"] },
    { "id": 11, "tasks": ["6.4", "7.2"] },
    { "id": 12, "tasks": ["7.4", "8.2"] },
    { "id": 13, "tasks": ["7.5", "8.1"] },
    { "id": 14, "tasks": ["8.3"] },
    { "id": 15, "tasks": ["8.4", "9.1a"] },
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
