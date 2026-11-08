from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        # Reject whitespace-only prompts; return the original text unchanged.
        if not value.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return value


class RequestResponse(BaseModel):
    id: int
    prompt: str
    status: str

    model_config = ConfigDict(from_attributes=True)
