"""
========================================
第五章：实用工具集 —— 文件操作与命令执行
========================================

前面的工具（计算器、天气）只是演示用。
真正的 Coding Agent（如 Claude Code）最核心的能力是：
1. 读取文件 —— 理解项目代码
2. 写入/编辑文件 —— 修改代码
3. 执行命令 —— 运行测试、安装依赖等

本章我们实现这三个核心工具，让 Agent 能真正操作文件系统。

安全考虑：
- 文件操作限制在工作目录内（防止路径穿越）
- 命令执行有超时限制
- 写入操作需要确认（可选）
"""

import json
import os
import subprocess
import httpx
from pathlib import Path
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# 工作目录 —— 所有文件操作限制在这个目录内
WORKSPACE = Path(__file__).parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)

# ============================================================
# 第 1 步：实现核心工具函数
# ============================================================

def read_file(path: str) -> str:
    """读取文件内容"""
    filepath = (WORKSPACE / path).resolve()
    # 安全检查：防止路径穿越（如 ../../etc/passwd）
    if not str(filepath).startswith(str(WORKSPACE.resolve())):
        return "错误：不允许访问工作目录外的文件"
    if not filepath.exists():
        return f"错误：文件 {path} 不存在"
    try:
        content = filepath.read_text(encoding="utf-8")
        # 添加行号，方便 LLM 定位
        lines = content.split("\n")
        numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
    except Exception as e:
        return f"读取错误：{e}"


def write_file(path: str, content: str) -> str:
    """写入文件（创建或覆盖）"""
    filepath = (WORKSPACE / path).resolve()
    if not str(filepath).startswith(str(WORKSPACE.resolve())):
        return "错误：不允许访问工作目录外的文件"
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return f"成功写入 {path}（{len(content)} 字节）"
    except Exception as e:
        return f"写入错误：{e}"


def list_files(directory: str = ".") -> str:
    """列出目录内容"""
    dirpath = (WORKSPACE / directory).resolve()
    if not str(dirpath).startswith(str(WORKSPACE.resolve())):
        return "错误：不允许访问工作目录外的文件"
    if not dirpath.exists():
        return f"错误：目录 {directory} 不存在"
    try:
        entries = []
        for entry in sorted(dirpath.iterdir()):
            rel = entry.relative_to(WORKSPACE)
            suffix = "/" if entry.is_dir() else f"  ({entry.stat().st_size} bytes)"
            entries.append(f"  {rel}{suffix}")
        return "\n".join(entries) if entries else "(空目录)"
    except Exception as e:
        return f"列出错误：{e}"


def run_command(command: str) -> str:
    """执行 shell 命令（限制在工作目录内）"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=30,  # 30 秒超时
        )
        output = ""
        if result.stdout:
            output += f"[stdout]\n{result.stdout}"
        if result.stderr:
            output += f"[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[退出码] {result.returncode}"
        return output.strip() or "(无输出)"
    except subprocess.TimeoutExpired:
        return "错误：命令执行超时（30秒）"
    except Exception as e:
        return f"执行错误：{e}"


# 工具映射
TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "run_command": run_command,
}

# ============================================================
# 第 2 步：工具定义（JSON Schema）
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定文件的内容，返回带行号的文本",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作目录）"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入文件（创建或覆盖）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作目录）"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出目录中的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "目录路径（相对于工作目录），默认为 '.'"
                    }
                },
                "required": []
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
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# ============================================================
# 第 3 步：Agent 循环（复用第四章的模式）
# ============================================================

def agent_loop(user_input: str, max_iterations: int = 10) -> str:
    print(f"\n{'='*60}")
    print(f"用户: {user_input}")
    print(f"{'='*60}")

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个编程助手 Agent，可以读写文件和执行命令。\n"
                "工作目录是 workspace/，所有文件操作都相对于这个目录。\n\n"
                "工作流程：\n"
                "1. 先用 list_files 了解目录结构\n"
                "2. 用 read_file 阅读文件内容\n"
                "3. 用 write_file 创建或修改文件\n"
                "4. 用 run_command 执行命令来验证结果\n\n"
                "每一步都要解释你在做什么和为什么。"
            )
        },
        {"role": "user", "content": user_input}
    ]

    for i in range(max_iterations):
        print(f"\n--- 第 {i+1} 轮 ---")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            temperature=0,
        )

        msg = response.choices[0].message

        # 打印 LLM 的思考（如果有文本内容）
        if msg.content:
            print(f"[思考] {msg.content}")

        if not msg.tool_calls:
            print(f"\n[完成] 助手: {msg.content}")
            return msg.content

        messages.append(msg)

        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
            print(f"[调用] {name}({args_str})")

            result = TOOL_MAP[name](**args)
            # 截断过长的输出
            if len(result) > 2000:
                result = result[:2000] + "\n...(输出被截断)"
            print(f"[结果] {result[:200]}{'...' if len(result) > 200 else ''}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return "达到最大迭代次数"

# ============================================================
# 第 4 步：实战测试！
# ============================================================

# 测试 1：创建一个 Python 文件
agent_loop("帮我创建一个 hello.py 文件，内容是打印九九乘法表，然后运行它看看结果")

# 测试 2：修改已有文件
agent_loop("读取 hello.py，然后修改它：让乘法表只打印到 5x5，再运行一下")

# ============================================================
# 本章小结
# ============================================================
print("\n" + "=" * 60)
print(f"""
本章小结：

1. 实现了 4 个核心工具：read_file, write_file, list_files, run_command
2. 安全措施：路径限制（防穿越）、命令超时、输出截断
3. Agent 已经能自主地：创建文件 → 写代码 → 运行验证

安全要点（Claude Code / OpenClaw 的做法）：
- 所有文件操作必须限制在工作目录内
- 命令执行需要超时限制
- 敏感操作（删除、覆盖）可以加确认步骤

工作目录在: {WORKSPACE}
你可以去看看 Agent 创建的文件！

下一章，我们解决一个关键问题：对话记忆与上下文管理。
""")
