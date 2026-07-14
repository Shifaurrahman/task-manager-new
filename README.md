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

A message hits `POST /message`. A LangGraph pipeline (1) asks Claude to
identify every distinct "concept" the message touches (a person, a project, a
task, an idea — zero, one, or several) and whether each is new or an update to
something existing, (2) writes/updates each concept as a markdown file with
YAML frontmatter, cross-linking related concepts, (3) regenerates that
folder's `log.md` (dated changelog) and `index.md` (table of contents). The
next message's extraction step reads those same files back — fuzzy-matched
relevant concepts plus every folder's `index.md` — so the model can reuse
existing files instead of creating duplicates.

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
│   │   └── client.py            # Claude Sonnet 5 wrapper - forced tool calls,
│   │                             #   missing-field retry (proper tool_result format)
│   ├── okf/
│   │   ├── __init__.py
│   │   ├── frontmatter.py       # read/write YAML frontmatter concept files
│   │   ├── bundle.py            # concept file I/O, list_concepts(), list_index_files(),
│   │   │                         #   log.md / index.md maintenance
│   │   ├── registry.py          # concept type registry - seeds from config/seed_types.json,
│   │   │                         #   grows automatically as the LLM invents new types
│   │   └── retrieval.py         # top-K relevant concept lookup (fuzzy match via rapidfuzz),
│   │                             #   swappable strategy via config/retrieval.json
│   └── graph/
│       ├── __init__.py
│       ├── state.py              # LangGraph state schema (TypedDicts)
│       ├── nodes.py              # extract_concepts -> write_concepts -> update_meta
│       └── build_graph.py        # wires the three nodes into a StateGraph
├── config/                       # data-driven settings - edit these, not .py files
│   ├── seed_types.json           # starting concept types (Person, Project, Task, ...)
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
| `extract_concepts_node` | Builds a prompt with: today's date, the type registry, fuzzy-matched existing concepts, every folder's `index.md`, and the single fixed `owner_name`. Forces a structured tool call returning `domain` + a list of concept touches (can be empty). |
| `write_concepts_node` | For each concept: creates or appends to its `.md` file (backfilling missing frontmatter on legacy files), registers any new type, writes cross-link lines into related concepts. |
| `update_meta_node` | Appends a dated entry to the nearest `log.md`, regenerates `index.md` for every touched directory. |

### Key design rules baked into the extraction prompt

- **Single owner, not a tracked contact** — the dashboard owner (`config.py` → `owner_name`) never gets their own Person file *unless* they explicitly self-reference as a participant ("I need to work on X"). Reporting/assigning someone else's work never touches the owner's file.
- **Empty responses are valid** — small talk or content with no durable knowledge value should return zero concepts, not be force-fit onto an unrelated existing file.
- **Reuse over duplication** — the model is shown existing concept IDs and told to reuse them, not invent near-duplicates.
- **Types are open-vocabulary** — `config/seed_types.json` only seeds the starting list; the LLM can invent new types freely, and they persist automatically to `data/bundle/types.json`.

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
