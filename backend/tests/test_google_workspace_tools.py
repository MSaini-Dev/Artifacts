import base64
from unittest.mock import Mock

from backend.tools import features
from backend.tools import google_workspace


def test_search_drive_files_passes_search_and_pagination(monkeypatch):
    drive = Mock()
    request = drive.files.return_value.list.return_value
    request.execute.return_value = {"files": [{"id": "file-1"}]}
    monkeypatch.setattr(google_workspace, "_drive", lambda: drive)

    result = google_workspace.search_drive_files(
        query="name contains 'report'",
        page_size=5,
        page_token="next",
    )

    assert result == {"files": [{"id": "file-1"}]}
    drive.files.return_value.list.assert_called_once()
    params = drive.files.return_value.list.call_args.kwargs
    assert params["q"] == "name contains 'report'"
    assert params["pageSize"] == 5
    assert params["pageToken"] == "next"


def test_add_task_includes_optional_fields(monkeypatch):
    tasks = Mock()
    tasks.tasks.return_value.insert.return_value.execute.return_value = {"id": "task-1"}
    monkeypatch.setattr(google_workspace, "_tasks", lambda: tasks)

    result = google_workspace.add_task(
        tasklist_id="list-1",
        title="Prepare report",
        notes="Include latest figures",
        due="2026-11-30T00:00:00.000Z",
        parent_task_id="parent-1",
        previous_task_id="previous-1",
    )

    assert result == {"id": "task-1"}
    tasks.tasks.return_value.insert.assert_called_once_with(
        tasklist="list-1",
        body={
            "title": "Prepare report",
            "notes": "Include latest figures",
            "due": "2026-11-30T00:00:00.000Z",
        },
        parent="parent-1",
        previous="previous-1",
    )


def test_send_email_uses_gmail_send_api(monkeypatch):
    gmail = Mock()
    gmail.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "message-1"
    }
    monkeypatch.setattr(google_workspace, "_gmail", lambda: gmail)
    monkeypatch.setattr(google_workspace, "_email_message", lambda *args: "encoded-message")

    result = google_workspace.send_email(
        to="person@example.com",
        subject="Hello",
        body="Message body",
    )

    assert result == {"id": "message-1"}
    gmail.users.return_value.messages.return_value.send.assert_called_once_with(
        userId="me",
        body={"raw": "encoded-message"},
    )


def test_read_email_adds_decoded_plain_text(monkeypatch):
    gmail = Mock()
    gmail.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "message-1",
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(b"Hello there").decode("ascii").rstrip("=")},
                }
            ],
        },
    }
    monkeypatch.setattr(google_workspace, "_gmail", lambda: gmail)

    result = google_workspace.read_email(message_id="message-1")

    assert result["body_text"] == "Hello there"


def test_create_tasklist_calls_tasks_api(monkeypatch):
    tasks = Mock()
    tasks.tasklists.return_value.insert.return_value.execute.return_value = {"id": "list-1"}
    monkeypatch.setattr(google_workspace, "_tasks", lambda: tasks)

    assert google_workspace.create_tasklist("Work") == {"id": "list-1"}
    tasks.tasklists.return_value.insert.assert_called_once_with(body={"title": "Work"})


def test_permanent_drive_delete_requires_explicit_confirmation(monkeypatch):
    drive = Mock()
    monkeypatch.setattr(google_workspace, "_drive", lambda: drive)

    try:
        google_workspace.delete_restore_drive_file(
            file_id="file-1",
            operation="permanent_delete",
        )
    except ValueError as error:
        assert "confirm_permanent=true" in str(error)
    else:
        raise AssertionError("Permanent deletion should require explicit confirmation")

    drive.files.return_value.delete.assert_not_called()


def test_registry_exposes_31_google_workspace_tools_and_removes_legacy_names():
    tools = features._discover_tools()
    workspace_path = str(google_workspace.__file__)
    google_tools = {
        name for name, info in tools.items()
        if info.get("path") == workspace_path
    }

    assert len(google_tools) == 31
    assert {"send_email", "read_email", "create_tasklist", "add_task"} <= google_tools
    assert not {
        "google_task_manager",
        "mark_tasks_completed",
        "get_editable_sheets",
        "get_editable_google_sheets",
        "list_editable_sheets",
        "upload_file_to_drive",
        "get_drive_service",
    } & tools.keys()
