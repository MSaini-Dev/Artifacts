import importlib
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent.brain_langchain.api_manager.api_caller import (
    GEMINI_DUMMY_SIGNATURE,
    _prepare_messages_for_provider,
    call_openai_compatible,
    decide_with_laya,
    parse_api_response,
    update_api_database,
)
from backend.agent.brain_langchain.api_manager.db_updater import get_connection, init_database
from backend.agent.brain_langchain.langchain_wrapper import BrainChatModel, _lc_messages_to_openai_messages


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def test_gemini_real_signature_is_preserved_without_mutating_input():
    signature = {"google": {"thought_signature": "real-signature"}}
    messages = [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call-1", "extra_content": signature}],
    }]

    prepared = _prepare_messages_for_provider(messages, GEMINI_URL, "gemini-3.5-flash")

    assert prepared[0]["tool_calls"][0]["extra_content"] == signature
    assert prepared is not messages
    assert prepared[0] is not messages[0]
    assert prepared[0]["tool_calls"] is not messages[0]["tool_calls"]
    assert messages[0]["tool_calls"][0]["extra_content"] == signature


def test_gemini_3_adds_dummy_signature_to_first_tool_call():
    messages = [{
        "role": "assistant",
        "tool_calls": [
            {"id": "call-1", "function": {"name": "first"}},
            {"id": "call-2", "function": {"name": "second"}},
        ],
    }]

    prepared = _prepare_messages_for_provider(messages, GEMINI_URL, "gemini-3.5-flash")

    assert prepared[0]["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": GEMINI_DUMMY_SIGNATURE}
    }
    assert "extra_content" not in prepared[0]["tool_calls"][1]
    assert "extra_content" not in messages[0]["tool_calls"][0]


def test_non_gemini_provider_strips_extra_content_without_mutating_input():
    messages = [{
        "role": "assistant",
        "tool_calls": [{"id": "call-1", "extra_content": {"google": {"thought_signature": "sig"}}}],
    }]

    prepared = _prepare_messages_for_provider(messages, "https://provider.test/v1/chat/completions", "model-a")

    assert "extra_content" not in prepared[0]["tool_calls"][0]
    assert messages[0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig"


def test_gemini_older_model_does_not_get_dummy_signature():
    messages = [{"role": "assistant", "tool_calls": [{"id": "call-1"}]}]

    prepared = _prepare_messages_for_provider(messages, GEMINI_URL, "gemini-2.5-flash")

    assert "extra_content" not in prepared[0]["tool_calls"][0]


def test_tool_call_extra_content_survives_langchain_message_conversion(monkeypatch):
    signature = {"google": {"thought_signature": "real-signature"}}
    monkeypatch.setattr(
        "backend.agent.brain_langchain.langchain_wrapper.brain",
        lambda **_kwargs: {
            "api_success": True,
            "api_response": None,
            "tool_calls": [{
                "id": "call-1",
                "name": "list_dir",
                "arguments": {"path": "."},
                "extra_content": signature,
            }],
            "chosen": {},
        },
    )

    response = BrainChatModel()._generate([HumanMessage(content="List files")])
    assistant_message = response.generations[0].message

    assert assistant_message.tool_calls == [{
        "name": "list_dir",
        "args": {"path": "."},
        "id": "call-1",
        "type": "tool_call",
    }]
    assert assistant_message.additional_kwargs["tool_call_extras"] == {"call-1": signature}

    converted = _lc_messages_to_openai_messages([
        HumanMessage(content="List files"),
        assistant_message,
        ToolMessage(content="files", tool_call_id="call-1", name="list_dir"),
    ])
    assert converted[1]["tool_calls"][0]["extra_content"] == signature


def test_provider_tool_call_parser_keeps_extra_content(monkeypatch):
    signature = {"google": {"thought_signature": "real-signature"}}
    response = SimpleNamespace(
        ok=True,
        status_code=200,
        headers={},
        text="{}",
        json=lambda: {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "list_dir", "arguments": '{"path":"."}'},
                        "extra_content": signature,
                    }],
                },
            }],
        },
    )
    api_caller_module = importlib.import_module("backend.agent.brain_langchain.api_manager.api_caller")
    monkeypatch.setattr(api_caller_module.requests, "post", lambda *_args, **_kwargs: response)

    result = call_openai_compatible(
        data={},
        url=GEMINI_URL,
        provider_label="Gemini",
        api="key",
        model="gemini-3.5-flash",
    )

    assert result["tool_calls"][0] == {
        "id": "call-1",
        "name": "list_dir",
        "arguments": {"path": "."},
        "extra_content": signature,
    }


def test_tool_compatibility_error_skips_model_for_this_request():
    decision = parse_api_response({
        "status_code": 400,
        "response": "Function call is missing a thought_signature in functionCall parts.",
    })

    assert decision == {
        "action": "SKIP_MODEL_THIS_REQUEST",
        "reason": "Function call is missing a thought_signature in functionCall parts.",
        "block_seconds": None,
    }


def test_laya_cannot_disable_model_for_a_400_request(monkeypatch):
    class FakeRouter:
        def predict(self, _state, _questions):
            return {"answers": {"action": {"choice": "DISABLE_MODEL"}}}

    laya_module = ModuleType("laya")
    laya_module.Router = FakeRouter
    monkeypatch.setitem(sys.modules, "laya", laya_module)

    decision = decide_with_laya({
        "status_code": 400,
        "response": "Function call is missing a thought_signature in functionCall parts.",
    })

    assert decision["action"] == "SKIP_MODEL_THIS_REQUEST"
    assert decision["block_seconds"] is None


def test_skip_model_action_does_not_change_database(tmp_path):
    database = str(tmp_path / "api-store.db")
    init_database(database)
    now = "2026-01-01T00:00:00"
    with get_connection(database) as conn:
        provider_id = conn.execute(
            "INSERT INTO providers (name, base_url, created_at, last_modify) VALUES (?, ?, ?, ?)",
            ("provider", "https://provider.test", now, now),
        ).lastrowid
        model_id = conn.execute(
            "INSERT INTO models (provider_id, name, created_at, last_modify) VALUES (?, ?, ?, ?)",
            (provider_id, "model-a", now, now),
        ).lastrowid
        api_key_id = conn.execute(
            "INSERT INTO api_keys (provider_id, unique_name, env_key, created_at, last_modify) VALUES (?, ?, ?, ?, ?)",
            (provider_id, "key-a", "API_KEY_A", now, now),
        ).lastrowid
        before = conn.execute(
            "SELECT status, rate_limit, disabled_reason FROM models WHERE id = ?",
            (model_id,),
        ).fetchone()

    result = update_api_database(
        database,
        provider_id,
        model_id,
        api_key_id,
        {
            "action": "SKIP_MODEL_THIS_REQUEST",
            "reason": "Missing thought_signature",
            "block_seconds": None,
        },
    )

    with sqlite3.connect(database) as conn:
        after = conn.execute(
            "SELECT status, rate_limit, disabled_reason FROM models WHERE id = ?",
            (model_id,),
        ).fetchone()

    assert result["updated"] is False
    assert tuple(after) == tuple(before)
