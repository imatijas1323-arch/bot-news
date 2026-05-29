from news_bot.validator import clean_ai_text, validate_post


def test_validate_post_blocks_links_emoji_and_hashtags():
    result = validate_post("Заголовок\n\nТекст https://example.com #tag 🏃")

    assert not result.ok
    assert "contains_url" in result.errors
    assert "contains_hashtag" in result.errors
    assert "contains_emoji" in result.errors


def test_clean_ai_text_removes_code_fence():
    assert clean_ai_text("```text\nЗаголовок\n\nТекст\n```") == "Заголовок\n\nТекст"
