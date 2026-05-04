from fastapi import APIRouter, Body
from integrations.openrouter import complete, list_free_models, FREE_MODELS

router = APIRouter(prefix="/openrouter", tags=["openrouter"])


@router.post("/complete")
def openrouter_complete(
    prompt:     str = Body(...),
    system:     str = Body("You are a helpful assistant."),
    model:      str = Body(FREE_MODELS[0]),
    max_tokens: int = Body(800),
):
    return {"response": complete(prompt, system, model, max_tokens), "model": model}


@router.get("/free-models")
def free_models():
    return list_free_models()
