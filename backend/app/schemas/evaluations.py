from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvaluationResponse(BaseModel):
    """A persisted quality evaluation, serialised from the ORM record.

    ``quality_score`` and ``confidence`` are both in [0.0, 1.0]; the Evaluation
    Service clamps and validates them on write.
    """

    id: int
    execution_id: int
    quality_score: float
    confidence: float
    escalation_flag: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
