# 证据登记簿

采集日期：2026-09-13

## 本机实测

| 编号 | 信息 | 来源 | 置信度 | 摘要 |
|---|---|---|---|---|
| L01 | 2026-09-12 本地兜底合成：5222 汉字，97 段，原生音频 1901 秒 | `github-podcast/output/local-fallback.log` | A | 逐段耗时求和 1901.5 秒，RTF≈1.00；语速 165 汉字/分 |
| L02 | 2026-09-12/13 调研稿合成：3949 汉字，70 段，原生音频 1390 秒 | `github-podcast/output/research-synth.log` | A | 单次完整逐段耗时约 1390 秒，RTF≈1.00；语速 170 汉字/分 |
| L03 | 本地机器为 MacBook Air M4 / 16GB | `system_profiler` | A | 本机实测 |
| L04 | 当前本地 TTS 为 VoxCPM2 2B GGUF Q8 + Metal，常驻服务约占 2.1GB 内存 | `scripts/tts_local.py`、本地能力清单 | A | 模型和脚本均已接入生产链路 |
| L05 | 本地功率未做仪表测量 | 本机 | A | 报告中的 20-40W 仅用于电费区间估算，不是实测功耗 |

## 千问

| 编号 | 信息 | 来源 | URL | 置信度 | 摘要 |
|---|---|---|---|---|---|
| Q01 | `qwen3-tts-flash`、`qwen3-tts-instruct-flash` 均 0.8 元/万字符 | 千问模型页 | https://www.qianwenai.com/models/qwen3-tts-flash ; https://www.qianwenai.com/models/qwen3-tts-instruct-flash | A | 页面价格栏原文为“语音合成 ¥0.8 每万字符” |
| Q02 | `qwen-audio-3.0-tts-plus` 为 1.4 元/万字符 | 千问模型页 | https://www.qianwenai.com/models/qwen-audio-3.0-tts-plus | A | 高质量 Qwen-Audio-TTS |
| Q03 | 千问 TTS 按输入文本字符计费；一个汉字计 2 个字符 | 千问计费说明 | https://platform.qianwenai.com/docs/developer-guides/getting-started/pricing.md | A | 中文成本要按“汉字数×2”再套每万字符单价 |
| Q04 | Qwen3-TTS-Flash、Instruct、VC、VD 等 TTS 模型常见免费额度为 1 万字符/模型，90 天 | 千问/百炼模型价格表 | https://help.aliyun.com/zh/model-studio/model-pricing?disableWebsiteRedirect=true | A | 不同模型额度独立，不互通；控制台权益页最终为准 |
| Q05 | CosyVoice 系列多款模型也有 1 万字符/模型的免费额度 | 千问/百炼模型价格表 | https://help.aliyun.com/zh/model-studio/model-pricing?disableWebsiteRedirect=true | A | v3.5-flash 0.8 元/万字符，v3.5-plus 1.5 元/万字符等 |
| Q06 | MiniMax 接入千问平台时，HD 3.5 元/万字符，Turbo 2 元/万字符，免费额度为无 | 千问/百炼模型价格表 | https://help.aliyun.com/zh/model-studio/model-pricing?disableWebsiteRedirect=true | A | 平台可接 MiniMax，但不算千问自研 TTS 免费额度 |
| Q07 | 用户权益页实际有 `qwen-audio-3.0-tts-plus`、`qwen-audio-3.0-tts-flash` 各 10K chars | 用户截图 | `<本地截图>2026-09-13 21.36.51.png` | A | 两者为当前账号可直接使用的 Qwen-Audio-TTS 额度 |
| Q08 | 用户权益页有 `cosyvoice-v1`、`cosyvoice-clone-v1` 各 10K chars，且显示永不过期 | 用户截图 | `<本地截图>2026-09-13 21.36.48.png` | A | 适合做免费系统音和免费克隆路线 |
| Q09 | 两个 `qwen-audio-3.0-realtime` 模型各 1M tokens | 用户截图 | `<本地截图>2026-09-13 21.36.48.png` | A | 更适合实时语音交互，不按普通长稿 TTS 直接折算 |
| Q10 | `cosyvoice-v1 / longyuan` 试听基频中位数 164.4 Hz，与现役 `podcast-voice.wav` 相同 | 官方试听 + 本机分析 | https://platform.qianwenai.com/docs/developer-guides/speech/voice-list/cosyvoice | A | 候选系统音里最接近现役参考音 |

## 腾讯

| 编号 | 信息 | 来源 | URL | 置信度 | 摘要 |
|---|---|---|---|---|---|
| T01 | TokenHub 语音合成：MiniMax Speech 2.8 HD 3.5 元/万字符，Turbo 2 元/万字符 | TokenHub 模型价格 | https://cloud.tencent.com/document/product/1823/130055 | A | 音色克隆另收 9.9 元/音色 |
| T02 | TokenHub 新用户免费包只列语言模型、视觉模型、多模态理解模型，没有语音合成 | TokenHub 新人免费体验包 | https://cloud.tencent.com/document/product/1823/130053 | A | 产品页“100 万 tokens”不能直接拿来当 TTS 免费额度 |
| T03 | 腾讯云 TTS 免费额度：基础/精品音色 800 万字符，大模型音色 10 万字符，超自然大模型音色 2 万字符 | 腾讯云语音合成计费概述 | https://cloud.tencent.com/document/product/1073/34112 | A | 领取后 3 个月有效，一个账号一次；仅通用语音合成接口，不含长文本和播客接口 |
| T04 | 腾讯云通用 TTS 后付费：超自然大模型 6.5 元/万字符起，大模型音色 1.2 元/万字符起，精品音色 0.3 元/万字符 | 腾讯云语音合成计费概述 | https://cloud.tencent.com/document/product/1073/34112 | A | 阶梯价按日用量变化；短文本每日 8500 字落在最低档 |
| T05 | MiniMax Voice Clone/Design 为 9.9 元/音色 | TokenHub 模型价格 | https://cloud.tencent.com/document/product/1823/130055 | A | 首次使用该音色合成时随 TTS 一并收取 |

## 火山

| 编号 | 信息 | 来源 | URL | 置信度 | 摘要 |
|---|---|---|---|---|---|
| V01 | 豆包语音合成公开价 5 元/万字符，声音复刻 8 元/万字符 | 火山方舟产品页/豆包大模型页 | https://www.volcengine.com/product/ark | A | 方舟公开模型价格表口径 |
| V02 | 豆包语音合成模型 2.0 独立语音服务后付费可到 3 元/万字符，资源包可低至约 2.4-2.8 元/万字符 | 豆包语音计费说明 | https://www.volcengine.com/docs/6561/1359369?lang=zh | A | 与方舟公开 5 元/万字符不是同一售卖口径，实际以购买入口为准 |
| V03 | 豆包语音独立试用：语音合成模型 2.0、声音复刻 2.0、各 20000 字符，有效期半年 | 豆包语音计费概述 | https://www.volcengine.com/docs/6561/1359369?lang=zh | A | 需在豆包语音控制台领取 |
| V04 | 火山方舟语音模型体验页写明语音合成免费额度 20000 字符，且写明当时仅对企业客户开放 | 火山方舟语音模型页 | https://www.volcengine.com/docs/82379/1347809?lang=zh | B | 页面后续发生重定向；同时方舟产品页“免费额度”表又列 Doubao-语音合成 5000 字符，存在控制台口径差异 |
| V05 | Agent Plan 中 `doubao-seed-tts-2.0` 抵扣系数为 1350 AFP/万字符 | Agent Plan 套餐内 AFP 抵扣规则 | https://docs.volcengine.com/docs/82379/2516283?lang=zh | A | 计算公式为“文本字符数 / 10000 × 1350” |
| V06 | Agent Plan 个人版 Small 为 40 元/月、20000 AFP；Medium 200 元/月、100000 AFP；Large 500 元/月、250000 AFP；Max 1000 元/月、500000 AFP | Agent Plan 套餐概览/活动页 | https://www.volcengine.com/activity/agentplan ; https://docs.volcengine.com/docs/82379/2366394 | B | 若 AFP 全部用于 TTS，等效约 2.7 元/万字符；现实中会被其他模型共享 |
| V07 | 豆包语音合成当前活动页出现 16.8 元/10 万字符的限时首购价 | 火山引擎 AI 普惠季活动页 | https://www.volcengine.com/activity/ai618 | B | 限时活动，不能当长期标准价 |
| V08 | 用户 Agent Plan Medium：5 小时额度 0/1 万 AFP；周额度 3.5 万/3.5 万，已用 99.68%；月额度 7 万/10 万，已用 70.25% | 用户截图 | `<本地截图>2026-09-13 21.49.50.png` | A | 周剩余约 112 AFP，月剩余 3 万 AFP |
| V09 | Agent Plan TTS HTTP URL 为 `/api/v3/plan/tts/unidirectional`，Resource ID 为 `seed-tts-2.0` | 用户截图 | `<本地截图>2026-09-13 21.50.09.png` | A | 不使用普通 Ark `/api/v3`，避免额外费用 |
| V10 | `doubao-seed-tts-2.0` 每万字符扣 1350 AFP | 用户截图/官方 AFP 规则 | `<本地截图>2026-09-13 21.50.49.png` | A | 8500 汉字一期约扣 1147.5 AFP |
| V11 | 语音模型、Harness 没有 5 小时限额与周限额；开启超额后付费后仅在触达月限额时切换 | 官方超额后付费规则 | https://docs.volcengine.com/docs/82379/2516284 | A | 周额度耗尽不应直接拦 Agent Plan TTS |
| V12 | 独立豆包语音新版统一使用 `/api/v3/tts/unidirectional`，TTS 1.0/2.0/ICL 2.0 分别用 `seed-tts-1.0`、`seed-tts-2.0`、`seed-icl-2.0` | 官方新版 HTTP 文档 | https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh | A | 与 Agent Plan 的 `/plan/` 路径不同，Key 也独立 |
| V13 | 音色设计入口为 `/api/v3/tts/voice_design` | 官方音色设计 HTTP 文档 | https://www.volcengine.com/docs/6561/2277844?lang=zh | A | 只做音色设计，不直接合成成品音频 |

## 复算

统一按一期 8500 个汉字计算。

### 千问

```text
计费字符 = 8500 × 2 = 17000
费用 = 17000 / 10000 × 单价

qwen3-tts-flash / instruct：17000 / 10000 × 0.8 = 1.36 元
qwen-audio-3.0-tts-plus：17000 / 10000 × 1.4 = 2.38 元
```

### 腾讯 TokenHub

```text
Turbo：8500 / 10000 × 2 = 1.70 元
HD：8500 / 10000 × 3.5 = 2.98 元
```

### 腾讯云自有 TTS

```text
精品音色：8500 / 10000 × 0.3 = 0.26 元
大模型音色：8500 / 10000 × 1.2 = 1.02 元
超自然大模型：8500 / 10000 × 6.5 = 5.53 元
```

### 火山

```text
方舟公开价 TTS：8500 / 10000 × 5 = 4.25 元
方舟公开价声音复刻：8500 / 10000 × 8 = 6.80 元
Agent Plan 等效：8500 / 10000 × 2.7 = 2.30 元
活动首购等效：8500 / 10000 × 1.68 = 1.43 元
```

### 本地

```text
音频时长 = 8500 / 168 ≈ 50.6 分钟
本地 RTF≈1.0，因此机器时间约 50.6 分钟

按 20W、0.6 元/kWh：
(50.6 / 60) × 20 / 1000 × 0.6 ≈ 0.010 元

按 40W、0.6 元/kWh：
(50.6 / 60) × 40 / 1000 × 0.6 ≈ 0.020 元
```
