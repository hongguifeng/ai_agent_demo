"""
========================================
第三章：工具定义与函数调用 —— 让 LLM 能"动手做事"
========================================

纯聊天的 LLM 只能"说"，不能"做"。
Tool Calling（工具调用）是 Agent 的关键能力：
LLM 不直接执行操作，而是输出"我想调用什么工具、传什么参数"，
由我们的程序去实际执行，再把结果返回给 LLM。

这就是 Claude Code 能读写文件、执行命令的原理。

核心概念：
1. 工具 = 函数名 + 参数的 JSON Schema 描述
2. LLM 不执行工具，只"决定"调用哪个工具
3. 我们负责实际执行，并把结果返回给 LLM

流程：
  User → LLM → "我想调用 calculator(expression='2+3')"
                → 我们执行 calculator("2+3")
                → 结果 "5" 返回给 LLM
                → LLM 生成最终回复
"""

import json
import os
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# ============================================================
# 第 1 步：定义工具（用 JSON Schema 描述函数签名）
# ============================================================

# 工具定义列表 —— 告诉 LLM "你有哪些工具可用"
tools = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行数学运算。支持加减乘除、幂运算等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式，例如 '2 + 3 * 4'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如 '北京'"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

# ============================================================
# 第 2 步：实现工具函数（实际执行逻辑）
# ============================================================

def calculator(expression: str) -> str:
    """安全地计算数学表达式"""
    # 安全限制：只允许数字和基本运算符
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return f"错误：表达式包含不允许的字符"
    try:
        result = eval(expression)  # 在生产环境中应使用更安全的方式
        return str(result)
    except Exception as e:
        return f"计算错误：{e}"


def get_weather(city: str) -> str:
    """模拟天气查询（实际项目中会调用天气 API）"""
    # 这里用模拟数据，实际中会调用真实 API
    mock_data = {
        "北京": "晴天，25°C，湿度 40%",
        "上海": "多云，22°C，湿度 65%",
        "深圳": "小雨，28°C，湿度 80%",
    }
    return mock_data.get(city, f"未找到 {city} 的天气数据")


# 工具名 → 函数的映射表
TOOL_MAP = {
    "calculator": calculator,
    "get_weather": get_weather,
}

# ============================================================
# 第 3 步：完整的工具调用流程
# ============================================================
print("=" * 60)
print("示例 1：LLM 自动选择工具")
print("=" * 60)

messages = [
    {"role": "system", "content": "你是一个有用的助手，可以使用工具来帮助用户。"},
    {"role": "user", "content": "帮我算一下 (15 + 27) * 3 等于多少"}
]

# 第一次调用：LLM 决定要用什么工具
print("\n[1] 发送用户消息给 LLM...")
response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    tools=tools,
)

assistant_message = response.choices[0].message
print(f"[2] LLM 决策: ", end="")

# 检查 LLM 是否想调用工具
if assistant_message.tool_calls:
    tool_call = assistant_message.tool_calls[0]
    func_name = tool_call.function.name
    func_args = json.loads(tool_call.function.arguments)
    print(f"调用工具 {func_name}({func_args})")

    # 第二步：我们执行工具
    result = TOOL_MAP[func_name](**func_args)
    print(f"[3] 工具执行结果: {result}")

    # 第三步：把工具结果返回给 LLM
    messages.append(assistant_message)  # 助手的工具调用消息
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": result,
    })

    # 第四步：LLM 根据工具结果生成最终回复
    print("[4] 将结果返回给 LLM，生成最终回复...")
    final_response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
    )
    print(f"[5] 最终回复: {final_response.choices[0].message.content}")
else:
    print(f"直接回复（未使用工具）: {assistant_message.content}")

# ============================================================
# 第 4 步：LLM 自主判断是否需要工具
# ============================================================
print("\n" + "=" * 60)
print("示例 2：LLM 判断不需要工具时直接回答")
print("=" * 60)

messages2 = [
    {"role": "system", "content": "你是一个有用的助手，可以使用工具来帮助用户。"},
    {"role": "user", "content": "你好，请介绍一下你自己"}
]

response2 = client.chat.completions.create(
    model=MODEL,
    messages=messages2,
    tools=tools,
)

msg = response2.choices[0].message
if msg.tool_calls:
    print(f"LLM 选择调用工具: {msg.tool_calls[0].function.name}")
else:
    print(f"LLM 直接回答（无需工具）: {msg.content}")

# ============================================================
# 第 5 步：多工具调用
# ============================================================
print("\n" + "=" * 60)
print("示例 3：一次请求中调用多个工具")
print("=" * 60)

messages3 = [
    {"role": "system", "content": "你是一个有用的助手。"},
    {"role": "user", "content": "帮我算 100/7 保留两位小数，另外查一下北京和上海的天气"}
]

response3 = client.chat.completions.create(
    model=MODEL,
    messages=messages3,
    tools=tools,
)

msg3 = response3.choices[0].message
if msg3.tool_calls:
    print(f"LLM 要求调用 {len(msg3.tool_calls)} 个工具：")
    messages3.append(msg3)

    for tc in msg3.tool_calls:
        name = tc.function.name
        args = json.loads(tc.function.arguments)
        print(f"  → {name}({args})")
        result = TOOL_MAP[name](**args)
        print(f"    结果: {result}")
        messages3.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })

    # 获取最终回复
    final = client.chat.completions.create(
        model=MODEL,
        messages=messages3,
        tools=tools,
    )
    print(f"\n最终回复: {final.choices[0].message.content}")

# ============================================================
# 本章小结
# ============================================================
print("\n" + "=" * 60)
print("""
本章小结：

1. 工具定义 = 函数名 + JSON Schema 参数描述
2. LLM 不执行工具，只输出"想调用什么"
3. 完整流程：用户消息 → LLM 选择工具 → 我们执行 → 结果返回 → LLM 最终回复
4. LLM 能自主判断是否需要工具，也能一次调用多个工具

关键洞察：
  LLM 就像一个"大脑"，工具就是它的"手"。
  大脑决定做什么，手去执行，结果反馈给大脑。
  这就是所有 AI Agent 的核心原理。

下一章，我们把这些拼成一个循环 —— ReAct Agent！
""")
