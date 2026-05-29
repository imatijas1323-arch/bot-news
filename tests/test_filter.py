from news_bot.filter import is_topic_candidate, keyword_score
from news_bot.models import ArticleCandidate


def test_keyword_filter_accepts_relevant_outdoor_news():
    article = ArticleCandidate(
        original_title="Salomon launches new trail running shoe",
        original_url="https://example.com/a",
        source_name="Example",
        summary="Outdoor gear for mountain races",
    )

    assert is_topic_candidate(article)
    assert keyword_score(article) > 0


def test_keyword_filter_rejects_crypto_noise():
    article = ArticleCandidate(
        original_title="Crypto casino launches betting campaign",
        original_url="https://example.com/b",
        source_name="Example",
    )

    assert not is_topic_candidate(article)


def test_keyword_filter_does_not_accept_by_source_name_only():
    article = ArticleCandidate(
        original_title="Yosemite dropped timed entry and delivered visitor chaos",
        original_url="https://example.com/yosemite-chaos",
        source_name="GearJunkie",
        summary="Visitors faced long queues after the park changed reservation rules.",
    )

    assert not is_topic_candidate(article)
    assert keyword_score(article) <= 0

