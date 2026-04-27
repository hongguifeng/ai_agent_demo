"""
========================================
第一章：你好，LLM —— 一切的起点
========================================

AI Agent 的核心是大语言模型（LLM）。在构建 Agent 之前，
我们首先要理解如何与 LLM 对话。

核心概念：
1. LLM 本质上是一个「输入消息列表 → 输出回复」的函数
2. 消息有三种角色：system（系统）、user（用户）、assistant（助手）
3. 每次调用都是无状态的 —— LLM 没有记忆，所有上下文都靠消息列表传入

这就像打电话给一个专家：你每次都要把完整的背景讲一遍，
专家才能给出有意义的回答。
"""

import os
import httpx
from openai import OpenAI

# ============================================================
# 第 1 步：创建客户端
# ============================================================
# OpenAI 客户端会自动读取 OPENAI_API_KEY 环境变量
# 如果你使用兼容接口（如 DeepSeek、月之暗面等），设置 OPENAI_BASE_URL 即可
# verify=False 用于处理代理的自签名证书，生产环境应移除
client = OpenAI(http_client=httpx.Client(verify=False))

# 模型名称：通过环境变量配置，默认 gpt-4o-mini
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# ============================================================
# 第 2 步：最简单的对话 —— 单轮问答
# ============================================================
print("=" * 60)
print("示例 1：单轮对话")
print("=" * 60)

response = client.chat.completions.create(
    model=MODEL,  # 模型名称，通过 AGENT_MODEL 环境变量配置
    messages=[
        {"role": "user", "content": "用一句话解释什么是 AI Agent"}
    ],
)

# response 的结构：
#   response.choices[0].message.role    -> "assistant"
#   response.choices[0].message.content -> 回复文本
reply = response.choices[0].message
print(f"助手回复: {reply.content}\n")

# ============================================================
# 第 3 步：多轮对话 —— 传入完整历史
# ============================================================
print("=" * 60)
print("示例 2：多轮对话（手动维护历史）")
print("=" * 60)

# 关键理解：LLM 本身无记忆，"多轮对话"是我们把历史消息一起传入实现的
messages = [
    {"role": "user", "content": "我叫小明"},
    {"role": "assistant", "content": "你好小明！有什么可以帮你的？"},
    {"role": "user", "content": "我叫什么名字？"},
]

response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
)

print(f"助手回复: {response.choices[0].message.content}\n")
# LLM 能"记住"名字，是因为我们把之前的对话作为输入传了进去

# ============================================================
# 第 4 步：流式输出 —— 逐字打印
# ============================================================
print("=" * 60)
print("示例 3：流式输出（像 ChatGPT 一样逐字显示）")
print("=" * 60)

stream = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "用三句话介绍 Python 语言"}
    ],
    stream=True,  # 开启流式
)

for chunk in stream:
    # 每个 chunk 包含一小段文本（通常是几个字符）
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)

print("\n")

# ============================================================
# 本章小结
# ============================================================
print("=" * 60)
print("""
本章小结：

1. LLM API 的本质：messages in → message out
2. 消息角色：system / user / assistant
3. 多轮对话 = 把完整消息历史传入
4. 流式输出 = 设置 stream=True，逐块读取

下一章，我们将学习如何用 System Prompt 给 LLM "塑造人格"，
这是构建 Agent 的第一步。
""")
