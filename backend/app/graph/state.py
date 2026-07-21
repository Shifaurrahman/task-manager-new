from typing import TypedDict


class Relation(TypedDict):
    predicate: str            # e.g. "assignedTo", "partOf", "attendee"
    target_concept_id: str


class ConceptTouch(TypedDict):
    concept_id: str      # e.g. "professional/people/piyal"
    type: str             # e.g. "Person"  (matched to registry, or newly invented)
    title: str
    description: str
    content: str           # markdown snippet to write/append into the concept body
    links_to: list[str]    # other concept_ids in this same batch to cross-link
    relations: list[Relation]   # typed structural links, e.g. assignedTo / partOf


class PipelineState(TypedDict):
    dashboard_owner: str
    raw_message: str
    domain: str                    # "professional" | "personal"
    concepts: list[ConceptTouch]
    written: list[dict]             # [{concept_id, type, action, path}]