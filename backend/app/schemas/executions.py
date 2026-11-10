from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ExecutionResponse(BaseModel):
    """A persisted execution attempt, serialised from the ORM record.

    The optional fields stay unset on a failed or timed-out attempt, where the
    provider returned no usage metrics.
    """

    id: int
    routing_decision_id: int
    response_text: str | None
    input_token_count: int | None
    output_token_count: int | None
    latency_ms: int | None
    estimated_cost: Decimal | None
    status: str
    error_message: str | None
    is_escalated: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
