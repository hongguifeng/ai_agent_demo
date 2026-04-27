"""
========================================
第六章：记忆与上下文管理
========================================

LLM 有一个硬约束：上下文窗口有限（如 128K tokens）。
随着对话越来越长，消息列表会超出限制。

Claude Code 等产品的关键技术之一就是上下文管理：
1. 对话历史管理 —— 保留重要消息，裁剪旧消息
2. Token 计数 —— 估算使用量，主动管理
3. 摘要压缩 —— 把长对话总结成短摘要

本章实现一个带记忆管理的多轮对话 Agent。
"""

import json
import os
import httpx
from openai import OpenAI

client = OpenAI(http_client=httpx.Client(verify=False))
MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")

# ============================================================
# 第 1 步：Token 估算
# ============================================================

def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数量。
    经验法则：英文约 1 token/4字符，中文约 1 token/1.5字符。
    生产环境应使用 tiktoken 库精确计算。
    """
    # 简单估算：中文字符 * 0.7 + 英文字符 * 0.25
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 0.7 + other_chars * 0.25)


def estimate_messages_tokens(messages: list) -> int:
    """估算消息列表的总 token 数"""
    total = 0
    for msg in messages:
        # 每条消息有额外开销（角色标记等），约 4 tokens
        total += 4
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if content:
                total += estimate_tokens(content)
        else:
            # OpenAI 消息对象
            if msg.content:
                total += estimate_tokens(msg.content)
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    total += estimate_tokens(tc.function.arguments)
    return total

# ============================================================
# 第 2 步：对话历史管理器
# ============================================================

class ConversationMemory:
    """
    对话记忆管理器

    核心策略（参考 Claude Code）：
    1. System Prompt 永远保留
    2. 最近 N 轮对话完整保留
    3. 超出限制时，旧消息被压缩成摘要
    """

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.system_message = None
        self.messages = []        # 完整的消息历史
        self.summary = ""         # 被压缩的历史摘要

    def set_system(self, content: str):
        self.system_message = {"role": "system", "content": content}

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, message):
        """添加助手消息（可能是字符串或 API 返回的消息对象）"""
        if isinstance(message, str):
            self.messages.append({"role": "assistant", "content": message})
        else:
            self.messages.append(message)

    def add_tool_result(self, tool_call_id: str, content: str):
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def get_messages(self) -> list:
        """
        获取发送给 LLM 的消息列表。
        如果有摘要，把它注入到 system prompt 中。
        """
        result = []

        # System prompt（包含摘要）
        if self.system_message:
            sys_content = self.system_message["content"]
            if self.summary:
                sys_content += f"\n\n## 之前的对话摘要\n{self.summary}"
            result.append({"role": "system", "content": sys_content})

        # 当前消息
        result.extend(self._serialize_messages(self.messages))
        return result

    def _serialize_messages(self, messages: list) -> list:
        """将消息列表序列化为 API 格式"""
        result = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(msg)
            else:
                # OpenAI 消息对象 → 字典
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

    def check_and_compress(self):
        """
        检查 token 使用量，必要时压缩历史。
        这是上下文管理的核心逻辑。
        """
        all_messages = self.get_messages()
        total_tokens = estimate_messages_tokens(all_messages)

        print(f"  [记忆] 当前 token 估算: ~{total_tokens} / {self.max_tokens}")

        if total_tokens <= self.max_tokens:
            return  # 未超限，不需要压缩

        print(f"  [记忆] 超出限制！开始压缩历史...")

        # 策略：保留最近的消息，把旧消息压缩成摘要
        # 找到可以压缩的消息（保留最近 6 条）
        keep_recent = 6
        if len(self.messages) <= keep_recent:
            return  # 消息太少，无法压缩

        old_messages = self.messages[:-keep_recent]
        self.messages = self.messages[-keep_recent:]

        # 用 LLM 生成摘要
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "请将以下对话历史压缩成简洁的摘要。\n"
                    "保留关键信息：用户的需求、已完成的操作、重要的结果。\n"
                    "摘要要简短，不超过 200 字。"
                )
            },
            {
                "role": "user",
                "content": (
                    f"已有摘要：{self.summary or '(无)'}\n\n"
                    f"新的对话内容：\n{json.dumps(self._serialize_messages(old_messages), ensure_ascii=False, indent=2)}"
                )
            }
        ]

        response = client.chat.completions.create(
                model=MODEL,
            temperature=0,
            max_tokens=300,
        )

        self.summary = response.choices[0].message.content
        print(f"  [记忆] 压缩完成。摘要: {self.summary[:100]}...")

    def get_stats(self) -> str:
        """获取记忆状态统计"""
        msgs = self.get_messages()
        tokens = estimate_messages_tokens(msgs)
        return (
            f"消息数: {len(self.messages)} | "
            f"Token 估算: ~{tokens} | "
            f"有摘要: {'是' if self.summary else '否'}"
        )

# ============================================================
# 第 3 步：带记忆管理的交互式 Agent
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
                        "description": "数学表达式"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

def calculator(expression: str) -> str:
    allowed = set("0123456789+-*/().% ")
    if not all(c in allowed for c in expression):
        return "错误"
    try:
        return str(eval(expression))
    except Exception as e:
        return f"错误：{e}"

TOOL_MAP = {"calculator": calculator}


def interactive_agent():
    """带记忆管理的交互式 Agent"""
    memory = ConversationMemory(max_tokens=4000)  # 设一个较小的限制便于演示
    memory.set_system(
        "你是一个有用的 AI 助手，支持多轮对话。\n"
        "你可以使用计算器工具来进行数学运算。\n"
        "你会记住之前的对话内容。"
    )

    print("=" * 60)
    print("交互式 Agent（带记忆管理）")
    print("输入 'quit' 退出，输入 'stats' 查看记忆状态")
    print("=" * 60)

    while True:
        user_input = input("\n你: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("再见！")
            break
        if user_input.lower() == "stats":
            print(f"[记忆状态] {memory.get_stats()}")
            if memory.summary:
                print(f"[摘要内容] {memory.summary}")
            continue

        # 添加用户消息
        memory.add_user(user_input)

        # Agent 循环
        for _ in range(5):
            # 检查并压缩历史
            memory.check_and_compress()

            response = client.chat.completions.create(
                model=MODEL,
                messages=memory.get_messages(),
                tools=tools,
                temperature=0,
            )

            msg = response.choices[0].message

            if not msg.tool_calls:
                memory.add_assistant(msg.content)
                print(f"\n助手: {msg.content}")
                break

            # 执行工具
            memory.add_assistant(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                print(f"  [工具] {name}({args})")
                result = TOOL_MAP[name](**args)
                print(f"  [结果] {result}")
                memory.add_tool_result(tc.id, result)

# ============================================================
# 第 4 步：演示记忆管理
# ============================================================

def demo_memory():
    """非交互式演示"""
    print("=" * 60)
    print("演示：记忆管理机制")
    print("=" * 60)

    memory = ConversationMemory(max_tokens=2000)  # 很小的限制，容易触发压缩
    memory.set_system("你是一个有用的助手，可以使用计算器。")

    conversations = [
        "我叫小明，我今年 25 岁",
        "帮我算 25 * 365",
        "那个结果代表我活了大约多少天，再乘以 24 算出小时数",
        "你还记得我叫什么名字吗？我几岁了？",
    ]

    for user_input in conversations:
        print(f"\n{'─'*40}")
        print(f"用户: {user_input}")

        memory.add_user(user_input)

        for _ in range(5):
            memory.check_and_compress()

            response = client.chat.completions.create(
                model=MODEL,
                messages=memory.get_messages(),
                tools=tools,
                temperature=0,
            )

            msg = response.choices[0].message

            if not msg.tool_calls:
                memory.add_assistant(msg.content)
                print(f"助手: {msg.content}")
                print(f"  [{memory.get_stats()}]")
                break

            memory.add_assistant(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                print(f"  [工具] {name}({args})")
                result = TOOL_MAP[name](**args)
                print(f"  [结果] {result}")
                memory.add_tool_result(tc.id, result)

# 运行演示
demo_memory()

# 如果想进入交互模式，取消下面的注释：
# interactive_agent()

# ============================================================
# 本章小结
# ============================================================
print("\n" + "=" * 60)
print("""
本章小结：

1. Token 管理：估算使用量，防止超出上下文窗口
2. 记忆策略：保留近期 + 压缩旧历史为摘要
3. 摘要注入：把压缩的摘要放入 System Prompt
4. 多轮对话：Agent 能"记住"之前的对话内容

Claude Code 的记忆管理更复杂：
- 使用精确的 tokenizer（tiktoken）
- 多级压缩策略
- 重要信息标记和保护
- 项目上下文的持久化存储

下一章：综合所有知识，构建一个完整可用的 Coding Agent！
""")
