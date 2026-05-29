from news_bot.models import ArticleCandidate, ArticleStatus, CuratorDecision
from news_bot.storage import SQLiteStorage


def test_storage_dedupes_by_url_and_tracks_status(tmp_path):
    storage = SQLiteStorage(tmp_path / "bot.db")
    storage.init_db()

    candidate = ArticleCandidate(
        original_title="New mountain route opens",
        original_url="https://example.com/news",
        source_name="Example",
    )

    first, inserted_first = storage.upsert_found(candidate)
    second, inserted_second = storage.upsert_found(candidate)

    assert inserted_first is True
    assert inserted_second is False
    assert first.id == second.id

    drafted = storage.save_draft(
        first.id,
        CuratorDecision(accept=True, score=8, category="outdoor", reason="relevant"),
        "Заголовок\n\nКороткий текст без ссылки.",
    )
    assert drafted.status == ArticleStatus.DRAFTED

    published = storage.mark_published(first.id)
    assert published.status == ArticleStatus.PUBLISHED
    assert published.published_at is not None


def test_storage_counts_and_recent_drafts(tmp_path):
    storage = SQLiteStorage(tmp_path / "bot.db")
    storage.init_db()

    candidate = ArticleCandidate(
        original_title="Trail route",
        original_url="https://example.com/counts",
        source_name="Example",
    )
    article, _ = storage.upsert_found(candidate)
    storage.save_draft(
        article.id,
        CuratorDecision(accept=True, score=9, category="outdoor", reason="ok"),
        "Заголовок\n\nТекст.",
    )

    counts = storage.count_by_status()
    recent = storage.recent_drafts(limit=1)

    assert counts[ArticleStatus.DRAFTED] == 1
    assert recent[0].id == article.id
