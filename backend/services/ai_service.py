from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    OpenAI = None


SYSTEM_PROMPT = """You are an English teacher for beginners. Teach like a child is learning.
Use short sentences.
Speak slowly.
Repeat important words.
Always correct mistakes gently.
Always encourage the user.
After correcting, continue the conversation.
Never be overly technical."""

JSON_INSTRUCTIONS = """Return only valid JSON with this exact shape:
{
  "original": "user sentence",
  "corrected": "correct sentence",
  "explanation": "simple explanation",
  "response": "AI conversational reply",
  "repeat": ["word1", "word2"],
  "translation": {
    "corrected_pt": "Brazilian Portuguese meaning of corrected sentence",
    "response_pt": "Brazilian Portuguese meaning of response"
  }
}

Rules:
- Keep every field short.
- Explanation must be simple and friendly.
- Response must continue the conversation with one short question.
- repeat must include 1 to 4 important words or phrases.
- Ask the student to repeat one short phrase when that helps.
- translation must be natural Brazilian Portuguese.
- Do not speak Portuguese in response. Use Portuguese only in translation.
"""

WORK_MODE_INSTRUCTIONS = """The user is practicing industrial workplace English.
Prefer simple work vocabulary when it fits:
- Check the machine.
- The alarm is active.
- Production stopped.
- The line is running.
- I need help."""


class AIService:
    def __init__(self) -> None:
        self.client = None
        if OpenAI and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_tutor_response(
        self,
        transcript: str,
        history: list[dict[str, str]],
        struggle_words: list[str],
        mode: str,
    ) -> dict[str, Any]:
        if not self.client:
            return self._fallback_response(
                transcript,
                warning="OPENAI_API_KEY is not configured. Using local fallback.",
            )

        messages = self._build_messages(transcript, history, struggle_words, mode)

        try:
            completion = self.client.chat.completions.create(
                model=settings.openai_chat_model,
                messages=messages,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
        except Exception:
            completion = self.client.chat.completions.create(
                model=settings.openai_chat_model,
                messages=messages,
                temperature=0.4,
            )

        content = completion.choices[0].message.content or ""
        try:
            parsed = _parse_json(content)
        except ValueError:
            return self._fallback_response(
                transcript,
                warning="The AI response was not valid JSON. Using local fallback.",
            )

        return _sanitize_response(parsed, transcript)

    def generate_lesson_start(self, struggle_words: list[str], mode: str) -> dict[str, Any]:
        repeat = struggle_words[:2]

        if mode == "work":
            if not repeat:
                repeat = ["check", "machine"]
            return {
                "response": (
                    "Hi. I am your English teacher. Listen and repeat: "
                    "Check the machine. Now say: I check the machine."
                ),
                "repeat": repeat,
                "translation": {
                    "response_pt": (
                        "Oi. Eu sou seu professor de ingles. Escute e repita: "
                        "Verifique a maquina. Agora diga: Eu verifico a maquina."
                    )
                },
            }

        if not repeat:
            repeat = ["hello", "ready"]
        return {
            "response": (
                "Hi. I am your English teacher. We will speak slowly. "
                "Listen and repeat: I am ready. Now say: I am ready."
            ),
            "repeat": repeat,
            "translation": {
                "response_pt": (
                    "Oi. Eu sou seu professor de ingles. Vamos falar devagar. "
                    "Escute e repita: Eu estou pronto. Agora diga: Eu estou pronto."
                )
            },
        }

    def build_spoken_text(self, tutor_result: dict[str, Any]) -> str:
        original = tutor_result["original"].strip().lower()
        corrected = tutor_result["corrected"].strip()
        parts = []

        if corrected and corrected.lower() != original:
            parts.append(f"Good job. The correct way is: {corrected}.")

        repeat = tutor_result.get("repeat") or []
        if repeat:
            parts.append("Repeat: " + ", ".join(repeat[:3]) + ".")

        parts.append(tutor_result["response"])
        return " ".join(part for part in parts if part)

    def _build_messages(
        self,
        transcript: str,
        history: list[dict[str, str]],
        struggle_words: list[str],
        mode: str,
    ) -> list[dict[str, str]]:
        system_content = SYSTEM_PROMPT + "\n\n" + JSON_INSTRUCTIONS
        if mode == "work":
            system_content += "\n\n" + WORK_MODE_INSTRUCTIONS

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        repeat_context = ", ".join(struggle_words) if struggle_words else "none"
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Student said: {transcript}\n"
                    f"Words to reinforce: {repeat_context}\n"
                    "Correct gently. Then teach actively with one short phrase "
                    "for the student to repeat or answer."
                ),
            }
        )
        return messages

    def _fallback_response(self, transcript: str, warning: str | None = None) -> dict[str, Any]:
        corrected = _simple_correction(transcript)
        repeat = _repeat_words(transcript, corrected)
        response = "Nice try. Tell me one more simple sentence."

        if "machine" in transcript.lower() or "work" in transcript.lower():
            response = "Good. What happened at work today?"

        result = {
            "original": transcript,
            "corrected": corrected,
            "explanation": "Small change. Say it this way.",
            "response": response,
            "repeat": repeat,
            "translation": {
                "corrected_pt": _fallback_translate(corrected),
                "response_pt": _fallback_translate(response),
            },
        }
        if warning:
            result["warning"] = warning
        return result


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found.")

    return json.loads(cleaned[start : end + 1])


def _sanitize_response(parsed: dict[str, Any], transcript: str) -> dict[str, Any]:
    original = str(parsed.get("original") or transcript).strip()
    corrected = str(parsed.get("corrected") or original).strip()
    explanation = str(parsed.get("explanation") or "Small change. Say it this way.").strip()
    response = str(parsed.get("response") or "Good. Tell me more.").strip()
    repeat_raw = parsed.get("repeat") if isinstance(parsed.get("repeat"), list) else []
    repeat = [str(word).strip() for word in repeat_raw if str(word).strip()][:4]
    translation_raw = parsed.get("translation")
    translation = translation_raw if isinstance(translation_raw, dict) else {}

    return {
        "original": original,
        "corrected": corrected or original,
        "explanation": explanation,
        "response": response,
        "repeat": repeat,
        "translation": {
            "corrected_pt": str(translation.get("corrected_pt") or "").strip(),
            "response_pt": str(translation.get("response_pt") or "").strip(),
        },
    }


def _simple_correction(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()

    replacements = {
        "i go work yesterday": "I went to work yesterday.",
        "i go to work yesterday": "I went to work yesterday.",
        "he don't": "He does not",
        "she don't": "She does not",
        "i am agree": "I agree.",
        "i have": "I have",
    }

    if lowered in replacements:
        return replacements[lowered]

    corrected = re.sub(r"\bi\b", "I", stripped, flags=re.IGNORECASE)
    if corrected and corrected[-1] not in ".!?":
        corrected += "."
    return corrected[:1].upper() + corrected[1:] if corrected else stripped


def _repeat_words(original: str, corrected: str) -> list[str]:
    if original.strip().lower() == corrected.strip().lower():
        words = re.findall(r"[a-zA-Z][a-zA-Z']*", corrected.lower())
        return list(dict.fromkeys(words[:2])) or ["hello"]

    original_words = set(re.findall(r"[a-zA-Z][a-zA-Z']*", original.lower()))
    corrected_words = re.findall(r"[a-zA-Z][a-zA-Z']*", corrected.lower())
    changed = [word for word in corrected_words if word not in original_words]
    return list(dict.fromkeys(changed[:3])) or ["try again"]


def _fallback_translate(text: str) -> str:
    translations = {
        "I went to work yesterday.": "Eu fui trabalhar ontem.",
        "Nice try. Tell me one more simple sentence.": (
            "Boa tentativa. Diga mais uma frase simples."
        ),
        "Good. What happened at work today?": "Bom. O que aconteceu no trabalho hoje?",
        "I agree.": "Eu concordo.",
    }
    return translations.get(text.strip(), "")
