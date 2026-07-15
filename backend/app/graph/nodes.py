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
                    "enum": _load_domains() + ["n/a"],
                    "description": (
                        "Which section of the bundle this message belongs to. "
                        "Use 'n/a' only when concepts is empty - never assign a real "
                        "domain to a message that produced no concepts."
                    ),
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
                                    "Concept type in PascalCase, no spaces (e.g. 'MeetingNote', not "
                                    "'Meeting note'). Prefer reusing one of the existing registry types "
                                    "below if it's a reasonable semantic match. Only invent a new concise "
                                    "PascalCase type if nothing fits."
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
                                "description": (
                                    "concept_id values of other concepts in this same batch to add a "
                                    "human-readable 'See [Title](...)' cross-link to in their body text."
                                ),
                            },
                            "relations": {
                                "type": "array",
                                "description": (
                                    "Typed structural links to other concepts in this same batch, for graph "
                                    "queries. Each needs a camelCase predicate describing HOW this concept "
                                    "relates to the target (e.g. 'attendee', 'assignedTo', 'partOf', "
                                    "'relatesTo') and the target's exact concept_id."
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "predicate": {
                                            "type": "string",
                                            "description": "camelCase relation name, e.g. 'attendee', 'assignedTo', 'partOf'.",
                                        },
                                        "target_concept_id": {"type": "string"},
                                    },
                                    "required": ["predicate", "target_concept_id"],
                                },
                            },
                        },
                        "required": ["concept_id", "type", "title", "description", "content", "links_to", "relations"],
                    },
                },
            },
            "required": ["domain", "concepts"],
        },
    }


def extract_concepts_node(state: PipelineState) -> PipelineState:
    existing_types = registry.load_types()
    existing_concepts = retrieval.get_relevant_concepts(state["raw_message"])
    index_files = bundle.list_index_files()
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

    if index_files:
        index_blocks = "\n\n".join(
            f"[{i['folder']}/index.md]\n{i['content']}" for i in index_files
        )
        index_context = (
            "Folder-level overviews of the bundle's existing structure (each index.md "
            "lists what's already in that folder) - use this for broad context on what "
            "categories/areas already exist, alongside the specific concept matches above:\n"
            + index_blocks
        )
    else:
        index_context = "No index.md files yet - the bundle is likely empty or new."

    system = (
        f"Today's date is {today} (UTC) - use this, not any other assumption, "
        "whenever a concept_id needs a date (e.g. journal entries). "
        "You convert a person's chat message into OKF knowledge-bundle updates. "
        "Decide which concepts (people, projects, tasks, decisions, personal notes, journal "
        "entries, etc.) the message touches - there can be one or several, or none. "
        f"Existing registry types: {', '.join(existing_types)}. "
        f"{concept_context} "
        f"{index_context} "
        "IMPORTANT - this bundle belongs to a single person: the dashboard owner. They are "
        "the implicit user of the whole system, not a contact to track by default. The rule: "
        "- If the owner is merely REPORTING or ASSIGNING someone else's work (e.g. 'Assign "
        "Mohamed to X', 'Dinuka removed from Y, per Kamal', 'Piyal is working on Z') - the "
        "owner is only the SOURCE of the update, not its subject. Do NOT create or update "
        "the owner's own Person concept in these cases. "
        "- EXCEPTION: if the message explicitly names the owner as a PARTICIPANT doing the "
        "work themselves, using first-person self-reference ('I need to work on X', 'me and "
        "Tharindu will do Y', 'I completed X') - treat the owner exactly like any other "
        "person who's a participant, and DO create/update their Person concept the same way "
        "you would for a colleague. "
        "In short: first-person self-reference as a doer = touch their Person concept. "
        "Third-person reporting/assigning of others = do not. "
        "Only create/update Person concepts for genuinely relevant people (the owner under "
        "the exception above, or any other person mentioned - e.g. Piyal, Sanduni, Dinuka). "
        "A legacy Person concept for the owner may already exist in the bundle from before "
        "this rule - if this message doesn't meet the first-person exception, leave it alone. "
        "If the message is small talk, off-topic, or has no durable knowledge content (e.g. "
        "a weather comment, a greeting), return an EMPTY concepts array - it is correct and "
        "expected to touch nothing rather than force-fitting it onto an unrelated existing "
        "concept. "
        "Whenever a concept has a clear real-world relationship to another concept in this "
        "same batch (e.g. a meeting has an attendee, a task is assignedTo a person, a task "
        "is partOf a project), express it in 'relations' with a short camelCase predicate - "
        "this is separate from 'links_to', which is just for the human-readable body text. "
        "Populate both when a relationship applies. "
        "You MUST always call extract_concepts with both the 'domain' field and the "
        "'concepts' field populated - never omit 'domain', even though it is a single "
        "enum choice. 'concepts' being an empty list is fine; omitting it is not."
    )
    user_message = (
        f"Dashboard owner (the single user of this tool - never a Person concept, "
        f"only ever the source/reporter of updates): {state['dashboard_owner']}\n"
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

        try:
            sanitized_type = registry.sanitize_type(concept["type"])
            registry.register_type(sanitized_type)

            path, action = bundle.write_concept(
                concept_id=concept_id,
                type_=sanitized_type,
                title=concept["title"],
                description=concept["description"],
                body_addition=concept["content"],
            )

            for target_id in concept.get("links_to", []):
                link_line = f"See [{concept['title']}](/{concept_id}.md)."
                bundle.add_link(target_id, link_line)

            for rel in concept.get("relations", []):
                bundle.add_relation(concept_id, rel["predicate"], rel["target_concept_id"])

            written.append({
                "concept_id": concept_id,
                "type": sanitized_type,
                "action": action,
                "path": str(path),
            })
        except bundle.UnsafeConceptIdError as e:
            # Don't let one bad concept_id fail the whole message - skip it,
            # log it, and keep writing the other concepts in this batch.
            print(f"[write_concepts_node] Skipped unsafe concept_id: {e}")
            written.append({
                "concept_id": concept_id,
                "type": concept["type"],
                "action": "rejected",
                "path": "",
            })
    state["written"] = written
    return state


def update_meta_node(state: PipelineState) -> PipelineState:
    touched_dirs = set()
    for item in state["written"]:
        if item["action"] == "rejected":
            continue
        concept_id = item["concept_id"]
        verb = "Creation" if item["action"] == "created" else "Update"
        bundle.append_log(concept_id, f"**{verb}**: {item['concept_id']}.md ({item['type']})")
        touched_dirs.add(bundle.concept_path(concept_id).parent)

    for directory in touched_dirs:
        bundle.rebuild_index(directory)

    return state