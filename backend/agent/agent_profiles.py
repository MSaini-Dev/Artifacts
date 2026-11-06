"""Persistent agent profile storage shared by the API and chat runner."""

import json
import uuid
from typing import Any, Dict, List, Optional

from backend.agent.brain_langchain.api_manager.sqlite_logger import get_db_connection
from backend.tools.features import load_registry

DEFAULT_AGENT_SYSTEM_PROMPT = """You are a highly capable and efficient autonomous coding agent. Environment: Windows.

Core Principles:

1. Prefer dense, high-information actions. When using the shell on Windows, use Windows-compatible commands (e.g. powershell or cmd, avoid unix-only paths like /tmp or commands like head/wc). Chain commands with && or ; when safe. ALWAYS run shell commands non-interactively (e.g. use `npx -y create-vite@latest ...`, `npm install --yes`, etc.)—never run commands that prompt or wait for interactive user input.

2. After writing or modifying any file, VERIFY that the change actually happened (read it back or check with a command).

3. When you create something that should run (server, script, game), try to run it and observe the result.

4. If something fails, read the error carefully and fix it instead of repeating the same failing action.

5. Use the minimum number of tool calls needed. Prefer parallel tool calls when actions are independent.

6. You can create new tools with `create_tool` if you need new capability. After creating, the new tool becomes available.

7. Treat implementation, setup, testing, and other explicit action requests as work to execute, not requests for a plan. Do not stop after describing proposed next steps. Continue using tools until the requested work is done and verified, or until a concrete blocker requiring user action is reached.

8. Before claiming completion, compare the user's requested outcomes with tool results. A successful tool call alone does not prove the full task is complete. If anything remains, continue working or clearly report the exact blocker without claiming success.

Be decisive, verify your work, and finish the task cleanly."""

DEFAULT_GOOGLE_CLOUD_SYSTEM_PROMPT = """You are the Google services assistant. Use only your assigned Google service tools to fulfill requests involving the connected Google account and services.

Before making changes, identify the requested account, document, task list, or destination from the user's request. Do not claim an action succeeded unless the tool result confirms it. If required information is missing, ask a concise clarifying question. Never expose credentials or tokens."""
_LEGACY_GOOGLE_TOOLS = {
    "get_editable_google_sheets",
    "get_editable_sheets",
    "google_task_manager",
    "list_editable_sheets",
    "mark_tasks_completed",
    "upload_file_to_drive",
}


def _google_service_tool_names() -> List[str]:
    tools = load_registry(force=True).get("tools", {})
    service_terms = ("google", "gmail", "drive", "calendar", "gcs", "storage", "sheet")
    return sorted(
        name
        for name, info in tools.items()
        if isinstance(info, dict)
        and (
            info.get("module") == "backend.tools.google_workspace"
            or any(term in name.lower() for term in service_terms)
        )
        and name != "get_drive_service"
        and info.get("status") == "valid"
        and info.get("enabled", True) is not False
    )


def ensure_agent_profile_schema() -> None:
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Agent_Profile (
                ID TEXT PRIMARY KEY,
                Name TEXT NOT NULL,
                Description TEXT NOT NULL,
                System_Prompt TEXT NOT NULL,
                Tool_Names TEXT NOT NULL,
                Profile_Photo TEXT,
                Is_Built_In INTEGER NOT NULL DEFAULT 0,
                Created_At TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                Updated_At TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO Agent_Profile
                (ID, Name, Description, System_Prompt, Tool_Names, Is_Built_In)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                "assistant",
                "Assistant",
                "Default autonomous coding assistant with access to all enabled tools.",
                DEFAULT_AGENT_SYSTEM_PROMPT,
                json.dumps(["*"]),
            ),
        )
        if conn.execute(
            "SELECT 1 FROM Agent_Profile WHERE ID = ?",
            ("google_cloud",),
        ).fetchone() is None:
            conn.execute(
                """
                INSERT INTO Agent_Profile
                    (ID, Name, Description, System_Prompt, Tool_Names, Is_Built_In)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    "google_cloud",
                    "Google Cloud",
                    "Works with registered Google Drive, Gmail, Sheets, and Tasks tools.",
                    DEFAULT_GOOGLE_CLOUD_SYSTEM_PROMPT,
                    json.dumps(_google_service_tool_names()),
                ),
            )
        else:
            row = conn.execute(
                "SELECT Tool_Names, Is_Built_In FROM Agent_Profile WHERE ID = ?",
                ("google_cloud",),
            ).fetchone()
            if row and row["Is_Built_In"]:
                registry = load_registry(force=True).get("tools", {})
                existing_names = json.loads(row["Tool_Names"])
                if set(existing_names) & _LEGACY_GOOGLE_TOOLS:
                    enabled_names = {
                        name
                        for name, info in registry.items()
                        if isinstance(info, dict)
                        and info.get("status") == "valid"
                        and info.get("enabled", True) is not False
                    }
                    next_names = sorted(
                        (set(existing_names) & enabled_names)
                        | set(_google_service_tool_names())
                    )
                    if next_names != existing_names:
                        conn.execute(
                            "UPDATE Agent_Profile SET Tool_Names = ?, Updated_At = CURRENT_TIMESTAMP WHERE ID = ?",
                            (json.dumps(next_names), "google_cloud"),
                        )
        conn.commit()


def list_agent_profiles() -> List[Dict[str, Any]]:
    ensure_agent_profile_schema()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Agent_Profile ORDER BY Is_Built_In DESC, Name COLLATE NOCASE"
        ).fetchall()
    return [_serialize_profile(dict(row)) for row in rows]


def get_agent_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    ensure_agent_profile_schema()
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Agent_Profile WHERE ID = ?",
            (profile_id,),
        ).fetchone()
    return _serialize_profile(dict(row)) if row else None


def save_agent_profile(profile: Dict[str, Any], profile_id: Optional[str] = None) -> Dict[str, Any]:
    ensure_agent_profile_schema()
    agent_id = profile_id or uuid.uuid4().hex
    with get_db_connection() as conn:
        if profile_id:
            cursor = conn.execute(
                """
                UPDATE Agent_Profile
                SET Name = ?, Description = ?, System_Prompt = ?, Tool_Names = ?,
                    Profile_Photo = ?, Updated_At = CURRENT_TIMESTAMP
                WHERE ID = ?
                """,
                (
                    profile["name"],
                    profile["description"],
                    profile["system_prompt"],
                    json.dumps(profile["tool_names"]),
                    profile.get("profile_photo"),
                    agent_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(agent_id)
        else:
            conn.execute(
                """
                INSERT INTO Agent_Profile
                    (ID, Name, Description, System_Prompt, Tool_Names, Profile_Photo)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    profile["name"],
                    profile["description"],
                    profile["system_prompt"],
                    json.dumps(profile["tool_names"]),
                    profile.get("profile_photo"),
                ),
            )
        conn.commit()
    result = get_agent_profile(agent_id)
    if result is None:
        raise RuntimeError(f"Saved agent profile {agent_id!r} could not be loaded.")
    return result


def delete_agent_profile(profile_id: str) -> bool:
    ensure_agent_profile_schema()
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT Is_Built_In FROM Agent_Profile WHERE ID = ?",
            (profile_id,),
        ).fetchone()
        if row is None:
            return False
        if row["Is_Built_In"]:
            raise ValueError("Built-in agent profiles cannot be deleted.")
        conn.execute("DELETE FROM Agent_Profile WHERE ID = ?", (profile_id,))
        conn.commit()
    return True


def set_tool_agent_assignments(tool_name: str, agent_ids: List[str]) -> List[Dict[str, Any]]:
    """Assign one registered tool to the selected agent profiles."""
    ensure_agent_profile_schema()
    registry_tools = load_registry(force=True).get("tools", {})
    valid_tool_names = {
        name
        for name, info in registry_tools.items()
        if isinstance(info, dict)
        and info.get("status") == "valid"
    }
    if tool_name not in valid_tool_names:
        raise KeyError(tool_name)

    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT ID, Tool_Names FROM Agent_Profile ORDER BY Name COLLATE NOCASE"
        ).fetchall()
        known_ids = {row["ID"] for row in rows}
        unknown_ids = set(agent_ids) - known_ids
        if unknown_ids:
            raise KeyError(", ".join(sorted(unknown_ids)))

        selected_ids = set(agent_ids)
        for row in rows:
            try:
                tool_names = json.loads(row["Tool_Names"])
            except (TypeError, json.JSONDecodeError):
                tool_names = []
            if not isinstance(tool_names, list):
                tool_names = []

            if row["ID"] in selected_ids:
                if "*" not in tool_names and tool_name not in tool_names:
                    tool_names.append(tool_name)
            elif "*" in tool_names:
                tool_names = sorted(valid_tool_names - {tool_name})
            else:
                tool_names = [name for name in tool_names if name != tool_name]

            conn.execute(
                """
                UPDATE Agent_Profile
                SET Tool_Names = ?, Updated_At = CURRENT_TIMESTAMP
                WHERE ID = ?
                """,
                (json.dumps(tool_names), row["ID"]),
            )
        conn.commit()
    return list_agent_profiles()


def remove_tool_from_agent_profiles(tool_name: str) -> None:
    """Remove a deleted tool from explicit profile assignments."""
    ensure_agent_profile_schema()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT ID, Tool_Names FROM Agent_Profile").fetchall()
        for row in rows:
            try:
                tool_names = json.loads(row["Tool_Names"])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(tool_names, list) or "*" in tool_names or tool_name not in tool_names:
                continue
            conn.execute(
                """
                UPDATE Agent_Profile
                SET Tool_Names = ?, Updated_At = CURRENT_TIMESTAMP
                WHERE ID = ?
                """,
                (json.dumps([name for name in tool_names if name != tool_name]), row["ID"]),
            )
        conn.commit()


def _serialize_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        tool_names = json.loads(row["Tool_Names"])
    except (TypeError, json.JSONDecodeError):
        tool_names = []
    return {
        "id": row["ID"],
        "name": row["Name"],
        "description": row["Description"],
        "system_prompt": row["System_Prompt"],
        "tool_names": tool_names,
        "profile_photo": row["Profile_Photo"],
        "is_built_in": bool(row["Is_Built_In"]),
        "created_at": row["Created_At"],
        "updated_at": row["Updated_At"],
    }
