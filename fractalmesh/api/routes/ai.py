from fastapi import APIRouter, Body
from integrations import github_ai, xai_client

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
