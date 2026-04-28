"""
========================================
第七章：完整 Coding Agent —— 大结局
========================================

这是最终章。我们将前六章的所有知识整合，
构建一个完整的、可交互使用的 Coding Agent。

它具备以下能力（和 Claude Code 的核心能力一致）：
✅ 阅读文件
✅ 创建/编辑文件
✅ 执行 Shell 命令
✅ 列出目录
✅ 搜索文件内容
✅ 多轮对话记忆
✅ 上下文管理
✅ 流式输出
✅ 安全限制

架构图：
    ┌──────────────────────────────────────────────┐
    │                 Coding Agent                  │
    │                                               │
    │  ┌─────────────┐     ┌────────────────────┐  │
    │  │ System Prompt│     │   Memory Manager   │  │
    │  │ (Agent 灵魂) │     │ (上下文/摘要/Token)│  │
    │  └──────┬──────┘     └────────┬───────────┘  │
    │         │                      │              │
    │         ▼                      ▼              │
    │  ┌─────────────────────────────────────────┐ │
    │  │              Agent Loop                  │ │
    │  │  while True:                             │ │
    │  │    response = LLM(messages + tools)      │ │
    │  │    if no tool_calls: break               │ │
    │  │    for tool in tool_calls:               │ │
    │  │      result = execute(tool)              │ │
    │  │      messages.append(result)             │ │
    │  └─────────────────────────────────────────┘ │
    │         │                                     │
    │         ▼                                     │
    │  ┌─────────────────────────────────────────┐ │
    │  │              Tool Suite                   │ │
    │  │  read_file | write_file | edit_file      │ │
    │  │  list_files | search_files | run_command  │ │
    │  └─────────────────────────────────────────┘ │
    └──────────────────────────────────────────────┘
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
import httpx
from openai import OpenAI

# ============================================================
# 配置
# ============================================================

MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
print(f"当前使用模型: {MODEL}")
MAX_TOKENS = 8000       # 上下文 token 预算
MAX_ITERATIONS = 20     # 单次任务最大循环轮数
COMMAND_TIMEOUT = 30    # 命令执行超时（秒）

# 工作目录
WORKSPACE = Path(__file__).parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)

client = OpenAI(http_client=httpx.Client(verify=False))

# ============================================================
# 工具实现
# ============================================================

def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """读取文件内容，可选指定行范围"""
    filepath = (WORKSPACE / path).resolve()
    if not str(filepath).startswith(str(WORKSPACE.resolve())):
        return "❌ 安全限制：不允许访问工作目录外的文件"
    if not filepath.exists():
        return f"❌ 文件不存在：{path}"
    try:
        lines = filepath.read_text(encoding="utf-8").split("\n")
        # 处理行范围
        if start_line > 0:
            s = max(0, start_line - 1)
            e = end_line if end_line > 0 else len(lines)
            lines = lines[s:e]
            offset = s
        else:
            offset = 0
        # 添加行号
        numbered = [f"{i+offset+1:4d} │ {line}" for i, line in enumerate(lines)]
        result = "\n".join(numbered)
        return f"📄 {path}（共 {len(lines)} 行）\n{result}"
    except Exception as e:
        return f"❌ 读取错误：{e}"


def write_file(path: str, content: str) -> str:
    """创建或覆盖文件"""
    filepath = (WORKSPACE / path).resolve()
    if not str(filepath).startswith(str(WORKSPACE.resolve())):
        return "❌ 安全限制：不允许访问工作目录外的文件"
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        line_count = content.count("\n") + 1
        return f"✅ 已写入 {path}（{line_count} 行，{len(content)} 字节）"
    except Exception as e:
        return f"❌ 写入错误：{e}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    """
    编辑文件：将 old_string 替换为 new_string。
    这是 Claude Code 的核心编辑方式 —— 精确替换而非整文件覆盖。
    """
    filepath = (WORKSPACE / path).resolve()
    if not str(filepath).startswith(str(WORKSPACE.resolve())):
        return "❌ 安全限制：不允许访问工作目录外的文件"
    if not filepath.exists():
        return f"❌ 文件不存在：{path}"
    try:
        content = filepath.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"❌ 未找到要替换的内容。请确认 old_string 完全匹配文件中的内容。"
        if count > 1:
            return f"⚠️ 找到 {count} 处匹配，请提供更精确的内容以确保只匹配一处。"
        new_content = content.replace(old_string, new_string, 1)
        filepath.write_text(new_content, encoding="utf-8")
        return f"✅ 已编辑 {path}：替换了 1 处内容"
    except Exception as e:
        return f"❌ 编辑错误：{e}"


def list_files(directory: str = ".") -> str:
    """列出目录内容"""
    dirpath = (WORKSPACE / directory).resolve()
    if not str(dirpath).startswith(str(WORKSPACE.resolve())):
        return "❌ 安全限制：不允许访问工作目录外的文件"
    if not dirpath.exists():
        return f"❌ 目录不存在：{directory}"
    try:
        entries = []
        for entry in sorted(dirpath.rglob("*")):
            if entry.is_file():
                rel = entry.relative_to(WORKSPACE)
                size = entry.stat().st_size
                entries.append(f"  📄 {rel}  ({size} B)")
            elif entry.is_dir():
                rel = entry.relative_to(WORKSPACE)
                entries.append(f"  📁 {rel}/")
        if not entries:
            return f"📁 {directory}/ (空目录)"
        return f"📁 {directory}/\n" + "\n".join(entries[:50])
    except Exception as e:
        return f"❌ 列出错误：{e}"


def search_files(pattern: str, directory: str = ".") -> str:
    """在文件中搜索文本（类似 grep）"""
    dirpath = (WORKSPACE / directory).resolve()
    if not str(dirpath).startswith(str(WORKSPACE.resolve())):
        return "❌ 安全限制"
    results = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return f"❌ 无效的正则表达式：{pattern}"

    try:
        for filepath in dirpath.rglob("*"):
            if not filepath.is_file():
                continue
            # 跳过二进制文件
            try:
                text = filepath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for i, line in enumerate(text.split("\n"), 1):
                if regex.search(line):
                    rel = filepath.relative_to(WORKSPACE)
                    results.append(f"  {rel}:{i}: {line.strip()}")
                    if len(results) >= 30:
                        results.append("  ... (结果过多，已截断)")
                        return f"🔍 搜索 '{pattern}'：找到 30+ 处匹配\n" + "\n".join(results)
        if not results:
            return f"🔍 搜索 '{pattern}'：未找到匹配"
        return f"🔍 搜索 '{pattern}'：找到 {len(results)} 处匹配\n" + "\n".join(results)
    except Exception as e:
        return f"❌ 搜索错误：{e}"


def run_command(command: str) -> str:
    """执行 Shell 命令"""
    # 基本安全检查
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/"]
    if any(d in command for d in dangerous):
        return "❌ 安全限制：禁止执行危险命令"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n" if output else "") + f"[stderr] {result.stderr}"
        if result.returncode != 0:
            output += f"\n[退出码 {result.returncode}]"
        output = output.strip() or "(无输出)"
        # 截断过长输出
        if len(output) > 3000:
            output = output[:3000] + "\n... (输出已截断)"
        return f"⚡ $ {command}\n{output}"
    except subprocess.TimeoutExpired:
        return f"❌ 命令超时（{COMMAND_TIMEOUT}秒）：{command}"
    except Exception as e:
        return f"❌ 执行错误：{e}"


# ============================================================
# 工具注册表
# ============================================================

TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "search_files": search_files,
    "run_command": run_command,
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。返回带行号的文本。可选指定行范围。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作目录）"},
                    "start_line": {"type": "integer", "description": "起始行号（可选，从 1 开始）"},
                    "end_line": {"type": "integer", "description": "结束行号（可选）"},
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建新文件或覆盖已有文件的全部内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件的完整内容"},
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件：将 old_string 精确替换为 new_string。old_string 必须完全匹配文件中的内容（包括空格和缩进），且只能匹配一处。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_string": {"type": "string", "description": "要替换的原始文本（必须精确匹配）"},
                    "new_string": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "递归列出目录中的所有文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "目录路径，默认 '.'"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "在文件中搜索匹配正则表达式的内容（类似 grep）",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "搜索的正则表达式"},
                    "directory": {"type": "string", "description": "搜索范围，默认 '.'"},
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在工作目录中执行 shell 命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                },
                "required": ["command"]
            }
        }
    },
]

# ============================================================
# System Prompt（Agent 的灵魂）
# ============================================================

SYSTEM_PROMPT = """你是一个专业的 AI 编程助手（Coding Agent），运行在用户的计算机上。

## 你的能力
你可以通过工具来：
- 阅读和搜索文件
- 创建和编辑文件
- 执行 Shell 命令

## 工作原则
1. **先了解再动手**：修改代码前，先阅读相关文件理解上下文
2. **小步快跑**：复杂任务分解为小步骤，每步做完验证
3. **精确编辑**：优先使用 edit_file 精确替换，避免整文件覆盖
4. **验证结果**：写完代码后，用 run_command 执行验证

## 编辑规则
- 使用 write_file 创建新文件
- 使用 edit_file 修改已有文件（更安全、更精确）
- edit_file 的 old_string 必须完全匹配文件内容

## 回复风格
- 简洁明了，不废话
- 先说做什么，再做
- 出错时分析原因，不重复同样的错误"""

# ============================================================
# 记忆管理器（复用第六章）
# ============================================================

class Memory:
    def __init__(self):
        self.messages = []
        self.summary = ""

    def get_messages(self):
        result = []
        sys_content = SYSTEM_PROMPT
        if self.summary:
            sys_content += f"\n\n## 之前的对话摘要\n{self.summary}"
        result.append({"role": "system", "content": sys_content})

        for msg in self.messages:
            if isinstance(msg, dict):
                result.append(msg)
            else:
                d = {"role": msg.role}
                if msg.content:
                    d["content"] = msg.content
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    d["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(d)
        return result

    def add(self, msg):
        self.messages.append(msg)

    def compress_if_needed(self):
        """简单的压缩策略"""
        total_chars = sum(
            len(json.dumps(m, ensure_ascii=False)) if isinstance(m, dict)
            else len(str(m))
            for m in self.messages
        )
        if total_chars < 30000:
            return
        keep = 8
        if len(self.messages) <= keep:
            return
        old = self.messages[:-keep]
        self.messages = self.messages[-keep:]
        try:
            old_text = json.dumps(
                [m if isinstance(m, dict) else {"content": str(m)} for m in old],
                ensure_ascii=False
            )[:5000]
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "用 200 字以内概括以下对话的关键信息："},
                    {"role": "user", "content": f"已有摘要: {self.summary or '无'}\n新内容: {old_text}"}
                ],
                temperature=0,
                max_tokens=300,
            )
            self.summary = resp.choices[0].message.content
            print(f"  💾 对话已压缩")
        except Exception:
            pass

# ============================================================
# Agent 主循环
# ============================================================

def agent_run(user_input: str, memory: Memory) -> str:
    """单次用户输入的 Agent 执行循环"""

    memory.add({"role": "user", "content": user_input})

    for iteration in range(MAX_ITERATIONS):
        memory.compress_if_needed()

        # 调用 LLM（流式）
        stream = client.chat.completions.create(
            model=MODEL,
            messages=memory.get_messages(),
            tools=TOOLS_SCHEMA,
            temperature=0,
            stream=True,
        )

        # 收集流式响应
        content_parts = []
        tool_calls_data = {}  # id -> {name, arguments}
        current_tc_index = None

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # 文本内容
            if delta.content:
                print(delta.content, end="", flush=True)
                content_parts.append(delta.content)

            # 工具调用（流式拼接）
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_data:
                        tool_calls_data[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": ""
                        }
                    if tc_delta.id:
                        tool_calls_data[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_data[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

        full_content = "".join(content_parts)

        # 没有工具调用 → 任务完成
        if not tool_calls_data:
            if full_content:
                print()  # 换行
            memory.add({"role": "assistant", "content": full_content})
            return full_content

        # 有工具调用 → 构建消息并执行
        if full_content:
            print()  # 换行

        # 构建助手消息
        assistant_msg = {"role": "assistant", "content": full_content or None}
        assistant_msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]}
            }
            for tc in tool_calls_data.values()
        ]
        memory.add(assistant_msg)

        # 执行每个工具
        for tc in tool_calls_data.values():
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            # 美观打印
            args_display = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
            print(f"\n  🔧 {name}({args_display})")

            if name in TOOL_MAP:
                result = TOOL_MAP[name](**args)
            else:
                result = f"❌ 未知工具：{name}"

            # 截断长输出
            if len(result) > 3000:
                result = result[:3000] + "\n... (输出已截断)"

            # 显示结果（缩进）
            for line in result.split("\n")[:20]:
                print(f"  {line}")
            if result.count("\n") > 20:
                print(f"  ... (显示了前 20 行)")

            memory.add({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        # 继续下一轮循环...

    return "⚠️ 达到最大迭代次数"

# ============================================================
# 交互式主程序
# ============================================================

def main():
    print("""
╔══════════════════════════════════════════════════╗
║            🤖 AI Coding Agent                    ║
║                                                  ║
║  一个从零构建的编程助手 Agent                      ║
║  参考 Claude Code / OpenClaw 核心架构              ║
║                                                  ║
║  命令:                                           ║
║    quit     - 退出                               ║
║    clear    - 清空对话历史                         ║
║                                                  ║
║  工作目录: workspace/                             ║
╚══════════════════════════════════════════════════╝
""")
    print(f"  模型: {MODEL}")
    print(f"  工作目录: {WORKSPACE}")
    print()

    memory = Memory()

    while True:
        try:
            user_input = input("🧑 你: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("再见！")
            break
        if user_input.lower() == "clear":
            memory = Memory()
            print("✅ 对话已清空\n")
            continue

        print()
        print("🤖 ", end="")
        agent_run(user_input, memory)
        print()


if __name__ == "__main__":
    # 如果直接运行，进入交互模式
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # 演示模式：自动执行几个任务
        print("=" * 60)
        print("🎬 演示模式")
        print("=" * 60)
        memory = Memory()

        demos = [
            "帮我创建一个 Python 项目：一个简单的 TODO 应用（命令行版本），包含添加、列出、完成、删除功能。创建好后运行测试看看。",
        ]
        for task in demos:
            print(f"\n🧑 你: {task}\n")
            print("🤖 ", end="")
            agent_run(task, memory)
            print("\n")
    else:
        main()
