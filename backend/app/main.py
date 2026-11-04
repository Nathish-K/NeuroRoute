from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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