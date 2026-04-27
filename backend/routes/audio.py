from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import settings
from backend.database import db
from backend.services.ai_service import AIService
from backend.services.exceptions import OpenAIConfigurationError
from backend.services.repetition_engine import RepetitionEngine
from backend.services.stt_service import SpeechToTextService
from backend.services.tts_service import TextToSpeechService


router = APIRouter(prefix="/api/audio", tags=["audio"])

stt_service = SpeechToTextService()
ai_service = AIService()
tts_service = TextToSpeechService()
repetition_engine = RepetitionEngine()


@router.post("/conversation")
async def create_conversation(
    audio: UploadFile = File(...),
    user_id: str = Form("default"),
    mode: str = Form("general"),
) -> dict:
    user_id = (user_id or "default").strip()[:80] or "default"
    mode = "work" if mode == "work" else "general"

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
    )

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

    audio_base64 = None
    audio_mime_type = None
    spoken_text = ai_service.build_spoken_text(tutor_result)
    try:
        speech_bytes = tts_service.synthesize(spoken_text)
        audio_base64 = base64.b64encode(speech_bytes).decode("ascii")
        audio_mime_type = "audio/mpeg"
    except OpenAIConfigurationError as exc:
        warnings.append(str(exc))
    except Exception as exc:
        warnings.append(f"Could not synthesize speech: {exc}")

    return {
        "transcript": transcript,
        "correction": {
            "original": tutor_result["original"],
            "corrected": tutor_result["corrected"],
            "explanation": tutor_result["explanation"],
            "response": tutor_result["response"],
            "repeat": tutor_result["repeat"],
        },
        "spoken_text": spoken_text,
        "audio_base64": audio_base64,
        "audio_mime_type": audio_mime_type,
        "warnings": warnings,
        "mode": mode,
    }


@router.get("/progress/{user_id}")
async def get_progress(user_id: str) -> dict:
    return db.get_progress((user_id or "default").strip()[:80] or "default")
