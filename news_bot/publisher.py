from __future__ import annotations

import logging
import re
from html import escape

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from .config import Settings
from .images import fetch_unsplash_image
from .models import ArticleRecord


logger = logging.getLogger(__name__)

BOLD_MARKER_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def strip_bold_markers(text: str) -> str:
    return BOLD_MARKER_RE.sub(r"\1", text).replace("**", "")


def bold_first_line(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            lines[i] = f"**{strip_bold_markers(line).strip()}**"
            break
    return "\n".join(lines)


def render_html(text: str) -> str:
    marked = bold_first_line(text)
    return BOLD_MARKER_RE.sub(r"<b>\1</b>", escape(marked)).replace("**", "")


RATING_REASON_LABELS = {
    "not_topic": "Не наша тема",
    "weak_event": "Слабый инфоповод",
    "guide_or_sale": "Гайд, подборка или скидка",
    "too_local": "Слишком локально",
    "bad_tone": "Не тот тон",
    "skipped": "Пропущено без оценки",
}


def rating_reason_label(reason: str | None) -> str:
    if not reason:
        return "без причины"
    return RATING_REASON_LABELS.get(reason, reason)


def rating_reason_keyboard(article_id: int, rating: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Не наша тема", callback_data=f"rate_reason:{article_id}:{rating}:not_topic")],
            [InlineKeyboardButton(text="Слабый инфоповод", callback_data=f"rate_reason:{article_id}:{rating}:weak_event")],
            [InlineKeyboardButton(text="Гайд/скидка", callback_data=f"rate_reason:{article_id}:{rating}:guide_or_sale")],
            [InlineKeyboardButton(text="Слишком локально", callback_data=f"rate_reason:{article_id}:{rating}:too_local")],
            [InlineKeyboardButton(text="Не тот тон", callback_data=f"rate_reason:{article_id}:{rating}:bad_tone")],
        ]
    )


RATE_GROUPS: dict[int, list[int]] = {1: [1, 2, 3], 4: [4, 5, 6, 7], 8: [8, 9, 10]}


def preview_keyboard(article_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Написать пост", callback_data=f"write:{article_id}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"skip:{article_id}"),
            ],
            [
                InlineKeyboardButton(text="1", callback_data=f"rate_open:{article_id}:1"),
                InlineKeyboardButton(text="4", callback_data=f"rate_open:{article_id}:4"),
                InlineKeyboardButton(text="8", callback_data=f"rate_open:{article_id}:8"),
            ],
        ]
    )


def rate_group_keyboard(article_id: int, group: int) -> InlineKeyboardMarkup:
    nums = RATE_GROUPS.get(group, [])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Написать пост", callback_data=f"write:{article_id}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"skip:{article_id}"),
            ],
            [InlineKeyboardButton(text=str(n), callback_data=f"rate:{article_id}:{n}") for n in nums],
            [InlineKeyboardButton(text="← назад", callback_data=f"rate_back:{article_id}")],
        ]
    )


def preview_keyboard_rated(article_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Написать пост", callback_data=f"write:{article_id}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"skip:{article_id}"),
            ],
        ]
    )


def draft_keyboard(article_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Опубликовать", callback_data=f"publish:{article_id}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"skip:{article_id}"),
            ],
            [
                InlineKeyboardButton(text="Переписать статью", callback_data=f"rewrite:{article_id}"),
                InlineKeyboardButton(text="Переписать заголовок", callback_data=f"rewrite_title:{article_id}"),
            ],
            [
                InlineKeyboardButton(text="Править вручную", callback_data=f"edit:{article_id}"),
            ],
        ]
    )


def format_admin_preview(article: ArticleRecord) -> str:
    score = article.ai_score if article.ai_score is not None else "?"
    category = article.category or "без категории"
    header = "СРОЧНО — кандидат для «Новостей»:" if article.is_breaking else "Кандидат для «Новостей»:"
    title = article.generated_text or article.original_title
    description = article.summary_ru or article.summary or "нет описания"
    return "\n\n".join(
        [
            header,
            f"{title}\n{article.source_name}",
            description,
            f"Оценка: {score}/10 · {category}",
        ]
    )


def format_admin_draft(article: ArticleRecord, *, article_text: str | None = None) -> str:
    score = article.ai_score if article.ai_score is not None else "?"
    category = article.category or "без категории"
    header = "СРОЧНО — черновик для «Новостей»:" if article.is_breaking else "Черновик для «Новостей»:"
    image_hint = "RSS-картинка: есть" if article.image_url else "RSS-картинка: нет, попробую Unsplash при публикации"
    source_hint = "Источник будет добавлен при публикации" if looks_like_research_article(article) else "Источник скрыт для читателя"
    blocks = [
        header,
        strip_bold_markers(article.generated_text or ""),
        f"Оценка: {score}/10 · {category}",
    ]
    if article_text is not None:
        if article_text:
            blocks.append(f"Написано по полной статье ({len(article_text)} знаков прочитано)")
        else:
            blocks.append("Статью прочитать не удалось — текст по короткому RSS-описанию")
    blocks.append(f"{image_hint}\n{source_hint}")
    blocks.append(f"Источник: {article.source_name}\nURL: {article.original_url}")
    return "\n\n".join(blocks)


async def send_admin_preview(
    bot: Bot,
    settings: Settings,
    article: ArticleRecord,
) -> Message:
    return await bot.send_message(
        chat_id=settings.admin_chat_id,
        text=format_admin_preview(article),
        reply_markup=preview_keyboard(article.id),
        disable_web_page_preview=True,
    )


TELEGRAM_CAPTION_LIMIT = 1024

RESEARCH_SOURCE_KEYWORDS = {
    "research",
    "researchers",
    "scientist",
    "scientists",
    "study",
    "studies",
    "paper",
    "journal",
    "university",
    "harvard",
    "nature",
    "science",
    "pubmed",
    "исслед",
    "учен",
    "науч",
    "статья",
    "журнал",
    "университет",
    "эксперимент",
    "данные",
}


def build_published_text(article: ArticleRecord, settings: Settings) -> str:
    text = article.generated_text or ""
    if should_attach_source(article, settings) and article.original_url not in text:
        text = text.rstrip() + f"\n\nИсточник: {article.original_url}"
    return text


def should_attach_source(article: ArticleRecord, settings: Settings) -> bool:
    if settings.show_source_link:
        return True
    return looks_like_research_article(article)


def looks_like_research_article(article: ArticleRecord) -> bool:
    haystack = " ".join(
        [
            article.original_title,
            article.summary,
            article.summary_ru,
            article.generated_text or "",
            article.source_name,
        ]
    ).casefold()
    return any(keyword in haystack for keyword in RESEARCH_SOURCE_KEYWORDS)


def build_image_search_query(article: ArticleRecord) -> str:
    return build_image_search_queries(article)[0]


def build_image_search_queries(article: ArticleRecord) -> list[str]:
    category = clean_category(article.category or "")
    generated_title = first_non_empty_line(article.generated_text or "")
    queries = [
        " ".join(part for part in [article.original_title, category] if part),
        " ".join(part for part in [generated_title, category] if part),
        fallback_image_query(article),
    ]
    return dedupe_queries(queries)


def fallback_image_query(article: ArticleRecord) -> str:
    text = " ".join(
        [
            article.original_title,
            article.summary,
            article.summary_ru,
            article.generated_text or "",
            article.category or "",
        ]
    ).casefold()
    if any(word in text for word in ["ultra", "ультра", "trail", "трейл", "marathon", "марафон", "running", "runner", "бег"]):
        return "trail running ultramarathon athlete mountains"
    if any(word in text for word in ["freeride", "ski", "snowboard", "mountain"]):
        return "freeride skiing mountains athlete"
    if any(word in text for word in ["cycling", "bike", "bicycle", "velo", "вел"]):
        return "cycling road bike athlete"
    if any(word in text for word in ["swim", "swimming", "плав"]):
        return "open water swimming athlete"
    return "outdoor endurance sport athlete"


def clean_category(category: str) -> str:
    return " ".join(category.replace("|", " ").replace(",", " ").split())


def dedupe_queries(queries: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = " ".join(str(query).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


async def publish_to_news_thread(
    bot: Bot,
    settings: Settings,
    article: ArticleRecord,
) -> Message:
    text = build_published_text(article, settings)
    image_url = article.image_url
    if not image_url and settings.unsplash_access_key:
        for query in build_image_search_queries(article):
            image_url = await fetch_unsplash_image(
                query,
                settings.unsplash_access_key,
                category=article.category or "",
            )
            if image_url:
                break

    html_text = render_html(text)
    visible_len = len(strip_bold_markers(text))

    if image_url:
        try:
            if visible_len <= TELEGRAM_CAPTION_LIMIT:
                return await bot.send_photo(
                    chat_id=settings.target_chat_id,
                    message_thread_id=settings.news_thread_id,
                    photo=image_url,
                    caption=html_text,
                    parse_mode="HTML",
                )
            return await bot.send_message(
                chat_id=settings.target_chat_id,
                message_thread_id=settings.news_thread_id,
                text=html_text,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(
                    url=image_url,
                    prefer_large_media=True,
                    show_above_text=True,
                ),
            )
        except Exception as exc:
            logger.warning("Failed to publish image for article_id=%s: %s", article.id, exc.__class__.__name__)

    return await bot.send_message(
        chat_id=settings.target_chat_id,
        message_thread_id=settings.news_thread_id,
        text=html_text,
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
