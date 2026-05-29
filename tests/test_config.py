from news_bot.config import Settings


def test_gemini_api_keys_are_deduped_in_order():
    settings = Settings(
        BOT_TOKEN="token",
        ADMIN_CHAT_ID=1,
        TARGET_CHAT_ID=-1,
        NEWS_THREAD_ID=2,
        AI_PROVIDER="gemini",
        AI_API_KEY="primary",
        GEMINI_API_KEY="primary",
        GEMINI_API_KEYS="reserve-1, reserve-2, reserve-1",
        _env_file=None,
    )

    assert settings.effective_ai_api_keys == ["primary", "reserve-1", "reserve-2"]
    assert settings.effective_ai_api_key == "primary"
