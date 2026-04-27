from __future__ import annotations

import mimetypes
from io import BytesIO

from backend.config import settings
from backend.services.exceptions import OpenAIConfigurationError

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    OpenAI = None


class SpeechToTextService:
    def __init__(self) -> None:
        self.client = None
        if OpenAI and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def transcribe(self, audio_bytes: bytes, filename: str | None, content_type: str | None) -> str:
        if not self.client:
            raise OpenAIConfigurationError("Set OPENAI_API_KEY to enable transcription.")

        audio_file = BytesIO(audio_bytes)
        audio_file.name = _safe_filename(filename, content_type)

        transcription = self.client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=audio_file,
        )
        text = getattr(transcription, "text", None)
        if not text and isinstance(transcription, dict):
            text = transcription.get("text")
        if not text:
            raise RuntimeError("Transcription returned no text.")

        return str(text).strip()


def _safe_filename(filename: str | None, content_type: str | None) -> str:
    if filename and "." in filename:
        return filename

    extension = mimetypes.guess_extension(content_type or "") or ".webm"
    if extension == ".weba":
        extension = ".webm"
    return f"speech{extension}"
