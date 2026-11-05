import json
from types import SimpleNamespace

from backend.tools import features


def test_refresh_preserves_disabled_state_and_enables_new_tools(tmp_path, monkeypatch):
    registry_file = tmp_path / "tools_registry.json"
    registry_file.write_text(
        json.dumps({"tools": {"existing_tool": {"enabled": False}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(features, "REGISTRY_FILE", registry_file)
    monkeypatch.setattr(
        features,
        "_discover_tools",
        lambda: {"existing_tool": {}, "new_tool": {}},
    )

    tools = features.refresh_tools_registry()

    assert tools["existing_tool"]["enabled"] is False
    assert tools["new_tool"]["enabled"] is True
    assert json.loads(registry_file.read_text(encoding="utf-8"))["tools"] == tools


def test_update_tool_enabled_persists_setting(tmp_path, monkeypatch):
    registry_file = tmp_path / "tools_registry.json"
    registry_file.write_text(
        json.dumps({"type": "tools", "tools": {"sample": {"enabled": True}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(features, "REGISTRY_FILE", registry_file)
    monkeypatch.setattr(features, "_registry_cache", None)
    monkeypatch.setattr(features, "_registry_mtime", None)

    updated = features.update_tool_enabled("sample", False)

    assert updated["enabled"] is False
    persisted = json.loads(registry_file.read_text(encoding="utf-8"))
    assert persisted["tools"]["sample"]["enabled"] is False


def test_get_langchain_tools_omits_disabled_tools(monkeypatch):
    def enabled_tool(query: str) -> str:
        return query

    def disabled_tool(query: str) -> str:
        return query

    modules = {
        "enabled-module": SimpleNamespace(enabled_tool=enabled_tool),
        "disabled-module": SimpleNamespace(disabled_tool=disabled_tool),
    }
    registry = {
        "tools": {
            "enabled_tool": {
                "status": "valid",
                "enabled": True,
                "path": "enabled.py",
                "module": "enabled-module",
                "function": "enabled_tool",
            },
            "disabled_tool": {
                "status": "valid",
                "enabled": False,
                "path": "disabled.py",
                "module": "disabled-module",
                "function": "disabled_tool",
            },
        }
    }
    monkeypatch.setattr(features, "load_registry", lambda force=False: registry)
    monkeypatch.setattr(
        features,
        "_load_module",
        lambda _path, module_name: modules[module_name],
    )

    tools = features.get_langchain_tools()

    assert [tool.name for tool in tools] == ["enabled_tool"]
