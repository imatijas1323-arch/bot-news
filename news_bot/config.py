from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_RSS_FEEDS = [
    "https://www.runnersworld.com/rss/all.xml/",
    "https://www.outsideonline.com/feed/",
    "https://www.advnture.com/feeds.xml",
    "https://hypebeast.com/feed",
    "https://gearjunkie.com/feed",
    "https://trailrunnermag.com/feed/",
    "https://www.matadornetwork.com/feed/",
    "https://velomania.ru/feed",
    "https://risk.ru/rss",
    "https://www.triathlete.com/feed/",
    "https://www.climbing.com/feed/",
    "https://www.backpacker.com/feed/",
    "https://www.letsrun.com/feed/",
    "https://www.uphillathlete.com/feed/",
    "https://swimswam.com/feed/",
    "https://www.cyclingweekly.com/rss",
    "https://marathonec.ru/feed/",
    "https://nogibogi.com/feed/",
]


PROVIDER_KEY_ENV = {
    "gemini": "GEMINI_API_KEY, GEMINI_API_KEYS, or AI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY or AI_API_KEY",
    "openai-compatible": "AI_API_KEY",
    "openai_compatible": "AI_API_KEY",
    "amvera": "AI_API_KEY",
}


def default_database_path() -> Path:
    amvera_data = Path("/data")
    if amvera_data.exists():
        return amvera_data / "news_bot.db"
    return Path("data") / "news_bot.db"


def parse_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bot_token: str = Field("", validation_alias="BOT_TOKEN")
    admin_chat_id: int = Field(0, validation_alias="ADMIN_CHAT_ID")
    target_chat_id: int = Field(0, validation_alias="TARGET_CHAT_ID")
    news_thread_id: int = Field(0, validation_alias="NEWS_THREAD_ID")

    ai_provider: str = Field("gemini", validation_alias="AI_PROVIDER")
    ai_model: str = Field("gemini-2.5-flash-lite", validation_alias="AI_MODEL")
    ai_writer_model: str = Field("", validation_alias="AI_WRITER_MODEL")
    ai_api_key: str = Field("", validation_alias="AI_API_KEY")
    ai_base_url: str = Field("", validation_alias="AI_BASE_URL")
    gemini_api_key: str = Field("", validation_alias="GEMINI_API_KEY")
    gemini_api_keys_raw: str = Field("", validation_alias="GEMINI_API_KEYS")
    openrouter_api_key: str = Field("", validation_alias="OPENROUTER_API_KEY")

    ai_fallback_provider: str = Field("openrouter", validation_alias="AI_FALLBACK_PROVIDER")
    ai_fallback_model: str = Field("qwen/qwen3-30b-a3b:free", validation_alias="AI_FALLBACK_MODEL")
    ai_fallback_api_key: str = Field("", validation_alias="AI_FALLBACK_API_KEY")
    ai_fallback_base_url: str = Field(
        "https://openrouter.ai/api/v1",
        validation_alias="AI_FALLBACK_BASE_URL",
    )

    database_path: Path = Field(default_factory=default_database_path, validation_alias="DATABASE_PATH")
    prompt_dir: Path = Field(Path("prompts"), validation_alias="PROMPT_DIR")
    rss_feeds_raw: str = Field(",".join(DEFAULT_RSS_FEEDS), validation_alias="RSS_FEEDS")

    max_posts_per_day: int = Field(1, validation_alias="MAX_POSTS_PER_DAY")
    max_drafts_per_day: int = Field(6, validation_alias="MAX_DRAFTS_PER_DAY")
    max_candidates_per_run: int = Field(50, validation_alias="MAX_CANDIDATES_PER_RUN")
    max_previews_per_run: int = Field(3, validation_alias="MAX_PREVIEWS_PER_RUN")
    news_check_hours: str = Field("12,18,22", validation_alias="NEWS_CHECK_HOURS")
    news_check_interval_hours: int = Field(4, validation_alias="NEWS_CHECK_INTERVAL_HOURS")
    min_ai_score: int = Field(8, validation_alias="MIN_AI_SCORE")

    breaking_check_interval_minutes: int = Field(180, validation_alias="BREAKING_CHECK_INTERVAL_MINUTES")
    breaking_max_age_hours: int = Field(3, validation_alias="BREAKING_MAX_AGE_HOURS")
    breaking_min_ai_score: int = Field(9, validation_alias="BREAKING_MIN_AI_SCORE")
    max_breaking_posts_per_day: int = Field(2, validation_alias="MAX_BREAKING_POSTS_PER_DAY")

    auto_publish: bool = Field(False, validation_alias="AUTO_PUBLISH")
    show_source_link: bool = Field(False, validation_alias="SHOW_SOURCE_LINK")
    allow_emoji: bool = Field(False, validation_alias="ALLOW_EMOJI")
    allow_hashtags: bool = Field(False, validation_alias="ALLOW_HASHTAGS")

    timezone_name: str = Field("Europe/Moscow", validation_alias="TIMEZONE")
    target_min_post_chars: int = Field(400, validation_alias="TARGET_MIN_POST_CHARS")
    target_max_post_chars: int = Field(900, validation_alias="TARGET_MAX_POST_CHARS")
    hard_max_post_chars: int = Field(1200, validation_alias="HARD_MAX_POST_CHARS")
    http_timeout_seconds: float = Field(20.0, validation_alias="HTTP_TIMEOUT_SECONDS")
    ai_request_delay_seconds: float = Field(4.0, validation_alias="AI_REQUEST_DELAY_SECONDS")
    ai_primary_timeout_seconds: float = Field(30.0, validation_alias="AI_PRIMARY_TIMEOUT_SECONDS")
    ai_candidate_timeout_seconds: float = Field(45.0, validation_alias="AI_CANDIDATE_TIMEOUT_SECONDS")
    unsplash_access_key: str = Field("", validation_alias="UNSPLASH_ACCESS_KEY")

    @property
    def rss_feeds(self) -> list[str]:
        parsed = parse_csv(self.rss_feeds_raw)
        return parsed or list(DEFAULT_RSS_FEEDS)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def effective_ai_api_key(self) -> str:
        return self.api_key_for_provider(self.ai_provider, primary=True)

    @property
    def effective_ai_api_keys(self) -> list[str]:
        return self.api_keys_for_provider(self.ai_provider, primary=True)

    @property
    def effective_fallback_api_key(self) -> str:
        return self.api_key_for_provider(self.ai_fallback_provider, primary=False)

    @property
    def effective_fallback_api_keys(self) -> list[str]:
        return self.api_keys_for_provider(self.ai_fallback_provider, primary=False)

    def api_key_for_provider(self, provider: str, *, primary: bool) -> str:
        keys = self.api_keys_for_provider(provider, primary=primary)
        return keys[0] if keys else ""

    def api_keys_for_provider(self, provider: str, *, primary: bool) -> list[str]:
        provider_key = provider.lower()
        explicit_key = self.ai_api_key if primary else self.ai_fallback_api_key
        keys: list[str] = []
        if explicit_key:
            keys.append(explicit_key)
        if provider_key == "gemini":
            keys.append(self.gemini_api_key)
            keys.extend(parse_csv(self.gemini_api_keys_raw))
        elif provider_key == "openrouter":
            keys.append(self.openrouter_api_key)
        return dedupe_strings(keys)

    def validate_runtime(self) -> None:
        missing = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.admin_chat_id:
            missing.append("ADMIN_CHAT_ID")
        if not self.target_chat_id:
            missing.append("TARGET_CHAT_ID")
        if not self.news_thread_id:
            missing.append("NEWS_THREAD_ID")

        provider = self.ai_provider.lower()
        if provider != "stub" and not self.effective_ai_api_key:
            missing.append(PROVIDER_KEY_ENV.get(provider, "AI_API_KEY"))

        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variables: {joined}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
