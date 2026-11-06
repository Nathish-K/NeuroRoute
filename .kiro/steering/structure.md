# NeuroRoute — Project Structure

## Repository Layout

```
Router/
├── .kiro/
│   └── steering/               ← Kiro steering documents (this file lives here)
│
├── backend/
│   ├── app/
│   │   ├── main.py             ← FastAPI app factory
│   │   ├── database/           ← DB engine, sessions, dependency injection
│   │   ├── models/             ← SQLAlchemy ORM models
│   │   ├── routers/            ← FastAPI route handlers
│   │   └── schemas/            ← Pydantic request/response schemas
│   ├── testing/                ← Standalone setup and verification scripts
│   └── .env                    ← Local secrets (never committed)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx             ← Root React component
│   │   ├── main.jsx            ← React DOM entry point
│   │   ├── index.css           ← Global styles and design tokens
│   │   ├── App.css             ← Unused scaffold CSS (leftover from Vite template)
│   │   └── services/
│   │       └── api.js          ← All fetch calls to the FastAPI backend
│   ├── public/                 ← Static assets (favicon, icon sprites)
│   ├── index.html              ← HTML shell
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
└── README.md
```

---

## Backend Directory Responsibilities

### `backend/app/main.py`
The FastAPI application factory. Responsibilities:
- Instantiate the `FastAPI()` app.
- Register all `APIRouter` instances via `app.include_router()`.
- Configure `CORSMiddleware`.
- Define the inline health check at `GET /api/health`.

Do not add business logic here. Route handlers belong in `routers/`.

### `backend/app/database/`

| File | Responsibility |
|---|---|
| `connection.py` | Creates the SQLAlchemy `engine` and `SessionLocal` factory; defines `Base` (the declarative base all models inherit from); loads `.env` via `python-dotenv`. |
| `dependencies.py` | Defines `get_db()` — a FastAPI dependency generator that opens a `SessionLocal`, yields it to the route handler, and closes it in the `finally` block. |

All database configuration changes (connection pool settings, engine options) happen only in `connection.py`.

### `backend/app/models/`
Contains SQLAlchemy ORM model classes. Each file maps to a logical domain entity.

- Models inherit from `Base` (imported from `connection.py`).
- Use SQLAlchemy 2.x style: `Mapped[type]` + `mapped_column()`.
- **Currently exists:** `request.py` — defines the `requests` table.

### `backend/app/routers/`
Contains `APIRouter` instances grouped by domain. Each router file defines its own `prefix` and `tags`.

- Route handlers must be thin: validate input, call `db` operations, return response.
- All database access goes through the `get_db()` dependency.
- **Currently exists:** `requests.py` — `POST /api/requests/` and `GET /api/requests/`.

### `backend/app/schemas/`
Contains Pydantic v2 schema classes for request validation and response serialisation.

- Always define separate `*Create` (input) and `*Response` (output) classes.
- Response schemas use `ConfigDict(from_attributes=True)` to work with SQLAlchemy model instances.
- **Currently exists:** `requests.py` — `RequestCreate` and `RequestResponse`.

### `backend/testing/`
Standalone Python scripts for development and setup verification. These are **not** pytest tests — they are run directly with `python testing/<script>.py` from the `backend/` directory.

| File | Purpose |
|---|---|
| `create_tables.py` | Runs `Base.metadata.create_all()` to create all ORM-defined tables in MySQL. |
| `test_db.py` | Verifies raw database connectivity; prints MySQL version and database name. |
| `test_crud.py` | Manually exercises CREATE and READ operations against the `requests` table. |

---

## Frontend Directory Responsibilities

### `frontend/src/main.jsx`
React DOM entry point. Mounts `<App />` inside `StrictMode` into `#root`. Do not add application logic here.

### `frontend/src/App.jsx`
Currently the only React component. Manages the prompt input, request list, and feedback message. As the UI grows, extract sub-components into a `frontend/src/components/` directory.

### `frontend/src/services/api.js`
The single source of all communication with the FastAPI backend. All `fetch` calls must live here — never call `fetch` directly from a component. Export one async function per API operation.

The API base URL must come from `import.meta.env.VITE_API_URL` (currently hardcoded — this must be fixed before any non-local deployment).

### `frontend/src/index.css`
Global styles and CSS custom properties (design tokens). Defines the colour palette, typography, and layout constraints for the app. `--accent: #aa3bff` (light) / `#c084fc` (dark).

### `frontend/src/App.css`
Dead code — leftover from the Vite scaffold template. Contains styles for classes that do not exist in the application. Safe to delete or repurpose; do not add to it.

---

## React → FastAPI Communication (Implemented)

```
frontend/src/App.jsx
    │  calls
    ▼
frontend/src/services/api.js
    │  fetch("http://localhost:8000/api/requests/", ...)
    ▼
backend/app/routers/requests.py   ← APIRouter prefix="/api/requests"
    │  Depends(get_db)
    ▼
backend/app/database/dependencies.py  ← get_db() yields SessionLocal
    │
    ▼
backend/app/models/request.py         ← SQLAlchemy Request model
```

**Currently active endpoints:**
- `POST /api/requests/` — saves a prompt, returns `{id, prompt, status}`
- `GET /api/requests/` — returns all requests ordered newest-first
- `GET /api/health` — returns backend health status

---

## FastAPI → MySQL Communication (Implemented)

```
backend/app/database/connection.py
    │  load_dotenv() reads backend/.env
    │  URL.create("mysql+pymysql", host, port, user, password, database)
    │  create_engine(..., pool_pre_ping=True)
    │  sessionmaker(bind=engine, autoflush=False, autocommit=False)
    ▼
backend/app/database/dependencies.py
    │  get_db() → yields SessionLocal → closes in finally
    ▼
Route handler
    │  db.add(obj) → db.commit() → db.refresh(obj)
    ▼
MySQL: neuroroute.requests
```

---

## Planned Module Placement

The following directories and modules **do not exist yet**. They represent where future components should be placed as the architecture grows.

### Query Intelligence
```
backend/app/intelligence/
├── __init__.py
├── complexity.py       ← Query complexity estimation logic
└── classifier.py       ← Intent classification (if needed)
```

### Adaptive Router
```
backend/app/routing/
├── __init__.py
├── router.py           ← Core routing decision logic
└── strategies.py       ← Routing strategies (cost-first, quality-first, etc.)
```

### Model Adapters
```
backend/app/models_adapters/     (or backend/app/adapters/)
├── __init__.py
├── base.py             ← Abstract base class for all model clients
├── openai_adapter.py   ← OpenAI / GPT-4o client
└── ollama_adapter.py   ← Local model client (Llama, etc.)
```

Note: avoid naming this directory `models/` — that name is already taken by the SQLAlchemy ORM models.

### Response Evaluation
```
backend/app/evaluation/
├── __init__.py
└── evaluator.py        ← Quality scoring, heuristic checks
```

### Feedback & Optimisation
```
backend/app/feedback/
├── __init__.py
└── optimizer.py        ← Routing weight updates from outcome data
```

### Future Database Models
As the planned tables are defined, add corresponding files to `backend/app/models/`:
- `model.py` — registered LLM models
- `routing_decision.py` — routing decision records (FK → requests)
- `execution.py` — inference execution records (latency, token usage)
- `evaluation.py` — response quality scores
- `feedback.py` — feedback and optimisation signals

Each new model must also be imported in `backend/testing/create_tables.py` before `Base.metadata.create_all()` is called.

### Future Frontend Structure
As the UI expands beyond a single component, organise the frontend as:
```
frontend/src/
├── components/         ← Reusable UI components
├── pages/              ← Page-level components (if routing is added)
├── hooks/              ← Custom React hooks
├── services/           ← API service functions (already exists)
└── context/            ← React Context providers (if global state is added)
```
