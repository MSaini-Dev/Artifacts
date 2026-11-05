# from langchain_core.tools import tool
# from backend.agent.brain_langchain import BrainChatModel

# @tool
# def add(a: int, b: int) -> int:
#     """Add two integers."""
#     return a + b

# llm = BrainChatModel(temperature=0)
# llm_with_tools = llm.bind_tools([add])

# msg = llm_with_tools.invoke("What is 21 + 21?")

# print("content     :", msg.content)          # often "" when a tool is called
# print("tool_calls  :", msg.tool_calls)
# print("provider    :", msg.additional_kwargs.get("provider"))
# print("model       :", msg.additional_kwargs.get("model"))

# ====================================================================================================================

# from langchain_core.messages import HumanMessage, ToolMessage
# from langchain_core.tools import tool
# from backend.agent.brain_langchain import BrainChatModel

# @tool
# def add(a: int, b: int) -> int:
#     """Add two integers."""
#     return a + b

# llm = BrainChatModel(temperature=0)
# llm_with_tools = llm.bind_tools([add])
# tools_by_name = {add.name: add}

# messages = [HumanMessage(content="What is 21 + 21?")]

# # 1) model may request tools
# ai_msg = llm_with_tools.invoke(messages)
# messages.append(ai_msg)

# # 2) execute tools
# for tc in ai_msg.tool_calls or []:
#     result = tools_by_name[tc["name"]].invoke(tc["args"])
#     messages.append(
#         ToolMessage(content=str(result), tool_call_id=tc["id"])
#     )

# # 3) model produces the final natural-language answer
# final = llm_with_tools.invoke(messages)

# print("Final answer:", final.content)
# print("Chosen     :", final.additional_kwargs.get("provider"),
#       final.additional_kwargs.get("model"))

# ====================================================================================================================

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from backend.agent.brain_langchain import BrainChatModel

@tool
def fetch_personal_info() -> dict:
    """Fetch the person detail like name, date of birth."""
    return {
        "name": "Mohit Saini",
        "dob": "13 Aug 2000",
    }

llm = BrainChatModel(temperature=0)
llm_with_tools = llm.bind_tools([fetch_personal_info])
tools_by_name = {fetch_personal_info.name: fetch_personal_info}

messages = [HumanMessage(content="hello llm, what my is name")]

# 1) Model requests the tool
ai_msg = llm_with_tools.invoke(messages)
print("=== step 1: model requested tool ===")
print("content   :", repr(ai_msg.content))
print("tool_calls:", ai_msg.tool_calls)
messages.append(ai_msg)

# 2) Execute tool(s)
for tc in ai_msg.tool_calls or []:
    result = tools_by_name[tc["name"]].invoke(tc["args"])
    print(f"=== step 2: ran {tc['name']} -> {result} ===")
    messages.append(
        ToolMessage(content=str(result), tool_call_id=tc["id"])
    )

# 3) Model writes the final answer using tool result
final = llm_with_tools.invoke(messages)
print("=== step 3: final answer ===")
print("content :", final.content)
print("provider:", final.additional_kwargs.get("provider"))
print("model   :", final.additional_kwargs.get("model"))
