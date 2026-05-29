from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from .ai_client import BaseAIClient, AIClientError
from .article_fetcher import fetch_article_content
from .config import Settings
from .curator import NewsPipeline
from .models import ArticleRecord, ArticleStatus, CuratorDecision
from .publisher import (
    draft_keyboard,
    format_admin_draft,
    format_admin_preview,
    preview_keyboard,
    preview_keyboard_rated,
    rate_group_keyboard,
    rating_reason_keyboard,
    rating_reason_label,
    publish_to_news_thread,
    send_admin_preview,
)
from .storage import SQLiteStorage, start_of_local_day_utc
from .validator import validate_post


STATUS_LABELS = {
    ArticleStatus.FOUND: "найдено",
    ArticleStatus.FILTERED: "отфильтровано",
    ArticleStatus.DRAFTED: "черновики",
    ArticleStatus.APPROVED: "одобрено",
    ArticleStatus.PUBLISHED: "опубликовано",
    ArticleStatus.SKIPPED: "пропущено",
    ArticleStatus.REJECTED: "отклонено",
}

BTN_CHECK = "Проверить сейчас"
BTN_STATS = "Статистика"
BTN_HELP = "Помощь"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHECK), KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def build_router(
    *,
    settings: Settings,
    storage: SQLiteStorage,
    ai_client: BaseAIClient,
    writer_client: BaseAIClient | None = None,
) -> Router:
    router = Router()
    if writer_client is None:
        writer_client = ai_client
    pipeline = NewsPipeline(settings=settings, storage=storage, ai_client=ai_client)
    pending_edits: dict[int, int] = {}

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        if not is_admin_message(settings, message):
            return
        await message.answer(
            "Бот «Туда и обратно / Новости» на связи.",
            reply_markup=main_keyboard(),
        )

    @router.message(Command("whereami"))
    async def whereami(message: Message) -> None:
        thread_id = getattr(message, "message_thread_id", None)
        from_user_id = message.from_user.id if message.from_user else None
        await message.answer(
            "Диагностика Telegram:\n"
            f"chat.id: {message.chat.id}\n"
            f"from_user.id: {from_user_id}\n"
            f"message_thread_id: {thread_id}"
        )

    @router.message(F.text == BTN_STATS)
    async def btn_stats(message: Message) -> None:
        if not is_admin_message(settings, message):
            return
        storage.init_db()
        await message.answer(format_stats_message(storage))

    @router.message(F.text == BTN_CHECK)
    async def btn_check_now(message: Message, bot: Bot) -> None:
        if not is_admin_message(settings, message):
            return
        await message.answer("Проверяю источники, ищу кандидатов.")
        previews = await pipeline.run_once(
            on_draft=lambda article: send_admin_preview(bot, settings, article)
        )
        if previews:
            await message.answer(f"Нашёл кандидатов: {len(previews)}. Выбирай что писать.")
        else:
            await message.answer("Сильных новостей сейчас не нашлось.")

    @router.message(F.text == BTN_HELP)
    async def btn_help(message: Message) -> None:
        if not is_admin_message(settings, message):
            return
        await message.answer(
            "Проверить сейчас — запустить проверку RSS и получить черновики\n"
            "Статистика — счетчики базы и последние черновики\n"
            "/whereami — показать chat.id и message_thread_id"
        )

    @router.callback_query(F.data.startswith("write:"))
    async def write_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return

        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return

        article = storage.get_article(article_id)
        if article is None:
            await safe_callback_answer(callback, "Статья не найдена.", show_alert=True)
            return

        await safe_callback_answer(callback, "Пишу пост...")
        await safe_edit_callback_message(callback, format_admin_preview(article) + "\n\n⏳ Читаю статью и пишу пост...")

        article_text, og_image = await fetch_article_content(
            article.original_url,
            timeout_seconds=settings.http_timeout_seconds,
        )
        if og_image and not article.image_url:
            storage.set_image_url(article.id, og_image)
            article = storage.get_article(article.id) or article

        decision = CuratorDecision(
            accept=True,
            score=article.ai_score or settings.min_ai_score,
            category=article.category or "unknown",
            reason="",
        )
        try:
            text = await writer_client.write(article.as_candidate(), decision, article_text)
        except AIClientError:
            await safe_edit_callback_message(callback, format_admin_preview(article) + "\n\nAI не смог написать пост. Попробуй ещё раз.", reply_markup=preview_keyboard(article.id))
            return

        validation = validate_post(
            text,
            allow_emoji=settings.allow_emoji,
            allow_hashtags=settings.allow_hashtags,
            min_chars=settings.target_min_post_chars,
            hard_max_chars=settings.hard_max_post_chars,
        )
        if not validation.ok:
            try:
                text = await writer_client.rewrite(article.as_candidate(), text, "Исправь ошибки: " + ", ".join(validation.errors), article_text)
            except AIClientError:
                await safe_edit_callback_message(callback, format_admin_preview(article) + "\n\nТекст не прошёл проверку.", reply_markup=preview_keyboard(article.id))
                return

        updated = storage.save_draft(article_id, decision, text, is_breaking=article.is_breaking)
        await safe_edit_callback_message(
            callback,
            format_admin_draft(updated, article_text=article_text),
            reply_markup=draft_keyboard(updated.id),
        )

    @router.callback_query(F.data.startswith("rewrite_title:"))
    async def rewrite_title_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return

        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return

        article = storage.get_article(article_id)
        if article is None or not article.generated_text:
            await safe_callback_answer(callback, "Черновик не найден.", show_alert=True)
            return

        await safe_callback_answer(callback, "Переписываю заголовок.")
        try:
            rewritten = await writer_client.rewrite(
                article.as_candidate(),
                article.generated_text,
                "Придумай новый заголовок — более точный, живой и цепляющий. Оставь остальной текст без изменений.",
            )
        except AIClientError:
            await safe_callback_answer(callback, "AI не смог переписать заголовок.", show_alert=True)
            return

        decision = CuratorDecision(
            accept=True,
            score=article.ai_score or settings.min_ai_score,
            category=article.category or "unknown",
            reason="rewrite_title",
        )
        updated = storage.save_draft(article.id, decision, rewritten)
        await safe_edit_callback_message(
            callback,
            format_admin_draft(updated),
            reply_markup=draft_keyboard(updated.id),
        )

    @router.callback_query(F.data.startswith("publish:"))
    async def publish_callback(callback: CallbackQuery, bot: Bot) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return

        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return

        article = storage.get_article(article_id)
        if article is None or not article.generated_text:
            await safe_callback_answer(callback, "Черновик не найден.", show_alert=True)
            return

        day_start = start_of_local_day_utc(settings.timezone)
        if storage.count_published_since(day_start) >= settings.max_posts_per_day:
            await safe_callback_answer(callback, "Лимит публикаций на сегодня уже достигнут.", show_alert=True)
            return

        try:
            await publish_to_news_thread(bot, settings, article)
        except TelegramBadRequest as exc:
            await safe_callback_answer(callback, f"Telegram не принял публикацию: {exc.message}", show_alert=True)
            return

        storage.mark_approved(article.id)
        published = storage.mark_published(article.id)
        await safe_callback_answer(callback, "Опубликовано.")
        await safe_edit_callback_message(
            callback,
            f"Опубликовано в ветке «Новости».\n\n{published.generated_text}",
        )

    @router.callback_query(F.data.startswith("skip:"))
    async def skip_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return

        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return

        previous = storage.get_article(article_id)
        if previous is not None and previous.user_rating is None:
            storage.save_rating(article_id, 2, "skipped")

        article = storage.mark_skipped(article_id)
        await safe_callback_answer(callback, "Пропущено.")
        await safe_edit_callback_message(
            callback,
            f"Пропущено. Учту как слабый кандидат.\n\nИсходный заголовок: {article.original_title}",
        )

    @router.callback_query(F.data.startswith("rate_open:"))
    async def rate_open_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 3:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        try:
            article_id = int(parts[1])
            group = int(parts[2])
        except ValueError:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        await safe_callback_answer(callback)
        if callback.message is not None:
            try:
                await callback.message.edit_reply_markup(reply_markup=rate_group_keyboard(article_id, group))
            except TelegramBadRequest:
                pass

    @router.callback_query(F.data.startswith("rate_back:"))
    async def rate_back_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return
        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        await safe_callback_answer(callback)
        if callback.message is not None:
            try:
                await callback.message.edit_reply_markup(reply_markup=preview_keyboard(article_id))
            except TelegramBadRequest:
                pass

    @router.callback_query(F.data.startswith("rate:"))
    async def rate_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 3:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        try:
            article_id = int(parts[1])
            rating = int(parts[2])
        except ValueError:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        article = storage.get_article(article_id)
        if article is None:
            await safe_callback_answer(callback, "Статья не найдена.", show_alert=True)
            return

        storage.save_rating(article_id, rating)
        stars = rating_stars(rating)
        if rating <= 4:
            await safe_callback_answer(callback, f"Оценка {rating}/10 сохранена.")
            updated_text = (
                format_admin_preview(article)
                + f"\n\nТвоя оценка: {stars} {rating}/10"
                + "\nПочему не подходит?"
            )
            await safe_edit_callback_message(
                callback,
                updated_text,
                reply_markup=rating_reason_keyboard(article_id, rating),
            )
            return

        await safe_callback_answer(callback, f"Оценка {rating}/10 сохранена.")
        updated_text = format_admin_preview(article) + f"\n\nТвоя оценка: {stars} {rating}/10"
        await safe_edit_callback_message(callback, updated_text, reply_markup=preview_keyboard_rated(article_id))

    @router.callback_query(F.data.startswith("rate_reason:"))
    async def rate_reason_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return
        parts = (callback.data or "").split(":", 3)
        if len(parts) != 4:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        try:
            article_id = int(parts[1])
            rating = int(parts[2])
        except ValueError:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        reason = parts[3]
        article = storage.get_article(article_id)
        if article is None:
            await safe_callback_answer(callback, "Статья не найдена.", show_alert=True)
            return

        storage.save_rating(article_id, rating, reason)
        stars = rating_stars(rating)
        await safe_callback_answer(callback, "Причина сохранена.")
        updated_text = (
            format_admin_preview(article)
            + f"\n\nТвоя оценка: {stars} {rating}/10"
            + f"\nПричина: {rating_reason_label(reason)}"
        )
        await safe_edit_callback_message(callback, updated_text, reply_markup=preview_keyboard_rated(article_id))

    @router.callback_query(F.data.startswith("rewrite:"))
    async def rewrite_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return

        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return

        article = storage.get_article(article_id)
        if article is None or not article.generated_text:
            await safe_callback_answer(callback, "Черновик не найден.", show_alert=True)
            return

        await safe_callback_answer(callback, "Переписываю.")
        article_text, og_image = await fetch_article_content(
            article.original_url,
            timeout_seconds=settings.http_timeout_seconds,
        )
        if og_image and not article.image_url:
            storage.set_image_url(article.id, og_image)
            article = storage.get_article(article.id) or article
        try:
            rewritten = await writer_client.rewrite(
                article.as_candidate(),
                article.generated_text,
                "Админ запросил новую версию. Сделай текст свежее, точнее и без лишнего пафоса.",
                article_text,
            )
        except AIClientError:
            await safe_callback_answer(callback, "AI не смог переписать текст.", show_alert=True)
            return

        validation = validate_post(
            rewritten,
            allow_emoji=settings.allow_emoji,
            allow_hashtags=settings.allow_hashtags,
            min_chars=settings.target_min_post_chars,
            hard_max_chars=settings.hard_max_post_chars,
        )
        if not validation.ok:
            await safe_callback_answer(
                callback,
                "Новая версия не прошла проверки: " + ", ".join(validation.errors),
                show_alert=True,
            )
            return

        decision = CuratorDecision(
            accept=True,
            score=article.ai_score or settings.min_ai_score,
            category=article.category or "unknown",
            reason="manual_rewrite",
        )
        updated = storage.save_draft(article.id, decision, rewritten)
        await safe_edit_callback_message(
            callback,
            format_admin_draft(updated, article_text=article_text),
            reply_markup=draft_keyboard(updated.id),
        )

    @router.callback_query(F.data.startswith("edit:"))
    async def edit_callback(callback: CallbackQuery) -> None:
        if not is_admin_callback(settings, callback):
            await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
            return
        article_id = callback_article_id(callback)
        if article_id is None:
            await safe_callback_answer(callback, "Некорректная кнопка.", show_alert=True)
            return
        article = storage.get_article(article_id)
        if article is None or not article.generated_text:
            await safe_callback_answer(callback, "Черновик не найден.", show_alert=True)
            return
        pending_edits[callback.from_user.id] = article_id
        await safe_callback_answer(callback, "Жду правленый текст.")
        if callback.message is not None:
            await callback.message.answer(
                "Отправь следующим сообщением правленый текст поста целиком. "
                "Заголовок — первой строкой, жирный бот поставит сам. "
                "Напиши «отмена», чтобы выйти из правки."
            )

    @router.message(F.text)
    async def maybe_apply_edit(message: Message) -> None:
        if not is_admin_message(settings, message):
            return
        user_id = message.from_user.id if message.from_user else None
        if user_id not in pending_edits:
            return
        article_id = pending_edits[user_id]
        text = (message.text or "").strip()
        if text.casefold() == "отмена":
            pending_edits.pop(user_id, None)
            await message.answer("Правка отменена.")
            return
        article = storage.get_article(article_id)
        if article is None:
            pending_edits.pop(user_id, None)
            await message.answer("Статья не найдена. Правка отменена.")
            return
        decision = CuratorDecision(
            accept=True,
            score=article.ai_score or settings.min_ai_score,
            category=article.category or "unknown",
            reason="manual_edit",
        )
        updated = storage.save_draft(article_id, decision, text, is_breaking=article.is_breaking)
        pending_edits.pop(user_id, None)
        await message.answer(
            format_admin_draft(updated),
            reply_markup=draft_keyboard(updated.id),
        )

    return router


def is_admin_message(settings: Settings, message: Message) -> bool:
    if not settings.admin_chat_id:
        return True
    from_user_id = message.from_user.id if message.from_user else None
    return message.chat.id == settings.admin_chat_id or from_user_id == settings.admin_chat_id


def is_admin_callback(settings: Settings, callback: CallbackQuery) -> bool:
    if not settings.admin_chat_id:
        return True
    return callback.from_user.id == settings.admin_chat_id


def callback_article_id(callback: CallbackQuery) -> int | None:
    try:
        return parse_article_id(callback.data)
    except (TypeError, ValueError):
        return None


def parse_article_id(data: str | None) -> int:
    if not data or ":" not in data:
        raise ValueError("Invalid callback data")
    return int(data.split(":", 1)[1])


def format_stats_message(storage: SQLiteStorage) -> str:
    counts = storage.count_by_status()
    lines = ["Статистика базы:"]
    for status in ArticleStatus:
        lines.append(f"{STATUS_LABELS[status]}: {counts.get(status, 0)}")

    recent = storage.recent_drafts(limit=5)
    if recent:
        lines.append("")
        lines.append("Последние черновики:")
        for article in recent:
            score = article.ai_score if article.ai_score is not None else "?"
            lines.append(
                f"#{article.id} [{STATUS_LABELS[article.status]}] {score}/10 — {article.original_title}"
            )
    return "\n".join(lines)


def rating_stars(rating: int) -> str:
    filled = max(0, min(5, rating // 2))
    return "★" * filled + "☆" * (5 - filled)


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
        return


async def safe_edit_callback_message(
    callback: CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)
