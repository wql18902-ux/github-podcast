# 豆包 seed-audio 播客合成流程（对话内工具路线）

「一份长口播稿（md）→ 分段合成 → 拼接 → m4a 成品 → 网易云」的固定流程，全部参数为 2026-09-09 实测（8 分钟版 ×1、51 分钟版 ×1 跑通）。**2026-09-11 定档：PACE 4.0（450–500 字/段 ≈ 120s，1.0x 直接可听）+ 慵懒魅惑御姐音色 + BGM 打包（前缀见第三节）**。

> 与 `docs/tts-flow.md` 的区别：那篇是**火山引擎 API 路线**（要 API Key、120 字/请求、ffmpeg atempo 变速）；本篇是**豆包对话内 seed-audio 路线**（`text_to_audio_plus` / `audio_to_audio_plus`，无需 Key、无需 ffmpeg、用 `duration` 参数直接锁时长）。两条路线二选一，本篇是默认路线。

## 前置依赖（整合方须知）

- **生成能力**：豆包 `seed-audio` 技能，工具 `text_to_audio_plus`（T2A，本流程用它）/ `audio_to_audio_plus`（A2A，本流程不用，原因见坑位 1）。
- **系统环境**：macOS；校验用自带 `afinfo`，压缩用自带 `afconvert`，无需 ffmpeg；下载用 `curl`；拼接用系统 `python3` 标准库（wave/struct，无第三方包）。
- **上传网易云**：`bash scripts/pipeline.sh upload`（封装 ncm-cli，死代理已绕过，已实测跑通），需已登录网易云账号。
- **输入**：一份纯口播稿 markdown；**输出**：一个单声道 64kbps 的 m4a 成品。

## 流程总览

```
口播稿 md
  → 剥 markdown、按自然段切分、按目标语速反推每段时长
  → text_to_audio_plus 分批并行（每段带 duration，上限 120s）
  → 下载，afinfo 逐段验时长
  → 手动提取 PCM 重写标准 WAV 拼接（中间产物，留 /tmp，不进项目目录）
  → afconvert 压成单声道 64kbps m4a（唯一默认成品，小体积）
  → bash scripts/pipeline.sh upload 上传网易云
```

## 一、硬约束（工具本身的边界）

| 项 | 结论 |
|---|---|
| 单次生成上限 | **120 秒**，`duration` 取 1–120 整数 |
| 不锁时长会怎样 | 模型自由发挥，语速约 8–9 字/秒，总时长严重缩水（实测 6 段目标 480s，首跑只有 336s） |
| 锁时长效果 | 每段时长**精确命中**（31 段全部零误差），靠放慢语速+自然停顿填满 |
| 输出格式 | WAV，40kHz / 16bit / 立体声 PCM；**data chunk size = 0xFFFFFFFF（流式头）** |
| A2A 音色克隆 | **不可用**：参考音频 URL 路径必须以 `.wav/.mp3/.ogg/.m4a/.aac/.pcm` 结尾，而平台返回的 `aka.doubaocdn.com/s/xxx` 短链不带扩展名；下载成本地 wav 再 FileBatchUpload 重传，拿到的还是无扩展名短链。跨段音色统一只能靠**每段使用完全相同的主播描述文案**，允许极细微音色漂移 |
| 并发 | 每批 6 个请求并行无压力；50 分钟约 5 批 |

## 二、切稿（决定成败的一步）

**直接用脚本**：`python3 scripts/split_segments.py <文稿.md> <PACE> <输出目录> [--unit char|han]`
它会产出各段 txt + manifest.json，并打印一份报告（段数、总时长、真实语速、clip 告警）。下面规则是脚本的实现依据。

### 规则

1. 剥掉 markdown：`#` 标题、`>` 引用、`---` 分隔线、空行全部丢弃。
2. **自然段是最小单位，绝不在句子中间切断**（否则拼接处生硬）。
3. 贪心合并相邻段落到目标字数。
4. **目标语速 PACE（2026-09-11 定档：4.0）** —— 先定口径，中文标点约占 30%，`char`/`han` 两档差 40%：

   | unit | 含义 | PACE 4.0 的实际效果 |
   |---|---|---|
   | `char`（默认） | 字符/秒（含标点） | **约 187 汉字/分钟，1.0x 直接可听** |
   | `han` | 汉字/秒 | PACE 4.0 → 240 汉字/分（偏快） |

   参考：正常播客 200-240 汉字/分钟。历史成品（ECC 51min、n8n 60min）是旧档 PACE 3.58 char（~148 汉字/分钟，**偏慢 35%**）——用户因此被迫 1.5x 倍速补偿；4.0 档按 1.0x 可听定。
5. **TARGET（字/段）由 PACE 推导：`int(120 * PACE)`**，不要硬编码。
   （PACE 4.0 → 480 字/段 ≈ 120s，顶满单次生成 2 分钟上限；450–500 字/段是用户实测的最佳档。）
6. **超长段必须先按句号、再按逗号拆开，不能直接 clip**。
   n8n 那期就有几个 800+ 字的自然段，只按段切会算出 230-290s，撞上限后语速失真近一倍。
7. 过短段（< 30s 量）**并入相邻段**，不要强拉到 30s —— 50 字段拉到 30s 等于慢 53%。
8. 段数估算：总字数 ÷ TARGET。约 12500 字符 / 480 ≈ 26 段（PACE 4.0 比 3.58 段数更少）。

脚本已落到 **`scripts/split_segments.py`**（上面的规则 5/6/7 都已实现），不要在文档里复制内联版本——内联版和文件会 drift。

```bash
# 默认档（2026-09-11 定档）：char 口径 PACE 4.0 → 480 字/段 ≈ 120s，1.0x 可听
python3 scripts/split_segments.py output/latest-script.md 4.0 /tmp/segs

# 旧档（已弃用）：3.58 复现历史成品（~148 汉字/分钟，太慢，曾被迫 1.5x 听）
# python3 scripts/split_segments.py output/latest-script.md 3.58 /tmp/segs
```

跑完务必看报告的「真实语速」行和 clip 告警，不要等生成完才发现时长对不上。

## 三、生成（text_to_audio_plus）

- 每段 prompt = **固定主播前缀 + 该段正文**，前缀所有段一字不差（2026-09-11 换音色：慵懒魅惑御姐 + 全片 BGM/音效/环境声打包）：

```
一档单人科技播客，主播是慵懒魅惑的御姐女声（魔女 / 卡芙卡风格，带松弛勾人感）：30 岁女性声优，声线低沉磁性，轻微气泡颗粒感，慵懒松弛，尾音轻轻拖长，语气暧昧从容，呼吸感自然，情绪淡淡的，不夸张。安静室内底噪，微弱空气声。全片叠加极轻柔的氛围 BGM（舒缓、循环、低音量不压人声）与微弱环境音效，人声 + BGM + 音效 + 环境声整体打包合成。说："（本段正文）"
```

- 每段必须带 `duration`（取自 manifest）。
- 每批并行 6 个；按顺序登记返回的短链 URL，别搞乱顺序。
- 个别段失败直接重试该段即可，已成功的不用重跑。

## 四、下载与校验

```bash
mkdir -p /tmp/ep_audio && cd /tmp/ep_audio
# urls.txt 每行一个短链，顺序 = 段序
i=1; while read u; do n=$(printf "a%02d.wav" $i); curl -sL -o "$n" "$u"; i=$((i+1)); done < urls.txt

# 用 afinfo 读真实时长；总时长求和
total=0; for f in a*.wav; do d=$(afinfo "$f" | grep "estimated duration" | awk '{print $3}'); echo "$f ${d}s"; total=$(echo "$total+$d"|bc); done; echo "TOTAL ${total}s"
```

**坑：不要用 Python `wave` 读时长**。这些 WAV 的 data 长度是流式标记 0xFFFFFFFF，`wave` 会把每段误读成 26843.5 秒。校验一律用 macOS 自带 `afinfo`。

## 五、拼接（手动提 PCM，重写标准 WAV）

WAV 只作**中间产物**，放 /tmp，不作为交付物（40k/16bit/立体声 ≈ 1.5MB/分钟，50 分钟 490MB，无保留价值）。

```python
# concat_wav.py  用法: python3 concat_wav.py /tmp/ep_audio /tmp/ep_full.wav
import glob, struct, wave, sys
indir, out = sys.argv[1], sys.argv[2]

def pcm(path):
    d = open(path, "rb").read()
    i = d.find(b"data")
    size = struct.unpack("<I", d[i+4:i+8])[0]
    body = d[i+8:]
    return body[:size] if size != 0xFFFFFFFF and size <= len(body) else body

with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(40000)
    for f in sorted(glob.glob(f"{indir}/a*.wav")):
        w.writeframes(pcm(f))
```

## 六、压缩成成品 m4a（默认只出一个小文件）

用 macOS 自带 afconvert，不需要 ffmpeg。**默认成品只有一个：单声道 64kbps m4a**（纯人声播客，与立体声 128k 听感无差，51 分钟 ≈ 25MB，体积小、网易云云盘和手机都好放）：

```bash
# 成品命名惯例：项目名-播客完整版-XXmin.m4a；存到 output/audio/ 分类
cd <项目根目录>/output/audio
afconvert -f m4af -d aac -b 64000 -c 1 /tmp/ep_full.wav "项目名-播客完整版-XXmin.m4a"
```

仅当明确要高音质时才额外出立体声 128kbps（51 分钟 ≈ 42MB）：`afconvert -f m4af -d aac -b 128000 ...`。**永远不交付 WAV**。

## 七、上传网易云

```bash
# 走 pipeline.sh 封装（内置死代理绕行 + 保原文件名，底层 ncm-cli cloudupload upload，已实测跑通）
# pipeline.sh 内部会 cd 到项目根；成品已在 output/audio/ 里，传相对项目根的路径
bash scripts/pipeline.sh upload "output/audio/项目名-播客完整版-XXmin.m4a"
```

ncm-cli 需已登录网易云账号。成品保留原文件名进网易云云盘，手机网易云 App 开云盘直接听。

## 八、坑位清单（全部实测踩过）

1. **A2A 走不通**：平台短链无音频扩展名，下载重传也没用 → 不做跨段音色克隆，统一主播描述文案。
2. **不锁 duration 必缩水**：模型默认语速过快，必须每段传 `duration`；prompt 用固定主播前缀锁音色与声场（御姐 + BGM 打包版）。
3. **Python wave 误读流式 WAV 头**（每段 26843.5s）：校验用 afinfo，拼接手动定位 `data` 块提 PCM。
4. **成品体积**：单声道 64kbps m4a，51 分钟 ≈ 25MB，比立体声 128k 省一半，网易云云盘和手机都好放。
5. **走 pipeline.sh 封装**：用 `bash scripts/pipeline.sh upload 文件`（内置死代理绕行），别裸调 `ncm-cli cloudupload upload`（会踩死代理 127.0.0.1:7890）。
6. **切分不能切半句**：只在自然段/句号边界切，拼接才顺。
7. **成品只要小文件**：默认只出一个单声道 64kbps m4a（本地交付和上传网易云用同一份）；不交付 WAV（40k/16bit/立体声 ≈1.5MB/分钟，50 分钟 490MB，无收益），也不默认出立体声 128k；WAV 只当 /tmp 中间产物。
8. **PACE 口径必须先定清楚**（2026-09-10 踩的）：中文标点约占 30%，`char`（含标点）和 `han`（纯汉字）两档算出的总时长差 40%。n8n 那期「标称 45 分钟、实际 60 分钟」就是标称按汉字算、脚本按字符算。现在脚本会打印两种口径的真实语速，跑完先看那行。
9. **超长自然段必须先按句号拆**：只按自然段切会让 800+ 字的段算出 230-290s，撞 120s 上限后语速失真近一倍。脚本已实现（句号→逗号两级拆）。
10. **别在文档里维护内联脚本副本**：切稿逻辑以 `scripts/split_segments.py` 为准，文档只写用法。

## 九、实测基准数据

| 版本 | 字符 | 汉字 | 段数 | PACE | unit | 真实语速 | 总时长 | 成品 |
|---|---|---|---|---|---|---|---|---|
| 8 分钟版（whisper.cpp） | ~2700 | — | 6 | ~5.6 | char | — | 480s 整 | m4a |
| 51 分钟版（ECC） | 10977 | — | 31 | 3.58 | char | ~149 汉字/分（推算） | 3064s（51:04），零误差 | 单声道 64k，24.8MB |
| 60 分钟版（n8n） | 12917 | 8987 | 38 | 3.58 | char | **148 汉字/分** | 3600s（60:00），零误差 | 单声道 64k，29.3MB |

历史三期真实语速都在 ~150 汉字/分钟（PACE 3.58 char 旧档），比正常播客慢约 35%，用户因此被迫 1.5x 倍速补偿。**2026-09-11 定档 PACE 4.0 char（450–500 字/段 ≈ 187 汉字/分钟），1.0x 直接可听**；PACE 4.0 整期首跑后在此回填实测行。
