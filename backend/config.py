from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    openai_stt_model: str = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    openai_tts_model: str = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    openai_tts_voice: str = os.getenv("OPENAI_TTS_VOICE", "alloy")
    database_path: Path = Path(
        os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "english_agent.sqlite3"))
    )
    cors_origins: tuple[str, ...] = _csv_env(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    )
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))


settings = Settings()
