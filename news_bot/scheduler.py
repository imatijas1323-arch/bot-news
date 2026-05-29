from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .ai_client import BaseAIClient
from .config import Settings
from .curator import NewsPipeline
from .publisher import send_admin_preview
from .storage import SQLiteStorage


logger = logging.getLogger(__name__)


def build_scheduler(
    *,
    settings: Settings,
    storage: SQLiteStorage,
    ai_client: BaseAIClient,
    bot: Bot,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone_name)
    pipeline = NewsPipeline(settings=settings, storage=storage, ai_client=ai_client)

    async def scheduled_check() -> None:
        try:
            await pipeline.run_once(
                on_draft=lambda article: send_admin_preview(bot, settings, article)
            )
        except Exception:
            logger.exception("Scheduled news check failed")

    async def scheduled_breaking_check() -> None:
        try:
            await pipeline.run_once(
                on_draft=lambda article: send_admin_preview(bot, settings, article),
                breaking=True,
            )
        except Exception:
            logger.exception("Scheduled breaking check failed")

    scheduler.add_job(
        scheduled_check,
        trigger="cron",
        hour=settings.news_check_hours,
        minute=0,
        id="news_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        scheduled_breaking_check,
        trigger="interval",
        minutes=settings.breaking_check_interval_minutes,
        id="breaking_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler

