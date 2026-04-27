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
  "next_phrase": "short phrase the student should say next",
  "translation": {
    "corrected_pt": "Brazilian Portuguese meaning of corrected sentence",
    "response_pt": "Brazilian Portuguese meaning of response",
    "next_phrase_pt": "Brazilian Portuguese meaning of next_phrase"
  }
}

Rules:
- Keep every field short.
- Explanation must be simple and friendly.
- Response must continue the conversation with one short question.
- repeat must include 1 to 4 important words or phrases.
- Ask the student to repeat one short phrase when that helps.
- next_phrase must be short and useful for the selected level and topic.
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

LESSON_STARTS = {
    ("beginner_1", "daily"): {
        "expected_phrase": "I am ready.",
        "translation": "Eu estou pronto.",
        "response": (
            "Hi. I am your English teacher. We will speak slowly. "
            "Listen and repeat: I am ready. Now say: I am ready."
        ),
        "response_pt": (
            "Oi. Eu sou seu professor de ingles. Vamos falar devagar. "
            "Escute e repita: Eu estou pronto. Agora diga: Eu estou pronto."
        ),
        "repeat": ["hello", "ready"],
    },
    ("beginner_2", "daily"): {
        "expected_phrase": "I worked yesterday.",
        "translation": "Eu trabalhei ontem.",
        "response": (
            "Hi. Today we practice past time. Listen and repeat: "
            "I worked yesterday. Now say: I worked yesterday."
        ),
        "response_pt": (
            "Oi. Hoje vamos praticar passado. Escute e repita: "
            "Eu trabalhei ontem. Agora diga: Eu trabalhei ontem."
        ),
        "repeat": ["worked", "yesterday"],
    },
    ("beginner_1", "work"): {
        "expected_phrase": "I check the machine.",
        "translation": "Eu verifico a maquina.",
        "response": (
            "Hi. I am your English teacher. Listen and repeat: "
            "I check the machine. Now say: I check the machine."
        ),
        "response_pt": (
            "Oi. Eu sou seu professor de ingles. Escute e repita: "
            "Eu verifico a maquina. Agora diga: Eu verifico a maquina."
        ),
        "repeat": ["check", "machine"],
    },
    ("beginner_2", "work"): {
        "expected_phrase": "Production stopped yesterday.",
        "translation": "A producao parou ontem.",
        "response": (
            "Hi. Let us practice work English. Listen and repeat: "
            "Production stopped yesterday. Now say: Production stopped yesterday."
        ),
        "response_pt": (
            "Oi. Vamos praticar ingles do trabalho. Escute e repita: "
            "A producao parou ontem. Agora diga: A producao parou ontem."
        ),
        "repeat": ["production", "stopped"],
    },
    ("beginner_1", "travel"): {
        "expected_phrase": "I need a taxi.",
        "translation": "Eu preciso de um taxi.",
        "response": (
            "Hi. Let us practice travel English. Listen and repeat: "
            "I need a taxi. Now say: I need a taxi."
        ),
        "response_pt": (
            "Oi. Vamos praticar ingles para viagem. Escute e repita: "
            "Eu preciso de um taxi. Agora diga: Eu preciso de um taxi."
        ),
        "repeat": ["need", "taxi"],
    },
    ("beginner_2", "travel"): {
        "expected_phrase": "Where is the hotel?",
        "translation": "Onde fica o hotel?",
        "response": (
            "Hi. Ask a simple travel question. Listen and repeat: "
            "Where is the hotel? Now say: Where is the hotel?"
        ),
        "response_pt": (
            "Oi. Faca uma pergunta simples de viagem. Escute e repita: "
            "Onde fica o hotel? Agora diga: Onde fica o hotel?"
        ),
        "repeat": ["where", "hotel"],
    },
    ("beginner_1", "routine"): {
        "expected_phrase": "I drink coffee.",
        "translation": "Eu bebo cafe.",
        "response": (
            "Hi. Let us practice your routine. Listen and repeat: "
            "I drink coffee. Now say: I drink coffee."
        ),
        "response_pt": (
            "Oi. Vamos praticar sua rotina. Escute e repita: "
            "Eu bebo cafe. Agora diga: Eu bebo cafe."
        ),
        "repeat": ["drink", "coffee"],
    },
    ("beginner_2", "routine"): {
        "expected_phrase": "I wake up early.",
        "translation": "Eu acordo cedo.",
        "response": (
            "Hi. Let us make a longer routine sentence. Listen and repeat: "
            "I wake up early. Now say: I wake up early."
        ),
        "response_pt": (
            "Oi. Vamos fazer uma frase maior sobre rotina. Escute e repita: "
            "Eu acordo cedo. Agora diga: Eu acordo cedo."
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
            parts.append(f"Good job. The correct way is: {corrected}.")

        repeat = tutor_result.get("repeat") or []
        if repeat:
            parts.append("Repeat: " + ", ".join(repeat[:3]) + ".")

        next_phrase = tutor_result.get("next_phrase")
        if next_phrase:
            parts.append(f"Now say: {next_phrase}.")

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
        next_phrase = "I am learning English."

        if "machine" in transcript.lower() or "work" in transcript.lower():
            response = "Good. What happened at work today?"
            next_phrase = "The machine is running."

        result = {
            "original": transcript,
            "corrected": corrected,
            "explanation": "Small change. Say it this way.",
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
    explanation = str(parsed.get("explanation") or "Small change. Say it this way.").strip()
    response = str(parsed.get("response") or "Good. Tell me more.").strip()
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
        "Nice try. Tell me one more simple sentence.": (
            "Boa tentativa. Diga mais uma frase simples."
        ),
        "Good. What happened at work today?": "Bom. O que aconteceu no trabalho hoje?",
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
