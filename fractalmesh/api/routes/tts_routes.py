"""ElevenLabs TTS routes — text-to-speech MP3 generation."""
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/tts", tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None
    model: str = "eleven_multilingual_v2"
    stability: float = 0.5
    similarity_boost: float = 0.75


@router.post("/speak", response_class=Response)
async def speak(req: TTSRequest):
    """Generate speech MP3 from text. Returns audio/mpeg bytes."""
    from integrations.elevenlabs import tts, _DEFAULT_VOICE
    try:
        audio = tts(
            req.text,
            voice_id=req.voice_id or _DEFAULT_VOICE,
            model=req.model,
            stability=req.stability,
            similarity_boost=req.similarity_boost,
        )
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/voices")
async def list_voices():
    from integrations.elevenlabs import list_voices
    return {"voices": list_voices()}


@router.get("/user")
async def user_info():
    from integrations.elevenlabs import get_user_info
    return get_user_info()
