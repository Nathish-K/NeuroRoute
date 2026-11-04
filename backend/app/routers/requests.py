from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.request import Request
from app.schemas.requests import RequestCreate, RequestResponse

router = APIRouter(
    prefix="/api/requests",
    tags=["Requests"]
)


# CREATE: Save a new request
@router.post("/", response_model=RequestResponse)
def create_request(
    request: RequestCreate,
    db: Session = Depends(get_db)
):
    new_request = Request(
        prompt=request.prompt,
        status="pending"
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return new_request


# READ: Get all requests
@router.get("/", response_model=list[RequestResponse])
def get_requests(db: Session = Depends(get_db)):
    return db.query(Request).order_by(Request.id.desc()).all()