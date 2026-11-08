from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.exceptions import (
    ConfigurationError,
    ConflictError,
    NoEligibleModelError,
    NotFoundError,
    PersistenceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.routers.requests import router as requests_router

app = FastAPI()
app.include_router(requests_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "message": "NeuroRoute backend is running"
    }


# --- Exception handlers -----------------------------------------------------
# Body is always exactly {"detail": str(exc)}; never a traceback or class name.
# The base NeuroRouteError is deliberately NOT registered: an unmapped subclass
# falls through to Starlette's generic 500, which hides internals.


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# ServiceUnavailableError -> 503 is only the default. The request orchestrator
# (Task 9.2) converts a Routing Engine outage to HTTP 202 (Requirement 8.4)
# BEFORE the exception reaches this handler, so no 202 logic belongs here.
@app.exception_handler(ServiceUnavailableError)
async def service_unavailable_handler(
    request: Request, exc: ServiceUnavailableError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# More specific subclass of ServiceUnavailableError; resolved first via MRO.
@app.exception_handler(NoEligibleModelError)
async def no_eligible_model_handler(
    request: Request, exc: NoEligibleModelError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PersistenceError)
async def persistence_handler(request: Request, exc: PersistenceError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(ConfigurationError)
async def configuration_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
