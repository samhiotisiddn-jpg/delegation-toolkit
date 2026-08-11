"""
SEO analyzer — scores content for keyword density, readability,
and affiliate link opportunities using OpenRouter LLMs.
"""

import re
from integrations.openrouter import complete, FREE_MODELS


def keyword_density(text: str, keyword: str) -> float:
    words = re.findall(r"\w+", text.lower())
    if not words:
        return 0.0
    count = sum(1 for w in words if w == keyword.lower())
    return round(count / len(words) * 100, 2)


def readability_score(text: str) -> dict:
    sentences = [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]
    words = re.findall(r"\w+", text)
    syllables = sum(_count_syllables(w) for w in words)
    if not sentences or not words:
        return {"flesch": 0, "grade": "unknown"}
    asl = len(words) / len(sentences)  # avg sentence length
    asw = syllables / len(words)       # avg syllables per word
    flesch = 206.835 - (1.015 * asl) - (84.6 * asw)
    return {
        "flesch":       round(flesch, 1),
        "grade":        _flesch_grade(flesch),
        "word_count":   len(words),
        "sentence_count": len(sentences),
    }


def _count_syllables(word: str) -> int:
    word = word.lower()
    count = len(re.findall(r"[aeiou]", word))
    if word.endswith("e"):
        count -= 1
    return max(1, count)


def _flesch_grade(score: float) -> str:
    if score >= 90: return "very_easy"
    if score >= 70: return "easy"
    if score >= 60: return "standard"
    if score >= 50: return "fairly_difficult"
    return "difficult"


def suggest_affiliate_angles(title: str, content: str) -> list[str]:
    """Ask LLM for 3 affiliate product angles for this content."""
    prompt = (
        f"Given this article, suggest 3 specific affiliate product categories "
        f"that would convert well. Be specific (e.g. 'Python course on Udemy', not 'courses').\n"
        f"Title: {title}\nContent: {content[:400]}\n"
        f"Reply with a numbered list of 3 items only."
    )
    try:
        result = complete(prompt, model=FREE_MODELS[0], max_tokens=200)
        lines = [l.strip() for l in result.split("\n") if l.strip() and l[0].isdigit()]
        return lines[:3]
    except Exception:
        return []


def generate_meta_tags(title: str, content: str) -> dict:
    """Generate SEO meta title and description."""
    prompt = (
        f"Write an SEO-optimised meta title (max 60 chars) and meta description (max 155 chars).\n"
        f"Title: {title}\nContent: {content[:400]}\n"
        f"Format:\nMETA_TITLE: ...\nMETA_DESC: ..."
    )
    try:
        result = complete(prompt, model=FREE_MODELS[0], max_tokens=100)
        meta_title = re.search(r"META_TITLE:\s*(.+)", result)
        meta_desc  = re.search(r"META_DESC:\s*(.+)", result)
        return {
            "meta_title": meta_title.group(1).strip()[:60] if meta_title else title[:60],
            "meta_desc":  meta_desc.group(1).strip()[:155] if meta_desc else content[:155],
        }
    except Exception:
        return {"meta_title": title[:60], "meta_desc": content[:155]}


def analyze(title: str, content: str, target_keyword: str = "") -> dict:
    readability = readability_score(content)
    result = {
        "readability":        readability,
        "keyword_density":    keyword_density(content, target_keyword) if target_keyword else None,
        "affiliate_angles":   suggest_affiliate_angles(title, content),
        "meta_tags":          generate_meta_tags(title, content),
        "word_count":         readability["word_count"],
    }
    return result
