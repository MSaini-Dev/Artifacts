"""
test_db_api.py — Comprehensive test suite for SQLite DB-backed API Store & failover router.
"""

import sys
import os
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

from backend.agent.brain_langchain.api_manager.api_caller import api_caller, find_best_api
from backend.agent.brain_langchain.api_manager.db_updater import seed_default_data, get_connection, DEFAULT_DB_FILE
from backend.agent.brain_langchain import BrainChatModel
from backend.agent.brain_langchain.brain import brain, ToolSpec


def test_database_initialization():
    print("--- 1. Testing Database Initialization & Seeding ---")
    seed_default_data()
    with get_connection(DEFAULT_DB_FILE) as conn:
        providers = conn.execute("SELECT name, base_url, status FROM providers").fetchall()
        models = conn.execute("SELECT name, model_size, status FROM models").fetchall()
        keys = conn.execute("SELECT unique_name, env_key, status FROM api_keys").fetchall()
        
        print(f"Providers count: {len(providers)}")
        for p in providers:
            print(f"  Provider: {p['name']} | Status: {p['status']} | URL: {p['base_url']}")
            
        print(f"\nModels count: {len(models)}")
        for m in models:
            print(f"  Model: {m['name']} | Size: {m['model_size']} | Status: {m['status']}")
            
        print(f"\nAPI Keys count: {len(keys)}")
        for k in keys:
            print(f"  Key: {k['unique_name']} | Env: {k['env_key']} | Status: {k['status']}")

    assert len(providers) > 0, "No providers found in DB!"
    assert len(models) > 0, "No models found in DB!"
    print("✅ Database initialization test passed!\n")


def test_api_caller_direct():
    print("--- 2. Testing Direct api_caller Invocation ---")
    data = {"prompt": "Reply with 'Hello from Assistant DB!' if you receive this message."}
    result = api_caller(data)

    print(f"Success           : {result.get('success')}")
    print(f"Response          : {result.get('response')}")
    print(f"Chosen Provider   : {result.get('chosen', {}).get('provider')}")
    print(f"Chosen Model      : {result.get('chosen', {}).get('model')}")
    print(f"Chosen Key        : {result.get('chosen', {}).get('key_name')}")
    print(f"Total Attempts    : {result.get('total_attempts')}")
    print(f"Total Duration    : {result.get('total_duration_ms')} ms")

    if result.get("error"):
        print(f"Error             : {result.get('error')}")

    assert result.get("success") is True, f"api_caller failed: {result.get('error')}"
    print("✅ Direct api_caller test passed!\n")


def test_brain_function():
    print("--- 3. Testing brain() Orchestration ---")
    res = brain(
        user_prompt="What is the capital of France?",
        system_prompt="You are a helpful assistant. Be brief.",
    )
    print(f"API Success  : {res.get('api_success')}")
    print(f"Response     : {res.get('api_response')}")
    print(f"Chosen       : {res.get('chosen')}")

    assert res.get("api_success") is True, f"brain() failed: {res.get('error_message')}"
    print("✅ brain() function test passed!\n")


def test_langchain_wrapper():
    print("--- 4. Testing BrainChatModel (LangChain wrapper) ---")
    llm = BrainChatModel(temperature=0)
    msg = llm.invoke("What is 10 + 5?")

    print(f"LLM Response : {msg.content}")
    print(f"Provider     : {msg.additional_kwargs.get('provider')}")
    print(f"Model        : {msg.additional_kwargs.get('model')}")
    print(f"Key          : {msg.additional_kwargs.get('key_name')}")

    assert msg.content and "15" in msg.content, "Unexpected response from BrainChatModel"
    print("✅ BrainChatModel test passed!\n")


def test_sqlite_logging_system():
    print("--- 5. Testing SQLite3 Logging System (Flat API Call Table) ---")
    with get_connection(DEFAULT_DB_FILE) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        expected_tables = ["Conversation", "API_Call_Log"]
        for tbl in expected_tables:
            assert tbl in tables, f"Expected logging table '{tbl}' was not found in DB!"
        obsolete_tables = ["Interactive", "Iteration", "Find_Best_API", "Decide", "Wait"]
        for tbl in obsolete_tables:
            assert tbl not in tables, f"Obsolete logging table '{tbl}' was not removed!"
        assert "reponses" not in tables, "Obsolete 'reponses' table was not removed!"

        last_conv = conn.execute("SELECT * FROM Conversation ORDER BY ID DESC LIMIT 1").fetchone()
        assert last_conv is not None, "No Conversation record found!"
        print(f"  Conversation ID: {last_conv['ID']} | Title: {last_conv['Title']}")

        last_call = conn.execute(
            "SELECT * FROM API_Call_Log WHERE Conversation_Id = ? ORDER BY API_Call_Id DESC LIMIT 1",
            (last_conv["ID"],)
        ).fetchone()
        assert last_call is not None, "No API call was recorded for Conversation!"
        assert last_call["Request_Status"] in ("Failed", "Success")
        print(
            f"  API Call ID: {last_call['API_Call_Id']} | Interaction: "
            f"{last_call['Interaction_Id']} | Iteration: {last_call['Iteration_Id']} | "
            f"Status: {last_call['Request_Status']}"
        )

        # Ensure no api_caller.log file was created in api_manager directory
        log_file_path = os.path.join(os.path.dirname(DEFAULT_DB_FILE), "api_caller.log")
        assert not os.path.exists(log_file_path), f"api_caller.log should not exist at {log_file_path}!"

    print("✅ SQLite3 logging system test passed!\n")


if __name__ == "__main__":
    print("==================================================")
    print("🚀 RUNNING ASSISTANT DB & API TEST SUITE")
    print("==================================================\n")
    test_database_initialization()
    test_api_caller_direct()
    test_brain_function()
    test_langchain_wrapper()
    test_sqlite_logging_system()
    print("==================================================")
    print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")
