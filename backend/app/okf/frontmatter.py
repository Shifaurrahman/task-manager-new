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


def save(post: frontmatter.Post, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)