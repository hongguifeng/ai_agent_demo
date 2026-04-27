"""
========================================
第四章：Agent 循环 —— ReAct 模式
========================================

前面我们学会了单次工具调用。但真正的 Agent 需要能"自主循环"：
思考 → 行动 → 观察 → 再思考 → 再行动...直到任务完成。

这就是 ReAct（Reasoning + Acting）模式，也是 Claude Code 的核心架构。

    ┌─────────────────────────────────┐
    │         Agent Loop               │
    │                                  │
    │   User Input                     │
    │       ↓                          │
    │   ┌──────────┐                   │
    │   │ LLM 思考  │ ← messages       │
    │   └──────────┘                   │
    │       ↓                          │
    │   有工具调用？                     │
    │    ├─ Yes → 执行工具 → 结果加入   │
    │    │         messages → 回到 LLM  │
    │    └─ No  → 输出最终回复，退出    │
    └─────────────────────────────────┘

核心原理就这么简单：一个 while 循环。
"""

import json
import os
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# ============================================================
# 第 1 步：定义工具
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行数学计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，例如 '2 + 3'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "string_length",
            "description": "计算字符串的长度",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要计算长度的字符串"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reverse",
            "description": "反转一个列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要反转的列表"
                    }
                },
                "required": ["items"]
            }
        }
    }
]

def calculator(expression: str) -> str:
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return "错误：包含不允许的字符"
    try:
        return str(eval(expression))
    except Exception as e:
        return f"错误：{e}"

def string_length(text: str) -> str:
    return str(len(text))

def list_reverse(items: list) -> str:
    return json.dumps(list(reversed(items)), ensure_ascii=False)

TOOL_MAP = {
    "calculator": calculator,
    "string_length": string_length,
    "list_reverse": list_reverse,
}

# ============================================================
# 第 2 步：Agent 循环（核心！）
# ============================================================

def agent_loop(user_input: str, max_iterations: int = 10) -> str:
    """
    Agent 主循环 —— 这就是 AI Agent 的核心。

    整个函数只做一件事：
    不断让 LLM 思考和调用工具，直到 LLM 认为任务完成（不再调用工具）。
    """
    print(f"\n{'='*60}")
    print(f"用户: {user_input}")
    print(f"{'='*60}")

    # 初始化消息列表
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个有用的 AI 助手。你可以使用工具来完成任务。\n"
                "对于需要多步才能完成的任务，你可以多次调用工具。\n"
                "每一步都要思考清楚再行动。"
            )
        },
        {"role": "user", "content": user_input}
    ]

    # ---- Agent 循环开始 ----
    for i in range(max_iterations):
        print(f"\n--- 第 {i+1} 轮 ---")

        # 调用 LLM
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            temperature=0,
        )

        assistant_message = response.choices[0].message

        # 判断：LLM 是否想调用工具？
        if not assistant_message.tool_calls:
            # 没有工具调用 → 任务完成，返回最终回复
            print(f"[完成] LLM 最终回复")
            print(f"助手: {assistant_message.content}")
            return assistant_message.content

        # 有工具调用 → 执行每个工具
        messages.append(assistant_message)  # 先保存助手消息

        for tool_call in assistant_message.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            print(f"[工具调用] {func_name}({func_args})")

            # 执行工具
            if func_name in TOOL_MAP:
                result = TOOL_MAP[func_name](**func_args)
            else:
                result = f"错误：未知工具 {func_name}"

            print(f"[工具结果] {result}")

            # 把结果加入消息列表
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        # 回到循环顶部，让 LLM 继续思考...
    # ---- Agent 循环结束 ----

    return "达到最大迭代次数，任务未完成"

# ============================================================
# 第 3 步：测试 Agent
# ============================================================

# 测试 1：简单任务（1 轮工具调用）
agent_loop("计算 (100 + 200) * 3")

# 测试 2：多步任务（需要多轮工具调用）
agent_loop(
    "先帮我计算 'Hello World' 的长度，然后将这个长度乘以 7"
)

# 测试 3：不需要工具的任务
agent_loop("你好，介绍一下你自己")

# ============================================================
# 本章小结
# ============================================================
print("\n" + "=" * 60)
print("""
本章小结：

1. Agent 的核心 = while 循环 + LLM + 工具
2. 每一轮：LLM 思考 → 决定是否调用工具 → 执行 → 结果返回
3. 循环终止条件：LLM 不再调用工具（认为任务完成）
4. max_iterations 防止无限循环

这就是 Claude Code、OpenClaw 等所有 AI Agent 的核心架构。
复杂的 Agent 只是在这个基础上添加了更多工具和更复杂的提示词。

下一章，我们将实现真正实用的工具：文件读写和命令执行！
""")
