"""
Retrieves the top-K existing concepts most relevant to an incoming message,
instead of dumping the entire bundle into every extraction prompt.

Swappable by config, not code: config/retrieval.json picks the strategy by
name. To add a new method (e.g. an embedding-based retriever), implement
ConceptRetriever, register it in _STRATEGIES below, then flip the "strategy"
value in config/retrieval.json - nodes.py and everything else calling
get_relevant_concepts() needs no changes.
"""

from typing import Protocol

from app.config import settings
from app.okf import bundle

_FALLBACK_RETRIEVAL_CONFIG = {"strategy": "fuzzy", "top_k": 15}


class ConceptRetriever(Protocol):
    def retrieve(self, message: str, concepts: list[dict], top_k: int) -> list[dict]:
        ...


class FuzzyRetriever:
    """Lexical fuzzy-match scoring via rapidfuzz. No embeddings, no external
    calls, no extra infra - good enough until recall against oblique phrasing
    (e.g. "the RAG bot" vs "multimodal-rag-chatbot") starts to matter."""

    def retrieve(self, message: str, concepts: list[dict], top_k: int) -> list[dict]:
        from rapidfuzz import fuzz

        message_lower = message.lower()
        scored = []
        for concept in concepts:
            haystack = f"{concept['title']} {concept['concept_id']}".lower()
            score = fuzz.partial_ratio(message_lower, haystack)
            scored.append((score, concept))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [concept for _, concept in scored[:top_k]]


# Register new strategies here by name - the name is what config/retrieval.json points at.
_STRATEGIES: dict[str, type] = {
    "fuzzy": FuzzyRetriever,
}


def _load_retrieval_config() -> dict:
    try:
        return settings.load_json_config(settings.retrieval_config_path)
    except FileNotFoundError:
        return dict(_FALLBACK_RETRIEVAL_CONFIG)


def get_relevant_concepts(message: str) -> list[dict]:
    config = _load_retrieval_config()
    top_k = config.get("top_k", _FALLBACK_RETRIEVAL_CONFIG["top_k"])
    strategy_name = config.get("strategy", _FALLBACK_RETRIEVAL_CONFIG["strategy"])

    all_concepts = bundle.list_concepts()
    if len(all_concepts) <= top_k:
        return all_concepts

    retriever_cls = _STRATEGIES.get(strategy_name, FuzzyRetriever)
    return retriever_cls().retrieve(message, all_concepts, top_k)