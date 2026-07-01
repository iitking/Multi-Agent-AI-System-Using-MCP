"""Central configuration, read from environment variables (a .env file is supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # never overrides variables that are already set

ROLES = ("viewer", "analyst", "admin")

_DEV_API_KEYS = (
    "dev-admin-key:admin:admin,"
    "dev-analyst-key:analyst:analyst,"
    "dev-viewer-key:viewer:viewer"
)


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _opt(name: str) -> str | None:
    value = _env(name)
    return value or None


def _parse_api_keys(raw: str) -> dict[str, tuple[str, str]]:
    """Parse ``key:user:role,key:user:role`` into ``{key: (user, role)}``."""
    keys: dict[str, tuple[str, str]] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3 or parts[2] not in ROLES:
            raise ValueError(f"API_KEYS entries must look like key:user:role (role in {ROLES}).")
        keys[parts[0]] = (parts[1], parts[2])
    return keys


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_dir: Path
    docs_dir: Path
    reports_dir: Path
    analytics_db_url: str  # writable; used only by the seeding script
    analytics_readonly_db_url: str | None  # read-only credentials for analytics (optional)
    app_db_url: str
    openai_api_key: str | None
    openai_model: str
    openai_base_url: str | None
    llm_price_in_per_1k: float
    llm_price_out_per_1k: float
    max_review_retries: int
    mcp_tool_timeout: float
    api_keys: dict[str, tuple[str, str]]
    cors_origins: list[str]
    rate_limit_per_minute: int
    n8n_webhook_url: str | None
    n8n_webhook_secret: str | None
    allowed_email_domains: list[str]


@lru_cache
def get_settings() -> Settings:
    app_env = _env("APP_ENV", "development")
    data_dir = Path(_env("DATA_DIR", str(ROOT / "data"))).resolve()

    raw_keys = _env("API_KEYS")
    if not raw_keys:
        if app_env == "production":
            raise RuntimeError("API_KEYS must be set when APP_ENV=production.")
        raw_keys = _DEV_API_KEYS

    return Settings(
        app_env=app_env,
        data_dir=data_dir,
        docs_dir=Path(_env("DOCS_DIR", str(data_dir / "company_docs"))).resolve(),
        reports_dir=Path(_env("REPORTS_DIR", str(data_dir / "reports"))).resolve(),
        analytics_db_url=_env("ANALYTICS_DATABASE_URL", f"sqlite:///{(data_dir / 'sales.db').as_posix()}"),
        analytics_readonly_db_url=_opt("ANALYTICS_READONLY_DATABASE_URL"),
        app_db_url=_env("APP_DATABASE_URL", f"sqlite:///{(data_dir / 'app.db').as_posix()}"),
        openai_api_key=_opt("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=_opt("OPENAI_BASE_URL"),
        llm_price_in_per_1k=float(_env("LLM_PRICE_IN_PER_1K", "0.00015")),
        llm_price_out_per_1k=float(_env("LLM_PRICE_OUT_PER_1K", "0.0006")),
        max_review_retries=int(_env("MAX_REVIEW_RETRIES", "2")),
        mcp_tool_timeout=float(_env("MCP_TOOL_TIMEOUT", "30")),
        api_keys=_parse_api_keys(raw_keys),
        cors_origins=[o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
        rate_limit_per_minute=int(_env("RATE_LIMIT_PER_MINUTE", "60")),
        n8n_webhook_url=_opt("N8N_WEBHOOK_URL"),
        n8n_webhook_secret=_opt("N8N_WEBHOOK_SECRET"),
        allowed_email_domains=[d.strip().lower() for d in _env("ALLOWED_EMAIL_DOMAINS").split(",") if d.strip()],
    )
