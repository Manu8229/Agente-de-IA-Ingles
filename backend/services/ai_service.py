from __future__ import annotations

import json
import re
from typing import Any

from backend.config import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is listed in requirements.txt
    OpenAI = None


SYSTEM_PROMPT = """You are a bilingual English teacher for Brazilian beginners.
Explain the task in simple Brazilian Portuguese.
Use English only for the phrase the student must practice.
Teach like a child is learning.
Use short sentences.
Correct mistakes gently.
Never be overly technical."""

JSON_INSTRUCTIONS = """Return only valid JSON with this exact shape:
{
  "original": "user sentence",
  "corrected": "correct sentence",
  "explanation": "simple correction in Brazilian Portuguese",
  "response": "teacher instruction in Brazilian Portuguese",
  "repeat": ["word1", "word2"],
  "next_phrase": "short phrase the student should say next",
  "translation": {
    "corrected_pt": "Brazilian Portuguese meaning of corrected sentence",
    "response_pt": "same Brazilian Portuguese teacher instruction",
    "next_phrase_pt": "Brazilian Portuguese meaning of next_phrase"
  }
}

Rules:
- Keep every field short.
- Explanation must be simple, friendly, and in Brazilian Portuguese.
- Response must be in Brazilian Portuguese and explain what the student should do next.
- repeat must include 1 to 4 important words or phrases.
- Ask the student to repeat one short phrase when that helps.
- next_phrase must be short and useful for the selected level and topic.
- translation must be natural Brazilian Portuguese.
- The student should speak English. The teacher may guide in Portuguese.
"""

WORK_MODE_INSTRUCTIONS = """The user is practicing industrial workplace English.
Prefer simple work vocabulary when it fits:
- Check the machine.
- The alarm is active.
- Production stopped.
- The line is running.
- I need help."""

LESSON_STARTS = {
    ("beginner_1", "daily"): {
        "expected_phrase": "I am ready.",
        "translation": "Eu estou pronto.",
        "response": (
            "Vamos praticar ingles de um jeito simples. "
            "Eu explico em portugues e voce repete em ingles. "
            "Frase em ingles: I am ready. Repita: I am ready."
        ),
        "response_pt": (
            "Vamos praticar ingles de um jeito simples. "
            "Eu explico em portugues e voce repete em ingles."
        ),
        "repeat": ["hello", "ready"],
    },
    ("beginner_2", "daily"): {
        "expected_phrase": "I worked yesterday.",
        "translation": "Eu trabalhei ontem.",
        "response": (
            "Agora vamos praticar uma frase no passado. "
            "Frase em ingles: I worked yesterday. Repita: I worked yesterday."
        ),
        "response_pt": (
            "Agora vamos praticar uma frase no passado."
        ),
        "repeat": ["worked", "yesterday"],
    },
    ("beginner_1", "work"): {
        "expected_phrase": "I check the machine.",
        "translation": "Eu verifico a maquina.",
        "response": (
            "Vamos praticar ingles do trabalho. "
            "Frase em ingles: I check the machine. Repita: I check the machine."
        ),
        "response_pt": (
            "Vamos praticar ingles do trabalho."
        ),
        "repeat": ["check", "machine"],
    },
    ("beginner_2", "work"): {
        "expected_phrase": "Production stopped yesterday.",
        "translation": "A producao parou ontem.",
        "response": (
            "Agora vamos praticar uma frase de producao no passado. "
            "Frase em ingles: Production stopped yesterday. Repita: Production stopped yesterday."
        ),
        "response_pt": (
            "Agora vamos praticar uma frase de producao no passado."
        ),
        "repeat": ["production", "stopped"],
    },
    ("beginner_1", "travel"): {
        "expected_phrase": "I need a taxi.",
        "translation": "Eu preciso de um taxi.",
        "response": (
            "Vamos praticar ingles para viagem. "
            "Frase em ingles: I need a taxi. Repita: I need a taxi."
        ),
        "response_pt": (
            "Vamos praticar ingles para viagem."
        ),
        "repeat": ["need", "taxi"],
    },
    ("beginner_2", "travel"): {
        "expected_phrase": "Where is the hotel?",
        "translation": "Onde fica o hotel?",
        "response": (
            "Vamos praticar uma pergunta de viagem. "
            "Frase em ingles: Where is the hotel? Repita: Where is the hotel?"
        ),
        "response_pt": (
            "Vamos praticar uma pergunta de viagem."
        ),
        "repeat": ["where", "hotel"],
    },
    ("beginner_1", "routine"): {
        "expected_phrase": "I drink coffee.",
        "translation": "Eu bebo cafe.",
        "response": (
            "Vamos praticar uma frase da sua rotina. "
            "Frase em ingles: I drink coffee. Repita: I drink coffee."
        ),
        "response_pt": (
            "Vamos praticar uma frase da sua rotina."
        ),
        "repeat": ["drink", "coffee"],
    },
    ("beginner_2", "routine"): {
        "expected_phrase": "I wake up early.",
        "translation": "Eu acordo cedo.",
        "response": (
            "Agora vamos praticar uma frase um pouco maior de rotina. "
            "Frase em ingles: I wake up early. Repita: I wake up early."
        ),
        "response_pt": (
            "Agora vamos praticar uma frase um pouco maior de rotina."
        ),
        "repeat": ["wake", "early"],
    },
}

TOPIC_INSTRUCTIONS = {
    "daily": "The student is practicing simple daily conversation.",
    "travel": "The student is practicing simple travel English.",
    "routine": "The student is practicing daily routine sentences.",
    "work": WORK_MODE_INSTRUCTIONS,
}

LEVEL_INSTRUCTIONS = {
    "beginner_1": "Use very short present-tense sentences with common words.",
    "beginner_2": "Use short sentences. Introduce simple past time and questions.",
}


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
        level: str = "beginner_1",
        topic: str | None = None,
        expected_phrase: str | None = None,
    ) -> dict[str, Any]:
        level = normalize_level(level)
        topic = normalize_topic(topic or mode)
        if not self.client:
            return self._fallback_response(
                transcript,
                warning="OPENAI_API_KEY is not configured. Using local fallback.",
            )

        messages = self._build_messages(
            transcript,
            history,
            struggle_words,
            mode,
            level=level,
            topic=topic,
            expected_phrase=expected_phrase,
        )

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

    def generate_lesson_start(
        self,
        struggle_words: list[str],
        mode: str,
        level: str = "beginner_1",
        topic: str | None = None,
    ) -> dict[str, Any]:
        level = normalize_level(level)
        topic = normalize_topic(topic or mode)
        lesson = LESSON_STARTS[(level, topic)]
        repeat = struggle_words[:2] or lesson["repeat"]

        return {
            "response": lesson["response"],
            "repeat": repeat,
            "expected_phrase": lesson["expected_phrase"],
            "next_phrase": lesson["expected_phrase"],
            "level": level,
            "topic": topic,
            "translation": {
                "response_pt": lesson["response_pt"],
                "next_phrase_pt": lesson["translation"],
            },
        }

    def build_spoken_text(self, tutor_result: dict[str, Any]) -> str:
        original = tutor_result["original"].strip().lower()
        corrected = tutor_result["corrected"].strip()
        parts = []

        if corrected and corrected.lower() != original:
            parts.append(f"Boa tentativa. A forma correta em ingles e: {corrected}.")

        repeat = tutor_result.get("repeat") or []
        if repeat:
            parts.append("Palavras importantes: " + ", ".join(repeat[:3]) + ".")

        next_phrase = tutor_result.get("next_phrase")
        if next_phrase:
            parts.append(f"Agora pratique em ingles: {next_phrase}. Repita: {next_phrase}.")

        parts.append(tutor_result["response"])
        return " ".join(part for part in parts if part)

    def _build_messages(
        self,
        transcript: str,
        history: list[dict[str, str]],
        struggle_words: list[str],
        mode: str,
        level: str,
        topic: str,
        expected_phrase: str | None,
    ) -> list[dict[str, str]]:
        system_content = SYSTEM_PROMPT + "\n\n" + JSON_INSTRUCTIONS
        system_content += "\n\n" + LEVEL_INSTRUCTIONS[level]
        system_content += "\n\n" + TOPIC_INSTRUCTIONS[topic]

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        for item in history:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        repeat_context = ", ".join(struggle_words) if struggle_words else "none"
        expected_context = expected_phrase or "none"
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Student said: {transcript}\n"
                    f"Expected phrase to repeat: {expected_context}\n"
                    f"Level: {level}\n"
                    f"Topic: {topic}\n"
                    f"Words to reinforce: {repeat_context}\n"
                    "Correct gently in Portuguese. Then give one short English "
                    "next_phrase for the student to repeat. The response must be "
                    "Portuguese instruction only."
                ),
            }
        )
        return messages

    def _fallback_response(self, transcript: str, warning: str | None = None) -> dict[str, Any]:
        corrected = _simple_correction(transcript)
        repeat = _repeat_words(transcript, corrected)
        response = "Boa tentativa. Agora repita a proxima frase em ingles."
        next_phrase = "I am learning English."

        if "machine" in transcript.lower() or "work" in transcript.lower():
            response = "Bom. Agora vamos praticar uma frase do trabalho."
            next_phrase = "The machine is running."

        result = {
            "original": transcript,
            "corrected": corrected,
            "explanation": "Pequena correcao. Fale assim em ingles.",
            "response": response,
            "repeat": repeat,
            "next_phrase": next_phrase,
            "translation": {
                "corrected_pt": _fallback_translate(corrected),
                "response_pt": _fallback_translate(response),
                "next_phrase_pt": _fallback_translate(next_phrase),
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
    explanation = str(
        parsed.get("explanation") or "Pequena correcao. Fale assim em ingles."
    ).strip()
    response = str(
        parsed.get("response") or "Agora repita a proxima frase em ingles."
    ).strip()
    next_phrase = str(parsed.get("next_phrase") or corrected or transcript).strip()
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
        "next_phrase": next_phrase,
        "translation": {
            "corrected_pt": str(translation.get("corrected_pt") or "").strip(),
            "response_pt": str(translation.get("response_pt") or "").strip(),
            "next_phrase_pt": str(translation.get("next_phrase_pt") or "").strip(),
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
        "Boa tentativa. Agora repita a proxima frase em ingles.": (
            "Boa tentativa. Agora repita a proxima frase em ingles."
        ),
        "Bom. Agora vamos praticar uma frase do trabalho.": (
            "Bom. Agora vamos praticar uma frase do trabalho."
        ),
        "I agree.": "Eu concordo.",
        "I am learning English.": "Eu estou aprendendo ingles.",
        "The machine is running.": "A maquina esta funcionando.",
    }
    return translations.get(text.strip(), "")


def normalize_level(level: str | None) -> str:
    return level if level in LEVEL_INSTRUCTIONS else "beginner_1"


def normalize_topic(topic: str | None) -> str:
    if topic == "general":
        return "daily"
    return topic if topic in TOPIC_INSTRUCTIONS else "daily"
