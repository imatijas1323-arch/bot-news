from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "figure",
    "figcaption",
)

MIN_PARAGRAPH_CHARS = 40

OG_IMAGE_META_SELECTORS = (
    ("meta", {"property": "og:image:secure_url"}),
    ("meta", {"property": "og:image"}),
    ("meta", {"name": "og:image"}),
    ("meta", {"name": "twitter:image"}),
    ("meta", {"name": "twitter:image:src"}),
    ("meta", {"property": "twitter:image"}),
)


async def fetch_article_content(
    url: str,
    *,
    timeout_seconds: float = 20.0,
    max_chars: int = 6000,
) -> tuple[str, str | None]:
    """Download the article page; return (clean body text, og:image url)."""
    if not url:
        return "", None
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": BROWSER_USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "").casefold():
                return "", None
            html = response.text
            final_url = str(response.url)
    except httpx.HTTPError as exc:
        logger.warning("Article fetch failed for %s: %s", url, exc.__class__.__name__)
        return "", None

    text, image_url = await asyncio.to_thread(parse_article_html, html, final_url)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip()
    logger.info(
        "Fetched article from %s: text=%d chars, og_image=%s",
        url,
        len(text),
        "yes" if image_url else "no",
    )
    return text, image_url


def parse_article_html(html: str, base_url: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    image_url = extract_og_image(soup, base_url)

    for tag in soup(DROP_TAGS):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [
        " ".join(p.get_text(" ", strip=True).split())
        for p in container.find_all("p")
    ]
    paragraphs = [p for p in paragraphs if len(p) >= MIN_PARAGRAPH_CHARS]
    text = "\n\n".join(paragraphs).strip()
    return text, image_url


def extract_og_image(soup: BeautifulSoup, base_url: str) -> str | None:
    for tag_name, attrs in OG_IMAGE_META_SELECTORS:
        meta = soup.find(tag_name, attrs=attrs)
        if not meta:
            continue
        raw = (meta.get("content") or "").strip()
        if not raw:
            continue
        absolute = urljoin(base_url, raw)
        if absolute.startswith(("http://", "https://")):
            return absolute
    return None
