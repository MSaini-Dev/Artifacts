"""
Powerful shell command execution tool.
Supports dense commands, longer timeouts, and clean output.
"""

import subprocess
import os
from typing import Optional

TOOL_NAME = "execute_command"

TOOL_META = {
    "description": (
        "Execute a shell command and return stdout, stderr, and return code. "
        "Prefer dense multi-command chains using &&, ;, pipes when safe. "
        "Use for running code, installing packages, checking status, git operations, etc."
    ),
    "parameter": {
        "command": {
            "required": True,
            "type": "str",
            "description": "The shell command to execute. Can be a dense chain of commands."
        },
        "timeout": {
            "required": False,
            "type": "int",
            "default": 60,
            "description": "Timeout in seconds (default 60)."
        },
        "cwd": {
            "required": False,
            "type": "str",
            "default": None,
            "description": "Working directory for the command."
        }
    },
    "return": {"type": "dict"}
}


def execute_command(command: str, timeout: int = 60, cwd: Optional[str] = None) -> dict:
    """
    Execute a shell command and return structured result.
    Prefer dense commands (multiple actions chained) to reduce turns.
    """
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd or os.getcwd(),
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.strip() if stdout else "",
                "stderr": stderr.strip() if stderr else "",
                "return_code": proc.returncode,
                "command": command
            }
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True, capture_output=True)
            else:
                proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:
                stdout, stderr = "", ""
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds. Run commands non-interactively (e.g. npx -y, npm --yes).",
                "command": command
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": command
        }
