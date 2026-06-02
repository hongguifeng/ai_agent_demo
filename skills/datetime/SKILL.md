---
name: datetime
description: 日期时间能力，适合查询当前日期、时间、时间戳和英文日期格式
tools: get_datetime
---

# DateTime Skill

## When to Use

Use this skill when the user asks about the current date, current time, timestamp, weekday, or wants a date formatted in English.

## Instructions

- Use `get_datetime` instead of guessing the current time.
- Choose the smallest format that answers the user's request.
- If the user asks for an English date, use `english_date`.
- If another skill is needed to transform the returned text, load that skill too.

## Tool Guide

`get_datetime(format)` returns current date/time information.

Formats:

- `date`: `YYYY-MM-DD`
- `time`: `HH:MM:SS`
- `full`: `YYYY-MM-DD HH:MM:SS`
- `timestamp`: Unix timestamp
- `english_date`: weekday, month day, year

## Example

User: 现在几点了？

Action: call `get_datetime` with `{"format": "time"}`

Answer: 现在是 15:04:05。
