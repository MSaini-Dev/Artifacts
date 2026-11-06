"""Example Google and local-coder tools for the orchestration package."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .config import OrchestrationConfig
from .registry import ToolRegistry, tool_spec


def register_example_tools(
    registry: ToolRegistry,
    working_directory: str,
    config: Optional[OrchestrationConfig] = None,
) -> None:
    """Register two Google tools and two restricted coder tools."""
    settings = config or OrchestrationConfig.from_env()
    root = Path(working_directory).resolve()

    def within_root(path_value: str) -> Path:
        path = Path(path_value)
        if not path.is_absolute():
            path = root / path
        resolved = path.resolve()
        if resolved != root and root not in resolved.parents:
            raise PermissionError(f"Path must be inside the workspace: {root}")
        return resolved

    def drive_download_latest(query: str, download_dir: str = ".") -> Dict[str, Any]:
        from backend.tools.google_workspace import download_export_drive_file, search_drive_files

        escaped_query = query.replace("\\", "\\\\").replace("'", "\\'")
        response = search_drive_files(
            query=f"name contains '{escaped_query}' and trashed = false",
            page_size=1,
        )
        files = response.get("files", [])
        if not files:
            raise FileNotFoundError(f"No Drive file matched {query!r}.")

        item = files[0]
        destination_dir = within_root(download_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(item["name"]).name or f"drive-{item['id']}"
        mime_type = item.get("mimeType", "")
        if mime_type.startswith("application/vnd.google-apps."):
            filename = f"{Path(filename).stem}.txt"
        destination = within_root(str(destination_dir / filename))
        download_export_drive_file(
            file_id=item["id"],
            destination_path=str(destination),
            export_mime_type="text/plain",
        )
        return {
            "file_id": item["id"],
            "name": item["name"],
            "path": str(destination),
            "modified_time": item.get("modifiedTime"),
        }

    def gmail_send(to: str, subject: str, body: str) -> Dict[str, Any]:
        from backend.tools.google_workspace import send_email

        result = send_email(to=to, subject=subject, body=body)
        return {"result": result, "to": to, "subject": subject}

    def read_file(file_path: str) -> Dict[str, Any]:
        path = within_root(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Not a file: {path}")
        from backend.tools.file_ops import read_file as read_existing_file

        result = read_existing_file(str(path))
        if result.get("success") is False:
            raise OSError(result.get("error", "File read failed."))
        return result

    def run_shell(command: str, cwd: str = ".", timeout: Optional[int] = None) -> Dict[str, Any]:
        workdir = within_root(cwd)
        if not workdir.is_dir():
            raise NotADirectoryError(str(workdir))
        limit = max(1, min(timeout or settings.shell_timeout, settings.shell_timeout))
        from backend.tools.execute_command import execute_command as execute_existing_command

        return execute_existing_command(command, timeout=limit, cwd=str(workdir))

    registry.register(
        tool_spec(
            "drive_download_latest",
            "Find the newest Google Drive file matching a name/query and download or export it inside the workspace.",
            {
                "query": {"type": "string"},
                "download_dir": {"type": "string", "default": "."},
            },
            ["query"],
        ),
        "google_cloud",
        drive_download_latest,
        service="drive",
    )
    registry.register(
        tool_spec(
            "gmail_send",
            "Send an email using the authenticated Gmail account.",
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            ["to", "subject", "body"],
        ),
        "google_cloud",
        gmail_send,
        service="gmail",
        requires_approval=True,
    )
    registry.register(
        tool_spec(
            "read_file",
            "Read a UTF-8 text file located inside the configured workspace.",
            {"file_path": {"type": "string"}},
            ["file_path"],
        ),
        "coder",
        read_file,
    )
    registry.register(
        tool_spec(
            "run_shell",
            "Run an approved shell command inside the configured workspace with a short timeout.",
            {
                "command": {"type": "string"},
                "cwd": {"type": "string", "default": "."},
                "timeout": {"type": "integer"},
            },
            ["command"],
        ),
        "coder",
        run_shell,
        requires_approval=True,
    )


def build_default_registry(
    working_directory: str,
    config: Optional[OrchestrationConfig] = None,
    vector_store_path: Optional[str] = None,
    embedder: Optional[Any] = None,
    vector_store: Optional[Any] = None,
) -> ToolRegistry:
    """Build the default registry with FAISS persistence and example handlers."""
    from .registry import FaissFlatVectorStore, HashingEmbedder

    settings = config or OrchestrationConfig.from_env()
    selected_embedder = embedder or HashingEmbedder()
    index_path = vector_store_path or os.getenv(
        "ORCHESTRATION_VECTOR_DB",
        str(Path(working_directory) / ".brain_tool_vectors.sqlite3"),
    )
    selected_store = vector_store or FaissFlatVectorStore(
        index_path,
        selected_embedder.dimension,
    )
    result = ToolRegistry(selected_embedder, selected_store)
    register_example_tools(result, working_directory, settings)
    return result
