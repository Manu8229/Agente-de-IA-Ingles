from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import settings
from backend.database import db
from backend.services.ai_service import AIService
from backend.services.exceptions import OpenAIConfigurationError
from backend.services.repetition_engine import RepetitionEngine
from backend.services.speech_feedback import evaluate_repetition
from backend.services.stt_service import SpeechToTextService
from backend.services.tts_service import TextToSpeechService


router = APIRouter(prefix="/api/audio", tags=["audio"])

stt_service = SpeechToTextService()
ai_service = AIService()
tts_service = TextToSpeechService()
repetition_engine = RepetitionEngine()


def _audio_response(spoken_text: str) -> tuple[str | None, str | None, list[str]]:
    warnings = []
    audio_base64 = None
    audio_mime_type = None

    try:
        speech_bytes = tts_service.synthesize(spoken_text)
        audio_base64 = base64.b64encode(speech_bytes).decode("ascii")
        audio_mime_type = "audio/mpeg"
    except OpenAIConfigurationError as exc:
        warnings.append(str(exc))
    except Exception as exc:
        warnings.append(f"Could not synthesize speech: {exc}")

    return audio_base64, audio_mime_type, warnings


@router.post("/start")
async def start_lesson(
    user_id: str = Form("default"),
    mode: str = Form("general"),
    level: str = Form("beginner_1"),
    topic: str = Form("daily"),
) -> dict:
    user_id = (user_id or "default").strip()[:80] or "default"
    mode = "work" if mode == "work" or topic == "work" else "general"
    struggle_words = repetition_engine.get_words_to_repeat(user_id, limit=4)
    lesson = ai_service.generate_lesson_start(
        struggle_words=struggle_words,
        mode=mode,
        level=level,
        topic=topic,
    )
    spoken_text = lesson["response"]
    db.save_message(user_id, "assistant", spoken_text)
    audio_base64, audio_mime_type, warnings = _audio_response(spoken_text)

    return {
        "message": spoken_text,
        "spoken_text": spoken_text,
        "repeat": lesson["repeat"],
        "expected_phrase": lesson["expected_phrase"],
        "next_phrase": lesson["next_phrase"],
        "translation": lesson["translation"],
        "audio_base64": audio_base64,
        "audio_mime_type": audio_mime_type,
        "warnings": warnings,
        "mode": mode,
        "level": lesson["level"],
        "topic": lesson["topic"],
    }


@router.post("/conversation")
async def create_conversation(
    audio: UploadFile = File(...),
    user_id: str = Form("default"),
    mode: str = Form("general"),
    level: str = Form("beginner_1"),
    topic: str = Form("daily"),
    expected_phrase: str | None = Form(None),
) -> dict:
    user_id = (user_id or "default").strip()[:80] or "default"
    mode = "work" if mode == "work" or topic == "work" else "general"

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    try:
        transcript = stt_service.transcribe(audio_bytes, audio.filename, audio.content_type)
    except OpenAIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not transcribe audio: {exc}") from exc

    history = db.get_recent_messages(user_id, limit=settings.max_history_messages)
    struggle_words = repetition_engine.get_words_to_repeat(user_id, limit=6)
    tutor_result = ai_service.generate_tutor_response(
        transcript=transcript,
        history=history,
        struggle_words=struggle_words,
        mode=mode,
        level=level,
        topic=topic,
        expected_phrase=expected_phrase,
    )
    speech_feedback = evaluate_repetition(transcript, expected_phrase)

    db.save_message(user_id, "user", transcript)
    db.save_message(user_id, "assistant", tutor_result["response"])
    db.save_attempt(
        user_id=user_id,
        original=tutor_result["original"],
        corrected=tutor_result["corrected"],
        explanation=tutor_result["explanation"],
        response=tutor_result["response"],
        repeat=tutor_result["repeat"],
        mode=mode,
    )
    repetition_engine.update_user_progress(user_id, tutor_result)

    warnings = []
    if tutor_result.get("warning"):
        warnings.append(tutor_result["warning"])

    spoken_text = ai_service.build_spoken_text(tutor_result)
    audio_base64, audio_mime_type, audio_warnings = _audio_response(spoken_text)
    warnings.extend(audio_warnings)

    return {
        "transcript": transcript,
        "correction": {
            "original": tutor_result["original"],
            "corrected": tutor_result["corrected"],
            "explanation": tutor_result["explanation"],
            "response": tutor_result["response"],
            "repeat": tutor_result["repeat"],
            "next_phrase": tutor_result["next_phrase"],
            "translation": tutor_result["translation"],
        },
        "speech_feedback": speech_feedback,
        "next_phrase": tutor_result["next_phrase"],
        "spoken_text": spoken_text,
        "audio_base64": audio_base64,
        "audio_mime_type": audio_mime_type,
        "warnings": warnings,
        "mode": mode,
        "level": level,
        "topic": topic,
    }


@router.get("/progress/{user_id}")
async def get_progress(user_id: str) -> dict:
    return db.get_progress((user_id or "default").strip()[:80] or "default")
