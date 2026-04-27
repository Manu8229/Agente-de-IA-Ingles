from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from backend.database import db


WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z']*")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "we",
    "you",
}


def normalize_word(word: str) -> str:
    return word.strip().lower().strip("'")


def extract_words(text: str, *, include_stopwords: bool = False) -> list[str]:
    words = []
    for match in WORD_RE.findall(text or ""):
        word = normalize_word(match)
        if not word:
            continue
        if not include_stopwords and word in STOPWORDS:
            continue
        words.append(word)
    return list(dict.fromkeys(words))


def changed_words(original: str, corrected: str) -> list[str]:
    original_words = extract_words(original, include_stopwords=True)
    corrected_words = extract_words(corrected, include_stopwords=True)
    matcher = SequenceMatcher(a=original_words, b=corrected_words)
    changed: list[str] = []

    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "insert"}:
            changed.extend(corrected_words[j1:j2])

    return [word for word in dict.fromkeys(changed) if word not in STOPWORDS]


class RepetitionEngine:
    def get_words_to_repeat(self, user_id: str, limit: int = 6) -> list[str]:
        return db.get_struggle_words(user_id, limit=limit)

    def update_user_progress(self, user_id: str, tutor_result: dict[str, Any]) -> None:
        original = str(tutor_result.get("original") or "")
        corrected = str(tutor_result.get("corrected") or original)
        repeat_words = [
            normalize_word(str(word))
            for word in tutor_result.get("repeat", [])
            if normalize_word(str(word))
        ]

        struggles = changed_words(original, corrected)
        if original.strip().lower() != corrected.strip().lower():
            struggles.extend(repeat_words)
            db.increment_struggle_words(user_id, list(dict.fromkeys(struggles)))

        learned = extract_words(corrected or original)
        learned = [word for word in learned if word not in set(struggles)]
        db.increment_learned_words(user_id, learned)
