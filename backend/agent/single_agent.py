import sys
import json
import logging
import re
import time
from typing import Optional, Any

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    SystemMessage,
    HumanMessage,
    ToolMessage,
)

from backend.agent.brain_langchain import BrainChatModel
from backend.agent.brain_langchain.api_manager.sqlite_logger import (
    conversation_scope,
    interactive_scope,
    update_interactive,
    active_conversation_id,
    active_interactive_id,
    create_tool_execution,
    update_tool_execution,
)
from backend.agent.agent_profiles import DEFAULT_AGENT_SYSTEM_PROMPT
from backend.tools.features import get_langchain_tools, refresh_tools_registry


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

KEEP_LAST_TURNS = 6
EARLIER_SUMMARY_MARKER = "[Earlier session summary]:"
INCOMPLETE_TASK_PREFIX = "Task not completed:"
ACTION_REQUEST_PATTERN = re.compile(
    r"\b(add|build|create|implement|modify|update|fix|write|install|configure|set\s+up|"
    r"setup|send|run|execute|test|deploy|delete|remove|change|refactor|finish|complete|continue|make)\b",
    re.IGNORECASE,
)
QUESTION_ONLY_PREFIX = re.compile(
    r"^\s*(how\s+(do|can|would)\s+i|what\s+is|why\s+does|explain|tell\s+me)\b",
    re.IGNORECASE,
)
BLOCKER_PATTERN = re.compile(
    r"\bblocked\s+(?:by|until|on)\b|\b(?:cannot|can't|unable to|need you to|please provide|requires? (?:your )?"
    r"(?:permission|authorization|consent|credentials?))\b",
    re.IGNORECASE,
)
PROGRESS_UPDATE_PATTERN = re.compile(
    r"\b(next steps?|plan(?:ned)?|will (?:now|then|need|continue|finish)|need to|"
    r"still need|not yet|not completed|haven't|hasn't|remaining work)\b",
    re.IGNORECASE,
)
OBSERVATION_TOOL_NAMES = {
    "read_file",
    "list_dir",
    "search_files",
    "search_code",
    "get_file_contents",
}
MUTATING_COMMAND_PATTERN = re.compile(
    r"\b(pip\s+install|npm\s+install|New-Item|Set-Content|Add-Content|Remove-Item|"
    r"Copy-Item|Move-Item|git\s+apply|git\s+commit)\b|"
    r"(?:open|Path)\s*\([^)]*['\"](?:w|a|x)",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def _is_action_request(prompt: str) -> bool:
    if QUESTION_ONLY_PREFIX.search(prompt):
        return False
    return bool(ACTION_REQUEST_PATTERN.search(prompt))


def _tool_succeeded(output: Any) -> bool:
    if isinstance(output, dict):
        return output.get("success") is not False
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return True
        if isinstance(parsed, dict):
            return parsed.get("success") is not False
    return True


def _is_meaningful_action_tool(name: str, args: Any) -> bool:
    if name in OBSERVATION_TOOL_NAMES:
        return False
    if name == "execute_command":
        command = args.get("command", "") if isinstance(args, dict) else ""
        return bool(MUTATING_COMMAND_PATTERN.search(str(command)))
    return True


def _safe_content(msg) -> str:
    content = getattr(msg, "content", None)

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    return str(content)


def _group_into_turns(messages):
    turns = []
    i = 0

    while i < len(messages):
        msg = messages[i]

        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            group = [msg]
            i += 1

            while i < len(messages) and isinstance(messages[i], ToolMessage):
                group.append(messages[i])
                i += 1

            turns.append(group)
        else:
            turns.append([msg])
            i += 1

    return turns


def _extract_earlier_summaries(system_content: str):
    summaries = [
        summary.strip()
        for summary in re.findall(
            rf"{re.escape(EARLIER_SUMMARY_MARKER)}\s*(.*?)(?={re.escape(EARLIER_SUMMARY_MARKER)}|\Z)",
            system_content,
            flags=re.DOTALL,
        )
        if summary.strip()
    ]
    base_content = re.sub(
        rf"\s*{re.escape(EARLIER_SUMMARY_MARKER)}.*\Z",
        "",
        system_content,
        flags=re.DOTALL,
    ).rstrip()
    return base_content, summaries


def _summarize_turns(model, turn_groups, earlier_summaries=None):
    lines = []

    for summary in earlier_summaries or []:
        lines.append(f"Earlier summary: {summary}")

    for group in turn_groups:
        for msg in group:
            role = type(msg).__name__.replace("Message", "")
            text = _safe_content(msg)

            if text:
                lines.append(f"{role}: {text}")
            for tool_call in getattr(msg, "tool_calls", []) or []:
                name = tool_call.get("name", "unknown")
                args = json.dumps(tool_call.get("args", {}), ensure_ascii=False, default=str)
                lines.append(f"Tool call: {name}({args})")

    transcript = "\n".join(lines)

    if not transcript.strip():
        return ""

    try:
        response = model.invoke([
            HumanMessage(
                content=(
                    "Summarize the earlier part of this agent's working session in 3-5 sentences. "
                    "Keep concrete facts, file names, decisions and outcomes that are still needed. "
                    "Carry forward established facts from earlier summaries, reconcile them with newer "
                    "messages, and do not describe completed actions as pending unless later evidence "
                    "shows they remain unresolved.\n\n"
                    f"{transcript}"
                )
            )
        ])
        return _safe_content(response).strip()
    except Exception:
        logger.exception("Could not summarize conversation context.")
        return ""


def _trim_context(model, messages, keep_last_turns: int = KEEP_LAST_TURNS):
    if len(messages) < 3:
        return messages

    system_msg, first_human = messages[0], messages[1]
    rest_turns = _group_into_turns(messages[2:])

    if len(rest_turns) <= keep_last_turns:
        return messages

    middle = rest_turns[:-keep_last_turns]
    tail = rest_turns[-keep_last_turns:]
    system_content, earlier_summaries = _extract_earlier_summaries(_safe_content(system_msg))
    summary = _summarize_turns(model, middle, earlier_summaries)

    if summary:
        system_msg = SystemMessage(
            content=(
                f"{system_content}\n\n{EARLIER_SUMMARY_MARKER} {summary}"
                if system_content
                else f"{EARLIER_SUMMARY_MARKER} {summary}"
            )
        )

    trimmed = [system_msg, first_human]

    for group in tail:
        trimmed.extend(group)

    return trimmed


def call_agent(
    user_prompt: str,
    tools: list = None,
    max_turns: int = 20,
    verbose: bool = True,
    model: Optional[Any] = None,
    temperature: float = 0.2,
    buffer: int = 0,
    conversation_id: Optional[int] = None,
    history: Optional[list] = None,
    log_payload: Optional[dict] = None,
    process_started_at: Optional[float] = None,
    system_prompt_override: Optional[str] = None,
) -> str:
    with conversation_scope(title=user_prompt[:80], conversation_id=conversation_id) as conv_id:
        owns_interaction = active_interactive_id.get() is None
        payload = log_payload if log_payload is not None else {
            "user_prompt": user_prompt,
            "mode": "agent",
            "temperature": temperature,
            "max_turns": max_turns,
            "buffer": buffer,
            "conversation_id": conv_id,
            "messages": history or [],
        }
        with interactive_scope(conversation_id=conv_id, payload=payload) as inter_id:
            started_at = process_started_at if process_started_at is not None else time.perf_counter()
            try:
                final_text = _call_agent_impl(
                    user_prompt=user_prompt,
                    tools=tools,
                    max_turns=max_turns,
                    verbose=verbose,
                    model=model,
                    temperature=temperature,
                    buffer=buffer,
                    history=history,
                    system_prompt_override=system_prompt_override,
                )
            except Exception:
                update_interactive(
                    interactive_id=inter_id,
                    response_status="Not_Final",
                    duration_seconds=time.perf_counter() - started_at,
                )
                raise
            response_status = (
                "Not_Final"
                if final_text.startswith(INCOMPLETE_TASK_PREFIX)
                else "Final"
            )
            if owns_interaction:
                update_interactive(
                    interactive_id=inter_id,
                    response_status=response_status,
                    actual_response=final_text,
                    duration_seconds=time.perf_counter() - started_at,
                )
            return final_text


def _call_agent_impl(
    user_prompt: str,
    tools: list = None,
    max_turns: int = 20,
    verbose: bool = True,
    model: Optional[Any] = None,
    temperature: float = 0.2,
    buffer: int = 0,
    history: Optional[list] = None,
    system_prompt_override: Optional[str] = None,
) -> str:

    if tools is None:
        try:
            refresh_tools_registry()
        except Exception:
            pass

        tools = get_langchain_tools()

    tools_map = {tool.name: tool for tool in tools}

    if model is None:
        model = BrainChatModel(
            temperature=temperature,
            buffer=buffer,
        )

    system_prompt = DEFAULT_AGENT_SYSTEM_PROMPT
    if system_prompt_override is not None:
        system_prompt = system_prompt_override

    messages = [SystemMessage(content=system_prompt)]

    # Inject historical turns if provided
    if history:
        for item in history:
            role = (item.get("role") or "").lower()
            content = item.get("content") or ""
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role == "system":
                messages.append(SystemMessage(content=content))

    messages.append(HumanMessage(content=user_prompt))

    tools_changed = False
    bound_model = model.bind_tools(list(tools_map.values()))
    action_request = _is_action_request(user_prompt)
    successful_action_tools = 0
    execution_nudges = 0
    completion_check_attempts = 0
    incomplete_task = False

    for turn in range(1, max_turns + 1):
        if verbose:
            print(f"\nTurn {turn}/{max_turns} {'=' * 60}")


        if tools_changed:
            if verbose:
                print("Reloading tools...")
            try:
                new_tools = get_langchain_tools(force_reload=True)

                for tool in new_tools:
                    if tool.name not in tools_map:
                        tools_map[tool.name] = tool

                bound_model = model.bind_tools(list(tools_map.values()))
            except Exception:
                pass

            tools_changed = False

        messages = _trim_context(model, messages)

        try:
            response = bound_model.invoke(messages)
        except Exception as e:
            error = f"Error during model invoke: {e}"
            return f"{INCOMPLETE_TASK_PREFIX} {error}" if action_request else error

        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        additional = getattr(response, "additional_kwargs", {}) or {}
        task_id = additional.get("iteration_id")
        try:
            task_id = int(task_id) if task_id is not None else None
        except (TypeError, ValueError):
            task_id = None

        if not tool_calls:
            tool_calls = additional.get("tool_calls", [])

        if not tool_calls:
            final_text = _safe_content(response)
            if final_text.strip():
                if action_request and BLOCKER_PATTERN.search(final_text):
                    incomplete_task = True
                    return f"{INCOMPLETE_TASK_PREFIX} {final_text}"
                if action_request and successful_action_tools == 0:
                    if execution_nudges >= 3:
                        incomplete_task = True
                        return f"{INCOMPLETE_TASK_PREFIX} {final_text}"
                    execution_nudges += 1
                    if verbose:
                        print("Action request is still unfulfilled; asking the agent to execute it.")
                    messages.append(
                        HumanMessage(
                            content=(
                                "Do not finish with a plan or progress summary. The user asked you to perform an action. "
                                "No successful action/implementation tool call has completed that request yet. "
                                "Use the available tools now to make concrete progress. If a necessary credential, "
                                "permission, or confirmation is missing, verify what you can and explain that exact blocker."
                            )
                        )
                    )
                    continue
                if action_request and (
                    completion_check_attempts == 0
                    or PROGRESS_UPDATE_PATTERN.search(final_text)
                ):
                    if completion_check_attempts >= 3:
                        incomplete_task = True
                        return f"{INCOMPLETE_TASK_PREFIX} {final_text}"
                    is_completion_retry = completion_check_attempts > 0
                    completion_check_attempts += 1
                    if verbose:
                        print("Checking the requested outcomes before returning a final response.")
                    messages.append(
                        HumanMessage(
                            content=(
                                "Your last response described remaining or future work, so it is not a completion report. "
                                "Continue using tools to finish and verify those steps. Do not return another plan."
                                if is_completion_retry
                                else "Before you finish, verify every requirement in the user's original request against the "
                                "work and tool results in this conversation. If anything is missing, use tools to finish "
                                "and test it. If blocked, state the precise blocker and do not claim success."
                            )
                        )
                    )
                    continue
                return final_text
            if verbose:
                print("Warning: Received empty response without tool calls. Prompting model to continue...")
            messages.append(
                HumanMessage(
                    content="Your last response was empty. Please continue implementing the remaining requirements and complete the task."
                )
            )
            continue

        for i, tc in enumerate(tool_calls):
            if isinstance(tc, dict):
                name = tc.get("name") or tc.get("function", {}).get("name")
                args = (
                    tc.get("args")
                    or tc.get("function", {}).get("arguments")
                    or {}
                )
                tid = tc.get("id", f"call_{i}")

                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
            else:
                name = getattr(tc, "name", None)
                args = getattr(tc, "args", {}) or {}
                tid = getattr(tc, "id", f"call_{i}")

            conversation_id = active_conversation_id.get()
            interaction_id = active_interactive_id.get()
            execution_id = None
            tool_started_at = time.perf_counter()
            if conversation_id is not None and interaction_id is not None:
                try:
                    execution_id = create_tool_execution(
                        conversation_id=conversation_id,
                        interaction_id=interaction_id,
                        task_id=task_id,
                        name=str(name or "Unknown tool"),
                        parameters=args,
                        tool_call_id=str(tid) if tid is not None else None,
                    )
                except Exception:
                    logger.exception("Could not start logging tool execution %r.", name)

            tool_status = "Success"
            tool_error = None
            if name in tools_map:
                try:
                    output = tools_map[name].invoke(args)

                    if name == "create_tool":
                        tools_changed = True
                    if _is_meaningful_action_tool(str(name), args) and _tool_succeeded(output):
                        successful_action_tools += 1

                except Exception as e:
                    output = f"Error executing tool '{name}': {e}"
                    tool_status = "Failed"
                    tool_error = str(e)
            else:
                output = (
                    f"Tool '{name}' not found. "
                    f"Available: {list(tools_map.keys())}"
                )
                tool_status = "Failed"
                tool_error = output

            if execution_id is not None:
                try:
                    update_tool_execution(
                        execution_id=execution_id,
                        status=tool_status,
                        response=output,
                        error=tool_error,
                        duration_seconds=time.perf_counter() - tool_started_at,
                    )
                except Exception:
                    logger.exception("Could not finish logging tool execution %r.", name)

            messages.append(
                ToolMessage(
                    content=str(output),
                    tool_call_id=tid,
                    name=name,
                )
            )

    if action_request:
        incomplete_task = True

    messages = _trim_context(model, messages)

    try:
        wrap = model.invoke(
            messages
            + [
                HumanMessage(
                    content=(
                        "Turn limit reached. Do not claim that unfinished work is complete. "
                        "Summarize verified accomplishments, list what remains, and state any concrete blocker. "
                        "Clearly label the task incomplete if all requested outcomes were not verified."
                    )
                )
            ]
        )
        summary = _safe_content(wrap)
        return f"{INCOMPLETE_TASK_PREFIX} {summary}" if incomplete_task else summary
    except Exception:
        summary = _safe_content(messages[-1])
        return f"{INCOMPLETE_TASK_PREFIX} {summary}" if incomplete_task else summary