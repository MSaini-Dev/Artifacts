from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.single_agent import (
    INCOMPLETE_TASK_PREFIX,
    _summarize_turns,
    _call_agent_impl,
    _trim_context,
)


class FakeTool:
    name = "write_file"

    def __init__(self):
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        return {"success": True, "message": "file written"}


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def bind_tools(self, _tools):
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        return next(self.responses)


def test_context_trim_replaces_summary_and_carries_forward_prior_facts():
    previous_summary = "The Gmail test email was sent successfully."
    model = FakeModel([
        AIMessage(content="The email was sent; the spreadsheet request remains unresolved.")
    ])
    messages = [
        SystemMessage(
            content=(
                "Agent instructions.\n\n"
                f"[Earlier session summary]: {previous_summary}"
            )
        ),
        HumanMessage(content="Original user request."),
        *[HumanMessage(content=f"Historical fact {index}.") for index in range(8)],
    ]

    trimmed = _trim_context(model, messages, keep_last_turns=6)

    system_content = trimmed[0].content
    summarizer_prompt = model.calls[0][0].content
    assert system_content.count("[Earlier session summary]:") == 1
    assert system_content.startswith("Agent instructions.")
    assert "The email was sent; the spreadsheet request remains unresolved." in system_content
    assert previous_summary in summarizer_prompt
    assert "Historical fact 0." in summarizer_prompt
    assert "Historical fact 1." in summarizer_prompt


def test_summarizer_includes_tool_call_name_and_arguments():
    model = FakeModel([AIMessage(content="A file was written.")])
    tool_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "write_file",
            "args": {"file_path": "backend/example.py"},
            "id": "write-1",
            "type": "tool_call",
        }],
    )

    _summarize_turns(model, [[tool_call]])

    prompt = model.calls[0][0].content
    assert "write_file" in prompt
    assert "backend/example.py" in prompt


def test_action_request_continues_after_plan_and_checks_work():
    tool = FakeTool()
    model = FakeModel([
        AIMessage(content="I will inspect the project and then create the file."),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "output.py", "content": "value = 1"},
                "id": "write-1",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="The implementation is complete."),
        AIMessage(content="I verified the implementation and it is complete."),
    ])

    result = _call_agent_impl(
        user_prompt="Create the requested Python file.",
        tools=[tool],
        max_turns=4,
        verbose=False,
        model=model,
    )

    assert result == "I verified the implementation and it is complete."
    assert tool.calls == [{"file_path": "output.py", "content": "value = 1"}]
    assert len(model.calls) == 4
    assert isinstance(model.calls[1][-1], HumanMessage)
    assert "Do not finish with a plan" in model.calls[1][-1].content
    assert "verify every requirement" in model.calls[3][-1].content


def test_action_request_without_action_is_reported_incomplete_at_turn_limit():
    model = FakeModel([
        AIMessage(content="Here is the plan. I will create the file next."),
        AIMessage(content="The task was not completed."),
    ])

    result = _call_agent_impl(
        user_prompt="Create a Python file.",
        tools=[],
        max_turns=1,
        verbose=False,
        model=model,
    )

    assert result.startswith(INCOMPLETE_TASK_PREFIX)
    assert len(model.calls) == 2


def test_question_request_can_return_without_forced_tool_execution():
    model = FakeModel([AIMessage(content="Use OAuth consent and the Gmail send scope.")])

    result = _call_agent_impl(
        user_prompt="How do I configure Gmail OAuth?",
        tools=[],
        max_turns=1,
        verbose=False,
        model=model,
    )

    assert result == "Use OAuth consent and the Gmail send scope."
    assert len(model.calls) == 1


def test_action_request_reports_a_concrete_blocker_without_claiming_success():
    model = FakeModel([
        AIMessage(content="I cannot continue without OAuth consent from the account owner.")
    ])

    result = _call_agent_impl(
        user_prompt="Set up Gmail sending.",
        tools=[],
        max_turns=3,
        verbose=False,
        model=model,
    )

    assert result.startswith(INCOMPLETE_TASK_PREFIX)
    assert "OAuth consent" in result
    assert len(model.calls) == 1


def test_progress_report_after_verification_prompt_keeps_working(monkeypatch):
    monkeypatch.setattr(
        "backend.agent.single_agent._trim_context",
        lambda _model, messages: messages,
    )
    tool = FakeTool()
    model = FakeModel([
        AIMessage(content="I will create the file."),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "output.py", "content": "value = 1"},
                "id": "write-2",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="The file is created; next I will run tests."),
        AIMessage(content="I have not yet run tests; next steps are to run them."),
        AIMessage(content="Tests passed and all requested work is complete."),
    ])

    result = _call_agent_impl(
        user_prompt="Create and test the requested Python file.",
        tools=[tool],
        max_turns=5,
        verbose=False,
        model=model,
    )

    assert result == "Tests passed and all requested work is complete."
    assert len(model.calls) == 5
    assert "verify every requirement" in model.calls[3][-1].content
    assert "continue" in model.calls[4][-1].content.lower()


def test_blocker_after_partial_action_is_not_reported_as_success():
    tool = FakeTool()
    model = FakeModel([
        AIMessage(content="I will create the email tool."),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "send_email.py", "content": "pass"},
                "id": "write-3",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="I cannot send email until OAuth consent is granted."),
    ])

    result = _call_agent_impl(
        user_prompt="Create a Gmail tool and send an email.",
        tools=[tool],
        max_turns=3,
        verbose=False,
        model=model,
    )

    assert result.startswith(INCOMPLETE_TASK_PREFIX)
    assert "OAuth consent" in result
