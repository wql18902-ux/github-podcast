# output/ 目录约定

> 2026-09-10 整理。规矩一句话：**脚本硬编码的路径留在根，历史期次进 `episodes/`。**
> 停用但没删的东西不在本目录。作者的私有工作副本里有一层 `_归档/`，公开仓不带。

## 留在根的文件（别改名、别移动、别看它们乱就想收拾）

`scripts/daily-prepare.sh`、本地合成脚本和人工云 TTS 控制台按这些路径读取文件，动一个就可能断链。

| 文件 | 谁写 | 谁读 | 是什么 |
|---|---|---|---|
| `latest-script.md` | 夜班写稿 | `local-fallback.sh` / 人工云 TTS 控制台 | **当期稿**，管道唯一的稿件交接点 |
| `latest-status.txt` | `daily-prepare.sh` 验收后 | `local-fallback.sh` | 状态闸。首行 `OK` 才合成；`FAILED` 就跳过 |
| `episodes.log` | `episode.py` | 选料去重 | 讲过的项目清单，**只追加不删改**（防重讲） |
| `<日期>.md` | `fetch.py` | 选料 | 当日信息源清单（86 个海外项目） |
| `<日期>-script.md` | 夜班写稿 | 留档 | 当期稿的 dated 副本，和 `latest-script.md` 内容相同 |
| `<日期>-breakdown.md` | 夜班写稿 | `daily-prepare.sh` 过程闸 | 拆解笔记，≥10 字段 + ≥2000 字节才算过闸 |
| `podcast-01-whisper-cpp.md` | 人工 | 写稿 agent | 第 1 期稿，**同时是全项目的文稿口径样板**（CLAUDE.md / DESIGN.md 都指向它），所以不归档 |
| `audio/` | 本地 `synth-local` / `research-synth.sh` | 手动上传网易云 | 正式成品音频 |
| `tts-console/` | 人工云 TTS 控制台 | 人工试听 | Agent Plan / Qwen 等云 TTS 样音，不是夜班成品 |
| `tts-audition/` | 官方音色样音/本地整理 | 人工试听 | 云 TTS 音色筛选素材 |
| `probe/` | 调试脚本/临时 A/B | 人工复核 | 测试音频和截图；稳定结论进 `docs/` 后可清 |

**为什么日期是「明天」**：`<日期>-script.md` 的日期取的是**音频上线日**不是写稿日。22:30 写的稿，02:00 合成，早上听到——所以 09-10 晚上写的稿叫 `2026-09-11-script.md`。

## `episodes/` —— 历史期次归档

一期一个文件夹。每期至少留稿子，有拆解笔记的留拆解。

| 期 | 项目 | 稿子 | 拆解 | 成品音频 |
|---|---|---|---|---|
| 1 | ggml-org/whisper.cpp | `podcast-01-whisper-cpp.md`（在根，见上） | — | — |
| 2 | affaan-m/ECC | `ep2-ecc/script.md`（另有两版：`完整稿-50min.md`、`试水稿.md`） | `ep2-ecc/breakdown.md` | `audio/ecc-播客完整版-51min.m4a` |
| 3 | NousResearch/hermes-agent | `ep3-hermes-agent/script.md` | — | `audio/hermes-播客完整版-114min.m4a` |
| 4 | n8n-io/n8n | `ep4-n8n/script.md` | — | `audio/n8n-播客完整版-60min.m4a` |
| 5 | topic:AI-Agents(Claude-Code) | `ep5-claude-code/script.md`（2026-09-11 夜班归档，原件在根被第 6 期覆盖） | ⚠️ **丢了**：原 `2026-09-11-breakdown.md` 被第 6 期同路径覆盖，无副本 | `audio/agent-播客完整版-57min.m4a` |
| 6 | Significant-Gravitas/AutoGPT | `ep6-autogpt/`（根目录的 `2026-09-11-script.md` 是它的原件，被第 7 期覆盖前已归档） | `2026-09-11-breakdown.md` | `audio/autogpt-播客完整版-38min.m4a` |
| 7 | openai/codex（对比 Claude Code） | `latest-script.md` + `2026-09-12-script.md`（**当期，等音频**） | `2026-09-12-breakdown.md` | 待合成 |

**当期为什么还在根**：稿子一旦离开 `latest-script.md`，合成链路就找不到它了。等 `audio/` 里出现当期成品，再按下面那三步把它移进 `episodes/ep7-codex-claude-code/`。

> ⚠️ **2026-09-12 状态闸没跟上**：第 7 期稿（12:21 写）是**手动会话**产出，没走 `daily-prepare.sh`，
> 所以 `latest-status.txt` 至今仍是第 6 期的 `OK 2026-09-11`。`scripts/local-fallback.sh` 的第①道闸
> 只判首行是否 `OK`、不判日期，会照常合成——**但状态的准确性靠人**。下次手动写稿后记得补写状态文件。

> ⚠️ **2026-09-11 日期撞车事故（第 5 期 vs 第 6 期）**：第 5 期按「音频上线日」命名，稿子和拆解都叫 `2026-09-11-*`；当晚 22:30 的夜班按 `daily-prepare.sh` 里的 `TODAY=$(date +%F)` 又写同一组路径。稿子因为当天先抄了一份进 `episodes/ep5-claude-code/` 保住，**拆解笔记没有第二份，被覆盖后无法恢复**。
> **根因**：本文件写的日期口径是「音频上线日 = 明天」，`daily-prepare.sh` 的过程闸（`output/${TODAY}-breakdown.md`）却按今天算，两个口径不一致。
> **要修的话**（二选一，别两边都留着）：① 把 `daily-prepare.sh` 里 `TODAY` 改成 `date -v+1d +%F`，跟本文件对齐；② 或者认「按今天算」，那夜班写稿前必须先归档上一期——**顺序不能反，反了就是这次这个结果**。

## 归档一期怎么操作

```bash
cd output
mkdir episodes/ep6-<项目名>
mv <日期>-script.md episodes/ep6-<项目名>/script.md
mv <日期>-breakdown.md episodes/ep6-<项目名>/breakdown.md
```

然后回本文件补一行表。

## `research/` —— 调研稿（2026-09-12 新建）

跟夜班拆解稿并列的第二条稿源，走**联网调研**而非读源码拆解。

| 文件 | 谁写 | 谁读 | 是什么 |
|---|---|---|---|
| `research/<日期>-<主题>.md` | Trae（claude headless + `scripts/write-research-prompt.md`） | `scripts/research-synth.sh` | 调研稿 |

**跟 `latest-script.md` 的区别**：那条路径是拆解稿专用、豆包硬编码读取，
调研稿**不写** `latest-script.md`、**不追加** `episodes.log`（那是拆解稿的地盘）。
合成产物走 `<日期>-research-<主题>.m4a` 命名，跟豆包产物、本地兜底产物都不撞名。

---

## 音频命名

现行惯例（`docs/seed-audio-schedule.md`）：`项目名-播客完整版-时长min.m4a`，**时长填实测值不填标称值**。

第 2 期原本还有一个旧 API 路线版 `2026-09-09-ep2.mp3`（更早的 `<日期>-ep<N>` 命名规则），2026-09-10 已挪进项目根的 `_归档/`——同期有更好的 seed-audio 版，留着是同一期两个音频。
