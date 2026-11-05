"""
Tool to delete an unused tool file from backend/tools/ and refresh registry.
"""

from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

def delete_tool(tool_name: str) -> dict:
    """
    Delete an unused tool by its name or file name from backend/tools/ and refresh the registry.
    """
    # Prevent deleting core management tools
    protected = {"create_tool", "refresh_tools_registry", "delete_tool", "features"}
    if tool_name in protected or tool_name.replace(".py", "") in protected:
        return {"success": False, "error": f"Cannot delete protected tool: {tool_name}"}

    # Search for matching file
    file_path = None
    # Check if tool_name is file name or tool name
    target_file = tool_name if tool_name.endswith(".py") else f"{tool_name}.py"
    candidate = TOOLS_DIR / target_file
    if candidate.exists() and candidate.is_file():
        file_path = candidate
    else:
        # Check by registry or scan files
        for p in TOOLS_DIR.glob("*.py"):
            if p.stem == tool_name:
                file_path = p
                break

    if not file_path or not file_path.exists():
        return {"success": False, "error": f"Tool '{tool_name}' not found in tools directory."}

    try:
        file_path.unlink()
        
        # Refresh tools registry
        from backend.tools.features import refresh_tools_registry
        refresh_tools_registry()

        return {
            "success": True,
            "message": f"Successfully deleted tool '{tool_name}' (file: {file_path.name}) and refreshed registry.",
            "deleted_file": str(file_path)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
