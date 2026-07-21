from datetime import datetime, timezone
from pathlib import Path

import frontmatter


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> frontmatter.Post | None:
    if not path.exists():
        return None
    return frontmatter.load(path)


def new_post(type_: str, title: str, description: str, body: str) -> frontmatter.Post:
    post = frontmatter.Post(body)
    post["type"] = type_
    post["title"] = title
    post["description"] = description
    post["timestamp"] = now_iso()
    return post


def append_body(post: frontmatter.Post, addition: str) -> None:
    post.content = post.content.rstrip() + "\n\n" + addition.strip() + "\n"
    post["timestamp"] = now_iso()


def set_relation(post: frontmatter.Post, predicate: str, target_concept_id: str) -> None:
    """Set a typed relation as a frontmatter field, Vault-LD wikilink style.
    Stores the full concept_id (not just filename stem) to stay collision-safe
    across folders (e.g. professional/people/x vs personal/journal/x)."""
    wikilink = f"[[{target_concept_id}]]"
    existing = post.get(predicate)
    if existing is None:
        post[predicate] = wikilink
    elif isinstance(existing, list):
        if wikilink not in existing:
            existing.append(wikilink)
    else:
        if existing != wikilink:
            post[predicate] = [existing, wikilink]
    post["timestamp"] = now_iso()


def touch_timestamp(post: frontmatter.Post) -> None:
    """Update just the timestamp - used by callers (like remove_relation()) that
    mutate frontmatter directly instead of through set_relation()/append_body(),
    so the file's 'last modified' still reflects the change."""
    post["timestamp"] = now_iso()


def save(post: frontmatter.Post, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)