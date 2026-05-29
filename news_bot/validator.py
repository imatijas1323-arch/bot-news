from __future__ import annotations

import re

from .models import ValidationResult


URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(^|\s)#[\wА-Яа-яЁё-]+")
EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]"
)

FORBIDDEN_PHRASES = [
    "шок",
    "срочно",
    "невероятно",
    "вы не поверите",
    "сенсация",
    "кликните",
    "жми",
]


def validate_post(
    text: str,
    *,
    allow_emoji: bool = False,
    allow_hashtags: bool = False,
    min_chars: int = 400,
    hard_max_chars: int = 1200,
) -> ValidationResult:
    errors: list[str] = []
    stripped = text.strip()
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]

    if not stripped:
        errors.append("empty_text")
    if not lines or len(lines[0]) < 4:
        errors.append("missing_title")
    if 0 < len(stripped) < min_chars:
        errors.append(f"too_short:{len(stripped)}_of_{min_chars}")
    if len(stripped) > hard_max_chars:
        errors.append("too_long")
    if URL_RE.search(stripped):
        errors.append("contains_url")
    if not allow_emoji and EMOJI_RE.search(stripped):
        errors.append("contains_emoji")
    if not allow_hashtags and HASHTAG_RE.search(stripped):
        errors.append("contains_hashtag")

    lowered = stripped.casefold()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            errors.append(f"forbidden_phrase:{phrase}")

    return ValidationResult(ok=not errors, errors=errors)


def clean_ai_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped

