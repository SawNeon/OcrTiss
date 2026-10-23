from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

DEFAULT_RENDER_DPI = 300
DEFAULT_OPENAI_MODEL = "gpt-4o"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    llm_fallback_enabled: bool
    template_reader_enabled: bool
    render_dpi: int

    @property
    def llm_available(self) -> bool:
        return self.llm_fallback_enabled and bool(self.openai_api_key)


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        llm_fallback_enabled=_read_bool("LLM_FALLBACK_ENABLED"),
        template_reader_enabled=_read_bool("TEMPLATE_READER_ENABLED", default=True),
        render_dpi=_read_int("RENDER_DPI", DEFAULT_RENDER_DPI),
    )
