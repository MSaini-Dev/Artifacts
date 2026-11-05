from backend.server import _extract_user_text


def test_extract_user_text_prefers_latest_structured_user_message():
    payload = {
        "user_prompt": "User: old question\n\nAssistant: old answer\n\nUser: current question",
        "messages": [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "current question"},
        ],
    }

    assert _extract_user_text(payload) == "current question"


def test_extract_user_text_falls_back_to_flat_prompt():
    assert _extract_user_text({"user_prompt": "current question"}) == "current question"


def test_extract_user_text_unwraps_flattened_transcript():
    transcript = """User: User: old question

Assistant: old answer

User: User: its jaipur not delhi send the mail with more detail"""

    assert _extract_user_text({"messages": [{"role": "user", "content": transcript}]}) == (
        "its jaipur not delhi send the mail with more detail"
    )


def test_extract_user_text_uses_last_user_line_from_flat_prompt():
    transcript = """User: first question

Assistant: first answer

User: so delete the unnecessary tools by yourself"""

    assert _extract_user_text({"user_prompt": transcript}) == (
        "so delete the unnecessary tools by yourself"
    )


def test_extract_user_text_cleans_serialized_transcript_string():
    transcript = "User: old question\nAssistant: old answer\nUser: latest question"

    assert _extract_user_text(transcript) == "latest question"
