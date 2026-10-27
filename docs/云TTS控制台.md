# 云 TTS 控制台

日期：2026-09-13

本地页面：http://127.0.0.1:8787

当前云 TTS 默认 provider：火山方舟 Agent Plan。自动播客流水线仍用本地 VoxCPM2，云控制台没有接进 Trae 定时任务。独立豆包共享 Key 已删除，相关 provider 保留但不作为当前路线。

不要直接双击打开 `web/tts-console.html`。直接打开时是 `file://`，页面无法连接本地后端，也不能保存 Key。

## 用途

- 在页面里保存云 TTS 的 endpoint、model、voice 和 API Key。
- endpoint/model/voice 等元数据保存到 `~/.config/ai-jarvis/tts-console/config.json`。
- API Key 保存到 macOS Keychain，服务名 `ai-jarvis-tts-console`。
- 页面只显示 Key 是否已保存，不读取、不回显完整 Key。
- 自动读取项目内的成文稿，默认路径 `output/latest-script.md`。
- 可试听前 900 字，也可直接合成当前文本框全文。

## 启动

```bash
cd <项目根目录>
bash scripts/run_tts_console.sh 8787
```

打开：

```text
http://127.0.0.1:8787
```

## 当前支持

| adapter | 用途 | 直接合成 |
|---|---|---|
| `dashscope` | 千问 Qwen-Audio-TTS / CosyVoice HTTP | 支持 |
| `minimax` | MiniMax、TokenHub 兼容端点 | 支持 |
| `volc_v1` | 火山豆包旧版 V1 HTTP | 支持 |
| `volc_agent_http` | 火山 Agent Plan 语音合成 | 支持，带 AFP 预算闸门 |
| `volc_http_v3` | 豆包语音合成/声音复刻 V3 HTTP | 支持 |
| `volc_audio_http` | 豆包音频生成 1.0 | 支持，支持内置音色或参考音频 |
| `openai` | OpenAI 兼容 `/audio/speech` | 支持 |
| `mimo_tts` | 小米 MiMo-V2.5-TTS 系列（chat.completions + audio 字段） | 支持 |
| `manual` | 只保存配置，留给后续适配器 | 不支持 |

### MiMo 三模型（2026-09-24 新增，真机验证通过）

| provider | 模型 | 音色来源 | 计费 |
|---|---|---|---|
| `mimo_tts` | `mimo-v2.5-tts` | 预置音色（`voice`，默认白桦；另有 冰糖/茉莉/苏打/Mia/Chloe/Milo/Dean） | 限时免费 |
| `mimo_tts_clone` | `mimo-v2.5-tts-voiceclone` | `extra.reference_audio_path` 的参考音频 Data URL（默认 `voices/podcast-voice.wav`） | 限时免费 |
| `mimo_tts_design` | `mimo-v2.5-tts-voicedesign` | `extra.style_prompt` 音色文字描述（必填） | 限时免费 |

- Endpoint 固定 `https://api.xiaomimimo.com/v1/chat/completions`；协议不是 OpenAI `/audio/speech`，是 chat.completions 里 `audio` 字段给格式/音色，返回 base64 音频在 `choices[0].message.audio.data`。
- **三模型共用一把 Key**（Keychain account `mimo_api`，service `ai-jarvis-tts-console`），任一入口保存后其余共用。
- `extra.style_prompt`：预置音色模型放自然语言风格指令（可空）；voicedesign 模型放音色描述（必填）；格式 `wav`（流式才需要 pcm16，控制台走非流式）。
- 「限时免费」核实自官方按量计费页（2026-09-22 更新时间，2026-09-24 抓取）；无字符额度数字，故不设本地免费闸门，改期收费时需回来补 `free_remaining_chars`。
- 同系列 `mimo-v2.5-asr`（语音识别）**不是免费**：¥0.5/小时，走 `转录系统/mimo_asr.py`，Key 同一把（见该文件 docstring），不进本控制台。
- **整期合成路线（2026-10-07 接入）**：`scripts/tts_mimo.py`（`bash scripts/pipeline.sh synth-mimo`）复用的是 `mimo_tts_clone` 这个 provider，但**参考音频不读控制台里保存的值**——脚本走 `cloud_tts.synthesize_with_config()` 在内存里把 `extra.reference_audio_path` 覆盖成 `voices/mimo-clone-ref.wav`（`--ref` 可换），**不写回 provider 配置**。所以控制台里 `mimo_tts_clone` 的默认值照旧是 `voices/podcast-voice.wav`，两边互不干扰。实测原速 257–317 汉字/分（2026-10-07 三段样本，882 汉字 / 343s），比本地 VoxCPM2 的 187 快一截；`--han-per-min` 用 atempo 定标，只改速度不改音高。

火山 Agent Plan 使用 HTTP 单流接口：

- URL：`https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional`
- Resource ID：`seed-tts-2.0`
- 模型：`doubao-seed-tts-2.0`
- AFP：每万字符 1350 AFP

官方规则写明语音模型没有 5 小时限额与周限额，只受月限额约束。截图时月额度还剩 3 万 AFP；适配器按语音模型规则只硬拦月额度，不会自动走超额后付费。周额度仍展示，但不误拦 TTS。

独立豆包语音额度也预置进页面：

| provider | 模型 | 免费额度 |
|---|---|---:|
| `volc_tts1` | `seed-tts-1.0` | 5000 字符 |
| `volc_tts2` | `doubao-seed-tts-2.0` | 20000 字符 |
| `volc_icl2` | `doubao-seed-icl-2.0` | 5000 字符 |
| `volc_design` | 音色设计 | 20000 字符 |
| `volc_audio1` | `seed-audio-1.0` | 60 分钟 |

这些独立入口不占 Agent Plan AFP；豆包语音这一组共用一把独立 Key。

火山各入口地址不共用，Key 按 Agent Plan / 独立豆包语音两组管理：

| 入口 | Endpoint | Resource ID | Key |
|---|---|---|---|
| Agent Plan | `/api/v3/plan/tts/unidirectional` | `seed-tts-2.0` | Agent Plan 专属 Key |
| TTS 1.0 | `/api/v3/tts/unidirectional` | `seed-tts-1.0` | 独立豆包语音 Key |
| TTS 2.0 | `/api/v3/tts/unidirectional` | `seed-tts-2.0` | 独立豆包语音 Key |
| 声音复刻 2.0 | `/api/v3/tts/unidirectional` | `seed-icl-2.0` | 独立豆包语音 Key |
| 音色设计 | `/api/v3/tts/voice_design` | 无 | 独立豆包语音 Key |

豆包语音这一整组共用同一把独立 API Key：TTS 1.0、TTS 2.0、声音复刻 2.0、音色设计，任一项保存后其余项共用。Agent Plan Key 仍然独立，不会串用。

豆包音频生成 1.0 使用单独地址：

- URL：`https://openspeech.bytedance.com/api/v3/tts/create`
- 模型：`seed-audio-1.0`
- 最大单次 120 秒
- 可直接传 `reference_audio_path` 引用项目内参考音频

2026-09-13 历史诊断：独立豆包共享 Key 在 `/api/v3/tts/unidirectional` 和 `/api/v3/tts/create` 都返回 `45000010 Invalid X-Api-Key`；随后 Key 已删除，不再测试。

WebSocket 协议也做了旁证测试：

- Agent Plan Key：`wss://openspeech.bytedance.com/api/v3/plan/tts/bidirection` 握手成功并生成音频。
- 豆包共享 Key：`wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream` 握手直接返回 HTTP 401。

结论：ZIP 里的协议实现没有问题；独立豆包语音 Key 未被平台接受，该路线已关闭。

AFP 复算：

```text
8500 汉字一期 = 8500 / 10000 × 1350 = 1147.5 AFP
月剩余 30000 AFP ≈ 222222 字符 ≈ 26.1 期
```

## 当前状态（2026-09-24 更新）

- **MiMo 三模型：2026-09-24 新增并真机验证**——预置音色 / voiceclone / voicedesign 各合成一次成功（wav，24kHz 单声道），Key 已入 Keychain（`mimo_api`）。ASR 往返测试：TTS 合成语音 → `mimo_asr.py` 正确识别回文字；410 秒长音频自动切 3 段成功。
- Agent Plan：HTTP 和 WebSocket 都已实测成功，默认音色高冷御姐。
- 本地账本月剩余约 29960 AFP；语音模型不扣周额度。
- 千问 Qwen-Audio Plus：Key 有效，做过 10 秒测试。
- 独立豆包共享 Key：已删除；provider 留档，不再测试。
- 云控制台不进自动夜班流水线；自动路线仍是 `scripts/local-fallback.sh` + VoxCPM2。

CosyVoice v1 的免费额度页面已出现，但 HTTP 路径不支持 v1；代码会自动切到 DashScope SDK/WebSocket 通道。

## 截图里的免费额度

2026-09-13 权益页截图显示，TTS 相关免费额度为：

| 模型 | 免费额度 | 说明 |
|---|---:|---|
| `qwen-audio-3.0-tts-plus` | 10K chars | 质量优先 |
| `qwen-audio-3.0-tts-flash` | 10K chars | 速度优先 |
| `cosyvoice-v1` | 10K chars | 永不过期，`longyuan` 最接近现役参考音 |
| `cosyvoice-clone-v1` | 10K chars | 永不过期，适合复刻现役参考音 |

保守按一个汉字计 2 字符，四项合计约 2 万汉字，约 2.35 期；如果接口按页面显示的 chars 直接扣，合计约 4 万字符，约 4.7 期。

## 命令行调用

给后续 Agent 调用用：

```bash
cd <项目根目录>

# 列出配置状态，不输出 Key
python3 scripts/cloud_tts.py list

# 直接用已保存配置合成
python3 scripts/cloud_tts.py synth qwen \
  --text-file output/latest-script.md \
  --max-chars 900 \
  --output output/tts-console/qwen-test.mp3
```

## 安全边界

- 服务只绑定 `127.0.0.1`。
- Key 不写进项目文件，不写进日志，不返回给前端。
- 额外参数 JSON 里禁止放 `key/token/secret/authorization` 字段。
- 页面请求只允许同源 `Origin`。
- 成文稿读取只允许项目目录内路径。

## 免费额度闸门

所有有免费额度的 provider 都保存四个字段：

```json
{
  "free_limit_chars": 10000,
  "free_used_chars": 818,
  "free_remaining_chars": 9182,
  "free_expires_at": "2026-10-12T00:00:00+08:00",
  "allow_overage": false
}
```

调用前按计费字符估算，额度不够直接拒绝。调用成功后才扣本地账本；失败不扣。`allow_overage=false`，不会在本控制台里自动转后付费。

当前本地账本：

| provider | 剩余字符/AFP |
|---|---:|
| `qwen` | 9182 chars |
| `qwen_flash` | 9591 chars |
| `cosyvoice` | 9700 chars |
| `cosyvoice_clone` | 10000 chars |
| `volc_tts1` | 5000 chars |
| `volc_tts2` | 20000 chars |
| `volc_icl2` | 5000 chars |
| `volc_design` | 20000 chars |
| `volc_agent` | 月剩余 29986 AFP |

本地账本是保守估算，平台控制台仍是最终真相源。平台侧如果已经接近额度，先在页面额外参数里调低 `free_remaining_chars`。

## 停止

如果按上面的 `bash scripts/run_tts_console.sh` 前台启动，`Ctrl+C` 即可。

如果使用了 Codex 临时注册的 launchd 服务：

```bash
launchctl remove local.ai-jarvis.github-podcast.tts-console
```
