"""
========================================
第八章：Skill 系统 —— 用 Markdown 给 Agent 扩展能力
========================================

前七章我们已经构建了一个完整的 Coding Agent。
但真实产品里的 Skill 通常不是写死在 Python 类里，
而是一个可被 Agent 按需读取的 Markdown 文件。

典型结构类似这样：

    skills/
      math/SKILL.md
      datetime/SKILL.md
      text/SKILL.md

每个 SKILL.md 是一份“能力说明书”：
- 什么时候应该使用这个 Skill
- 使用这个 Skill 时要遵守什么规则
- 这个 Skill 会启用哪些底层工具
- 示例和注意事项

为什么要把 Skill 写成 Markdown？
1. 低耦合 —— 改 Skill 不需要改 Agent 主循环
2. 省 Token —— 只在需要时读取完整 Skill 内容
3. 易维护 —— 非程序员也能修改能力说明
4. 可组合 —— 一个 Agent 可以按任务动态加载多个 Skill

架构：
    ┌──────────────────────────────────────────┐
    │                Agent Core                 │
    │                                          │
    │  启动时只扫描索引：name / description      │
    │                │                         │
    │                ▼                         │
    │        list_skills / load_skill          │
    │                │                         │
    │                ▼                         │
    │       读取 skills/*/SKILL.md             │
    │                │                         │
    │                ▼                         │
    │       根据 Skill 开放对应工具              │
    │                │                         │
    │                ▼                         │
    │              ReAct Loop                  │
    └──────────────────────────────────────────┘

本章会实现一个更接近 Claude Code / Cursor / OpenClaw 的 Skill 模型：
Agent 先发现 Skill，再按需读取 Markdown，然后使用被 Skill 启用的工具。
"""

import datetime as dt
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from openai import OpenAI, OpenAIError

MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
USE_REAL_LLM = os.environ.get("SKILL_DEMO_USE_LLM") == "1"
client: OpenAI | None = None
ROOT = Path(__file__).parent
SKILLS_DIR = ROOT / "skills"

print(f"当前使用模型: {MODEL}\n")
if not USE_REAL_LLM:
    print("当前演示模式: 本地模拟 LLM 决策（设置 SKILL_DEMO_USE_LLM=1 可调用真实模型）\n")


# ============================================================
# 第 1 步：Skill 是 Markdown 文件，不是 Python 类
# ============================================================
print("=" * 60)
print("第 1 步：Markdown Skill 的文件结构")
print("=" * 60)

print("""
  本章使用真实的 markdown 文件作为 Skill：

    skills/math/SKILL.md
    skills/datetime/SKILL.md
    skills/text/SKILL.md

  每个 SKILL.md 包含两部分：

  1. Frontmatter：给程序读取的机器索引

     ---
     name: math
     description: 数学计算能力，适合精确计算、单位换算、公式求值
     tools: calculator
     ---

  2. Markdown 正文：给 Agent 阅读的行为说明

     # Math Skill
     ## When to use
     ...
     ## Instructions
     ...

  真实系统一般不会一开始把所有 Skill 正文塞进 system prompt，
  而是先扫描 name / description，等任务需要时再读取完整 markdown。
""")


# ============================================================
# 第 2 步：读取 Markdown Skill，并解析轻量元数据
# ============================================================
print("=" * 60)
print("第 2 步：SkillLoader —— 扫描和读取 SKILL.md")
print("=" * 60)


@dataclass
class SkillDocument:
    """一个从 SKILL.md 读取出来的 Skill 文档。"""

    name: str
    description: str
    tool_names: list[str]
    path: Path
    content: str


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析非常轻量的 YAML frontmatter，只支持 key: value。"""
    if not text.startswith("---\n"):
        return {}, text

    match = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    raw_meta, body = match.groups()
    metadata: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, body.strip()


class SkillLoader:
    """负责发现、索引和按需读取 markdown Skill。"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._index: dict[str, SkillDocument] = {}
        self._loaded: dict[str, SkillDocument] = {}
        self.refresh()

    def refresh(self):
        """扫描 skills/*/SKILL.md，建立轻量索引。"""
        self._index.clear()
        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
            text = skill_file.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(text)
            name = metadata.get("name") or skill_file.parent.name
            description = metadata.get("description", "")
            tools = [
                item.strip()
                for item in metadata.get("tools", "").split(",")
                if item.strip()
            ]
            self._index[name] = SkillDocument(
                name=name,
                description=description,
                tool_names=tools,
                path=skill_file,
                content=body,
            )

    def list_skills(self) -> str:
        """返回轻量 Skill 索引，不返回完整正文。"""
        if not self._index:
            return f"未发现 Skill。请检查目录：{self.skills_dir}"

        lines = []
        for skill in self._index.values():
            loaded = "已加载" if skill.name in self._loaded else "未加载"
            tools = ", ".join(skill.tool_names) or "无"
            lines.append(f"- {skill.name} ({loaded})：{skill.description}；tools: {tools}")
        return "可用 Skill：\n" + "\n".join(lines)

    def load_skill(self, name: str) -> str:
        """读取完整 SKILL.md，并标记其工具可用。"""
        if name not in self._index:
            return f"错误：未找到 Skill '{name}'。请先调用 list_skills 查看可用项。"

        skill = self._index[name]
        self._loaded[name] = skill
        tool_text = ", ".join(skill.tool_names) or "无"
        return f"已加载 Skill: {skill.name}\n启用工具: {tool_text}\n\n{skill.content}"

    def loaded_tool_names(self) -> set[str]:
        """返回所有已加载 Skill 启用的工具名。"""
        names: set[str] = set()
        for skill in self._loaded.values():
            names.update(skill.tool_names)
        return names

    def loaded_skill_names(self) -> list[str]:
        return list(self._loaded.keys())

    def clear_loaded(self):
        """清空当前会话中已加载的 Skill。"""
        self._loaded.clear()


loader = SkillLoader(SKILLS_DIR)

print(f"  Skill 目录: {SKILLS_DIR}")
print("  扫描结果:")
for line in loader.list_skills().splitlines():
    print(f"  {line}")


# ============================================================
# 第 3 步：底层工具仍由程序实现，但由 Markdown Skill 启用
# ============================================================
print("\n" + "=" * 60)
print("第 3 步：工具实现和动态暴露")
print("=" * 60)


def calculator(expression: str) -> str:
    """执行数学表达式。"""
    safe_env = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pi": math.pi,
        "e": math.e,
        "log": math.log,
        "pow": pow,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, safe_env)
        return str(result)
    except Exception as exc:
        return f"计算错误: {exc}"


def get_datetime(format: str = "full") -> str:
    """获取日期时间。"""
    now = dt.datetime.now()
    if format == "date":
        return now.strftime("%Y-%m-%d")
    if format == "time":
        return now.strftime("%H:%M:%S")
    if format == "timestamp":
        return str(int(now.timestamp()))
    if format == "english_date":
        return now.strftime("%A, %B %d, %Y")
    return now.strftime("%Y-%m-%d %H:%M:%S")


def text_tool(action: str, text: str) -> str:
    """文本处理工具。"""
    if action == "count_words":
        return str(len(text.split()))
    if action == "count_chars":
        return str(len(text))
    if action == "to_upper":
        return text.upper()
    if action == "to_lower":
        return text.lower()
    if action == "reverse":
        return text[::-1]
    return f"未知操作: {action}"


def list_skills() -> str:
    return loader.list_skills()


def load_skill(name: str) -> str:
    return loader.load_skill(name)


TOOL_MAP = {
    "list_skills": list_skills,
    "load_skill": load_skill,
    "calculator": calculator,
    "get_datetime": get_datetime,
    "text_tool": text_tool,
}

DISCOVERY_TOOL_SCHEMAS = {
    "list_skills": {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出可用 Skill 的名称、描述和会启用的工具。不会读取完整 Skill 正文。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "load_skill": {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "按名称读取一个 SKILL.md 的完整内容，并启用它声明的工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill 名称，例如 math、datetime、text"},
                },
                "required": ["name"],
            },
        },
    },
}

SKILL_TOOL_SCHEMAS = {
    "calculator": {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行数学表达式计算。只有加载 math Skill 后才可用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '2**10'、'sqrt(144)'、'sin(pi/2)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    "get_datetime": {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "获取当前日期和时间。只有加载 datetime Skill 后才可用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "输出格式",
                        "enum": ["date", "time", "full", "timestamp", "english_date"],
                    }
                },
                "required": ["format"],
            },
        },
    },
    "text_tool": {
        "type": "function",
        "function": {
            "name": "text_tool",
            "description": "文本统计和转换。只有加载 text Skill 后才可用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作类型",
                        "enum": ["count_words", "count_chars", "to_upper", "to_lower", "reverse"],
                    },
                    "text": {"type": "string", "description": "要处理的文本"},
                },
                "required": ["action", "text"],
            },
        },
    },
}


def available_tools() -> list[dict]:
    """根据当前已加载的 Skill 动态组装工具列表。"""
    schemas = [DISCOVERY_TOOL_SCHEMAS["list_skills"], DISCOVERY_TOOL_SCHEMAS["load_skill"]]
    for tool_name in sorted(loader.loaded_tool_names()):
        schema = SKILL_TOOL_SCHEMAS.get(tool_name)
        if schema:
            schemas.append(schema)
    return schemas


print("""
  注意这里的分层：

  - Python 负责实现真正的工具函数，例如 calculator / text_tool
  - Markdown Skill 负责告诉 Agent 什么时候用、怎么用、有什么约束
  - Agent 未加载某个 Skill 前，不会暴露该 Skill 声明的工具

  这和前一版“每个 Skill 是 Python 类”的教程不同：
  Skill 的主要载体变成了可读、可编辑、可按需加载的 SKILL.md。
""")


# ============================================================
# 第 4 步：基于 Markdown Skill 的 Agent Loop
# ============================================================
print("=" * 60)
print("第 4 步：让 Agent 按需读取 Skill")
print("=" * 60)

SYSTEM_PROMPT = """你是一个多功能 AI 助手，支持按需加载 Markdown Skill。

工作方式：
1. 你启动时只知道可以调用 list_skills 和 load_skill。
2. 遇到需要专门能力的任务时，先调用 list_skills 查看可用 Skill。
3. 选择合适的 Skill 后调用 load_skill 读取完整 SKILL.md。
4. 读取 Skill 后，遵守其中的说明，并使用新启用的工具完成任务。
5. 如果一个任务需要多个能力，可以加载多个 Skill。

不要假装已经读取了某个 Skill。需要使用某个 Skill 的规则时，必须先 load_skill。
"""


def execute_and_print_tool(name: str, args: dict) -> str:
    """执行工具并打印统一的演示日志。"""
    print(f"  🔧 调用 [{name}]: {args}")
    result = TOOL_MAP.get(name, lambda **_: f"未知工具: {name}")(**args)
    print(f"  📎 结果: {result[:500]}{'...' if len(result) > 500 else ''}")
    return result


def scripted_skill_agent(user_input: str) -> str:
    """
    用本地规则模拟 LLM 的工具选择。

    真实教程里这里由 LLM 决定调用 list_skills / load_skill / 具体工具。
    但自动跑 4 个 demo 会产生多轮 API 请求，容易触发 429。
    默认使用这个稳定版本，保证教程脚本可以直接执行完。
    """
    loader.clear_loaded()

    print(f"\n  用户: {user_input}")
    print(f"  当前已加载 Skill: {loader.loaded_skill_names() or ['无']}")
    print(f"  当前可用工具: {[tool['function']['name'] for tool in available_tools()]}")

    execute_and_print_tool("list_skills", {})

    if "2 的 20 次方" in user_input:
        execute_and_print_tool("load_skill", {"name": "math"})
        print(f"  当前已加载 Skill: {loader.loaded_skill_names()}")
        print(f"  当前可用工具: {[tool['function']['name'] for tool in available_tools()]}")
        result = execute_and_print_tool("calculator", {"expression": "2**20"})
        answer = f"2 的 20 次方是 {int(result):,}。"
        print(f"  助手: {answer}")
        return answer

    if "现在几点" in user_input:
        execute_and_print_tool("load_skill", {"name": "datetime"})
        print(f"  当前已加载 Skill: {loader.loaded_skill_names()}")
        print(f"  当前可用工具: {[tool['function']['name'] for tool in available_tools()]}")
        result = execute_and_print_tool("get_datetime", {"format": "time"})
        answer = f"现在是 {result}。"
        print(f"  助手: {answer}")
        return answer

    if "多少个字符" in user_input:
        execute_and_print_tool("load_skill", {"name": "text"})
        print(f"  当前已加载 Skill: {loader.loaded_skill_names()}")
        print(f"  当前可用工具: {[tool['function']['name'] for tool in available_tools()]}")
        text = user_input.split("：", 1)[-1]
        result = execute_and_print_tool("text_tool", {"action": "count_chars", "text": text})
        answer = f"这段文字共有 {result} 个字符。"
        print(f"  助手: {answer}")
        return answer

    if "当前日期" in user_input and "大写英文" in user_input:
        execute_and_print_tool("load_skill", {"name": "datetime"})
        date_text = execute_and_print_tool("get_datetime", {"format": "english_date"})
        execute_and_print_tool("load_skill", {"name": "text"})
        print(f"  当前已加载 Skill: {loader.loaded_skill_names()}")
        print(f"  当前可用工具: {[tool['function']['name'] for tool in available_tools()]}")
        result = execute_and_print_tool("text_tool", {"action": "to_upper", "text": date_text})
        answer = f"当前日期的大写英文是：{result}。"
        print(f"  助手: {answer}")
        return answer

    answer = "这个任务不需要加载额外 Skill，可以直接回答。"
    print(f"  助手: {answer}")
    return answer


def real_llm_skill_agent(user_input: str, max_iterations: int = 10) -> str:
    """使用真实 LLM tool calling 的版本。"""
    global client

    if client is None:
        client = OpenAI(http_client=httpx.Client(verify=False))

    loader.clear_loaded()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    print(f"\n  用户: {user_input}")

    for _ in range(max_iterations):
        tool_names = [tool["function"]["name"] for tool in available_tools()]
        print(f"  当前已加载 Skill: {loader.loaded_skill_names() or ['无']}")
        print(f"  当前可用工具: {tool_names}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=available_tools(),
            temperature=0,
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            print(f"  助手: {msg.content}")
            return msg.content or ""

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result = execute_and_print_tool(name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "达到最大迭代次数"


def skill_agent(user_input: str, max_iterations: int = 10) -> str:
    """演示一个会按需加载 Markdown Skill 的 Agent。"""
    if not USE_REAL_LLM:
        return scripted_skill_agent(user_input)

    try:
        return real_llm_skill_agent(user_input, max_iterations=max_iterations)
    except OpenAIError as exc:
        print(f"  ⚠️ 模型调用失败，切换到本地模拟流程继续演示：{exc}")
        return scripted_skill_agent(user_input)


# ============================================================
# 第 5 步：测试 —— Agent 先加载 Skill，再使用工具
# ============================================================
print("\n" + "=" * 60)
print("第 5 步：测试 Markdown Skill Agent")
print("=" * 60)

print("\n--- 测试 1：数学任务，应该加载 math Skill ---")
skill_agent("计算 2 的 20 次方")

print("\n--- 测试 2：日期任务，应该加载 datetime Skill ---")
skill_agent("现在几点了？")

print("\n--- 测试 3：文本任务，应该加载 text Skill ---")
skill_agent("帮我统计这段文字有多少个字符：Hello World 你好世界")

print("\n--- 测试 4：跨 Skill 协作，应该加载 datetime + text ---")
skill_agent("把当前日期转成大写英文")


# ============================================================
# 第 6 步：动态加载和 Token 控制
# ============================================================
print("\n" + "=" * 60)
print("第 6 步：为什么要按需加载")
print("=" * 60)

all_skill_chars = sum(len(skill.content) for skill in loader._index.values())
loaded_skill_chars = sum(len(skill.content) for skill in loader._loaded.values())

print(f"""
  Skill 索引只包含 name / description / tools，通常很短。
  完整 SKILL.md 只有在任务需要时才读进上下文。

  本次演示中：
  - 全部 Skill 正文字符数: {all_skill_chars}
  - 已加载 Skill 正文字符数: {loaded_skill_chars}
  - 已加载 Skill: {loader.loaded_skill_names()}

  当 Skill 很多时，这个差异会非常大：
  Agent 不必背着所有能力说明跑每一次请求，
  只在需要某项能力时读取对应 markdown。
""")


# ============================================================
# 本章小结
# ============================================================
print("=" * 60)
print("""
本章小结：

1. 更常见的 Skill 形态是 SKILL.md，而不是写死的 Python 类
2. Agent 启动时只扫描轻量索引：name / description / tools
3. 任务需要时，Agent 调用 load_skill 读取完整 Markdown 说明
4. Skill 被加载后，Agent 才获得它声明的底层工具
5. Markdown 负责“怎么判断、怎么使用、有什么约束”
6. Python 负责真正执行工具逻辑，二者解耦

这就是很多现代 Agent 产品的 Skill / Prompt Pack / Tool Guide 设计思路：
把能力说明写成可维护的文档，让 Agent 在运行时按需读取。

下一章，我们将学习 MCP（Model Context Protocol）——
让不同 Agent 和工具之间通过标准协议互联互通！
""")
