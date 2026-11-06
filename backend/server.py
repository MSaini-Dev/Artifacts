"""
Frontend Server — FastAPI backend for Brain Studio UI.
Provides REST APIs for:
1. DB Updater (Providers, Models, API Keys without SQL/terminal)
2. Tools Manager (Inspect, execute manually with params, create new tools)
3. Chat Page (Connect to Brain / Agent with tool-calling & failover diagnostics)
4. Logs Inspector (conversation, task attempts, and tool execution records)
"""

import inspect
import base64
import hmac
import ipaddress
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import requests
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add the repository root so the backend also works when launched as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agent.brain_langchain.api_manager.db_updater import (
    DEFAULT_DB_FILE,
    get_connection,
    init_database,
    update_api_keys,
)
from backend.agent.brain_langchain.api_manager.sqlite_logger import (
    get_db_connection,
    init_logging_schema,
    conversation_scope,
    interactive_scope,
    create_conversation,
    update_conversation,
    update_interactive,
)
from backend.agent.brain_langchain.api_manager.activity_stream import (
    register_client,
    unregister_client,
)
from backend.agent.brain_langchain import BrainChatModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from backend.agent.single_agent import call_agent
from backend.agent.agent_profiles import (
    delete_agent_profile,
    get_agent_profile,
    list_agent_profiles,
    remove_tool_from_agent_profiles,
    save_agent_profile,
    set_tool_agent_assignments,
)
from backend.tools.features import (
    get_langchain_tools,
    load_registry,
    refresh_tools_registry,
    create_tool,
    update_tool_enabled,
    _load_module,
    _find_main_func,
    delete_tool_file,
    get_tool_source,
    update_tool_source,
)

app = FastAPI(title="Brain Studio UI Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _api_bind_host() -> str:
    return os.environ.get("HOST") or (
        "0.0.0.0" if os.environ.get("MESH_AGENT_TOKEN") else "127.0.0.1"
    )


# -----------------------------------------------------------------------------
# Pydantic Schemas for API Requests
# -----------------------------------------------------------------------------

class ProviderCreate(BaseModel):
    name: str
    base_url: str
    status: str = "active"
    rate_limit: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    status: Optional[str] = None
    rate_limit: Optional[str] = None


class ModelCreate(BaseModel):
    provider_id: int
    name: str
    status: str = "active"
    preference: Optional[str] = None
    model_size: Optional[float] = 100.0
    RPM: Optional[int] = None
    RPD: Optional[int] = None
    TPM: Optional[int] = None
    TPD: Optional[int] = None
    disabled_reason: Optional[str] = None
    rate_limit: Optional[str] = None


class ModelUpdate(BaseModel):
    provider_id: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    preference: Optional[str] = None
    model_size: Optional[float] = None
    RPM: Optional[int] = None
    RPD: Optional[int] = None
    TPM: Optional[int] = None
    TPD: Optional[int] = None
    disabled_reason: Optional[str] = None
    rate_limit: Optional[str] = None


class APIKeyCreate(BaseModel):
    provider_id: int
    unique_name: str
    env_key: str
    status: str = "active"
    rate_limit: Optional[str] = None
    disabled_reason: Optional[str] = None


class APIKeyUpdate(BaseModel):
    provider_id: Optional[int] = None
    unique_name: Optional[str] = None
    env_key: Optional[str] = None
    status: Optional[str] = None
    rate_limit: Optional[str] = None
    disabled_reason: Optional[str] = None


class ToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = {}


class ToolCreateRequest(BaseModel):
    file_name: str
    content: str
    mode: str = "x"


class ToolSourceRequest(BaseModel):
    content: str = Field(max_length=262144)


class ToolAgentAssignmentRequest(BaseModel):
    agent_ids: List[str] = Field(default_factory=list, max_length=100)


class ToolEnabledRequest(BaseModel):
    enabled: bool


class AgentProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    system_prompt: str = Field(min_length=1, max_length=50000)
    tool_names: List[str] = Field(default_factory=list, max_length=200)
    profile_photo: Optional[str] = None


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ConversationUpdate(BaseModel):
    title: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "agent"  # "agent" or "direct"
    agent_id: Optional[str] = None
    temperature: float = 0.2
    max_turns: int = Field(default=20, ge=1, le=50)
    conversation_id: Optional[int] = None


class MeshMessageRequest(BaseModel):
    dest: str = Field(min_length=1, max_length=128)
    msg: str = Field(min_length=1, max_length=10000)


class MeshConnectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512)


class MeshNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class MeshAgentRequest(BaseModel):
    peer_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=100000)
    temperature: float = Field(default=0.2, ge=0, le=1)
    max_turns: int = Field(default=20, ge=1, le=50)
    conversation_id: Optional[int] = None


def _mesh_api_url(path: str) -> str:
    base_url = os.environ.get("MESH_API_URL", "http://127.0.0.1:8766").rstrip("/")
    return f"{base_url}/{path.lstrip('/')}"


def _mesh_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> Any:
    try:
        response = requests.request(
            method,
            _mesh_api_url(path),
            json=payload,
            timeout=5,
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach the local Mesh node at {os.environ.get('MESH_API_URL', 'http://127.0.0.1:8766')}: {error}",
        ) from error

    try:
        result = response.json()
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Mesh node returned an invalid response") from error

    if not response.ok:
        detail = result.get("error") if isinstance(result, dict) else None
        raise HTTPException(status_code=response.status_code, detail=detail or "Mesh node request failed")
    return result


def _remote_agent_url(peer: dict) -> str:
    address = peer.get("addr")
    if not isinstance(address, str):
        raise HTTPException(status_code=400, detail="Selected peer has no reachable Mesh address")

    parsed = urlsplit(address)
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Selected peer has an invalid Mesh address")

    try:
        agent_port = int(os.environ.get("MESH_AGENT_PORT", "8000"))
    except ValueError as error:
        raise HTTPException(status_code=500, detail="MESH_AGENT_PORT must be a valid port number") from error
    if not 1 <= agent_port <= 65535:
        raise HTTPException(status_code=500, detail="MESH_AGENT_PORT must be between 1 and 65535")

    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunsplit((scheme, f"{host}:{agent_port}", "/api/chat", "", ""))


@app.middleware("http")
async def protect_remote_api(request: Request, call_next):
    client_host = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False

    if not is_loopback:
        expected_token = os.environ.get("MESH_AGENT_TOKEN", "")
        supplied_token = request.headers.get("X-Mesh-Agent-Token", "")
        if not expected_token or not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
            return JSONResponse(
                {"detail": "Remote API access requires a valid MESH_AGENT_TOKEN"},
                status_code=403,
            )
    return await call_next(request)


def _clean_user_message(content: Any) -> str:
    """Unwrap transcript labels accidentally stored inside a user message."""
    if not content:
        return ""
    text = str(content).strip()
    user_labels = list(re.finditer(r"(?m)^\s*User:\s*", text))
    if user_labels:
        text = text[user_labels[-1].end():].strip()

    while re.match(r"^User:\s*", text):
        text = re.sub(r"^User:\s*", "", text, count=1).strip()
    return text


def _extract_user_text(payload: Any) -> str:
    """Extract the latest user message from structured or flattened chat payloads."""
    if not payload:
        return ""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return _clean_user_message(payload)
        if isinstance(payload, str):
            return _clean_user_message(payload)
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("role") == "user":
                    content = message.get("content")
                    if content:
                        return _clean_user_message(content)
        if payload.get("user_prompt"):
            return _clean_user_message(payload["user_prompt"])
        if payload.get("prompt"):
            return _clean_user_message(payload["prompt"])
    return ""


def _load_api_call_interactions(conn: Any, conversation_id: int) -> List[List[Dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT * FROM API_Call_Log
        WHERE Conversation_Id = ?
        ORDER BY Interaction_Id ASC, Iteration_Id ASC, API_Call_Id ASC
        """,
        (conversation_id,),
    ).fetchall()
    interactions: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        interactions.setdefault(row["Interaction_Id"], []).append(dict(row))
    return list(interactions.values())


# -----------------------------------------------------------------------------
# Database Updater Endpoints (Providers, Models, API Keys)
# -----------------------------------------------------------------------------

@app.get("/api/stats")
def get_system_stats():
    init_database()
    init_logging_schema()
    with get_connection() as conn:
        providers_count = conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]
        models_count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        keys_count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        active_models = conn.execute("SELECT COUNT(*) FROM models WHERE status='active'").fetchone()[0]
        convs_count = conn.execute("SELECT COUNT(*) FROM Conversation").fetchone()[0]

    registry = load_registry()
    tools_count = len(registry.get("tools", {}))

    return {
        "providers_count": providers_count,
        "models_count": models_count,
        "keys_count": keys_count,
        "active_models": active_models,
        "tools_count": tools_count,
        "conversations_count": convs_count,
    }


# --- Providers ---

@app.get("/api/providers")
def list_providers():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM providers ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/providers")
def add_provider(p: ProviderCreate):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO providers (name, base_url, status, rate_limit, created_at, last_modify)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (p.name.strip(), p.base_url.strip(), p.status, p.rate_limit, now, now),
            )
            conn.commit()
            return {"success": True, "id": cursor.lastrowid}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/providers/{provider_id}")
def update_provider(provider_id: int, p: ProviderUpdate):
    fields = []
    params = []
    now = datetime.now().isoformat()

    if p.name is not None:
        fields.append("name = ?")
        params.append(p.name.strip())
    if p.base_url is not None:
        fields.append("base_url = ?")
        params.append(p.base_url.strip())
    if p.status is not None:
        fields.append("status = ?")
        params.append(p.status)
    if p.rate_limit is not None:
        fields.append("rate_limit = ?")
        params.append(p.rate_limit)

    fields.append("last_modify = ?")
    params.append(now)
    params.append(provider_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE providers SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return {"success": True}


@app.delete("/api/providers/{provider_id}")
def delete_provider(provider_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()
    return {"success": True}


# --- Models ---

@app.get("/api/models")
def list_models():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT m.*, p.name as provider_name 
            FROM models m
            JOIN providers p ON m.provider_id = p.id
            ORDER BY m.id ASC
        """).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/models")
def add_model(m: ModelCreate):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO models (
                    provider_id, name, status, preference, model_size,
                    RPM, RPD, TPM, TPD, disabled_reason, rate_limit, created_at, last_modify
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    m.provider_id, m.name.strip(), m.status, m.preference, m.model_size,
                    m.RPM, m.RPD, m.TPM, m.TPD, m.disabled_reason, m.rate_limit, now, now
                ),
            )
            conn.commit()
            return {"success": True, "id": cursor.lastrowid}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/models/{model_id}")
def update_model(model_id: int, m: ModelUpdate):
    fields = []
    params = []
    now = datetime.now().isoformat()

    for k, v in m.dict(exclude_unset=True).items():
        fields.append(f"{k} = ?")
        params.append(v)

    fields.append("last_modify = ?")
    params.append(now)
    params.append(model_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE models SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return {"success": True}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        conn.commit()
    return {"success": True}


# --- API Keys ---

@app.get("/api/api-keys")
def list_api_keys():
    update_api_keys()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT k.*, p.name as provider_name
            FROM api_keys k
            JOIN providers p ON k.provider_id = p.id
            ORDER BY k.id ASC
        """).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            env_key = d.get("env_key")
            d["env_configured"] = bool(os.environ.get(env_key) or os.environ.get("LLM_" + env_key) or os.environ.get(env_key.replace("LLM_", "")))
            res.append(d)
        return res


@app.post("/api/api-keys")
def add_api_key(k: APIKeyCreate):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO api_keys (provider_id, unique_name, env_key, status, rate_limit, disabled_reason, created_at, last_modify)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (k.provider_id, k.unique_name.strip(), k.env_key.strip(), k.status, k.rate_limit, k.disabled_reason, now, now),
            )
            conn.commit()
            return {"success": True, "id": cursor.lastrowid}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/api-keys/{key_id}")
def update_api_key(key_id: int, k: APIKeyUpdate):
    fields = []
    params = []
    now = datetime.now().isoformat()

    for field, val in k.dict(exclude_unset=True).items():
        fields.append(f"{field} = ?")
        params.append(val)

    fields.append("last_modify = ?")
    params.append(now)
    params.append(key_id)

    with get_connection() as conn:
        conn.execute(f"UPDATE api_keys SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return {"success": True}


@app.delete("/api/api-keys/{key_id}")
def delete_api_key(key_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        conn.commit()
    return {"success": True}


# -----------------------------------------------------------------------------
# Tools Manager Endpoints (List, Manual Execution, Creation)
# -----------------------------------------------------------------------------

@app.get("/api/tools")
def list_tools():
    registry = load_registry(force=True)
    tools = registry.get("tools", {})
    profiles = list_agent_profiles()
    for info in tools.values():
        if isinstance(info, dict):
            info.setdefault("enabled", True)
    for tool_name, info in tools.items():
        if not isinstance(info, dict):
            continue
        info["assigned_agents"] = [
            {"id": profile["id"], "name": profile["name"]}
            for profile in profiles
            if profile["tool_names"] == ["*"] or tool_name in profile["tool_names"]
        ]
    return tools


@app.get("/api/tools/{tool_name}/source")
def read_tool_source(tool_name: str):
    try:
        return get_tool_source(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found in registry")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/tools/{tool_name}/source")
def write_tool_source(tool_name: str, req: ToolSourceRequest):
    try:
        return update_tool_source(tool_name, req.content)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found in registry")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/tools/{tool_name}/agents")
def assign_tool_agents(tool_name: str, req: ToolAgentAssignmentRequest):
    try:
        profiles = set_tool_agent_assignments(tool_name, req.agent_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown tool or agent: {exc}") from exc
    return {
        "success": True,
        "assigned_agents": [
            {"id": profile["id"], "name": profile["name"]}
            for profile in profiles
            if profile["tool_names"] == ["*"] or tool_name in profile["tool_names"]
        ],
    }


@app.delete("/api/tools/{tool_name}")
def remove_tool(tool_name: str):
    try:
        result = delete_tool_file(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found in registry")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for deleted_name in result["deleted_tools"]:
        remove_tool_from_agent_profiles(deleted_name)
    return result


@app.put("/api/tools/{tool_name}/enabled")
def set_tool_enabled(tool_name: str, req: ToolEnabledRequest):
    try:
        return update_tool_enabled(tool_name, req.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found in registry")


@app.post("/api/tools/execute")
def execute_tool_manually(req: ToolExecuteRequest):
    """Execute a registered tool directly with provided arguments."""
    registry = load_registry()
    tools = registry.get("tools", {})
    tool_info = tools.get(req.tool_name)

    if not tool_info:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool_name}' not found in registry")

    start_time = time.perf_counter()
    try:
        module = _load_module(tool_info["path"], tool_info["module"])
        func_name = tool_info.get("function")
        func = getattr(module, func_name, None) if func_name else _find_main_func(module)
        if func is None:
            raise ValueError(f"No executable function found for tool {req.tool_name}")

        result = func(**req.arguments)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "success": True,
            "tool_name": req.tool_name,
            "duration_ms": duration_ms,
            "result": result,
            "error": None,
        }
    except Exception as e:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": False,
            "tool_name": req.tool_name,
            "duration_ms": duration_ms,
            "result": None,
            "error": str(e),
        }


@app.post("/api/tools/create")
def create_new_tool(req: ToolCreateRequest):
    """Create a new tool script in backend/tools/ and reload the registry."""
    if req.mode != "x":
        raise HTTPException(status_code=400, detail="Creating a tool cannot overwrite an existing file.")
    res = create_tool(file_name=req.file_name, content=req.content, mode=req.mode)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


# -----------------------------------------------------------------------------
# Agent profile management
# -----------------------------------------------------------------------------

def _validated_agent_profile(req: AgentProfileRequest) -> Dict[str, Any]:
    tool_names = list(dict.fromkeys(name.strip() for name in req.tool_names if name.strip()))
    if "*" in tool_names and tool_names != ["*"]:
        raise HTTPException(status_code=400, detail="'*' must be the only selected tool.")

    available_tools = load_registry(force=True).get("tools", {})
    unknown_tools = [name for name in tool_names if name != "*" and name not in available_tools]
    if unknown_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tool name(s): {', '.join(unknown_tools)}",
        )

    photo = req.profile_photo
    if photo:
        match = re.fullmatch(
            r"data:image/(?:png|jpeg|webp|gif);base64,([A-Za-z0-9+/]*={0,2})",
            photo,
        )
        if not match:
            raise HTTPException(status_code=400, detail="Profile photo must be a PNG, JPEG, WebP, or GIF image.")
        try:
            decoded = base64.b64decode(match.group(1), validate=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Profile photo data is invalid.") from exc
        if len(decoded) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Profile photo must be 2 MB or smaller.")

    return {
        "name": req.name.strip(),
        "description": req.description.strip(),
        "system_prompt": req.system_prompt,
        "tool_names": tool_names,
        "profile_photo": photo,
    }


@app.get("/api/agents")
def list_agents():
    """Return saved agent profiles and the current registered tool catalog."""
    profiles = list_agent_profiles()
    registry = load_registry(force=True).get("tools", {})
    return {
        "agents": profiles,
        "tools": [
            {
                "name": name,
                "description": info.get("description", ""),
                "enabled": info.get("enabled", True),
                "status": info.get("status", "unknown"),
            }
            for name, info in sorted(registry.items())
            if isinstance(info, dict)
        ],
    }


@app.post("/api/agents")
def create_agent(req: AgentProfileRequest):
    try:
        return save_agent_profile(_validated_agent_profile(req))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not create agent profile: {exc}") from exc


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: str, req: AgentProfileRequest):
    if get_agent_profile(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent profile '{agent_id}' was not found.")
    try:
        return save_agent_profile(_validated_agent_profile(req), profile_id=agent_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not update agent profile: {exc}") from exc


@app.delete("/api/agents/{agent_id}")
def remove_agent(agent_id: str):
    try:
        if not delete_agent_profile(agent_id):
            raise HTTPException(status_code=404, detail=f"Agent profile '{agent_id}' was not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True}


# -----------------------------------------------------------------------------
# Conversation Management Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/conversations")
def list_conversations():
    """List all conversations ordered by recent activity, with turn count."""
    init_logging_schema()
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT c.ID, c.Title, c.Created_At, c.Updated_At,
                   COUNT(DISTINCT l.Interaction_Id) AS message_count
            FROM Conversation c
            LEFT JOIN API_Call_Log l ON l.Conversation_Id = c.ID
            GROUP BY c.ID
            ORDER BY c.Updated_At DESC, c.ID DESC
        """).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/conversations")
def create_new_conversation(req: Optional[ConversationCreate] = None):
    """Create an isolated new conversation."""
    init_logging_schema()
    title = (req.title if req and req.title else "New Chat").strip()
    cid = create_conversation(title=title)
    return {"id": cid, "title": title}


@app.get("/api/conversations/{conv_id}/messages")
def get_conversation_messages(conv_id: int):
    """Get all past turns for an isolated conversation."""
    init_logging_schema()
    with get_db_connection() as conn:
        conv = conn.execute("SELECT * FROM Conversation WHERE ID = ?", (conv_id,)).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = []
        for calls in _load_api_call_interactions(conn, conv_id):
            first_payload = next((call["Payload"] for call in calls if call["Payload"]), None)
            final_call = next(
                (call for call in reversed(calls) if call["Final_Response"] == 1),
                None,
            )
            interaction_id = calls[0]["Interaction_Id"]
            created_at = calls[0]["Timestamp"]
            # Provider payloads retain the structured messages; prefer their last
            # user message over Interaction_Prompt, which older versions stored
            # as a flattened User:/Assistant: transcript.
            u_text = _extract_user_text(first_payload) or _clean_user_message(
                calls[0]["Interaction_Prompt"]
            )
            tool_activity = [
                dict(tool)
                for tool in conn.execute(
                    """
                    SELECT *
                    FROM Tool_Execution
                    WHERE Conversation_Id = ? AND Interaction_Id = ?
                    ORDER BY ID
                    """,
                    (conv_id, interaction_id),
                ).fetchall()
            ]
            if u_text:
                messages.append({
                    "id": f"u_{interaction_id}",
                    "role": "user",
                    "content": u_text,
                    "created_at": created_at,
                    "interactive_id": interaction_id,
                })
            if final_call and final_call["Response"]:
                messages.append({
                    "id": f"a_{interaction_id}",
                    "role": "assistant",
                    "content": final_call["Response"],
                    "created_at": final_call["Timestamp"],
                    "interactive_id": interaction_id,
                    "status": "Final",
                    "tool_activity": tool_activity,
                })

        return {
            "conversation": dict(conv),
            "messages": messages,
        }


@app.get("/api/conversations/{conv_id}/activity")
def get_conversation_activity(conv_id: int, after_interaction_id: int = 0):
    """Return tool executions for the latest interaction newer than the caller's baseline."""
    with get_db_connection() as conn:
        conversation = conn.execute(
            "SELECT Next_Interaction_Id FROM Conversation WHERE ID = ?",
            (conv_id,),
        ).fetchone()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        interaction_id = int(conversation["Next_Interaction_Id"]) - 1
        if interaction_id <= after_interaction_id:
            return {"interaction_id": None, "tools": []}

        tools = conn.execute(
            """
            SELECT *
            FROM Tool_Execution
            WHERE Conversation_Id = ? AND Interaction_Id = ?
            ORDER BY ID
            """,
            (conv_id, interaction_id),
        ).fetchall()
        return {
            "interaction_id": interaction_id,
            "tools": [dict(tool) for tool in tools],
        }


@app.websocket("/ws/conversations/{conv_id}/activity")
async def stream_conversation_activity(
    websocket: WebSocket,
    conv_id: int,
    after_interaction_id: int = 0,
):
    """Push tool execution changes to a chat client over a persistent socket."""
    client_host = websocket.client.host if websocket.client else ""
    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False

    if not is_loopback:
        expected_token = os.environ.get("MESH_AGENT_TOKEN", "")
        supplied_token = websocket.headers.get("X-Mesh-Agent-Token", "")
        if not expected_token or not supplied_token or not hmac.compare_digest(
            supplied_token, expected_token
        ):
            await websocket.close(code=4403)
            return

    with get_db_connection() as conn:
        conversation = conn.execute(
            "SELECT Next_Interaction_Id FROM Conversation WHERE ID = ?",
            (conv_id,),
        ).fetchone()
    if not conversation:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    await register_client(conv_id, websocket)
    try:
        interaction_id = int(conversation["Next_Interaction_Id"]) - 1
        if interaction_id > after_interaction_id:
            with get_db_connection() as conn:
                tools = conn.execute(
                    """
                    SELECT *
                    FROM Tool_Execution
                    WHERE Conversation_Id = ? AND Interaction_Id = ?
                    ORDER BY ID
                    """,
                    (conv_id, interaction_id),
                ).fetchall()
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "interaction_id": interaction_id,
                    "tools": [dict(tool) for tool in tools],
                }
            )

        while True:
            message = json.loads(await websocket.receive_text())
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except (json.JSONDecodeError, RuntimeError):
        await websocket.close(code=4400)
    finally:
        await unregister_client(conv_id, websocket)


@app.patch("/api/conversations/{conv_id}")
def rename_conversation(conv_id: int, req: ConversationUpdate):
    """Rename a conversation title."""
    init_logging_schema()
    update_conversation(conversation_id=conv_id, title=req.title)
    return {"success": True, "id": conv_id, "title": req.title}


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    """Delete a conversation and its logged interactions."""
    init_logging_schema()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM Conversation WHERE ID = ?", (conv_id,))
        conn.commit()
    return {"success": True, "id": conv_id}


# -----------------------------------------------------------------------------
# Chat / Agent Endpoint
# -----------------------------------------------------------------------------

@app.get("/api/mesh/snapshot")
def get_mesh_snapshot():
    return {
        "mesh_api_url": os.environ.get("MESH_API_URL", "http://127.0.0.1:8766"),
        "status": _mesh_request("/status"),
        "inbox": _mesh_request("/inbox"),
        "sent": _mesh_request("/sent"),
    }


@app.post("/api/mesh/send")
def send_mesh_message(req: MeshMessageRequest):
    return _mesh_request("/send", "POST", {"dest": req.dest, "msg": req.msg})


@app.post("/api/mesh/connect")
def connect_mesh_peer(req: MeshConnectRequest):
    parsed = urlsplit(req.url.strip())
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname or parsed.port is None:
        raise HTTPException(status_code=400, detail="Peer URL must look like ws://<laptop-ip>:8765")
    return _mesh_request("/connect", "POST", {"url": req.url.strip()})


@app.post("/api/mesh/name")
def set_mesh_name(req: MeshNameRequest):
    return _mesh_request("/name", "POST", {"name": req.name.strip()})


@app.post("/api/mesh/agent")
def call_peer_agent(req: MeshAgentRequest):
    token = os.environ.get("MESH_AGENT_TOKEN", "")
    if not token:
        raise HTTPException(
            status_code=503,
            detail="Set MESH_AGENT_TOKEN on every laptop before calling a remote agent",
        )

    status = _mesh_request("/status")
    graph = status.get("graph", {})
    if not isinstance(graph, dict) or req.peer_id == status.get("self_id"):
        raise HTTPException(status_code=400, detail="Select a remote Mesh peer")
    peer = graph.get(req.peer_id)
    if not isinstance(peer, dict):
        raise HTTPException(status_code=404, detail="Selected peer is not in the Mesh network")

    agent_url = _remote_agent_url(peer)
    try:
        response = requests.post(
            agent_url,
            headers={"X-Mesh-Agent-Token": token},
            json={
                "message": req.message,
                "mode": "agent",
                "temperature": req.temperature,
                "max_turns": req.max_turns,
                "conversation_id": req.conversation_id,
            },
            timeout=(5, 300),
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach the selected peer's agent at {agent_url}: {error}",
        ) from error

    try:
        result = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail=f"The selected peer's agent returned an invalid response (HTTP {response.status_code})",
        ) from error

    if not response.ok:
        detail = result.get("detail") or result.get("error") if isinstance(result, dict) else None
        raise HTTPException(
            status_code=response.status_code,
            detail=detail or "The selected peer's agent request failed",
        )
    return result


@app.post("/api/chat")
def handle_chat_message(req: ChatRequest):
    """Run interactive chat with history retention in the active conversation."""
    start_time = time.perf_counter()
    try:
        init_logging_schema()
        conv_id = req.conversation_id

        # Validate or create conversation
        with get_db_connection() as conn:
            if conv_id:
                exists = conn.execute("SELECT ID, Title FROM Conversation WHERE ID = ?", (conv_id,)).fetchone()
                if not exists:
                    conv_id = None

            if not conv_id:
                title = (req.message[:50] if req.message else "New Chat").strip()
                conv_id = create_conversation(title=title)
            else:
                row = conn.execute("SELECT Title FROM Conversation WHERE ID = ?", (conv_id,)).fetchone()
                if row and (row["Title"] in ("New Chat", "Untitled Conversation") or not row["Title"]):
                    title = (req.message[:50] if req.message else "New Chat").strip()
                    update_conversation(conversation_id=conv_id, title=title)

        # Retrieve prior turns for this specific conversation to retain context
        history = []
        with get_db_connection() as conn:
            for calls in _load_api_call_interactions(conn, conv_id):
                payload = next((call["Payload"] for call in calls if call["Payload"]), None)
                final_call = next(
                    (call for call in reversed(calls) if call["Final_Response"] == 1),
                    None,
                )
                u_text = _extract_user_text(payload) or _clean_user_message(
                    calls[0]["Interaction_Prompt"]
                )
                a_text = final_call["Response"] if final_call else None
                if u_text:
                    history.append({"role": "user", "content": u_text})
                if a_text:
                    history.append({"role": "assistant", "content": a_text})

        agent_profile = None
        if req.mode == "agent":
            agent_id = req.agent_id or "assistant"
            agent_profile = get_agent_profile(agent_id)
            if agent_profile is None:
                raise HTTPException(status_code=404, detail=f"Agent profile '{agent_id}' was not found.")

        request_payload = {
            "user_prompt": req.message,
            "mode": req.mode,
            "agent_id": agent_profile["id"] if agent_profile else None,
            "temperature": req.temperature,
            "max_turns": req.max_turns,
            "conversation_id": conv_id,
            "messages": history + [{"role": "user", "content": req.message}],
        }

        if req.mode == "direct":
            with conversation_scope(conversation_id=conv_id):
                with interactive_scope(conversation_id=conv_id, payload=request_payload) as inter_id:
                    lc_msgs = []
                    for h in history:
                        if h["role"] == "user":
                            lc_msgs.append(HumanMessage(content=h["content"]))
                        elif h["role"] == "assistant":
                            lc_msgs.append(AIMessage(content=h["content"]))
                    lc_msgs.append(HumanMessage(content=req.message))

                    try:
                        model = BrainChatModel(temperature=req.temperature)
                        resp = model.invoke(lc_msgs)
                    except Exception:
                        update_interactive(
                            interactive_id=inter_id,
                            response_status="Not_Final",
                            duration_seconds=time.perf_counter() - start_time,
                        )
                        raise
                    content = resp.content if hasattr(resp, "content") else str(resp)
                    update_interactive(
                        interactive_id=inter_id,
                        response_status="Final",
                        duration_seconds=time.perf_counter() - start_time,
                    )

                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    additional = getattr(resp, "additional_kwargs", {}) or {}
                    return {
                        "success": True,
                        "response": content,
                        "duration_ms": duration_ms,
                        "conversation_id": conv_id,
                        "chosen": {
                            "provider": additional.get("provider"),
                            "model": additional.get("model"),
                            "key_name": additional.get("key_name"),
                        },
                        "total_attempts": additional.get("total_attempts", 1),
                        "tool_calls": getattr(resp, "tool_calls", None) or [],
                        "mode": "direct",
                    }
        else:
            available_tools = get_langchain_tools(force_reload=True)
            selected_tool_names = agent_profile["tool_names"]
            if selected_tool_names == ["*"]:
                agent_tools = available_tools
            else:
                available_by_name = {tool.name: tool for tool in available_tools}
                missing_tools = [
                    name for name in selected_tool_names if name not in available_by_name
                ]
                if missing_tools:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Selected tool(s) are not currently enabled or available: "
                            + ", ".join(missing_tools)
                        ),
                    )
                agent_tools = [
                    available_by_name[name] for name in selected_tool_names
                ]

            result_text = call_agent(
                user_prompt=req.message,
                tools=agent_tools,
                max_turns=req.max_turns,
                temperature=req.temperature,
                verbose=False,
                conversation_id=conv_id,
                history=history,
                log_payload=request_payload,
                process_started_at=start_time,
                system_prompt_override=agent_profile["system_prompt"],
            )
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": True,
                "response": result_text,
                "duration_ms": duration_ms,
                "mode": "agent",
                "agent_id": agent_profile["id"],
                "conversation_id": conv_id,
            }
    except Exception as e:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": False,
            "response": None,
            "error": str(e),
            "duration_ms": duration_ms,
        }


# -----------------------------------------------------------------------------
# SQLite3 Logs & Iterations Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/logs/conversations")
def get_conversations(limit: int = 20):
    init_logging_schema()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Conversation ORDER BY ID DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/logs/conversations/{conv_id}")
def get_conversation_details(conv_id: int):
    init_logging_schema()
    with get_db_connection() as conn:
        conv = conn.execute("SELECT * FROM Conversation WHERE ID = ?", (conv_id,)).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        result_interactives = []
        for calls in _load_api_call_interactions(conn, conv_id):
            iteration_groups: Dict[int, List[Dict[str, Any]]] = {}
            for call in calls:
                iteration_groups.setdefault(call["Iteration_Id"], []).append(call)
            tool_rows = conn.execute(
                """
                SELECT * FROM Tool_Execution
                WHERE Conversation_Id = ? AND Interaction_Id = ?
                ORDER BY Timestamp ASC, ID ASC
                """,
                (conv_id, calls[0]["Interaction_Id"]),
            ).fetchall()
            task_records = []
            execution_records = []
            for task_id, api_calls in iteration_groups.items():
                successful_calls = [
                    call for call in api_calls if call["Request_Status"] == "Success"
                ]
                first_call = api_calls[0]
                task_started_at = next(
                    (
                        call["Task_Started_At"]
                        for call in api_calls
                        if call["Task_Started_At"]
                    ),
                    first_call["Timestamp"],
                )
                task_duration = next(
                    (
                        call["Task_Duration_Seconds"]
                        for call in api_calls
                        if call["Task_Duration_Seconds"] is not None
                    ),
                    None,
                )
                task_is_running = any(
                    not call["Task_Is_Complete"] for call in api_calls
                )
                task = {
                    "ID": task_id,
                    "Name": "LLM API",
                    "Model": next(
                        (call["Model"] for call in reversed(api_calls) if call["Model"]),
                        None,
                    ),
                    "Timestamp": task_started_at,
                    "Duration_Seconds": task_duration,
                    "Status": (
                        "Running"
                        if task_is_running
                        else "Success"
                        if successful_calls
                        else "Failed"
                    ),
                    "Request": next(
                        (call["Payload"] for call in api_calls if call["Payload"]),
                        None,
                    ),
                    "Final_Response": next(
                        (
                            call["Response"]
                            for call in reversed(successful_calls)
                            if call["Response"] is not None
                        ),
                        None,
                    ),
                    "api_calls": api_calls,
                }
                task_records.append(task)
                execution_records.append(
                    {
                        "type": "task",
                        "Timestamp": task_started_at,
                        "ID": task_id,
                        "task": task,
                    }
                )

            for row in tool_rows:
                tool = dict(row)
                execution_records.append(
                    {
                        "type": "tool",
                        "Timestamp": tool["Timestamp"],
                        "ID": tool["ID"],
                        "tool": tool,
                    }
                )
            execution_records.sort(
                key=lambda record: (
                    record["Timestamp"] or "",
                    0 if record["type"] == "task" else 1,
                    record["ID"],
                )
            )
            final_call = next(
                (call for call in reversed(calls) if call["Final_Response"] == 1),
                None,
            )
            durations = [call["Duration"] for call in calls if call["Duration"] is not None]
            result_interactives.append({
                "ID": calls[0]["Interaction_Id"],
                "Created_At": calls[0]["Timestamp"],
                "Response_Status": "Final" if final_call else "Not_Final",
                "Duration_Seconds": sum(durations) if durations else None,
                "Payload": next((call["Payload"] for call in calls if call["Payload"]), None),
                "Interaction_Prompt": calls[0]["Interaction_Prompt"],
                "Actual_Response": final_call["Response"] if final_call else None,
                "iterations": [
                    {
                        "ID": iteration_id,
                        "api_calls": api_calls,
                    }
                    for iteration_id, api_calls in iteration_groups.items()
                ],
                "tasks": task_records,
                "execution_records": execution_records,
            })

        return {
            "conversation": dict(conv),
            "interactives": result_interactives,
        }


# -----------------------------------------------------------------------------
# Static Files & SPA Routing
# -----------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"status": "healthy", "message": "Frontend static files not yet compiled"})
    return FileResponse(str(index_file))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.server:app",
        host=_api_bind_host(),
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
