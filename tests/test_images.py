from news_bot.images import category_keywords, compact_query


def test_category_keywords_support_compound_categories():
    keywords = category_keywords("sport | culture | people")

    assert "sport athlete endurance" in keywords
    assert "sport culture community lifestyle" in keywords
    assert "athlete portrait endurance" in keywords


def test_compact_query_removes_pipe_noise():
    assert compact_query("Courtney | sport   culture") == "Courtney sport culture"
