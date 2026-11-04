from pydantic import BaseModel, ConfigDict


class RequestCreate(BaseModel):
    prompt: str


class RequestResponse(BaseModel):
    id: int
    prompt: str
    status: str

    model_config = ConfigDict(from_attributes=True)