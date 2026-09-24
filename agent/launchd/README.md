# launchd 兜底班

> 这一步属于设计稿 §12.3 的**第 5-6 步**：先跑通，**最后才拆旧**。
> 在下面三条前提都满足之前，不要 bootstrap 这个 plist。

## 装之前必须满足的三条

1. **新链路已经跑通一期真稿**（`python3 -m agent.cli run` → `resume` → 有稿有音频）。
   旧链路还在的时候装新的，出问题分不清是谁的锅。
2. **旧兜底确实停着**。2026-09-21 实测：WorkBuddy 面板里「播客本地兜底」（03:00）**是 PAUSED**，
   且用户确认 **Trae 侧没有挂任何任务** → **旧的 03:00 兜底现在没在跑**。
   所以装这个 plist 不会跟谁抢 GPU。**但装完再回头把旧的打开就会抢**——两个同时跑会争
   `tts_local.py`（16G 机器跑不动两个，脚本里有 `pgrep -f tts_local.py` 互斥，真撞上只是后者跳过）。
3. **旧兜底那个「今天有没有成品」的判据不再被依赖**。
   `scripts/local-fallback.sh` 第 39 行用 `ls output/audio/${TODAY}*.m4a` 判，
   而豆包产物叫「项目名-播客完整版-NNmin.m4a」（**名字里没有日期**），所以那条判据
   **永远不成立**——豆包出了成品，它还会白跑两小时。新链路按 mtime 判（`agent/tools.py`
   的 `newest_product`），这个 bug 已经在新链路里绕开了。

> **为什么值得尽快装**：旧兜底停着 = **豆包那班一旦失败就完全没有兜底**，
> 那一夜就是没有音频（ep15 就是这么缺的）。

## 装

```bash
cp agent/launchd/com.github-podcast.fallback.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.github-podcast.fallback.plist

# 验证（看到 state = waiting / 有 StartCalendarInterval 就对了）
launchctl print gui/$(id -u)/com.github-podcast.fallback
```

想立刻试一次（不用等到 03:00）：

```bash
launchctl kickstart -p gui/$(id -u)/com.github-podcast.fallback
tail -40 /tmp/github-podcast-fallback.log
```

## 卸

```bash
launchctl bootout gui/$(id -u)/com.github-podcast.fallback
rm ~/Library/LaunchAgents/com.github-podcast.fallback.plist
```

## 它到底干什么

入口是 `python3 -m agent.cli fallback-auto`，从 `await_synth` 阶段续跑，两种结果都覆盖：

- **豆包已出成品** → `await_synth` 立刻按 mtime 找到 → 进 `publish`，**不重复合成**
- **豆包没出** → 过了 `synth_expect_by`（02:40）就进 `fallback`，先查有没有成品，
  再过三道闸（`latest-status.txt` 首行 OK / 稿子在 / 稿子 ≤12 小时），全过才真跑本地 VoxCPM2

「稿子 ≤12 小时」这条是硬闸，跟豆包那班闸 b 同一条规矩：超龄稿子还合成 = 把上一期重录一遍，
那是文档里记过的事故（套1 失败没覆盖 → 豆包把上一期重录了一遍）。
