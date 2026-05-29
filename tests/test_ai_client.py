import pytest

from news_bot.ai_client import AIClientError, extract_json_object, normalize_api_keys, parse_accept, parse_curator_response


def test_parse_curator_response_from_json_fence():
    decision = parse_curator_response(
        "```json\n"
        "{\"accept\": true, \"score\": 9, \"category\": \"outdoor\", \"reason\": \"strong fit\"}\n"
        "```"
    )

    assert decision.accept is True
    assert decision.score == 9
    assert decision.category == "outdoor"


def test_parse_curator_response_clamps_bad_score():
    decision = parse_curator_response(
        '{"decision": "publish", "score": "not-a-number", "category": "gear"}'
    )

    assert decision.accept is True
    assert decision.score == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (1, True),
        (0, False),
        ("да", True),
        ("reject", False),
    ],
)
def test_parse_accept(value, expected):
    assert parse_accept(value) is expected


def test_extract_json_object_rejects_plain_text():
    with pytest.raises(AIClientError):
        extract_json_object("just text")

def test_normalize_api_keys_removes_empty_and_duplicates():
    assert normalize_api_keys(["", "key-1", " key-2 ", "key-1"]) == ["key-1", "key-2"]

