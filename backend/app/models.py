from pydantic import BaseModel


class MessageRequest(BaseModel):
    dashboard_owner: str      # e.g. "kamal" - whose dashboard sent this
    message: str               # the raw chat input


class WrittenConcept(BaseModel):
    concept_id: str
    type: str
    action: str                # "created" | "updated"
    path: str


class MessageResponse(BaseModel):
    domain: str                 # "professional" | "personal"
    written: list[WrittenConcept]