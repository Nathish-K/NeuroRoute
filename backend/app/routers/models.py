from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.exceptions import ConflictError
from app.models.model import Model
from app.schemas.models import ModelCreate, ModelResponse

router = APIRouter(
    prefix="/api/models",
    tags=["Models"]
)


def _duplicate_identifier_error(identifier: str) -> ConflictError:
    return ConflictError(
        f"Model with identifier '{identifier}' already exists",
        field="identifier",
    )


# READ: List every registered model, including disabled ones (Requirement 1.7)
@router.get("/", response_model=list[ModelResponse])
def list_models(db: Session = Depends(get_db)) -> list[ModelResponse]:
    models = (
        db.query(Model)
        .order_by(Model.provider_name.asc(), Model.model_name.asc())
        .all()
    )
    return [ModelResponse.model_validate(model) for model in models]


# CREATE: Register a new model; identifiers must be unique (Requirement 1.4)
@router.post("/", response_model=ModelResponse, status_code=201)
def create_model(data: ModelCreate, db: Session = Depends(get_db)) -> ModelResponse:
    exists = db.query(Model.id).filter(Model.identifier == data.identifier).first()
    if exists is not None:
        raise _duplicate_identifier_error(data.identifier)

    new_model = Model(**data.model_dump())
    db.add(new_model)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent insert won the race past the check above; the UNIQUE
        # constraint on identifier is the final guard.
        db.rollback()
        raise _duplicate_identifier_error(data.identifier)
    db.refresh(new_model)

    return ModelResponse.model_validate(new_model)
