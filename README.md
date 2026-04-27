# 从零构建 AI Agent 教程

> 参考 Claude Code / OpenClaw 等主流 Agent 实现原理，由浅入深，手把手搭建一个可用的 AI Agent。

## 教程大纲

| 章节 | 主题 | 核心概念 |
|------|------|----------|
| 01 | 你好，LLM | API 调用基础、消息格式 |
| 02 | 系统提示词与角色设计 | System Prompt、人格塑造 |
| 03 | 工具定义与函数调用 | Tool/Function Calling、JSON Schema |
| 04 | Agent 循环：ReAct 模式 | Think → Act → Observe 循环 |
| 05 | 实用工具集：文件与命令 | 文件读写、Shell 执行 |
| 06 | 记忆与上下文管理 | 对话历史、Token 管理、摘要 |
| 07 | 完整 Coding Agent | 整合所有模块，构建可用 Agent |

## 环境准备

```bash
# Python >= 3.10
cd agent_demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置 API Key
export OPENAI_API_KEY="sk-..."          # OpenAI API Key
export OPENAI_BASE_URL="https://..."    # 兼容接口（可选，如 DeepSeek、月之暗面等）
export AGENT_MODEL="gpt-4o-mini"        # 模型名称（可选，默认 gpt-4o-mini）
```

## 运行方式

每一章都是独立可运行的 Python 文件：

```bash
python 01_hello_llm.py
python 02_system_prompt.py
python 03_tool_calling.py
python 04_react_loop.py
python 05_file_tools.py
python 06_memory.py
python 07_full_agent.py
```

## 核心原理

```
用户输入
   │
   ▼
┌──────────────────────────────────────────┐
│              Agent Loop                   │
│                                           │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐ │
│  │  Think   │→│   Act    │→│ Observe  │ │
│  │ (LLM推理)│  │(执行工具)│  │(获取结果)│ │
│  └─────────┘  └─────────┘  └──────────┘ │
│       ▲                          │        │
│       └──────────────────────────┘        │
│              循环直到任务完成               │
└──────────────────────────────────────────┘
   │
   ▼
最终回复
```

一个 AI Agent 的本质就是：**LLM + 工具 + 循环**。

LLM 负责思考和决策，工具负责与外界交互，循环让 Agent 能自主地一步步完成复杂任务。
这正是 Claude Code、OpenClaw 等产品的核心架构。
