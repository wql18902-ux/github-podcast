# Handoff · 云 TTS 与本地 TTS 成本调研

- 当前 Phase: 已完成并收口（2026-09-13）
- 已确认事实:
  - 本地 VoxCPM2 按电费算约 1-2 分/期。
  - 千问 Qwen3-TTS-Flash 约 1.36 元/期。
  - 腾讯 TokenHub MiniMax Turbo 约 1.70 元/期，且 TTS 不在新人免费包。
  - 腾讯云自有 TTS 有 800 万基础/精品字符免费额度，限制是仅通用接口。
  - 火山公开价约 4.25 元/期，Agent Plan 等效约 2.30 元/期。
- 已建真相源:
  - `evidence-ledger.md`
  - `truth-source/overview.md`
  - `truth-source/sources.md`
- 最终决定: 自动流水线继续用本地 VoxCPM2；人工云 TTS 统一走火山 Agent Plan；独立豆包共享 Key 已删除。
- 已完成: 云 TTS 控制台、Agent Plan HTTP/WS、Qwen 和音色试听。
- AI 下一步: 只有用户明确要求时，才把云 TTS 接进正式生产链路。
- 未解决风险:
  - Agent Plan AFP 本地账本是估算，平台控制台仍是最终真相源
  - 云 TTS 尚未接进每日自动流水线
