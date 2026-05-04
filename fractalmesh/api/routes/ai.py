from fastapi import APIRouter, Body
from integrations import github_ai, xai_client, venice_ai
from integrations.unified_ai import complete as unified_complete

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/github")
def github_complete(
    prompt:  str = Body(...),
    system:  str = Body("You are a helpful assistant."),
    model:   str = Body("microsoft/Phi-4-multimodal-instruct"),
    max_tokens: int = Body(1000),
):
    return {"response": github_ai.complete(prompt, system, model, max_tokens)}


@router.get("/github/models")
def github_models():
    return github_ai.list_models()


@router.post("/xai")
def xai_complete(
    prompt:  str = Body(...),
    system:  str = Body("You are a helpful assistant."),
    model:   str = Body("grok-3"),
    max_tokens: int = Body(1000),
):
    return {"response": xai_client.complete(prompt, system, model, max_tokens)}


@router.post("/venice")
def venice_complete(
    prompt:  str = Body(...),
    system:  str = Body("You are a helpful assistant."),
    model:   str = Body(venice_ai.VENICE_MODELS[0]),
    max_tokens: int = Body(1000),
):
    return {"response": venice_ai.complete(prompt, system, model, max_tokens)}


@router.get("/venice/models")
def venice_models():
    return venice_ai.list_models()


@router.post("/unified")
def unified(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    prefer:     str = Body("venice"),
    max_tokens: int = Body(800),
):
    """Auto-routes to best available AI: Venice → OpenRouter → xAI → GitHub."""
    return {"response": unified_complete(prompt, system, max_tokens, prefer), "prefer": prefer}
