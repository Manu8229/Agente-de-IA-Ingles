from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z']*")


def evaluate_repetition(transcript: str, expected_phrase: str | None) -> dict[str, Any] | None:
    if not expected_phrase:
        return None

    heard = _normalize(transcript)
    expected = _normalize(expected_phrase)
    if not heard or not expected:
        return None

    score = round(SequenceMatcher(a=expected, b=heard).ratio() * 100)

    if score >= 85:
        label = "Good"
        message = "Good. Your phrase was clear."
    elif score >= 60:
        label = "Almost"
        message = "Almost. Say it slowly one more time."
    else:
        label = "Try again"
        message = "Try again. Listen first, then repeat."

    return {
        "label": label,
        "score": score,
        "expected": expected_phrase,
        "heard": transcript,
        "message": message,
    }


def _normalize(text: str) -> str:
    return " ".join(word.lower() for word in WORD_RE.findall(text or ""))
