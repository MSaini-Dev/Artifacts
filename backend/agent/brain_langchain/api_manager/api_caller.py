"""
api_caller.py — SQLite-backed failover router for LLM provider selection and database updates.
Incorporates model-size ranking, cooldown tracking, waiting nodes, and Laya recovery decision making.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .db_updater import (
    DEFAULT_DB_FILE,
    get_connection,
    init_database,
    provider_generator,
    model_generator,
    update_api_keys,
    seed_default_data,
    _ensure_column,
    _parse_env_key,
)
from .sqlite_logger import (
    init_logging_schema,
    create_conversation,
    create_interactive,
    update_interactive,
    create_api_call,
    next_iteration_id,
    update_api_call,
    log_decide,
    log_wait,
    active_conversation_id,
    active_interactive_id,
    active_iteration_id,
    active_api_call_id,
    complete_api_task,
)

DB_FILE = DEFAULT_DB_FILE

DAY_SECONDS = 86400
MINUTE_SECONDS = 60
TRANSIENT_STATUSES = (408, 429, 500, 502, 503, 504)

LAYA_ACTIONS = (
    "DISABLE_PROVIDER",
    "COOLDOWN_PROVIDER_MINUTE",
    "DISABLE_MODEL",
    "COOLDOWN_MODEL_MINUTE",
    "COOLDOWN_MODEL_DAY",
    "DISABLE_API_KEY",
    "COOLDOWN_API_KEY_MINUTE",
    "COOLDOWN_API_KEY_DAY",
)

GEMINI_DUMMY_SIGNATURE = "skip_thought_signature_validator"


def _is_gemini(url: str, model: str) -> bool:
    return (
        "generativelanguage.googleapis.com" in url.lower()
        or model.lower().startswith("gemini")
    )


def _is_tool_compat_error(text: str) -> bool:
    return bool(re.search(r"thought[_ ]?signature|function call is missing", text, re.I))




def resolve_db_path(db_path: Optional[str] = None) -> str:
    path = db_path or os.environ.get("DB_PATH") or DB_FILE
    if os.path.isabs(path):
        return path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base_dir, path))


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def reactivate_expired_cooldowns(db_path: str = DB_FILE) -> bool:
    db_path = resolve_db_path(db_path)
    init_database(db_path)
    now = datetime.now().astimezone()
    now_str = now.replace(tzinfo=None).isoformat(timespec="seconds")
    changed = False
    with get_connection(db_path) as conn:
        bad_model_rows = conn.execute(
            """SELECT id, provider_id, disabled_reason FROM api_keys
               WHERE status = 'cooldown' AND disabled_reason LIKE '%not found%'"""
        ).fetchall()
        for key_row in bad_model_rows:
            reason = key_row["disabled_reason"] or ""
            match = re.search(r"\bmodel\b\s+['\"]([^'\"]+)['\"]\s+not found", reason, re.I)
            if not match:
                continue
            model = conn.execute(
                "SELECT id FROM models WHERE provider_id = ? AND LOWER(name) = LOWER(?)",
                (key_row["provider_id"], match.group(1)),
            ).fetchone()
            if not model:
                continue
            conn.execute(
                "UPDATE models SET status = 'disabled', disabled_reason = ?, last_modify = ? WHERE id = ?",
                (reason, now_str, model["id"]),
            )
            conn.execute(
                """UPDATE api_keys SET status = 'active', rate_limit = NULL,
                   disabled_reason = NULL, last_modify = ? WHERE id = ?""",
                (now_str, key_row["id"]),
            )
            changed = True

        for table, clear_reason in (
            ("api_keys", True),
            ("providers", False),
            ("models", True),
        ):
            rows = conn.execute(
                f"SELECT id, rate_limit FROM {table} WHERE status = 'cooldown' AND rate_limit IS NOT NULL"
            ).fetchall()
            for row in rows:
                expiry = _parse_ts(row["rate_limit"])
                if expiry is None:
                    continue
                if expiry <= now.replace(tzinfo=None):
                    statement = "status = 'active', rate_limit = NULL, last_modify = ?"
                    if clear_reason:
                        statement += ", disabled_reason = NULL"
                    conn.execute(
                        f"UPDATE {table} SET {statement} WHERE id = ?",
                        (now_str, row["id"]),
                    )
                    changed = True
        conn.commit()
    return changed


def _error_text(response: dict) -> str:
    """Readable error message out of the raw provider body."""
    body = response.get("response")
    if not body:
        return ""
    body = str(body)
    try:
        payload = json.loads(body)
        if isinstance(payload, list) and payload:
            payload = payload[0]
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
    except ValueError:
        pass
    return body[:500]


def _error_context(response: dict) -> tuple[str, dict]:
    """Return the user-facing error and structured provider metadata."""
    body = response.get("response")
    if not body:
        return _error_text(response), {}
    try:
        payload = json.loads(body) if isinstance(body, str) else body
    except (TypeError, ValueError):
        return _error_text(response), {}
    if isinstance(payload, list) and payload:
        payload = payload[0]
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return _error_text(response), {}
    return str(error.get("message") or _error_text(response)), error


def _is_model_quota(context: str, details: dict) -> bool:
    """Detect model-scoped quotas from provider fields and message formats."""
    normalized = re.sub(r"[^a-z0-9]+", "", context.lower())
    if "permodel" in normalized or "modelper" in normalized:
        return True
    details_text = json.dumps(details, ensure_ascii=True).lower()
    if re.search(r"[\"']model[\"']\s*:", details_text):
        return True
    return bool(re.search(r"\bmodel\s*(?:[:=]|is)\s*[\"']?[\w./-]+", context, re.I))


def _redact_log_value(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Redact credential-bearing headers and known secret values before logging."""
    sensitive_names = {"authorization", "cookie", "set-cookie", "x-api-key", "api-key"}
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in sensitive_names
            else _redact_log_value(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_log_value(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def _retry_after(response: dict) -> Optional[float]:
    for key, value in (response.get("headers") or {}).items():
        if key.lower() == "retry-after":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _provider_retry_delay(context: str, details: dict) -> Optional[float]:
    """Read provider RetryInfo durations when Retry-After is not a header."""
    candidates: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in {"retrydelay", "retry_after"} and isinstance(item, str):
                    candidates.append(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(details)
    retry_message = re.search(
        r"\bretry\s+(?:in|after)\s+((?:\d+(?:\.\d+)?\s*[hms]\s*)+)",
        context,
        re.I,
    )
    if retry_message:
        candidates.append(retry_message.group(1))

    for candidate in candidates:
        parts = re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", candidate.lower())
        if parts:
            factors = {"h": 3600, "m": 60, "s": 1}
            return sum(float(amount) * factors[unit] for amount, unit in parts)
    return None


def parse_api_response(response: dict) -> dict:
    """Static parser. Maps a raw HTTP result onto one of the recovery actions."""
    if not isinstance(response, dict):
        return {"action": "UNKNOWN", "reason": "Invalid API response", "block_seconds": None}

    status = response.get("status_code")
    if response.get("success") is True or status == 200:
        return {"action": "SUCCESS", "reason": None, "block_seconds": None}

    reason, provider_details = _error_context(response)
    reason = reason or None
    error = " ".join((reason or "", json.dumps(provider_details, ensure_ascii=True))).lower()
    retry_after = _retry_after(response) or _provider_retry_delay(reason or "", provider_details)

    if status in (400, 422) and _is_tool_compat_error(error):
        return {
            "action": "SKIP_MODEL_THIS_REQUEST",
            "reason": reason or "Tool-call compatibility error (missing thought_signature)",
            "block_seconds": None,
        }

    if status == 429:
        model_scoped = _is_model_quota(error, provider_details)
        if model_scoped:
            if re.search(r"\b(day|daily|tpd|rpd)\b|perday|per_day", error):
                return {
                    "action": "COOLDOWN_MODEL_DAY",
                    "reason": "Model daily quota exceeded",
                    "block_seconds": retry_after or DAY_SECONDS,
                }
            return {
                "action": "COOLDOWN_MODEL_MINUTE",
                "reason": "Model rate limit exceeded",
                "block_seconds": retry_after or MINUTE_SECONDS,
            }

        if re.search(r"\b(tpd|tokens?\s*(per|/)\s*day|tokens?\s*daily|rpd|requests?\s*(per|/)\s*day|requests?\s*daily|daily|quota)\b", error):
            return {
                "action": "COOLDOWN_API_KEY_DAY",
                "reason": "TPD/RPD limit exceeded",
                "block_seconds": retry_after or DAY_SECONDS,
            }
        if re.search(r"\b(tpm|tokens?\s*(per|/)\s*minute)\b", error):
            return {
                "action": "COOLDOWN_API_KEY_MINUTE",
                "reason": "TPM limit exceeded",
                "block_seconds": retry_after or MINUTE_SECONDS,
            }
        if re.search(r"\b(rpm|requests?\s*(per|/)\s*minute)\b", error):
            return {
                "action": "COOLDOWN_API_KEY_MINUTE",
                "reason": "RPM limit exceeded",
                "block_seconds": retry_after or MINUTE_SECONDS,
            }
        retry_after = retry_after or MINUTE_SECONDS
        if retry_after >= DAY_SECONDS:
            return {
                "action": "COOLDOWN_API_KEY_DAY",
                "reason": "Rate limit exceeded",
                "block_seconds": retry_after,
            }
        return {
            "action": "COOLDOWN_API_KEY_MINUTE",
            "reason": "Rate limit exceeded",
            "block_seconds": retry_after,
        }

    if status in (401, 402, 403):
        return {
            "action": "DISABLE_API_KEY",
            "reason": reason or "API key invalid / forbidden",
            "block_seconds": None,
        }

    if status == 404:
        model_missing = re.search(
            r"\bmodel\b.{0,100}\b(?:not found|does not exist|doesn't exist|unknown model|not available|no access)\b",
            error,
        )
        if model_missing:
            return {
                "action": "DISABLE_MODEL",
                "reason": reason or "Model not found",
                "block_seconds": None,
            }
        return {
            "action": "COOLDOWN_PROVIDER_MINUTE",
            "reason": reason or "API endpoint returned 404",
            "block_seconds": MINUTE_SECONDS,
        }

    if status == 413:
        return {
            "action": "COOLDOWN_MODEL_MINUTE",
            "reason": reason or "Request too large / TPM limit",
            "block_seconds": MINUTE_SECONDS,
        }

    if status == 503:
        return {
            "action": "COOLDOWN_MODEL_MINUTE",
            "reason": reason or "Model temporarily unavailable",
            "block_seconds": MINUTE_SECONDS,
        }

    if status in (500, 502, 504, 408) or status is None:
        return {
            "action": "COOLDOWN_PROVIDER_MINUTE",
            "reason": reason or "Provider server error / timeout",
            "block_seconds": MINUTE_SECONDS,
        }

    return {
        "action": "UNKNOWN",
        "reason": reason or f"HTTP {status}",
        "block_seconds": None,
    }


def _action_payload(choice: str, reason: Optional[str]) -> dict:
    mapping = {
        "DISABLE_PROVIDER": ("DISABLE_PROVIDER", None),
        "COOLDOWN_PROVIDER_MINUTE": ("COOLDOWN_PROVIDER_MINUTE", MINUTE_SECONDS),
        "DISABLE_MODEL": ("DISABLE_MODEL", None),
        "COOLDOWN_MODEL_MINUTE": ("COOLDOWN_MODEL_MINUTE", MINUTE_SECONDS),
        "COOLDOWN_MODEL_DAY": ("COOLDOWN_MODEL_DAY", DAY_SECONDS),
        "DISABLE_API_KEY": ("DISABLE_API_KEY", None),
        "COOLDOWN_API_KEY_MINUTE": ("COOLDOWN_API_KEY_MINUTE", MINUTE_SECONDS),
        "COOLDOWN_API_KEY_DAY": ("COOLDOWN_API_KEY_DAY", DAY_SECONDS),
    }
    action, seconds = mapping.get(choice, ("UNKNOWN", None))
    return {"action": action, "reason": reason, "block_seconds": seconds}


def decide_with_laya(response: dict) -> dict:
    """Ask Laya to pick one of the recovery actions. Falls back to static parser."""
    try:
        from laya import Router
    except ImportError:
        return parse_api_response(response)

    state = {
        "response": _error_text(response),
    }
    questions = {
        "action": {
            "type": "choice",
            "instructions": (
                "Choose exactly one recovery action for this failed LLM API call. "
                "Use a one-minute API cooldown for per-minute rate limits (RPM/TPM). "
                "Use a one-day API cooldown for daily quotas (RPD/TPD). "
                "Disable the API key for auth or permission failures. "
                "Disable a model only when it does not exist (404), never for a 400/422 request-format error such as a missing thought_signature. "
                "Cooldown the model for one minute when the model itself is temporarily unavailable or experiencing high demand. "
                "Cooldown the provider for one minute on provider-wide server failures or the timeout error. "
                "Disable the provider only when the provider account is unusable."
            ),
            "criteria": {
                "DISABLE_PROVIDER": "Provider account is unusable and should be turned off",
                "COOLDOWN_PROVIDER_MINUTE": "Provider-wide outage or server error or the timeout error; cool down for one minute",
                "DISABLE_MODEL": "This model is missing, rejected, or permanently unusable",
                "COOLDOWN_MODEL_MINUTE": "This model is temporarily unavailable cool down about one minute",
                "DISABLE_API_KEY": "API key is invalid, unpaid, or forbidden",
                "COOLDOWN_API_KEY_MINUTE": "Per-minute rate limit (RPM or TPM); cool down about one minute",
                "COOLDOWN_API_KEY_DAY": "Daily quota (RPD or TPD); cool down for one day",
            },
        }
    }
    try:
        result = Router().predict(state, questions)
        choice = result["answers"]["action"]["choice"]
    except Exception:
        return parse_api_response(response)

    if choice not in LAYA_ACTIONS:
        return parse_api_response(response)

    status = response.get("status_code")
    if (status is None or status in TRANSIENT_STATUSES) and choice.startswith("DISABLE"):
        return parse_api_response(response)

    if status in (400, 422) and choice == "DISABLE_MODEL":
        return {
            "action": "SKIP_MODEL_THIS_REQUEST",
            "reason": _error_text(response) or "Tool-call compatibility error (missing thought_signature)",
            "block_seconds": None,
        }

    return _action_payload(choice, _error_text(response) or None)


def get_parser_mode() -> str:
    mode = (os.environ.get("PARSER_MODE") or "parse").strip().lower()
    if mode == "laya":
        return "laya"
    return "parse"


def get_waiting_type() -> str:
    raw = (os.environ.get("WAITING_TYPE") or "normal").strip().lower()
    if raw in ("true", "1", "yes", "run_anyhow", "run-anyhow", "anyhow"):
        return "run_anyhow"
    return "normal"


def decide_action(response: dict) -> dict:
    parsed = parse_api_response(response)
    if get_parser_mode() != "laya" or parsed.get("action") != "UNKNOWN":
        return parsed
    return decide_with_laya(response)


def update_api_database(
    db_path: str,
    provider_id: int,
    model_id: int,
    api_key_id: int,
    parsed_response: dict,
) -> dict:
    action = parsed_response.get("action")
    reason = parsed_response.get("reason")
    if not action or action in ("SUCCESS", "UNKNOWN"):
        return {"updated": False, "action": action, "reason": reason}

    block_seconds = parsed_response.get("block_seconds") or MINUTE_SECONDS
    now = datetime.now()
    now_string = now.isoformat()
    cooldown_until = (now + timedelta(seconds=block_seconds)).isoformat()

    with get_connection(db_path) as conn:
        if action in ("COOLDOWN_API_KEY_MINUTE", "COOLDOWN_API_KEY_DAY"):
            conn.execute(
                """UPDATE api_keys
                   SET status = 'cooldown', rate_limit = ?, disabled_reason = ?, last_modify = ?
                   WHERE id = ?""",
                (cooldown_until, reason, now_string, api_key_id),
            )
        elif action == "DISABLE_API_KEY":
            conn.execute(
                """UPDATE api_keys
                   SET status = 'disabled', rate_limit = NULL, disabled_reason = ?, last_modify = ?
                   WHERE id = ?""",
                (reason, now_string, api_key_id),
            )
        elif action == "DISABLE_MODEL":
            conn.execute(
                """UPDATE models
                   SET status = 'disabled', rate_limit = NULL, disabled_reason = ?, last_modify = ?
                   WHERE id = ?""",
                (reason, now_string, model_id),
            )
        elif action in ("COOLDOWN_MODEL_MINUTE", "COOLDOWN_MODEL_DAY"):
            conn.execute(
                """UPDATE models
                   SET status = 'cooldown', rate_limit = ?, disabled_reason = ?, last_modify = ?
                   WHERE id = ?""",
                (cooldown_until, reason, now_string, model_id),
            )
        elif action == "COOLDOWN_PROVIDER_MINUTE":
            conn.execute(
                """UPDATE providers
                   SET status = 'cooldown', rate_limit = ?, last_modify = ?
                   WHERE id = ?""",
                (cooldown_until, now_string, provider_id),
            )
        elif action == "DISABLE_PROVIDER":
            conn.execute(
                """UPDATE providers
                   SET status = 'disabled', rate_limit = NULL, last_modify = ?
                   WHERE id = ?""",
                (now_string, provider_id),
            )
        else:
            return {"updated": False, "action": action, "reason": reason}
        conn.commit()

    return {"updated": True, "action": action, "reason": reason}


def resolve_api_key_value(env_key_name: str) -> Optional[str]:
    val = os.environ.get(env_key_name)
    if val and val.strip():
        return val.strip()
    if env_key_name.startswith("API_KEY_"):
        alt = "LLM_" + env_key_name
        val = os.environ.get(alt)
        if val and val.strip():
            return val.strip()
    if env_key_name.startswith("LLM_API_KEY_"):
        alt = env_key_name[4:]
        val = os.environ.get(alt)
        if val and val.strip():
            return val.strip()
    return None


def find_best_api(
    db_path: str = DB_FILE,
    exclude_key_ids: Optional[Set[int]] = None,
    exclude_model_ids: Optional[Set[int]] = None,
    exclude_provider_ids: Optional[Set[int]] = None,
    exclude_combinations: Optional[Set[tuple]] = None,
    target_provider: Optional[str] = None,
    target_model: Optional[str] = None,
    target_key_name: Optional[str] = None,
) -> dict:
    db_path = resolve_db_path(db_path)
    reactivate_expired_cooldowns(db_path)
    update_api_keys(db_path)

    exclude_key_ids = exclude_key_ids or set()
    exclude_model_ids = exclude_model_ids or set()
    exclude_provider_ids = exclude_provider_ids or set()
    exclude_combinations = exclude_combinations or set()

    where_clauses = [
        "p.status = 'active'",
        "m.status = 'active'",
        "k.status = 'active'",
    ]
    params: List[Any] = []

    if target_provider:
        where_clauses.append("LOWER(p.name) = LOWER(?)")
        params.append(target_provider)

    if target_model:
        where_clauses.append("LOWER(m.name) = LOWER(?)")
        params.append(target_model)

    if target_key_name:
        where_clauses.append("LOWER(k.unique_name) = LOWER(?)")
        params.append(target_key_name)

    query = f"""
        SELECT
            p.id AS provider_id, p.name AS provider_name, p.base_url AS provider_url,
            m.id AS model_id, m.name AS model, m.model_size,
            k.id AS api_key_id, k.unique_name AS key_name, k.env_key AS api_key_env
        FROM models m
        JOIN providers p ON m.provider_id = p.id
        JOIN api_keys k ON k.provider_id = p.id
        WHERE {" AND ".join(where_clauses)}
        ORDER BY
            CAST(m.model_size AS REAL) DESC,
            m.id DESC
    """

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

        for row in rows:
            p_id = row["provider_id"]
            m_id = row["model_id"]
            k_id = row["api_key_id"]
            if (
                p_id in exclude_provider_ids
                or m_id in exclude_model_ids
                or k_id in exclude_key_ids
                or (p_id, m_id, k_id) in exclude_combinations
            ):
                continue

            api_key_val = resolve_api_key_value(row["api_key_env"])
            if not api_key_val:
                conn.execute(
                    "UPDATE api_keys SET status = 'disabled', disabled_reason = 'missing_env_var' WHERE id = ?",
                    (k_id,),
                )
                conn.commit()
                continue

            return {
                "provider_id": p_id,
                "provider_name": row["provider_name"],
                "model_id": m_id,
                "api_key_id": k_id,
                "provider_url": row["provider_url"],
                "model": row["model"],
                "key_name": row["key_name"],
                "api_key_env": row["api_key_env"],
                "api_key": api_key_val,
            }

    return {"error": "No active provider/model/key combination found in database."}


def earliest_cooldown_wait(db_path: str = DB_FILE) -> Optional[float]:
    """Seconds until soonest cooldown ends. 0 if one is due. None if nothing cooling down."""
    db_path = resolve_db_path(db_path)
    now = datetime.now()
    soonest: Optional[datetime] = None
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT rate_limit FROM api_keys
             WHERE status = 'cooldown' AND rate_limit IS NOT NULL
            UNION ALL
            SELECT rate_limit FROM providers
             WHERE status = 'cooldown' AND rate_limit IS NOT NULL
            UNION ALL
            SELECT rate_limit FROM models
             WHERE status = 'cooldown' AND rate_limit IS NOT NULL
            """
        ).fetchall()
    for row in rows:
        expiry = _parse_ts(row["rate_limit"])
        if expiry is None:
            continue
        if soonest is None or expiry < soonest:
            soonest = expiry
    if soonest is None:
        return None
    return max(0.0, (soonest - now).total_seconds())


def waiting_node(db_path: str = DB_FILE) -> str:
    """
    Called when find_best_api finds nothing active.
    WAITING_TYPE=normal      -> fail immediately
    WAITING_TYPE=run_anyhow  -> wait until earliest cooldown expires, then retry
    """
    if get_waiting_type() != "run_anyhow":
        return "fail"

    wait_seconds = earliest_cooldown_wait(db_path)
    if wait_seconds is None:
        return "fail"

    if wait_seconds > 0:
        time.sleep(wait_seconds + 0.05)
    return "retry"


def _prepare_messages_for_provider(
    messages: List[Dict[str, Any]],
    url: str,
    model: str,
) -> List[Dict[str, Any]]:
    is_gemini = _is_gemini(url, model)
    is_gemini_3_or_later = bool(re.search(r"gemini-(?:[3-9]|\d{2,})", model, re.I))
    prepared = []

    for message in messages:
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        if (
            not isinstance(message, dict)
            or message.get("role") != "assistant"
            or not isinstance(tool_calls, list)
        ):
            prepared.append(message)
            continue

        copied_message = dict(message)
        copied_calls = [dict(call) if isinstance(call, dict) else call for call in tool_calls]
        if not is_gemini:
            for call in copied_calls:
                if isinstance(call, dict):
                    call.pop("extra_content", None)
        elif is_gemini_3_or_later:
            has_signature = any(
                isinstance(call, dict)
                and isinstance(call.get("extra_content"), dict)
                and isinstance(call["extra_content"].get("google"), dict)
                and call["extra_content"]["google"].get("thought_signature")
                for call in copied_calls
            )
            if not has_signature:
                first_call = next((call for call in copied_calls if isinstance(call, dict)), None)
                if first_call is not None:
                    first_call["extra_content"] = {
                        "google": {"thought_signature": GEMINI_DUMMY_SIGNATURE}
                    }

        copied_message["tool_calls"] = copied_calls
        prepared.append(copied_message)

    return prepared


def _format_tools(tools_input: Any) -> Optional[List[Dict[str, Any]]]:
    """Ensure tools are in OpenAI compatible format."""
    if not tools_input:
        return None
    if isinstance(tools_input, list):
        formatted = []
        for t in tools_input:
            if hasattr(t, "name") and hasattr(t, "parameters"):
                # ToolSpec instance
                formatted.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": getattr(t, "description", "") or "",
                        "parameters": t.parameters,
                    }
                })
            elif isinstance(t, dict):
                if t.get("type") == "function" and "function" in t:
                    formatted.append(t)
                elif "name" in t:
                    formatted.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name", ""),
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                        }
                    })
                else:
                    formatted.append(t)
            else:
                formatted.append(t)
        return formatted
    return None


def call_openai_compatible(
    data: dict,
    url: str,
    provider_label: str,
    api: str,
    model: str,
    temperature: Optional[float] = None,
    interactive_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Plain HTTP call to an OpenAI-compatible endpoint with parsed output and tool calling.
    """
    messages: List[Dict[str, Any]] = data.get("messages") or []
    if not messages:
        if data.get("system_prompt"):
            messages.append({"role": "system", "content": data["system_prompt"]})
        messages.extend(data.get("memory") or [])
        user_prompt = data.get("user_prompt") or data.get("prompt")
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})

    if temperature is None:
        temperature = data.get("temperature", 0.7)

    messages = _prepare_messages_for_provider(messages, url, model)
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": data.get("max_tokens", 8192),
    }

    tools_raw = data.get("tools") or data.get("tool_list")
    tools = _format_tools(tools_raw)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    timeout = data.get("timeout", 60)
    api_call_id = active_api_call_id.get()
    request_started_at = datetime.now().isoformat(timespec="milliseconds")
    request_start = time.perf_counter()
    if api_call_id is not None:
        update_api_call(
            api_call_id=api_call_id,
            payload=payload,
            timestamp=request_started_at,
            db_path=db_path,
        )
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except Exception as e:
        if api_call_id is not None:
            update_api_call(
                api_call_id=api_call_id,
                request_status="Failed",
                response=str(e),
                duration_seconds=time.perf_counter() - request_start,
                db_path=db_path,
            )
        return {
            "success": False,
            "status": False,
            "status_code": None,
            "response": str(e),
            "headers": {},
            "error": str(e),
            "tool_calls": None,
        }

    headers_dict = dict(response.headers)
    body_text = response.text or ""

    if response.ok:
        try:
            body_json = response.json()
            choice = (body_json.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            raw_tool_calls = message.get("tool_calls") or []

            parsed_tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function") or {}
                args_raw = fn.get("arguments", "{}")
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw)
                    except Exception:
                        args = {"_raw": args_raw}
                elif isinstance(args_raw, dict):
                    args = args_raw
                else:
                    args = {"_raw": str(args_raw)}
                parsed_tool_call = {
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": args,
                }
                if "extra_content" in tc:
                    parsed_tool_call["extra_content"] = tc["extra_content"]
                parsed_tool_calls.append(parsed_tool_call)

            response_text = content if (content or not parsed_tool_calls) else None
            if api_call_id is not None:
                update_api_call(
                    api_call_id=api_call_id,
                    request_status="Success",
                    final_response=False,
                    response=(
                        json.dumps(parsed_tool_calls, ensure_ascii=False)
                        if parsed_tool_calls
                        else response_text
                    ),
                    duration_seconds=time.perf_counter() - request_start,
                    db_path=db_path,
                )
            return {
                "success": True,
                "status": True,
                "status_code": response.status_code,
                "response": response_text,
                "tool_calls": parsed_tool_calls if parsed_tool_calls else None,
                "raw_response": body_text,
                "headers": headers_dict,
                "error": None,
            }
        except Exception as e:
            if api_call_id is not None:
                update_api_call(
                    api_call_id=api_call_id,
                    request_status="Failed",
                    response=body_text,
                    duration_seconds=time.perf_counter() - request_start,
                    db_path=db_path,
                )
            return {
                "success": False,
                "status": False,
                "status_code": response.status_code,
                "response": body_text,
                "headers": headers_dict,
                "error": f"Failed to parse provider response JSON: {e}",
                "tool_calls": None,
            }

    if api_call_id is not None:
        update_api_call(
            api_call_id=api_call_id,
            request_status="Failed",
            response=body_text,
            duration_seconds=time.perf_counter() - request_start,
            db_path=db_path,
        )
    return {
        "success": False,
        "status": False,
        "status_code": response.status_code,
        "response": body_text,
        "headers": headers_dict,
        "error": _error_text({"response": body_text}),
        "tool_calls": None,
    }


def api_caller(
    data: dict,
    db_path: Optional[str] = None,
    exclude_combinations: Optional[Set[tuple]] = None,
    target_provider: Optional[str] = None,
    target_model: Optional[str] = None,
    target_key_name: Optional[str] = None,
) -> dict:
    resolved_db_path = resolve_db_path(db_path)
    seed_default_data(resolved_db_path)
    init_logging_schema(resolved_db_path)

    conversation_id = data.get("conversation_id") or active_conversation_id.get()
    if conversation_id is None:
        user_text = data.get("user_prompt") or data.get("prompt") or ""
        if not user_text:
            for message in reversed(data.get("messages") or []):
                if isinstance(message, dict) and message.get("role") == "user":
                    user_text = message.get("content") or ""
                    break
        title = (user_text[:80] if user_text else "API Session").strip() or "API Session"
        conversation_id = create_conversation(title=title, db_path=resolved_db_path)

    interaction_id = data.get("interactive_id") or active_interactive_id.get()
    owns_interaction = interaction_id is None
    if interaction_id is None:
        interaction_id = create_interactive(
            conversation_id=conversation_id,
            payload=data,
            db_path=resolved_db_path,
        )
    iteration_id = next_iteration_id(conversation_id, interaction_id, resolved_db_path)
    conversation_token = active_conversation_id.set(conversation_id)
    interaction_token = active_interactive_id.set(interaction_id)
    iteration_token = active_iteration_id.set(iteration_id)
    api_call_token = active_api_call_id.set(None)
    task_started_at = datetime.now().isoformat(timespec="milliseconds")
    task_start = time.perf_counter()
    try:
        return _api_caller_impl(
            data=data,
            db_path=resolved_db_path,
            exclude_combinations=exclude_combinations,
            target_provider=target_provider,
            target_model=target_model,
            target_key_name=target_key_name,
            mark_final=owns_interaction,
        )
    finally:
        complete_api_task(
            conversation_id=int(conversation_id),
            interaction_id=int(interaction_id),
            task_id=iteration_id,
            started_at=task_started_at,
            duration_seconds=time.perf_counter() - task_start,
            db_path=resolved_db_path,
        )
        active_api_call_id.reset(api_call_token)
        active_iteration_id.reset(iteration_token)
        active_interactive_id.reset(interaction_token)
        active_conversation_id.reset(conversation_token)


def _api_caller_impl(
    data: dict,
    db_path: Optional[str] = None,
    exclude_combinations: Optional[Set[tuple]] = None,
    target_provider: Optional[str] = None,
    target_model: Optional[str] = None,
    target_key_name: Optional[str] = None,
    mark_final: bool = True,
) -> dict:
    """
    Main API caller router. Backed by SQLite DB.
    Logs every provider attempt in the flat API_Call_Log table.
    """
    start_time = time.perf_counter()
    db_path = resolve_db_path(db_path)

    try:
        max_iterations = int(os.environ.get("MAX_ITERATIONS", 25))
    except ValueError:
        max_iterations = 25

    conv_id = active_conversation_id.get()
    inter_id = active_interactive_id.get()
    iteration_id = active_iteration_id.get()
    if conv_id is None or inter_id is None or iteration_id is None:
        raise RuntimeError("API call logging context was not initialized.")

    exclude_keys: Set[int] = set()
    exclude_models: Set[int] = set()
    exclude_providers: Set[int] = set()
    exclude_combinations = set(exclude_combinations or ())
    iterations: List[Dict[str, Any]] = []
    iteration_count = 0
    interaction_prompt = None
    for message in reversed(data.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "user":
            interaction_prompt = message.get("content")
            break
    if not interaction_prompt:
        interaction_prompt = data.get("user_prompt") or data.get("prompt")
    if interaction_prompt is not None and not isinstance(interaction_prompt, str):
        interaction_prompt = json.dumps(interaction_prompt, ensure_ascii=False, default=str)

    def finish(result: dict) -> dict:
        result["conversation_id"] = conv_id
        result["interactive_id"] = inter_id
        result["iteration_id"] = iteration_id
        return result

    def failure(message: str) -> dict:
        total_duration_ms = int((time.perf_counter() - start_time) * 1000)
        return {
            "success": False,
            "status": False,
            "status_code": None,
            "response": None,
            "tool_calls": None,
            "error": message,
            "headers": {},
            "api_iterations": iterations,
            "total_attempts": iteration_count,
            "total_duration_ms": total_duration_ms,
            "chosen": None,
        }

    while iteration_count < max_iterations:
        t_iter_start = time.perf_counter()
        api = find_best_api(
            db_path=db_path,
            exclude_key_ids=exclude_keys,
            exclude_model_ids=exclude_models,
            exclude_provider_ids=exclude_providers,
            exclude_combinations=exclude_combinations,
            target_provider=target_provider if iteration_count == 0 else None,
            target_model=target_model if iteration_count == 0 else None,
            target_key_name=target_key_name if iteration_count == 0 else None,
        )

        api_call_id = create_api_call(
            conversation_id=conv_id,
            interaction_id=inter_id,
            iteration_id=iteration_id,
            url=api.get("provider_url"),
            model=api.get("model"),
            api_name=api.get("key_name") or "unknown",
            interaction_prompt=interaction_prompt,
            db_path=db_path,
        )
        active_api_call_id.set(api_call_id)

        if "error" in api:
            t_wait = time.perf_counter()
            decision = waiting_node(db_path)
            wait_dur = time.perf_counter() - t_wait
            log_wait(
                iteration_id=iteration_id,
                time_to_be_waited=wait_dur,
                db_path=db_path,
            )
            update_api_call(
                api_call_id=api_call_id,
                request_status="Failed",
                response=api["error"],
                duration_seconds=time.perf_counter() - t_iter_start,
                db_path=db_path,
            )
            active_api_call_id.set(None)
            if decision == "retry":
                exclude_keys.clear()
                exclude_models.clear()
                exclude_providers.clear()
                continue

            update_interactive(
                interactive_id=inter_id,
                response_status="Not_Final",
                actual_response=api["error"],
                iteration_no=iteration_count,
                db_path=db_path,
            )
            return finish(failure(api["error"]))

        iteration_count += 1
        t_call = time.perf_counter()
        response = call_openai_compatible(
            data=data,
            url=api["provider_url"],
            provider_label=api["provider_name"],
            api=api["api_key"],
            model=api["model"],
            interactive_id=inter_id,
            db_path=db_path,
        )

        iter_info = {
            "n": iteration_count,
            "provider": api["provider_name"],
            "model": api["model"],
            "api_key_name": api["key_name"],
            "success": response.get("success", False),
            "duration_ms": int((time.perf_counter() - t_call) * 1000),
            "provider_id": api["provider_id"],
            "model_id": api["model_id"],
            "api_key_id": api["api_key_id"],
            "iteration_id": iteration_id,
            "api_call_id": api_call_id,
        }
        iterations.append(iter_info)

        if response.get("success"):
            total_duration_ms = int((time.perf_counter() - start_time) * 1000)
            iter_info["response"] = response.get("response")
            iter_info["tool_calls"] = response.get("tool_calls")

            actual_resp = response.get("response")
            if not actual_resp and response.get("tool_calls"):
                try:
                    actual_resp = json.dumps(response.get("tool_calls"), ensure_ascii=False)
                except Exception:
                    actual_resp = str(response.get("tool_calls"))

            active_api_call_id.set(None)
            if mark_final:
                update_interactive(
                    interactive_id=inter_id,
                    response_status="Final",
                    actual_response=actual_resp,
                    iteration_no=iteration_count,
                    db_path=db_path,
                )

            return finish({
                "success": True,
                "status": True,
                "status_code": response.get("status_code", 200),
                "response": response.get("response"),
                "tool_calls": response.get("tool_calls"),
                "raw_response": response.get("raw_response", response.get("response")),
                "headers": response.get("headers", {}),
                "error": None,
                "api_iterations": iterations,
                "total_attempts": iteration_count,
                "total_duration_ms": total_duration_ms,
                "chosen": {
                    "provider": api["provider_name"],
                    "model": api["model"],
                    "key_name": api["key_name"],
                    "provider_id": api["provider_id"],
                    "model_id": api["model_id"],
                    "api_key_id": api["api_key_id"],
                },
            })

        t_decide = time.perf_counter()
        parsed = decide_action(response)
        decide_dur = time.perf_counter() - t_decide

        mode_str = "LAYA" if get_parser_mode() == "laya" else "Parser"
        req_str = _error_text(response) or str(response.get("error") or response.get("response") or "Unknown error")
        act_str = parsed.get("action") or str(parsed)

        log_decide(
            iteration_id=iteration_id,
            mode=mode_str,
            request=req_str,
            action=act_str,
            time_take_to_process=decide_dur,
            db_path=db_path,
        )

        update_api_call(
            api_call_id=api_call_id,
            request_status="Failed",
            response=req_str,
            duration_seconds=time.perf_counter() - t_call,
            db_path=db_path,
        )
        active_api_call_id.set(None)

        update_api_database(
            db_path=db_path,
            provider_id=api["provider_id"],
            model_id=api["model_id"],
            api_key_id=api["api_key_id"],
            parsed_response=parsed,
        )

        action = parsed.get("action")
        if action in ("COOLDOWN_API_KEY_MINUTE", "COOLDOWN_API_KEY_DAY", "DISABLE_API_KEY"):
            exclude_keys.add(api["api_key_id"])
        elif action in (
            "DISABLE_MODEL",
            "COOLDOWN_MODEL_MINUTE",
            "COOLDOWN_MODEL_DAY",
            "SKIP_MODEL_THIS_REQUEST",
        ):
            exclude_models.add(api["model_id"])
        elif action in ("COOLDOWN_PROVIDER_MINUTE", "DISABLE_PROVIDER"):
            exclude_providers.add(api["provider_id"])
        elif action == "UNKNOWN":
            pass

    update_interactive(
        interactive_id=inter_id,
        response_status="Not_Final",
        actual_response="All API attempts failed. Exceeded max iterations.",
        iteration_no=iteration_count,
        db_path=db_path,
    )
    return finish(failure("All API attempts failed. Exceeded max iterations."))


if __name__ == "__main__":
    resp = api_caller({"user_prompt": "Hello!"})
    print("Direct api_caller test result:", resp.get("success"), resp.get("response"))
