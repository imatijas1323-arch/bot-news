from __future__ import annotations

from pathlib import Path

from .models import ArticleCandidate, ArticleRecord, CuratorDecision


class PromptStore:
    def __init__(self, prompt_dir: Path) -> None:
        self.prompt_dir = prompt_dir

    def load(self, name: str) -> str:
        path = self.prompt_dir / name
        return path.read_text(encoding="utf-8")

    def load_optional(self, name: str) -> str:
        path = self.prompt_dir / name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()


def build_article_context(article: ArticleCandidate) -> str:
    return "\n".join(
        [
            f"Заголовок источника: {article.original_title}",
            f"Источник: {article.source_name}",
            f"URL: {article.original_url}",
            f"Описание: {article.summary or 'нет описания'}",
        ]
    )


RATING_REASON_TEXT = {
    "not_topic": "не наша тема",
    "weak_event": "слабый инфоповод",
    "guide_or_sale": "гайд, подборка или скидка",
    "too_local": "слишком локально",
    "bad_tone": "не тот тон",
    "skipped": "редактор пропустил без отдельной оценки",
}


def build_recent_published_context(recent: list[ArticleRecord]) -> str:
    if not recent:
        return ""
    lines = [
        "Последние опубликованные посты канала — сигнал разнообразия.",
        "Если новый кандидат по теме, формату или категории сильно похож на пост из этого списка (особенно на 3-5 самых свежих), понижай score на 1-3 балла: лента не должна повторяться.",
        "Если категория давно не появлялась — наоборот, при прочих равных можно повысить.",
    ]
    for a in recent:
        title = first_line(a.generated_text or "") or a.original_title
        lines.append(f"- [{a.category or '?'}] {compact_text(title, 100)}")
    return "\n".join(lines)


def build_feedback_context(recent_rated: list[ArticleRecord]) -> str:
    liked = [a for a in recent_rated if a.user_rating is not None and a.user_rating >= 7]
    disliked = [a for a in recent_rated if a.user_rating is not None and a.user_rating <= 4]
    if not liked and not disliked:
        return ""

    lines = [
        "Обратная связь редактора по прошлым кандидатам. Это сильный сигнал для отбора.",
        "Если новый кандидат похож на низко оцененные примеры по типу инфоповода, теме или причине отказа, понижай score до 0-4 и возвращай accept=false.",
        "Высокие оценки показывают направление, но не отменяют общие стоп-правила.",
    ]
    if disliked:
        lines.append("Низко оценено / избегать:")
        lines.extend(format_feedback_item(article) for article in disliked[:6])
    if liked:
        lines.append("Высоко оценено / искать похожее:")
        lines.extend(format_feedback_item(article) for article in liked[:6])
    return "\n".join(lines)


def format_feedback_item(article: ArticleRecord) -> str:
    rating = article.user_rating if article.user_rating is not None else "?"
    reason = RATING_REASON_TEXT.get(article.rating_reason or "", article.rating_reason or "без причины")
    title = article.original_title.strip()
    curator_title = first_line(article.generated_text or "")
    summary = article.summary_ru or article.summary

    parts = [
        f"- {rating}/10",
        f"reason: {reason}",
        f"category: {article.category or '?'}",
        f"source: {article.source_name}",
        f"title: {compact_text(title, 120)}",
    ]
    if curator_title and curator_title.casefold() != title.casefold():
        parts.append(f"curator_title: {compact_text(curator_title, 90)}")
    if summary:
        parts.append(f"summary: {compact_text(summary, 180)}")
    return " | ".join(parts)


def first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def compact_text(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def add_editor_profile(system_prompt: str, prompt_store: PromptStore) -> str:
    profile = prompt_store.load_optional("editor_profile.txt")
    if not profile:
        return system_prompt
    return system_prompt + "\n\n" + profile


def build_curator_prompt(
    prompt_store: PromptStore,
    article: ArticleCandidate,
    feedback_context: str = "",
    recent_published_context: str = "",
) -> tuple[str, str]:
    system = add_editor_profile(prompt_store.load("curator_prompt.txt"), prompt_store)
    if recent_published_context:
        system = system + "\n\n" + recent_published_context
    if feedback_context:
        system = system + "\n\n" + feedback_context
    return system, build_article_context(article)


def build_source_block(article_text: str) -> str:
    if article_text:
        return "Полный текст статьи (единственный источник фактов):\n" + article_text
    return (
        "Полный текст статьи получить не удалось. Пиши строго по заголовку и описанию выше, "
        "не добавляй фактов, которых там нет, и сделай пост короче."
    )


def build_writer_prompt(
    prompt_store: PromptStore,
    article: ArticleCandidate,
    decision: CuratorDecision,
    article_text: str = "",
) -> tuple[str, str]:
    user_prompt = "\n\n".join(
        [
            build_article_context(article),
            build_source_block(article_text),
            "Решение куратора:",
            f"Категория: {decision.category}",
            f"Оценка: {decision.score}",
            f"Причина: {decision.reason}",
        ]
    )
    return add_editor_profile(prompt_store.load("writer_prompt.txt"), prompt_store), user_prompt


def build_rewrite_prompt(
    prompt_store: PromptStore,
    article: ArticleCandidate,
    previous_text: str,
    reason: str,
    article_text: str = "",
) -> tuple[str, str]:
    blocks = [build_article_context(article)]
    if article_text:
        blocks.append(build_source_block(article_text))
    blocks.extend(
        [
            "Предыдущая версия:",
            previous_text,
            "Что улучшить:",
            reason,
        ]
    )
    return add_editor_profile(prompt_store.load("rewrite_prompt.txt"), prompt_store), "\n\n".join(blocks)

