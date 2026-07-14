from pydantic import BaseModel


class MessageRequest(BaseModel):
    message: str               # the raw chat input


class WrittenConcept(BaseModel):
    concept_id: str
    type: str
    action: str                # "created" | "updated"
    path: str


class MessageResponse(BaseModel):
    domain: str                 # "professional" | "personal"
    written: list[WrittenConcept]