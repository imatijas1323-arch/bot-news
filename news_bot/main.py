from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher

from .ai_client import create_ai_client
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

    ai_client = create_ai_client(settings)
    writer_client = (
        create_ai_client(settings, model=settings.ai_writer_model)
        if settings.ai_writer_model
        else ai_client
    )
    bot = Bot(token=settings.bot_token)
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

