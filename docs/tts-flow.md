# 火山引擎 TTS（豆包 seed-tts-2.0）语音生成流程

> 本文档是旧 API 备选路线。本地全离线路线（VoxCPM2，`scripts/tts_local.py` / `pipeline.sh synth-local`）见 README「本地路线」。

「一段文字 → 一个 mp3」的完整固定流程，全部参数为 2026-09-09 实测结论。参考实现：`scripts/tts.py`；官方接口文档：`豆包语音合成代码/豆包.md`。

## 流程总览

```
文本 → 按句分段(≤120字) → 逐段 POST → 解 base64 拼接 → ffmpeg atempo 变速 → mp3
```

播客整期文稿走 `pipeline.sh synth`；任意一段文字走 `pipeline.sh tts`（见文末）。

## Key 的获取与使用（红线：key 绝不落盘）

1. **获取**：火山方舟控制台 → 开通管理 → Agent Plan（语音模型）→ 创建专属 API Key（`ark-` 开头）。入口见 `豆包语音合成代码/豆包.md` 的「核心配置」一节。
2. **注入**（二选一）：
   - 单次内联（推荐，不留痕）：`DOUBAO_TTS_KEY=ark-xxx bash scripts/pipeline.sh synth`
   - 长期会话：自己 `export DOUBAO_TTS_KEY=ark-xxx`（可写进 `~/.zshrc`，那是你的个人 shell 配置；项目文件里永远不出现 key）
3. **验证 key 好坏**（反向验证法）：
   - 错 key → `HTTP 401`，tts.py 重试 3 次后退出码非 0（红）
   - 对 key → 合成一句话成功（绿）
   - 脚本已内置：无 key 直接报错退出码 2，不空跑

## 接口细节

```
POST https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional
X-Api-Key: <$DOUBAO_TTS_KEY>
X-Api-Resource-Id: seed-tts-2.0
Content-Type: application/json

{"req_params": {
    "text": "<一段文本，≤120字>",
    "speaker": "zh_female_vv_uranus_bigtts",
    "audio_params": {"format": "mp3", "sample_rate": 24000}
}}
```

**响应不是一次性 JSON，是 chunked JSON lines**：每行一条，`data` 字段是 base64 音频块，收到 `code: 20000000` 表示本段结束；其他非零 `code` 是错误（如 `55000000` = 音色与 resource 不匹配）。逐行解析、解码、顺序追加即可。

## 关键参数（实测）

| 参数 | 值 | 说明 |
|------|-----|------|
| 音色 | `zh_female_vv_uranus_bigtts` | 默认；备选 `zh_female_gaolengyujie_uranus_bigtts`，语速相同 |
| 采样率 | 24000 Hz mp3 单声道 | |
| 分段 | ≤120 字/请求 | 短句合并、长句按逗号硬切；整期 11700 字 ≈ 123 段 ≈ 6 分钟 |
| 变速 | ffmpeg `atempo 0.72` | 原始语速约 340 字/分钟；0.72 后 ≈232 字/分钟（50 分钟档） |
| 重试 | 3 次/段 | 网络抖动自动重试，指数退避 |

## 坑位备忘（全部实测踩过）

1. **speed / speed_ratio 参数无效**（实测只有 ~3% 差异）——调语速只能靠 atempo 后处理。
2. **原始语速 ~340 字/分钟**，明显快于播客节奏；要落到 ~230 字/分须 atempo 0.72。注意：atempo 是为了语速舒服，不是为凑时长。
3. **音色分资源**：非 seed-tts 音色（如 `zh_male_M392_conversation_wvae`）报 code 55000000，资源 ID 与音色不匹配。
4. **死代理**：本机代理变量指向 127.0.0.1:7890 且代理常不在，直接请求会连接失败——tts.py 内部已用 `trust_env=False` 绕行；裸 curl 排障时须 `env -u http_proxy -u https_proxy ...`。
5. **飞书语音消息位只收 opus**，mp3 走文件消息（`lark-cli im +messages-send --file`）。

## 排障表

| 症状 | 原因 | 处置 |
|------|------|------|
| `HTTP 401` | key 错/过期 | 核对 key；控制台重新生成 |
| `code 55000000` | 音色与 seed-tts-2.0 不匹配 | 换回 bigtts 系音色 |
| 连接失败/EOF | 死代理 | 脚本已绕行；裸调用剥代理变量 |
| 某段 3 次重试全失败 | 网络抖动 | 直接重跑（已合成段不缓存，会整期重合成） |
| 时长短于 30 分钟 | 忘了 atempo 或文稿太短 | `pipeline.sh synth` 已内置 0.72 + 下限验收；长短本身不是问题 |

## 一键用法

```bash
# 播客整期（文稿 → 合成 → 自动验时长）
DOUBAO_TTS_KEY=ark-xxx bash scripts/pipeline.sh synth

# 任意文本（txt/md 均可，输出可选，默认 /tmp/tts_out.mp3）
echo "你好，这是测试。" > /tmp/test.txt
DOUBAO_TTS_KEY=ark-xxx bash scripts/pipeline.sh tts /tmp/test.txt /tmp/test.mp3
```
