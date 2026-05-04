from fastapi import APIRouter, Body
from agents.seo_analyzer import analyze, keyword_density, generate_meta_tags

router = APIRouter(prefix="/seo", tags=["seo"])


@router.post("/analyze")
def seo_analyze(
    title:          str = Body(...),
    content:        str = Body(...),
    target_keyword: str = Body(""),
):
    return analyze(title, content, target_keyword)


@router.post("/meta-tags")
def meta_tags(title: str = Body(...), content: str = Body(...)):
    return generate_meta_tags(title, content)


@router.post("/keyword-density")
def density(text: str = Body(...), keyword: str = Body(...)):
    return {"keyword": keyword, "density_pct": keyword_density(text, keyword)}
