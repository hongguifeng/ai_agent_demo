"""
========================================
第二章：系统提示词与角色设计
========================================

System Prompt 是 Agent 的"灵魂"。它决定了 LLM 如何思考、如何回答、
遵循什么规则。Claude Code、OpenClaw 等产品的核心竞争力，
很大程度上就在于精心设计的 System Prompt。

核心概念：
1. System Prompt 定义 Agent 的身份、能力边界和行为规则
2. 好的 System Prompt = 明确的角色 + 清晰的规则 + 输出格式约束
3. 温度参数（temperature）控制输出的确定性
"""

import os
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# ============================================================
# 第 1 步：感受 System Prompt 的威力
# ============================================================
print("=" * 60)
print("示例 1：没有 System Prompt")
print("=" * 60)

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "帮我看看这段代码有什么问题：\ndef add(a, b)\n    return a + b"}
    ],
)
print(response.choices[0].message.content)
print()

print("=" * 60)
print("示例 2：加上 System Prompt，变身代码专家")
print("=" * 60)

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "system",
            "content": """你是一个资深的 Python 代码审查专家。

你的回答必须遵循以下格式：
## 问题
- 列出发现的每个问题

## 修复后的代码
```python
修复后的完整代码
```

## 解释
简短解释修复原因。

规则：
- 只关注代码问题，不要闲聊
- 回答要简洁精准
- 使用中文回答"""
        },
        {"role": "user", "content": "帮我看看这段代码有什么问题：\ndef add(a, b)\n    return a + b"}
    ],
)
print(response.choices[0].message.content)
print()

# ============================================================
# 第 2 步：设计一个 Agent 风格的 System Prompt
# ============================================================
print("=" * 60)
print("示例 3：Agent 风格的 System Prompt")
print("=" * 60)

# 这是一个简化版的 Claude Code 风格 System Prompt
AGENT_SYSTEM_PROMPT = """你是一个 AI 编程助手，工作在用户的计算机上。

## 你的身份
- 你是一个专业的编程 Agent
- 你可以阅读文件、编写代码、执行命令
- 你总是先思考，再行动

## 工作流程
当用户提出需求时，你应该：
1. **分析需求**：理解用户想要什么
2. **制定计划**：列出需要执行的步骤
3. **逐步执行**：一步一步完成任务
4. **验证结果**：确认任务完成

## 回答规则
- 简洁明了，不废话
- 先展示思考过程，再给出结果
- 如果不确定，要主动询问
- 代码要可运行，不要伪代码

## 输出格式
思考过程用 <thinking>...</thinking> 包裹。
最终回答直接输出。"""

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": "帮我写一个函数，统计字符串中每个字符出现的次数"}
    ],
    temperature=0,  # temperature=0 让输出更确定，适合 Agent 场景
)
print(response.choices[0].message.content)
print()

# ============================================================
# 第 3 步：温度参数的影响
# ============================================================
print("=" * 60)
print("示例 4：temperature 对比")
print("=" * 60)

prompt = [{"role": "user", "content": "给变量取个名字，表示用户年龄"}]

for temp in [0, 0.5, 1.5]:
    response = client.chat.completions.create(
        model=MODEL,
        messages=prompt,
        temperature=temp,
        max_tokens=50,
    )
    content = response.choices[0].message.content or "(空)"
    print(f"  temperature={temp}: {content.strip()}")

print()

# ============================================================
# 本章小结
# ============================================================
print("=" * 60)
print("""
本章小结：

1. System Prompt 是 Agent 的"灵魂"，定义身份和行为
2. 好的 System Prompt 包含：角色定义 + 行为规则 + 输出格式
3. temperature=0 适合 Agent（需要确定性），高温度适合创意任务
4. Claude Code 等产品的核心：精心设计的 System Prompt + 工具调用

下一章，我们将学习"工具调用"—— 让 LLM 不只是说，还能做！
""")
