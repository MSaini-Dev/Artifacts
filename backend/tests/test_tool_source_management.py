import json

import pytest

from backend.tools import features


def _set_registry(monkeypatch, tmp_path, tool_path):
    registry_path = tmp_path / "tools_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "type": "tools",
                "tools": {
                    "sample_tool": {
                        "path": str(tool_path),
                        "module": "backend.tools.sample_tool",
                        "function": "sample_tool",
                        "status": "valid",
                        "enabled": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(features, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(features, "REGISTRY_FILE", registry_path)
    monkeypatch.setattr(features, "_registry_cache", None)
    monkeypatch.setattr(features, "_registry_mtime", None)
    return registry_path


def test_create_tool_rejects_paths_and_invalid_python(tmp_path, monkeypatch):
    registry_path = tmp_path / "tools_registry.json"
    monkeypatch.setattr(features, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(features, "REGISTRY_FILE", registry_path)

    traversal = features.create_tool("../outside.py", "def run():\n    return 1\n", mode="x")
    invalid = features.create_tool("sample.py", "def run(:\n", mode="x")

    assert traversal["success"] is False
    assert invalid["success"] is False
    assert not (tmp_path.parent / "outside.py").exists()
    assert not (tmp_path / "sample.py").exists()


def test_source_update_validates_and_reindexes(tmp_path, monkeypatch):
    tool_path = tmp_path / "sample_tool.py"
    tool_path.write_text("def sample_tool():\n    return 'old'\n", encoding="utf-8")
    _set_registry(monkeypatch, tmp_path, tool_path)

    with pytest.raises(ValueError, match="Invalid Python syntax"):
        features.update_tool_source("sample_tool", "def sample_tool(:\n")
    assert "old" in tool_path.read_text(encoding="utf-8")

    result = features.update_tool_source("sample_tool", "def sample_tool():\n    return 'new'\n")

    assert result == {"success": True, "updated_tools": ["sample_tool"]}
    assert "new" in tool_path.read_text(encoding="utf-8")
    assert features.load_registry(force=True)["tools"]["sample_tool"]["status"] == "valid"


def test_delete_removes_source_and_registry_entry(tmp_path, monkeypatch):
    tool_path = tmp_path / "sample_tool.py"
    tool_path.write_text("def sample_tool():\n    return 'sample'\n", encoding="utf-8")
    _set_registry(monkeypatch, tmp_path, tool_path)

    result = features.delete_tool_file("sample_tool")

    assert result == {"success": True, "deleted_tools": ["sample_tool"]}
    assert not tool_path.exists()
    assert "sample_tool" not in features.load_registry(force=True)["tools"]


def test_delete_rejects_sources_outside_tools_folder(tmp_path, monkeypatch):
    outside_path = tmp_path.parent / "outside.py"
    outside_path.write_text("def sample_tool():\n    return 'sample'\n", encoding="utf-8")
    _set_registry(monkeypatch, tmp_path, outside_path)

    with pytest.raises(ValueError, match="outside the managed tools directory"):
        features.delete_tool_file("sample_tool")
    assert outside_path.exists()
