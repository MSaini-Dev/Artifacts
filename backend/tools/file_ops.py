"""
Powerful file operations: read, write, replace, list.
All paths are relative to current working directory unless absolute.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

TOOL_NAME = "file_ops"  # Not used directly; individual functions are registered


def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
    """
    Read a file. Optionally return only a line range (1-indexed).
    Returns content + metadata.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        if not path.is_file():
            return {"success": False, "error": f"Not a file: {file_path}"}

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total = len(lines)

        if start_line is not None or end_line is not None:
            start = max(0, (start_line - 1) if start_line else 0)
            end = min(total, end_line if end_line else total)
            content = "".join(lines[start:end])
            return {
                "success": True,
                "content": content,
                "total_lines": total,
                "returned_range": f"{start+1}-{end}",
                "file_path": str(path)
            }

        return {
            "success": True,
            "content": "".join(lines),
            "total_lines": total,
            "file_path": str(path)
        }
    except Exception as e:
        return {"success": False, "error": str(e), "file_path": file_path}


def write_file(file_path: str, content: str) -> dict:
    """
    Write content to a file. Creates parent directories if needed.
    Overwrites existing file.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "message": f"Successfully wrote {len(content)} chars to {file_path}",
            "file_path": str(path),
            "bytes_written": len(content.encode("utf-8"))
        }
    except Exception as e:
        return {"success": False, "error": str(e), "file_path": file_path}


def replace_in_file(file_path: str, old_text: str, new_text: str, replace_all: bool = True) -> dict:
    """
    Replace text in a file. Returns how many replacements were made.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_text not in content:
            return {
                "success": False,
                "error": "old_text not found in file",
                "file_path": file_path
            }

        count = content.count(old_text) if replace_all else 1
        new_content = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "success": True,
            "message": f"Replaced {count} occurrence(s) in {file_path}",
            "replacements": count,
            "file_path": file_path
        }
    except Exception as e:
        return {"success": False, "error": str(e), "file_path": file_path}


def list_dir(dir_path: str = ".", max_depth: int = 2) -> dict:
    """
    List directory structure up to max_depth. Ignores common junk folders.
    """
    ignored = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv", ".idea", ".vscode"}
    result = []

    def _walk(current: Path, depth: int, prefix: str = ""):
        if depth > max_depth:
            return
        try:
            items = sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for item in items:
                if item.name in ignored or item.name.startswith("."):
                    continue
                rel = str(item.relative_to(Path(dir_path).resolve() if dir_path != "." else Path.cwd()))
                if item.is_dir():
                    result.append({"name": item.name, "path": rel, "type": "directory"})
                    _walk(item, depth + 1, rel)
                else:
                    result.append({"name": item.name, "path": rel, "type": "file"})
        except Exception:
            pass

    try:
        root = Path(dir_path).resolve()
        if not root.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}
        _walk(root, 1)
        return {"success": True, "items": result, "root": str(root)}
    except Exception as e:
        return {"success": False, "error": str(e)}
