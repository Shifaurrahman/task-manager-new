# task-manager-new

A personal task/knowledge manager for **one person**. You type natural-language
chat messages ("Assign Piyal to the RAG chatbot project"), and the system uses
Claude Sonnet 5 + LangGraph to turn them into a structured, cross-linked
markdown knowledge base (an [OKF](https://github.com/) bundle) — one `.md`
file per person/project/task/idea/etc., auto-organized into folders,
auto-cross-linked, auto-indexed.

FastAPI backend + React (Tailwind, Vite, JS) frontend.

---

## How it works, in one paragraph

A message hits `POST /message`. A LangGraph pipeline (1) runs an **agentic
extraction step** where Claude decides for itself which existing concepts
(people, projects, tasks, decisions, etc.) are relevant — calling a
`search_concepts` tool (fuzzy match) and a `get_related_concepts` tool
(1-hop graph lookup on existing typed relations) as many times as it needs,
rather than having the whole bundle pre-loaded into the prompt — before
finally calling `extract_concepts` to report every concept the message
touches and how to update each, including typed `relations` between them
(e.g. a task `assignedTo` a person, `partOf` a project); (2) writes/updates
each concept as a markdown file with YAML frontmatter, cross-linking related
concepts both as human-readable body links and as machine-readable
`[[wikilink]]`-style relation fields; (3) regenerates that folder's `log.md`
(dated changelog) and `index.md` (table of contents).

---

## Backend structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, POST /message endpoint
│   ├── config.py                # settings: API key, model, owner_name, config file paths
│   ├── models.py                # request/response schemas
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py            # Claude Sonnet 5 wrapper:
│   │                             #   - call_with_tool(): single forced tool call, missing-field retry
│   │                             #   - call_agentic(): multi-turn tool loop - model freely chooses
│   │                             #     retrieval tools (search_concepts, get_related_concepts) as
│   │                             #     many times as it wants before calling the final structured
│   │                             #     tool (extract_concepts)
│   ├── okf/
│   │   ├── __init__.py
│   │   ├── frontmatter.py       # read/write YAML frontmatter concept files; set_relation()
│   │   │                         #   writes typed [[wikilink]]-style relation fields
│   │   ├── bundle.py            # concept file I/O, list_concepts(), list_index_files(),
│   │   │                         #   add_relation(), get_related_concepts() (1-hop graph lookup),
│   │   │                         #   log.md / index.md maintenance
│   │   ├── registry.py          # concept type registry - seeds from config/seed_types.json,
│   │   │                         #   grows automatically as the LLM invents new types;
│   │   │                         #   sanitize_type() forces PascalCase/no-spaces for URI-safety
│   │   └── retrieval.py         # fuzzy match (rapidfuzz) via two entry points:
│   │                             #   - get_relevant_concepts(): static top-K batch (legacy/other callers)
│   │                             #   - search(query, top_k, concept_type): on-demand, called by the
│   │                             #     search_concepts tool during agentic extraction
│   └── graph/
│       ├── __init__.py
│       ├── state.py              # LangGraph state schema (TypedDicts)
│       ├── nodes.py              # extract_concepts (agentic) -> write_concepts -> update_meta
│       └── build_graph.py        # wires the three nodes into a StateGraph
├── config/                       # data-driven settings - edit these, not .py files
│   ├── seed_types.json           # starting concept types (Person, Project, Task, ...) - PascalCase
│   ├── domains.json               # valid top-level bundle sections (professional, personal)
│   └── retrieval.json             # {"strategy": "fuzzy", "top_k": 15}
├── data/
│   └── bundle/                    # the actual OKF knowledge bundle lives here
│       ├── types.json              # full grown type registry (seeded from config/, then
│       │                            #   appended to at runtime - never hand-edit)
│       └── professional/, personal/  # concept files, organized by the LLM at write time
├── requirements.txt
└── .env / .env.example
```

### Pipeline detail (`app/graph/nodes.py`)

| Node | Job |
|---|---|
| `extract_concepts_node` | Runs an agentic tool-use loop (`call_agentic`): Claude is given `search_concepts`, `get_related_concepts`, and `extract_concepts` as tools, with no fixed bundle context pre-loaded into the prompt. It calls the retrieval tools on demand — as many times as needed, once per person/project/task it's unsure about — then calls `extract_concepts` with its final answer (`domain` + a list of concept touches, each with optional typed `relations`). |
| `write_concepts_node` | For each concept: creates or appends to its `.md` file (backfilling missing frontmatter on legacy files), sanitizes and registers its type (PascalCase, no spaces), writes human-readable cross-links (`links_to`), and writes typed machine-readable relations (`relations`) as `[[wikilink]]`-style frontmatter fields via `bundle.add_relation()`. |
| `update_meta_node` | Appends a dated entry to the nearest `log.md`, regenerates `index.md` for every touched directory. |

### Key design rules baked into the extraction prompt

- **Single owner, not a tracked contact** — the dashboard owner (`config.py` → `owner_name`) never gets their own Person file *unless* they explicitly self-reference as a participant ("I need to work on X"). Reporting/assigning someone else's work never touches the owner's file.
- **Empty responses are valid** — small talk or content with no durable knowledge value should return zero concepts, not be force-fit onto an unrelated existing file.
- **Agentic retrieval over static context injection** — instead of pre-loading a fixed batch of "relevant" concepts and every folder's `index.md` into every prompt (which scales poorly and pulls in irrelevant context), the model calls `search_concepts`/`get_related_concepts` itself, only for what it actually needs, before deciding whether to reuse or create a concept.
- **Reuse over duplication** — the model is expected to search before creating, and reuse an existing `concept_id` rather than inventing a near-duplicate.
- **Typed relations, not just prose links** — concepts can carry a `relations` array (e.g. `assignedTo`, `partOf`, `hasTask`) alongside the existing human-readable `links_to` body links, giving the bundle a machine-traversable graph structure in addition to being human-readable.
- **Types are open-vocabulary, but sanitized** — `config/seed_types.json` only seeds the starting list; the LLM can invent new types freely, but `registry.sanitize_type()` forces them into PascalCase/no-spaces form before they're persisted, keeping type values safe for any downstream graph/URI use.

---

## Frontend structure

```
frontend/my-project/
├── vite.config.js              # registers the Tailwind v4 plugin
└── src/
    ├── main.jsx                  # Vite/React entry point (unmodified scaffold)
    ├── index.css                  # Tailwind import
    ├── api.js                     # sendMessage(message) -> POST /message
    ├── App.jsx                    # root: composer + result feed (no owner field -
    │                                #   single-person tool, owner is fixed server-side)
    └── components/
        ├── Composer.jsx            # chat input, posts to the backend
        └── ResultCard.jsx          # shows which concept files were created/updated per message
```

---

## Setup

**Backend**
```bash
cd backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env       # then paste your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend/my-project
npm install
npm run dev
```

Frontend expects the backend at `http://127.0.0.1:8000` by default (override
with a `VITE_API_BASE` env var if needed).

---

