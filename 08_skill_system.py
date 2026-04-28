"""
========================================
第八章：Skill 系统 —— 让 Agent 具备可插拔能力
========================================

前七章我们已经构建了一个完整的 Coding Agent。
但在实际产品中（如 Claude Code、Cursor、OpenClaw），
Agent 的能力需要是"可插拔"的 —— 不同任务加载不同 Skill。

Skill（技能）是一种模块化设计：
- 每个 Skill 是一个独立的能力单元
- 包含 System Prompt 片段 + 工具定义 + 工具实现
- Agent 运行时动态加载/组合 Skill

为什么需要 Skill？
1. 解耦 —— 新增能力不需要改 Agent 核心代码
2. 复用 —— 同一个 Skill 可以被多个 Agent 使用
3. 灵活 —— 根据任务动态选择加载哪些 Skill
4. 安全 —— 限制 Agent 能使用的工具范围

架构：
    ┌──────────────────────────────────────┐
    │             Agent Core               │
    │                                      │
    │  ┌──────────┐   ┌────────────────┐   │
    │  │ Skill    │   │  Agent Loop    │   │
    │  │ Registry │──▶│  (ReAct)       │   │
    │  └──────────┘   └────────────────┘   │
    │       │                              │
    │  ┌────┴──────────────────────┐       │
    │  │         Skills            │       │
    │  │  ┌─────┐ ┌─────┐ ┌─────┐ │       │
    │  │  │Math │ │File │ │Web  │ │       │
    │  │  │Skill│ │Skill│ │Skill│ │       │
    │  │  └─────┘ └─────┘ └─────┘ │       │
    │  └───────────────────────────┘       │
    └──────────────────────────────────────┘
"""

import json
import os
import math
import datetime
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
print(f"当前使用模型: {MODEL}\n")


# ============================================================
# 第 1 步：定义 Skill 基类
# ============================================================
print("=" * 60)
print("第 1 步：Skill 基类设计")
print("=" * 60)

# 每个 Skill 必须包含：
# 1. name        - 技能名称
# 2. description - 技能描述
# 3. system_prompt - 注入到 System Prompt 中的指令
# 4. tools       - 工具定义列表（OpenAI function calling 格式）
# 5. execute()   - 工具执行方法


class Skill:
    """Skill 基类 —— 所有技能都继承自这个类"""

    name: str = ""
    description: str = ""
    system_prompt: str = ""

    def get_tools(self) -> list[dict]:
        """返回该 Skill 提供的工具定义列表"""
        return []

    def execute(self, tool_name: str, arguments: dict) -> str:
        """执行指定工具，返回结果字符串"""
        raise NotImplementedError(f"未实现工具: {tool_name}")


print("""
  Skill 基类定义了统一的接口：
  - get_tools()  → 返回工具 JSON Schema
  - execute()    → 执行工具并返回结果
  - system_prompt → 额外的 System Prompt 指令

  所有具体 Skill 继承这个基类，实现自己的工具。
""")


# ============================================================
# 第 2 步：实现具体 Skill
# ============================================================
print("=" * 60)
print("第 2 步：实现几个实用 Skill")
print("=" * 60)


# ---- Skill 1：数学计算 ----
class MathSkill(Skill):
    name = "math"
    description = "数学计算能力，支持基本运算和科学计算"
    system_prompt = "你可以使用 calculator 工具执行数学计算。"

    def get_tools(self):
        return [{
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "执行数学表达式计算，支持 +, -, *, /, **, sqrt, sin, cos, pi 等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，如 '2**10' 或 'sqrt(144)'"
                        }
                    },
                    "required": ["expression"]
                }
            }
        }]

    def execute(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "calculator":
            expr = arguments["expression"]
            # 安全的数学环境
            safe_env = {
                "abs": abs, "round": round, "min": min, "max": max,
                "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
                "tan": math.tan, "pi": math.pi, "e": math.e,
                "log": math.log, "pow": pow,
            }
            try:
                result = eval(expr, {"__builtins__": {}}, safe_env)
                return str(result)
            except Exception as e:
                return f"计算错误: {e}"
        raise NotImplementedError(f"未知工具: {tool_name}")


# ---- Skill 2：日期时间 ----
class DateTimeSkill(Skill):
    name = "datetime"
    description = "获取当前日期时间，进行日期计算"
    system_prompt = "你可以使用 get_datetime 工具获取当前时间信息。"

    def get_tools(self):
        return [{
            "type": "function",
            "function": {
                "name": "get_datetime",
                "description": "获取当前日期和时间信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "输出格式：'date'(日期)、'time'(时间)、'full'(完整)、'timestamp'(时间戳)",
                            "enum": ["date", "time", "full", "timestamp"]
                        }
                    },
                    "required": ["format"]
                }
            }
        }]

    def execute(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "get_datetime":
            now = datetime.datetime.now()
            fmt = arguments.get("format", "full")
            if fmt == "date":
                return now.strftime("%Y-%m-%d")
            elif fmt == "time":
                return now.strftime("%H:%M:%S")
            elif fmt == "timestamp":
                return str(int(now.timestamp()))
            else:
                return now.strftime("%Y-%m-%d %H:%M:%S")
        raise NotImplementedError(f"未知工具: {tool_name}")


# ---- Skill 3：文本处理 ----
class TextSkill(Skill):
    name = "text"
    description = "文本处理能力，支持字数统计、大小写转换等"
    system_prompt = "你可以使用 text_tool 进行文本分析和处理。"

    def get_tools(self):
        return [{
            "type": "function",
            "function": {
                "name": "text_tool",
                "description": "文本处理工具：统计字数、字符数，或进行大小写转换",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "操作类型",
                            "enum": ["count_words", "count_chars", "to_upper", "to_lower", "reverse"]
                        },
                        "text": {
                            "type": "string",
                            "description": "要处理的文本"
                        }
                    },
                    "required": ["action", "text"]
                }
            }
        }]

    def execute(self, tool_name: str, arguments: dict) -> str:
        if tool_name == "text_tool":
            action = arguments["action"]
            text = arguments["text"]
            if action == "count_words":
                return str(len(text.split()))
            elif action == "count_chars":
                return str(len(text))
            elif action == "to_upper":
                return text.upper()
            elif action == "to_lower":
                return text.lower()
            elif action == "reverse":
                return text[::-1]
            return f"未知操作: {action}"
        raise NotImplementedError(f"未知工具: {tool_name}")


print("""
  已实现 3 个 Skill：
  ✅ MathSkill    - 数学计算 (calculator)
  ✅ DateTimeSkill - 日期时间 (get_datetime)
  ✅ TextSkill    - 文本处理 (text_tool)

  每个 Skill 都遵循相同的接口，可以自由组合。
""")


# ============================================================
# 第 3 步：Skill 注册中心
# ============================================================
print("=" * 60)
print("第 3 步：Skill Registry（技能注册中心）")
print("=" * 60)


class SkillRegistry:
    """
    技能注册中心 —— 管理所有可用的 Skill。

    职责：
    1. 注册/注销 Skill
    2. 汇总所有 Skill 的工具定义（提供给 LLM）
    3. 汇总所有 Skill 的 System Prompt 片段
    4. 路由工具调用到正确的 Skill
    """

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        # 工具名 → Skill 的映射，用于快速路由
        self._tool_map: dict[str, Skill] = {}

    def register(self, skill: Skill):
        """注册一个 Skill"""
        self._skills[skill.name] = skill
        for tool_def in skill.get_tools():
            tool_name = tool_def["function"]["name"]
            self._tool_map[tool_name] = skill
        print(f"  ✅ 已注册 Skill: {skill.name} ({skill.description})")

    def unregister(self, skill_name: str):
        """注销一个 Skill"""
        if skill_name in self._skills:
            skill = self._skills.pop(skill_name)
            for tool_def in skill.get_tools():
                tool_name = tool_def["function"]["name"]
                self._tool_map.pop(tool_name, None)
            print(f"  ❌ 已注销 Skill: {skill_name}")

    def get_all_tools(self) -> list[dict]:
        """获取所有已注册 Skill 的工具定义"""
        tools = []
        for skill in self._skills.values():
            tools.extend(skill.get_tools())
        return tools

    def get_system_prompt(self, base_prompt: str = "") -> str:
        """组合基础 System Prompt + 所有 Skill 的 prompt 片段"""
        parts = [base_prompt] if base_prompt else []
        for skill in self._skills.values():
            if skill.system_prompt:
                parts.append(skill.system_prompt)
        return "\n".join(parts)

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """将工具调用路由到对应的 Skill"""
        if tool_name not in self._tool_map:
            return f"错误：未找到工具 '{tool_name}'"
        return self._tool_map[tool_name].execute(tool_name, arguments)

    def list_skills(self) -> list[str]:
        """列出所有已注册的 Skill 名称"""
        return list(self._skills.keys())


# 创建注册中心并注册 Skill
registry = SkillRegistry()
registry.register(MathSkill())
registry.register(DateTimeSkill())
registry.register(TextSkill())

print(f"\n  已注册 {len(registry.list_skills())} 个 Skill: {registry.list_skills()}")
print(f"  共提供 {len(registry.get_all_tools())} 个工具")


# ============================================================
# 第 4 步：基于 Skill 的 Agent
# ============================================================
print("\n" + "=" * 60)
print("第 4 步：用 Skill 驱动的 Agent")
print("=" * 60)


def skill_agent(user_input: str, registry: SkillRegistry, max_iterations: int = 10):
    """
    基于 Skill 系统的 Agent。

    和第四章的 ReAct Agent 核心逻辑一样，
    区别在于工具列表和执行都由 SkillRegistry 提供。
    """
    # 1. 组合 System Prompt
    system_prompt = registry.get_system_prompt(
        "你是一个多功能 AI 助手。根据用户需求，选择合适的工具来完成任务。"
    )

    # 2. 获取所有可用工具
    tools = registry.get_all_tools()

    # 3. 初始化消息
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    print(f"\n  用户: {user_input}")
    print(f"  可用工具: {[t['function']['name'] for t in tools]}")

    # 4. Agent 循环
    for i in range(max_iterations):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
        )

        msg = response.choices[0].message
        messages.append(msg)

        # 没有工具调用 → 输出最终回复
        if not msg.tool_calls:
            print(f"  助手: {msg.content}")
            return msg.content

        # 执行工具调用
        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"  🔧 调用 [{name}]: {args}")

            # 通过 Registry 路由到正确的 Skill
            result = registry.execute_tool(name, args)
            print(f"  📎 结果: {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "达到最大迭代次数"


# ============================================================
# 第 5 步：测试 Skill Agent
# ============================================================
print("\n" + "=" * 60)
print("第 5 步：测试 —— 让 Agent 自动选择 Skill")
print("=" * 60)

# 测试 1：涉及数学
print("\n--- 测试 1：数学计算 ---")
skill_agent("计算 2 的 20 次方", registry)

# 测试 2：涉及日期
print("\n--- 测试 2：日期查询 ---")
skill_agent("现在几点了？", registry)

# 测试 3：涉及文本
print("\n--- 测试 3：文本处理 ---")
skill_agent("帮我统计这段文字有多少个字符：Hello World 你好世界", registry)

# 测试 4：混合使用多个 Skill
print("\n--- 测试 4：跨 Skill 协作 ---")
skill_agent("把当前日期转成大写英文", registry)


# ============================================================
# 第 6 步：动态管理 Skill（热插拔）
# ============================================================
print("\n" + "=" * 60)
print("第 6 步：动态 Skill 管理 —— 热插拔")
print("=" * 60)

print("\n  当前 Skills:", registry.list_skills())

# 运行时注销某个 Skill
registry.unregister("text")
print("  注销 text 后:", registry.list_skills())
print(f"  剩余工具: {[t['function']['name'] for t in registry.get_all_tools()]}")

# 运行时重新注册
registry.register(TextSkill())
print("  重新注册后:", registry.list_skills())

print("""
  ↑ 热插拔能力让 Agent 可以：
  - 按需加载 Skill（节省 Token、减少干扰）
  - 根据用户权限动态启用/禁用功能
  - 支持插件系统（第三方开发 Skill）
""")


# ============================================================
# 本章小结
# ============================================================
print("=" * 60)
print("""
本章小结：

1. Skill 是 Agent 能力的最小模块化单元
2. 每个 Skill 包含：描述 + System Prompt + 工具定义 + 执行逻辑
3. SkillRegistry 负责注册、发现、路由
4. Agent 通过 Registry 获取工具和 Prompt，不需要知道具体 Skill
5. 支持运行时热插拔，可以灵活增减能力

这种设计模式在主流 Agent 框架中广泛使用：
- Claude Code 的 Tool 模块
- OpenClaw 的 Skill 系统
- LangChain 的 Tool / Toolkit 抽象

下一章，我们将学习 MCP（Model Context Protocol）——
让不同 Agent 和工具之间通过标准协议互联互通！
""")
