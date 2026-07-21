from datetime import datetime, timezone

from app.config import settings
from app.graph.state import PipelineState
from app.llm.client import call_agentic
from app.okf import bundle, registry, retrieval

_FALLBACK_DOMAINS = ["professional", "personal"]


def _load_domains() -> list[str]:
    try:
        return settings.load_json_config(settings.domains_path)
    except FileNotFoundError:
        return list(_FALLBACK_DOMAINS)


def _build_search_tool() -> dict:
    return {
        "name": "search_concepts",
        "description": (
            "Search existing bundle concepts by keyword (person name, project title, "
            "task description, etc). Call this BEFORE deciding a concept is new, to "
            "check whether a matching one already exists and should be reused instead "
            "of creating a near-duplicate. Call it as many times as you need - once per "
            "distinct person/project/task you're unsure about. This applies to Tasks "
            "just as much as People and Projects - search using keywords from the work "
            "description itself (not only the person/project name), since task wording "
            "often varies between messages about the same piece of work. Optionally "
            "filter by type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text - a name, title, or phrase to match against existing concepts.",
                },
                "concept_type": {
                    "type": "string",
                    "description": "Optional - restrict results to one type, e.g. 'Person' or 'Project'.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return. Default 5.",
                },
            },
            "required": ["query"],
        },
    }


def _build_related_tool() -> dict:
    return {
        "name": "get_related_concepts",
        "description": (
            "Given a concept_id, return concepts already linked to it via typed "
            "relations (e.g. what tasks a person is assignedTo, what project a task "
            "is partOf). Use this to check existing relationships before adding new "
            "ones, or to understand context around a concept you're about to update."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "concept_id": {"type": "string"},
            },
            "required": ["concept_id"],
        },
    }


def _build_extract_tool() -> dict:
    return {
        "name": "extract_concepts",
        "description": (
            "Final answer - call this once you've done any needed searching and are "
            "ready to report every knowledge-base concept touched by the message, and "
            "how to update each."
        ),
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
                                    "Bundle-relative path without extension. Use this EXACT structure - "
                                    "'professional/people/<name>' for people, 'professional/projects/<name>' "
                                    "for projects, 'professional/tasks/<name>' for tasks (always flat under "
                                    "'tasks/', never nested inside a project's own folder), "
                                    "'personal/journal/<date>' for journal entries, "
                                    "'personal/personalNotes/<name>' for personal notes. kebab-case, stable "
                                    "across messages about the same person/project/task so files get reused, "
                                    "not duplicated. If search_concepts found a matching existing concept - "
                                    "including a Task referring to the same piece of work under slightly "
                                    "different wording - reuse its exact concept_id here rather than "
                                    "inventing a new, similar-looking one, even if that existing concept's "
                                    "path doesn't match this convention (legacy files may differ)."
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
                                "description": (
                                    "Markdown body content to write for this update (a few sentences/bullets). "
                                    "Any status or state information (e.g. a task being complete, in progress, "
                                    "blocked) belongs here as plain prose - never as a relation."
                                ),
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
                                    "Typed STRUCTURAL links to other concepts (in this batch, or found via "
                                    "search_concepts/get_related_concepts), for graph queries. Each needs a "
                                    "camelCase predicate describing HOW this concept relates to the target "
                                    "(e.g. 'attendee', 'assignedTo', 'partOf', 'relatesTo'). Only use this for "
                                    "stable structural relationships between two DIFFERENT concepts - never a "
                                    "concept pointing at itself, and never to express status/state (see "
                                    "'content' for that instead)."
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


def _handle_search_concepts(tool_input: dict) -> list[dict]:
    query = tool_input["query"]
    top_k = tool_input.get("top_k", 5)
    concept_type = tool_input.get("concept_type")
    results = retrieval.search(query, top_k=top_k, concept_type=concept_type)
    if not results:
        return [{"info": "No matching concepts found - this is likely new."}]
    return results


def _handle_get_related_concepts(tool_input: dict) -> list[dict]:
    concept_id = tool_input["concept_id"]
    return bundle.get_related_concepts(concept_id)


def extract_concepts_node(state: PipelineState) -> PipelineState:
    existing_types = registry.load_types()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    system = (
        f"Today's date is {today} (UTC) - use this, not any other assumption, "
        "whenever a concept_id needs a date (e.g. journal entries). "
        "You convert a person's chat message into OKF knowledge-bundle updates. "
        "Decide which concepts (people, projects, tasks, decisions, personal notes, journal "
        "entries, etc.) the message touches - there can be one or several, or none. "
        f"Existing registry types: {', '.join(existing_types)}. "
        "You do NOT have the bundle's contents pre-loaded. Before deciding ANY concept "
        "is new - including Tasks - you MUST call search_concepts to check whether a "
        "matching one already exists. This is not optional for Tasks: a task's wording "
        "often varies between messages about the same piece of work (e.g. 'object "
        "detection pipeline' vs 'the pipeline component'), so search using keywords "
        "from the work description itself, not only the person's or project's name. "
        "Reusing an existing Task's exact concept_id so its full history lives in one "
        "file matters more than matching the message's exact wording. "
        "Use get_related_concepts if you need to see what a concept is already linked "
        "to before adding relations. Only call extract_concepts once you've done "
        "whatever searching you need. "
        "IMPORTANT - this bundle belongs to a single person: the dashboard owner. They are "
        "the implicit user of the whole system, not a contact to track by default. The rule "
        "below applies to PROFESSIONAL reporting/assigning only: "
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
        "Small talk includes greetings, weather comments, and purely conversational filler "
        "with no lasting content - return an EMPTY concepts array for those, domain 'n/a'. "
        "It is correct and expected to touch nothing rather than force-fitting small talk "
        "onto an unrelated existing concept. However, small talk does NOT include durable "
        "personal facts the owner shares about themselves - hobbies, preferences, routines, "
        "life events, personal notes. For those, create or update a PersonalNote (or a more "
        "specific existing type if a better one fits) in the 'personal' domain, describing "
        "the owner as its subject in third person (e.g. 'The owner enjoys playing cricket'). "
        "This is a personal-domain exception to the owner-Person-concept rule above, which "
        "is about professional work reporting/assigning only. "
        "Whenever a concept has a clear real-world STRUCTURAL relationship to another "
        "concept (in this same batch, or an existing one found via search_concepts), "
        "express it in 'relations' with a short camelCase predicate - this is separate from "
        "'links_to', which is just for the human-readable body text. Populate both when a "
        "relationship applies. Relations are for stable structural edges only (assignedTo, "
        "partOf, attendee, etc) - NEVER use a relation to express a concept's own status or "
        "state, and NEVER have a concept's relation point at itself. Status/state (e.g. a "
        "task being complete, in progress, blocked) belongs in that concept's own 'content' "
        "as plain prose instead. "
        "When a message describes a person being assigned to specific, scoped work "
        "within a project (e.g. 'X to work on Y project's Z component/module/pipeline/"
        "workstream'), ALWAYS create a separate Task concept for that specific work - "
        "do not fold it into the Project's description text only. The Task should have "
        "'assignedTo' relating it to the Person, and 'partOf' relating it to the Project. "
        "Put 'assignedTo' ONLY on the Task (Task -> Person) - do not also add an "
        "'assignedTo' relation on the Person pointing back at the Task; that direction is "
        "redundant and reversed. "
        "When a message reports that a task has been completed, reuse that Task's existing "
        "concept_id (found via search_concepts) and update its 'content' to describe the "
        "completion in prose. Do not add a 'completed' relation anywhere, and do not create "
        "a new Task file for a completion update to work already tracked. "
        "Be consistent: identical message structures should always produce the same "
        "concept-splitting decision. "
        "You MUST always call extract_concepts with both the 'domain' field and the "
        "'concepts' field populated - never omit 'domain', even though it is a single "
        "enum choice. 'concepts' being an empty list is fine; omitting it is not."
    )
    user_message = (
        f"Dashboard owner (the single user of this tool - never a Person concept, "
        f"only ever the source/reporter of updates): {state['dashboard_owner']}\n"
        f"Message: {state['raw_message']}"
    )

    tools = [_build_search_tool(), _build_related_tool(), _build_extract_tool()]
    tool_handlers = {
        "search_concepts": _handle_search_concepts,
        "get_related_concepts": _handle_get_related_concepts,
    }

    result = call_agentic(
        system,
        user_message,
        tools=tools,
        tool_handlers=tool_handlers,
        final_tool_name="extract_concepts",
        required_keys=["domain", "concepts"],
    )

    # ADD THIS — print the exact prompt going to the LLM
    print("=" * 80)
    print("SYSTEM PROMPT:")
    print(system)
    print("-" * 80)
    print("USER MESSAGE:")
    print(user_message)
    print("=" * 80)

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

            if not bundle.concept_exists(concept_id):
                similar = bundle.find_similar_concept(sanitized_type, concept["title"])
                if similar:
                    print(
                        f"[write_concepts_node] Redirecting new '{concept_id}' "
                        f"onto existing similar concept '{similar}'"
                    )
                    concept_id = similar

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
                if rel["target_concept_id"] == concept_id:
                    print(f"[write_concepts_node] Skipped self-referencing relation on '{concept_id}': {rel['predicate']}")
                    continue
                bundle.add_relation(concept_id, rel["predicate"], rel["target_concept_id"])

                # Guarantee a human-readable body link BOTH directions whenever a
                # structural relation exists, regardless of what links_to said —
                # code-level guardrail so no relation ever leaves an orphan node.
                target_title = bundle.get_title(rel["target_concept_id"]) or rel["target_concept_id"]
                bundle.add_link(rel["target_concept_id"], f"See [{concept['title']}](/{concept_id}.md).")
                bundle.add_link(concept_id, f"See [{target_title}](/{rel['target_concept_id']}.md).")

            written.append({
                "concept_id": concept_id,
                "type": sanitized_type,
                "action": action,
                "path": str(path),
            })
        except bundle.UnsafeConceptIdError as e:
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