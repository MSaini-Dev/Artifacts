import importlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

from backend.agent.brain_langchain.api_manager.sqlite_logger import (
    active_api_call_id,
    complete_api_task,
    create_api_call,
    create_conversation,
    create_interactive,
    create_tool_execution,
    get_db_connection,
    init_logging_schema,
    interactive_scope,
    log_decide,
    log_wait,
    next_iteration_id,
    update_api_call,
    update_interactive,
    update_tool_execution,
)


def test_failover_and_tool_round_are_grouped_as_api_calls(tmp_path):
    database = str(tmp_path / "calls.db")
    init_logging_schema(database)
    conversation_id = create_conversation("API call logging", database)

    with interactive_scope(
        conversation_id=conversation_id,
        payload={"user_prompt": "Find the answer"},
        db_path=database,
    ) as interaction_id:
        iteration_id = next_iteration_id(conversation_id, interaction_id, database)
        first_call = create_api_call(
            conversation_id,
            interaction_id,
            iteration_id,
            url="https://provider-one.test/chat",
            model="model-a",
            api_name="KEY_A",
            payload={"messages": [{"role": "user", "content": "Find the answer"}]},
            interaction_prompt="Find the answer",
            db_path=database,
        )
        call_token = active_api_call_id.set(first_call)
        log_decide(iteration_id, "Parser", "rate limit payload", "RETRY", 0.01, database)
        log_wait(iteration_id, 0.25, database)
        update_api_call(
            first_call,
            request_status="Failed",
            response="rate limit",
            duration_seconds=0.5,
            db_path=database,
        )
        active_api_call_id.reset(call_token)

        tool_response = json.dumps([
            {"id": "tool-1", "name": "lookup", "arguments": {"query": "answer"}}
        ])
        second_call = create_api_call(
            conversation_id,
            interaction_id,
            iteration_id,
            url="https://provider-two.test/chat",
            model="model-b",
            api_name="KEY_B",
            payload={"messages": [{"role": "user", "content": "Find the answer"}]},
            interaction_prompt="Find the answer",
            db_path=database,
        )
        update_api_call(
            second_call,
            request_status="Success",
            final_response=False,
            response=tool_response,
            duration_seconds=0.75,
            db_path=database,
        )

        final_iteration_id = next_iteration_id(conversation_id, interaction_id, database)
        assert final_iteration_id == iteration_id + 1
        final_call = create_api_call(
            conversation_id,
            interaction_id,
            final_iteration_id,
            url="https://provider-two.test/chat",
            model="model-b",
            api_name="KEY_B",
            payload={"messages": [{"role": "tool", "content": "42"}]},
            interaction_prompt="Find the answer",
            db_path=database,
        )
        update_api_call(
            final_call,
            request_status="Success",
            final_response=True,
            response="The answer is 42.",
            duration_seconds=0.2,
            db_path=database,
        )
        update_interactive(
            interaction_id,
            response_status="Final",
            actual_response="The answer is 42.",
            db_path=database,
        )

    with get_db_connection(database) as conn:
        calls = conn.execute(
            """
            SELECT * FROM API_Call_Log
            WHERE Conversation_Id = ?
            ORDER BY API_Call_Id
            """,
            (conversation_id,),
        ).fetchall()
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert len(calls) == 3
    assert calls[0]["Iteration_Id"] == calls[1]["Iteration_Id"]
    assert calls[2]["Iteration_Id"] != calls[1]["Iteration_Id"]
    assert len({call["API_Call_Id"] for call in calls}) == 3
    assert calls[0]["Request_Status"] == "Failed"
    assert calls[0]["Final_Response"] is None
    assert calls[0]["Recovery_Request"] == "rate limit payload"
    assert calls[0]["Wait_Duration_Seconds"] == 0.25
    assert calls[1]["Final_Response"] == 0
    assert calls[2]["Final_Response"] == 1
    assert calls[2]["Duration"] == 0.2
    assert "API_Call_Log" in tables
    assert not ({"Interactive", "Iteration", "Find_Best_API", "Decide", "Wait"} & tables)


def test_api_caller_retries_share_a_logical_iteration(tmp_path, monkeypatch):
    router = importlib.import_module("backend.agent.brain_langchain.api_manager.api_caller")
    database = str(tmp_path / "router.db")
    responses = [
        {
            "status_code": 429,
            "ok": False,
            "text": '{"error":{"message":"rate limit"}}',
            "headers": {},
        },
        {
            "status_code": 200,
            "ok": True,
            "text": '{"choices":[{"message":{"content":"Recovered"}}]}',
            "headers": {},
        },
        {
            "status_code": 200,
            "ok": True,
            "text": '{"choices":[{"message":{"content":"Standalone final"}}]}',
            "headers": {},
        },
    ]

    class MockResponse:
        def __init__(self, value):
            self.status_code = value["status_code"]
            self.ok = value["ok"]
            self.text = value["text"]
            self.headers = value["headers"]

        def json(self):
            return json.loads(self.text)

    providers = iter([
        {
            "provider_url": "https://provider-one.test/chat",
            "provider_name": "Provider One",
            "api_key": "do-not-log-this-secret",
            "key_name": "KEY_ONE",
            "model": "model-a",
            "provider_id": 1,
            "model_id": 1,
            "api_key_id": 1,
        },
        {
            "provider_url": "https://provider-two.test/chat",
            "provider_name": "Provider Two",
            "api_key": "do-not-log-this-secret",
            "key_name": "KEY_TWO",
            "model": "model-b",
            "provider_id": 2,
            "model_id": 2,
            "api_key_id": 2,
        },
        {
            "provider_url": "https://provider-three.test/chat",
            "provider_name": "Provider Three",
            "api_key": "do-not-log-this-secret",
            "key_name": "KEY_THREE",
            "model": "model-c",
            "provider_id": 3,
            "model_id": 3,
            "api_key_id": 3,
        },
    ])
    monkeypatch.setattr(router, "seed_default_data", lambda *_args: None)
    monkeypatch.setattr(router, "find_best_api", lambda **_kwargs: next(providers))
    monkeypatch.setattr(router, "decide_action", lambda _response: {"action": "DISABLE_API_KEY"})
    monkeypatch.setattr(router, "get_parser_mode", lambda: "parser")
    monkeypatch.setattr(router, "update_api_database", lambda **_kwargs: None)
    monkeypatch.setattr(
        router.requests,
        "post",
        lambda *_args, **_kwargs: MockResponse(responses.pop(0)),
    )

    init_logging_schema(database)
    conversation_id = create_conversation("Wrapped API invocation", database)
    with interactive_scope(
        conversation_id=conversation_id,
        payload={"user_prompt": "Try another provider"},
        db_path=database,
    ) as interaction_id:
        result = router.api_caller(
            {"user_prompt": "Try another provider"},
            db_path=database,
        )
        with get_db_connection(database) as conn:
            pending_final_flag = conn.execute(
                """
                SELECT Final_Response FROM API_Call_Log
                WHERE Conversation_Id = ? AND Interaction_Id = ?
                ORDER BY API_Call_Id DESC LIMIT 1
                """,
                (conversation_id, interaction_id),
            ).fetchone()[0]
        assert pending_final_flag == 0
        update_interactive(
            interaction_id,
            response_status="Final",
            actual_response="Recovered",
            db_path=database,
        )

    with get_db_connection(database) as conn:
        calls = conn.execute(
            "SELECT * FROM API_Call_Log ORDER BY API_Call_Id"
        ).fetchall()
    assert result["success"] is True
    assert result["response"] == "Recovered"
    assert result["iteration_id"] == 1
    assert len(calls) == 2
    assert calls[0]["Iteration_Id"] == calls[1]["Iteration_Id"] == 1
    assert all(call["Task_Is_Complete"] == 1 for call in calls)
    assert all(call["Task_Duration_Seconds"] is not None for call in calls)
    assert calls[0]["API_Call_Id"] != calls[1]["API_Call_Id"]
    assert [call["Request_Status"] for call in calls] == ["Failed", "Success"]
    assert [call["Final_Response"] for call in calls] == [None, 1]
    assert calls[0]["Recovery_Action"] == "DISABLE_API_KEY"
    assert calls[0]["Interaction_Prompt"] == "Try another provider"
    assert all("do-not-log-this-secret" not in str(dict(call)) for call in calls)

    standalone = router.api_caller(
        {"user_prompt": "Standalone prompt"},
        db_path=database,
    )
    with get_db_connection(database) as conn:
        standalone_call = conn.execute(
            "SELECT * FROM API_Call_Log ORDER BY API_Call_Id DESC LIMIT 1"
        ).fetchone()
    assert standalone["response"] == "Standalone final"
    assert standalone_call["Interaction_Prompt"] == "Standalone prompt"
    assert standalone_call["Final_Response"] == 1


def test_task_and_tool_execution_records_preserve_status_and_timing(tmp_path):
    database = str(tmp_path / "execution.db")
    init_logging_schema(database)
    conversation_id = create_conversation("Execution trace", database)
    with interactive_scope(
        conversation_id=conversation_id,
        payload={"user_prompt": "Run a lookup"},
        db_path=database,
    ) as interaction_id:
        task_id = next_iteration_id(conversation_id, interaction_id, database)
        api_call_id = create_api_call(
            conversation_id,
            interaction_id,
            task_id,
            payload={"messages": [{"role": "user", "content": "Run a lookup"}]},
            db_path=database,
        )
        update_api_call(
            api_call_id,
            request_status="Success",
            response='[{"id":"call-1","name":"lookup","arguments":{"q":"value"}}]',
            duration_seconds=0.2,
            db_path=database,
        )
        complete_api_task(
            conversation_id,
            interaction_id,
            task_id,
            "2025-01-01T00:00:00.000",
            0.25,
            database,
        )
        tool_id = create_tool_execution(
            conversation_id,
            interaction_id,
            task_id,
            "lookup",
            {"q": "value"},
            tool_call_id="call-1",
            timestamp="2025-01-01T00:00:00.300",
            db_path=database,
        )
        with get_db_connection(database) as conn:
            running_tool = conn.execute(
                "SELECT Status FROM Tool_Execution WHERE ID = ?",
                (tool_id,),
            ).fetchone()
        assert running_tool["Status"] == "Running"
        update_tool_execution(
            tool_id,
            "Success",
            response={"result": 42},
            duration_seconds=0.1,
            db_path=database,
        )

    with get_db_connection(database) as conn:
        task = conn.execute(
            "SELECT * FROM API_Call_Log WHERE API_Call_Id = ?",
            (api_call_id,),
        ).fetchone()
        tool = conn.execute(
            "SELECT * FROM Tool_Execution WHERE ID = ?",
            (tool_id,),
        ).fetchone()

    assert task["Is_Complete"] == 1
    assert task["Task_Is_Complete"] == 1
    assert task["Task_Started_At"] == "2025-01-01T00:00:00.000"
    assert task["Task_Duration_Seconds"] == 0.25
    assert tool["Task_Id"] == task_id
    assert tool["Tool_Call_Id"] == "call-1"
    assert tool["Parameters"] == '{"q": "value"}'
    assert tool["Response"] == '{"result": 42}'
    assert tool["Status"] == "Success"
    assert tool["Duration"] == 0.1


def test_logs_endpoint_orders_tasks_and_tools_chronologically(tmp_path, monkeypatch):
    database = str(tmp_path / "endpoint.db")
    monkeypatch.setenv("DB_PATH", database)
    module_name = "_frontend_server_logs_test"
    server_path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location(module_name, server_path)
    assert spec is not None and spec.loader is not None
    server = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, server)
    spec.loader.exec_module(server)

    init_logging_schema(database)
    conversation_id = create_conversation("Ordered trace", database)
    with interactive_scope(conversation_id=conversation_id, db_path=database) as interaction_id:
        first_task_id = next_iteration_id(conversation_id, interaction_id, database)
        first_call_id = create_api_call(
            conversation_id,
            interaction_id,
            first_task_id,
            payload={"messages": [{"role": "user", "content": "Look up a value"}]},
            timestamp="2025-01-01T00:00:00.000",
            db_path=database,
        )
        update_api_call(
            first_call_id,
            request_status="Success",
            final_response=False,
            response="tool call",
            duration_seconds=0.2,
            db_path=database,
        )
        complete_api_task(
            conversation_id,
            interaction_id,
            first_task_id,
            "2025-01-01T00:00:00.000",
            0.2,
            database,
        )
        tool_id = create_tool_execution(
            conversation_id,
            interaction_id,
            first_task_id,
            "lookup",
            {"query": "value"},
            timestamp="2025-01-01T00:00:00.250",
            db_path=database,
        )
        update_tool_execution(
            tool_id,
            "Success",
            response="found",
            duration_seconds=0.1,
            db_path=database,
        )

        final_task_id = next_iteration_id(conversation_id, interaction_id, database)
        final_call_id = create_api_call(
            conversation_id,
            interaction_id,
            final_task_id,
            payload={"messages": [{"role": "tool", "content": "found"}]},
            timestamp="2025-01-01T00:00:00.500",
            db_path=database,
        )
        update_api_call(
            final_call_id,
            request_status="Success",
            final_response=True,
            response="The value was found.",
            duration_seconds=0.1,
            db_path=database,
        )
        complete_api_task(
            conversation_id,
            interaction_id,
            final_task_id,
            "2025-01-01T00:00:00.500",
            0.1,
            database,
        )

    details = server.get_conversation_details(conversation_id)
    records = details["interactives"][0]["execution_records"]
    assert [record["type"] for record in records] == ["task", "tool", "task"]
    assert records[0]["task"]["ID"] == first_task_id
    assert records[1]["tool"]["ID"] == tool_id
    assert records[1]["tool"]["Task_Id"] == first_task_id
    assert records[2]["task"]["ID"] == final_task_id
    assert records[2]["task"]["Final_Response"] == "The value was found."


def test_legacy_logs_migrate_once_and_keep_recoverable_data(tmp_path):
    database = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE Conversation (
            ID INTEGER PRIMARY KEY,
            Title TEXT,
            Created_At TEXT,
            Updated_At TEXT
        );
        CREATE TABLE providers (name TEXT, base_url TEXT);
        CREATE TABLE Interactive (
            ID INTEGER PRIMARY KEY,
            Conversation_Id INTEGER,
            Created_At TEXT,
            Updated_At TEXT,
            Payload TEXT,
            Response_Status TEXT,
            Actual_Response TEXT,
            Iteration_No INTEGER,
            Duration_Seconds REAL
        );
        CREATE TABLE Iteration (
            ID INTEGER PRIMARY KEY,
            Interactive_Id INTEGER,
            Status TEXT,
            Request_Payload TEXT,
            Actual_Response TEXT,
            Time_Take_to_Process TEXT
        );
        CREATE TABLE Find_Best_API (
            ID INTEGER PRIMARY KEY,
            Iteration_Id INTEGER,
            Model TEXT,
            Provider TEXT,
            API TEXT,
            Time_Take_to_Process TEXT
        );
        CREATE TABLE Decide (
            ID INTEGER PRIMARY KEY,
            Iteration_Id INTEGER,
            Mode TEXT,
            Request TEXT,
            Action TEXT,
            Time_Take_To_Process TEXT
        );
        CREATE TABLE Wait (
            ID INTEGER PRIMARY KEY,
            Iteration_Id INTEGER,
            Time_To_Be_Waited TEXT
        );

        INSERT INTO Conversation VALUES (7, 'Old conversation', '2025-01-01', '2025-01-02');
        INSERT INTO providers VALUES ('Provider A', 'https://provider-a.test/chat');
        INSERT INTO Interactive VALUES (
            42, 7, '2025-01-02 10:00:00', '2025-01-02 10:01:00',
            '{"user_prompt":"Legacy prompt"}', 'Final', 'Final answer', 3, 2.0
        );
        INSERT INTO Iteration VALUES (100, 42, 'Failed', NULL, 'rate limit', '00:00:01.250');
        INSERT INTO Iteration VALUES (
            101, 42, 'Success', NULL,
            '[{"id":"tool-1","name":"lookup","arguments":{"q":"x"}}]', '00:00:02.500'
        );
        INSERT INTO Iteration VALUES (102, 42, 'Success', NULL, 'Final answer', '00:00:00.500');
        INSERT INTO Find_Best_API VALUES (200, 100, 'model-a', 'Provider A', 'KEY_A', NULL);
        INSERT INTO Find_Best_API VALUES (201, 101, 'model-a', 'Provider A', 'KEY_A', NULL);
        INSERT INTO Find_Best_API VALUES (202, 102, 'model-b', 'Provider A', 'KEY_B', NULL);
        INSERT INTO Decide VALUES (300, 100, 'Parser', 'legacy recovery request', 'RETRY', NULL);
        INSERT INTO Wait VALUES (400, 100, '00:00:00.250');
        """
    )
    conn.commit()
    conn.close()

    init_logging_schema(database)
    init_logging_schema(database)

    with get_db_connection(database) as migrated:
        calls = migrated.execute(
            "SELECT * FROM API_Call_Log ORDER BY API_Call_Id"
        ).fetchall()
        tables = {
            row["name"]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        conversation = migrated.execute(
            "SELECT Next_Interaction_Id FROM Conversation WHERE ID = 7"
        ).fetchone()

    assert len(calls) == 3
    assert [call["Iteration_Id"] for call in calls] == [1, 1, 2]
    assert [call["Request_Status"] for call in calls] == ["Failed", "Success", "Success"]
    assert [call["Final_Response"] for call in calls] == [None, 0, 1]
    assert calls[0]["URL"] == "https://provider-a.test/chat"
    assert calls[0]["Recovery_Request"] == "legacy recovery request"
    assert calls[0]["Wait_Duration_Seconds"] == 0.25
    assert calls[0]["Interaction_Prompt"] == "Legacy prompt"
    assert all(call["Legacy_Record"] == 1 for call in calls)
    assert all(call["Payload"] is None for call in calls)
    assert conversation["Next_Interaction_Id"] == 43
    assert "API_Call_Log" in tables
    assert not ({"Interactive", "Iteration", "Find_Best_API", "Decide", "Wait"} & tables)

    assert create_interactive(7, db_path=database) == 43
