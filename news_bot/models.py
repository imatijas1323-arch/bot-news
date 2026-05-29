from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArticleStatus(StrEnum):
    FOUND = "found"
    FILTERED = "filtered"
    DRAFTED = "drafted"
    APPROVED = "approved"
    PUBLISHED = "published"
    SKIPPED = "skipped"
    REJECTED = "rejected"


@dataclass(slots=True)
class ArticleCandidate:
    original_title: str
    original_url: str
    source_name: str
    summary: str = ""
    image_url: str | None = None
    published_at: datetime | None = None


@dataclass(slots=True)
class CuratorDecision:
    accept: bool
    score: int
    category: str
    reason: str
    title_ru: str = ""
    summary_ru: str = ""


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    errors: list[str]


@dataclass(slots=True)
class ArticleRecord:
    id: int
    original_title: str
    original_url: str
    source_name: str
    summary: str
    category: str | None
    image_url: str | None
    status: ArticleStatus
    ai_score: int | None
    generated_text: str | None
    is_breaking: bool
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    user_rating: int | None = None
    rating_reason: str | None = None
    summary_ru: str = ""

    def as_candidate(self) -> ArticleCandidate:
        return ArticleCandidate(
            original_title=self.original_title,
            original_url=self.original_url,
            source_name=self.source_name,
            summary=self.summary,
            image_url=self.image_url,
            published_at=self.published_at,
        )

