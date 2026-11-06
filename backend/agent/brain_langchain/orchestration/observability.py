"""Structured orchestration events stored beside existing Brain logs."""

import json
from datetime import datetime
from typing import Any, Dict

from ..api_manager.sqlite_logger import (
    active_conversation_id,
    active_interactive_id,
    get_db_connection,
)


def log_event(event_type: str, payload: Dict[str, Any]) -> None:
    """Persist an orchestration event in the Brain SQLite database."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Orchestration_Event (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Conversation_Id INTEGER,
                Interaction_Id INTEGER,
                Event_Type TEXT NOT NULL,
                Payload TEXT NOT NULL,
                Timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO Orchestration_Event (
                Conversation_Id, Interaction_Id, Event_Type, Payload, Timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                active_conversation_id.get(),
                active_interactive_id.get(),
                event_type,
                json.dumps(payload, ensure_ascii=False, default=str),
                datetime.now().isoformat(timespec="milliseconds"),
            ),
        )
        conn.commit()
