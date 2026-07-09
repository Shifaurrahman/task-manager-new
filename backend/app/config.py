import json
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    bundle_root: str = "./data/bundle"
    model: str = "claude-sonnet-5"

    # Data-driven config - edit these files, not Python, to change behavior.
    seed_types_path: str = "./config/seed_types.json"
    domains_path: str = "./config/domains.json"
    retrieval_config_path: str = "./config/retrieval.json"

    class Config:
        env_file = ".env"

    @property
    def bundle_path(self) -> Path:
        return Path(self.bundle_root).resolve()

    def load_json_config(self, path_str: str):
        path = Path(path_str).resolve()
        return json.loads(path.read_text())


settings = Settings()