# NeuroRoute - Master TODO (Kiroween Hackathon)

> Single source of truth for development status. Audited against the real codebase on **2026-11-07**
> (branch `main`, commit `a96ea7b`, working tree clean). Status was verified by inspection and by running
> checks, not copied from `tasks.md`. See "Verification Log" at the bottom for evidence and for what was NOT verified.

## Project Tracking

| Item | Value |
|---|---|
| **Objective** | Demonstrate a self-optimizing LLM inference router: classify each prompt, route to a model by cost/latency/quality policy, execute via provider adapters, evaluate with a heuristic scorer, allow one-level escalation, collect feedback, and show everything in an observability dashboard. Compare adaptive routing against a fixed-model baseline. |
| **Current phase** | Phase 1 - Project Foundation is complete and verified live (2026-11-07). Phase 2 (Model Registry, Task 2.1) is next but has not been started. |
| **Overall progress** | 26.8% (26 of 97 trackable items verified complete, including pre-existing baseline work) |
| **Spec-task progress** | 9 of 66 `tasks.md` leaf tasks complete |
| **Completed** | 26 |
| **In progress** | 0 |
| **Not started** | 65 |
| **Blocked / needs decision** | 6 |
| **Open spec inconsistencies (section C)** | 9 (tracked separately, not in the counts above) |
| **Next recommended task** | Start Phase 2 at Task 2.1 (needs the user's go-ahead). Open items to settle first or soon: C-08 (ConflictError field) before Task 2.2; C-04 before Task 5.1; C-06 before Task 9.2. |
| **Hackathon window** | Submission period reported as Oct 30 - Dec 4, 2026 (about 27 days left). **UNVERIFIED**: taken from a search snippet; the official 2026 rules page returned HTTP 403. See N-17. |

Counting rule: every line below that starts with `- [ ]`, `- [x]`, `- [~]` or `- [!]` and has a bold ID (other than `C-xx`) is one item.
The percentage is `completed / total`. Optional `tasks.md` tasks (marked `*`) are counted in the total.

## Legend

- `[x]` completed and verified (evidence given)
- `[ ]` not started
- `[~]` in progress
- `[!]` blocked, or needs a decision before work can proceed
- `*` optional in `tasks.md` (property-test run tasks / security audit)
- IDs like `1.2`, `5.1` are the original `tasks.md` IDs. `B-xx` = pre-existing baseline work. `N-xx` = new item found by this audit (not in `tasks.md`). `C-xx` = spec inconsistency or open decision.
- Phase names here differ from `tasks.md` (15 phases vs 11). Original IDs are preserved, so e.g. 1.3/1.4 appear under Phase 2.

## How to Update This File

1. Finish the task, run its tests, and satisfy its "Done when" line. Do not tick it on code-written alone.
2. Change `- [ ]` to `- [x]` and set the `Status:` line to `Done (YYYY-MM-DD) - <evidence>`.
3. When you start a task, use `- [~]` and `Status: In progress`. Keep at most one or two in progress.
4. If something blocks you, use `- [!]` and write the reason and the decision needed in `Status:`.
5. In the same commit, mark the same task completed in Kiro (`tasks.md`) so the two files agree. `tasks.md` currently still shows 1.1 as `[-]`.
6. Recompute the header counts (they are plain numbers). A quick check from the repo root:
   `Select-String -Path TODO.md -Pattern '^- \[x\] \*\*' | Measure-Object`
7. Resolve a `C-xx` item by editing the spec (with your approval), then tick it and unblock the tasks that reference it.

---

## Approved Decisions (2026-11-07)

| Decision | Outcome | Where it landed |
|---|---|---|
| N-02 database migration | Controlled `ALTER TABLE` on the existing `requests` table. No drop or recreate. Existing rows preserved. New columns are nullable or server-defaulted. | New Task **1.4a**; Task 1.4 narrowed; design.md "Migration of the existing `requests` table"; Checkpoint 1.7 |
| C-01 Evaluation failure | Routing unavailable -> `pending` + HTTP 202 (unchanged). Evaluation fails after a completed execution -> response kept, HTTP 200 `partial`, evaluation null, `step_errors` entry, never 202 or `pending`. Intelligence-only failure -> `moderate` fallback and continue. | requirements.md Req 8.4 and 7.8; design.md degraded modes, API, pipeline, 202 section, per-step table; tasks 9.2, 9.3, 10.5 |
| C-02 Classification | One deterministic rule set. HIGH (`complex`) if R>=3 or S>=2 or D>=3 or N>=200. LOW (`simple`) if N<50 and D=0 and R<2 and S=0. MEDIUM (`moderate`) is the fallback for everything else. | requirements.md Glossary and Req 2.2-2.5; design.md classifier; Tasks 4.2 and 4.3 |
| N-05 Prompt validation | HTTP 422 for missing, empty, whitespace-only, or over-1000-character prompts; nothing persisted. | New Task **9.1a**; requirements.md Req 8.7; design.md |
| N-03 Git tracking | `testing/` un-ignored; `backups/` and `*.dump` ignored; venv, caches and env files still ignored. | `.gitignore` (done) |
| N-08 Second Ollama model | Deferred to the benchmarking phase. | Phase 12 |
| Provider change | OpenAI replaced by Google Gemini (Ollama unchanged). Gemini is called over REST with `httpx`; the key is `GEMINI_API_KEY`, sent only in the `x-goog-api-key` header; output tokens include thinking tokens; `openai` dependency removed. | requirements.md Glossary and Req 4.4; design.md adapter section, diagram, examples, Property 12, packages, cost note; tasks.md 1.1, 3.2-3.6, 6.1, 11.5, Notes; steering examples; `backend/requirements.txt` |
## Phase 1 - Project Foundation

- [x] **B-01** GitHub repository - `origin = github.com/Nathish-K/NeuroRoute`
  - Depends on: none
  - Done when: remote exists and local `main` is pushed
  - Status: Done - `origin/main` equals `HEAD` (a96ea7b); 4 commits (2026-11-04 to 2026-11-06)
- [x] **B-02** React 19 + Vite frontend scaffold - `frontend/`
  - Depends on: none
  - Done when: app builds and lints
  - Status: Done - `vite build` succeeded (17 modules); `oxlint` 0 errors, 1 warning (`App.jsx:19` react set-state-in-effect)
- [x] **B-03** FastAPI app with CORS and health check - `backend/app/main.py`
  - Depends on: none
  - Done when: `GET /api/health` returns healthy; CORS allows the Vite origin
  - Status: Done - health 200; `Access-Control-Allow-Origin: http://localhost:5173` returned
- [x] **B-09** Kiro steering files - `.kiro/steering/{product,structure,tech}.md`
  - Depends on: none
  - Done when: files exist and are committed
  - Status: Done - tracked in git
- [x] **B-10** Kiro specs - `.kiro/specs/neuroroute-mvp/{requirements,design,tasks}.md`
  - Depends on: B-09
  - Done when: three documents exist, are committed, and pass format validation
  - Status: Done - tracked; format validation clean. Content problems are listed in section C
- [x] **B-13** Python venv with pinned dependencies installed - `backend/.venv`
  - Depends on: 1.1
  - Done when: all 10 pinned packages import at the pinned versions
  - Status: Done - all 10 pinned packages are installed and `pip install --dry-run -r requirements.txt` reports them satisfied. `openai` is still installed in the venv but is no longer a dependency (provider changed to Gemini); `pip uninstall openai` is optional
- [x] **B-14** Local Ollama available for development - `C:\Users\nathi\AppData\Local\Programs\Ollama`
  - Depends on: none
  - Done when: API reachable and a chat model present
  - Status: Done - API 200 on `localhost:11434`; models: `qwen2.5:3b` (chat), `nomic-embed-text` (embeddings). Only ONE chat model - see N-08
- [x] **B-15** No secrets committed and `.kiro/` is not gitignored
  - Depends on: none
  - Done when: `.env` never appears in history; `.kiro/` is tracked
  - Status: Done - no commit touches `.env`; `git grep` finds only the README placeholder; `.kiro/` not ignored. Re-run before submission (N-09)
- [x] **1.1** Create `backend/requirements.txt` with pinned versions - `backend/requirements.txt`
  - Depends on: none
  - Done when: file exists, 10 packages pinned with `==`, versions match the venv
  - Status: Done - verified. `openai` was removed on 2026-11-07 when the provider changed to Gemini, and the file was re-saved as UTF-8 (N-01). `tasks.md` still shows `[-]`; sync it
- [x] **N-01** Re-save `backend/requirements.txt` as UTF-8 without BOM - `backend/requirements.txt`
  - Depends on: 1.1
  - Done when: first bytes are not `FF FE`; `pip install --dry-run -r requirements.txt` still succeeds; GitHub renders it as text
  - Status: Done (2026-11-07) - rewritten as plain UTF-8 (405 bytes, no BOM, no NUL bytes) while removing `openai`; the dry run reports all 10 pins satisfied and nothing new to install
- [x] **1.2** Create custom exception hierarchy - `backend/app/exceptions.py`
  - Depends on: none
  - Done when: `NeuroRouteError` plus 7 subclasses exist, each docstring names its HTTP status; importable
  - Status: Done (2026-11-07) - NeuroRouteError plus 7 subclasses in app/exceptions.py, each docstring names its HTTP status; tests/test_exceptions.py 26 passed
- [x] **1.5** Register exception handlers - `backend/app/main.py`
  - Depends on: 1.2 (the dependency graph schedules it after 1.4)
  - Done when: each exception maps to its status with `{"detail": ...}`; CORS, routers and health check untouched; a unit test per mapping passes
  - Status: Done (2026-11-07) - 7 handlers registered in main.py (NeuroRouteError itself is not registered); body is {"detail": ...}; tests/test_exception_handlers.py 15 passed. C-08 is still open
- [x] **1.6** Scaffold `backend/tests/` and pytest config - `backend/tests/conftest.py`, `backend/pytest.ini`
  - Depends on: 1.3, 1.4 (fixtures create all tables)
  - Done when: `pytest backend/tests -q` collects without import errors; `asyncio_mode = auto`; in-memory SQLite fixtures work
  - Status: Done (2026-11-07) - backend/tests scaffold with in-memory SQLite fixtures and a guard that blocks the live MySQL session; 109 tests pass from backend/ and from the repo root, twice in a row with the same count; "addopts = -q" removed from pytest.ini so the summary line prints
- [x] **N-04** Add `backend/.env.example` and placeholder env vars - `backend/.env.example`, local `backend/.env`
  - Depends on: none
  - Done when: `.env.example` lists `MYSQL_*`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`, `ROUTING_POLICY`, `BASELINE_MODEL_ID`, `FALLBACK_MODEL_ID`, `ESCALATION_CONFIDENCE_THRESHOLD` with NO real values; it is committable (`!.env.example` is allowed by `.gitignore`)
  - Status: Done (2026-11-07) - backend/.env.example lists every required variable with placeholders only. The checkpoint found a real-looking Gemini key in the file (pasted after creation); it was replaced with the placeholder, never staged or committed, and never recorded here. If that key was real, rotate it in Google AI Studio and put the new one in backend/.env only.

## Phase 2 - Database and ORM

- [x] **B-04** MySQL connection and sessions - `backend/app/database/connection.py`, `dependencies.py`
  - Depends on: none
  - Done when: engine connects; `get_db()` yields and closes sessions
  - Status: Done - `test_db.py` connected to `neuroroute` on MySQL 8.0.44 (needs `PYTHONPATH=.`, see N-03); `pool_pre_ping=True` present
- [x] **B-05** `requests` table and `Request` ORM model - `backend/app/models/request.py`
  - Depends on: B-04
  - Done when: table exists and matches the model
  - Status: Done - live table now has 6 columns (`id, prompt, status, complexity_class, end_to_end_latency_ms, created_at`) and 5 rows after the 2026-11-07 probe; original rows 1-4 unchanged (ids 1-2 `completed`, ids 3-4 `pending`)
- [x] **B-11** Local DB helper scripts exist - `backend/testing/{create_tables,test_db,test_crud}.py`
  - Depends on: B-04
  - Done when: scripts exist and run
  - Status: Done - the scripts work and are now trackable in Git (N-03). Run them from `backend/` as `python -m testing.<script>`; running by path fails with `ModuleNotFoundError: app`. Warning: `test_crud.py` INSERTS a row each time it runs (it created the existing `completed` rows), so do not run it casually
- [x] **1.3** Create ORM models for 5 new tables - `backend/app/models/{model,routing_decision,execution,evaluation,feedback}.py`
  - Depends on: B-04
  - Done when: 5 `Mapped[...]`/`mapped_column()` models inherit `Base`; FKs and unique constraints as in design.md; `execution.response_text` is LONGTEXT (`Text(4294967295)`)
  - Status: Done (2026-11-07) - 5 models in app/models; configure_mappers ok; MySQL DDL compiled offline (LONGTEXT response_text, NUMERIC(20,10) money columns, unique indexes on models.identifier, evaluations.execution_id, feedback.request_id, FKs as designed); tests/test_database passed
- [x] **1.4** Extend `Request` model and update `create_tables.py` - `backend/app/models/request.py`, `backend/testing/create_tables.py`
  - Depends on: 1.3
  - Done when: `Request` has `complexity_class`, `end_to_end_latency_ms`, `created_at` (`server_default=func.now()`) and the relationships; `create_tables.py` imports all new models; `python -m testing.create_tables` creates the 5 new tables
  - Status: Done (2026-11-07) - Request has complexity_class, end_to_end_latency_ms, created_at (NOT NULL DEFAULT (now())); create_tables.py imports all 6 models. create_tables run live 2026-11-07: five empty tables created; requests untouched; second run is a no-op
- [x] **1.4a** Controlled `ALTER TABLE` migration for the existing `requests` table (was N-02) - `backend/testing/migrate_requests_table.py`, `backend/tests/test_migration/`
  - Depends on: 1.3 (can run in parallel with 1.4). Approved decision
  - Done when: dry run lists exactly the 3 `ADD COLUMN` statements; `--apply` adds them without dropping or recreating `requests`; the 4 existing rows keep the same row count and `(id, prompt, status)` checksum; legacy rows have NULL `complexity_class` and `end_to_end_latency_ms` and a filled `created_at`; a second run does nothing; unit tests pass; a `mysqldump` backup was taken and a rehearsal on a scratch table passed first
  - Status: Done (2026-11-07) - applied via `python -m testing.migrate_requests_table --apply` after a verified JSON backup and a scratch-table rehearsal; 3 columns added; fingerprint of the 4 original rows unchanged; a re-run reports "Nothing to apply". NOTE: `mysqldump` is NOT installed, so the backup is the script's JSON backup plus an independent verified JSON copy in `backend/backups/` (a deviation from the spec text that says mysqldump; equivalent protection - please confirm you accept this).
- [x] **N-03** Track `backend/testing/` scripts in Git - `.gitignore`
  - Depends on: none
  - Done when: the three scripts are addable while venv, caches, env files and dumps stay ignored
  - Status: Done (2026-11-07) - removed the blanket `testing/` rule; added `backups/` and `*.dump`. `git add -n backend/testing` lists only `create_tables.py`, `test_crud.py`, `test_db.py`; `.venv`, `__pycache__`, `.env`, `node_modules` and dumps are still ignored. The files are NOT staged or committed yet (your call)
- [x] **1.7** Checkpoint - Phases 1-2 foundation verified - (verification only)
  - Depends on: 1.2, 1.3, 1.4, 1.4a, 1.5, 1.6
  - Done when: all 6 tables exist; `requests` has the 3 new columns with the original 4 rows unchanged; `python -m testing.migrate_requests_table` (dry run) reports nothing left to apply; `pytest backend/tests -q` has no errors; `POST`/`GET /api/requests/` and `/api/health` behave as before
  - Status: Done (2026-11-07) - live checks all PASS: 6 tables exist (5 new ones empty, no ORM/live column drift); requests has the 3 new columns and original rows 1-4 unchanged (fingerprint 0360760e...ebe600); migration re-run reports "Nothing to apply" (exit 0); pytest 109 passed (3 runs, live DB unchanged by tests, no skip/xfail); live health 200, GET 200, POST 200 (probe row id 5), 422 for empty/blank/1001-char/missing prompt, CORS preflight OK. Browser run of the frontend NOT performed

## Phase 3 - Model Registry

- [ ] **2.1** Registry schemas - `backend/app/schemas/models.py`
  - Depends on: 1.3
  - Done when: `ModelCreate` enforces length/range limits; `ModelResponse` uses `from_attributes`; missing-field errors name the field
  - Status: Not started. See C-05 (`capability_tier` missing from Req 1.1)
- [ ] **2.2** Registry router - `backend/app/routers/models.py`, `backend/app/main.py`
  - Depends on: 2.1, 1.5
  - Done when: `GET /api/models/` ordered by provider then model name; `POST` returns 201, 409 on duplicate identifier, 422 on missing fields; disabled models still listed
  - Status: Not started
- [ ] **2.3** Registry tests - `backend/tests/test_models/test_registry.py`
  - Depends on: 2.2, 1.6
  - Done when: unit tests plus Hypothesis Properties 1, 2, 3 (max_examples=100) pass
  - Status: Not started
- [ ] **2.4*** Run Registry property tests - `backend/tests/test_models/`
  - Depends on: 2.3
  - Done when: `pytest backend/tests/test_models -v` is green
  - Status: Not started
- [ ] **2.5** Checkpoint - Registry works via Swagger UI - (verification only)
  - Depends on: 2.2, 2.3
  - Done when: two models created and listed in order; duplicate returns 409
  - Status: Not started

## Phase 4 - Provider Adapters (Gemini and Ollama)

- [ ] **3.1** Adapter interface - `backend/app/adapters/base.py`, `__init__.py`
  - Depends on: 1.2
  - Done when: `ExecutionResult` dataclass and abstract `ProviderAdapter.dispatch()` exist; direct instantiation raises `TypeError`
  - Status: Not started
- [ ] **3.2** Gemini adapter - `backend/app/adapters/gemini_adapter.py`
  - Depends on: 3.1, 1.2
  - Done when: reads `GEMINI_API_KEY`; sends it only in the `x-goog-api-key` header (never in the URL); 30 s timeout; 1,000,000-char truncation; input tokens = `promptTokenCount`, output tokens = `candidatesTokenCount` + `thoughtsTokenCount`; cost = in*price_in + out*price_out to 10 dp; non-2xx (including HTTP 429) and blocked prompts -> `failed`, timeout -> `timed_out`; key never appears in errors, logs or URLs
  - Status: Not started. See C-06 (missing-config handling). Confirm the endpoint path and request body against Google's current docs when implementing
- [ ] **3.3** Ollama adapter - `backend/app/adapters/ollama_adapter.py`
  - Depends on: 3.1, 1.2
  - Done when: reads `OLLAMA_BASE_URL`; POSTs to `/api/generate`; same contract as 3.2
  - Status: Not started. Ollama is already running locally (B-14)
- [ ] **3.4** Adapter tests - `backend/tests/test_adapters/test_{base,gemini_adapter,ollama_adapter}.py`
  - Depends on: 3.1, 3.2, 3.3
  - Done when: unit tests plus Properties 9, 10, 11, 12 pass using mocked HTTP, including the Gemini token mapping (thinking tokens), 429 and blocked-prompt handling, and a check that the key never appears in the request URL
  - Status: Not started. Use `httpx.MockTransport` or `unittest.mock`; `respx` is not in `requirements.txt` (C-10)
- [ ] **3.5*** Run adapter property tests - `backend/tests/test_adapters/`
  - Depends on: 3.4
  - Done when: green
  - Status: Not started
- [ ] **3.6** Checkpoint - adapters reject missing config - (verification only)
  - Depends on: 3.2, 3.3, 3.4
  - Done when: both adapters fail cleanly with env vars unset
  - Status: Not started
## Phase 5 - Query Intelligence

- [ ] **4.1** Tokeniser - `backend/app/intelligence/complexity.py`, `__init__.py`
  - Depends on: none
  - Done when: `tokenise()` splits on whitespace and punctuation, drops empties; `count_tokens()` returns its length
  - Status: Not started
- [ ] **4.2** Classifier - `backend/app/intelligence/classifier.py`
  - Depends on: 4.1
  - Done when: deterministic rules exactly as in Requirements 2.3-2.5: HIGH (`complex`) if R>=3 or S>=2 or D>=3 or N>=200; LOW (`simple`) if N<50 and D=0 and R<2 and S=0; MEDIUM (`moderate`) otherwise; 10-300 char explanation; `ValueError` for empty and for over-1000-token prompts
  - Status: Not started - UNBLOCKED by the C-02 decision
- [ ] **4.3** Intelligence tests - `backend/tests/test_intelligence/test_{tokeniser,classifier}.py`
  - Depends on: 4.1, 4.2
  - Done when: boundary unit tests (N = 49/50/199/200; R = 2/3; D = 1/3; S = 1/2; fallback), counting-rule tests, error tests, plus Properties 4 and 5 pass
  - Status: Not started
- [ ] **4.4*** Run Intelligence property tests - `backend/tests/test_intelligence/`
  - Depends on: 4.3
  - Done when: green
  - Status: Not started
- [ ] **4.5** Checkpoint - classifier outputs sane results - (verification only)
  - Depends on: 4.2, 4.3
  - Done when: "What is 2+2?" -> simple; a multi-step medical prompt -> complex
  - Status: Not started

## Phase 6 - Routing Engine

- [!] **5.1** Routing strategies - `backend/app/routing/strategies.py`, `__init__.py`
  - Depends on: 1.3, 1.2, C-04
  - Done when: `cost_optimised`, `quality_optimised`, `baseline` implemented; lexicographic tie-break; disabled models never chosen; `NoEligibleModelError` when none eligible
  - Status: BLOCKED on C-04 - the cost formula needs prompt-token and expected-output-token inputs that the planned function signature does not receive
- [ ] **5.2** Routing orchestrator - `backend/app/routing/router.py`
  - Depends on: 5.1, 4.2
  - Done when: reads `ROUTING_POLICY` (default `cost_optimised`) and `BASELINE_MODEL_ID`; explanation <= 500 chars; persists `RoutingDecision`; DB failure -> `PersistenceError`
  - Status: Not started
- [ ] **5.3** Routing schema - `backend/app/schemas/routing.py`
  - Depends on: 1.3
  - Done when: `RoutingDecisionResponse` with `from_attributes`
  - Status: Not started
- [ ] **5.4** Routing tests - `backend/tests/test_routing/test_{strategies,router}.py`
  - Depends on: 5.1, 5.2, 5.3
  - Done when: unit tests plus Properties 3, 6, 7, 8 pass
  - Status: Not started
- [ ] **5.5*** Run Routing property tests - `backend/tests/test_routing/`
  - Depends on: 5.4
  - Done when: green
  - Status: Not started
- [ ] **5.6** Checkpoint - each policy picks the expected model - (verification only)
  - Depends on: 5.2, 5.4
  - Done when: two seeded models routed correctly under each policy
  - Status: Not started

## Phase 7 - Execution Engine

- [ ] **6.1** Execution orchestrator with fallback - `backend/app/adapters/engine.py`
  - Depends on: 3.1, 3.2, 3.3, 1.3, 5.2
  - Done when: persists `completed`/`failed`/`timed_out` executions; with `FALLBACK_MODEL_ID` a failed primary yields two execution rows; never raises
  - Status: Not started. See C-06 (missing-config handling)
- [ ] **6.2** Execution schema - `backend/app/schemas/executions.py`
  - Depends on: 1.3
  - Done when: `ExecutionResponse` with `from_attributes`
  - Status: Not started
- [ ] **6.3** Execution tests - `backend/tests/test_adapters/test_engine.py`
  - Depends on: 6.1, 6.2
  - Done when: happy, timeout, error, fallback, no-fallback cases plus Property 11 pass
  - Status: Not started
- [ ] **6.4*** Run Execution property tests - `backend/tests/test_adapters/test_engine.py`
  - Depends on: 6.3
  - Done when: green
  - Status: Not started
- [ ] **6.5** Checkpoint - real call to local Ollama - (verification only)
  - Depends on: 6.1, 3.3, B-14
  - Done when: `execute_request()` returns a `completed` execution against `qwen2.5:3b` with `latency_ms >= 0`
  - Status: Not started

## Phase 8 - Evaluation and Escalation

- [ ] **7.1** Heuristic evaluator - `backend/app/evaluation/evaluator.py`, `__init__.py`
  - Depends on: 1.3, 1.2, N-04
  - Done when: score and confidence in [0.0, 1.0]; `escalation_flag == confidence < threshold`; `ESCALATION_CONFIDENCE_THRESHOLD` validated at startup (absent or out of range -> startup error)
  - Status: Not started
- [ ] **7.2** One-level escalation - `backend/app/evaluation/escalation.py`
  - Depends on: 7.1, 5.2, 6.1
  - Done when: re-routes to the next higher `capability_tier`; max depth 1; keeps the response with the higher score; no higher tier -> flag cleared, original returned
  - Status: Not started
- [ ] **7.3** Evaluation schema - `backend/app/schemas/evaluations.py`
  - Depends on: 1.3
  - Done when: `EvaluationResponse` with `from_attributes`
  - Status: Not started
- [ ] **7.4** Evaluation tests - `backend/tests/test_evaluation/test_evaluator.py`
  - Depends on: 7.1, 7.2, 7.3
  - Done when: unit tests plus Properties 13 and 14 pass
  - Status: Not started
- [ ] **7.5*** Run Evaluation property tests - `backend/tests/test_evaluation/`
  - Depends on: 7.4
  - Done when: green
  - Status: Not started
- [ ] **N-06** Document that confidence is a heuristic, not a correctness proof - evaluator docstring, `EvaluationResponse` field descriptions
  - Depends on: 7.1, 7.3
  - Done when: docstring and OpenAPI field text say scores are heuristic estimates of response quality and do not verify factual correctness
  - Status: Not started. Implements your constraint about not overclaiming
- [ ] **7.6** Checkpoint - evaluation and escalation logic - (verification only)
  - Depends on: 7.1, 7.2, 7.4
  - Done when: mock execution yields in-range scores and the correct escalation flag
  - Status: Not started

## Phase 9 - Feedback System

- [ ] **8.1** Feedback service - `backend/app/feedback/service.py`, `__init__.py`
  - Depends on: 1.3, 1.2
  - Done when: create (404 unknown request, 409 duplicate, rating 1-5, comment <= 500), get, and global summary (mean 2 dp, distribution 1-5, total)
  - Status: Not started. Requirement 6.7 no longer names a file; `optimizer.py` is not required
- [ ] **8.2** Feedback schemas - `backend/app/schemas/feedback.py`
  - Depends on: 1.3
  - Done when: `FeedbackCreate`, `FeedbackResponse`, `FeedbackSummary` as in design.md
  - Status: Not started
- [ ] **8.3** Feedback router - `backend/app/routers/feedback.py`, `backend/app/main.py`
  - Depends on: 8.1, 8.2, 1.5
  - Done when: `POST`/`GET /api/requests/{id}/feedback` and `GET /api/metrics/feedback-summary` work with the documented status codes
  - Status: Not started
- [ ] **8.4** Feedback tests - `backend/tests/test_feedback/test_service.py`
  - Depends on: 8.1, 8.2, 8.3
  - Done when: unit tests plus Properties 15, 16, 17, 18 pass
  - Status: Not started
- [ ] **8.5*** Run Feedback property tests - `backend/tests/test_feedback/`
  - Depends on: 8.4
  - Done when: green
  - Status: Not started
- [ ] **8.6** Checkpoint - feedback endpoints via Swagger UI - (verification only)
  - Depends on: 8.3, 8.4
  - Done when: submit, retrieve and summary reflect a stored rating
  - Status: Not started
## Phase 10 - Pipeline Integration

The first task that is allowed to change the existing endpoints is 9.2. Until then keep B-06 and B-07 intact.

- [x] **B-06** `GET /api/requests/` - `backend/app/routers/requests.py`
  - Depends on: B-05
  - Done when: returns saved requests newest first
  - Status: Done - live call returned 200 with 4 rows; re-verified live on 2026-11-07 after the migration (4 rows, then 5 rows after the probe, newest first)
- [x] **B-07** `POST /api/requests/` - `backend/app/routers/requests.py`
  - Depends on: B-05
  - Done when: saves a prompt as `pending` and returns `{id, prompt, status}`
  - Status: Done - verified against an in-memory SQLite override (200, `{'id':1,'prompt':...,'status':'pending'}`). Verified live on 2026-11-07 (probe row id 5 exists, status pending). Earlier gap, now closed by 9.1a: empty and 1500-char prompts are also accepted (200), which `tech.md` forbids - see 9.1a
- [x] **9.1a** Add API-level prompt validation to `RequestCreate` (was N-05) - `backend/app/schemas/requests.py`, `backend/tests/test_pipeline/test_prompt_validation.py`
  - Depends on: 1.4, 1.6. Approved decision. Lands before 9.1 and 9.2 (same file; the pipeline must never see an invalid prompt)
  - Done when: missing, empty, whitespace-only and 1001-character prompts return 422 and create no row; 1000-character and normal prompts still work with the unchanged `{id, prompt, status}` response; unit tests and the Hypothesis properties pass
  - Status: Done (2026-11-07) - RequestCreate enforces min_length=1, max_length=1000 and non-blank; tests/test_pipeline/test_prompt_validation.py 16 passed (422 for missing, empty, whitespace-only, 1001 chars; 1000 chars accepted). Not exercised against the live server
- [ ] **9.1** Expand request schemas - `backend/app/schemas/requests.py`
  - Depends on: 5.3, 6.2, 7.3, 8.2, 9.1a
  - Done when: `PipelineResponse`, `DegradedResponse`, `RequestSummaryResponse`, `RequestDetailResponse`, `AggregateMetricsResponse` added; `RequestCreate` and `RequestResponse` kept
  - Status: Not started. Task cites non-existent Requirement 7.9 (C-09)
- [!] **9.2** Pipeline orchestrator and new read endpoints - `backend/app/routers/requests.py`
  - Depends on: 4.2, 5.2, 6.1, 7.1, 7.2, 9.1, 9.1a, 1.4a, C-06
  - Done when: `POST /` runs persist -> classify -> route -> execute -> evaluate; Routing unavailable -> `pending` + 202; Evaluation failure after a completed execution -> HTTP 200 `partial` with the execution kept; Intelligence-only failure -> `moderate` fallback with no 202; `GET /` returns the 50 newest ordered by `created_at` desc then `id` desc; `GET /{id}` returns full detail or 404; `GET /api/requests/metrics` returns aggregate + adaptive-vs-baseline metrics (declare `/metrics` BEFORE `/{request_id}`, otherwise FastAPI treats "metrics" as an id and returns 422); legacy rows still render
  - Status: BLOCKED on C-06 only (missing provider config: error payload or HTTP 500). C-01 is resolved
- [ ] **9.3** Pipeline tests - `backend/tests/test_pipeline/test_orchestrator.py`
  - Depends on: 9.1, 9.2
  - Done when: smoke, Routing-unavailable 202, Intelligence-only fallback (200, `moderate`, `intelligence` step error, not `pending`), execution-failure, Evaluation-failure (200 `partial`, evaluation null, execution and response preserved, not `pending`), ordering with ties, and 404 tests plus Properties 19 and 20 pass
  - Status: Not started - no longer blocked by C-01; becomes ready once 9.2 is done
- [ ] **9.4*** Run pipeline property tests - `backend/tests/test_pipeline/`
  - Depends on: 9.3
  - Done when: green
  - Status: Not started
- [ ] **9.5** CRITICAL checkpoint - old behavior preserved and pipeline works end to end - (verification only)
  - Depends on: 9.2, 9.3, 6.5
  - Done when: plain `{"prompt": "..."}` body still accepted; list and health still work; a real Ollama prompt returns 200 with routing, execution and evaluation blocks
  - Status: Not started

## Phase 11 - Frontend Dashboard

- [x] **B-08** React <-> FastAPI communication - `frontend/src/App.jsx`, `frontend/src/services/api.js`
  - Depends on: B-03, B-06, B-07
  - Done when: UI submits a prompt and lists saved requests via `api.js`
  - Status: Done at the contract level - code calls both endpoints, CORS verified, build passes. A manual browser run was NOT performed by this audit. Known defects: `API_URL` is hardcoded (violates `tech.md`; fixed by 10.4/10.6) and errors drop the HTTP status
- [ ] **10.1** `PromptForm` and `ErrorBanner` - `frontend/src/components/PromptForm.jsx`, `ErrorBanner.jsx`
  - Depends on: B-08
  - Done when: form extracted from `App.jsx`; banner shows HTTP status plus message, hides when null
  - Status: Not started
- [ ] **10.2** Request list and detail components - `frontend/src/components/{RequestListItem,RequestList,RequestDetail}.jsx`
  - Depends on: 10.1, 9.1
  - Done when: prompt truncated to 100 chars, costs 4 dp, quality 2 dp, empty-state message; handles legacy rows with null model fields
  - Status: Not started
- [ ] **10.3** Metrics and comparison components - `frontend/src/components/{MetricsSummary,ComparisonPanel}.jsx`
  - Depends on: 9.1
  - Done when: zero-state shows 0 / 0.0000 / 0.00; "Insufficient data" when a mode has no executions
  - Status: Not started
- [ ] **10.4** Expand API client - `frontend/src/services/api.js`
  - Depends on: 9.2, 8.3
  - Done when: base URL from `import.meta.env.VITE_API_URL`; handles 200 and 202; all new functions added; errors carry `{status, message}`; no `fetch` outside `api.js`
  - Status: Not started
- [ ] **10.5** Wire everything in `App.jsx` - `frontend/src/App.jsx`
  - Depends on: 10.1, 10.2, 10.3, 10.4
  - Done when: state per design.md; refreshes list and metrics after each submission; shows the degraded message only for the Routing-unavailable (202) outcome and shows the response plus "Response generated. Quality evaluation was unavailable for this request." for a partial result
  - Status: Not started. C-01 is resolved (202 message only for a Routing outage). C-07 (nothing processes pending requests) is still open and affects the wording of that message
- [ ] **10.6** Configure `VITE_API_URL` - `frontend/.env.local`
  - Depends on: none
  - Done when: `.env.local` defines `VITE_API_URL=http://localhost:8000` and stays gitignored
  - Status: Not started. Currently no `.env*` file exists in `frontend/`
- [ ] **N-07** Label confidence as a heuristic in the UI - `frontend/src/components/RequestDetail.jsx`
  - Depends on: 10.2, N-06
  - Done when: confidence and quality show a "heuristic estimate" label or tooltip; nothing implies the answer is verified correct
  - Status: Not started
- [ ] **10.7** Checkpoint - dashboard end to end in a browser - (verification only)
  - Depends on: 10.5, 10.6, N-07
  - Done when: submit a prompt, see it in the list, open detail, metrics non-zero after a completed request
  - Status: Not started

## Phase 12 - Testing and Benchmarking

- [ ] **11.1** Integration test with real Ollama - `backend/tests/test_pipeline/test_integration.py`
  - Depends on: 9.2, B-14
  - Done when: skipped if `OLLAMA_BASE_URL` unset; otherwise asserts completed execution, score in range, full response blocks
  - Status: Not started
- [ ] **11.2** Adaptive vs baseline benchmark - `backend/tests/test_pipeline/test_benchmark.py`, `README.md`
  - Depends on: 11.1, N-08 (deferred to this phase)
  - Done when: 10 prompts run under `cost_optimised` and again under `baseline`; `GET /api/requests/metrics` shows adaptive cost <= baseline cost; results written to README
  - Status: Not started. Needs the second Ollama chat model from N-08, decided when this phase starts
- [ ] **11.3** Full PBT suite run - `backend/tests/`
  - Depends on: all test tasks
  - Done when: all 20 properties pass with `max_examples=100`; any shrunk counterexample is recorded in the test file
  - Status: Not started
- [ ] **N-08** Install a second Ollama chat model - local machine (`ollama pull <model>`)
  - Depends on: none. DEFERRED to this phase (approved 2026-11-07); not needed for Phases 1-11
  - Done when: two chat models are available and registered with different `capability_tier` values (e.g. 1 and 3)
  - Status: Deferred. Choose the model (disk and RAM) when benchmarking starts. Until then `qwen2.5:3b` is enough. Consequence: with one model, escalation and the cost-vs-quality policy difference can be shown only with mocked adapters (Tasks 6.3, 7.4) until this is done
## Phase 13 - Security and Reliability

- [ ] **11.4*** Security audit - `backend/app/`, `frontend/src/`
  - Depends on: 9.2, 10.5, N-05
  - Done when: no API key literals; `allow_origins` is not `*`; `RequestCreate.prompt` has `min_length=1, max_length=1000`; no `text()` SQL with unbound user input; no key substring in logs or error bodies
  - Status: Not started. Marked optional in `tasks.md`, but treat as required because the repo will be public
- [ ] **N-09** Pre-submission secret and history scan - repository root
  - Depends on: none (run last, right before submitting)
  - Done when: `git log --all -- backend/.env` is empty; `git grep` finds no key-like strings except placeholders; `.env`, `.env.local` still gitignored
  - Status: Not started (baseline scan passed on 2026-11-07, see B-15)

## Phase 14 - Deployment

- [ ] **11.5** Deployment prep and documentation - `README.md`, `backend/.env.example`
  - Depends on: N-04, N-03, 1.4, 1.4a
  - Done when: README documents venv + `pip install -r requirements.txt`, every `backend/.env` variable, `frontend/.env.local` `VITE_API_URL`, and `python -m testing.create_tables` (from `backend/`) is proven to build all 6 tables on a fresh database and `python -m testing.migrate_requests_table` then reports nothing to apply
  - Status: Not started
- [ ] **N-10** Correct stale README content - `README.md`
  - Depends on: 11.5
  - Done when: fixes applied for: `create_tables.py` is shown at `backend/` root but lives in `backend/testing/` and must be run as `python -m testing.create_tables`; install step lists packages instead of `pip install -r requirements.txt`; structure lists `schemas/request.py` but the file is `requests.py`; roadmap leaves "Kiro specification and steering setup" unchecked although both exist; endpoint and table lists reflect the MVP; license line says "To be determined"
  - Status: Not started
- [!] **N-11** Decide deployment target - `backend/app/main.py` (CORS), docs
  - Depends on: none. DECISION NEEDED
  - Options: (A) local install only, judges run it from the README (matches the 2025 rule that the project must be installable and run as described); (B) hosted demo (needs a MySQL host, HTTPS, a real CORS origin, and no key leakage; Ollama would not be available there)
  - Done when: choice recorded; if B, `allow_origins` set to the real origin (never `*`) and secrets are provided via the host's environment
  - Status: Blocked on your decision. Recommended: A for a hackathon MVP

## Phase 15 - Hackathon Submission and Demo

Requirements below come from the Kiroween 2025 rules as summarized in a third-party article, plus a 2026 snippet. The official 2026 page could not be fetched (HTTP 403). Confirm every item against the official Devpost rules (N-17).

- [ ] **11.6** Final end-to-end demo run - fresh database
  - Depends on: 10.7, 11.2, 8.6, N-18
  - Done when: two models registered; 5 prompts of varied complexity show correct class, model and response; feedback on 3 requests is reflected in the summary; comparison panel shows adaptive vs baseline
  - Status: Not started
- [!] **N-12** Choose the Kiroween category - Devpost entry
  - Depends on: none. DECISION NEEDED
  - Options reported for 2025: Resurrection, Frankenstein, Skeleton Crew, Costume Contest. Categories for 2026 are unverified
  - Done when: category chosen and the write-up (N-14) argues why NeuroRoute fits it
  - Status: Blocked on your decision
- [!] **N-13** Add an OSI-approved open-source LICENSE - `LICENSE`, `README.md`
  - Depends on: none. DECISION NEEDED (e.g. MIT or Apache-2.0)
  - Done when: `LICENSE` file at repo root, detected by GitHub, and README license section updated
  - Status: Blocked on your choice. README currently says "To be determined"; a visible OSI license was a stated requirement in 2025
- [ ] **N-14** Write the "How Kiro was used" explanation - `README.md` or a doc linked from it
  - Depends on: most phases done
  - Done when: it describes concrete use of specs (requirements -> design -> tasks), steering files, and any hooks/MCP used, with examples from this repo; it does not claim adaptive learning exists
  - Status: Not started. Judges reportedly require this write-up
- [ ] **N-15** Record a demo video under 3 minutes
  - Depends on: 11.6, N-18
  - Done when: video shows submit -> classify -> route -> execute -> evaluate -> dashboard -> feedback, plus the adaptive vs baseline comparison; uploaded and linked
  - Status: Not started
- [ ] **N-16** Clean-clone install test
  - Depends on: 11.5, N-10, N-13
  - Done when: a fresh clone in a new folder runs following only the README (venv, install, `.env`, tables, backend, frontend) with no undocumented step
  - Status: Not started. Confirms the project is installable by judges
- [ ] **N-17** Verify official rules and submit on Devpost
  - Depends on: N-12, N-13, N-14, N-15, N-16
  - Done when: official 2026 rules read (eligibility incl. start date, deadline and time zone, required fields); repo public; `.kiro/` at root and not gitignored; submission confirmed
  - Status: Not started. Eligibility note: your first commit is 2026-11-04. A search snippet says only projects started on or after Oct 30, 2026 qualify, which would include you - confirm against the official page
- [ ] **N-18** Prepare demo script and seed data - `README.md` or `docs/`
  - Depends on: 2.2, B-14, N-08
  - Done when: a repeatable set of model registrations and 5 demo prompts is documented; Ollama is running and warmed up before the demo
  - Status: Not started
- [!] **N-19** Decide whether to add Kiro hooks / MCP for the judging "Implementation" criterion
  - Depends on: none. DECISION NEEDED
  - Notes: specs and steering are already in use. Hooks and MCP are NOT in the confirmed MVP scope; adding them is optional and must not displace core tasks
  - Done when: you either record "not adding" or add a small, scoped task
  - Status: Blocked on your decision. Recommended: decide after Phase 10 is working

---

## Future Enhancements (NOT in current scope - do not implement for the MVP)

- Customer-managed provider connections / BYOK
- Automatic model discovery
- Automated model capability benchmarking
- Adaptive learning from historical requests (the MVP only STORES feedback; do not claim learning exists)
- Multi-agent orchestration
- MCP integration (listed as planned in `product.md` and the README roadmap, not in the MVP spec; see N-19)
- Alembic or another migration tool (needs approval under `tech.md`; see N-02)
- A worker that retries or processes `pending` requests (see C-07)

---

## Section C - Spec Inconsistencies and Open Decisions

These were found by reading all three specs against each other and against the code. None of them were silently resolved and no spec file was changed by this audit. Each needs your decision, then a small spec edit.

- [x] **C-01** HIGH - HTTP 202 / degraded-mode rule (RESOLVED 2026-11-07)
  - Decision: Routing unavailable -> `pending` + HTTP 202 (unchanged). Evaluation fails after a completed execution -> response and execution preserved, HTTP 200 `partial`, evaluation null, `step_errors` entry; never 202 or `pending`. Intelligence-only failure -> `moderate` fallback, continue, no 202.
  - Applied to: requirements.md Req 8.4 and Req 7.8; design.md Degraded Modes, `POST /api/requests/` responses, pipeline steps 1/3/4/6, "HTTP 202 Degraded Mode Trigger Conditions", per-step table, unit-test focus; tasks.md 9.2, 9.3, 10.5.
  - Implementation note: `NoEligibleModelError` (HTTP 503) subclasses `ServiceUnavailableError`, so the orchestrator must catch it first.
- [x] **C-02** HIGH - Complexity classification rules (RESOLVED 2026-11-07)
  - Decision: one deterministic rule set using N (tokens), D (distinct domain terms), R (distinct reasoning connectives), S (distinct synthesis indicators). HIGH (`complex`): R>=3, or S>=2, or D>=3, or N>=200. LOW (`simple`): N<50 and D=0 and R<2 and S=0. MEDIUM (`moderate`): everything else, including 50-199 tokens with no indicator. LOW/MEDIUM/HIGH map to the existing labels simple/moderate/complex; no label was renamed.
  - Applied to: requirements.md Glossary and Req 2.2-2.5; design.md classifier section and generator table; tasks.md 4.2, 4.3.
- [x] **C-03** MED - Token limit handling (RESOLVED 2026-11-07 as a consequence of C-02 and N-05)
  - Task 4.2 now enforces the 1000-token guard and Task 4.3 tests it. The API accepts at most 1000 characters (Req 8.7, Task 9.1a), so the token guard is unreachable through the API by design and is kept as defence in depth. Requirement 2.7 is unchanged.
- [ ] **C-04** MED - Cost estimate inputs are undefined (blocks 5.1)
  - Task 5.1 uses `prompt_token_count` and `average_output_tokens`, but `select_cost_optimised(models, complexity)` receives neither. design.md's Property 6 example uses `m.estimated_cost`, which is not a field of `Model`.
  - Decision: pass the prompt token count and use a fixed expected-output-tokens value per complexity class.
- [ ] **C-05** MED - `capability_tier` is missing from Requirement 1.1 and 1.5
  - Requirements 3.4 and 5.5 depend on it, and design.md/tasks.md store it (default 1). Add it to Req 1.1.
- [ ] **C-06** MED - Missing provider config: error payload or HTTP 500?
  - Req 4.9 and 8.3: return an error payload and continue. design.md step 5 and its table: "Missing config -> HTTP 500". Tasks 3.2/3.3 raise `ConfigurationError` in `__init__`; Task 6.3 expects "ConfigurationError, no unhandled exception", which is self-contradictory.
  - Decision: recommended - catch it in `execute_request`, store a `failed` execution, add to `step_errors`.
- [ ] **C-07** MED - Nothing processes `pending` requests, but the UI promises it
  - Req 7.8 fixes the message "will be processed when services recover" and Req 8.4 says "queued for deferred processing", yet no task builds a retry or worker, and design.md forbids queues.
  - Decision: reword the message to what is true, or add a minimal manual "retry" action. Do not ship a promise the system cannot keep.
- [ ] **C-08** LOW - `ConflictError(field=...)` is used in Task 2.2 and in the design's error body, but Task 1.2 defines no `field` attribute and Task 1.5 returns only `detail`.
- [ ] **C-09** LOW - Task 9.1 cites Requirement 7.9, which does not exist (Requirement 7 has 8 criteria).
- [ ] **C-10** LOW - Task 3.4 suggests `respx`, which is not in `requirements.txt`. Use `httpx.MockTransport` or `unittest.mock`.
- [x] **C-11** LOW - Unused `openai` dependency (RESOLVED 2026-11-07). The provider changed from OpenAI to Gemini; `openai` was removed from `backend/requirements.txt`, design.md and tasks.md. The Gemini adapter calls the REST API with `httpx`, so no provider SDK is needed.
- [ ] **C-12** LOW - Glossary names the table `routing_decision`; design and tasks use `routing_decisions` (previously noted and deferred).
- [ ] **C-13** LOW - Listing and legacy rows (partly addressed). Addressed: 1.4a gives legacy rows a `created_at`, and design/tasks now order by `created_at` desc then `id` desc. Still open: the 50-row limit appears in Req 7.1 and the design but not in Req 8.6 (existing `GET /api/requests/` returns all rows), and the legacy `completed` rows (ids 1-2) have no execution, so the list and metrics must tolerate null model, cost and quality fields.
- [x] **C-14** MED - ORM and live schema are out of step until 1.4a is applied (found by checkpoint 1.7, 2026-11-07) - RESOLVED 2026-11-07: migration applied; live GET /api/requests/ returns 200 again
  - The `Request` model now declares `complexity_class`, `end_to_end_latency_ms` and `created_at`, but the live `requests` table has only `id, prompt, status`. A read-only `SELECT` through the ORM fails with MySQL error 1054 (Unknown column requests.complexity_class), so the live `GET /api/requests/` returns HTTP 500 and `POST` would fail too. Tests are unaffected (in-memory SQLite).
  - Decision: approve the live migration soon (rehearsal, then apply), and do not use the live app or the frontend against MySQL until then.

---

## Verification Log (2026-11-07)

Checks that were actually run, and their results:

| Check | Result |
|---|---|
| `git status`, `git log`, `git remote -v` | Clean tree; 4 commits; `origin/main` equals `HEAD`; remote is GitHub |
| `git ls-files` / `git check-ignore` | `backend/.env` ignored; `backend/testing/` ignored by `.gitignore:29`; `.kiro/` tracked and not ignored |
| `pip list`, `pip install --dry-run -r requirements.txt` | 11 pinned packages installed and satisfied |
| Byte check of `backend/requirements.txt` | Starts with `FF FE` (UTF-16 LE BOM), 734 bytes |
| `python testing\test_db.py` | Fails with `ModuleNotFoundError: app` as documented; works with `PYTHONPATH=.` (MySQL 8.0.44, db `neuroroute`) |
| Read-only inspection of live MySQL | One table `requests` (`id, prompt, status`), 4 rows |
| `GET /api/health`, `GET /api/requests/` through TestClient on live DB | 200 and 200 (4 rows) |
| `POST/GET /api/requests/` through TestClient with in-memory SQLite | 200 with `{id, prompt, status:"pending"}`; empty prompt -> 200; 1500-char prompt -> 200 (both should be 422 per `tech.md`) |
| CORS header for `Origin: http://localhost:5173` | Echoed back |
| `npm run lint` / `vite build` (output to a temp folder, then deleted) | 0 lint errors, 1 warning; build succeeded |
| Ollama API | Reachable; models `qwen2.5:3b`, `nomic-embed-text:latest` |
| Git history and tracked files secret scan | No `.env` ever committed; only the README placeholder matched |
| Spec text encoding scan | No mojibake in the three spec files |
| Existing automated tests | None. `backend/tests/` and any pytest config do not exist |

Not verified:

- Browser end-to-end run of the React app (backend contract and build only).
- `POST /api/requests/` against live MySQL (deliberately not called to avoid writing data).
- Any MVP subsystem: none of the new tables, routers, services, adapters or components exist yet.
- Official Kiroween 2026 rules, deadline, categories and eligibility (official page returned HTTP 403; 2025 rules are from a third-party summary; the 2026 window comes from one unverified snippet).
- Whether `ALTER TABLE` on the live `requests` table succeeds (not attempted).

Spec edits for the 2026-11-07 decisions were applied to requirements.md, design.md and tasks.md and checked with `validate_spec_format` (no issues); line endings and encoding were preserved. `.gitignore` was updated for N-03. No application source code was changed.

The LLM provider was changed from OpenAI to Google Gemini on 2026-11-07 (Ollama unchanged). The specs, steering examples and `backend/requirements.txt` were updated; the earlier verification rows above that mention 11 pinned packages describe the state before `openai` was removed.


---

## Phase 1 implementation log (2026-11-07)

Files created or changed by Phase 1 (names only):
- backend/app: exceptions.py, main.py, models/__init__.py, models/request.py, models/model.py, models/routing_decision.py, models/execution.py, models/evaluation.py, models/feedback.py, schemas/requests.py
- backend/testing: create_tables.py, migrate_requests_table.py, MIGRATION.md
- backend/tests: conftest.py, test_guard.py, test_exceptions.py, test_exception_handlers.py, test_database/test_orm_models.py, test_migration/test_migrate_requests_table.py, test_pipeline/test_existing_crud.py, test_pipeline/test_prompt_validation.py, plus package __init__.py files
- backend: requirements.txt, .env.example, pytest.ini
- repository: .gitignore, TODO.md, .kiro specs and steering

Final test count: 109 passed (run twice from backend/ and once from the repo root, same count each time).

Live `requests` table fingerprint taken before and after the full test run (identical), for comparison after the real migration:
- row count: 4
- sha256 over (id, prompt, status): 0360760e2bb03e7657aa994fa4c284b03df44bb55a751bc37d6d0c1140ebe600
- columns: id, prompt, status

The live migration (Task 1.4a) and `testing/create_tables.py` have NOT been run. The live database still has only the `requests` table.

### Live migration and checkpoint 1.7 results (2026-11-07)

- Migration backup (under `backend/backups/`, gitignored): `requests_premigration_20261107_181823.json`, SHA-256 `0dc17a7de6e46bbb9a8c3a54d7532066e8f8051da2498e9d2226acbb53dc0290`.
- Original rows 1-4 fingerprint unchanged after migration, create_tables (twice), three pytest runs and the live API calls: `0360760e2bb03e7657aa994fa4c284b03df44bb55a751bc37d6d0c1140ebe600`. Their `complexity_class` and `end_to_end_latency_ms` are still NULL.
- `python -m testing.create_tables` run live twice: five empty tables created (models, routing_decisions, executions, evaluations, feedback); second run changed nothing. No column drift between the ORM and the live schema. `executions.response_text` is LONGTEXT; money columns are DECIMAL(20,10); unique keys on models.identifier, evaluations.execution_id, feedback.request_id; all five required foreign keys exist.
- Migration re-run (dry run): "Nothing to apply", exit 0.
- pytest: 109 passed from `backend/` (twice) and 109 passed from the repo root; no skip, skipif or xfail in `backend/tests`; live DB snapshots before and after the test runs are identical.
- Live API (uvicorn on port 8765, stopped afterwards): health 200; GET list 200 with 4 items (ids 4,3,2,1; keys id, prompt, status); POST 200 with id 5 and status pending; GET list 200 with 5 items (5,4,3,2,1); 422 with a `detail` list mentioning `prompt` for empty, whitespace-only, 1001-character and missing prompt (row count stayed 5); CORS preflight 200 with `Access-Control-Allow-Origin: http://localhost:5173`. The 1000-character boundary was not sent live (covered by unit tests).
- Probe row: id 5, prompt "Phase 1 live verification probe (safe to delete)", status pending, NULL complexity_class and latency, `created_at` 2026-11-07 18:27:50. It was NOT deleted; the user decides whether to remove it.
- Browser verification of the React frontend was NOT performed (no Vite server was running on port 5173).
