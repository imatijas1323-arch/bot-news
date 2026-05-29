from __future__ import annotations

import re

import httpx


UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"

CATEGORY_KEYWORDS: dict[str, str] = {
    "gear": "outdoor gear equipment product",
    "sport": "sport athlete endurance",
    "outdoor": "outdoor nature mountains adventure",
    "travel": "adventure travel landscape road trip",
    "culture": "sport culture community lifestyle",
    "tech": "sport technology wearable",
    "people": "athlete portrait endurance",
}


async def fetch_unsplash_image(
    query: str,
    access_key: str,
    *,
    category: str = "",
    timeout_seconds: float = 10.0,
) -> str | None:
    if not access_key:
        return None

    search_query = compact_query(" ".join([query, category_keywords(category)]))

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                UNSPLASH_SEARCH_URL,
                params={
                    "query": search_query,
                    "per_page": 1,
                    "orientation": "landscape",
                },
                headers={"Authorization": f"Client-ID {access_key}"},
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results") or []
            if results:
                return str(results[0]["urls"]["regular"])
    except Exception:
        pass
    return None


def category_keywords(category: str) -> str:
    tokens = [token.strip().casefold() for token in re.split(r"[|,/]+", category or "") if token.strip()]
    return " ".join(CATEGORY_KEYWORDS.get(token, "") for token in tokens).strip()


def compact_query(query: str) -> str:
    return " ".join(str(query).replace("|", " ").split())
