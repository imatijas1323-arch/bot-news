from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher

from .ai_client import create_ai_client, gemini_quota_date
from .bot import build_router, main_keyboard
from .config import get_settings
from .scheduler import build_scheduler
from .storage import SQLiteStorage


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    settings = get_settings()
    settings.validate_runtime()

    storage = SQLiteStorage(settings.database_path, timezone_name=settings.timezone_name)
    storage.init_db()

    bot = Bot(token=settings.bot_token)

    sent_quota_alerts: set[tuple[object, str]] = set()

    async def notify_admin(text: str) -> None:
        if not settings.admin_chat_id:
            return
        key = (gemini_quota_date(), text)
        if key in sent_quota_alerts:
            return
        sent_quota_alerts.add(key)
        # keep set small — drop entries from older PT days
        for stale in [k for k in sent_quota_alerts if k[0] != gemini_quota_date()]:
            sent_quota_alerts.discard(stale)
        try:
            await bot.send_message(chat_id=settings.admin_chat_id, text=text)
        except Exception:
            logging.getLogger(__name__).exception("Failed to send quota alert")

    ai_client = create_ai_client(settings, notify=notify_admin)
    writer_client = (
        create_ai_client(settings, model=settings.ai_writer_model, notify=notify_admin)
        if settings.ai_writer_model
        else ai_client
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            settings=settings,
            storage=storage,
            ai_client=ai_client,
            writer_client=writer_client,
        )
    )

    scheduler = build_scheduler(
        settings=settings,
        storage=storage,
        ai_client=ai_client,
        bot=bot,
    )
    scheduler.start()

    if settings.admin_chat_id:
        try:
            await bot.send_message(
                chat_id=settings.admin_chat_id,
                text="Бот запущен и готов к работе.",
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    polling_task = asyncio.create_task(dispatcher.start_polling(bot))
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {polling_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    for task in done:
        task.result()

    scheduler.shutdown(wait=False)
    await ai_client.aclose()
    if writer_client is not ai_client:
        await writer_client.aclose()
    await bot.session.close()
    storage.close()


if __name__ == "__main__":
    asyncio.run(main())

