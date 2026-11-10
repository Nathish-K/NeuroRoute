from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RoutingDecisionResponse(BaseModel):
    """A persisted routing decision, serialised from the ORM record."""

    id: int
    request_id: int
    # Foreign key into the models table, not the model's identifier string.
    model_id: int
    policy: str
    complexity_class: str
    estimated_cost: Decimal
    explanation: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
