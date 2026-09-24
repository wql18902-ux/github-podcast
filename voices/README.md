# voices/ —— 播客音色库

这个目录管「播客用哪把嗓子」。

## 机制

`scripts/tts_local.py` 里写死了标准路径：

```
voices/podcast-voice.wav      ← 存在 = 自动启用克隆模式，整期锁这一个音色
voices/podcast-voice.txt      ← 可选：上面那段 wav 对应的文本，提升克隆稳定性
```

- **有这个文件** → 合成走 `generate_with_clone`，全期同一音色（正路）
- **没有这个文件** → 走默认的 `generate`，**每段现采一个新音色**，整期音色乱跳（2026-09-11 踩过的坑，见下）

换音色 = 换掉 `podcast-voice.wav`（和同名 .txt）即可，不用改任何代码。

**换音色只动这一个文件，别改代码。** 仓库不附任何参考音频——那是作者本人的声音，公开它没有意义。
按下面「造一把新嗓子」自己做一段 10-20 秒干净人声放进来即可。

实测口径（2026-09-11）：基频 164.4 Hz 的参考 → 克隆输出 166.7 Hz，**差 1.4%**；
只给音频不给文本的纯克隆差 **10.6%**。所以 `podcast-voice.txt`（参考文本）是必需项，不是可选升级。

## 为什么需要这个（2026-09-11 踩的坑）

`llama-tts-server` 的 `/v1/audio/speech`：

| 请求带 reference_audio | 走哪条路 | 音色 |
|---|---|---|
| 不带 | `rt->generate(input)` | **每段随机**（seed 只管「同文本两次一致」） |
| 带 | `generate_with_clone` | 锁在参考上 |

第一次整期全量合成（122 段）就是没带参考，结果音色乱跳。A/B 实测基频中位数（**量基频的尺子本身修过一次 bug，2026-09-11；下面是修好后的数**）：

- 不带参考 3 段：240.0 / 133.3 / 169.0 Hz（散 107 Hz ≈ 0.85 个八度，先女后男）
- 带参考 3 段：193.5 / 203.4 / 200.0 Hz（参考 cand-42 = 193.5 Hz，差 9.9 Hz ≈ 5%，锁住了）
- **终极克隆（参考音频 + 参考文本）**：参考 164.4 Hz → 输出 166.7 Hz（**差 1.4%**）；
  只给音频的纯克隆差 **10.6%** → **参考文本是必需项，不是可选升级**

## 造一把新嗓子（一条命令，2026-09-11 新增）

```bash
cd <项目根目录>
bash scripts/voice_from_media.sh <音视频> <音色名> [起始秒] [时长秒]   # 出 <名>.wav + <名>.txt
# 只想要参考音频、自己接转写：bash scripts/make_voice_ref.sh ...
```

- 内部 = 抽音频 → 单声道 48k → `loudnorm=I=-20` 归一 → SenseVoice 转写 → 落 `voices/<名>.{wav,txt}`
- **参考必须先切到「完整句末」再转写**：切在半句上，文本会和音频对不上（实测先切 20s，末尾被截成「急什」，白转一轮；用 `silencedetect` 找静音边界重切 79.63→98.13s 才干净）
- ⚠️ **别用 `volume=+6dB` 之类拍脑袋增益**：引擎输出本来就常用贴近满刻度，喂过热的参考只会加重杂音；要归一就 `loudnorm`，而且方向是往下压
- 起停 SenseVoice 的坑（脚本里已处理）：常驻进程用裸 `&` 会吊住调用方终端 → `nohup … & disown` 起、收尾 `pkill -f sensevoice_onnx_server`

## 输出侧的保险丝：限幅 -1.5 dBTP

`tts_local.py` 最终编码**始终**挂 `alimiter=limit=0.8414:level=disabled`（= -1.5 dBTP，只削峰不动响度），与 `--pace` 无关。

实测结论（别照旧结论归因）：**克隆模式**的模型输出峰值 -4.0 ~ -4.2 dB，本来就有约 4 dB 余量、不削波；
贴着 0 dBFS 的是**旧的无参考模式**（-0.10 dB）。所以限幅是**保险丝**，别把它当「杂音」的主因——
克隆链路上的杂音更可能来自声码器底噪。详细测量与判定法见 skill `podcast-local-tts` 与
`research/本地TTS调研/research-2026-09-10/evidence-ledger.md` E042/E043。

## 怎么选一把嗓子

候选音色试听在：

```
<VoxCPM2 引擎目录>/samples/voice-ref/试听/
```

造新候选（改 seed 即换音色）：

```bash
cd <VoxCPM2 引擎目录>
python3 voice_ref_test.py          # 产出 samples/voice-ref/cand-<seed>.mp3
```

选定后放进来：

```bash
cp <挑中的>.wav <项目根目录>/voices/podcast-voice.wav
cp <对应的参考文本>.txt <项目根目录>/voices/podcast-voice.txt
```

## 验收

```bash
cd <项目根目录>
python3 scripts/tts_local.py --input output/latest-script.md --output /tmp/t.m4a --limit 2
```

头一行应打印 `... / 克隆锁音色(podcast-voice.wav)`；若打印 `每段随机音色` 说明文件没放对。
