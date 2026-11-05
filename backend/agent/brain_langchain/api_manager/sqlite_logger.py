"""SQLite-backed conversation and per-API-call logging."""

import json
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_DB_FILE = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "API_Store.db")
)

active_conversation_id: ContextVar[Optional[int]] = ContextVar("active_conversation_id", default=None)
active_interactive_id: ContextVar[Optional[int]] = ContextVar("active_interactive_id", default=None)
active_iteration_id: ContextVar[Optional[int]] = ContextVar("active_iteration_id", default=None)
active_api_call_id: ContextVar[Optional[int]] = ContextVar("active_api_call_id", default=None)


def resolve_db_path(db_path: Optional[str] = None) -> str:
    path = db_path or os.environ.get("DB_PATH") or DEFAULT_DB_FILE
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), path))


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_db_path(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _serialize(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone() is not None


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {declaration}")


def _duration_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        parts = str(value).split(":")
        if len(parts) == 3:
            return max(0.0, int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
    except (TypeError, ValueError):
        return None
    return None


def _looks_like_tool_call(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return False
    if isinstance(parsed, dict):
        return isinstance(parsed.get("tool_calls"), list) or (
            isinstance(parsed.get("function"), dict) and bool(parsed.get("function"))
        )
    if isinstance(parsed, list):
        return any(
            isinstance(item, dict)
            and (
                isinstance(item.get("function"), dict)
                or "arguments" in item
                or "tool_call_id" in item
            )
            for item in parsed
        )
    return False


def _legacy_values(values: List[Any]) -> Optional[str]:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return _serialize(values)


def _extract_legacy_prompt(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload) if isinstance(payload, str) else payload
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, dict):
        for key in ("user_prompt", "prompt"):
            if parsed.get(key):
                return str(parsed[key])
        messages = parsed.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("role") == "user":
                    return str(message.get("content") or "")
    return None


def _migrate_legacy_logs(conn: sqlite3.Connection) -> None:
    legacy_tables = ("Interactive", "Iteration", "Find_Best_API", "Decide", "Wait")
    if not any(_table_exists(conn, table) for table in legacy_tables):
        return

    required = ("Interactive", "Iteration")
    if not all(_table_exists(conn, table) for table in required):
        raise RuntimeError("Cannot migrate legacy logs: Interactive or Iteration table is missing.")

    conversations = conn.execute("SELECT ID FROM Conversation").fetchall()
    existing_counts = {
        row["ID"]: row["Next_Interaction_Id"]
        for row in conn.execute("SELECT ID, Next_Interaction_Id FROM Conversation")
    }

    has_providers = _table_exists(conn, "providers")
    for interactive in conn.execute(
        "SELECT * FROM Interactive ORDER BY Conversation_Id, ID"
    ).fetchall():
        old_iterations = conn.execute(
            "SELECT * FROM Iteration WHERE Interactive_Id = ? ORDER BY ID",
            (interactive["ID"],),
        ).fetchall()
        logical_iteration_id = 1
        for old_iteration in old_iterations:
            fields = set(old_iteration.keys())
            request_payload = (
                old_iteration["Request_Payload"]
                if "Request_Payload" in fields
                else None
            )
            response = old_iteration["Actual_Response"] if "Actual_Response" in fields else None
            status = old_iteration["Status"] if "Status" in fields else "Failed"
            request_status = "Success" if status == "Success" else "Failed"

            find_rows = []
            if _table_exists(conn, "Find_Best_API"):
                find_rows = conn.execute(
                    "SELECT * FROM Find_Best_API WHERE Iteration_Id = ? ORDER BY ID",
                    (old_iteration["ID"],),
                ).fetchall()
            provider = find_rows[0]["Provider"] if find_rows else None
            model = find_rows[0]["Model"] if find_rows else None
            api_name = find_rows[0]["API"] if find_rows else None

            url = None
            if has_providers and provider:
                provider_row = conn.execute(
                    "SELECT base_url FROM providers WHERE LOWER(name) = LOWER(?) LIMIT 1",
                    (provider,),
                ).fetchone()
                if provider_row:
                    url = provider_row["base_url"]

            decide_rows = []
            if _table_exists(conn, "Decide"):
                decide_rows = conn.execute(
                    "SELECT * FROM Decide WHERE Iteration_Id = ? ORDER BY ID",
                    (old_iteration["ID"],),
                ).fetchall()
            modes = [row["Mode"] for row in decide_rows if row["Mode"]]
            requests = [row["Request"] for row in decide_rows if row["Request"]]
            actions = [row["Action"] for row in decide_rows if row["Action"]]

            wait_seconds = None
            if _table_exists(conn, "Wait"):
                waits = conn.execute(
                    "SELECT Time_To_Be_Waited FROM Wait WHERE Iteration_Id = ? ORDER BY ID",
                    (old_iteration["ID"],),
                ).fetchall()
                durations = [
                    parsed
                    for parsed in (_duration_seconds(row["Time_To_Be_Waited"]) for row in waits)
                    if parsed is not None
                ]
                if durations:
                    wait_seconds = sum(durations)

            final_response = None
            if request_status == "Success":
                final_response = int(
                    response is not None
                    and response == interactive["Actual_Response"]
                    and not _looks_like_tool_call(response)
                )

            created_at = interactive["Created_At"] or datetime.now().isoformat()
            duration = _duration_seconds(old_iteration["Time_Take_to_Process"])
            conn.execute(
                """
                INSERT INTO API_Call_Log (
                    Conversation_Id, Interaction_Id, Iteration_Id, URL, Model,
                    API_Name, Payload, Response, Request_Status, Final_Response,
                    Timestamp, Duration, Recovery_Mode, Recovery_Request,
                    Recovery_Action, Wait_Duration_Seconds, Interaction_Prompt,
                    Legacy_Record
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    interactive["Conversation_Id"],
                    interactive["ID"],
                    logical_iteration_id,
                    url,
                    model,
                    api_name,
                    request_payload,
                    response,
                    request_status,
                    final_response,
                    created_at,
                    duration,
                    _legacy_values(modes),
                    _legacy_values(requests),
                    _legacy_values(actions),
                    wait_seconds,
                    _extract_legacy_prompt(interactive["Payload"]),
                ),
            )
            if request_status == "Success":
                logical_iteration_id += 1

    for conversation in conversations:
        legacy_next = existing_counts.get(conversation["ID"], 1)
        if _table_exists(conn, "Interactive"):
            last_interaction = conn.execute(
                "SELECT COALESCE(MAX(ID), 0) + 1 FROM Interactive WHERE Conversation_Id = ?",
                (conversation["ID"],),
            ).fetchone()[0]
            legacy_next = max(legacy_next, last_interaction)
        conn.execute(
            "UPDATE Conversation SET Next_Interaction_Id = ? WHERE ID = ?",
            (legacy_next, conversation["ID"]),
        )

    for table in ("Wait", "Decide", "Find_Best_API", "Iteration", "Interactive"):
        if _table_exists(conn, table):
            conn.execute(f'DROP TABLE "{table}"')


def init_logging_schema(conn_or_path: Any = None) -> None:
    """Create the flat API-call log and migrate legacy detail tables atomically."""
    should_close = conn_or_path is None or isinstance(conn_or_path, str)
    conn = get_db_connection(conn_or_path) if should_close else conn_or_path
    nested_transaction = conn.in_transaction
    if nested_transaction:
        conn.execute("SAVEPOINT logging_schema_migration")
    else:
        conn.execute("BEGIN IMMEDIATE")

    try:
        conn.execute("DROP TABLE IF EXISTS reponses")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Conversation (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Title VARCHAR(255),
                Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                Updated_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                Next_Interaction_Id INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        _ensure_column(
            conn,
            "Conversation",
            "Next_Interaction_Id",
            "Next_Interaction_Id INTEGER NOT NULL DEFAULT 1",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS API_Call_Log (
                API_Call_Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Conversation_Id INTEGER NOT NULL REFERENCES Conversation(ID) ON DELETE CASCADE,
                Interaction_Id INTEGER NOT NULL,
                Iteration_Id INTEGER NOT NULL,
                URL TEXT,
                Model TEXT,
                API_Name TEXT,
                Payload TEXT,
                Response TEXT,
                Request_Status TEXT NOT NULL
                    CHECK (Request_Status IN ('Failed', 'Success')),
                Final_Response INTEGER
                    CHECK (Final_Response IN (0, 1) OR Final_Response IS NULL),
                Timestamp TEXT NOT NULL,
                Duration REAL,
                Is_Complete INTEGER NOT NULL DEFAULT 1,
                Task_Started_At TEXT,
                Task_Duration_Seconds REAL,
                Task_Is_Complete INTEGER NOT NULL DEFAULT 1,
                Recovery_Mode TEXT,
                Recovery_Request TEXT,
                Recovery_Action TEXT,
                Wait_Duration_Seconds REAL,
                Interaction_Prompt TEXT,
                Legacy_Record INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Interaction_Prompt",
            "Interaction_Prompt TEXT",
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Legacy_Record",
            "Legacy_Record INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Is_Complete",
            "Is_Complete INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Task_Started_At",
            "Task_Started_At TEXT",
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Task_Duration_Seconds",
            "Task_Duration_Seconds REAL",
        )
        _ensure_column(
            conn,
            "API_Call_Log",
            "Task_Is_Complete",
            "Task_Is_Complete INTEGER NOT NULL DEFAULT 1",
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Tool_Execution (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Conversation_Id INTEGER NOT NULL REFERENCES Conversation(ID) ON DELETE CASCADE,
                Interaction_Id INTEGER NOT NULL,
                Task_Id INTEGER,
                Tool_Call_Id TEXT,
                Name TEXT NOT NULL,
                Parameters TEXT,
                Response TEXT,
                Error TEXT,
                Status TEXT NOT NULL CHECK (Status IN ('Running', 'Success', 'Failed')),
                Timestamp TEXT NOT NULL,
                Duration REAL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tool_execution_interaction_task
            ON Tool_Execution(Conversation_Id, Interaction_Id, Task_Id, ID)
            """
        )
        _migrate_legacy_logs(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_call_conversation_interaction
            ON API_Call_Log(Conversation_Id, Interaction_Id, Iteration_Id, API_Call_Id)
            """
        )

        if nested_transaction:
            conn.execute("RELEASE SAVEPOINT logging_schema_migration")
        else:
            conn.commit()
    except Exception:
        if nested_transaction:
            conn.execute("ROLLBACK TO SAVEPOINT logging_schema_migration")
            conn.execute("RELEASE SAVEPOINT logging_schema_migration")
        else:
            conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()


def create_conversation(
    title: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    clean_title = (title or "Untitled Conversation").strip()
    if len(clean_title) > 255:
        clean_title = clean_title[:252] + "..."
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("INSERT INTO Conversation (Title) VALUES (?)", (clean_title,))
        conn.commit()
        return int(cursor.lastrowid)


def update_conversation(
    conversation_id: int,
    title: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with get_db_connection(db_path) as conn:
        if title:
            clean_title = title.strip()
            if len(clean_title) > 255:
                clean_title = clean_title[:252] + "..."
            conn.execute(
                "UPDATE Conversation SET Title = ?, Updated_At = ? WHERE ID = ?",
                (clean_title, now, conversation_id),
            )
        else:
            conn.execute(
                "UPDATE Conversation SET Updated_At = ? WHERE ID = ?",
                (now, conversation_id),
            )
        conn.commit()


def create_interactive(
    conversation_id: int,
    payload: Optional[Any] = None,
    response_status: str = "Not_Final",
    actual_response: Optional[str] = None,
    iteration_no: int = 0,
    db_path: Optional[str] = None,
) -> int:
    """Reserve an interaction ID; request and response data live on API-call rows."""
    del payload, response_status, actual_response, iteration_no
    with get_db_connection(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT Next_Interaction_Id FROM Conversation WHERE ID = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Conversation {conversation_id} does not exist.")
        interaction_id = int(row["Next_Interaction_Id"])
        conn.execute(
            """
            UPDATE Conversation
            SET Next_Interaction_Id = ?, Updated_At = ?
            WHERE ID = ?
            """,
            (interaction_id + 1, datetime.now().isoformat(timespec="seconds"), conversation_id),
        )
        conn.commit()
        return interaction_id


def next_iteration_id(
    conversation_id: int,
    interaction_id: int,
    db_path: Optional[str] = None,
) -> int:
    with get_db_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(Iteration_Id), 0) + 1
            FROM API_Call_Log
            WHERE Conversation_Id = ? AND Interaction_Id = ?
            """,
            (conversation_id, interaction_id),
        ).fetchone()
        return int(row[0])


def create_api_call(
    conversation_id: int,
    interaction_id: int,
    iteration_id: int,
    url: Optional[str] = None,
    model: Optional[str] = None,
    api_name: Optional[str] = None,
    payload: Optional[Any] = None,
    interaction_prompt: Optional[str] = None,
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO API_Call_Log (
                Conversation_Id, Interaction_Id, Iteration_Id, URL, Model,
                API_Name, Payload, Request_Status, Timestamp, Interaction_Prompt,
                Is_Complete, Task_Is_Complete
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Failed', ?, ?, 0, 0)
            """,
            (
                conversation_id,
                interaction_id,
                iteration_id,
                url,
                model,
                api_name,
                _serialize(payload),
                timestamp or datetime.now().isoformat(timespec="milliseconds"),
                interaction_prompt,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_api_call(
    api_call_id: int,
    request_status: Optional[str] = None,
    final_response: Optional[bool] = None,
    payload: Optional[Any] = None,
    response: Optional[Any] = None,
    duration_seconds: Optional[float] = None,
    recovery_mode: Optional[str] = None,
    recovery_request: Optional[Any] = None,
    recovery_action: Optional[Any] = None,
    wait_duration_seconds: Optional[float] = None,
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    values: Dict[str, Any] = {}
    if request_status is not None:
        if request_status not in ("Failed", "Success"):
            raise ValueError("request_status must be 'Failed' or 'Success'.")
        values["Request_Status"] = request_status
    if final_response is not None:
        values["Final_Response"] = int(final_response)
    if payload is not None:
        values["Payload"] = _serialize(payload)
    if response is not None:
        values["Response"] = _serialize(response)
    if duration_seconds is not None:
        values["Duration"] = max(0.0, float(duration_seconds))
    if request_status is not None or response is not None or duration_seconds is not None:
        values["Is_Complete"] = 1
    if recovery_mode is not None:
        values["Recovery_Mode"] = recovery_mode
    if recovery_request is not None:
        values["Recovery_Request"] = _serialize(recovery_request)
    if recovery_action is not None:
        values["Recovery_Action"] = _serialize(recovery_action)
    if wait_duration_seconds is not None:
        values["Wait_Duration_Seconds"] = max(0.0, float(wait_duration_seconds))
    if timestamp is not None:
        values["Timestamp"] = timestamp
    if not values:
        return

    assignments = ", ".join(f'"{column}" = ?' for column in values)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            f"UPDATE API_Call_Log SET {assignments} WHERE API_Call_Id = ?",
            (*values.values(), api_call_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"API call {api_call_id} does not exist.")
        conn.commit()


def complete_api_task(
    conversation_id: int,
    interaction_id: int,
    task_id: int,
    started_at: str,
    duration_seconds: float,
    db_path: Optional[str] = None,
) -> None:
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE API_Call_Log
            SET Task_Started_At = ?, Task_Duration_Seconds = ?, Task_Is_Complete = 1
            WHERE Conversation_Id = ? AND Interaction_Id = ? AND Iteration_Id = ?
            """,
            (
                started_at,
                max(0.0, float(duration_seconds)),
                conversation_id,
                interaction_id,
                task_id,
            ),
        )
        conn.commit()


def create_tool_execution(
    conversation_id: int,
    interaction_id: int,
    task_id: Optional[int],
    name: str,
    parameters: Any,
    tool_call_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO Tool_Execution (
                Conversation_Id, Interaction_Id, Task_Id, Tool_Call_Id,
                Name, Parameters, Status, Timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, 'Running', ?)
            """,
            (
                conversation_id,
                interaction_id,
                task_id,
                tool_call_id,
                name,
                _serialize(parameters),
                timestamp or datetime.now().isoformat(timespec="milliseconds"),
            ),
        )
        execution_id = int(cursor.lastrowid)
        tool = dict(
            conn.execute(
                "SELECT * FROM Tool_Execution WHERE ID = ?",
                (execution_id,),
            ).fetchone()
        )
        conn.commit()
    from .activity_stream import publish_activity

    publish_activity(
        conversation_id,
        {
            "type": "tool_update",
            "interaction_id": interaction_id,
            "tool": tool,
        },
    )
    return execution_id


def update_tool_execution(
    execution_id: int,
    status: str,
    response: Any = None,
    error: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    db_path: Optional[str] = None,
) -> None:
    if status not in ("Success", "Failed"):
        raise ValueError("Tool execution status must be 'Success' or 'Failed'.")
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE Tool_Execution
            SET Status = ?, Response = ?, Error = ?, Duration = ?
            WHERE ID = ?
            """,
            (
                status,
                _serialize(response),
                error,
                max(0.0, float(duration_seconds or 0.0)),
                execution_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Tool execution {execution_id} does not exist.")
        tool = dict(
            conn.execute(
                "SELECT * FROM Tool_Execution WHERE ID = ?",
                (execution_id,),
            ).fetchone()
        )
        conn.commit()
    from .activity_stream import publish_activity

    publish_activity(
        int(tool["Conversation_Id"]),
        {
            "type": "tool_update",
            "interaction_id": int(tool["Interaction_Id"]),
            "tool": tool,
        },
    )


def update_interactive(
    interactive_id: int,
    response_status: Optional[str] = None,
    actual_response: Optional[str] = None,
    iteration_no: Optional[int] = None,
    payload: Optional[Any] = None,
    duration_seconds: Optional[float] = None,
    db_path: Optional[str] = None,
) -> None:
    """Mark the latest successful API call as the interaction's final response."""
    del actual_response, iteration_no, payload, duration_seconds
    if response_status != "Final":
        return

    conversation_id = active_conversation_id.get()
    with get_db_connection(db_path) as conn:
        if conversation_id is None:
            matches = conn.execute(
                """
                SELECT DISTINCT Conversation_Id FROM API_Call_Log
                WHERE Interaction_Id = ? LIMIT 2
                """,
                (interactive_id,),
            ).fetchall()
            if len(matches) != 1:
                raise ValueError(
                    f"Cannot resolve conversation for interaction {interactive_id}."
                )
            conversation_id = int(matches[0]["Conversation_Id"])

        conn.execute(
            """
            UPDATE API_Call_Log SET Final_Response = 0
            WHERE Conversation_Id = ? AND Interaction_Id = ?
              AND Request_Status = 'Success'
            """,
            (conversation_id, interactive_id),
        )
        last_success = conn.execute(
            """
            SELECT API_Call_Id, Response FROM API_Call_Log
            WHERE Conversation_Id = ? AND Interaction_Id = ?
              AND Request_Status = 'Success'
            ORDER BY API_Call_Id DESC LIMIT 1
            """,
            (conversation_id, interactive_id),
        ).fetchone()
        if last_success:
            is_final = not _looks_like_tool_call(last_success["Response"])
            conn.execute(
                "UPDATE API_Call_Log SET Final_Response = ? WHERE API_Call_Id = ?",
                (int(is_final), last_success["API_Call_Id"]),
            )
        conn.execute(
            "UPDATE Conversation SET Updated_At = ? WHERE ID = ?",
            (datetime.now().isoformat(timespec="seconds"), conversation_id),
        )
        conn.commit()


def log_decide(
    iteration_id: int,
    mode: str,
    request: Optional[Any],
    action: Optional[Any],
    time_take_to_process: Optional[float],
    db_path: Optional[str] = None,
) -> int:
    del iteration_id, time_take_to_process
    api_call_id = active_api_call_id.get()
    if api_call_id is None:
        raise RuntimeError("Cannot record a recovery decision without an active API call.")
    update_api_call(
        api_call_id,
        recovery_mode="LAYA" if str(mode).strip().lower() == "laya" else "Parser",
        recovery_request=request,
        recovery_action=action,
        db_path=db_path,
    )
    return api_call_id


def log_wait(
    iteration_id: int,
    time_to_be_waited: Optional[float],
    db_path: Optional[str] = None,
) -> int:
    del iteration_id
    api_call_id = active_api_call_id.get()
    if api_call_id is None:
        raise RuntimeError("Cannot record a wait without an active API call.")
    update_api_call(
        api_call_id,
        wait_duration_seconds=time_to_be_waited,
        db_path=db_path,
    )
    return api_call_id


@contextmanager
def conversation_scope(
    title: Optional[str] = None,
    conversation_id: Optional[int] = None,
    db_path: Optional[str] = None,
):
    init_logging_schema(db_path)
    cid = conversation_id or active_conversation_id.get()
    if cid is None:
        cid = create_conversation(title=title, db_path=db_path)
    token = active_conversation_id.set(cid)
    try:
        yield cid
    finally:
        active_conversation_id.reset(token)


@contextmanager
def interactive_scope(
    conversation_id: Optional[int] = None,
    payload: Optional[Any] = None,
    interactive_id: Optional[int] = None,
    db_path: Optional[str] = None,
):
    init_logging_schema(db_path)
    cid = conversation_id or active_conversation_id.get()
    if cid is None:
        cid = create_conversation(title="Interactive Session", db_path=db_path)
    iid = interactive_id or active_interactive_id.get()
    if iid is None:
        iid = create_interactive(conversation_id=cid, payload=payload, db_path=db_path)

    token_conv = active_conversation_id.set(cid)
    token_inter = active_interactive_id.set(iid)
    try:
        yield iid
    finally:
        active_interactive_id.reset(token_inter)
        active_conversation_id.reset(token_conv)
