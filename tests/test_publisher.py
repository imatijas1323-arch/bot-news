from datetime import datetime, timezone

from news_bot.config import Settings
from news_bot.models import ArticleRecord, ArticleStatus
from news_bot.publisher import build_image_search_queries, build_published_text, looks_like_research_article


def make_article(**overrides):
    data = dict(
        id=1,
        original_title="Scientists found a new way to train marathon runners",
        original_url="https://example.com/study",
        source_name="Journal",
        summary="A university study measured endurance training effects.",
        category="sport",
        image_url=None,
        status=ArticleStatus.DRAFTED,
        ai_score=9,
        generated_text="Заголовок\n\nУчёные проверили новый подход к тренировкам.",
        is_breaking=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        published_at=None,
        user_rating=None,
        rating_reason=None,
        summary_ru="",
    )
    data.update(overrides)
    return ArticleRecord(**data)


def test_research_article_gets_source_link_by_default():
    article = make_article()
    settings = Settings(_env_file=None)

    assert looks_like_research_article(article)
    assert build_published_text(article, settings).endswith("Источник: https://example.com/study")


def test_non_research_article_does_not_get_source_link_by_default():
    article = make_article(
        original_title="The Speed Project is still a beast",
        original_url="https://example.com/speed-project",
        source_name="Magazine",
        summary="A relay race from LA to Vegas keeps its underground format.",
        generated_text="The Speed Project жив\n\nГонка из ЛА в Вегас осталась странной и красивой.",
    )
    settings = Settings(_env_file=None)

    assert not looks_like_research_article(article)
    assert "Источник:" not in build_published_text(article, settings)


def test_image_search_prefers_original_title_for_unsplash():
    article = make_article(
        original_title="The Evolution of Courtney Dauwalter",
        generated_text="Кортни Дауолтер: королева ультрамарафона\n\nТекст",
        category="sport | culture | people",
    )

    queries = build_image_search_queries(article)

    assert queries[0] == "The Evolution of Courtney Dauwalter sport culture people"
    assert "Кортни Дауолтер" in queries[1]
    assert "trail running ultramarathon athlete mountains" in queries
