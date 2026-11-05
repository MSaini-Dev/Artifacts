# Brain LangChain — failover-aware chat model

Production wrapper that turns the existing **Brain / call_api** stack into a
drop-in `langchain_core.language_models.chat_models.BaseChatModel`.

Every request is routed through size-ranked failover across providers → models → API keys
(with cooldowns, payment/invalid-key disables, and 413 model-exclusion).

## Install

```bash
pip install -r requirements.txt
# run package commands from the repository root:
pip install -e .
```

## Environment

API keys are auto-discovered from env vars:

```
LLM_API_KEY_GROQ=...
LLM_API_KEY_GROQ_MOHIT=...
LLM_API_KEY_GEMINI=...
LLM_API_KEY_CEREBRAS=...
```

Optional knobs:

```
BRAIN_TESTING_IS=false
CALL_API_IS=true
BRAIN_MAX_RETRIES=3
```

`api_data.json` (next to the package) tracks provider/model/key status and is
updated at runtime. Logs land in `logs/call_api.jsonl`.

## Quick start

```python
from backend.agent.brain_langchain import BrainChatModel
from langchain_core.messages import HumanMessage, SystemMessage

llm = BrainChatModel(temperature=0.3, max_tokens=1024, buffer=0)

# plain invoke
resp = llm.invoke([
    SystemMessage(content="You are concise."),
    HumanMessage(content="Say hello in one sentence."),
])
print(resp.content)
print(resp.additional_kwargs.get("provider"), resp.additional_kwargs.get("model"))
```

## With tools / agents

```python
from langchain_core.tools import tool
from backend.agent.brain_langchain import BrainChatModel

@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

llm = BrainChatModel(temperature=0)
llm_with_tools = llm.bind_tools([add])

msg = llm_with_tools.invoke("What is 21 + 21?")
print(msg.tool_calls)   # modern LangChain shape: [{id, name, args}]
```

Works with `create_react_agent` / `create_tool_calling_agent` / LangGraph.

## Direct Brain API (no LangChain)

```python
from backend.agent.brain_langchain import brain, ToolSpec

result = brain(
    user_prompt="Hello",
    system_prompt="You are helpful.",
    tools=[ToolSpec(name="ping", description="Ping", parameters={"type":"object","properties":{}})],
    buffer=0,
)
print(result["api_success"], result.get("chosen"), result.get("api_response"))
```

## Failover behaviour (unchanged from original stack)

| Error                 | Action                                                           |
| --------------------- | ---------------------------------------------------------------- |
| 429 rate limit        | Cooldown key (or wait if`buffer` ≥ Retry-After), try next key |
| 401 / 403             | Permanently disable key                                          |
| 402 payment required  | Permanently disable key                                          |
| 404 model missing     | Disable model                                                    |
| 413 request too large | Exclude model for*this* call only                              |
| 5xx / network         | Cooldown provider                                                |
| Timeout               | Cooldown key                                                     |

Models are ranked by `size` (largest first). When `estimated_tokens` is known,
candidates whose TPM comfortably fits are preferred.

## Package layout

```
brain_langchain/
├── langchain_wrapper.py   # BrainChatModel
├── brain.py
├── types.py
├── api_data.json
├── api_manager/
│   ├── call_api.py
│   ├── api_handler/       # data_store, selector, call_logger
│   └── provider/          # call_groq, call_gemini, call_cerebras, _http_provider
└── logs/
```
