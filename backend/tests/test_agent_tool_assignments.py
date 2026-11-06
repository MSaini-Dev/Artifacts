import sqlite3

from backend.agent import agent_profiles


def test_tool_assignments_update_profiles_and_remove_deleted_tools(tmp_path, monkeypatch):
    database_path = tmp_path / "profiles.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(agent_profiles, "get_db_connection", connect)
    monkeypatch.setattr(
        agent_profiles,
        "load_registry",
        lambda force=False: {
            "tools": {
                "google_tool": {"status": "valid", "enabled": True},
                "local_tool": {"status": "valid", "enabled": True},
            }
        },
    )

    agent_profiles.ensure_agent_profile_schema()
    custom = agent_profiles.save_agent_profile(
        {
            "name": "Coder",
            "description": "",
            "system_prompt": "You write code.",
            "tool_names": ["local_tool"],
            "profile_photo": None,
        }
    )
    profiles = agent_profiles.set_tool_agent_assignments(
        "google_tool",
        [custom["id"], "google_cloud"],
    )
    by_id = {profile["id"]: profile for profile in profiles}

    assert by_id["assistant"]["tool_names"] == ["local_tool"]
    assert "google_tool" in by_id[custom["id"]]["tool_names"]
    assert "google_tool" in by_id["google_cloud"]["tool_names"]

    agent_profiles.remove_tool_from_agent_profiles("google_tool")
    profiles_after_delete = {profile["id"]: profile for profile in agent_profiles.list_agent_profiles()}
    assert "google_tool" not in profiles_after_delete[custom["id"]]["tool_names"]
    assert "google_tool" not in profiles_after_delete["google_cloud"]["tool_names"]
