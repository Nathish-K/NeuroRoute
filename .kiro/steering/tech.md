# NeuroRoute — Technology Stack & Conventions

## Approved Stack

This is the canonical technology stack for NeuroRoute. Do not introduce new databases, ORMs, frameworks, or runtimes without explicit approval. Do not replace any layer listed here with an alternative (e.g. do not swap MySQL for MongoDB, do not swap FastAPI for Django or Flask).

---

## Frontend

### React 19
- Version: `react@^19.3.1`, `react-dom@^19.3.1`
- Plain JavaScript (`.jsx`). The project does not use TypeScript even though `@types/react` is installed.
- No class components. Use functional components with hooks only.
- No component library is installed. Keep the UI dependency footprint minimal until a library is formally adopted.
- No client-side routing library is installed yet (`react-router-dom` is not a dependency).

### Vite 8
- Version: `vite@^8.3.5` with `@vitejs/plugin-react@^6.1.2` (Babel-based Fast Refresh).
- Dev server runs on `http://localhost:5173` by default.
- All environment variables exposed to the frontend must be prefixed with `VITE_` and accessed via `import.meta.env.VITE_*`.
- Do not hardcode the API base URL in source files. Use `import.meta.env.VITE_API_URL`.

### Linter
- `oxlint@^1.89.0` — Rust-based linter, faster than ESLint.
- Run with `npm run lint`.

### API Communication
- Use the native browser `fetch` API. Axios is not installed; do not add it without approval.
- All API calls are centralised in `frontend/src/services/api.js`. Do not make fetch calls directly from components.
- Throw meaningful `Error` objects on non-OK responses so components can display feedback.

---

## Backend

### Python
- Minimum version: Python 3.10 (required for `match` statements and modern type hints).
- Use a virtual environment: `backend/.venv/` (already initialised).
- Activate on Windows PowerShell: `.\.venv\Scripts\Activate.ps1`

### FastAPI
- Used as the web framework and API layer.
- Run with: `python -m uvicorn app.main:app --reload` from the `backend/` directory.
- Interactive docs available at `http://127.0.0.1:8000/docs` (Swagger UI).
- All routes must be grouped into `APIRouter` instances with a `prefix` and `tags`. Do not define business logic routes inline in `main.py`.
- Use `Depends()` for dependency injection (database sessions, auth, etc.).

### Uvicorn
- ASGI server for FastAPI.
- Use `--reload` flag in development only. Never use `--reload` in production.

### Pydantic v2
- Used for request/response schema validation (ships with FastAPI).
- Use `ConfigDict(from_attributes=True)` on response schemas that are built from SQLAlchemy model instances (replaces the v1 `orm_mode = True`).
- Always define separate `Create` and `Response` schemas — do not reuse the same schema for input and output.
- Add field-level validation (`min_length`, `max_length`, `pattern`) to all string inputs.

---

## Database

### MySQL
- Database name: `neuroroute` (configured in `backend/.env`).
- MySQL Server must be running locally on port 3306 (default).
- Never run raw SQL strings with user-supplied values. Use ORM queries or parameterised statements only.

### SQLAlchemy 2.x
- Use the modern `DeclarativeBase` style (not the legacy `declarative_base()` function).
- Define all columns using `Mapped[type]` and `mapped_column()` annotations.
- All models must inherit from `Base` defined in `backend/app/database/connection.py`.
- Import every model in `backend/testing/create_tables.py` before calling `Base.metadata.create_all()` to ensure models are registered.
- `pool_pre_ping=True` is set on the engine — keep this in place to prevent stale connection errors.

### PyMySQL
- Pure-Python MySQL client driver (`mysql+pymysql` dialect).
- No C extensions required. Do not switch to `mysqlclient` or `aiomysql` without approval.

### Sessions
- Use the `get_db()` dependency from `backend/app/database/dependencies.py` for all database access in route handlers.
- Never create a `SessionLocal()` directly inside a route handler. Always inject via `Depends(get_db)`.
- Manual transaction control: `autoflush=False`, `autocommit=False`. Call `db.commit()` explicitly after writes.

---

## Security Rules

### Secrets and Environment Variables
- **Never hardcode credentials, passwords, API keys, or connection strings in source files.**
- All secrets must live in `backend/.env` and be loaded via `python-dotenv`.
- `backend/.env` is listed in `.gitignore` and must never be committed to version control.
- Frontend secrets (API keys, etc.) must use `.env.local` files with `VITE_` prefix and must also be gitignored.
- When any LLM API keys are added in future, they must follow the same `.env` pattern.

### CORS
- The current allowed origin is `http://localhost:5173` (development only).
- Before any deployment, update `allow_origins` in `main.py` to the actual production domain. Do not use `allow_origins=["*"]` in production.

### Input Validation
- All user-supplied strings must have explicit `min_length` and `max_length` constraints in their Pydantic schema.
- The `prompt` field on `RequestCreate` currently has no constraints — add `min_length=1, max_length=1000` before extending the feature.

### SQL Injection
- Use SQLAlchemy ORM queries exclusively. If raw SQL is ever needed, use `text()` with bound parameters only.

---

## Dependency Management

### Backend
- There is currently no `requirements.txt` or `pyproject.toml`. One must be created before new packages are added.
- Minimum required packages: `fastapi`, `uvicorn`, `sqlalchemy`, `pymysql`, `python-dotenv`.
- Pin versions (e.g. `fastapi==0.115.0`) in `requirements.txt` to ensure reproducible installs.

### Frontend
- `package-lock.json` is committed — always run `npm install` (not `npm ci`) unless versions are explicitly pinned.
- Do not add UI component libraries or state management libraries (Redux, Zustand, etc.) without approval.

---

## Coding Conventions

### Python
- Follow PEP 8. Use 4-space indentation.
- Use type hints on all function signatures (parameters and return types).
- Keep route handlers thin — move business logic to service functions if it grows beyond a few lines.
- Group imports: standard library → third-party → local application, separated by blank lines.

### JavaScript / JSX
- Use `camelCase` for variables and functions; `PascalCase` for component names.
- Prefer `async/await` over `.then()` chains.
- All API service functions live in `frontend/src/services/`. Components must not call `fetch` directly.
- Use `const` by default; only use `let` when reassignment is needed.

### File Naming
- Python modules: `snake_case.py`
- React components and files: `PascalCase.jsx`
- Service and utility files: `camelCase.js`
