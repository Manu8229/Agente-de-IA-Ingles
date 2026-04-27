from __future__ import annotations

from backend.config import settings
from backend.services.exceptions import OpenAIConfigurationError

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    OpenAI = None


class TextToSpeechService:
    def __init__(self) -> None:
        self.client = None
        if OpenAI and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def synthesize(self, text: str) -> bytes:
        if not self.client:
            raise OpenAIConfigurationError("Set OPENAI_API_KEY to enable speech output.")

        response = self.client.audio.speech.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=text,
            response_format="mp3",
        )

        if isinstance(response, bytes):
            return response

        content = getattr(response, "content", None)
        if content:
            return bytes(content)

        if hasattr(response, "read"):
            return response.read()

        raise RuntimeError("Speech endpoint returned an unsupported response.")
