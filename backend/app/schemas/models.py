from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ModelCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    provider_name: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)
    max_context_length: int = Field(gt=0)
    cost_per_input_token: Decimal = Field(ge=0)
    cost_per_output_token: Decimal = Field(ge=0)
    # 1 = LOW (simple), 2 = MEDIUM (moderate), 3 = HIGH (complex)
    capability_tier: int = Field(default=1, ge=1, le=3)
    enabled: bool = True


class ModelResponse(ModelCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
