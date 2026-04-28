"""
========================================
第九章：MCP 协议 —— Agent 的标准化连接层
========================================

MCP（Model Context Protocol）是一个开放标准，
为 AI 应用连接外部系统提供统一协议。

你可以把 MCP 想象成"AI 界的 USB-C"：
- 不同的 Agent（Claude、ChatGPT、Cursor）= 不同的设备
- 不同的工具/数据源 = 不同的外设
- MCP = 统一的接口标准

核心架构：
    ┌──────────────────────────────────────────┐
    │           MCP Host (AI 应用)              │
    │  (如 Claude Code, VS Code, ChatGPT)       │
    │                                           │
    │  ┌──────────┐  ┌──────────┐              │
    │  │MCP Client│  │MCP Client│  ...          │
    │  └────┬─────┘  └────┬─────┘              │
    └───────┼──────────────┼────────────────────┘
            │              │
      JSON-RPC 2.0    JSON-RPC 2.0
      (stdio/HTTP)    (stdio/HTTP)
            │              │
    ┌───────┴──────┐ ┌────┴────────┐
    │  MCP Server  │ │ MCP Server  │
    │  (文件系统)   │ │  (数据库)   │
    └──────────────┘ └─────────────┘

MCP 三大核心原语（Primitives）：
- Tools    : 可执行的函数（让 LLM 执行操作）
- Resources: 数据源（为 LLM 提供上下文）
- Prompts  : 可复用的提示词模板

本章我们将：
1. 用 Python MCP SDK 构建一个 MCP Server
2. 用 MCP Client 连接并调用它
3. 将 MCP Server 集成到我们的 Agent 中

前置依赖：pip install mcp
"""

import asyncio
import json
import os
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
print(f"当前使用模型: {MODEL}\n")


# ============================================================
# 第 1 步：理解 MCP 协议基础
# ============================================================
print("=" * 60)
print("第 1 步：MCP 协议基础")
print("=" * 60)

print("""
  MCP 使用 JSON-RPC 2.0 协议通信，核心流程：

  1. 初始化握手（Capability Negotiation）
     Client → Server: initialize (声明支持的能力)
     Server → Client: 返回服务器能力
     Client → Server: notifications/initialized

  2. 工具发现
     Client → Server: tools/list
     Server → Client: 返回可用工具列表

  3. 工具调用
     Client → Server: tools/call { name, arguments }
     Server → Client: 返回执行结果

  传输方式：
  - stdio  : 本地进程间通信（最常用）
  - HTTP   : 远程服务器通信（支持 SSE 流式）
""")


# ============================================================
# 第 2 步：构建 MCP Server
# ============================================================
print("=" * 60)
print("第 2 步：构建一个 MCP Server")
print("=" * 60)

# MCP Server 代码 —— 写入独立文件，稍后作为子进程启动
MCP_SERVER_CODE = '''
"""
一个简单的 MCP Server，提供两个工具：
- greet: 生成问候语
- word_count: 统计文本字数
"""
from mcp.server.fastmcp import FastMCP

# 创建 MCP Server 实例
mcp = FastMCP(
    name="demo-server",
)


# 用装饰器定义工具 —— 这是 MCP SDK 最简洁的方式
@mcp.tool()
def greet(name: str, language: str = "zh") -> str:
    """生成问候语。

    Args:
        name: 要问候的人名
        language: 语言，'zh' 中文，'en' 英文
    """
    if language == "en":
        return f"Hello, {name}! Welcome to the world of MCP!"
    return f"你好，{name}！欢迎来到 MCP 的世界！"


@mcp.tool()
def word_count(text: str) -> str:
    """统计文本信息：字符数、单词数、行数。

    Args:
        text: 要统计的文本内容
    """
    chars = len(text)
    words = len(text.split())
    lines = len(text.splitlines()) or 1
    return f"字符数: {chars}, 词数: {words}, 行数: {lines}"


# 同时提供一个 Resource（数据源）
@mcp.resource("config://server-info")
def get_server_info() -> str:
    """返回服务器信息"""
    return "Demo MCP Server v1.0 - 提供 greet 和 word_count 工具"


# 提供一个 Prompt 模板
@mcp.prompt()
def analyze_text(text: str) -> str:
    """生成文本分析的提示词模板"""
    return f"请分析以下文本的内容、风格和情感：\\n\\n{text}"


if __name__ == "__main__":
    # 以 stdio 传输方式运行
    mcp.run(transport="stdio")
'''

# 将 MCP Server 写入文件
server_path = os.path.join(os.path.dirname(__file__), "mcp_demo_server.py")
with open(server_path, "w") as f:
    f.write(MCP_SERVER_CODE)

print(f"""
  已生成 MCP Server 文件: mcp_demo_server.py

  MCP Server 的核心要素：
  1. FastMCP()       - 创建服务器实例
  2. @mcp.tool()     - 注册工具（函数自动变成 MCP 工具）
  3. @mcp.resource() - 注册数据源
  4. @mcp.prompt()   - 注册提示词模板
  5. mcp.run()       - 启动服务器

  使用 FastMCP 比手写 JSON Schema 简洁得多：
  - 函数签名自动转换为 inputSchema
  - docstring 自动变成工具描述
  - 类型注解自动推导参数类型
""")


# ============================================================
# 第 3 步：用 MCP Client 连接 Server
# ============================================================
print("=" * 60)
print("第 3 步：MCP Client —— 连接并调用 Server")
print("=" * 60)

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def demo_mcp_client():
    """演示 MCP Client 的基本用法"""

    # 1. 配置 Server 连接参数（stdio 方式）
    server_params = StdioServerParameters(
        command="python3",
        args=[server_path],
    )

    print("\n  --- 连接 MCP Server ---")

    # 2. 建立连接
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 3. 初始化（能力协商）
            await session.initialize()
            print("  ✅ 连接已建立，初始化完成")

            # 4. 列出可用工具
            tools_result = await session.list_tools()
            print(f"\n  📋 可用工具 ({len(tools_result.tools)} 个):")
            for tool in tools_result.tools:
                print(f"     - {tool.name}: {tool.description}")

            # 5. 调用工具：greet
            print("\n  --- 调用 greet 工具 ---")
            result = await session.call_tool("greet", {"name": "开发者", "language": "zh"})
            print(f"  结果: {result.content[0].text}")

            # 6. 调用工具：word_count
            print("\n  --- 调用 word_count 工具 ---")
            result = await session.call_tool("word_count", {"text": "Hello MCP! 这是一个测试文本。"})
            print(f"  结果: {result.content[0].text}")

            # 7. 列出资源
            resources_result = await session.list_resources()
            print(f"\n  📦 可用资源 ({len(resources_result.resources)} 个):")
            for resource in resources_result.resources:
                print(f"     - {resource.uri}: {resource.name}")

            # 8. 读取资源
            if resources_result.resources:
                res = await session.read_resource(resources_result.resources[0].uri)
                print(f"  资源内容: {res.contents[0].text}")

            # 9. 列出提示词模板
            prompts_result = await session.list_prompts()
            print(f"\n  💬 可用 Prompt ({len(prompts_result.prompts)} 个):")
            for prompt in prompts_result.prompts:
                print(f"     - {prompt.name}: {prompt.description}")

            print("\n  ✅ 所有操作完成")


# 运行 Client demo
asyncio.run(demo_mcp_client())


# ============================================================
# 第 4 步：将 MCP 集成到 Agent
# ============================================================
print("\n" + "=" * 60)
print("第 4 步：MCP + Agent —— 真正的集成")
print("=" * 60)

print("""
  核心思路：
  1. Agent 启动时，连接所有配置的 MCP Server
  2. 从每个 Server 获取 tools/list → 合并成统一工具列表
  3. 将工具列表传给 LLM（和之前一样）
  4. LLM 返回 tool_call 时，路由到对应的 MCP Server 执行
  5. 将结果返回给 LLM

  这就是 Claude Code / VS Code Copilot 的工作方式！
""")


async def mcp_agent(user_input: str):
    """
    集成 MCP Server 的 Agent。

    流程：
    1. 连接 MCP Server，获取工具列表
    2. 转换为 OpenAI function calling 格式
    3. 运行 Agent 循环
    4. 工具调用通过 MCP Client 执行
    """

    server_params = StdioServerParameters(
        command="python3",
        args=[server_path],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # ---- 1. 从 MCP Server 获取工具，转成 OpenAI 格式 ----
            mcp_tools = await session.list_tools()

            openai_tools = []
            for tool in mcp_tools.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema,
                    }
                })

            print(f"  从 MCP Server 加载了 {len(openai_tools)} 个工具")

            # ---- 2. Agent 循环 ----
            messages = [
                {"role": "system", "content": "你是一个 AI 助手，可以使用 MCP 工具完成任务。"},
                {"role": "user", "content": user_input},
            ]

            print(f"  用户: {user_input}")

            for _ in range(10):
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=openai_tools,
                )

                msg = response.choices[0].message
                messages.append(msg)

                if not msg.tool_calls:
                    print(f"  助手: {msg.content}")
                    return msg.content

                for tool_call in msg.tool_calls:
                    name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    print(f"  🔧 MCP 调用 [{name}]: {args}")

                    # 通过 MCP Client 执行工具
                    result = await session.call_tool(name, args)
                    result_text = result.content[0].text if result.content else "无结果"
                    print(f"  📎 MCP 返回: {result_text}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text,
                    })

    return "任务完成"


# ============================================================
# 第 5 步：测试 MCP Agent
# ============================================================
print("\n" + "=" * 60)
print("第 5 步：测试 MCP Agent")
print("=" * 60)

# 测试 1
print("\n--- 测试 1：通过 MCP 调用 greet ---")
asyncio.run(mcp_agent("用英文跟 Alice 打个招呼"))

# 测试 2
print("\n--- 测试 2：通过 MCP 调用 word_count ---")
asyncio.run(mcp_agent("帮我统计这段文字的信息：人工智能正在改变世界，MCP 让 AI 应用的连接变得标准化。"))


# ============================================================
# 第 6 步：多 Server 架构概览
# ============================================================
print("\n" + "=" * 60)
print("第 6 步：多 MCP Server 架构")
print("=" * 60)

print("""
  实际生产环境中，一个 Agent 会连接多个 MCP Server：

  ┌─────────────────────────────────────────────┐
  │              AI Agent (Host)                 │
  │                                              │
  │  MCP Client 1 ──→ 文件系统 Server (stdio)   │
  │  MCP Client 2 ──→ 数据库 Server   (stdio)   │
  │  MCP Client 3 ──→ GitHub Server   (HTTP)     │
  │  MCP Client 4 ──→ Sentry Server   (HTTP)     │
  └─────────────────────────────────────────────┘

  配置通常用 JSON 文件（类似 VS Code 的 mcp.json）：

  {
    "servers": {
      "filesystem": {
        "command": "python3",
        "args": ["servers/filesystem_server.py"],
        "transport": "stdio"
      },
      "database": {
        "command": "python3",
        "args": ["servers/db_server.py"],
        "transport": "stdio"
      },
      "github": {
        "url": "https://api.github.com/mcp",
        "transport": "http",
        "headers": { "Authorization": "Bearer ..." }
      }
    }
  }

  Agent 启动时：
  1. 读取配置，为每个 Server 创建一个 MCP Client
  2. 分别初始化连接，获取各自的工具列表
  3. 合并所有工具，形成统一的能力集
  4. 运行 Agent Loop，将 tool_call 路由到正确的 Server
""")


# ============================================================
# 第 7 步：创建自定义 MCP Server 的模板
# ============================================================
print("=" * 60)
print("第 7 步：快速创建你自己的 MCP Server")
print("=" * 60)

print("""
  创建 MCP Server 只需三步：

  ──────────── server.py ────────────
  from mcp.server.fastmcp import FastMCP

  mcp = FastMCP("my-server")

  @mcp.tool()
  def my_tool(param: str) -> str:
      \\"\\"\\"工具描述\\"\\"\\"
      return f"处理结果: {param}"

  @mcp.resource("data://my-resource")
  def my_resource() -> str:
      \\"\\"\\"资源描述\\"\\"\\"
      return "资源内容"

  mcp.run(transport="stdio")
  ──────────────────────────────────

  然后在 Agent 或 VS Code 中配置连接即可。
  
  如果要在 VS Code 中使用，添加到 .vscode/mcp.json：
  {
    "servers": {
      "my-server": {
        "command": "python3",
        "args": ["server.py"]
      }
    }
  }
""")


# ============================================================
# 本章小结
# ============================================================
print("=" * 60)
print("""
本章小结：

1. MCP 是 AI 应用连接外部系统的开放标准协议
2. 核心架构：Host (AI应用) → Client → Server
3. 三大原语：Tools(工具) / Resources(数据) / Prompts(模板)
4. 通信基于 JSON-RPC 2.0，支持 stdio 和 HTTP 传输
5. FastMCP SDK 极大简化了 Server 开发
6. Agent 集成 MCP 的关键：工具发现 → 格式转换 → 路由执行

MCP 的意义：
- 解耦：工具开发者和 Agent 开发者各自独立
- 标准化：一个 MCP Server 可以被所有支持 MCP 的 Agent 使用
- 生态：npm、PyPI 上已有大量现成的 MCP Server

这正是 Claude Code、VS Code Copilot、ChatGPT 等产品
正在使用的连接方式。恭喜你完成了全部教程！🎉
""")
