---
name: text
description: 文本处理能力，适合统计字符、统计单词、大小写转换和反转文本
tools: text_tool
---

# Text Skill

## When to Use

Use this skill when the user asks to count characters, count words, uppercase text, lowercase text, or reverse text.

## Instructions

- Use `text_tool` for deterministic text operations.
- Preserve spaces and punctuation exactly when counting or transforming text.
- For Chinese text, `count_chars` counts Unicode characters, including spaces.
- If the text comes from another tool result, pass that exact result into `text_tool`.

## Tool Guide

`text_tool(action, text)` processes text.

Actions:

- `count_words`
- `count_chars`
- `to_upper`
- `to_lower`
- `reverse`

## Example

User: 把 hello 转成大写

Action: call `text_tool` with `{"action": "to_upper", "text": "hello"}`

Answer: HELLO
