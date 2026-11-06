# Requirements Document

## Introduction

NeuroRoute MVP is an adaptive AI inference architecture that routes each user prompt to the most appropriate language model based on query complexity, estimated cost, expected latency, and quality targets. The system extends the existing React 19 + FastAPI + MySQL stack with six new backend subsystems — Model Registry, Query Intelligence, Routing Engine, Multi-Model Execution, Quality Evaluation, and Feedback — plus an updated observability UI. Existing working endpoints (`POST /api/requests/`, `GET /api/requests/`, `GET /api/health`) and all current data are preserved throughout.

---

## Glossary

- **System**: The NeuroRoute application as a whole (frontend + backend + database).
- **API**: The FastAPI backend running at `http://localhost:8000`.
- **Frontend**: The React 19 + Vite application running at `http://localhost:5173`.
- **Model_Registry**: The backend subsystem (`backend/app/models/model.py` + supporting router) that stores registered LLM providers and their metadata.
- **Intelligence_Service**: The backend subsystem (`backend/app/intelligence/`) responsible for analysing a prompt and returning a complexity estimate and classification.
- **Routing_Engine**: The backend subsystem (`backend/app/routing/`) that selects a model for a given request based on complexity, cost, and latency signals.
- **Routing_Policy**: A named, configurable set of weights that governs how the Routing_Engine balances cost, latency, and quality objectives.
- **Execution_Engine**: The backend subsystem (`backend/app/adapters/`) that dispatches a prompt to a specific LLM provider and captures the response.
- **Provider_Adapter**: A concrete implementation of the provider interface (e.g. `openai_adapter.py`, `ollama_adapter.py`) used by the Execution_Engine.
- **Evaluation_Service**: The backend subsystem (`backend/app/evaluation/`) that scores a completed execution for quality and signals when escalation is required.
- **Feedback_Service**: The backend subsystem (`backend/app/feedback/`) that stores user-submitted feedback alongside the relevant request and routing decision.
- **Baseline_Router**: A deterministic routing mode that always selects the same fixed model, used for performance comparison.
- **Complexity_Class**: One of three discrete labels assigned by the Intelligence_Service: `simple`, `moderate`, or `complex`.
- **Routing_Decision**: A database record (`routing_decision` table) that captures which model was selected, the Routing_Policy applied, and the reasoning explanation.
- **Execution_Record**: A database record (`executions` table) that captures the provider response, token counts, latency in milliseconds, and estimated cost in USD.
- **Evaluation_Record**: A database record (`evaluations` table) that captures the quality score and confidence level for a completed execution.
- **Feedback_Record**: A database record (`feedback` table) that stores a user rating and optional comment linked to a specific request.
- **LLM_Provider**: An external service that accepts a prompt and returns a text response (e.g. OpenAI, a locally-hosted Ollama instance).
- **Token**: The unit of input/output measurement used by LLM providers for billing.
- **Escalation**: The process of re-routing a request to a more capable model when quality evaluation confidence falls below the configured threshold.

---

## Requirements

### Requirement 1: Model Registry

**User Story:** As an AI/ML engineer, I want to register available LLM providers and models with their capabilities and pricing, so that the routing and execution subsystems can make informed decisions without hardcoded values.

#### Acceptance Criteria

1. THE Model_Registry SHALL store, for each registered model: a unique string identifier of at most 128 characters, a provider name of at most 128 characters, a model name of at most 256 characters, a maximum context length in tokens as a positive integer, a cost per input token in USD as a non-negative decimal with up to 10 decimal places, a cost per output token in USD as a non-negative decimal with up to 10 decimal places, and an enabled flag that defaults to `true` when not supplied.
2. WHEN a request is made to `GET /api/models/`, THE API SHALL return all registered models ordered by provider name then model name.
3. WHEN a request is made to `POST /api/models/` with valid model data, THE API SHALL persist the new model record and return the created record with HTTP 201.
4. IF a `POST /api/models/` request includes a model identifier that already exists, THEN THE API SHALL return HTTP 409 with an error message that identifies the conflicting field and its value.
5. IF a `POST /api/models/` request is missing any of the required fields — identifier, provider name, model name, maximum context length, cost per input token, or cost per output token — THEN THE API SHALL return HTTP 422 with a validation error identifying each missing field by name.
6. THE Model_Registry SHALL load LLM provider API credentials exclusively from environment variables defined in `backend/.env`; credentials SHALL NOT appear in any source file or database record.
7. WHILE a model's enabled flag is `false`, THE Routing_Engine SHALL not select that model as a candidate in any routing decision, and THE API SHALL still return that model in `GET /api/models/` responses.
8. THE Model_Registry SHALL be backed by a `models` table in MySQL, defined using `Mapped[type]` and `mapped_column()` on a class that inherits from `Base`.

**Correctness Properties**

- FOR ALL registered models, the cost per input token and cost per output token SHALL each be greater than or equal to zero.
- FOR ALL registered models, the maximum context length SHALL be a positive integer.
- WHEN a model is retrieved by identifier after creation, THE Model_Registry SHALL return a record whose fields are identical to those submitted at creation time (round-trip property).

---

### Requirement 2: Query Intelligence

**User Story:** As an AI/ML engineer, I want incoming prompts to be analysed and classified by complexity, so that the Routing_Engine receives a structured signal rather than operating on raw text.

#### Acceptance Criteria

1. WHEN the Intelligence_Service receives a prompt string, THE Intelligence_Service SHALL return a Complexity_Class (`simple`, `moderate`, or `complex`) and an explanation string between 10 and 300 characters describing the classification rationale.
2. THE Intelligence_Service SHALL use whitespace-and-punctuation token splitting to count tokens for all classification and validation thresholds.
3. IF a prompt contains fewer than 50 tokens and does not contain terminology or concepts specific to a named professional or academic domain, THEN THE Intelligence_Service SHALL classify that prompt as `simple`.
4. IF a prompt requires 2 or more distinct reasoning steps or contains domain-specific terminology but does not require drawing on 2 or more independent sources of information, THEN THE Intelligence_Service SHALL classify that prompt as `moderate`.
5. IF a prompt requires drawing on 2 or more independent sources of information, requires specialized knowledge beyond general-purpose reasoning, or requires a reasoning chain of 3 or more distinct steps, THEN THE Intelligence_Service SHALL classify that prompt as `complex`.
6. WHEN the Intelligence_Service receives a prompt whose content is empty, THE Intelligence_Service SHALL return HTTP 422 with an error message indicating the prompt must not be empty, regardless of whether a request object was received.
7. WHEN the Intelligence_Service receives a prompt longer than 1 000 tokens, THE Intelligence_Service SHALL return HTTP 422 with an error message indicating the prompt exceeds the maximum allowed length.
8. WHERE the host machine has a CPU with a base clock of 2 GHz or higher and at least 8 GB of RAM, WHEN the Intelligence_Service classifies a prompt of up to 1 000 tokens, THE Intelligence_Service SHALL return the Complexity_Class within 500 ms.

**Correctness Properties**

- WHEN the Intelligence_Service classifies the same prompt twice without any configuration change, THE Intelligence_Service SHALL return the same Complexity_Class both times (idempotence).
- FOR ALL valid prompts, the returned explanation SHALL be a string of between 10 and 300 characters (completeness invariant).
- FOR ALL valid prompts, exactly one of `simple`, `moderate`, or `complex` SHALL be assigned per classification request (mutual exclusivity invariant).

---

### Requirement 3: Routing Engine

**User Story:** As an AI/ML engineer, I want the system to automatically select the most appropriate model for each request based on complexity, cost, and latency, so that I can compare adaptive routing against a fixed-model baseline.

#### Acceptance Criteria

1. WHEN the Routing_Engine receives a Complexity_Class and the current list of enabled models, THE Routing_Engine SHALL select exactly one model and return the selection alongside a human-readable explanation of no more than 500 characters describing the reason for model selection.
2. THE Routing_Engine SHALL support at least two Routing_Policies: `cost_optimised` (minimise estimated cost) and `quality_optimised` (prefer higher-capability models).
3. WHEN the active Routing_Policy is `cost_optimised`, THE Routing_Engine SHALL select the enabled model with the lowest estimated total cost for the given Complexity_Class; IF two or more eligible models share the lowest estimated total cost, THEN THE Routing_Engine SHALL select the model whose identifier is lexicographically first among the tied models.
4. WHEN the active Routing_Policy is `quality_optimised`, THE Routing_Engine SHALL select the enabled model with the highest context length among models whose Complexity_Class support tier is greater than or equal to the request's Complexity_Class rank in the ordered sequence LOW < MEDIUM < HIGH; IF two or more eligible models share the highest context length, THEN THE Routing_Engine SHALL select the model whose identifier is lexicographically first among the tied models.
5. WHEN the Baseline_Router mode is active, THE Routing_Engine SHALL select the model identified by the `BASELINE_MODEL_ID` environment variable, provided that model exists in the Model_Registry with enabled equal to `true` at the time of selection, regardless of Complexity_Class or policy.
6. IF no enabled model is available for the given Complexity_Class under the active policy, THEN THE Routing_Engine SHALL return HTTP 503 (and not any other 5xx status code) with an error message stating no suitable model is available.
7. IF the Baseline_Router mode is active and the model identified by `BASELINE_MODEL_ID` does not exist in the Model_Registry or has enabled equal to `false`, THEN THE Routing_Engine SHALL return HTTP 503 with an error message indicating the baseline model is unavailable.
8. THE Routing_Engine SHALL persist every routing decision as a Routing_Decision record containing: request identifier, selected model identifier, Routing_Policy name, Complexity_Class, estimated cost, and the routing explanation.
9. IF the Routing_Decision record cannot be persisted after a routing selection is made, THEN THE Routing_Engine SHALL return HTTP 500 with an error message indicating a persistence failure and SHALL NOT return the model selection to the caller.

**Correctness Properties**

- FOR ALL routing decisions made under the `cost_optimised` policy, the estimated cost of the selected model SHALL be less than or equal to the estimated cost of every other enabled model eligible for that request (cost minimisation invariant).
- WHEN the Baseline_Router is active and the same prompt is submitted twice, THE Routing_Engine SHALL select the same model both times (determinism invariant).
- FOR ALL routing decisions, the selected model identifier SHALL reference a model that exists in the Model_Registry with enabled equal to `true` at the time of selection (referential integrity invariant).
- WHEN a Routing_Decision is retrieved by request identifier after creation, THE Routing_Engine SHALL return a record whose selected model identifier matches the model returned to the caller (round-trip property).

---

### Requirement 4: Multi-Model Execution

**User Story:** As an AI/ML engineer, I want the system to execute prompts against the selected LLM provider and capture the full response with usage metrics, so that I can measure cost and latency for each inference call.

#### Acceptance Criteria

1. THE Execution_Engine SHALL define a Provider_Adapter interface that all concrete provider adapters implement, specifying at minimum: a method to dispatch a prompt and return response text, input token count, output token count, latency in milliseconds, and estimated cost in USD.
2. WHEN the Execution_Engine dispatches a prompt to a provider, THE Execution_Engine SHALL capture: the response text truncated to at most 1,000,000 characters (with the record persisted as successful even when truncation occurs), input token count, output token count, end-to-end latency as a non-negative integer in milliseconds, and estimated cost in USD rounded to 10 decimal places calculated from the model's stored pricing.
3. WHEN execution completes successfully, THE Execution_Engine SHALL persist an Execution_Record linked to the corresponding Routing_Decision.
4. THE Execution_Engine SHALL support dispatching prompts to OpenAI-compatible APIs, reading the API key from the `OPENAI_API_KEY` environment variable.
5. THE Execution_Engine SHALL support dispatching prompts to locally-hosted Ollama models, reading the base URL from the `OLLAMA_BASE_URL` environment variable.
6. IF a provider returns an error response, THEN THE Execution_Engine SHALL set the Execution_Record status to `failed`, log the error, and return an error payload containing at minimum an error indicator and a human-readable message describing the failure cause, without raising an unhandled exception.
7. IF a provider request exceeds 30 seconds without a response, THEN THE Execution_Engine SHALL cancel the request, set the Execution_Record status to `timed_out`, and return an error payload containing at minimum an error indicator and a human-readable message stating that the request timed out, without raising an unhandled exception.
8. IF a provider error or timeout occurs and a fallback model is configured via the `FALLBACK_MODEL_ID` environment variable, THEN THE Execution_Engine SHALL retry the prompt using the fallback model and record both the failed attempt and the fallback attempt as separate Execution_Records.
9. IF the required environment variable for a provider is absent or empty at the time of a dispatch request, THEN THE Execution_Engine SHALL reject the request and return an error payload indicating the missing configuration, without raising an unhandled exception.
10. THE Execution_Engine SHALL never expose raw provider API keys in logs, error messages, or API responses.

**Correctness Properties**

- FOR ALL successful executions, the estimated cost SHALL equal `(input_token_count × cost_per_input_token) + (output_token_count × cost_per_output_token)` for the selected model's stored pricing (cost calculation invariant).
- FOR ALL executions, the recorded latency SHALL be a non-negative integer (non-negativity invariant).
- WHEN an execution is retrieved by identifier after creation, THE Execution_Engine SHALL return a record whose response text, token counts, and latency match those captured at execution time (round-trip property).
- FOR ALL error conditions (provider error, timeout), THE Execution_Engine SHALL return an error payload rather than raise an unhandled exception (error containment invariant).

---

### Requirement 5: Quality Evaluation

**User Story:** As an AI/ML engineer, I want completed responses to be evaluated for quality, so that I can identify low-confidence answers and trigger escalation when necessary.

#### Acceptance Criteria

1. WHEN an Execution_Record's status transitions to `completed`, THE Evaluation_Service SHALL produce a quality score in the range [0.0, 1.0] (inclusive) and a confidence level in the range [0.0, 1.0] (inclusive) for that record.
2. WHEN the Evaluation_Service produces a quality score and confidence level for an Execution_Record, THE Evaluation_Service SHALL persist them as a new Evaluation_Record linked to that Execution_Record's identifier.
3. IF the `ESCALATION_CONFIDENCE_THRESHOLD` environment variable is absent or contains a value outside [0.0, 1.0], THEN THE Evaluation_Service SHALL reject startup with an error indicating the variable is invalid or missing.
4. IF an Evaluation_Record's confidence level is strictly less than the value of `ESCALATION_CONFIDENCE_THRESHOLD`, THEN THE Evaluation_Service SHALL set that Evaluation_Record's escalation flag to `true`; otherwise THE Evaluation_Service SHALL set the escalation flag to `false`.
5. IF an Evaluation_Record has escalation flag `true` and the Model_Registry contains at least one model with a capability_tier strictly greater than the model used for the original Execution_Record, THEN THE System SHALL re-route the original prompt to the model with the next higher capability_tier and create a new Routing_Decision and Execution_Record for the escalated attempt.
6. IF an Evaluation_Record has escalation flag `true` and no model in the Model_Registry has a capability_tier strictly greater than the model used for the original Execution_Record, THEN THE System SHALL set the escalation flag to `false` and return the response from the original Execution_Record unchanged.
7. IF the Evaluation_Record produced for an escalated Execution_Record has a confidence level strictly less than `ESCALATION_CONFIDENCE_THRESHOLD`, THEN THE Evaluation_Service SHALL set that Evaluation_Record's escalation flag to `false` and return the response with the higher quality score among the two Execution_Records.
8. WHEN `GET /api/requests/{id}` is called and a request with the given identifier exists, THE API SHALL return the original request, its Routing_Decision, its most recent Execution_Record, and its most recent Evaluation_Record (or null for any record not yet created) as a single response object.
9. IF `GET /api/requests/{id}` is called and no request with the given identifier exists, THEN THE API SHALL return an error response indicating the resource was not found.

**Correctness Properties**

- FOR ALL Evaluation_Records, the quality score SHALL be in the range [0.0, 1.0] and the confidence level SHALL be in the range [0.0, 1.0] (bounds invariant).
- WHEN the Evaluation_Service evaluates the same Execution_Record twice without any model or threshold change, THE Evaluation_Service SHALL return the same score and confidence (idempotence).
- FOR ALL escalated requests, the escalation chain length SHALL not exceed two Execution_Records (depth-limit invariant).

---

### Requirement 6: Feedback

**User Story:** As a developer, I want users to submit ratings and comments on responses, so that feedback is captured alongside routing decisions and can inform future routing policy improvements.

#### Acceptance Criteria

1. WHEN a user submits a `POST /api/requests/{id}/feedback` request with a rating between 1 and 5 and an optional comment, THE Feedback_Service SHALL persist a Feedback_Record linked to the request identifier.
2. IF a `POST /api/requests/{id}/feedback` request includes a rating outside the range 1–5, THEN THE Feedback_Service SHALL return HTTP 422 with an error message stating the rating must be an integer between 1 and 5 inclusive.
3. IF a `POST /api/requests/{id}/feedback` request references a request identifier that does not exist, THEN THE Feedback_Service SHALL return HTTP 404 with an error message stating the request was not found.
4. IF a `POST /api/requests/{id}/feedback` request is submitted for a request that already has a Feedback_Record, THEN THE Feedback_Service SHALL return HTTP 409 with an error message stating feedback has already been submitted for this request.
5. WHEN `GET /api/requests/{id}/feedback` is called and a Feedback_Record for the given request identifier exists, THE API SHALL return that Feedback_Record.
6. IF `GET /api/requests/{id}/feedback` is called and no Feedback_Record exists for the given request identifier, THEN THE API SHALL return HTTP 404 with an error message stating no feedback has been submitted for this request.
7. THE Feedback_Service SHALL persist each Feedback_Record with: request identifier, rating (integer 1–5), optional comment (maximum 500 characters), and creation timestamp.
8. IF a `POST /api/requests/{id}/feedback` request includes a comment exceeding 500 characters, THEN THE Feedback_Service SHALL return HTTP 422 with an error message stating the comment must not exceed 500 characters.
9. THE System SHALL expose `GET /api/metrics/feedback-summary` returning: mean rating rounded to 2 decimal places, rating distribution as a count per value from 1 to 5, and total feedback count, aggregated across all Feedback_Records globally with no filtering by request, time range, or any other dimension.

**Correctness Properties**

- FOR ALL Feedback_Records, the rating SHALL be an integer in the range [1, 5] (bounds invariant).
- WHEN a Feedback_Record is retrieved by request identifier after creation, THE Feedback_Service SHALL return a record whose rating and comment match those submitted (round-trip property).
- FOR ALL requests, the count of Feedback_Records with that request identifier SHALL never exceed one (uniqueness invariant).

---

### Requirement 7: Observability Dashboard

**User Story:** As a developer, I want a frontend dashboard showing request history, routing decisions, execution metrics, and quality scores, so that I can monitor system behaviour and compare adaptive routing against the baseline.

#### Acceptance Criteria

1. WHEN the Frontend loads, THE Frontend SHALL display a list of the 50 most recent requests, each showing: prompt (truncated to 100 characters), Complexity_Class, selected model name, Routing_Policy, latency in milliseconds, estimated cost in USD, and quality score; IF no requests exist, THE Frontend SHALL display a message indicating no requests have been submitted.
2. WHEN a user selects a request from the list, THE Frontend SHALL display the full request detail including: full prompt, routing explanation, full response text, token counts, latency, estimated cost, quality score, confidence level, and feedback rating if submitted.
3. WHEN the Frontend loads, THE Frontend SHALL retrieve aggregate metrics and display: total request count, mean latency in milliseconds rounded to the nearest integer, mean estimated cost in USD rounded to 4 decimal places, and mean quality score rounded to 2 decimal places; IF no Execution_Records exist, THE Frontend SHALL display each metric as zero.
4. WHEN the Frontend loads, THE Frontend SHALL retrieve and display a comparison panel showing mean latency and mean estimated cost for adaptive routing versus Baseline_Router; IF fewer than one Execution_Record exists for either routing mode, THE Frontend SHALL display "Insufficient data" for that mode's metrics.
5. WHEN a user submits a new prompt via the existing input form, THE Frontend SHALL display the Complexity_Class, selected model name, and response text returned by the API alongside the existing saved-request confirmation.
6. THE Frontend SHALL call the API exclusively through functions defined in `frontend/src/services/api.js`; no `fetch` call SHALL appear directly in a React component.
7. WHEN an API call fails, THE Frontend SHALL display an error message in the UI that includes the HTTP status code and a plain-language description of the failure, without logging the full request payload or any API credentials to the browser console.
8. WHEN the Routing_Engine or Evaluation_Service is unavailable and a user submits a prompt, THE Frontend SHALL still submit the prompt, display a message stating "Service partially unavailable — your prompt has been saved and will be processed when services recover", and show the saved request in the request list with status `pending`; IF only the Intelligence_Service is unavailable but the Routing_Engine and Evaluation_Service remain available, THE Frontend SHALL submit the prompt without the partial-unavailability message and allow the pipeline to proceed using fallback defaults.

**Correctness Properties**

- FOR ALL displayed cost values, THE Frontend SHALL render the value to exactly four decimal places in USD (display precision invariant).
- WHEN aggregate metrics are recalculated after a new Execution_Record is added, the new mean values SHALL reflect the updated record set (consistency invariant).

---

### Requirement 8: End-to-End Request Pipeline

**User Story:** As a developer, I want a single API call to trigger the full pipeline — Intelligence, Routing, Execution, and Evaluation — so that the system behaves as an integrated unit rather than requiring clients to orchestrate each subsystem manually.

#### Acceptance Criteria

1. WHEN a `POST /api/requests/` request is received with a valid prompt, THE API SHALL execute the following steps in order: persist the request, classify the prompt via the Intelligence_Service, select a model via the Routing_Engine, execute the prompt via the Execution_Engine, and evaluate the response via the Evaluation_Service.
2. WHEN all pipeline steps complete successfully, THE API SHALL return HTTP 200 with a response containing: request identifier, Complexity_Class, selected model name, routing explanation, response text, token counts, latency, estimated cost, and quality score.
3. IF any pipeline step fails with a recoverable error, THEN THE API SHALL continue to the next step where possible and include an error description for the failed step in the response payload.
4. IF the Routing_Engine or Evaluation_Service is unavailable, THEN THE API SHALL persist the request with status `pending`, return HTTP 202, and include a message stating the request has been queued for deferred processing; IF only the Intelligence_Service is unavailable but the Routing_Engine remains available, THEN THE API SHALL continue the pipeline using `moderate` as the fallback Complexity_Class and SHALL NOT return HTTP 202.
5. THE System SHALL record the end-to-end latency of the full pipeline for every request and store it in the Request record as `end_to_end_latency_ms`.
6. WHEN `GET /api/requests/` is called, THE API SHALL return requests ordered by creation timestamp descending, including Complexity_Class and selected model name for requests that completed the full pipeline.

**Correctness Properties**

- FOR ALL completed pipeline executions, the sum of individual subsystem latencies SHALL be less than or equal to the recorded end-to-end latency (latency composition invariant).
- WHEN the same prompt is submitted under identical configuration, THE System SHALL produce a Routing_Decision that selects the same model (determinism invariant, assuming no model availability changes between calls).
- FOR ALL requests that complete the full pipeline, exactly one Routing_Decision, one Execution_Record, and one Evaluation_Record SHALL exist per original request identifier, excluding escalation records (cardinality invariant).
