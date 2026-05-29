from __future__ import annotations

import asyncio

from .ai_client import AIClientError, create_ai_client
from .config import PROVIDER_KEY_ENV, get_settings
from .models import ArticleCandidate


async def main() -> None:
    settings = get_settings()
    provider = settings.ai_provider.lower()

    if provider != "stub" and not settings.effective_ai_api_key:
        key_hint = PROVIDER_KEY_ENV.get(provider, "AI_API_KEY")
        raise SystemExit(f"Missing AI key for provider {settings.ai_provider}: {key_hint}")

    article = ArticleCandidate(
        original_title="Salomon updates its trail running line for long mountain days",
        original_url="https://example.com/trail-running-test",
        source_name="AI smoke test",
        summary=(
            "A short test article about trail running shoes, outdoor gear, "
            "and endurance culture. This is not a real news item."
        ),
    )

    client = create_ai_client(settings)
    try:
        decision = await client.curate(article)
        print("curator:")
        print(f"  accept={decision.accept}")
        print(f"  score={decision.score}")
        print(f"  category={decision.category}")
        print(f"  reason={decision.reason}")

        if decision.accept:
            post = await client.write(article, decision)
            print("post:")
            print(post)
    except AIClientError as exc:
        raise SystemExit(f"AI check failed: {exc}") from exc
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

