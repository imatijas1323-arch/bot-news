from __future__ import annotations

import re
from html import unescape
from datetime import datetime, timezone
from time import struct_time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .models import ArticleCandidate


IMG_SRC_RE = re.compile(r"<img[^>]+src=[\'\"]([^\'\"]+)[\'\"]", re.IGNORECASE)


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
}


async def fetch_rss_candidates(
    feed_urls: list[str],
    *,
    timeout_seconds: float = 20.0,
) -> list[ArticleCandidate]:
    candidates: list[ArticleCandidate] = []
    seen_urls: set[str] = set()

    headers = {
        "User-Agent": "tudai-obratno-news-bot/0.1 (+https://t.me/)",
    }
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True, headers=headers) as client:
        for feed_url in feed_urls:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            feed = feedparser.parse(response.content)
            source_name = clean_text(feed.feed.get("title") or host_from_url(feed_url))

            for entry in feed.entries:
                title = clean_text(entry.get("title") or "")
                url = normalize_url(entry.get("link") or "")
                if not title or not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(
                    ArticleCandidate(
                        original_title=title,
                        original_url=url,
                        source_name=source_name,
                        summary=clean_text(entry.get("summary") or entry.get("description") or ""),
                        image_url=extract_image_url(entry),
                        published_at=parse_entry_datetime(entry),
                    )
                )

    candidates.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return candidates


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/") or parts.path,
            urlencode(query, doseq=True),
            "",
        )
    )


def host_from_url(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def clean_text(value: str) -> str:
    return " ".join(str(value).split())


def parse_entry_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if isinstance(parsed, struct_time):
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def extract_image_url(entry) -> str | None:
    thumbnails = entry.get("media_thumbnail") or []
    if thumbnails and thumbnails[0].get("url"):
        return str(thumbnails[0]["url"])

    media_content = entry.get("media_content") or []
    for item in media_content:
        url = item.get("url")
        medium = str(item.get("medium") or "")
        content_type = str(item.get("type") or "")
        if url and (medium == "image" or content_type.startswith("image/")):
            return str(url)

    for enclosure in entry.get("enclosures") or []:
        href = enclosure.get("href") or enclosure.get("url")
        content_type = str(enclosure.get("type") or "")
        if href and content_type.startswith("image/"):
            return str(href)

    for link in entry.get("links") or []:
        href = link.get("href")
        content_type = str(link.get("type") or "")
        rel = str(link.get("rel") or "")
        if href and (content_type.startswith("image/") or rel in {"enclosure", "image_src"}):
            return str(href)

    for html in html_fragments(entry):
        image_url = extract_first_img_src(html)
        if image_url:
            return image_url
    return None


def html_fragments(entry) -> list[str]:
    fragments = [entry.get("summary") or "", entry.get("description") or ""]
    for item in entry.get("content") or []:
        value = item.get("value") if hasattr(item, "get") else None
        if value:
            fragments.append(str(value))
    return [fragment for fragment in fragments if fragment]


def extract_first_img_src(html: str) -> str | None:
    match = IMG_SRC_RE.search(str(html))
    if not match:
        return None
    url = unescape(match.group(1)).strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None

