
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
    return f"请分析以下文本的内容、风格和情感：\n\n{text}"


if __name__ == "__main__":
    # 以 stdio 传输方式运行
    mcp.run(transport="stdio")
