# 云 TTS 音色试听

日期：2026-09-13

## 当前结论

- 云 TTS 默认路线：`火山 Agent Plan / doubao-seed-tts-2.0`。
- 默认音色：`zh_female_gaolengyujie_uranus_bigtts`（高冷御姐）。
- 备选音色：`zh_female_vv_uranus_bigtts`。
- Qwen-Audio Plus 只作云侧备选；独立豆包共享 Key 已删除，不再测试。
- 本地 VoxCPM2 不进入云 TTS 音色候选；自动流水线仍单独使用它。

## 当前样音

Agent Plan 高冷御姐，HTTP 10 秒：

![高冷御姐](<项目根目录>/output/tts-console/voice-tests-10s/11-agentplan-gaolengyujie.mp3)

Agent Plan vv，HTTP 10 秒：

![Agent Plan vv](<项目根目录>/output/tts-console/voice-tests-10s/12-agentplan-vv.mp3)

Agent Plan 高冷御姐，WebSocket：

![高冷御姐 WebSocket](<项目根目录>/output/tts-console/voice-tests-10s/50-agentplan-ws-gaolengyujie.mp3)

全部成功音色各截前 10 秒：

![全部成功音色各 10 秒](<项目根目录>/output/tts-console/voice-tests-10s/00-all-free-voices-10s.wav)

## 判断

| 音色 | 基频中位数 | 方向 |
|---|---:|---|
| CosyVoice v1 `longyuan` | 176.5 Hz | 低沉温暖，但当前 Key 路线已停 |
| Agent Plan 高冷御姐 | 196.7 Hz | 最接近高冷御姐 |
| Qwen Plus `longanlingxin` | 226.4 Hz | 温暖但偏年轻 |
| Agent Plan vv | 230.8 Hz | 活泼明亮 |
| Qwen Flash `longanfengyue` | 240.0 Hz | 自然但偏亮 |

主选：Agent Plan 高冷御姐。

## 额度状态

- Agent Plan 语音模型只看月额度，不扣 5 小时/周额度。
- 2026-09-13 本地账本：月剩余约 29960 AFP。
- 8500 汉字一期约 1147.5 AFP。
- 独立豆包免费字符没有消耗；共享 Key 已删除。

## 历史素材

`output/tts-audition/` 和更早的 `output/tts-console/free-*-300.*` 是选型过程中的历史试听，不再作为当前决策依据。需要保留供复核时再听，不进入默认路线。
