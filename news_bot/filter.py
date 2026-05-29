from __future__ import annotations

from .models import ArticleCandidate


POSITIVE_KEYWORDS = {
    "adventure",
    "adidas",
    "arc'teryx",
    "arcteryx",
    "bike",
    "cycling",
    "district vision",
    "endurance",
    "expedition",
    "garmin",
    "gear",
    "gorpcore",
    "hike",
    "hiking",
    "hoka",
    "ironman",
    "marathon",
    "mountain",
    "nike",
    "oakley",
    "on running",
    "outdoor",
    "rapha",
    "running",
    "salomon",
    "ski",
    "strava",
    "streetwear",
    "swim",
    "techwear",
    "trail",
    "travel",
    "trek",
    "utmb",
    "whoop",
    "велосипед",
    "город",
    "горы",
    "дорога",
    "забег",
    "маршрут",
    "одежда",
    "плавание",
    "путешествие",
    "спорт",
    "трейл",
    "экипировка",
    "экспедиция",
}

NEGATIVE_KEYWORDS = {
    "casino",
    "crypto",
    "gambling",
    "politics",
    "war",
    "казино",
    "крипт",
    "политик",
    "ставки",
}


def keyword_score(article: ArticleCandidate) -> int:
    text = article_text(article)
    positive = sum(1 for keyword in POSITIVE_KEYWORDS if keyword in text)
    negative = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword in text)
    return positive - (negative * 2)


def is_topic_candidate(article: ArticleCandidate) -> bool:
    return keyword_score(article) > 0


def article_text(article: ArticleCandidate) -> str:
    # Source names like GearJunkie contain broad topic words, so they must not
    # make an otherwise unrelated article pass the first filter.
    return " ".join(
        [
            article.original_title,
            article.summary,
        ]
    ).casefold()

