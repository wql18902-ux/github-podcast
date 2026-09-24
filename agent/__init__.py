"""播客 Agent 外环（平台无关）。

红线（设计稿 §3.1，可机械检查）：本目录**不许 import 任何平台 SDK**，
只许标准库 + `subprocess`。这是「换宿主不重写」的唯一保证。

    grep -rE '^\\s*(import|from)\\s+(anthropic|openai|codex|hermes)' agent/ && echo 违反红线

分层：编排（pipeline/stages）→ 工具（tools，subprocess 打现有 CLI）→ 状态（state，SQLite）。
智能规范不在这里，在 ~/.claude/skills/podcast-agent/SKILL.md（三家共用的软链库）。
"""

__all__ = ["paths", "state", "tools", "gates", "request", "stages", "pipeline"]
