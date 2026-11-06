"""Plan, execute, and merge specialist work through Brain."""

import contextvars
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from ..brain import brain
from ..brain_types import ToolSpec
from ..api_manager.sqlite_logger import conversation_scope, interactive_scope
from .agents import AgentRegistry, AgentSpec, register_core_tools
from .config import OrchestrationConfig
from .observability import log_event
from .runner import AgentResult, BrainCallable, SubAgentRunner

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    id: str
    agent: str
    prompt: str
    depends_on: List[str]


class PlanError(ValueError):
    pass


class Orchestrator:
    def __init__(
        self,
        agents: AgentRegistry,
        runner: SubAgentRunner,
        config: Optional[OrchestrationConfig] = None,
        brain_callable: Optional[BrainCallable] = None,
    ):
        self.agents = agents
        self.runner = runner
        self.config = config or OrchestrationConfig.from_env()
        self.brain = brain_callable or brain
        registry = getattr(self.runner, "registry", None)
        if registry is not None:
            for agent in self.agents.all():
                register_core_tools(registry, agent.tool_scope, self.config)

    def run(self, user_prompt: str) -> Dict[str, Any]:
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("user_prompt must be a non-empty string.")
        with conversation_scope(title=f"Orchestration: {user_prompt[:60]}") as conversation_id:
            with interactive_scope(
                conversation_id=conversation_id,
                payload={"user_prompt": user_prompt, "mode": "tool-rag"},
            ):
                return self._run(user_prompt.strip())

    def _run(self, user_prompt: str) -> Dict[str, Any]:
        if self._is_trivial(user_prompt):
            final = self._brain_call(
                phase="direct_answer",
                system_prompt="Answer the user's simple request directly and concisely.",
                messages=[{"role": "user", "content": user_prompt}],
                tools=None,
                call_number=1,
            )
            text = self._response_text(final)
            status = (
                "ok"
                if text and not final.get("error_status") and final.get("api_success") is not False
                else "error"
            )
            log_event("orchestration_final", {"status": status, "path": "direct"})
            return {"status": status, "answer": text, "plan": [], "results": {}}

        plan = self._fast_path(user_prompt)
        failures: List[Dict[str, Any]] = []
        replans = 0
        if plan is None:
            while True:
                try:
                    request = (
                        user_prompt if replans == 0
                        else self._replan_prompt(user_prompt, {}, failures)
                    )
                    plan = self._make_plan(request, call_number=replans + 1)
                    break
                except PlanError as exc:
                    failures.append({"error": str(exc), "phase": "planning"})
                    if replans >= self.config.max_replans:
                        plan = []
                        break
                    replans += 1
        log_event("orchestration_plan", {"plan": [self._step_dict(item) for item in plan]})

        completed: Dict[str, Dict[str, Any]] = {}
        execution_count = 0

        while plan and execution_count < self.config.max_total_steps:
            try:
                self._validate_plan(
                    plan,
                    {
                        step_id for step_id, result in completed.items()
                        if result.get("status") == "ok"
                    },
                )
            except PlanError as exc:
                failures.append({"error": str(exc), "phase": "plan_validation"})
                if replans >= self.config.max_replans:
                    break
                replans += 1
                try:
                    plan = self._make_plan(
                        self._replan_prompt(user_prompt, completed, failures),
                        call_number=replans + 1,
                        available_dependencies={
                            step_id for step_id, result in completed.items()
                            if result.get("status") == "ok"
                        },
                    )
                except PlanError as replan_error:
                    failures.append({"error": str(replan_error), "phase": "replanning"})
                    break
                continue

            successful_ids = {
                step_id for step_id, result in completed.items()
                if result.get("status") == "ok"
            }
            pending = {step.id: step for step in plan if step.id not in successful_ids}
            execution_error = False
            while pending and execution_count < self.config.max_total_steps:
                ready = [
                    step for step in pending.values()
                    if all(
                        completed.get(dependency, {}).get("status") == "ok"
                        for dependency in step.depends_on
                    )
                ]
                if not ready:
                    failures.append({"error": "No executable step; dependency cycle or missing dependency."})
                    execution_error = True
                    break
                batch = ready[: self.config.parallelism]
                futures = {}
                with ThreadPoolExecutor(max_workers=self.config.parallelism) as pool:
                    for step in batch:
                        dependency_data = {
                            dependency: completed[dependency]
                            for dependency in step.depends_on
                        }
                        focused_prompt = self._self_contained_prompt(step, dependency_data)
                        context = contextvars.copy_context()
                        futures[pool.submit(
                            context.run,
                            self._execute_with_retry,
                            step,
                            focused_prompt,
                        )] = step
                    for future in as_completed(futures):
                        step = futures[future]
                        try:
                            result = future.result()
                        except Exception as exc:
                            logger.exception("Orchestration step %s raised unexpectedly.", step.id)
                            result = AgentResult("error", "", error=str(exc))
                        execution_count += 1
                        result_dict = result.to_dict()
                        completed[step.id] = result_dict
                        log_event(
                            "orchestration_step",
                            {
                                "step": self._step_dict(step),
                                "agent": step.agent,
                                "result": result_dict,
                                "execution_count": execution_count,
                            },
                        )
                        pending.pop(step.id, None)
                        if result.status == "error":
                            failures.append(
                                {"step_id": step.id, "agent": step.agent, "error": result.error}
                            )
                            execution_error = True
                if execution_error:
                    break

            if not execution_error:
                break
            if replans >= self.config.max_replans or execution_count >= self.config.max_total_steps:
                break
            replans += 1
            try:
                plan = self._make_plan(
                    self._replan_prompt(user_prompt, completed, failures),
                    call_number=replans + 1,
                    available_dependencies={
                        step_id for step_id, result in completed.items()
                        if result.get("status") == "ok"
                    },
                )
            except PlanError as replan_error:
                failures.append({"error": str(replan_error), "phase": "replanning"})
                break
            log_event("orchestration_replan", {"replans": replans, "plan": [self._step_dict(s) for s in plan]})

        answer_data = {
            "completed_steps": completed,
            "failures": failures,
            "replans_used": replans,
            "step_limit": self.config.max_total_steps,
        }
        final = self._brain_call(
            phase="final_merge",
            system_prompt=(
                "You are the orchestrator's final response writer. Answer the user's request using only "
                "the provided step results. Be clear about completed work, missing information, and failures. "
                "Never claim an external action succeeded unless a step result confirms it."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User request:\n{user_prompt}\n\n"
                        f"Structured execution results:\n{json.dumps(answer_data, ensure_ascii=False, default=str)}"
                    ),
                }
            ],
            tools=None,
            call_number=1,
        )
        answer = self._response_text(final)
        needs_input = any(item.get("status") == "needs_input" for item in completed.values())
        status = "needs_input" if needs_input else (
            "error"
            if failures or not answer or final.get("error_status") or final.get("api_success") is False
            else "ok"
        )
        log_event(
            "orchestration_final",
            {
                "status": status,
                "plan": [self._step_dict(item) for item in plan],
                "attempts": final.get("total_attempts", 0),
            },
        )
        return {
            "status": status,
            "answer": answer,
            "plan": [self._step_dict(item) for item in plan],
            "results": completed,
            "failures": failures,
            "replans_used": replans,
        }

    def _execute_with_retry(self, step: PlanStep, prompt: str) -> AgentResult:
        agent = self.agents.get(step.agent)
        result = self.runner.run(prompt, agent)
        if result.status != "error":
            return result
        refined = (
            f"{prompt}\n\nThe previous attempt failed: {result.error}\n"
            "Retry this same sub-task once. Avoid repeating a side effect if the previous "
            "attempt may have completed it; verify state first. Return the required structured result."
        )
        return self.runner.run(refined, agent)

    def _make_plan(
        self,
        request: str,
        call_number: int,
        available_dependencies: Optional[Set[str]] = None,
    ) -> List[PlanStep]:
        agents = "\n".join(
            f"- {item.name}: {item.description}" for item in self.agents.all()
        )
        prompt = (
            "Create an execution plan for the request below. Return JSON only, exactly an array of objects "
            'with keys "id", "agent", "prompt", and "depends_on". Each prompt must be self-contained: '
            "state the goal, concrete inputs or IDs, constraints, and expected output format. Do not rely "
            "on hidden conversation history. Use dependencies for outputs needed by later steps. "
            f"Use the smallest practical number of steps.\n\nRequest:\n{request}"
        )
        response = self._brain_call(
            phase="planning",
            system_prompt=(
                "You are a precise task planner. Output valid JSON only, with no prose or markdown. "
                "Available specialist agents:\n"
                f"{agents}"
            ),
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            call_number=call_number,
        )
        if response.get("error_status") or response.get("api_success") is False:
            raise PlanError(str(response.get("error_message") or "Planner Brain call failed."))
        raw = response.get("api_response")
        if not isinstance(raw, str) or not raw.strip():
            raise PlanError("Planner returned no JSON plan.")
        try:
            steps = self._parse_plan(raw)
            self._validate_plan(steps, available_dependencies)
            if len(steps) > self.config.max_total_steps:
                raise PlanError("Plan exceeds max_total_steps.")
            return steps
        except (json.JSONDecodeError, PlanError, TypeError) as exc:
            raise PlanError(f"Invalid planner output: {exc}") from exc

    def _parse_plan(self, value: str) -> List[PlanStep]:
        candidate = value.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
        data = json.loads(candidate)
        if not isinstance(data, list):
            raise PlanError("Plan root must be a JSON array.")
        result = []
        for item in data:
            if not isinstance(item, dict) or set(item) != {"id", "agent", "prompt", "depends_on"}:
                raise PlanError("Each step must contain exactly id, agent, prompt, and depends_on.")
            if not all(isinstance(item[key], str) and item[key].strip() for key in ("id", "agent", "prompt")):
                raise PlanError("Step id, agent, and prompt must be non-empty strings.")
            if not isinstance(item["depends_on"], list) or not all(
                isinstance(dep, str) for dep in item["depends_on"]
            ):
                raise PlanError(f"Step {item['id']} depends_on must be a string array.")
            result.append(
                PlanStep(
                    item["id"].strip(),
                    item["agent"].strip(),
                    item["prompt"].strip(),
                    item["depends_on"],
                )
            )
        return result

    def _validate_plan(
        self,
        steps: Sequence[PlanStep],
        available_dependencies: Optional[Set[str]] = None,
    ) -> None:
        ids = [step.id for step in steps]
        if len(ids) != len(set(ids)):
            raise PlanError("Plan contains duplicate step IDs.")
        known: Set[str] = set(ids)
        available = available_dependencies or set()
        for step in steps:
            try:
                self.agents.get(step.agent)
            except KeyError as exc:
                raise PlanError(str(exc)) from exc
            if step.id in step.depends_on or any(
                dep not in known and dep not in available for dep in step.depends_on
            ):
                raise PlanError(f"Step {step.id} has a self or unknown dependency.")
        remaining = {
            step.id: set(step.depends_on).intersection(known)
            for step in steps
        }
        resolved: Set[str] = set(available)
        while remaining:
            ready = {step_id for step_id, deps in remaining.items() if deps <= resolved}
            if not ready:
                raise PlanError("Plan dependencies contain a cycle.")
            resolved.update(ready)
            for step_id in ready:
                remaining.pop(step_id)

    def _fast_path(self, prompt: str) -> Optional[List[PlanStep]]:
        lower = prompt.lower()
        google_terms = ("google", "gmail", "drive", "calendar", "gcs", "cloud storage", "email")
        coder_terms = (
            "code", "script", "file", "folder", "shell", "command", "local", "workspace",
            "python", "javascript", "test", "refactor", "install", "execute", "implement",
            "write", "modify", "edit", "fix",
        )
        uses_google = any(term in lower for term in google_terms)
        uses_coder = any(term in lower for term in coder_terms)
        if uses_google == uses_coder:
            return None
        name = "google_cloud" if uses_google else "coder"
        try:
            self.agents.get(name)
        except KeyError:
            return None
        return [PlanStep("s1", name, prompt, [])]

    @staticmethod
    def _is_trivial(prompt: str) -> bool:
        return bool(
            re.match(r"^\s*(hi|hello|hey|thanks|thank you)\b", prompt, re.IGNORECASE)
            and len(prompt.split()) <= 8
        )

    @staticmethod
    def _self_contained_prompt(
        step: PlanStep, dependencies: Dict[str, Dict[str, Any]]
    ) -> str:
        return (
            f"Goal:\n{step.prompt}\n\n"
            f"Concrete inputs and upstream artifacts:\n"
            f"{json.dumps(dependencies, ensure_ascii=False, default=str)}\n\n"
            "Constraints:\n"
            "- Use only the tools available to your specialist agent.\n"
            "- Do not assume or access any other conversation history.\n"
            "- Do not claim an action succeeded unless a tool result confirms it.\n\n"
            "Expected output format:\n"
            "Call finish with a concise summary and a list of typed artifacts "
            "({\"type\": \"...\", \"value\": \"...\"}); call ask_user if a required input is missing."
        )

    def _replan_prompt(
        self,
        user_prompt: str,
        completed: Dict[str, Dict[str, Any]],
        failures: List[Dict[str, Any]],
    ) -> str:
        successful = {
            step_id: result
            for step_id, result in completed.items()
            if result.get("status") == "ok"
        }
        return (
            f"Original task:\n{user_prompt}\n\n"
            "Previously completed steps (do not repeat successful side effects):\n"
            f"{json.dumps(successful, ensure_ascii=False, default=str)}\n\n"
            "Failed attempts and errors:\n"
            f"{json.dumps(failures, ensure_ascii=False, default=str)}\n\n"
            "Return a new JSON plan only for the remaining work. Reuse completed artifacts through "
            "depends_on where needed, do not repeat already completed work, and keep it self-contained."
        )

    def _brain_call(
        self,
        phase: str,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]],
        call_number: int,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self.brain(
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
            )
        except Exception as exc:
            logger.exception("Brain call failed in phase %s.", phase)
            response = {"error_status": True, "error_message": str(exc)}
        log_event(
            "brain_call",
            {
                "phase": phase,
                "call_number": call_number,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "attempts": response.get("total_attempts", 0),
                "error": response.get("error_message"),
            },
        )
        return response

    @staticmethod
    def _response_text(response: Dict[str, Any]) -> str:
        return str(response.get("api_response") or response.get("error_message") or "")

    @staticmethod
    def _step_dict(step: PlanStep) -> Dict[str, Any]:
        return {
            "id": step.id,
            "agent": step.agent,
            "prompt": step.prompt,
            "depends_on": step.depends_on,
        }
