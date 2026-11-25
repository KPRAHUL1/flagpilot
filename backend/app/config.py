from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Runtime configuration loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI Provider (Google Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Flagsmith Management API & MCP
    flagsmith_api_url: str = "https://api.flagsmith.com/api/v1"
    flagsmith_mcp_url: str = "https://mcp.flagsmith.com"
    flagsmith_org_api_key: str = ""
    flagsmith_project_id: str = ""
    flagsmith_environment_id: str = ""
    flagsmith_environment_key: str = ""

    # Target Repository & GitHub PR Automation
    target_repo_path: str = "./demo-app"
    github_repo: str = ""

    # Server Ports
    backend_port: int = 8000
    frontend_port: int = 5173
    demo_app_port: int = 5174

    def resolved_target_repo(self) -> Path:
        raw = Path(self.target_repo_path)
        return raw if raw.is_absolute() else (ROOT_DIR / raw).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
