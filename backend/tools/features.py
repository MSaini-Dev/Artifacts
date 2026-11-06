"""
Tool discovery & registry system.
Scans the backend/tools directory, builds registry, supports dynamic create_tool,
and converts tools into LangChain StructuredTools.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import logging
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

TOOLS_DIR = Path(__file__).resolve().parent
REGISTRY_FILE = TOOLS_DIR / "tools_registry.json"
logger = logging.getLogger(__name__)

_registry_cache: Optional[dict] = None
_registry_mtime: Optional[float] = None


def refresh_tools_registry() -> dict[str, dict]:
    """Discover all valid tools and write registry JSON."""
    global _registry_cache, _registry_mtime

    tools = _discover_tools()
    existing_tools = {}
    if REGISTRY_FILE.exists():
        try:
            existing_tools = json.loads(REGISTRY_FILE.read_text(encoding="utf-8")).get("tools", {})
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read existing tool settings from %s.", REGISTRY_FILE, exc_info=True)
    if not isinstance(existing_tools, dict):
        existing_tools = {}

    for name, info in tools.items():
        previous = existing_tools.get(name)
        info["enabled"] = (
            previous.get("enabled", True) is not False
            if isinstance(previous, dict)
            else True
        )

    registry = {"type": "tools", "tools": tools}

    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    _registry_cache = registry
    _registry_mtime = REGISTRY_FILE.stat().st_mtime
    return tools


def create_tool(file_name: str, content: str, mode: str = "w") -> dict:
    """
    Create or overwrite a new tool file inside backend/tools/ and refresh registry.
    After creation the new tool becomes immediately available.
    """
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.py)?", file_name):
        return {"success": False, "error": "Use a simple Python module name without a path."}
    if not file_name.endswith(".py"):
        file_name += ".py"
    if file_name == "features.py":
        return {"success": False, "error": "The tool registry module cannot be overwritten."}
    try:
        ast.parse(content, filename=file_name)
    except SyntaxError as exc:
        return {"success": False, "error": f"Invalid Python syntax: {exc}"}

    path = TOOLS_DIR / file_name

    if mode not in ("w", "a", "x"):
        return {"success": False, "error": f"Invalid mode '{mode}'. Use w/a/x"}

    try:
        with open(path, mode, encoding="utf-8") as f:
            bytes_written = f.write(content)

        refresh_tools_registry()

        return {
            "success": True,
            "file_path": str(path),
            "bytes_written": bytes_written,
            "message": f"Tool '{file_name}' created and registry refreshed."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tool_source(tool_name: str) -> dict:
    """Return a tool's source file and all tools defined in that file."""
    registry = load_registry(force=True)
    tools = registry.get("tools", {})
    info = tools.get(tool_name)
    if not isinstance(info, dict):
        raise KeyError(tool_name)

    path = _managed_tool_path(info)
    return {
        "tool_name": tool_name,
        "file_name": path.name,
        "source": path.read_text(encoding="utf-8"),
        "editable": path.name != "features.py",
        "related_tools": sorted(
            name
            for name, item in tools.items()
            if isinstance(item, dict) and item.get("path") == str(path)
        ),
    }


def update_tool_source(tool_name: str, content: str) -> dict:
    """Validate and replace the Python source for a registered tool."""
    registry = load_registry(force=True)
    tools = registry.get("tools", {})
    info = tools.get(tool_name)
    if not isinstance(info, dict):
        raise KeyError(tool_name)

    path = _managed_tool_path(info)
    if path.name == "features.py":
        raise ValueError("The tool registry source cannot be edited here.")
    try:
        ast.parse(content, filename=path.name)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc}") from exc

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)

    refreshed = refresh_tools_registry()
    related_tools = sorted(
        name
        for name, item in refreshed.items()
        if isinstance(item, dict) and item.get("path") == str(path)
    )
    return {"success": True, "updated_tools": related_tools}


def delete_tool_file(tool_name: str) -> dict:
    """Delete the local Python file backing a registered tool."""
    registry = load_registry(force=True)
    tools = registry.get("tools", {})
    info = tools.get(tool_name)
    if not isinstance(info, dict):
        raise KeyError(tool_name)

    path = _managed_tool_path(info)
    if path.name == "features.py":
        raise ValueError("The tool registry source cannot be deleted.")
    related_tools = sorted(
        name
        for name, item in tools.items()
        if isinstance(item, dict) and item.get("path") == str(path)
    )
    path.unlink()
    refresh_tools_registry()
    return {"success": True, "deleted_tools": related_tools}


def _managed_tool_path(info: dict) -> Path:
    raw_path = info.get("path")
    if not isinstance(raw_path, str):
        raise ValueError("Tool does not have a managed Python source file.")
    path = Path(raw_path).resolve()
    if path.parent != TOOLS_DIR.resolve() or path.suffix != ".py" or not path.is_file():
        raise ValueError("Tool source is outside the managed tools directory.")
    return path


def load_registry(force: bool = False) -> dict:
    """Load registry from cache or disk. Refresh if missing/outdated."""
    global _registry_cache, _registry_mtime

    if REGISTRY_FILE.exists():
        mtime = REGISTRY_FILE.stat().st_mtime
        if not force and _registry_cache is not None and mtime == _registry_mtime:
            return _registry_cache
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            tools = data.get("tools")
            paths_exist = isinstance(tools, dict) and all(
                not isinstance(info, dict)
                or not info.get("path")
                or Path(info["path"]).is_file()
                for info in tools.values()
            )
            if paths_exist:
                _registry_cache = data
                _registry_mtime = mtime
                return _registry_cache
        except Exception:
            pass

    refresh_tools_registry()
    return _registry_cache  # type: ignore


def update_tool_enabled(tool_name: str, enabled: bool) -> dict:
    """Persist whether a registered tool is available to the LLM."""
    global _registry_cache, _registry_mtime

    registry = load_registry(force=True)
    tools = registry.get("tools", {})
    if tool_name not in tools or not isinstance(tools[tool_name], dict):
        raise KeyError(tool_name)

    tools[tool_name]["enabled"] = enabled
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    _registry_cache = registry
    _registry_mtime = REGISTRY_FILE.stat().st_mtime
    return tools[tool_name]


def get_langchain_tools(force_reload: bool = False) -> list:
    """Convert discovered tools into LangChain StructuredTool list."""
    from langchain_core.tools import StructuredTool

    registry = load_registry(force=force_reload)
    tools_dict = registry.get("tools", {})

    result = []
    for name, info in tools_dict.items():
        if (
            not isinstance(info, dict)
            or info.get("status") != "valid"
            or info.get("enabled", True) is False
        ):
            continue
        try:
            module = _load_module(info["path"], info["module"])
            func_name = info.get("function")
            func = getattr(module, func_name, None) if func_name else _find_main_func(module)
            if func is None:
                continue

            desc = info.get("description") or inspect.getdoc(func) or f"Tool: {name}"
            tool = StructuredTool.from_function(func=func, name=name, description=desc)
            result.append(tool)
        except Exception as e:
            print(f"[registry] Skipping tool '{name}': {e}")
    return result


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _discover_tools() -> dict[str, dict]:
    tools = {}

    for file_path in sorted(TOOLS_DIR.glob("*.py")):
        if file_path.name.startswith("_") or file_path.name == "features.py":
            # features.py is special – we only expose create_tool & refresh
            if file_path.name == "features.py":
                tools["create_tool"] = {
                    "parameter": {
                        "file_name": {"required": True, "type": "str"},
                        "content": {"required": True, "type": "str"},
                        "mode": {"required": False, "type": "str", "default": "w"}
                    },
                    "description": "Create a new tool file inside backend/tools/ and refresh the registry so it becomes usable immediately.",
                    "return": {"type": "dict"},
                    "path": str(file_path),
                    "module": "backend.tools.features",
                    "function": "create_tool",
                    "status": "valid",
                    "error": None
                }
                tools["refresh_tools_registry"] = {
                    "parameter": {},
                    "description": "Force re-discovery of all tools and update the registry.",
                    "return": {"type": "dict"},
                    "path": str(file_path),
                    "module": "backend.tools.features",
                    "function": "refresh_tools_registry",
                    "status": "valid",
                    "error": None
                }
            continue

        module_name = f"backend.tools.{file_path.stem}"
        try:
            module = _load_module(str(file_path), module_name)
        except Exception as e:
            tools[file_path.stem] = {
                "status": "invalid",
                "error": str(e),
                "path": str(file_path),
                "module": module_name,
                "function": None
            }
            continue

        # Prefer TOOL_NAME if defined and only one public function
        public_funcs = [
            (n, obj) for n, obj in inspect.getmembers(module, inspect.isfunction)
            if not n.startswith("_") and obj.__module__ == module.__name__
        ]

        if not public_funcs:
            tools[file_path.stem] = {
                "status": "invalid",
                "error": "No public function found",
                "path": str(file_path),
                "module": module_name,
                "function": None
            }
            continue

        explicit_name = getattr(module, "TOOL_NAME", None)
        meta = getattr(module, "TOOL_META", None) or {}

        for func_name, func in public_funcs:
            tool_name = explicit_name if (len(public_funcs) == 1 and isinstance(explicit_name, str)) else func_name

            tools[tool_name] = {
                "parameter": meta.get("parameter") or _extract_params(func),
                "description": meta.get("description") or (inspect.getdoc(func) or "").strip(),
                "return": meta.get("return") or {},
                "path": str(file_path),
                "module": module_name,
                "function": func_name,
                "status": "valid",
                "error": None
            }

    return tools


def _load_module(file_path: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _find_main_func(module: ModuleType) -> Optional[Callable]:
    for candidate in ("main", "run", "execute"):
        f = getattr(module, candidate, None)
        if callable(f):
            return f
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("_") and obj.__module__ == module.__name__:
            return obj
    return None


def _extract_params(func: Callable) -> dict:
    params = {}
    try:
        sig = inspect.signature(func)
        for name, p in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            info = {"required": p.default is inspect.Parameter.empty}
            if p.annotation is not inspect.Parameter.empty:
                info["type"] = getattr(p.annotation, "__name__", str(p.annotation))
            if p.default is not inspect.Parameter.empty:
                info["default"] = p.default
            params[name] = info
    except Exception:
        pass
    return params
