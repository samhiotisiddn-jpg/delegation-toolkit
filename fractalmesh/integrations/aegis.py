"""
Aegis v6.0 — Security sanitizer.
Implements UTS #39 confusables skeleton algorithm, emoji scrubbing,
and zero-width character stripping to prevent Unicode-based injection attacks.
"""
import re
import unicodedata
import logging

log = logging.getLogger("aegis")

# Zero-width and invisible characters
_INVISIBLE = re.compile(
    r"[­͏؜܏ᅟᅠ឴឵"
    r"᠋-᠍᠎​-‏‪-‮"
    r"⁠-⁯ㅤ﻿ﾠ\u{E0000}-\u{E007F}]+",
    re.UNICODE,
)

# Emoji ranges (broad coverage)
_EMOJI = re.compile(
    r"[\U0001F000-\U0001FFFF"
    r"\U00002600-\U000027BF"
    r"\U0001F300-\U0001F9FF"
    r"\U0000FE00-\U0000FE0F"
    r"\U000024C2-\U0001F251"
    r"✀-➿"
    r"⌀-⏿"
    r"⭐-⭕"
    r"⌚-⌛"
    r"☔-☕"
    r"♈-♓]+",
    re.UNICODE,
)

# Common confusables — homoglyph → ASCII mapping (subset of UTS #39 table)
_CONFUSABLES: dict[str, str] = {
    # Cyrillic lookalikes
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Х": "X",
    # Greek lookalikes
    "α": "a", "β": "b", "ε": "e", "ο": "o", "ρ": "p", "τ": "t",
    # Common Unicode homoglyphs
    "а": "a", "е": "e", "о": "o",
    # Full-width ASCII
    **{chr(0xFF01 + i): chr(0x21 + i) for i in range(94)},
    # Mathematical bold/italic letters
    **{chr(c): chr(0x41 + (c - 0x1D400) % 52) for c in range(0x1D400, 0x1D456)},
}


def _skeleton(text: str) -> str:
    """Apply UTS #39 skeleton algorithm: NFKD + confusable replacement."""
    result = []
    for ch in unicodedata.normalize("NFKD", text):
        result.append(_CONFUSABLES.get(ch, ch))
    return "".join(result)


def strip_invisible(text: str) -> str:
    """Remove zero-width and invisible Unicode characters."""
    try:
        return _INVISIBLE.sub("", text)
    except re.error:
        return re.sub(
            r"[​-‏‪-‮⁠-⁯﻿]+",
            "",
            text,
        )


def strip_emoji(text: str) -> str:
    """Remove all emoji characters."""
    try:
        return _EMOJI.sub("", text)
    except re.error:
        # Fallback: remove chars outside BMP
        return "".join(c for c in text if ord(c) < 0x10000)


def normalize_unicode(text: str) -> str:
    """NFC normalize and remove combining marks outside Latin."""
    nfc = unicodedata.normalize("NFC", text)
    return "".join(c for c in nfc if unicodedata.category(c) not in ("Mn",) or ord(c) < 0x0300)


def sanitize(text: str, *, strip_emojis: bool = True, max_len: int = 10_000) -> str:
    """Full Aegis pipeline: invisible → emoji → confusables → normalize → truncate."""
    if not isinstance(text, str):
        text = str(text)
    text = strip_invisible(text)
    if strip_emojis:
        text = strip_emoji(text)
    text = _skeleton(text)
    text = normalize_unicode(text)
    text = text[:max_len]
    return text.strip()


def sanitize_dict(data: dict, **kwargs) -> dict:
    """Recursively sanitize all string values in a dict."""
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = sanitize(v, **kwargs)
        elif isinstance(v, dict):
            out[k] = sanitize_dict(v, **kwargs)
        elif isinstance(v, list):
            out[k] = [sanitize(i, **kwargs) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out


def is_safe(text: str) -> bool:
    """Return True if text passes Aegis checks without modification."""
    return sanitize(text) == text
