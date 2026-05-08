"""AI gateway routes — Venice, OpenAI, Gemini, xAI, GitHub, unified cascade."""
from fastapi import APIRouter, Body, HTTPException
from integrations import github_ai, xai_client, venice_ai
from integrations.unified_ai import complete as unified_complete

router = APIRouter(prefix="/ai", tags=["ai"])


# ── Venice AI ─────────────────────────────────────────────────────────────────

@router.post("/venice")
def venice_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body(venice_ai.VENICE_MODELS[0]),
    max_tokens: int = Body(1000),
):
    return {"response": venice_ai.complete(prompt, system, model, max_tokens), "provider": "venice"}


@router.get("/venice/models")
def venice_models():
    return venice_ai.list_models()


# ── OpenAI ────────────────────────────────────────────────────────────────────

@router.post("/openai")
def openai_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body("gpt-4o-mini"),
    max_tokens: int = Body(1000),
):
    from integrations import openai_client
    try:
        return {"response": openai_client.complete(prompt, system, model, max_tokens), "provider": "openai"}
    except Exception as exc:
        raise HTTPException(502, str(exc))


# ── Google Gemini ─────────────────────────────────────────────────────────────

@router.post("/gemini")
def gemini_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body("gemini-2.0-flash"),
    max_tokens: int = Body(1000),
):
    from integrations import google_ai
    try:
        return {"response": google_ai.complete(prompt, system, model, max_tokens), "provider": "gemini"}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/gemini/key-stats")
def gemini_key_stats():
    from integrations import google_ai
    return {"key_stats": google_ai.get_key_stats()}


# ── xAI / Grok ────────────────────────────────────────────────────────────────

@router.post("/xai")
def xai_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body("grok-3"),
    max_tokens: int = Body(1000),
):
    return {"response": xai_client.complete(prompt, system, model, max_tokens), "provider": "xai"}


# ── GitHub AI / Phi-4 ────────────────────────────────────────────────────────

@router.post("/github")
def github_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body("microsoft/Phi-4-multimodal-instruct"),
    max_tokens: int = Body(1000),
):
    return {"response": github_ai.complete(prompt, system, model, max_tokens), "provider": "github"}


@router.get("/github/models")
def github_models():
    return github_ai.list_models()


# ── Unified cascade ───────────────────────────────────────────────────────────

@router.post("/unified")
def unified(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    prefer:     str = Body("venice"),
    max_tokens: int = Body(800),
):
    """Auto-routes through Venice → OpenAI → Gemini → OpenRouter → xAI → GitHub."""
    return {
        "response": unified_complete(prompt, system, max_tokens, prefer),
        "prefer": prefer,
    }


# ── Aegis sanitize ────────────────────────────────────────────────────────────

@router.post("/sanitize")
def sanitize_text(
    text:          str  = Body(...),
    strip_emojis:  bool = Body(True),
    max_len:       int  = Body(10000),
):
    """UTS #39 Aegis sanitize — strip confusables, emoji, zero-width chars."""
    from integrations.aegis import sanitize
    clean = sanitize(text, strip_emojis=strip_emojis, max_len=max_len)
    return {"original_len": len(text), "clean_len": len(clean), "text": clean}
