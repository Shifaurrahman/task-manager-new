from datetime import datetime, timezone

from app.config import settings
from app.graph.state import PipelineState
from app.llm.client import call_with_tool
from app.okf import bundle, registry, retrieval

_FALLBACK_DOMAINS = ["professional", "personal"]


def _load_domains() -> list[str]:
    try:
        return settings.load_json_config(settings.domains_path)
    except FileNotFoundError:
        return list(_FALLBACK_DOMAINS)


def _build_extract_tool() -> dict:
    return {
        "name": "extract_concepts",
        "description": "Identify every knowledge-base concept touched by a chat message, and how to update each.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": _load_domains(),
                    "description": "Which section of the bundle this message belongs to.",
                },
                "concepts": {
                    "type": "array",
                    "description": "One entry per distinct concept this message touches. Usually 1-4.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "concept_id": {
                                "type": "string",
                            "description": (
                                "Bundle-relative path without extension, e.g. "
                                "'professional/people/piyal' or 'professional/projects/multimodal-rag-chatbot' "
                                "or 'personal/journal/2026-07-08'. kebab-case, stable across messages "
                                "about the same person/project so files get reused, not duplicated."
                            ),
                        },
                        "type": {
                            "type": "string",
                            "description": (
                                "Concept type. Prefer reusing one of the existing registry types given "
                                "below if it's a reasonable semantic match. Only invent a new concise "
                                "Title Case type if nothing fits."
                            ),
                        },
                        "title": {"type": "string"},
                        "description": {"type": "string", "description": "One-sentence summary."},
                        "content": {
                            "type": "string",
                            "description": "Markdown body content to write for this update (a few sentences/bullets).",
                        },
                        "links_to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "concept_id values of other concepts in this same batch to cross-link to.",
                        },
                    },
                    "required": ["concept_id", "type", "title", "description", "content", "links_to"],
                },
            },
        },
        "required": ["domain", "concepts"],
    },
}


def extract_concepts_node(state: PipelineState) -> PipelineState:
    existing_types = registry.load_types()
    existing_concepts = retrieval.get_relevant_concepts(state["raw_message"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if existing_concepts:
        concept_lines = "\n".join(
            f"- {c['concept_id']}: {c['title']} ({c['type']})" for c in existing_concepts
        )
        concept_context = (
            "Concepts already in the bundle that look most relevant to this message "
            "(not necessarily exhaustive) - if this message clearly refers to one of "
            "these same real-world people/projects/tasks/etc, REUSE its exact concept_id "
            "rather than inventing a new, similar-looking one:\n" + concept_lines
        )
    else:
        concept_context = "No closely related existing concepts were found - treat this as likely new."

    system = (
        f"Today's date is {today} (UTC) - use this, not any other assumption, "
        "whenever a concept_id needs a date (e.g. journal entries). "
        "You convert a person's chat message into OKF knowledge-bundle updates. "
        "Decide which concepts (people, projects, tasks, decisions, personal notes, journal "
        "entries, etc.) the message touches - there can be one or several. "
        f"Existing registry types: {', '.join(existing_types)}. "
        f"{concept_context} "
        "You MUST always call extract_concepts with both the 'domain' field and the "
        "'concepts' field populated - never omit 'domain', even though it is a single "
        "enum choice."
    )
    user_message = (
        f"Dashboard owner: {state['dashboard_owner']}\n"
        f"Message: {state['raw_message']}"
    )
    result = call_with_tool(system, user_message, _build_extract_tool(), required_keys=["domain", "concepts"])
    state["domain"] = result["domain"]
    state["concepts"] = result["concepts"]
    return state


def write_concepts_node(state: PipelineState) -> PipelineState:
    written = []
    for concept in state["concepts"]:
        concept_id = concept["concept_id"]
        registry.register_type(concept["type"])

        path, action = bundle.write_concept(
            concept_id=concept_id,
            type_=concept["type"],
            title=concept["title"],
            description=concept["description"],
            body_addition=concept["content"],
        )

        for target_id in concept.get("links_to", []):
            link_line = f"See [{concept['title']}](/{concept_id}.md)."
            bundle.add_link(target_id, link_line)

        written.append({
            "concept_id": concept_id,
            "type": concept["type"],
            "action": action,
            "path": str(path),
        })
    state["written"] = written
    return state


def update_meta_node(state: PipelineState) -> PipelineState:
    touched_dirs = set()
    for item in state["written"]:
        concept_id = item["concept_id"]
        verb = "Creation" if item["action"] == "created" else "Update"
        bundle.append_log(concept_id, f"**{verb}**: {item['concept_id']}.md ({item['type']})")
        touched_dirs.add(bundle.concept_path(concept_id).parent)

    for directory in touched_dirs:
        bundle.rebuild_index(directory)

    return state