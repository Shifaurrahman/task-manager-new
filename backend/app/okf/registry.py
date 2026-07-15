import json
import re

from app.config import settings

REGISTRY_PATH = settings.bundle_path / "types.json"

# Minimal Python fallback, used only if config/seed_types.json is missing -
# the real source of truth is that file, edit it there, not here.
_FALLBACK_SEED_TYPES = ["Person", "Project", "Task"]


def _load_seed_types() -> list[str]:
    try:
        return settings.load_json_config(settings.seed_types_path)
    except FileNotFoundError:
        return list(_FALLBACK_SEED_TYPES)


def sanitize_type(type_name: str) -> str:
    """Force PascalCase, no spaces - keeps type values URI-safe for any future
    RDF/graph export, regardless of what the LLM actually returned."""
    words = re.findall(r"[A-Za-z0-9]+", type_name)
    return "".join(w.capitalize() for w in words) or "Unknown"


def load_types() -> list[str]:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    seed_types = _load_seed_types()
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(seed_types, indent=2))
    return seed_types


def register_type(type_name: str) -> None:
    type_name = sanitize_type(type_name)
    types = load_types()
    if type_name not in types:
        types.append(type_name)
        REGISTRY_PATH.write_text(json.dumps(types, indent=2))