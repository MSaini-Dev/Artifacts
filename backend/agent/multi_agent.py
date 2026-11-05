"""
Multi-Agent Orchestrator

- Planner agent: breaks the task into clear steps
- Coder agent: writes code / files
- Verifier agent: checks that files exist, content is correct, and tries to run

Each agent has a focused system prompt and shares the same powerful tool set.
The orchestrator keeps overall context small by only passing necessary information.
"""

import sys
import os
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from langchain_core.messages import SystemMessage, HumanMessage
from backend.agent.brain_langchain import BrainChatModel
from backend.agent.brain_langchain.api_manager.sqlite_logger import (
    conversation_scope,
    interactive_scope,
    update_interactive,
)

from backend.agent.single_agent import call_agent as run_single_agent
from backend.tools.features import get_langchain_tools, refresh_tools_registry

load_dotenv()


def _llm(model_name: str = None, provider: str = None):
    return BrainChatModel(model=model_name, provider=provider, temperature=0.2)


def planner_agent(user_prompt: str) -> str:
    """Breaks the big request into clear, ordered steps."""
    system = """You are a planning agent. 
Given a user request, output a short numbered list of concrete steps that a coding agent should follow.
Keep it practical and ordered. Do not write code. Only the plan."""
    
    model = _llm()
    resp = model.invoke([
        SystemMessage(content=system),
        HumanMessage(content=user_prompt)
    ])
    return resp.content if hasattr(resp, "content") else str(resp)


def coder_agent(step_description: str, original_prompt: str) -> str:
    """Focused coding agent for one step."""
    focused_prompt = f"""Original user request:
{original_prompt}

Current step you must complete:
{step_description}

Complete only this step. Write files, run commands, verify your work. When done, give a short summary of what you did."""
    
    return run_single_agent(focused_prompt, max_turns=20, verbose=True)


def verifier_agent(summary_of_work: str, original_prompt: str) -> str:
    """Checks that the work actually satisfies the original request."""
    focused_prompt = f"""Original user request:
{original_prompt}

Work that was supposedly done:
{summary_of_work}

Your job:
1. Verify that the important files exist and contain reasonable content.
2. If something should be runnable, try to run it or check its status.
3. Report clearly what is working and what is missing or broken.
4. If critical things are missing, fix them.

Be strict but practical."""
    
    return run_single_agent(focused_prompt, max_turns=12, verbose=True)


def call_multi_agent(user_prompt: str, verbose: bool = True) -> str:
    """
    Main entry point for multi-agent mode.
    """
    with conversation_scope(title=f"Multi-Agent: {user_prompt[:60]}") as conversation_id:
        with interactive_scope(
            conversation_id=conversation_id,
            payload={"user_prompt": user_prompt, "mode": "multi-agent"},
        ) as interaction_id:
            final_text = _call_multi_agent_impl(user_prompt, verbose=verbose)
            update_interactive(
                interactive_id=interaction_id,
                response_status="Final",
                actual_response=final_text,
            )
            return final_text


def _call_multi_agent_impl(user_prompt: str, verbose: bool = True) -> str:
    if verbose:
        print("\n" + "=" * 60)
        print("🧠 MULTI-AGENT ORCHESTRATOR STARTED")
        print("=" * 60)

    # Ensure tools are ready
    try:
        refresh_tools_registry()
    except Exception:
        pass

    # 1. Plan
    if verbose:
        print("\n📋 Phase 1: Planning...")
    plan = planner_agent(user_prompt)
    if verbose:
        print("Plan:\n", plan)

    # 2. Execute steps (simple sequential for reliability)
    # We treat the whole plan as guidance for the coder
    if verbose:
        print("\n💻 Phase 2: Coding...")
    
    coding_prompt = f"""User request:
{user_prompt}

Here is a suggested plan (follow the spirit, not rigidly):
{plan}

Now implement the full solution. Create all necessary files, make it work, and verify as you go."""
    
    coding_result = run_single_agent(coding_prompt, max_turns=20, verbose=verbose)

    # 3. Verify
    if verbose:
        print("\n🔍 Phase 3: Verification...")
    verification = verifier_agent(coding_result, user_prompt)

    final = f"""=== MULTI-AGENT RESULT ===

--- PLAN ---
{plan}

--- CODING SUMMARY ---
{coding_result}

--- VERIFICATION ---
{verification}
"""
    if verbose:
        print("\n" + "=" * 60)
        print("✅ MULTI-AGENT FINISHED")
        print("=" * 60)

    return final
