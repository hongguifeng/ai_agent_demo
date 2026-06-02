---
name: math
description: 数学计算能力，适合精确计算、公式求值、简单科学计算
tools: calculator
---

# Math Skill

## When to Use

Use this skill when the user asks for exact arithmetic, powers, roots, trigonometry, logarithms, or any result that should be calculated rather than estimated mentally.

## Instructions

- Use the `calculator` tool for numeric computation.
- Convert the user's request into a compact mathematical expression.
- Do not use arbitrary Python features; only use mathematical functions described by the tool.
- After the tool returns a result, explain the answer briefly in the user's language.

## Tool Guide

`calculator(expression)` evaluates a math expression.

Supported examples:

- `2**20`
- `sqrt(144)`
- `sin(pi / 2)`
- `round(100 / 7, 2)`

## Example

User: 计算 2 的 20 次方

Action: call `calculator` with `{"expression": "2**20"}`

Answer: 2 的 20 次方是 1,048,576。
