from datetime import datetime, timezone

from news_bot.models import ArticleCandidate, ArticleRecord, ArticleStatus, CuratorDecision
from news_bot.writer import PromptStore, build_curator_prompt, build_feedback_context, build_writer_prompt


def make_record(rating, reason):
    return ArticleRecord(
        id=1,
        original_title="Yosemite dropped timed entry and delivered visitor chaos",
        original_url="https://example.com/yosemite",
        source_name="GearJunkie",
        summary="Visitors faced queues after reservation rules changed.",
        category="travel",
        image_url=None,
        status=ArticleStatus.SKIPPED,
        ai_score=8,
        generated_text="Yosemite visitor chaos",
        is_breaking=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        published_at=None,
        user_rating=rating,
        rating_reason=reason,
        summary_ru="Queues and reservation chaos in a national park.",
    )


def test_build_feedback_context_includes_rating_reason_and_rules():
    context = build_feedback_context([make_record(2, "not_topic")])

    assert "сильный сигнал" in context
    assert "Низко оценено" in context
    assert "не наша тема" in context
    assert "Yosemite dropped timed entry" in context

def write_prompt_files(tmp_path):
    (tmp_path / "curator_prompt.txt").write_text("CURATOR", encoding="utf-8")
    (tmp_path / "writer_prompt.txt").write_text("WRITER", encoding="utf-8")
    (tmp_path / "rewrite_prompt.txt").write_text("REWRITE", encoding="utf-8")
    (tmp_path / "editor_profile.txt").write_text("Редакционный профиль: архив любит странные endurance-истории", encoding="utf-8")
    return PromptStore(tmp_path)


def test_editor_profile_is_added_to_curator_and_writer_prompts(tmp_path):
    prompt_store = write_prompt_files(tmp_path)
    article = ArticleCandidate(
        original_title="Backyard Ultra record",
        original_url="https://example.com/backyard",
        source_name="Example",
        summary="A runner keeps going in an unusual endurance format.",
    )

    curator_system, _ = build_curator_prompt(prompt_store, article)
    writer_system, _ = build_writer_prompt(
        prompt_store,
        article,
        CuratorDecision(accept=True, score=9, category="sport", reason="archive fit"),
    )

    assert "CURATOR" in curator_system
    assert "WRITER" in writer_system
    assert "Редакционный профиль" in curator_system
    assert "странные endurance-истории" in writer_system

