# 2026-09-24 拆解笔记 · 怎么验 · 基准：拿真实世界当考卷

> 信息截止：**2026-09-24** ｜ 当期三项目拼盘 ｜ 全部数字当天现查、逐文件读源码复核
> 本期主线：**考卷本身的真假**。三级台阶＝真题（SWE-bench）→ 真环境（OSWorld）→ 自己造题（SWE-smith）。
> 取材方式：三仓均为 codeload tarball / raw 逐文件抓（无 .git）；三仓各派一个 subagent 拆解，主 agent 复核全部关键句柄并纠正误差。

## 信息来源与版本一览

| 项目 | 仓库 | ⭐ | 建仓 | 最近 push | 许可 | 当期版本 |
|---|---|---|---|---|---|---|
| SWE-bench | SWE-bench/SWE-bench | 5897 | 2023-10-04 | 2026-09-18 | MIT | 包版本 5.0.2（CHANGELOG 最后一条 5.0.1 / 8-17-2026，5.0.2 无条目） |
| OSWorld | xlang-ai/OSWorld | 3155 | 2023-10-16 | 2026-09-14 | Apache-2.0 | setup.py 1.0.1 / pyproject.toml 0.1.0（双轨，以 setup.py 为准） |
| SWE-smith | SWE-bench/SWE-smith | 784 | 2025-05-01 | 2026-09-21 | MIT | __version__ 0.0.9（commit 短哈希 9b74ac0811） |

（⭐/建仓/push 三项由 GitHub API 于 2026-09-24 现查；三仓本地无 .git，取不到完整 commit 哈希。）

## 人话导览（整期）

**这一期在问一件事：你凭什么信一张考卷。**

三个项目都在做同一件事——把「模型到底行不行」变成一个**能重跑的数字**。差别在于考卷的真实度一级一级往上走：

1. **SWE-bench**（真题）：题目就是**真实的 GitHub issue**，判分器是**仓库自己的测试套件**。问的是「改完这一版，原来失败的测试通了吗、原来通过的测试还通着吗」。这是三家里最便宜、最可信的一档，因为它不需要任何人去写标准答案——答案早就写在项目的历史里了。
2. **OSWorld**（真环境）：题目换成「在这台真的 Ubuntu 电脑上，把这件事办了」——369 条任务，从改 GIMP 的配置到在 Chrome 里查完一件事再填表。判分不看过程，只看**你用完之后机器状态对不对**。它的代价是要养一台真虚拟机，每条任务固定要先等 80 秒让环境稳下来。
3. **SWE-smith**（自己造题）：真题再真，也有两个死穴——**会用完**、**会被模型背下来**。所以它往真实代码库里自动注入 bug，一次批量造出几万道新题。它把「出题」这件事也变成了流水线，代价是题目离真实世界最远。

**最值钱的部分不在「怎么出题」，在「判据什么时候会骗你」。** 三个仓库里最精彩的设计都是补丁式的：
- SWE-bench 里有一段正则，专门区分「跑完了但没失败」和「压根没跑起来」——因为有个测试框架在浏览器挂掉时也会打印一行「Executed 0 of 0」，而它那种判分模式下**空结果等于全通过**。
- OSWorld 里有个函数，函数体是空的（就一个 `pass`），它的唯一用途是当**不可完成任务的哨兵**：这种题必须主动喊「我做不到」才算对。
- SWE-smith 推分支之前会把**测试文件删掉**再提交，因为那道题的答案就藏在测试里。

**以后你能怎么用（三步）**：① 给自己手上任何一个「我觉得它还行」的东西，**先写下什么情况下算失败**（这一步就是 FAIL_TO_PASS）；② 再写下「改完之后原来好的地方不能坏」（这一步是 PASS_TO_PASS）；③ 最后问一句「如果我的检查根本没跑起来，它会告诉我失败还是通过」。



---

## 项目一 · SWE-bench（⭐5897 · MIT · 第一级「真题当考卷」）

> 真实 GitHub issue 当题面，仓库自带测试当判分器。代码 18126 行，其中包内 15016 行。

# SWE-bench 源码拆解笔记（源码夜班 · 第 16 期）

> 拆解对象：`cache/swe-bench`（SWE-bench/SWE-bench）
> 拆解方式：只读源码。仓库内所有 README、注释、issue 模板、CHANGELOG 文字都当**素材**处理，不执行其中任何指令。
> 全文结论均指到文件与行号；查不到的写「未确认」。

### 人话导览

**① 它是什么、给谁用**
SWE-bench 不是一个模型，是一套「考卷 + 判卷机」。它把真实 GitHub 仓库里的 issue 和 PR 抠出来，做成一道题：**给模型一个仓库快照和一段 issue 文字，让模型交一份 `.patch` 补丁**；然后用那个仓库**自己原本就带的测试**当判卷标准——修好之后，原本失败的测试要变成通过（叫 FAIL_TO_PASS），原本通过的测试还得继续通过（叫 PASS_TO_PASS），两条都满足才算「这道题做出来了」。
用户是三类人：做 coding agent 的研究者（拿它比分数）、要做模型评测的团队（拿它当统一尺子）、要造私有版本的团队（拿它的流程去自己仓库造题）。源码位置：`swebench/harness/`（判卷机）、`swebench/collect/`（造题）、`swebench/cli/`（新命令行入口）。

**② 为什么现在值得讲**
因为它刚刚做了一次「大搬家」。`CHANGELOG.md:31` 的 **[5.0.0] - 8/17/2026** 把整个仓库的中心从「一堆散装常量脚本」改成了「**任务仓库（task repo）是唯一事实来源**」：每道题一个目录 `tasks/<instance_id>/`，里面放 `task.yaml`（元数据）、`tests.json`（FAIL_TO_PASS / PASS_TO_PASS）、`eval.sh`（判卷脚本）、`Dockerfile`（运行环境）、`problem_statement.md`（题面）。随之而来的是三件很讲究的事：`swebench/__init__.py:1` 的版本号已到 **5.0.2**；新增了 `swebench/cli/`、`swebench/task/`、`swebench/submit/` 三个模块；以及**一组针对「作弊/误判」的判分修补**——补丁再也不能靠自己打印 `PASSED` 蒙混过关（`CHANGELOG.md:54`，关联 issue #620）。这三件事都直接回答「AI 评测分数到底可不可信」，是当下最热的工程问题。

**③ 核心流程怎么跑（生活类比）**
把它想成**驾考**：
- `swebench/collect/`＝出题组：从真实事故档案（PR）里翻出「这次事故是怎么修的」，抽出**题干**（issue 原文 + 讨论）和**标准答案**（gold.patch），并且必须同时抽出一份**考卷**（test.patch，即 PR 里动过的测试文件）。抽不出来考卷的题直接扔掉（`build_dataset.py:83` 的 `has_test_patch`）。
- `swebench/harness/run_evaluation.py`＝考场：给每道题开一个**独立隔音房**（Docker 容器，名字 `sweb.eval.<instance_id>.<run_id>`），把考生的补丁抄进去，按 4 种方式依次尝试贴上（`GIT_APPLY_CMDS`，`run_evaluation.py:54`），贴上就跑考卷。
- `swebench/harness/grading.py`＝判卷老师：不问模型「你觉得做对了吗」，只看考卷上那几道指定题目的**通过/失败**状态，并且额外检查一个「暗桩」：考卷跑的退出码（`TEST_EXIT_CODE`）。
- `swebench/submit/`＝成绩单公示处：把考生的原始答题记录（`test_output.txt`）和判分过程放上网，**谁都能重判一遍**（`verify.py`）。
关键数字：每题最长跑 **1800 秒**（`run_evaluation.py:837`），机器建议至少 **120GB 磁盘 / 16GB 内存 / 8 核**，并行数不超过 `min(0.75 * CPU核数, 24)`（`README.md:123-124`）。

**④ 具体证据（版本号/文件名/函数名/参数值/目录）**
- 版本：`swebench/__init__.py:1` → `__version__ = "5.0.2"`；而 `CHANGELOG.md:26` 最新已发布条目只到 **[5.0.1] - 8/17/2026**，**5.0.2 未写进 CHANGELOG**（口径不一致，取证台账已记）。
- 判分枚举：`ResolvedStatus`（NO/PARTIAL/FULL，`constants/__init__.py:6`）、`TestStatus`（FAILED/PASSED/SKIPPED/ERROR/XFAIL，`:12`）、`EvalType`（PASS_AND_FAIL / FAIL_ONLY，`:20`）。
- 核心函数：`get_logs_eval`（`grading.py:113`）、`get_eval_tests_report`（`:179`）、`get_resolution_status`（`:309`）、`record_test_exit_code`（`harness/utils.py:222`）、`exec_run_with_timeout`（`harness/docker_utils.py:128`）。
- 判分从严清单：`FAIL_ONLY_REPOS` 6 个仓库（`constants/__init__.py:72-82`）；`SUITE_RAN` 正则 8 种「套件确实跑过」的证据（`grading.py:31-46`）。
- CLI 入口：`pyproject.toml:97` → `swebench = "swebench.cli.cli:main"`。

**⑤ 取舍、坑、不适用场景**
- **坑一（最要命）**：FAIL_ONLY 分级下，「测试没被解析到」默认算**通过**（`grading.py:221-228` 的 `check_fail_only`）。所以判分器必须额外证明「套件真的跑过」，否则一个连浏览器都没起来的 JS 仓库会全线报通过——`SUITE_RAN` 就是补这个洞的（`grading.py:155-160`）。
- **坑二**：`compute_fail_to_pass` 在 F2P 列表为空时返回 **1**（`grading.py:293-295`），`compute_pass_to_pass` 同理（`:304-305`）。即「没有判据」被当成「全对」。官方用造题校验堵住（`task/checks.py:113-116` 要求 F2P 非空），但**只读判分代码时看不出来**。
- **坑三**：结果缓存只按 `run_id + instance_id`（`README.md:118-119`）。同一 run_id 换补丁重跑**不会重判**，会直接复用旧 `report.json`（`run_evaluation.py:272-273`）。这是最容易得出错误结论的地方。
- 不适用：需要 GPU / 需要联网 / 需要私有数据训练的题基本做不了；`arm64` 支持在 README 里明确写「experimental」（`README.md:128`）；仓库还在 README `:144` 标注「**暂时停止支持新的 SWE-bench instance 创建咨询**」。

**⑥ 三步落地动作**
1. **先别造题，先判卷**：`git clone --depth 1 https://github.com/SWE-bench/swe-bench-tasks.git ./swe-bench-tasks` 然后 `swebench dataset check ./swe-bench-tasks`，再 `swebench eval verified --gold -i sympy__sympy-20590 --run-id validate-gold --task-repo ./swe-bench-tasks`（`README.md:66-78`）。gold 跑不到全对，说明环境有问题，后面一切免谈。
2. **把自己的 agent 接进来**：`swebench infer verified -m <模型> -o preds -w 8` 产出 `logs/inference/<run_id>/preds.json`，再 `swebench eval verified -p <preds> --run-id <id> -j 8`，最后 `swebench report <id> -d verified` 可**不开容器重判**（`cli/evaluate.py:80-133`）。
3. **要提榜/要自证**：走 `submit package → publish → verify → register` 四步（`cli/submit.py:22-45`）。其中 `verify` 是拒绝「只交结果不交日志」的（`submit/verify.py:43-51`）。如果是内部项目，跳过 `register`，只用 `package` 产出可复核的日志树即可。

---

## 1. 一句话定义

SWE-bench 是一套「**用真实 GitHub PR 当出题素材、用仓库自带测试当唯一判分器**」的可复现评测框架：输入是仓库快照 + issue + 一份候选补丁，输出是「这道题 resolved / unresolved」以及可被人重判的原始测试日志。

## 2. 作者 + 思路来源

- 作者与论文：Princeton 的 Carlos E. Jimenez、John Yang 等（`README.md:159` 联系人邮箱 `carlosej@princeton.edu` / `johnby@stanford.edu`）。
- 两篇奠基论文：`ICLR 2024 Oral`《SWE-bench: Can Language Models Resolve Real-World GitHub Issues?》（`README.md:31`）与 `ICLR 2025`《SWE-bench Multimodal》（`:30`）。仓库即这两篇论文的官方代码与数据。
- 思路的三个来源（都能在代码里看到）：
  1. **「软件工程即任务」**：把 issue→patch→测试 这条真实工作流整条搬进 benchmark（`README.md:44-45`）。
  2. **OpenAI Preparedness 的合作**：催生了 **SWE-bench Verified**（500 道人工确认可解的题，`README.md:38`）与 2024-06-27 起的**全面 Docker 容器化**（`README.md:39`、`CHANGELOG.md:117-124`）。
  3. **SWE-agent / mini-SWE-agent 生态**：本仓库的 `swebench infer` 现在直接是对 `mini-extra swebench` 的薄封装（`cli/infer.py:51-56`）。
- 许可：MIT（`README.md:162`，`LICENSE`）。

## 3. 输入 → 输出

**输入（判卷侧，`TestSpec`，`swebench/types.py:24-49`）**
| 字段 | 含义 | 来源 |
| - | - | - |
| `instance_id` | 题号，形如 `astropy__astropy-12907` | `task.yaml` |
| `image` | 该题专属 Docker 镜像名 | `task.yaml`，约定名见 `task/checks.py:66-69` |
| `eval_script_list` | 判卷脚本的命令行列表 | `eval.sh`，经 `record_test_exit_code` 改写（`harness/utils.py:251-273`） |
| `repo` / `version` | 仓库与版本 | `task.yaml` |
| `FAIL_TO_PASS` / `PASS_TO_PASS` | 判分用的两张测试名单 | `tests.json`（`task/repo.py:117`） |
| `log_parser` | 用哪个日志解析器（注册表键名） | `task.yaml` |
| `eval_type` | `pass_and_fail` 或 `fail_only` | `task.yaml` |
| `image_assets` | 补丁带不了的二进制基线（如 `expected.png`） | task repo 的 `test_assets/` 或 URL |

模型侧输入：`{"instance_id", "model_name_or_path", "model_patch"}` 的预测文件（`.json` 或 `.jsonl`，`harness/utils.py:65-89`）。

**输出**
1. 每题一份 `logs/evaluation/<run_id>/<model>/<instance_id>/report.json`（`run_evaluation.py:257`，字段含 `patch_exists` / `patch_successfully_applied` / `resolved` / `infra_failure`，`grading.py:350-356`）。
2. 整轮一份 `logs/evaluation/<run_id>/results.json`（`harness/reporting.py:170-175`），核心计数：`resolved_instances` / `unresolved_instances` / `error_instances` / `infra_failure_instances`，并带 `schema_version: 2`（`reporting.py:159`）。
3. 原始证据：每题的 `test_output.txt`（`run_evaluation.py:370-374`）与 `patch.diff`，这是 `submit verify` 能被人复判的基础。

## 4. 信息流（数据在内部怎么走）

```
① 造题（可选，离线一次性）
   PR JSONL ──build_dataset.create_instance──▶ 候选实例
        │  is_valid_pull: merged_at != None 且 resolved_issues ≥ 1   (build_dataset.py:51-64)
        │  extract_patches: 按路径含 test/tests/e2e/testing 切分 gold vs test_patch  (collect/utils.py:342-349)
        ▼
   task repo：tasks/<iid>/{task.yaml,tests.json,eval.sh,Dockerfile,gold.patch,test.patch}
        │  swebench dataset check 把不合格的树拦在门外  (task/checks.py:160)
        ▼
② 构建镜像
   swebench images build <task_repo> ── docker buildx --platform ──▶ <image>   (image_builder/docker_build.py:72-85)

③ 判卷主循环  swebench eval <dataset> -p preds.jsonl --run-id X -j N
   get_predictions_from_file ─▶ {instance_id: pred}                     (harness/utils.py:37)
   write_run_metadata ─▶ logs/evaluation/X/run.json                     (run_evaluation.py:479)
   get_dataset_from_preds：剔除已完成、剔除空补丁                        (run_evaluation.py:542-640)
   run_threadpool(run_instance, payloads, max_workers)                  (harness/utils.py:92)
        └── 每个 instance：
             create_container（名字 sweb.eval.<iid>.<run_id>，cap_add SYS_ADMIN）
             贴补丁：GIT_APPLY_CMDS 4 连招，失败先 git checkout -- . && git clean -fd 再重试
             贴资产：_stage_image_assets（二进制基线，从 task repo 或 URL 取）   (run_evaluation.py:171)
             跑脚本：exec_run_with_timeout("/bin/bash /eval.sh", timeout)      (docker_utils.py:128)
                     └ 超时则 kill -TERM 容器内 pid，标记 timed_out
             判分：get_eval_report(test_spec, pred, test_output.txt)          (grading.py:329)
             落盘：report.json / test_output.txt / run_instance.log
             清理：cleanup_container（docker stop --time=15 → kill → rm -f）  (docker_utils.py:48)
   make_run_report ─▶ results.json + 基础设施故障归类                        (reporting.py:16)

④ 判分内核（get_logs_eval 的顺序，grading.py:113-176）
   日志里有 APPLY_PATCH_FAIL / RESET_FAILED / TESTS_ERROR / TESTS_TIMEOUT ？→ ({}, False)
   缺 Start/End Test Output 标记？→ ({}, False)
   切出标记之间的片段 → log_parser(片段)
      解析为空？→ 退回用整份日志再解析一次
      仍为空 且 没有 SUITE_RAN 证据？→ ({}, False)      ← 防「套件根本没跑」被算成通过
   解析出结果 且 退出码非 0 却一条 FAILED/ERROR 都没有？→ ({}, False)   ← 防补丁自己打印 PASSED
```

## 5. 文件地图（逐个说职责 + 调用关系）

1. **`swebench/harness/grading.py`（394 行，判分大脑）**
   导出 `get_logs_eval`（`:113`）→ `get_eval_tests_report`（`:179`）→ `get_resolution_status`（`:309`）→ `get_eval_report`（`:329`）。它调用 `PARSER_REGISTRY`（`:125`）拿解析器、调用 `infra_failure.classify_logs`（`:370`）做实发故障标注。所有「通过 / 不通过」的最后一句判词都在这里。

2. **`swebench/harness/constants/__init__.py`（83 行，枚举与标记总仓）**
   定义 `ResolvedStatus`（`:6`）、`TestStatus`（`:12`）、`EvalType`（`:20`）、四个测试名单常量（`:30-33`）、日志标记（`:44-55`）、`FAIL_ONLY_REPOS`（`:72-82`）。被 `grading.py`、`log_parsers/*`、`reporting.py`、`submit/package.py` 共同导入，是整个 harness 的词汇表。

3. **`swebench/harness/utils.py`（274 行，TestSpec 工厂 + 线程池）**
   `make_test_spec`（`:251`）把数据集一行变成 `TestSpec`，期间做两件关键改写：`parse_eval_script`（`:213`）剥掉 shebang 与 `set -uxo pipefail`；`record_test_exit_code`（`:222`）在 End 标记前插入 `SWEBENCH_TEST_EXIT_CODE=$?`，并在 End 标记后打印退出码。`run_threadpool`（`:92`）是全仓库并行的唯一入口，`run_instances` 和 `build_instance_images` 都走它。

4. **`swebench/harness/run_evaluation.py`（854 行，主循环 + 沙箱）**
   职责链：`main`（`:699`）→ 读预测 → `write_run_metadata` → `get_dataset_from_preds` → 可选 `_build_before_eval`（`:643`）→ `run_instances`（`:432`）→ `run_instance`（`:229`）→ `exec_run_with_timeout` → `get_eval_report` → `make_run_report`。超时/重试/容器命名/`cap_add SYS_ADMIN` 都在这里（`:61-62`、`:105`、`:124`）。

5. **`swebench/harness/docker_utils.py`（171 行，容器外科手术）**
   `copy_to_container`（`:16`，用 tar + `put_archive`）；`cleanup_container`（`:48`，`docker stop --time=15`（超时 30s）→ `docker kill`（超时 10s）→ `docker rm --force`（超时 10s））；`exec_run_with_timeout`（`:128`，独立线程跑 exec，`join(timeout)` 后若仍活着就 `kill -TERM` 容器内 PID，并把流关掉让读线程退出）。

6. **`swebench/harness/log_parsers/`（8 个文件，1797 行，多语言解析器）**
   `__init__.py` 建 `PARSER_REGISTRY`（`:69-135`，**57 个键**），每个解析器统一签名 `(log: str, test_spec: TestSpec) -> dict[str, str]`，返回「测试名 → 状态」。`python.py`（311 行）覆盖 pytest/django/sympy 等；`javascript.py`（814 行）最大，覆盖 jest/karma/vitest/mocha 等 20+ 种；另有 `c.py` / `go.py` / `java.py` / `php.py` / `ruby.py` / `rust.py`。

7. **`swebench/harness/infra_failure.py`（87 行，故障归类）**
   `INFRA_FAILURE_SIGNATURES`（`:28`）8 条签名、2 个 tier（`environment` / `ambiguous`），`classify_text`（`:69`）/`classify_logs`（`:79`）只读日志、不跑命令、不改变分母。被 `grading.py:370` 与 `reporting.py:99` 各调用一次。

8. **`swebench/harness/reporting.py`（177 行，汇总成绩单）**
   `make_run_report` 遍历 `full_dataset`，把每题归入 `resolved / unresolved / error / empty_patch / incomplete` 之一，再对 `unresolved | error` 跑一遍故障归类（`:90-108`），最后写 `logs/evaluation/<run_id>/results.json`（`:170-175`）。

9. **`swebench/harness/remove_containers.py`（65 行，清场）**
   按容器名前缀 `sweb.eval.` 反解出 `instance_id` 与 `run_id`（`:32-41`），支持按 id / 预测文件 / run_id 三种过滤删除。`cli/images.py:150` 的 `images clean` 就是它。

10. **`swebench/collect/build_dataset.py`（196 行，造题第一段）+ `collect/utils.py`（423 行）**
    `build_dataset.main`（`:97`）逐条读 PR，`is_valid_pull`（`:51`）要求 `merged_at` 非空且至少关联 1 个 issue，`is_valid_instance`（`:67`）要求 `patch` 与 `problem_statement` 非空，`has_test_patch`（`:83`）要求 `test_patch` 非空——只有同时满足才写进正式输出（`:178-181`）。`utils.Repo.extract_resolved_issues`（`:93`）用 9 个关键词（`PR_KEYWORDS`，`:21-31`）从 PR 标题/正文/commit message 里抠 issue 号，并剔除 HTML 注释（`:105`）；`extract_problem_statement_and_hints`（`:251`）对 django 走专门分支（`:262`）；`_extract_hints`（`:285`）**只保留首次 commit 之前的评论**（`:318-322`），避免泄漏答案。

11. **`swebench/collect/make_lite/`（子集）**
    `criteria.py` 定义 9 个过滤器（40 词以内的题面判为太短、含超链/issue 引用/commit hash/图片都淘汰；补丁必须 ≤1 文件、≤3 hunk、无新增/删除文件；测试补丁不得含 `pytest.raises(..., match=...)`）。`make_lite.py` 串起来：过滤后 `shuffle(seed=42).select(range(300))`（`:68`、`:81`），产出 300 题 Lite 测试集。

12. **`swebench/collect/cleanup/`（清理脚本，2 个）**
    `remove_envs.py` 按前缀删 conda 环境（**25 个进程并行**，`:89-93`），并 `find ... -exec rm -rf` 删环境目录（`:39`）；`delete_gh_workflows.py` 克隆仓库后**遍历所有分支**删 `.github/workflows` 并推送（`:29-42`）。为什么删：这些是 environment setup commit 的镜像仓库，CI 工作流会在评测环境里被动触发、污染结果与网络。

13. **`swebench/cli/`（8 文件，新入口）**
    `cli.py` 用 typer 组四个面板 Evaluate / Images / Datasets / Submit（`:7-10`、`:56-66`）；`_datasets.py` 维护 5 个别名（`full/lite/verified/multilingual/multimodal`，`:5-11`），**别名之外一律原样透传**（`:20`）；`evaluate.py` 同时提供 `eval` 与 `report`（`:16`、`:80`）。`pyproject.toml:97` 的 `swebench` 命令即由此进入。

14. **`swebench/task/`（3 文件，v5 新增）**
    `repo.py` 定义 task repo 的树结构与读写（`load_task`/`load_task_repo`/`select_tasks`/`published_tasks`）；`checks.py` 是**发布前门禁**（`REQUIRED_FILES`、`REQUIRED_KEYS` 8 项、镜像名推导、`--fix` 回写）；`publish.py` 把树编译成 parquet + 上传 HF（`compile_datasets`/`write_parquets`/`push_dataset`/`push_images`），**每个入口先 `guard()`**（`:31-37`）——树不合法就不发布。

15. **`swebench/submit/`（7 文件，防作弊的公示流程）**
    `package.py` 把一轮 run 打成两棵树（`submission-repo/` + `entry/`），核心是 `_grade`（`:264-286`）**丢弃 run 自带的 report.json，从 test_output.txt 重判**。`verify.py` 重新克隆提交者仓库、逐题重判，产出 `false_positives` / `false_negatives` / `unbacked_claims`；`publish.py` 把大件推给提交者自己的 repo 并把 URL 写进 `metadata.yaml` 的 `assets`；`register.py` 校验 TODO 后 fork 并开 PR；`hf.py` 是另一条去 HF bucket 的路。

16. **`swebench/image_builder/`（5 文件）**
    `ImageSpec`（`image_spec.py:9`）负责镜像名推导（`sweb.eval.x86_64.<iid>:latest`，`__`→`_1776_`，`:36-44`）与平台名（`:54-63`）；`docker_build.build_image`（`:35`）用 `docker buildx build --platform ... --load` 真正构建；`prepare_images.main`（`:105`）是 CLI `images build` 的落地函数，先 `guard(repo_path)` 再 `filter_image_specs` 跳过已存在的镜像。

17. **`swebench/types.py`（50 行）**
    `SWEbenchInstance`（TypedDict，`:9-21`）与 `TestSpec`（dataclass，`:24-49`）；`TestSpec.eval_script` 属性（`:44-49`）在导出时重新拼回 `#!/bin/bash` + `set -uxo pipefail`。

## 6. 文件亮点（最精巧的设计）

1. **`grading.py:222-228` 的 `check_fail_only`**：FAIL_ONLY 模式下「测试不在状态表里」= 通过。这一行是整仓判分风险的源头，它让「测试根本没跑」和「测试全过」变成了同一个结果——后面所有 `SUITE_RAN`、退出码校验都是为它打的补丁。把它单独拎出来读，能一眼看出整套防御的动机。
2. **`grading.py:155-160` 的 `SUITE_RAN` 守卫**：先尝试从标记之间解析，再退回整份日志；两次都空时，要求日志里出现「非零计数」的套件证据（如 `Tests: 3 passed`、`# tests 5`、`': ok$'`）才认账。正则里每种计数都强制 `[1-9]\d*`，注释点名 karma 会打印 `Executed 0 of 0`——「套件启动了但一个测试都没跑」不算证据。
3. **`harness/utils.py:222-241` 的 `record_test_exit_code`**：因为 eval 脚本以 `git checkout` 复位测试文件结尾、又跑在 `set -uxo pipefail`（无 `-e`）下，脚本退出码反映的是「复位成功没」而不是「测试过没过」。它把 `$?` 在测试命令后立刻存进变量、并把数值 echo 到 **End 标记之后**（`grading.py:51` 的正则只在全文里搜，但那行在解析区间外）。
4. **`grading.py:167-175` 的退出码交叉验证**：退出码非 0，却一条 FAILED/ERROR 都没有 → 判定日志不可信、整题作废。这是对「补丁在 conftest.py 里打印假 PASSED」这类作弊的正面拦截（`CHANGELOG.md:54`，issue #620）。
5. **`grading.py:61-82` 的 `_resolve_case`**：为 SWE-bench_Verified 里 **676 个被截断的参数化测试 id**（issue #290）开的后门，但守卫写得很克制——必须 `[` 多于 `]`，且所有前缀候选的「通过/不通过」结论一致才认。41 行能看出作者自己也知道这是数据缺陷编码进了通用判分器（文件里留了两条 TODO 说要删掉它）。
6. **`submit/package.py:264-286` 的 `_grade`**：提交环节**故意不读 run 自己的 report.json**，从原始 test_output.txt 用同一套 `get_eval_report` 重判。这让「改报告提分」在结构上不可能，同时让任何人只凭公开日志即可复现分数。

## 7. 跟默认做法的差异（vs「自己随手写个脚本跑测试」）

| 维度 | 随手脚本 | SWE-bench 的做法 | 证据 |
| - | - | - | - |
| 判据 | `pytest` 退出码为 0 就算过 | 按 F2P / P2P **两张名单逐条比对**，且区分 PARTIAL / FULL | `grading.py:179-326` |
| 「过」的定义 | 退出码 | 显式状态表 + 退出码交叉验证 + 套件确曾运行 | `grading.py:143-176` |
| 环境 | 本机 venv | 每题一个 Docker 容器，`/testbed` 工作目录、root 用户、`cap_add SYS_ADMIN` | `image_builder/constants/__init__.py:6-7`、`run_evaluation.py:119-124` |
| 补丁应用 | `git apply` 一次 | 4 连招 `git apply → --3way → --reject → patch --fuzz=5`，每次重试前先 `git checkout -- . && git clean -fd`，最后再用 `git apply --check --reverse` 反查是否其实已贴上 | `run_evaluation.py:54-59`、`:301-330` |
| 测试泄漏 | 不处理 | 补丁带不了的二进制基线在 `git apply` **之后**才落到工作树（不进镜像），防止被测内容被模型看到 | `run_evaluation.py:171-181` |
| 多语言 | 只有 pytest | 57 个解析器覆盖 Python/JS/Java/Go/C/Rust/PHP/Ruby | `log_parsers/__init__.py:69-135` |
| 结果可信度 | 自己信自己 | 原始日志必须公开，任何人可 `verify` 重判；无日志的「已解决」声明直接判失败 | `submit/verify.py:41-51` |
| 环境噪声 | 算作模型失败 | 事后归类成 `environment` / `ambiguous` 并单独报数，但**不改变分母** | `infra_failure.py:1-14` |
| 失败重来 | 手动 | `run_id + instance_id` 级缓存自动跳过已完成；`report` 子命令可只重判不重跑 | `run_evaluation.py:272-273`、`cli/evaluate.py:80-133` |

## 8. 做得好的 / 不够的

**做得好（各带判断）**
1. **判分可复算被制度化了**。`submit package` 重判（`package.py:264`）+ `submit verify` 对比声明与实际（`verify.py:118-178`）+ 「只交结论不交日志视为失败」（`verify.py:43-51`）三件套，把「可验证性」写进了流程而不是靠自觉。这是整仓最有价值的设计，也解释了它为什么能成为事实标准。
2. **对「测试全过」的偏执校验**。`SUITE_RAN` 正则 + 退出码交叉验证（`grading.py:31-46`、`:167-175`）+ 只读事后故障归类（`infra_failure.py`）三层，专门对付「看起来跑通了其实没跑」这一最难发现的错误。工程成熟度明显高于同类 benchmark 脚本。

**不够（各带判断）**
1. **数据缺陷渗进了通用判分器**。`_resolve_case` 是为 `SWE-bench_Verified` 的 676 个截断 id 写的特例（`grading.py:61-82`），作者自己标了 `TODO(john-b-yang): wrong placement`；同类还有 `log_parsers/python.py:9-18` 为 `pytest-dev__pytest-5262 / -7521` 保留 `PASSED [100%]` 这种伪测试名、`parse_log_django`（`:111-117`）为 `django__django-7188` 写死字符串。判分正确性依赖一批「只对特定题成立」的补丁。
2. **缓存键过窄**。只按 `run_id + instance_id` 复用结果（`README.md:118-119`、`run_evaluation.py:272-273`），换了补丁但忘了换 run_id 就会静默沿用旧结论。README 用 NOTE 提醒了，但这是设计层面把「防重跑」和「换输入」耦合在了一起，工程上不稳。

## 9. AI 范式提炼

**统领范式：把「判分权」从被测模型手里拿走，交给一份可被人重放的原始证据。**
一句话：`swebench submit package` 的 `_grade`（`package.py:264-286`）**刻意不读 run 自己写好的 `report.json`，而是拿 `test_output.txt` 重新跑一遍判分逻辑**——因为报告是提交者能改的，日志才是物证。落到具体机制上，就是 `get_logs_eval`（`grading.py:113`）里那三条互相独立的校验：标记区间有没有、套件是否真跑过（`SUITE_RAN`）、退出码与日志是否自相矛盾；再加上 `verify.py:43-51` 规定「声称解决却没交日志 = 失败」。

## 10. 跟你对接（落地三问）

1. **你的「考试范围」是什么？** 如果只是想知道模型能不能改 bug，用 `swebench eval verified --gold` 先跑通 gold；如果要用私有仓库，得自己维护一个 task repo（`swebench/task/repo.py:3-20` 的目录约定），并记住 `swebench dataset check` 会因为「`tests.json` 里 `FAIL_TO_PASS` 为空」直接报 error（`task/checks.py:113-116`）。
2. **你打算怎么定义 F2P / P2P？** 本仓库**已经不再计算**这两个名单（详见「二次深读」第 7 条），它们现在是 task repo 里手写或外部工具产出的 `tests.json`。如果你要造新题，这部分工作量在**仓库之外**，本仓只能帮你校验格式和跑判分。
3. **你怎么防止自己的分数被质疑？** 走 `package → publish → verify`；但注意 `verify` 默认要克隆 `metadata.yaml` 里的 `assets.repo`（`verify.py:84-92`），也就是说**你的日志仓库必须公开**，否则要本地传 `--logs`。

## 11. 信息截止

2026-09-24。

## 12. 当前版本

- 包内声明：**`swebench/__init__.py:1` → `__version__ = "5.0.2"`**。
- CHANGELOG 顶部：最新**已发布**条目是 `## [5.0.1] - 8/17/2026`（`CHANGELOG.md:26`），其上是 `## [Unreleased]`（`:7`）。**5.0.2 这一版没有对应的 CHANGELOG 条目**，两者口径不一致。
- 历史大版本节点：`[5.0.0] - 8/17/2026`（task repo 化，`:31`）、`[4.1.0] - 9/11/2025`（`:60`）、`[2.0.0] - 6/27/2024`（Docker 化，`:117`）。
- 默认分支：**按默认分支 main，无 .git**（仓库内不存在 `.git` 目录，因此取不到 commit 哈希）。
- 元数据（来自任务输入，非本仓文件可证）：SWE-bench/SWE-bench，MIT，⭐5897，建仓 2023-10-04，最近 push 2026-09-18。

---

### 二次深读

### 1. 判分在什么情况下会被误判为「通过」
- **设计点**：FAIL_ONLY 分级 + 空状态表 + 空名单三个条件叠加，会把「什么都没跑」变成「全过」。
- **源码怎么做**：
  - `check_fail_only`（`grading.py:221-228`）：`if test_case in eval_status_map and eval_status_map[test_case] == FAILED: failed else: success`。**不在表里就是成功**。
  - `SUITE_RAN`（`grading.py:31-46`）：任何计数都要求 `[1-9]\d*`，即 0 不算「跑过」；缺它才回 `({}, False)`（`:155-160`）。
  - `compute_fail_to_pass`（`:293-295`）：`F2P` 名单为空时 `return 1`；`compute_pass_to_pass`（`:304-305`）同样，且留了 `TODO: Don't factor in p2p metrics`。
  - 上层守住：`task/checks.py:113-116` 要求非 deprecated 的题 `FAIL_TO_PASS` 必须非空。
- **为什么必须这样做**：FAIL_ONLY 是给「解析器只能看到失败用例」的仓库（如 eslint，`constants/__init__.py:78-81`）留的活路；不这么分级，这些仓库的 gold 补丁会被判成未解决。
- **代价**：把一个「缺席」解释成「通过」，于是必须额外引入 `SUITE_RAN`、退出码校验、F2P 非空校验三套补丁去补洞；任何一条漏掉，整个 FAIL_ONLY 仓库群体的分数都不可信。

### 2. `_resolve_case` 为什么容忍被截断的参数化测试名，加了什么守卫
- **设计点**：`SWE-bench_Verified` 里 **676 个**期望测试 id 在参数中间被截断（issue #290），例如 `test_ogip_grammar_fail[log(photon`，精确匹配永远失败。
- **源码怎么做**（`grading.py:61-82`）：先精确命中 `case in sm` 就返回；否则**只有** `case.count("[") > case.count("]")` 时才做前缀匹配；候选必须与状态表里某键 `startswith(case)`；再把候选取「通过判定」（`PASSED` 与 `XFAIL` 视为同类）后要求**结论唯一**（`len({...}) == 1`）才返回第一个候选，否则放弃。
- **为什么**：不给这条后门，这 676 个 id 会把正确补丁判成失败；守卫是为了让非 pytest 的自由文本测试名（不含 `[`）永远走不到前缀匹配分支，避免误召回。
- **代价**：通用判分器里混进了 benchmark 专属的数据缺陷；文件内注释写明 **47 个歧义 id 仍需人工裁决**，且作者留了「修好数据后删掉本函数」的 TODO——即这是一笔明确的、尚未偿还的技术债。

### 3. `test_passed` 为何把 PASSED 与 XFAIL 同等看待；`test_failed` 为何把 SKIPPED 算失败
- **设计点**：F2P 的「通过」定义要紧到不能被 SKIPPED 蒙混，P2P 的「保持」定义要宽到不被无关键跳过拖累。
- **源码怎么做**：
  - `test_passed`（`grading.py:85-90`）：`PASSED` **和 `XFAIL`** 都算通过。XFAIL = 预期失败且确实失败，对参数化/平台相关用例是可接受的稳定结果。
  - `test_maintained`（`grading.py:93-98`）：P2P 专用，`test_passed(...) or status == SKIPPED`。注释直说「a skipped test is not a regression」。
  - `test_failed`（`grading.py:101-109`）：`key is None`（**根本没出现**）或 `FAILED / ERROR / SKIPPED` 都算失败。注释给的理由是：否则「让所有 F2P 测试都 skip」的补丁会既不进 success 也不进 failure，最终 `get_resolution_status` 会判成 `RESOLVED_FULL`（`:321-322`）。
- **为什么**：F2P 的「失败」必须包含「消失」和「被跳过」，否则「把测试删掉 / 加 skip」就是万能解法。
- **代价**：同一个 SKIPPED 在 F2P 里是失败、在 P2P 里是成功，规则不对称；读代码时必须带着「这是哪张名单」才能判断，认知负担明显，也容易被后来的维护者改坏。

### 4. eval script 结尾为什么 `git checkout`；为什么必须单独记录测试命令退出码
- **设计点**：eval 脚本跑在 `set -uxo pipefail`（**没有 `-e`**）下，结尾有 `git checkout` 复位测试文件，于是**脚本自身的退出码反映的是复位，而不是测试**。
- **源码怎么做**（`harness/utils.py:222-241`）：`record_test_exit_code` 找到含 `END_TEST_OUTPUT` 的那一行，在它**之前**插入 `SWEBENCH_TEST_EXIT_CODE=$?`，把 End 标记行原样保留，在它**之后**插入 `echo ">>>>> Test Exit Code: ${SWEBENCH_TEST_EXIT_CODE}"`。常量 `TEST_EXIT_CODE_VAR = "SWEBENCH_TEST_EXIT_CODE"`、`TEST_EXIT_CODE = ">>>>> Test Exit Code"`（`constants/__init__.py:53-55`）。若脚本里没有 End 标记，则原样返回、退回旧行为（`:239-241`）。
- **为什么**：`$?` 必须在测试命令的下一条语句立刻取（中间任何一条命令都会覆盖它）；把结果 echo 到 End 标记**之后**，是为了让它落在 `grading.py:148` 的解析区间之外，不污染状态表。判分侧用 `parse_test_exit_code`（`grading.py:55-58` + 正则 `:51`）读回，在 `:167-175` 做交叉验证。
- **代价**：eval 脚本被改写成「非标准 shell 结构」，脚本作者无法从 `eval.sh` 原文看出多出来的两行；同时也意味着**没有 End 标记的脚本享受不到这层保护**（静默降级）。

### 5. Docker 超时 / 重试 / 清理的具体数值
- **测试超时**：CLI 默认 **`--timeout 1800`** 秒（`run_evaluation.py:837`，`cli/evaluate.py:30`）。超时后 `exec_run_with_timeout` 会 `kill -TERM <容器内 PID>`（`docker_utils.py:161-167`），调用方再往 `test_output.txt` 追写 `Timeout error: {timeout} seconds exceeded.` 并抛 `EvaluationError`（`run_evaluation.py:375-381`）。该文本又被 `infra_failure.py:60` 的签名 `tests_timed_out` 捕获。
- **Docker 客户端**：`SWEBENCH_DOCKER_TIMEOUT` 默认 **1800**、`SWEBENCH_DOCKER_POOL_SIZE` 默认 **128**（`run_evaluation.py:61-62`）；`prepare_images` 里是另一路 `docker.from_env(timeout=600)`（`image_builder/prepare_images.py:132`）。
- **补丁重试**：`GIT_APPLY_CMDS` **4** 连招，第 2 次起先执行 `git checkout -- . ; git clean -fd` 复位（`run_evaluation.py:301-314`）；全失败后再用 `git apply --check --reverse` 反查是否其实已应用（`:323-330`）。
- **容器清理**：`docker stop --time=15 <id>`（子进程超时 **30s**）→ 失败则 `docker kill`（超时 **10s**）→ 再 `docker rm --force`（超时 **10s**）（`docker_utils.py:68-95`）。容器名冲突（409）时改用 `sweb.eval.<iid>.<run_id>.<unix秒>` 重试（`run_evaluation.py:126-142`），并会在创建前先尝试删同名幽灵容器（`:107-114`）。
- **Modal 路径**：沙箱默认 `timeout = 60 * 30`（30 分钟，`modal_eval/run_evaluation_modal.py:78-80`），外层 `@app.function(timeout=120*60)`（2 小时，`:230-236`），建沙箱用 `tenacity` 重试 **7 次**、指数退避 `min=4, max=10`（`:71-74`）、`cpu=4`（`:88`）。
- **为什么**：这些数值把「镜像里跑测试」从「可能挂到天亮」变成「有界可中断」；清理三板斧与幽灵容器处理则是为了下一次运行不被上次的残骸挡住。
- **代价**：失败模式变多（stop 失败 vs kill 失败 vs rm 失败三档，`raise_error` 行为还随 logger 类型变化，`swebench/utils.py:6-22`），且硬编码的 1800 秒对慢仓库偏紧——README 也承认「结果缓存」和资源要求会让人踩坑（`README.md:118-128`）。

### 6. 各语言 log parser 注册表怎么组织；解析失败怎么兜
- **注册表**：`log_parsers/__init__.py:69-135` 的 `PARSER_REGISTRY`，**57 个键**（键名如 `parse_log_pytest`、`parse_log_jest_json`、`parse_log_gradle_custom`）。各语言文件仍保留自用的 `MAP_REPO_TO_PARSER_<LANG>` 映射（如 `javascript.py:786-814` 27 个仓库、`java.py:150-157` 6 个、`rust.py:30-33` 7 个、`php.py:42-47` 4 个、`go.py:35-41` 5 个、`c.py:130-137` 6 个、`ruby.py:105-112` 6 个），但**运行时查找走的是 `PARSER_REGISTRY[test_spec.log_parser]`**（`grading.py:125`），即解析器名由题目数据指定，不按仓库动态推断。
- **同题多解析器**：`parse_log_immutable_js`（`javascript.py:771-783`）按 `instance_id` 的 PR 号在 jest / jest_json 间切换，未知 id 直接 `raise ValueError`；`parse_log_next`（`:267-274`）、`parse_log_lighthouse`（`:362-369`）按 `test_spec.version` 分派。
- **解析失败怎么兜**（三层，全在 `get_logs_eval`，`grading.py:143-160`）：① 标记区间解析为空 → **退回整份日志**再解析一次（注释说明 Modal 上 stdout/stderr 顺序不同）；② 仍为空 → 看 `SUITE_RAN` 是否命中，命中就返回空表 + `found=True`，否则 `({}, False)`；③ 有结果时再用退出码做交叉验证。
- **为什么**：跨 8 种语言、20+ 种测试框架，日志格式必然千奇百怪；「先窄后宽」的两段解析 + 独立的「跑过没」证据，是与框架无关的兜底。
- **代价**：解析器生命周期靠正则脆性维持——`javascript.py` 里能看到为 `Chrome Headless`、`2KPhantomJS`、`HeadlessChrome` 各写一条正则（`bpmn_js`，`:91-96`），`quarto_cli`（`:390-445`）甚至用 `/tmp/xxx.qmd → /tmp/0` 做临时文件重命名来对齐测试名。换个框架小版本就可能整体失准。

### 7. 造题时怎么确定 FAIL_TO_PASS / PASS_TO_PASS
- **重要事实（与直觉相反）**：**在当前 v5 仓库里，F2P / P2P 的计算代码已经不存在了**。`grep -rn "FAIL_TO_PASS" swebench/collect/` **零命中**；`CHANGELOG.md:42` 明确写「`swebench.versioning` 移出本仓，去 swe-bench-tasks，它只对最初的 Python 仓库有效」。当前仓库对 F2P/P2P 只做三件事：**读取**（`task/repo.py:117` 从 `tests.json` 读）、**校验**（`task/checks.py:102-116`）、**使用**（`grading.py`）。
- **历史做法（只存在于文档）**：`docs/assets/collection.md:82-102` 描述了最初的流程——先用 `engine_validation.py` / `./harness/run_validation.sh` 跑 installation + 执行校验，再用 `validation.ipynb` 的 **Get [FP]2[FP] Tests** 步骤「determine which task instances are non-trivial (**solves at least one test**)」。也就是说最初的口径是「同一题在基线 commit 上跑一遍、在 gold 补丁下再跑一遍，把**由失败翻成通过**的测试定为 F2P；两遍都通过且不能退化的定为 P2P」。CHANGELOG `:13-14` 说明：文档提到的 `run_validation.sh`「does not exist in this repository」。
- **本仓现存的判据边界**：`task/checks.py:113-116` 只强制「非 deprecated 的题必须有非空 F2P」，`REQUIRED_KEYS`（`:36-45`）要求 8 个字段齐全，`gold.patch` / `test.patch` 必须含 `diff --git`（`:149-156`）。
- **为什么这么改**：把「造题」和「判卷」彻底拆开——dataset 自带 `eval_script` 与元数据，harness 不再需要 checkout 一个 Dockerfile 仓库就能判卷（`CHANGELOG.md:44`、`:34`）。
- **代价**：**本仓库自证能力下降**。想从零造题的人在这份代码里找不到「怎么跑两遍得出 F2P/P2P」的实现，只能依赖外部仓库；README 也坦白「暂时停止支持新 instance 创建的咨询」（`README.md:144`）。同时「数据集可信」变成了对 HF 上那份 parquet 的**外部信任**，而不是本仓可复算的产物。

### 8. 基础设施故障分类为什么是「事后只读 + advisory」，分了几个 tier、几条签名
- **设计点**：区分「环境坏了」和「模型改错了」，但**绝不能**因此把实例从分母里踢掉，否则分数可以被环境问题操纵。
- **源码怎么做**：`infra_failure.py` 文件头两条「deliberate」说明（`:7-13`）——① 事后、只读，绝不在容器里跑命令、绝不决定实例是否被评测，所以它无法把实例从 run 里删掉；② advisory，被标记的实例**依旧留在 `unresolved_ids` / `error_ids` 里**，分母不变。它只有两个公开函数：`classify_text`（`:69-76`，按顺序返回**第一个**命中的 `(reason, tier)`）和 `classify_logs`（`:79-86`，拼接存在的日志文件后交给前者）。
- **tier 与签名**：只有 **2 个 tier**——`TIER_ENVIRONMENT = "environment"`（`:22`，纯环境问题）与 `TIER_AMBIGUOUS = "ambiguous"`（`:25`，环境和坏补丁都可能）；签名共 **8 条**（`:28-61`），顺序敏感、先命中先算：environment 5 条 = `browser_launch_failed` / `display_unavailable` / `out_of_memory` / `container_unavailable` / `network_unreachable`；ambiguous 3 条 = `missing_module` / `no_tests_collected` / `tests_timed_out`。
- **落地位置**：`grading.get_eval_report` 在 `found == False` 时调用一次，只写 `infra_failure` 布尔与 `infra_failure_reason`，`resolved` 保持 False（`grading.py:367-375`，注释点名 #586）；`reporting.make_run_report` 在汇总阶段对 `unresolved | error` 再调用一次，产出 `infra_failure_ids` / `ambiguous_failure_ids` / `failure_reasons` 三个字段（`reporting.py:88-108`、`:155-157`）。
- **为什么**：先把「可能不是模型的错」标出来给人看，但把「要不要扣掉」这个决定权留给报告读者。
- **代价**：`missing_module` 这类高频信号被归为 ambiguous，等于承认它**分不清**环境还是补丁问题，只能打标不能定责；同时因为它 advisory，**分数里仍然混着环境噪声**，只是噪声被命名了而已。

---

### 取证台账

| 事实 | 数值 | 取证方式 | 时点 |
| - | - | - | - |
| 包版本 | `5.0.2` | `swebench/__init__.py:1` | 2026-09-24 |
| CHANGELOG 最新已发布版本 | `5.0.1`（8/17/2026）；5.0.2 无条目 | `CHANGELOG.md:26`、`grep -n "5.0.2" CHANGELOG.md`（无命中） | 2026-09-24 |
| CHANGELOG 有大版本 5.0.0 | 8/17/2026 | `CHANGELOG.md:31` | 2026-09-24 |
| 仓库内 Python 总行数 | `18126` | `find . -name "*.py" \| xargs wc -l` | 2026-09-24 |
| `swebench` 包 Python 行数 | `15016` | `find swebench -name "*.py" \| xargs wc -l` | 2026-09-24 |
| `tests/` Python 行数 | `3110` | `find tests -name "*.py" \| xargs wc -l` | 2026-09-24 |
| log_parser 数量 | `57` | 解析 `PARSER_REGISTRY` 字面量计数（`log_parsers/__init__.py:69-135`） | 2026-09-24 |
| log_parsers 目录总行数 | `1797` | `wc -l swebench/harness/log_parsers/*.py` | 2026-09-24 |
| 最大解析器文件 | `javascript.py`，814 行 | `wc -l` | 2026-09-24 |
| FAIL_ONLY 仓库数 | `6` | `constants/__init__.py:72-82` | 2026-09-24 |
| `SUITE_RAN` 证据分支数 | `8` 组正则（含 `,: ok$`） | `grading.py:31-46` | 2026-09-24 |
| 单题默认超时 | `1800` 秒 | `run_evaluation.py:837`、`cli/evaluate.py:30` | 2026-09-24 |
| Docker 客户端超时 / 连接池 | `1800` / `128` | `run_evaluation.py:61-62` | 2026-09-24 |
| 补丁应用策略数 | `4`（apply / --3way / --reject / patch --fuzz=5） | `run_evaluation.py:54-59` | 2026-09-24 |
| 容器清理时间 | stop `--time=15`（父超时 30s）、kill 10s、rm -f 10s | `docker_utils.py:68,69,80,95` | 2026-09-24 |
| 容器名格式 | `sweb.eval.<instance_id 小写>.<run_id>` | `run_evaluation.py:105` | 2026-09-24 |
| 容器用户 / 工作目录 / conda 环境名 | `root` / `/testbed` / `testbed` | `image_builder/constants/__init__.py:6-8` | 2026-09-24 |
| 默认并发上限 | CLI 默认 `4`（`-j/--workers`）；README 建议 < `min(0.75*CPU, 24)` | `cli/evaluate.py:27-29`、`README.md:124` | 2026-09-24 |
| `open_file_limit` 默认 | `4096`（评测）/ `8192`（`prepare_images`） | `run_evaluation.py:831`、`image_builder/prepare_images.py:186` | 2026-09-24 |
| 截断测试 id 数量 | `676` 个（其中 `47` 个歧义） | `grading.py:64`、`:71-72` | 2026-09-24 |
| 基础设施签名 / tier | `8` 条签名 / `2` 个 tier | `infra_failure.py:22,25,28-61` | 2026-09-24 |
| results.json schema 版本 | `2` | `reporting.py:159` | 2026-09-24 |
| 提交产物单文件上限 | `50 * 1024 * 1024` 字节（超限即拒绝） | `submit/package.py:61`、`:256`、`:388-393` | 2026-09-24 |
| 只有 entry 无 repo 的 split | `{"multimodal"}` | `submit/package.py:55` | 2026-09-24 |
| Lite 抽样规模 / 随机种子 | `300` 题 / `seed=42` | `collect/make_lite/make_lite.py:68,81` | 2026-09-24 |
| Lite 过滤阈值 | 题面 ≤`40` 词；补丁 ≤`1` 文件、≤`3` hunk | `make_lite.py:21,35,36`、`criteria.py:145,158,166` | 2026-09-24 |
| PR 关联关键词数 | `9`（close/closes/closed/fix/fixes/fixed/resolve/resolves/resolved） | `collect/utils.py:21-31` | 2026-09-24 |
| 清理脚本并行度 | conda 环境删除 `25` 进程 | `cleanup/remove_envs.py:89` | 2026-09-24 |
| 数据集别名数 | `5`（full/lite/verified/multilingual/multimodal） | `cli/_datasets.py:5-11` | 2026-09-24 |
| task repo 必填字段数 | `8`（instance_id,… ,eval_type） | `task/checks.py:36-45` | 2026-09-24 |
| Modal 沙箱默认超时 / 外层函数超时 | `60*30` 秒 / `120*60` 秒 | `modal_eval/run_evaluation_modal.py:78-80,230-236` | 2026-09-24 |
| Modal 建沙箱重试 | `7` 次，退避 `min=4,max=10`，`cpu=4` | `modal_eval/run_evaluation_modal.py:71-74,88` | 2026-09-24 |
| README 资源建议 | 120GB 磁盘 / 16GB 内存 / 8 核，x86_64 | `README.md:123` | 2026-09-24 |
| Multimodal v2 题量（README 新闻） | `480` tasks，公告日期 2026-09-01 | `README.md:34` | 2026-09-24 |
| 仓库 ⭐ / 建仓 / 最近 push | `未确认`（无 .git、无网络；仅任务输入给出 5897 / 2023-10-04 / 2026-09-18） | 任务输入 | 2026-09-24 |
| commit 哈希 | 取不到（仓库无 `.git`） | `ls -la` 无 `.git` | 2026-09-24 |

### 取舍台账

1. **判分从严 vs 从宽（F2P 侧从严）**
   选了：F2P 必须**逐条**通过才 `RESOLVED_FULL`，且「不存在」「被 SKIPPED」都算失败（`grading.py:101-109`、`:321-322`）。
   放弃了：用 pytest 整体退出码当判据的简洁性。
   代价落在：**过严会误杀**——环境导致的零散 skip/flake 会把正确补丁判成未解决；而这正是 `_resolve_case`（676 个截断 id）和 XFAIL 特例必须存在的原因，通用判分器因此长出了 benchmark 专属分支。

2. **判分从宽（FAIL_ONLY 侧从宽）**
   选了：`FAIL_ONLY_REPOS` 6 个仓库走 `check_fail_only`，**不在状态表里就算成功**（`constants/__init__.py:72-82`、`grading.py:221-228`）。
   放弃了：对这些仓库证明「每个 F2P 测试真的通过」的能力。
   代价落在：必须新增 `SUITE_RAN`（8 组非零计数正则，`grading.py:31-46`）与退出码交叉验证（`:167-175`）两道补丁去堵「缺席=通过」的洞；其中 `': ok$'` 这种为 openlayers 单独写的证据（`:41-44`）说明堵洞本身就是持续维护负担。

3. **把测试当唯一判据**
   选了：只看仓库自带测试的通过/失败，不看补丁语义、不看 code review（`grading.py:179-326`）。
   放弃了：对「改了测试来迎合补丁」的防御力。
   代价落在：**测试本身的判据质量决定一切**。于是必须把测试补丁单独切出来当判卷标准（`collect/utils.py:342-349` 按路径名 `test/tests/e2e/testing` 切分——一个纯粹的字符串启发式），并在判分侧加「退出码非 0 却无失败」的拦截（`grading.py:167-175`）。换句话说，判分的可靠性被外包给了「PR 里恰好改了叫 test 的文件」这一个假设。

4. **Docker 异构环境统一化**
   选了：每题一个容器、`/testbed` 固定工作目录、root 用户、`cap_add=["SYS_ADMIN"]`（`run_evaluation.py:116-125`），并预生成每题的 `Dockerfile`（`image_builder/docker_build.py:72-85`）。
   放弃了：单机共享环境的速度和磁盘占用。
   代价落在：README 要求 **≥120GB 磁盘、16GB 内存、8 核**（`README.md:123`），并明确 `arm64` 只是 experimental（`:128`）；还要额外维护 `image_builder`、镜像发布（`task/publish.py:222`）、以及一整套「镜像不存在就 pull、build 失败就 fall back 到已发布镜像」的降级逻辑（`run_evaluation.py:678-696`）——这套降级本身又引入了「**陈旧镜像冒充干净通过**」的新风险，`_build_before_eval` 的注释正是为堵这个洞而写（`:643-649`）。

5. **把 Verified 的数据缺陷写进 grading**
   选了：在通用判分函数里为 676 个截断 id 开前缀匹配后门（`grading.py:61-82`），并为 `pytest-dev__pytest-5262 / -7521` 保留伪测试名 `[100%]`（`log_parsers/python.py:9-18`）、为 `django__django-7188` 写死字符串（`parse_log_django`，`:111-117`）。
   放弃了：判分逻辑的 benchmark 无关性。
   代价落在：作者自己在代码里留了两条 TODO 承认 `wrong placement`（`grading.py:69-72`），并把删除条件写成「先修 676 个 id，其中 47 个还需人工裁决」；技术债被显式记账，但**在没有外部修数据之前无法清偿**。

6. **把原始日志公开、让提交者自证**
   选了：`submit package` 丢弃 run 自带报告、从 `test_output.txt` 重判（`submit/package.py:264-286`），`submit verify` 克隆提交者仓库逐题复判，并把「声称 resolved 却没交日志」直接判 FAIL（`submit/verify.py:43-51`）。
   放弃了：只交一份 `results.json` 的轻量提交。
   代价落在：**提交体验变重**——产物要走提交者自己的公开 GitHub 仓库（`submit/publish.py:40-51`），单文件超 50MB 就整体报错拒绝（`package.py:61`、`:388-393`），于是又必须给 `test_output.txt` 加 gzip（`:250-261`）；同时 `verify` 依赖 `metadata.yaml` 里 `assets.repo` 可达，私有仓库会导致校验走不通（`verify.py:84-92`）。

---

### 给写稿人的「硬数字清单」

1. **`5.0.2`** —— 包版本，`swebench/__init__.py:1`。
2. **`5.0.1 / 8-17-2026`** —— CHANGELOG 最新已发布条目；**5.0.2 没写进 CHANGELOG**，`CHANGELOG.md:26`。
3. **`5.0.0 / 8-17-2026`** —— task repo 化那次大改，`CHANGELOG.md:31`。
4. **`18126` 行** —— 仓库内 Python 总行数；其中 `swebench` 包 `15016` 行、`tests/` `3110` 行。
5. **`57`** —— `PARSER_REGISTRY` 里的日志解析器数量（覆盖 8 种语言），`log_parsers/__init__.py:69-135`。
6. **`814` 行** —— 最大解析器 `javascript.py` 的行数，`wc -l`。
7. **`1800` 秒** —— 单题测试超时（`run_evaluation.py:837`），同时也是 Docker 客户端超时（`:61`）。
8. **`128`** —— Docker 连接池大小 `SWEBENCH_DOCKER_POOL_SIZE`，`run_evaluation.py:62`。
9. **`4` 连招** —— 补丁应用策略：`git apply → --3way → --reject → patch --fuzz=5`，`run_evaluation.py:54-59`。
10. **`15` 秒** —— `docker stop --time=15`；失败则 kill（10s 超时）再 `rm --force`（10s 超时），`docker_utils.py:68,80,95`。
11. **`6` 个仓库** —— `FAIL_ONLY_REPOS`（Chart.js、p5.js、marked、bpmn-js、openlayers、eslint），`constants/__init__.py:72-82`。
12. **`676` / `47`** —— SWE-bench_Verified 中被截断的参数化测试 id 数量 / 其中歧义需人工裁决的数量，`grading.py:64,71-72`。
13. **`8` 条签名 / `2` 个 tier** —— 基础设施故障分类 `INFRA_FAILURE_SIGNATURES`：5 条 `environment` + 3 条 `ambiguous`，`infra_failure.py:22-61`。
14. **`exec_run_with_timeout(timeout=60)`** —— 该函数签名默认值 60 秒（评测主循环传入的是 1800），`docker_utils.py:128`。
15. **`300` / `seed=42`** —— SWE-bench Lite 抽样题数与随机种子，`collect/make_lite/make_lite.py:68,81`。
16. **`40` 词 / `1` 文件 / `3` hunk** —— Lite 三条质量过滤阈值，`make_lite.py:21,35,36`。
17. **`9` 个关键词** —— PR 关联 issue 的关键词表，`collect/utils.py:21-31`。
18. **`8` 个必填字段** —— task repo 的 `REQUIRED_KEYS`，`task/checks.py:36-45`。
19. **`50 * 1024 * 1024` 字节** —— 提交产物单文件上限，超限直接报错，`submit/package.py:61,388-393`。
20. **`schema_version: 2`** —— `results.json` 的 schema 版本，`reporting.py:159`。
21. **`120*60` 秒 / `60*30` 秒 / `7` 次重试** —— Modal 外层函数超时 / 沙箱默认超时 / 建沙箱重试次数，`modal_eval/run_evaluation_modal.py:230-236,78-80,71-74`。
22. **`120GB / 16GB / 8 核`** —— README 给出的评测资源下限，`README.md:123`。
23. **`min(0.75 * os.cpu_count(), 24)`** —— README 建议的并发上限，`README.md:124`。
24. **`480`** —— SWE-bench Multimodal v2 开放题量（2026-09-01 公告），`README.md:34`。
25. **`sweb.eval.x86_64.<instance_id>:latest`** —— 镜像命名约定；`__` 会被替换成 `_1776_`（Docker Hub 不允许双下划线），`image_builder/image_spec.py:36-44`、`task/checks.py:66-69`。


---

## 项目二 · OSWorld（⭐3155 · Apache-2.0 · 第二级「考场修成真电脑」）

> 369 条 Ubuntu 任务 + 49 条 Windows 任务，判分只看用完机器之后的状态。

# OSWorld 源码拆解笔记

> 仓库：`xlang-ai/OSWorld`（本地路径 `cache/osworld`）
> 规模：22 MB，619 个 `.py`（`find . -name '*.py' | wc -l` → 619），无 `.git`
> 取证时点：2026-09-24
> 说明：下文所有行号均指本仓库当前文件内容；数字凡"会变"的均已用命令实测。

---

### 人话导览

**① 它是什么、给谁用**

想象一个考场：不是发卷子，而是给你一台**真的装了 Ubuntu（或 Windows）的电脑**，屏幕上 Chrome、LibreOffice、GIMP、VS Code、VLC、Thunderbird 一应俱全，桌面文件也摆好了。考生不是人，是 AI（多模态 agent）。监考老师不发选择题，只给一句自然语言指令（比如"帮我把 Chrome 的『请勿追踪』打开"），AI 自己看屏幕、自己动鼠标键盘，做完之后**由机器去检查真实软件的最终状态**，判它过没过。`evaluation_examples/` 下就是 369 道（Ubuntu 版）这样的题。给谁用：做 computer-use agent 的研究者、模型团队、榜单提交者。

**② 为什么现在值得讲**

它不是"模拟器里点按钮"，而是**真虚拟机 + 真软件 + 真文件**的组合（`desktop_env/providers/` 里 VMware/VirtualBox/Docker/AWS/Azure 等 11 个 provider）。而且在 2025-07-28 出过一次 **OSWorld-Verified** 大修（`README.md:36`）：修题、加 AWS 并行（README 声称能把评测压到 1 小时内），并明确说"请用新版结果对比排行榜"。一个基准能做到"作者自己回头修题并宣布旧结果不作数"，本身就说明这套判分是真的当生产力在用。

**③ 核心流程怎么跑（生活类比）**

把它当成**考前装考场 → 考试 → 阅卷**三步：

- **装考场**：开机（`provider.start_emulator`）→ 把快照回滚到干净状态（`revert_to_snapshot`）→ 按题目 JSON 里的 `config` 列表，逐条把"考前布置"做完：下载文件、打开应用、摆好标签页（`desktop_env/controllers/setup.py` 的 `setup()` 按 `type` 字符串反射调用 `_xxx_setup`）。
- **考试**：agent 每步拿到「截图 +（可选）无障碍树」，吐出一串 pyautogui 命令，环境执行、截图、记 trajectory；上限 15 步（默认）。
- **阅卷**：`env.evaluate()` 按 JSON 里的 `evaluator` 指认的 **getter** 去把"某个应用的真实状态"取出来（比如读 VLC 的 HTTP 接口状态、读 Chrome 的 cookie 数据库），再交给 **metric** 函数比对 `expected`，吐 0 或 1。

**④ 具体证据（可核对）**

- 判分器注册方式：`desktop_env/desktop_env.py:380-382` → `getattr(metrics, func)`；结果取数器 `desktop_env.py:385` → `getattr(getters, "get_{:}".format(res["type"]))`。
- 一条任务长什么样：`evaluation_examples/examples/chrome/030eeff7-b492-4218-b312-701ec99ee0cc.json`（`id / snapshot / instruction / source / config / trajectory / related_apps / evaluator / proxy / fixed_ip / possibility_of_env_change`）。
- 判分最重的函数：`compare_table`（79 次，`counted`），`compare_pptx_files`（53 次）。
- 步数上限默认 15：`run.py:97`。
- 分辨率 1920×1080：`desktop_env/desktop_env.py:97`，坐标归一化常数在 `gemini_action_parser.py:48-53`。

**⑤ 取舍、坑、不适用场景**

- **真虚拟机很重**：默认 VMware，一次快照回滚 + 重启就是分钟级；Docker provider 干脆**不支持快照**（`docker/provider.py:151` 抛 `NotImplementedError`），只能"关掉重开"。
- **判分按应用硬编码**：148 个 metric 函数 + 58 个 getter 全部手工写死到具体软件的界面/文件结构上（`metrics/` 目录 15 个文件）。新加一个软件，往往要新写一批 getter + metric。
- **Ubuntu / Windows 严重不对称**：Ubuntu 369 题 vs Windows 49 题；Windows 的 JSON 连 `proxy`/`fixed_ip` 字段都没有。
- **不适合**：想轻量、想纯容器、想跑非桌面（Web-only）任务的场景——它刻意选了"整台真机"这条路。

**⑥ 三步落地动作**

1. 先跑 `python quickstart.py --provider_name docker`（或 vmware），确认环境能被拉起、能截到图（`quickstart.py:58` 会执行一次 `rightClick` 自检）。
2. 跑小集：`python scripts/python/run_multienv.py --provider_name docker --max_steps 15 --num_envs 10 --test_all_meta_path evaluation_examples/test_small.json`。
3. 读结果：`python show_result.py --detailed`，会打印 `score/total` 形式的按域明细（`show_result.py:56-66`）。

---

## 1. 一句话定义

OSWorld 是一个**把真实操作系统虚拟机当作可编程环境、用真实桌面软件（Chrome/LibreOffice/GIMP/VLC/VSCode/Thunderbird）的最终状态来做判分的多模态 agent 基准与基础设施**，以 `DesktopEnv`（Gymnasium 接口）+ 可插拔 provider + 声明式任务 JSON 三件套对外提供。

## 2. 作者 + 思路来源

- 作者：Tianbao Xie、Danyang Zhang、Jixuan Chen、Xiaochuan Li、Siheng Zhao、Ruisheng Cao 等（`README.md:288` 的 arXiv BibTeX；`setup.py:27` 的 author 字段是同一批人）。
- 论文：arXiv `2404.07972`（`README.md:287-292`），NeurIPS 2024（题面提供）。
- 机构背景：xlang-ai 组织（`README.md:2` 的 HuggingFace 资产域 `huggingface.co/datasets/xlangai/...`）。
- 思路来源（源码里能看到的血统）：
  - 明确沿用 **WebArena 的 run 脚本骨架**——`run.py:2` 注释："Utils and basic architecture credit to https://github.com/web-arena-x/webarena/blob/main/run.py"。
  - 环境层用 **Gymnasium / OpenAI Gym 接口**（`desktop_env/desktop_env.py:12` `import gymnasium as gym`，类声明在 `:85` `class DesktopEnv(gym.Env)`），`step/reset/render` 全套对齐 RL 惯例。
  - 观察空间定义直接对应经典 computer-use 三件套：截图 / 无障碍树 / 两者叠加（`mm_agents/README.md`）。

## 3. 输入 → 输出

**输入**
- 一条任务 JSON（字段见第 4、5 节），或一个任务清单 JSON（`evaluation_examples/test_all.json` 等）。
- 一个能连上的 VM（provider + `path_to_vm`，`desktop_env/desktop_env.py:91-104` 的构造参数）。
- 一个 agent 对象，接口约定是 `reset(...)` + `predict(instruction, obs) -> (response, actions)`（`mm_agents/README.md`；实现见 `mm_agents/agent.py:300`）。

**输出**（落在 `result_dir`）
- 每个任务的 `result.txt`（0/1，`lib_run_single.py:68-69`）；日志 `runtime.log`；轨迹 `traj.jsonl`；每步截图 `step_N_时间戳.png`；录像 `recording.mp4`。
- 汇总：`summary/results.json`（线程安全追加，`lib_results_logger.py:26-105`，用 `fcntl.flock` 加锁）。
- 终端：`show_result.py` 打印按域成功率 + Office/Daily/Professional 三个大类的成功率（`show_result.py:75-90`）。

## 4. 信息流（一条任务从配置到出分怎么走）

以 `examples/chrome/030eeff7-...json` 为例：

1. **run.py 读清单**：`test_all_meta` 是 `{domain: [example_id,...]}`（`run.py:323-324`），逐域逐 id 打开 `examples/{domain}/{id}.json`（`run.py:175-179`）。
2. **建环境**：`DesktopEnv(...)`（`run.py:161-171`）→ 内部 `create_vm_manager_and_provider(provider_name, region)`（`desktop_env.py:148`）→ `_start_emulator()`（`:198`）→ `provider.start_emulator` → `provider.get_ip_address` 返回 `"host:server:chromium:vnc:vlc"`，按 `rsplit(':', 4)` 拆出端口（`desktop_env.py:207-216`）。
3. **reset + 环境准备**：`run_single_example` 先 `env.reset(task_config=example)`（`lib_run_single.py:18`）。reset 里先决定要不要回滚快照（云 provider 且环境"干净"就跳过，`desktop_env.py:298-307`），再 `self.setup_controller.setup(self.config, ...)`（`:316`）——**这一步是"考前布置"**。
4. **setup 反射分发**：`setup()` 对 `config` 里每一项取 `cfg["type"]`，拼成 `_{type}_setup` 用 `getattr` 调用（`controllers/setup.py:184-196`）。本任务两条 `launch`：先起 `google-chrome --remote-debugging-port=1337`，再 `socat tcp-listen:9222,fork tcp:localhost:1337` 把调试端口转出来。
5. **考试循环**：`while not done and step_idx < max_steps`（`lib_run_single.py:31`）；每轮 `agent.predict(instruction, obs)` 拿 `actions`，对每个 action 调 `env.step(action, sleep_after_execution)`（`:40`），写截图与 `traj.jsonl`，`done` 为真则 break。
6. **动作落地**：`DesktopEnv.step` 把 `pyautogui` 类动作当 Python 代码串发给 VM 里的 HTTP 服务（`desktop_env.py:441-451`；VM 内服务见 `desktop_env/server/main.py:77-79` `/execute`）。
7. **判分前收尾**：`evaluator.postconfig` 先执行（`desktop_env.py:463-464`）。本任务的 postconfig 很讲究：注入 JS 让焦点失焦 → sleep 1s → `pkill chrome` → 重开 chrome → sleep 3s（目的：让"改设置"落盘到 profile，再重启读盘）。
8. **取状态 + 打分**：`env.evaluate()` 里 `result` getter = `getters.get_enable_do_not_track(env, {"type": "enable_do_not_track"})`；`expected` getter = `get_rule` 返回 `{"expected": "true"}`；metric = `exact_match(result, {"expected": "true"})` 返回 1.0 或 0.0（`desktop_env.py:512-524`）。
9. **落盘 + 汇总**：`result.txt`、`log_task_completion` → `results.json`（`lib_run_single.py:65-72`）。

## 5. 文件地图（10 个核心文件逐个说）

### 5.1 `README.md`（306 行）
项目门面。关键信息点：Updates 里 2025-07-28 的 **OSWorld-Verified**（`:36`）、provider 安装分叉（VMware/VirtualBox `:43`，Docker `:77`，Modal `:97`，Daytona `:110`，AWS `:120`）、两条基线命令（单机 `run.py :166`、并行 `scripts/python/run_multienv.py :180`）、账号密码约定（`:260-263`：Ubuntu 是 `user`/`password`，云上默认 `osworld-public-evaluation`）。**注意** `:247` 链接到 `desktop_env/README.md`，但本仓库**没有这个文件**（`find` 未列出），是坏链。

### 5.2 `desktop_env/desktop_env.py`（530 行）
全仓的"总控"。`class DesktopEnv(gym.Env)`（`:85`）。负责：provider 工厂调用（`:148`）、端口解析（`:207-216`）、快照回滚决策（`:298-307`）、`config` 准备（`:316`）、`step`（`:416`）、`evaluate`（`:458`）。**它同时是"判分注册表"**：把 JSON 里的字符串 `func`/`result.type`/`expected.type` 反射成真正的 Python 函数（`:380-410`）。`MAX_RETRIES = 5`（`:25`）。

### 5.3 `desktop_env/controllers/setup.py`（1148 行）
"考前布置"的执行器。21 个 `_{type}_setup` 方法（实测 `grep -c` → 21）：`_download_setup / _upload_file_setup / _launch_setup / _execute_setup / _command_setup / _open_setup / _sleep_setup / _activate_window_setup / _chrome_open_tabs_setup / _chrome_inject_js_setup / _googledrive_setup / _login_setup / _update_browse_history_setup / _proxy_setup ...`。它把宿主机的文件/URL 送进 VM（multipart 上传到 `/setup/upload`，`:274`），并处理 Chrome CDP 的"启动就绪"竞态（`_wait_for_chrome_ws_ready`，`:101`）。

### 5.4 `desktop_env/controllers/python.py`（644 行）
动作执行与基础观测。`execute_action`（`:301`）把 13 种动作翻译成 pyautogui 调用（`:320-472`）；`execute_python_command`（`:195`）把 `pyautogui` 代码串 POST 到 VM；`get_screenshot`（`:101`）带 3 次重试与 PNG/JPEG magic bytes 校验（`:84-99`）；`get_accessibility_tree`（`:129`）。含一段**输入补丁**：为了修正 pyautogui 在 Linux 上对 `{}|:"<>?` 等符号的 Shift 判定，注入 `PYAUTOGUI_INPUT_PATCH`（`:13-27`）。

### 5.5 `desktop_env/actions.py`（203 行）
动作空间"规格书"。`X_MAX = 1920 / Y_MAX = 1080`（`:1-2`），`KEYBOARD_KEYS` 是白名单（`:4`），`ACTION_SPACE`（`:6-203`）逐条声明 13 个动作 + 参数类型/范围/是否可选，末尾三个特殊动作 `WAIT / FAIL / DONE`（`:191-202`）。

### 5.6 `desktop_env/evaluators/__init__.py`（5 行）与 `evaluators/metrics/__init__.py`（170 行）、`evaluators/getters/__init__.py`（45 行）
判分体系的"注册表"。`metrics/__init__.py` 把 15 个 metrics 模块里的 148 个函数名平铺 re-export（实测解析得 148），末尾定义 `infeasible()` 空函数（`:169-170`）作为"任务本身不可完成"的哨兵；`getters/__init__.py` re-export 58 个 `get_` 函数（实测）。`evaluators/__init__.py` 只剩两行注释，是历史残留。

### 5.7 `desktop_env/evaluators/metrics/`（15 文件，206 个 `def`）
本仓最值钱的部分。"怎么判对不对"全在这。按应用分文件：`chrome.py(796) / docs.py(1436) / gimp.py(947) / slides.py(1550) / table.py(1026) / general.py(704) / vlc.py(558) / vscode.py(381) / utils.py(842) ...`。`utils.py` 是公共底座（`_match_value_to_rule` 在 `:712`，支持 `re.* / eq / ne / le / lt / ge / gt / approx:TH / range.* / str_set_eq` 等规则）。

### 5.8 `desktop_env/evaluators/getters/`（11 文件，71 个 `def`）
"把状态取出来"的取数器。`chrome.py` 最重（2928 行、41 个 `def`），因为 Chrome 的大部分状态没法通过 UI 读，得靠 CDP/Playwright/SQLite/a11y 树绕。`file.py(186)` 负责把 VM 里的文件拉回宿主机缓存（`get_vm_file`，`:100`）；`vlc.py(108)` 走 VLC 的 HTTP 接口（`get_vlc_playing_info`）。

### 5.9 `desktop_env/providers/`（11 个可接线 provider）
`base.py`（97 行）定义两个抽象基类：`Provider`（`start_emulator / get_ip_address / save_state / revert_to_snapshot / stop_emulator`，`:4-44`）与 `VMManager`（`initialize_registry / add_vm / delete_vm / occupy_vm / list_free_vms / check_and_clean / get_vm_path`，`:47-97`）。`__init__.py:4` 的工厂 `create_vm_manager_and_provider` 用 if-elif 分发 11 个 provider。

### 5.10 `lib_run_single.py`（1485 行）
单任务的"考试流程"。**16 个** `run_single_example*` 变体（实测 `grep -c`）——因为不同 agent 的 `step()` 返回签名不一样，作者没有抽象成统一接口，而是**一个模型抄一份循环**。主版本在 `:14`，循环在 `:31`，`time.sleep(60)` 等环境就绪（`:26`）、判分前 `time.sleep(20)`（`:64`）。

### 5.11 `run.py`（348 行）与 `scripts/python/run_multienv.py`
单机入口与并行入口。`run.py` 自带 `--max_steps 15`（`:97`）和断点续跑（`get_unfinished`，`:234`）（注释 `:18` 已说明"almost deprecated"）。并行版用 `multiprocessing.Process + Manager`（`run_multienv.py:11`），`--num_envs`（`:86`），并按信号做优雅退出（`:155-171`）。全仓 40+ 个 `run_multienv_*.py` 基本是同一模板换 agent。

## 6. 文件亮点（6 条，各点名文件与函数）

1. **判分器靠"字符串反射"解耦**：`desktop_env.py:380` `self.metric = [getattr(metrics, func) for func in self.evaluator["func"]]`——任务 JSON 里写 `"func": "compare_table"` 就能指到函数，不用改代码。代价是拼错就是 `AttributeError`，没有编译期检查。
2. **`postconfig` 让"改设置类任务"可判**：`desktop_env.py:463-464` 在判分前先跑 `evaluator.postconfig`。`examples/chrome/030eeff7-...json` 用它做了 `pkill chrome` → 重开 → 等 3s 的"重启落盘"动作，否则读 profile 会读到内存态。
3. **Chrome CDP 双向就绪判定**：`controllers/setup.py:101` `_wait_for_chrome_ws_ready` 同时要求"stderr 日志出现 `DevTools listening on ws://`"**且**"日志里的 browser GUID == 活着的 `/json/version` GUID"，用 GUID 相等来排除"上次被杀掉的 Chrome 留下的陈旧日志"。超时 `CHROME_CDP_READY_TIMEOUT_S = 120`（`:51`）。
4. **坐标归一化被放在客户端**：`gemini_action_parser.py:51-53` `normalize_coord = int(coord/1000 * max)`——模型吐 0–1000 的归一化坐标，客户端换成像素。而 pyautogui 路线（`mm_agents/agent.py`）**不做归一化**，模型直接吐像素。两套坐标观并存。
5. **`infeasible` 哨兵任务**：`metrics/__init__.py:169` 定义空函数，`desktop_env.py:469-474` 特判——如果任务本身不可完成，**agent 最后一步必须是 `FAIL` 才得 1 分**，否则 0。这是防"瞎做也得分"的设计，`test_infeasible.json` 收了 26 条。
6. **`_match_value_to_rule` 一套规则打天下**：`metrics/utils.py:712` 把 `{"method": "approx:3", "ref": 100}`、`{"method": "re.IGNORECASE", "ref": "..."}`、`{"method": "range.te", "ref": [0,2]}` 等规则统一解释，让 `compare_table`（`table.py:281`）能用同一套 DSL 逐单元格声明断言。

## 7. 跟默认做法的差异

"默认做法"= 让模型自己说"我做完了"（self-report / 让 LLM 当裁判）。

| 维度 | 让模型自说 | OSWorld 的做法 |
|---|---|---|
| 判据 | 模型的话 | **真实软件的真状态**：`getters/` 里的 58 个取数器 |
| 判分者 | 模型自己（会自利） | **确定性函数**：`metrics/` 里 148 个函数，返回 0/1 或相似度 |
| 状态从哪来 | 无 | VLC HTTP 接口（`getters/vlc.py:get_vlc_playing_info`）、Chrome profile SQLite、xlsx/docx/pptx 解析、a11y 树、VM 命令行输出 |
| `DONE` 的意义 | 结束信号 = 成功 | `DONE` 只是"我停了"，**不等于得分**；分要靠 `env.evaluate()` 独立算（`desktop_env.py:434-436` vs `:458`） |
| 不可完成任务 | 模型会瞎蒙 | `infeasible` 哨兵：必须主动喊 `FAIL` 才对（`:469-474`） |

一句话：**把"做没做完"从主语（模型）手里拿走，交给宾语（软件状态）。**

## 8. 做得好的 / 不够的

**做得好**
1. **"状态取数"与"状态判定"彻底分离**（getters vs metrics）。同一个 getter（如 `get_vm_command_line`）能被几十个 metric 复用；换应用主要加新文件，不动框架。这是它能扩到 418 条任务的结构性原因。
2. **容错写在取数环节而不是判分环节**：`getters/file.py:137-141` 取不到文件时 `append(None)` 而不是抛异常；`getters/vlc.py:get_vlc_playing_info` 连不上时重试 5 次、轮换 3 个候选密码，最后返回 `None`。这让"环境抽风"表现为**判 0 分**而不是**崩掉整轮**——对一个要跑几百条任务、每条几分钟的基准，这是对的取舍。

**不够的**
1. **判分大多是全有全无**。`compare_table` 一路 `passes = passes and metric`（`table.py`），最后 `return float(passes)`；`check_direct_json_object` 任一 key 不等即 `return 0.`。真正做连续给分的只有少数（`fuzz.ratio` 系：`metrics/docs.py:228`、`:1221` 附近、`metrics/general.py:98`）。结果是"做了 90% 但最后一个单元格错"和"什么都没做"分数一样，**信号分辨率低**。
2. **判分器对软件版本/界面细节高度敏感，且维护靠人肉**。判分逻辑写死到具体文件名/坐标/HTML 结构（如 `getters/chrome.py:get_active_url_from_accessTree` 要匹配 `application[name=Google Chrome] entry[name=Address and search bar]`，还要分支 ARM 用 `Chromium`）。OSWorld-Verified（`README.md:36`）本身就是"作者回头大修题面与判分"的证据——**这类基准的维护成本是持续性的，不是一次性**。

## 9. AI 范式提炼

**统领范式：把"任务成功"定义成对**环境客观状态的断言**，而不是对模型输出的断言；于是 agent 能力的上限由"状态可观测性"决定，而不是由"模型的表述能力"决定。**

具体例子：判断"Chrome 请勿追踪是否开启"，不是问模型，而是 `getters.get_enable_do_not_track` 去读 Chrome 的 Preferences/state，再 `exact_match(actual, "true")`（`examples/chrome/030eeff7-...json` 的 `evaluator`）。推论是：**你想考什么能力，就必须先为那个能力造一把"客观尺子"**——OSWorld 的 58 个 getter 就是 58 把尺子，尺子之外的能力，这个基准测不到。

## 10. 跟你对接（落地三问）

1. **你有"客观状态"吗？** 如果你的 agent 产物是文件/数据库/应用设置，可以照搬 getters+metrics 两层；如果产物是"一段回答好不好"，那 OSWorld 这套帮不上，你只能回到 LLM-judge。
2. **你愿意付虚拟机的钱和时间吗？** 真 VM 意味着每条任务分钟级、需要快照/回滚。如果你只需要容器级隔离，`--provider_name docker` 能省运维，但要接受**没有快照、每次重开容器**（`docker/provider.py:151-154`），任务数一多时间会爆。要并行上量就走 AWS（`AWS_GUIDELINE.md`，AMI 见 `providers/aws/manager.py:42`）。
3. **你的判分要不要"部分给分"？** OSWorld 主流是 0/1。如果你要用它做训练 reward，先想清楚稀疏信号怎么处理——这是它设计上的已知短板（第 8 节）。

## 11. 信息截止

2026-09-24（以本地 cache 快照为准；README 内最晚一条更新为 2025-07-28）。

## 12. 当前版本

- 仓库内两个版本号**不一致**：`pyproject.toml:3` → `version = "0.1.0"`；`setup.py:26` → `version="1.0.1"`（发布到 PyPI 的 `desktop-env` 包用后者）。
- `pyproject.toml:6` → `requires-python = ">=3.12"`；但 `setup.py:39` → `python_requires='>=3.10'`，README `:47` 也说 ">= 3.10"。**同一仓三处口径不同**。
- 无 `.git`，取不到 commit 哈希 → **按默认分支 main，无 .git**。
- 语言/工具链：`.mise.toml` 锁 `python = "3.12"`，`.envrc` 用 direnv + mise 自动建 `.venv`。

---

### 二次深读

### 深读 1：判分器是怎么组织的——"注册表 + 目录分文件 + 字符串反射"

- **源码怎么做**：`desktop_env/evaluators/metrics/__init__.py` 按应用从 15 个模块 re-export 了 **148 个**函数名（实测解析）；`getters/__init__.py` re-export **58 个** `get_` 函数。任务 JSON 里 `evaluator.func` 是个字符串（或字符串列表），`desktop_env.py:380` 用 `getattr(metrics, func)` 解析；`evaluator.result`/`expected` 的 `type` 字段被拼成 `"get_{type}"` 再 `getattr(getters, ...)`（`:385`、`:395`）。目录结构：`metrics/{basic_os,chrome,docs,general,gimp,libreoffice,others,pdf,slides,table,thunderbird,utils,vlc,vscode}.py`。
- **规模实测**：`metrics/*.py` 里 `^def` 共 206 个（含未导出的内部helper，如 `table.py` 的 `_parse_sheet_idx`、`utils.py` 的 `_match_value_to_rule`）；`getters/chrome.py` 一个文件就有 41 个 `def`、2928 行。
- **为什么必须这样**：任务与判分是"数据"与"代码"分离的。题目贡献者只写 JSON，不改框架；判分器贡献者只加函数，不改题目。这是能堆到 418 条任务的组织前提。
- **代价**：没有注册校验。实测 `参考的 func 唯一值 121 个` 全部能在 metrics 里找到（引用了但未导出 = 无），但这依赖人工纪律；拼错一个字母就是运行期 `AttributeError`，且要到跑到那条任务才暴露。

### 深读 2：一条任务 JSON 的完整字段 + config.type 的种类

- **顶层字段**（实测 418 条 JSON 的字段计数）：`id`(418)、`snapshot`(418)、`instruction`(418)、`source`(418)、`trajectory`(418)、`related_apps`(418)、`evaluator`(418)、`config`(417，有 1 条无 config)；另有 **369 条** Ubuntu 任务才有的 `proxy` / `fixed_ip` / `possibility_of_env_change`，4 条有 `hint`，1 条是 `env_may_change`。
- **`config[].type` 分布**（实测）：`download` 324、`launch` 293、`open` 194、`execute` 166、`activate_window` 67、`chrome_open_tabs` 58、`command` 37、`sleep` 19、`googledrive` 10、`login` 10、`update_browse_history` 1、`chrome_close_tabs` 1 —— 共 **12 种**，与 `SetupController` 的 21 个 `_xxx_setup` 对应（部分 setup 方法没有被任何任务用到，如 `_replay_setup`/`_act_setup` 直接 `raise NotImplementedError`）。
- **`evaluator` 子字段**：`func`(418)、`result`(390)、`expected`(378)、`postconfig`(240)、`options`(134)、`conj`(37)。
- **`evaluator.func` 单值 vs 列表**：**57 条**任务的 `func` 是列表（多判分），其中 `conj` 为 `and` 的 27 条、`or` 的 30 条（`desktop_env.py:383` 默认 `"and"`，`:502-509` 处理 and 则取均值、or 则取 max）。
- **`result.type` 分布**（前几名）：`vm_file` 309、`vm_command_line` 40、`active_url_from_accessTree` 14、`active_tab_html_parse` 12、`googledrive_file` 9、`cache_file` 9…… **`expected.type`**：`cloud_file` 258、`rule` 178、`rule_relativeTime` 13。
- **为什么必须这样**：`result`（实际状态）与 `expected`（期望状态）用**同一套 getter 语义**取，才能"苹果比苹果"。`expected.type: cloud_file` 之所以占 258，是因为基准把"标准答案文件"托管在 HuggingFace，判分时现下（`getters/file.py:get_cloud_file`），避免把 GB 级答案塞进仓库。
- **代价**：示例任务看不出"一条任务到底要下多少东西"——`download` 出现 324 次且 URL 分散在每条 JSON 里，断网/失效链接会直接让判分变 0，而不是报"题目坏了"。

### 深读 3：判分器遇到"环境状态取不到"怎么办——三层兜底、最终判 0，不炸

- **第一层（getter 自己）**：`getters/file.py:137-141` 取文件失败返回 `None` 并记账，不抛；`getters/general.py:20-22` 命令执行非 200 返回 `None`；`getters/vlc.py:get_vlc_playing_info` 5 次重试 + 3 个候选密码（`configured_password`/`"password"`/`client_password`），失败返回 `None`；`getters/chrome.py:get_active_url_from_accessTree` 在 a11y 树为空/解析失败/选择器找不到元素时统统 `return None`。
- **第二层（metric 自己）**：绝大多数 metric 第一行就做 None 短路。`metrics/general.py:29-30` `check_include_exclude`：`if result is None: return 0.`；`compare_table`（`table.py:298-305`）：`result is None` 或文件不存在 → `return 0.0`。
- **第三层（env.evaluate）**：`desktop_env.py:491-494`（多 metric 分支）和 `:514-516`（单 metric 分支）捕获 `FileNotFoundError` → 记 error 并按 `conj` 决定返回 0。注意一个细节：多 metric 分支里 `FileNotFoundError` 只在 `conj == 'and'` 时直接 `return 0`，`conj == 'or'` 时**不 return**，会继续往下走（`:493-494` 的条件式），这算是给 `or` 语义留的口子。
- **部分给分在哪**：`fuzzy_match`（`general.py:95-98`，`fuzz.ratio/100`）、`diff_text_file`（`:84-92`，`difflib.SequenceMatcher.ratio()`）、`compare_docx_paper_records`（`docs.py` 附近 `:1218` 公式 `score_i = clamp((s_i - b_i)/(1 - b_i), 0, 1)`，最终取均值）。
- **为什么必须这样做**：一个 run 要跑几百条任务、总计几小时到几十分钟（并行），任何一条因"读不到文件"抛异常都会污染整轮。**把不确定性收敛成"这条得 0"是唯一能跑完几百条的选择**。
- **代价**：环境真的坏了 和 agent 真没做，在结果里**看起来一样**（都是 0）。所以 OSWorld 提供 `scripts/python/manual_examine.py` 和 `monitor/` 来人工复核（README `:223-243`）——这本身就是"机器判分不可全信"的自我承认。

### 深读 4：`run.py` / `lib_run_single.py` 的执行循环细节（步数、截图、坐标、超时、兜底）

- **动作空间**：`desktop_env/actions.py:6-203` 声明 13 个动作，`X_MAX/Y_MAX = 1920/1080`（`:1-2`），键盘白名单 `KEYBOARD_KEYS`（`:4`）。特殊动作 `WAIT/FAIL/DONE` 在 `:191-202`。
- **循环上限**：`run.py:97` `--max_steps` 默认 **15**；循环条件 `while not done and step_idx < max_steps`（`lib_run_single.py:31`），每轮内层 `for action in actions`，遇 `done` 就 `break`（`:60-62`）。
- **`done` 从哪来**：只有 `DesktopEnv.step` 遇到 `FAIL`/`DONE` 才置 `done=True`（`desktop_env.py:431-436`）。**没有"环境自己判断完成"的外部信号**。所以"防提前结束"只靠 `max_steps` 这个上界——**agent 说 DONE 就立刻停，判分照跑**（不管它说得多离谱）。
- **截图**：每步执行完都存 `step_{n}_{时间戳}.png` 并把 action/response/reward/done/screenshot_file 追加到 `traj.jsonl`（`lib_run_single.py:44-59`）。时间戳用 `%Y%m%d@%H%M%S%f`（`:38`）。
- **坐标处理**：**不在 run 循环里做**。pyautogui 路线的动作就是"Python 代码串"，模型吐什么坐标就执行什么（`desktop_env.py:446-451` → `python.py:execute_python_command`）；归一化只出现在 CLI 系 agent 的 parser 里（`gemini_action_parser.py:51-53`，`uitars15_v1.py:286` 注释 "Convert to float and scale by 1000"）。
- **超时/等待**：reset 后硬等 `time.sleep(60)`（`lib_run_single.py:26`），最终判分前再等 `time.sleep(20)`（`:64`）；每步之间 `time.sleep(pause)`（`desktop_env.py:453`，`pause` 来自 `--sleep_after_execution`，默认 `0.0`）。HTTP 层各自带超时：截图 10s（`python.py:108`）、执行命令 120s（`:207`）、上传 `(10, 600)`（`setup.py:332`）、打开文件 HTTP 1300s+10s=1810s（`setup.py:391`）。环境准备重试 `MAX_RETRIES=5`（`desktop_env.py:25`，`:283` 起），setup 连接重试 `MAX_RETRIES=20`（`setup.py:40`）。
- **异常兜底**：`run.py:204-228` 用 try/except 包住 `run_single_example`，失败时**结束录像**并往 `traj.jsonl` 写一条 `{"Error": "Time limit exceeded ..."}`，**不中断整轮**。
- **为什么必须这样做**：真软件慢且不可预测（Chrome 起不来、LibreOffice 弹窗），60s/20s 的硬等是"用时间换确定性"；单条失败不杀全局则是"用 0 分换整轮完成"。
- **代价**：每条任务的**固定开销就有 80 秒**（60+20），369 条就是 8 小时级别的纯等待——这也是为什么 README 一再强调 AWS 并行（`README.md:121`）。

### 深读 5：provider 抽象——5 个方法统一 11 种后端，代价各不相同

- **接口**：`providers/base.py` 定 `Provider`（`:12 start_emulator(path_to_vm, headless)`、`:19 get_ip_address`、`:26 save_state`、`:33 revert_to_snapshot`、`:40 stop_emulator`）与 `VMManager`（`:47-97`，含 `occupy_vm(vm_path, pid)` 做多进程抢占、`list_free_vms`、`check_and_clean`）。
- **统一方式有二**：一是 `get_ip_address` 的返回约定——带端口的 provider 返回 `"host:server:chromium:vnc:vlc"`，`desktop_env.py:208` 用 `rsplit(':', 4)` 拆（注释 `:205-206` 特别说明 IPv6 要用 rsplit 免得把 host 自己的冒号吃掉）；不带端口的只返回 `"host"`，此时 `len(vm_ports) != 5`，沿用类默认端口（`:212-216`）。二是 VM "占用登记"，`VMManager.occupy_vm` 让多进程不抢同一台机（`desktop_env.py:262`）。
- **各后端落地**：`vmware/provider.py:33` 用 `subprocess.Popen` 包 `vmrun`（`:63 start`、`:90 snapshot`、`:96 revertToSnapshot`）；`virtualbox/provider.py:106` `VBoxManage snapshot <uuid> take`、`:114 restore`；`docker/provider.py` 直接 `docker.from_env()`，`:109` 起 `happysixd/osworld-docker`，`:120-125` 映射 8006/5000/9222/8080 四个端口（宿主端口用 `_get_available_port` 从 8006/5000/9222/8080 起找，`:94-97`，并用 `FileLock` + `/tmp/docker_port_allocation.lck` 防并发抢端口，`:36`、`:89`）；AWS 按区域查 AMI（`aws/manager.py:42` `IMAGE_ID_MAP`，us-east-1 的 1920×1080 AMI 是 `ami-0d23263edb96951d8`）。
- **文件传输与端口映射**：文件走后端无关的 HTTP——`setup.py:_download_setup` 先下到本地缓存（用 `uuid5(NAMESPACE_URL, url)` 命名，`:218-220`），再 multipart 上传到 VM 的 `/setup/upload`（`:274`）；Docker/AWS 这类端口是动态的，靠 `get_ip_address` 把映射后的宿主端口回传给 `PythonController`。
- **为什么必须抽象**：`DesktopEnv` 只认这 5 个方法，换后端不改上层。
- **代价（很实在）**：
  - **快照能力不对等**。Docker 的 `save_state` 直接 `raise NotImplementedError`（`docker/provider.py:151`），`revert_to_snapshot` 退化成 `stop_emulator`（`:153-154`）——**没有"秒回干净状态"，只能重建容器**。
  - **`base.py` 的签名已经过期**：抽象 `start_emulator(self, path_to_vm, headless)` 是 2 参，但实际调用点 `desktop_env.py:201` 传 3 参（多一个 `os_type`），Docker/VirtualBox 实现都补了 `os_type`。抽象基类与实现不一致，是长期演化留下的痕。
  - **工厂没接线完**：`providers/` 里有 `gcp/manager.py`、`gcp/provider.py`，但 `providers/__init__.py` 的工厂**没有任何 `gcp` 分支**（实测 grep 无命中），而 `run.py:80` 的 `--provider_name` help 却写着支持 `gcp`（`:80`）→ 传 `--provider_name gcp` 会落到 `raise NotImplementedError`（`providers/__init__.py:58-59`）。

### 深读 6：初始状态快照（`settings/`）与"为什么用快照而不是每次重装"

- **快照名从哪来**：任务 JSON 的 `snapshot` 字段（418 条全有），默认值是 `DesktopEnv(snapshot_name="init_state")`（`desktop_env.py:94`）。Chrome 类任务 `snapshot: "chrome"`、Windows Word 类 `snapshot: "word"`（实测 `examples_windows/word/0810415c-....json`）。
- **`evaluation_examples/settings/` 里是什么**：不是镜像，而是**凭据/配置模板**——`settings/proxy/dataimpulse.json`（代理池，`setup.py:32` 默认路径）、`settings/google/settings.json.template`（Google 账号，`SETUP_GUIDELINE.md:32`）、`settings/googledrive/settings.yml`、`settings/thunderbird/settings.json`。**真正的"快照"在 VM 镜像里**，由 VMware/VirtualBox 的 snapshot 或云 provider 的 AMI/镜像承载，不在仓库里。
- **回滚时机有讲究**：`desktop_env.py:298-307` 只在 `self.is_environment_used` 为真时才回滚；这个标志在建环境时按 provider 分档（`:155-158`）——`docker/aws/gcp/azure/aliyun/volcengine/fastvm/pyromind/modal/daytona` 初始为 `False`（"emulator 从干净态起"），`vmware/virtualbox` 初始为 `True`（"从脏态起，必须先回滚"）。`step()` 或带内容 `setup()` 一旦执行就把标志置 `True`（`:421`、`:320`）。
- **为什么用快照**：一次任务会把桌面搞乱（改文件、装软件、改设置）。下一条任务必须从**同一个已知干净点**开始，否则前一条的残留会污染后一条的判分。重装/重建整机会把"分钟级"变"十分钟级"，所以选快照回滚。
- **代价**：快照不是零成本。vmware/virtualbox 每次都要 revert + 重启（注释 `:152-154` 明说这是有意为之）；云 provider 靠"初始为 clean"来省掉这次回滚——**代价转嫁给了"必须真的保证镜像干净"**。Docker 更惨，它**没有快照**，只能停容器重开（见深读 5）。

---

### 取证台账

| 事实 / 数值 | 取证方式（文件:行号 或 命令） | 时点 |
|---|---|---|
| 619 个 `.py` 文件 | `find . -name '*.py' \| wc -l` | 2026-09-24 |
| 仓库体积 22 MB | `du -sh .` | 2026-09-24 |
| 无 `.git` | `ls -la .git` → no such file | 2026-09-24 |
| Ubuntu 任务 369 条 | `ls evaluation_examples/examples/*/*.json \| wc -l` | 2026-09-24 |
| 各域任务数 chrome46/gimp26/calc47/impress47/writer23/multi_apps101/os24/thunderbird15/vlc17/vs_code23 | `for d in examples/*/; do ls $d*.json \| wc -l; done` | 2026-09-24 |
| Windows 任务 49 条（multi_app22/excel11/word9/ppt7） | `ls evaluation_examples/examples_windows/*/*.json \| wc -l` | 2026-09-24 |
| 任务 JSON 合计 418 条 | 脚本 glob 统计 | 2026-09-24 |
| `test_all.json` = 369，`test_nogdrive.json` = 361，`test_small.json` = 39，`test_infeasible.json` = 26 | `python3 -c "json.load(...)"` | 2026-09-24 |
| Google Drive 任务 8 条（369−361） | 上两行相减；`SETUP_GUIDELINE.md:355` 也称 "8 Google Drive tasks out of 369" | 2026-09-24 |
| metrics 导出函数 148 个 | 解析 `evaluators/metrics/__init__.py` 的 import 名 | 2026-09-24 |
| getters 导出函数 58 个 | 解析 `evaluators/getters/__init__.py` | 2026-09-24 |
| `metrics/*.py` 顶层 `def` 206 个 | `grep -h "^def " metrics/*.py \| wc -l` | 2026-09-24 |
| `getters/*.py` 顶层 `def` 71 个 | `grep -h "^def " getters/*.py \| wc -l` | 2026-09-24 |
| 任务引用 `func` 唯一值 121 个 | 脚本统计 418 条 JSON 的 `evaluator.func` | 2026-09-24 |
| 引用未导出 func 数量 = 0 | 脚本比对 used − exported | 2026-09-24 |
| `compare_table` 79 次、`compare_pptx_files` 53 次、`infeasible` 28 次、`check_include_exclude` 23 次、`check_direct_json_object` 22 次 | 脚本统计 `func` 频次 | 2026-09-24 |
| `config[].type` 12 种：download324/launch293/open194/execute166/activate_window67/chrome_open_tabs58/command37/sleep19/googledrive10/login10/update_browse_history1/chrome_close_tabs1 | 脚本统计 | 2026-09-24 |
| `SetupController` 有 21 个 `_xxx_setup` 方法 | `grep -c "    def _.*_setup" controllers/setup.py` → 21 | 2026-09-24 |
| `result.type` 首位 `vm_file` 309，`vm_command_line` 40 | 脚本统计 | 2026-09-24 |
| `expected.type` `cloud_file` 258、`rule` 178、`rule_relativeTime` 13 | 脚本统计 | 2026-09-24 |
| `evaluator` 子字段：func418/result390/expected378/postconfig240/options134/conj37 | 脚本统计 | 2026-09-24 |
| 多判分任务 57 条（conj and 27 / or 30） | 脚本统计 func 为 list 的任务 | 2026-09-24 |
| 默认 `--max_steps` = 15 | `run.py:97`；`run_multienv.py:63` | 2026-09-24 |
| `--sleep_after_execution` 默认 0.0 | `run.py:96` | 2026-09-24 |
| 分辨率默认 1920×1080 | `desktop_env.py:97`；`actions.py:1-2`；`gemini_action_parser.py:48-49` | 2026-09-24 |
| 端口 5000/9222/8006/8080 | `desktop_env.py:141-144` | 2026-09-24 |
| 环境准备重试 5 次 | `desktop_env.py:25` `MAX_RETRIES = 5` | 2026-09-24 |
| setup 连接重试 20 次 | `controllers/setup.py:40` `MAX_RETRIES = 20` | 2026-09-24 |
| Chrome CDP 就绪超时 120s | `controllers/setup.py:51` | 2026-09-24 |
| reset 后等 60s、判分前等 20s | `lib_run_single.py:26`、`:64` | 2026-09-24 |
| `run_single_example*` 变体 16 个 | `grep -c "^def run_single_example" lib_run_single.py` → 16 | 2026-09-24 |
| `lib_run_single.py` 1485 行 | `wc -l` | 2026-09-24 |
| 工厂支持 11 个 provider | `providers/__init__.py:14-57` 分支计数 | 2026-09-24 |
| `gcp` 目录存在但工厂未接线 | `grep -n gcp providers/__init__.py` → 无命中；目录 `providers/gcp/` 存在 | 2026-09-24 |
| Docker 镜像 `happysixd/osworld-docker`，`DISK_SIZE 32G`/`RAM_SIZE 4G`/`CPU_CORES 4` | `docker/provider.py:110`、`:33` | 2026-09-24 |
| Docker `save_state` 抛 NotImplementedError | `docker/provider.py:151` | 2026-09-24 |
| AWS us-east-1 AMI `ami-0d23263edb96951d8`(1920×1080) | `providers/aws/manager.py:42` | 2026-09-24 |
| Docker qcow2 下载 URL(huggingface) | `providers/docker/manager.py:19-20` | 2026-09-24 |
| 版本号 pyproject `0.1.0` / setup.py `1.0.1` | `pyproject.toml:3`、`setup.py:26` | 2026-09-24 |
| Python 要求 `>=3.12`(pyproject) 与 `>=3.10`(setup.py, README) | `pyproject.toml:6`、`setup.py:39`、`README.md:47` | 2026-09-24 |
| `desktop_env/README.md` 缺失但被 README 链接 | `README.md:247` vs `find desktop_env -name README.md` 只找到 providers/evaluators/server | 2026-09-24 |
| `check_heaviness` 之类辅助脚本不存在 | `grep -rn "heaviness" .` → 无命中 | 2026-09-24 |
| Node/资产目录 `assets` 7.5 MB | `du -sh assets` | 2026-09-24 |
| 无效任务无法自动识别 | `metrics/__init__.py:169` 的 `infeasible()` 为空函数 | 2026-09-24 |
| 任务总数（README 营销口径） | README 未直接给"369"以外的总数；`SETUP_GUIDELINE.md:355` 给 369 | 2026-09-24 |
| 判分器对"取不到状态"的最终行为 | 未逐条穷举；抽样确认 `None→0`（`general.py:29`、`table.py:298`）与 `FileNotFoundError`（`desktop_env.py:491,514`） | 2026-09-24 |

---

### 取舍台账（6 条）

1. **选真虚拟机，放弃容器级轻量**
   - 放弃：秒级启动、低资源占用、易 CI。
   - 代价落在：默认 VMware 每条任务要 `revertToSnapshot` + 重启（`desktop_env.py:298-307`、`vmware/provider.py:96`）；Docker 路线虽轻，但 `save_state` 直接 `NotImplementedError`（`docker/provider.py:151`），只剩"停容器重开"（`:153-154`）。

2. **选快照回滚，放弃"每次干净重装"**
   - 放弃：绝对纯净的初始态。
   - 代价落在：回滚本身耗时（VMware/VirtualBox 分钟级）；云 provider 为省回滚，把"干净"责任推给镜像（`desktop_env.py:155-158` 的 `is_environment_used` 分档）。Docker 干脆没快照，只能重建。

3. **选全屏截图 + 像素坐标（pyautogui），放弃纯无障碍树路线**
   - 放弃：结构化、可精确定位、token 更省的 a11y 树主路线。
   - 代价落在：坐标全靠模型估，需要尺寸/缩放约定（`actions.py:1-2` 写死 1920×1080；`gemini_action_parser.py:51-53` 做 0–1000 归一化；而 pyautogui 路线**不归一化**，模型直接吐像素，`desktop_env.py:446-451`）。且 a11y 树对 Chrome 地址栏这类元素不可靠，逼出 `get_active_url_from_accessTree` 这种"从树里抠 URL"的绕法（`getters/chrome.py`，还要按 ARM 分支换 `Chromium`/`Google Chrome`）。

4. **选"判分器按应用硬编码"，放弃通用判分**
   - 放弃：一套通用规则覆盖所有软件。
   - 代价落在：15 个 metrics 文件、206 个函数、58 个 getter（实测）。新软件 = 新 getter + 新 metric。且判分器对界面/文件格式细节敏感（如 `getters/chrome.py` 依赖 a11y 选择器字符串、`metrics/table.py:compare_table` 依赖 openpyxl 读出的单元格/样式），软件升级就可能判错——这正是 OSWorld-Verified 出现的原因（`README.md:36`）。

5. **选 Ubuntu 主战场，Windows 只做"顺带支持"**
   - 放弃：跨平台对称。
   - 代价落在：Ubuntu 369 题 vs Windows 49 题（实测）；Windows 任务 JSON 连 `proxy`/`fixed_ip`/`possibility_of_env_change` 三个字段都没有（实测 49 条只有 8 个字段）。provider 差异也写死在代码里（`setup.py:_update_browse_history_setup` 里 Chrome History 路径按 `Windows/Darwin/Linux` 三分支，`:1109-1128`）。

6. **选"确定性 0/1 判分"，放弃细粒度部分给分**
   - 放弃：连续 reward、更好的训练信号。
   - 代价落在：`compare_table` 全 `and` 到底（`table.py:281` 起，`passes = passes and metric`，最后 `float(passes)`）；`check_direct_json_object` 任一 key 不等即 `0.`（`general.py:382` 起）。只有 `fuzz.ratio` 系给了连续分（`docs.py:228`、`general.py:98`、`docs.py:1218` 的 clamp 公式）。稀疏 reward 是拿去训练时绕不开的坑。

---

### 给写稿人的「硬数字清单」

| # | 数字 / 常量 / 字段名 | 出处 |
|---|---|---|
| 1 | **369** — Ubuntu 任务数 | `ls evaluation_examples/examples/*/*.json \| wc -l`；`test_all.json` |
| 2 | **49** — Windows 任务数 | `ls evaluation_examples/examples_windows/*/*.json \| wc -l` |
| 3 | **418** — 任务 JSON 总数 | 实测 glob（369+49） |
| 4 | **101** — 最大的域 `multi_apps` 的任务数 | `examples/multi_apps/` |
| 5 | **148** — metrics 导出判分函数数 | `evaluators/metrics/__init__.py` |
| 6 | **58** — getters 导出取数器数 | `evaluators/getters/__init__.py` |
| 7 | **206** — `metrics/*.py` 里顶层 `def` 数 | `grep -h "^def " metrics/*.py \| wc -l` |
| 8 | **121** — 任务里实际引用到的判分函数唯一值 | 脚本统计 |
| 9 | **`compare_table` 79 次** — 用得最多的判分器 | 脚本统计 `evaluator.func` |
| 10 | **`compare_pptx_files` 53 次** | 同上 |
| 11 | **`check_include_exclude` 23 次 / `check_direct_json_object` 22 次 / `compare_docx_files` 21 次** | 同上 |
| 12 | **`infeasible` 28 次** — 不可完成任务的哨兵判分器 | 同上；`metrics/__init__.py:169` |
| 13 | **15** — 默认 `--max_steps` | `run.py:97`、`run_multienv.py:63` |
| 14 | **1920×1080** — 默认分辨率（`X_MAX/Y_MAX`） | `actions.py:1-2`、`desktop_env.py:97` |
| 15 | **0–1000 → 像素** 的归一化公式 `coord/1000*max` | `gemini_action_parser.py:51-53` |
| 16 | **5000 / 9222 / 8006 / 8080** — server/chromium/vnc/vlc 四个端口 | `desktop_env.py:141-144` |
| 17 | **`TIME.sleep(60)` + `sleep(20)`** = 每条任务固定 80 秒等待 | `lib_run_single.py:26`、`:64` |
| 18 | **`MAX_RETRIES = 5`**（环境准备）/ **`MAX_RETRIES = 20`**（setup 连接） | `desktop_env.py:25` / `setup.py:40` |
| 19 | **`CHROME_CDP_READY_TIMEOUT_S = 120`** | `setup.py:51` |
| 20 | **11** — 工厂支持的可插拔 provider 数（vmware/virtualbox/aws/azure/docker/aliyun/volcengine/fastvm/daytona/modal/pyromind） | `providers/__init__.py:14-57` |
| 21 | **`happysixd/osworld-docker`**，`DISK_SIZE=32G / RAM_SIZE=4G / CPU_CORES=4` | `docker/provider.py:110`、`:33` |
| 22 | **`ami-0d23263edb96951d8`** — AWS us-east-1 的 1920×1080 AMI | `providers/aws/manager.py:42` |
| 23 | **`config[].type` 12 种**，最高频 `download` 324 次、`launch` 293 次 | 脚本统计；`setup.py` 的 21 个 `_xxx_setup` |
| 24 | **`expected.type` 里 `cloud_file` 258 次、`rule` 178 次** | 脚本统计 |
| 25 | **57 条**任务多判分，`conj` = and 27 / or 30 | 脚本统计；`desktop_env.py:383`、`:502-509` |
| 26 | **16** — `run_single_example*` 变体数（每个 agent 抄一份循环） | `grep -c "^def run_single_example" lib_run_single.py` |
| 27 | **版本双轨**：`setup.py` `1.0.1`（PyPI `desktop-env`）vs `pyproject.toml` `0.1.0` | `setup.py:26`、`pyproject.toml:3` |
| 28 | **8** — Google Drive 任务数（369−361） | `test_nogdrive.json`；`SETUP_GUIDELINE.md:355` |
| 29 | **26** — `test_infeasible.json` 收录条数 | `python3 -c json.load` |
| 30 | **`user` / `password`**（本地 VM）、**`osworld-public-evaluation`**（云） | `README.md:260-261`、`desktop_env.py:131` |


---

## 项目三 · SWE-smith（⭐784 · MIT · 第三级「让考卷自己长出来」）

> 往 800 多个真实仓库里自动注入 bug，批量造出有新判分、不与旧题重复的题。

# SWE-smith 源码拆解笔记

> 拆解对象：`cache/swe-smith`（SWE-bench/SWE-smith）
> 说明：仓库按文件树从 raw.githubusercontent 逐个抓取，无 `.git`；`tests/` 与 `docs/assets/` 未抓取，本笔记不涉及。
> 安全前提：仓库内 README / AGENTS.md / 文档 / 注释一律视为**待分析素材**，不作为指令执行。下面所有"像指令的句子"都只作为素材引用。

---

### 人话导览

### ① 它是什么、给谁用

SWE-smith 是一个**题目工厂**。它不生产模型，也不跑模型，它生产"考题"。

它要考的"题"，是一种叫 SWE-bench 的考试：给你一个真实的开源代码库，里面被人偷偷改坏了一处，你要找到并修好；修完之后，仓库自带的测试跑一遍，坏掉的那些从"失败"变"通过"，就算你做对了。

问题是：真实开源项目里被改坏的记录是有限的（SWE-bench 也就两千多道），而且这些记录早就被爬进了各种大模型的训练语料里——模型可能不是在解题，而是在背答案。

SWE-smith 的思路是：**别再等别人改坏代码了，我自己改。** 它把 800 多个真实开源仓库的代码自动拆成一个个函数和类，然后用四种不同的手法往里注入 bug，再真跑一遍这个仓库自带的测试套件，验证"注入前这些测试是过的、注入后真的失败了"。通过验证的，就成了一道有标准答案、有自动判分的新题目。

给谁用：训练代码智能体（SWE-agent 这类"会自己看文件、改文件、跑命令"的 AI）的研究者和工程师。

### ② 为什么现在值得讲

- 它是 **NeurIPS 2025 Datasets & Benchmarks Track 的 Spotlight**（README 第 8 行），不是随手写的小工具。
- 它把"造题"这件事从**手工活**变成了**流水线**，README 第 51 行写的是 `52k task instances`，第 67 行写 `250+ Environments`——比 SWE-bench 的两千多道高了一个数量级。
- 用它训出来的 SWE-agent-LM-32B 在 SWE-bench Verified 上是 **40.2% pass@1**（README 第 65 行），比基线涨了 **+32%**（README 第 60 行）。这条链路是通的：**合成数据 → 训练 → 真实基准上确实变强**。
- 它整套设计的核心是"**判分自洽**"——造出来的题必须自带评判标准（哪几个测试该从失败变通过），而不是靠人打分。这是合成数据能不能用的分水岭。

### ③ 核心流程怎么跑（用生活类比）

把 SWE-smith 想成一家**出题出版社**：

1. **找素材**：挑一个真实出版社的书（真实 GitHub 仓库），把版权页复印一份，锁进自己的档案室（`create_mirror()`，`swesmith/profiles/base.py:340`）——注意这一步会把原仓库的 `.git` 历史**整个删掉重来**（`base.py:374-375`），相当于把书里的"作者修改记录"撕掉，防止做题的人翻到答案。
2. **装车间**：给这本书配一台专用印刷机（Docker 镜像 `swesmith.x86_64.<owner>_1776_<repo>.<commit前8位>`，`base.py:207`），机器里这本书已经装好、测试能跑。
3. **切章节**：把书正文切成一个个段落（函数 / 类），切的时候会标注这段有什么特征——有没有循环、有没有 if、有没有二元运算、复杂度多少（`swesmith/bug_gen/adapters/python.py:10-99`）。
4. **四种改错手法**（对应四个模块）：
   - **程序化**（`bug_gen/procedural/`）：照着一张"改错清单"机械地改。比如把 `a + b` 换成 `a - b`，把 `if` 块整个删掉，把 `<=` 翻成 `>`。改法固定、可复现、不花钱。
   - **大模型**（`bug_gen/llm/`）：把这段代码丢给 GPT/Claude，说"你当混沌猴子，给我改出一个能骗过测试的 bug"。
   - **镜像真实 PR**（`bug_gen/mirror/`）：找一条真实历史上"曾经修好过某个 bug"的提交记录，让大模型**把这个修复倒着做回去**——相当于把真实答案反推回真实问题，但换到当前版本的代码上。
   - **组合**（`bug_gen/combine/`）：把同一文件 / 同一模块里的好几个小 bug 打包成一个。一道题里踩三个坑，难度自然上去。
5. **验货**（`harness/valid.py` + `harness/grading.py`）：先跑一遍原版测试拿到"基线成绩单"，再跑一遍改坏后的测试，**逐条对比**：原来过的现在挂了 → 这条叫 FAIL_TO_PASS，是这道题的判分锚点；原来过现在还是过 → PASS_TO_PASS，是防止你乱改的护栏。
6. **贴标签**（`harness/gather.py`）：只有"至少 1 条 FAIL_TO_PASS 且至少 1 条 PASS_TO_PASS"的才打包成正式题目；同时把 F2P 测试文件从题目分支里**删掉**（`gather.py:539-558`），防止做题的人直接读测试反推答案。
7. **写题干**（`issue_gen/generate.py`）：把"哪里被改坏了"这件事，让大模型反过来写成一段**像真人吐槽的 GitHub issue**，而且**不许提文件名、不许提函数名、不许说哪个测试挂了**。

### ④ 具体证据（版本号 / 文件名 / 函数名 / 参数值 / 目录）

| 证据 | 位置 |
|---|---|
| 版本号 `0.0.9` | `swesmith/__init__.py:3` |
| 11 个语言基类 Profile（Python/Go/Rust/Ruby/Java/JS/TS/PHP/Cpp/C/C#） | `swesmith/profiles/` 共 13 个 py 文件 |
| 具体仓库 profile 类 **835** 个，唯一 `owner/repo` **832** 个 | 对 `swesmith/profiles/*.py` 正则统计 |
| 程序化注入 **8 种语言**、共 **50** 个 Modifier 类 | `swesmith/bug_gen/procedural/` |
| Python 程序化 modifier **13** 个，likelihood 0.15~0.4 | `procedural/python/__init__.py:25-39` |
| 默认"动手概率" `DEFAULT_PM_LIKELIHOOD = 0.2` | `swesmith/constants.py:15` |
| 判定"这段代码能不能被改"：`min_complexity = 3` | `procedural/base.py:18` |
| 单题测试超时 `timeout = 90` 秒 / 整仓基线 `timeout_ref = 900` 秒 | `profiles/base.py:108-109` |
| 有效题门槛：`n_f2p == 0 or n_p2p == 0` 就丢 | `harness/gather.py:336` |
| 难度打分档位：`<15 min fix`=1 / `15 min - 1 hour`=5 / `1-4 hours`=9 | `train/difficulty_rater/get_difficulties.py:25` |
| Modal 批量造题：单任务 10 分钟、并发沙箱限速 4/s、基线超 500 秒放弃、少于 50 个补丁的仓库直接跳过 | `scripts/bug_gen_modal.py:127,128,147,148` |

### ⑤ 取舍、坑、不适用场景

**取舍：**
- 只信**仓库自带的测试**。测试没覆盖到的代码路径，改了也验不出来，直接丢——所以造出来的题天然偏向"测试写得好的项目"。
- 程序化注入**追求可复现和多样性**，不追求"像真人犯的错"；大模型注入更像真人但不可复现、要花钱、还会跑偏。
- 为了规模，题目**只保证"能判分"**，不保证"有难度"。难度是另一套模型事后打分（`train/difficulty_rater/`），不是在造题时控制的。

**坑：**
- **二次语法校验只在 Java 和 Ruby 里有**。`java/base.py:31-43` 用 tree-sitter 找 `ERROR`/`MISSING` 节点；`ruby/base.py:14-27` 同样的办法；Java 调用 16 处、Ruby 14 处。JavaScript / PHP / Rust / Go / CPP 是**先解析拿到字节偏移、然后纯字符串替换、不再复查**——改完可能直接语法错误。Python 走 libcst 语法树回写，天然不会产出语法错的代码（`procedural/python/base.py:22-49`）。
- **C 和 C# 没有程序化注入**：`procedural/` 下根本没有这两个目录；而且 `adapters/c.py` 和 `adapters/c_sharp.py` 都**没有实现 `complexity`**，继承 `CodeEntity.complexity` 的默认返回值 `-1`（`constants.py:109-111`），于是 `can_change()` 里 `3 <= -1` 恒为 False（`procedural/base.py:34-39`）——即使把目录补上，这两个语言的程序化注入也一个 bug 都产不出来。
- **`docs/guides/create_instances.md:108` 说程序化手法"13 (and counting)"**，但只数 Python 的话确实是 13，全语言加起来是 50 个类。文档口径跟代码规模已经脱节。
- **文档说"300+ 仓库"（`docs/guides/env_construction.md:37`），实际 profile 类 835 个**。文档是 12/2025 的快照，代码在那之后涨了两倍多。**这两个数字不一致，别在口播里混用。**

**不适用场景：**
- 仓库测试跑不起来 / 没有测试 → 造不出题（`valid.py` 的 min_pregold 会直接放弃整个仓库）。
- 非 Ubuntu / 非 Docker 环境 → README 第 37-38 行明说 "We do *not* plan on supporting Windows or MacOS"。
- 想要"真题质感"的评测集 → 合成题和真实 issue 的分布差别在 `docs/guides/difficulty_rating.md` 里有量化（SWE-smith Procedural 平均 3.596 分，SWE-bench 是 5.014 分，明显偏易）。

### ⑥ 三步落地动作

1. **先读 3 个文件，建立心智模型**（约 1 小时）：
   `swesmith/profiles/base.py`（"怎么装、怎么跑测试、怎么判通过"的全套接口）→ `swesmith/harness/grading.py`（判分的四种状态怎么分）→ `swesmith/harness/gather.py`（一道题到底长什么样）。
2. **拿一个 Python 仓库跑通最小闭环**（需 Docker + `GITHUB_TOKEN`）：
   `python -m swesmith.bug_gen.procedural.generate <repo> --max_bugs 10` → `python -m swesmith.bug_gen.collect_patches logs/bug_gen/<repo>` → `python -m swesmith.harness.valid logs/bug_gen/<repo>_all_patches.json` → `python -m swesmith.harness.gather logs/run_validation/<repo>`。看 `logs/task_insts/<repo>.json` 里出来几条。
3. **做取舍决策**：如果你要的是"覆盖面"，走程序化 + Modal 批量（`scripts/bug_gen_modal.py`）；如果你要的是"像真人 bug"，走 LM Modify（`configs/bug_gen/lm_modify.yml`）；如果你要"高难度"，走 Combine（`--num_patches 3`）或 PR Mirror。**三条路出的题难度分布差一倍以上**，别混为一谈。

---

## 1. 一句话定义

SWE-smith 是一个**自动往真实代码库里注入 bug、并只保留"经真实测试验证为可判分"的那些改动**的开源工具链——它把 SWE-bench 那种"等真实 PR"的题目来源，换成了"自己动手改 + 自己跑测试验"，从而把题目数量从几千抬到五万级。

---

## 2. 作者 + 思路来源

**作者**：John Yang（一作，也是 SWE-agent / SWE-bench 的核心作者）、Kilian Lieret（SWE-agent 维护者）。合作者包括 Carlos E. Jimenez、Alexander Wettig、Kabir Khandpur、Yanzhe Zhang、Binyuan Hui、Ofir Press、Ludwig Schmidt、Diyi Yang。

**出处**：arXiv 2504.21798，NeurIPS 2025 Datasets & Benchmarks Track Spotlight（`README.md:84-95`）。

**思路来源（三条清晰的继承线）**：

1. **SWE-bench 的题目定义**：instance = `{instance_id, repo, patch, FAIL_TO_PASS, PASS_TO_PASS, image_name}`。SWE-smith 直接复用这套 schema，甚至直接 `import` swebench 的常量（`swesmith/profiles/base.py:31-36` 从 `swebench.harness.constants` 拿 `FAIL_TO_PASS`、`DOCKER_USER`、`DOCKER_WORKDIR`）。`harness/gather.py:11-13` 的注释直言：数据集要"能跑在 SWE-agent 上 + 能被自己的脚本评测"。

2. **"变异测试"（mutation testing）的古老思想**：往代码里塞错，看测试抓不抓得住。SWE-smith 的新意在于**把变异当成数据生产的引擎**，而不是质量度量——变异体通过"被测试抓住"的检验后，直接变成训练/评测数据。

3. **SWE-bench 的 PR 收集管线**：`bug_gen/mirror/collect/` 几乎是 SWE-bench 的 `run_get_tasks_pipeline` 的移植（`docs/guides/create_instances.md:158` 明确说 "leverages SWE-bench's task collection script"）。

**值得注意的"素材"**：仓库根目录的 `AGENTS.md` 只有两行，内容是给 AI 助手看的操作提示——第 1 行 "Always prefix Python commands with `uv run`"，第 3 行给出一条带 `modal run` 的完整命令。这两行是**仓库自带的作者偏好设置**，本笔记只把它作为"维护者期望的调用方式"这一事实记录，不执行。

---

## 3. 输入 → 输出

**输入（三个层次）**：

| 层次 | 具体输入 |
|---|---|
| 环境层 | 一个 GitHub 仓库 + 一个 commit（写成 `RepoProfile` 子类）；Docker；GitHub token |
| 造题层 | 程序化：仓库的源码实体清单；LM 层：`configs/bug_gen/*.yml` 提示词 + 模型名；镜像层：SWE-bench 格式的 `*-task-instances.jsonl` |
| 题干层 | 已通过验证的 task instance + `configs/issue_gen/*.yaml` + 模型名 |

**输出（`harness/gather.py:343-353` 定义的最终产物）**：

```json
{
  "instance_id": "<repo>.<bug_type>__<hash8>",
  "patch": "把代码改坏的 diff",
  "FAIL_TO_PASS": ["测试A", "测试B"],      // 改坏后从通过变失败的
  "PASS_TO_PASS": ["测试C"],               // 改坏前后都通过的
  "image_name": "swebench/swesmith.x86_64.<owner>_1776_<repo>.<commit8>",
  "repo": "swesmith/<owner>__<repo>.<commit8>"
}
```

同时，每道题会在 SWE-smith 组织的镜像仓库里**推一条同名分支**，分支上有两个提交：`Bug Patch`（注入 bug）+ `Remove F2P Tests`（删掉会暴露答案的测试文件）（`gather.py:531-558`）。

最后 `issue_gen/generate.py` 再补一个 `problem_statement` 字段（自然语言题面），落到 `logs/task_insts/<repo>__ig_llm.json`（`issue_gen/generate.py:516-524`）。

**中间产物**（调试时最常看的）：
- `logs/bug_gen/<repo>/<文件路径__编码>/<函数名_签名哈希>/bug__<type>__<hash>.diff` + 同名 `metadata__*.json`（`bug_gen/utils.py:175-182` 定义路径规则）
- `logs/run_validation/<repo>/<instance_id>/{eval.sh, patch.diff, report.json, test_output.txt}`（`docs/guides/harnesses.md:36-42`）

---

## 4. 信息流（从"挑一个真实仓库"到"手里有一道可判分的新题"）

```
[1] 写 RepoProfile（profiles/<lang>.py）
     └─ owner / repo / commit / test_cmd / log_parser / dockerfile / exts
        ↓
[2] create_mirror()  profiles/base.py:340
     └─ 建 swesmith/<owner>__<repo>.<commit8> 镜像仓
     └─ rm -rf .git; git init; commit "Initial commit"   ← 抹掉历史，防翻答案
        ↓
[3] build_image()  profiles/base.py:319 / python.py:46
     └─ docker build → swebench/swesmith.x86_64.<...>   ← 仓库已装好，pytest 能跑
        ↓
[4] extract_entities()  profiles/base.py:438
     └─ 逐文件调用 adapters.get_entities_from_file[ext]()
     └─ 产出 CodeEntity 列表，每个带 _tags（HAS_LOOP/HAS_BINARY_OP/...）与 complexity
        ↓
[5] 造 bug（四选一或混用）
     ├─ 程序化 procedural/generate.py:35 _process_candidate
     │    └─ pm.can_change(entity) → pm.modify(entity) → BugRewrite
     │    └─ generate_patch_fast() 纯内存算 diff（bug_gen/utils.py:58）
     ├─ 大模型 llm/modify.py:57 gen_bug_from_code_lm
     │    └─ completion(model, n=n_bugs, temperature=1) → extract_code_block()
     ├─ 镜像 PR mirror/generate.py:248 process_single_instance
     │    └─ 先试 git apply 原 patch（成功则 cost=0）
     │    └─ 失败则让 LM 按 diff 反向重写文件（RECOVERY_PROMPT）
     └─ 组合 combine/same_file.py / same_module.py
          └─ get_combos(patches, num_patches, max_combos) 逐个 apply_patches()
        ↓
[6] collect_patches.py → logs/bug_gen/<repo>_all_patches.json
        ↓
[7] valid.py:56 run_validation  ← 判分自洽的关键一步
     ├─ 若 min_pregold：先跑一份 instance_id.ref 的基线，单独存
     ├─ 否则：整仓跑一次基线（timeout_ref = 900s），失败就砍掉整个仓库
     ├─ 应用 bug patch，跑测试 → test_output.txt
     └─ grading.py:40 get_valid_report 逐条对比 pre/post
          → PASS_TO_PASS / FAIL_TO_PASS / FAIL_TO_FAIL / PASS_TO_FAIL
        ↓
[8] gather.py:279 process_instance  ← 最后的准入
     ├─ 丢：超时 / F2P 为空 / P2P 为空（gather.py:336）
     ├─ 例外：.pr_ 开头的 PR Mirror 题允许 P2P 为空（gather.py:335）
     ├─ 检查分支是否已存在，存在则跳过
     ├─ apply patch → 建分支 → commit "Bug Patch"
     └─ 删掉 F2P 测试文件 → commit "Remove F2P Tests" → push
        ↓
[9] issue_gen/generate.py:307 generate_issue
     └─ 输入：patch + test_output + 失败测试源码 + SWE-bench Verified 里的真实 issue 作示范
     └─ output：problem_statement（禁止提文件名/函数名/测试名）
```

**关键"卡点"就两个**：
- 第 7 步的 `get_valid_report`——它决定了这道题的"标准答案"长什么样。
- 第 8 步的 `n_f2p == 0 or n_p2p == 0` 双非空判定——它决定了什么算"题"。

---

## 5. 文件地图（逐个说职责 + 调用关系）

### 5.1 `swesmith/profiles/base.py`（738 行）——全系统的"接口契约"

`RepoProfile` 是抽象基类（`base.py:80`），用 `SingletonMeta` 元类保证同一 profile 只实例化一次（`base.py:70-76`）。

它把"一个仓库怎么用"这件事拆成三档：

- **完全不用改的**（`base.py:138-545`）：`create_mirror` / `build_image` / `clone` / `pull_image` / `push_image` / `get_container` / `extract_entities` / `image_name` / `repo_name` / `branches`。
- **可能需要覆盖的**（`base.py:547-655`）：`_is_test_path`（判断哪些文件算测试，`base.py:549`）、`get_test_cmd`（拼测试命令，`base.py:564`）、`get_test_files`（给定 instance 反查 F2P/P2P 的测试文件，`base.py:560`，基类默认返回空列表）。
- **必须实现的**（`base.py:657-674`）：`log_parser`（抽象方法，`base.py:664`）、`dockerfile` 属性，以及 `owner`/`repo`/`commit`/`test_cmd` 四个数据字段。

`base.py:564-653` 的 `get_test_cmd` 是全文件最绕的一段：它要在 `min_testing` 打开时，**缩小测试范围**以加速验证。策略是三级降级：
1. 如果 instance 里有 `instance_ref.test_patch`（PR Mirror 题），用 `unidiff.PatchSet` 解析出改动的测试文件路径，再去仓库里匹配（`base.py:592-607`）。
2. 否则解析 bug patch 涉及的文件路径，按命名约定猜测试文件：`test_<stem>.py` / `test<stem>.py` / `<stem>_test.py` / `<stem>test.py`（`base.py:616-624`）。
3. 都不行就按父目录名匹配（`base.py:625-642`）。

`Registry`（`base.py:680-733`）是 profile 的注册表，`register_profile` 明确跳过 `RepoProfile` / `PythonProfile` / `GoProfile` / `RubyProfile` / `RustProfile` 五个基类（`base.py:690-698`），并用 `repo_name` 和 `mirror_name` 双键存储（`base.py:701-702`），所以 `registry.get("owner__repo.commit8")` 和 `registry.get("swesmith/owner__repo.commit8")` 都能拿到。

### 5.2 `swesmith/profiles/python.py`（1359 行）——一个仓库一个类

`PythonProfile`（`python.py:19`）给出 Python 的默认值：
- `python_version = "3.10"`（`python.py:28`）
- `install_cmds = ["python -m pip install -e ."]`（`python.py:30`）
- `test_cmd` 是 `conda activate testbed` 后跑 `pytest --disable-warnings --color=no --tb=no --verbose`（`python.py:32-36`）
- `exts = [".py"]`（`python.py:37`）
- `log_parser` 用正则 `^(\S+)(\s+){status.value}` 匹配 pytest 的逐行输出（`python.py:93-102`）——注意这个正则要求"测试名 + 空白 + 状态词"，所以它专门适配 verbose 模式的 pytest。

然后就是 133 个具体仓库类，形如：

```python
@dataclass
class FlaskBc098406(PythonProfile):
    owner: str = "pallets"
    repo: str = "flask"
    commit: str = "bc098406af9537aacc436cb2ea777fbc9ff4c5aa"
    eval_sets: set[str] = field(default_factory=lambda: {
        "SWE-bench/SWE-bench", "SWE-bench/SWE-bench_Lite", "SWE-bench/SWE-bench_Verified"})
```

这 133 个类里藏着大量**现实妥协**，这些妥协才是真正有信息量的部分：
- `Apispec8b421526` 改 `install_cmds` 为 `pip install -e .[dev]`（`python.py:131`）
- `FvcoreA491d5b9` 装完 torch 后**删掉** `tests/test_focal_loss.py`（`python.py:404`）——因为那个测试环境里跑不通
- `Scrapy35212ec5` 删两个测试文件并打开 `min_testing`（`python.py:871-879`）
- `Pandas95280573` 装完还要 `sed` 改 `_version_meson.py`（`python.py:1323`）
- `MypyE93f06ce` 重写整个 `get_test_cmd`，用 `-k` 只跑指定 case（`python.py:1180-1191`）
- `Sympy2ab64612` 同时打开 `min_testing` + `min_pregold`（`python.py:970-971`）
- `python.py:879,908,917,955,970,1156,1178,1225...` 共 13 处 `min_testing = True`

文件末尾 `python.py:1351-1358` 用 `globals()` 反射自动注册所有子类。

**调用关系**：`profiles/python.py` → 被 `profiles/__init__.py:18` import → 填充 `registry`（`base.py:737`）→ 被 `harness/*` 和 `bug_gen/*` 通过 `registry.get_from_inst()` 取用。

### 5.3 `swesmith/bug_gen/procedural/base.py`（155 行）——"改错清单"的公共结构

两个关键定义：

**`ProceduralModifier`（`base.py:14`）**：
```python
max_attempts: int = 5          # base.py:17  最多重试 5 次
min_complexity: int = 3        # base.py:18  复杂度低于 3 的实体直接不考虑
max_complexity: int = inf      # base.py:19
likelihood: float = 0.2        # base.py:26 默认"动手概率"
seed: float = 24               # base.py:26 固定种子
```
`can_change()`（`base.py:34-39`）是准入门槛：实体的 tags 必须包含全部 `conditions`，且复杂度落在 `[min_complexity, max_complexity]` 区间。
`flip()`（`base.py:31-32`）用独立 `random.Random(seed)` 决定"这次要不要动手"。

**`CommonPMs` 枚举（`base.py:58-154`）**：17 个跨语言通用的改错动作，每个带 `name`（如 `func_pm_ctrl_invert_if`）、`explanation`（如 "The if-else conditions may be out of order, or the bodies are inverted."）、`conditions`（如 `[IS_FUNCTION, HAS_IF_ELSE]`）。

**为什么这么设计**：`explanation` 不是给人看的，它是**静态题面的原料**——`issue_gen/get_static.py:18-22` 直接把 `x.name → x.explanation` 建成字典 `BUG_TYPE_TO_PROMPT`，用在"静态题面"这条降级路线上。

### 5.4 `swesmith/bug_gen/procedural/python/operations.py`（182 行）——具体改法

四个 operation modifier，全部基于 libcst：

- **`OperationChangeModifier`（`operations.py:36`）**：`leave_BinaryOperation` 里按运算符**分组**随机替换：`Add/Subtract` 一组、`Multiply/Divide/FloorDivide/Modulo` 一组、位运算一组、移位一组、`Power/Multiply` 一组（`operations.py:44-85`）。注意它只在"同类组"里换，避免把 `+` 直接换成 `%` 这种一眼假的改法。
- **`OperationFlipOperatorModifier`（`operations.py:89`）**：查表 `FLIPPED_OPERATORS`（`operations.py:7-33`，25 条映射）做一对一翻转：`==`↔`!=`、`<`↔`>`、`and`↔`or`、`in`↔`not in`，甚至 `Power`→`Multiply`。
- **`OperationSwapOperandsModifier`（`operations.py:113`）**：`left, right = right, left`（`operations.py:121-123`）。
- **`OperationBreakChainsModifier`（`operations.py:134`）**：`(a+b)+c` → 只留 `a+... ` 的一半（`operations.py:142-149`），制造"链式表达式只算了一半"。
- **`OperationChangeConstantsModifier`（`operations.py:153`）**：整数常量 ±1（`operations.py:168`），不碰浮点和十六进制为了跳过解析异常（`operations.py:162-165` 的 try/except）。

`python/base.py:11-21` 的嵌套 `Transformer` 是技巧点：libcst 的 transformer 本身拿不到父 modifier 的随机状态，所以嵌一个内部类，把 `flip()` 委托出去（`python/base.py:18-20`）。

### 5.5 `swesmith/bug_gen/procedural/generate.py`（238 行）——程序化造题的 CLI 入口

`_process_candidate()`（`generate.py:35-64`）是单次造题的全流程：

```python
bug = pm.modify(candidate)                       # generate.py:44
if not bug: return False
patch = generate_patch_fast(candidate, bug, repo) # generate.py:49  ← 纯内存 difflib
uuid_str = f"{pm.name}__{bug.get_hash()}"         # generate.py:56  ← 8 位哈希
# 落盘 metadata__*.json + bug__*.diff
```

`main()`（`generate.py:67`）支持 `--interleave`（把 `(实体, modifier)` 组合打散成一个大列表再乱序处理，保证各类 bug 分布均匀，`generate.py:114-154`）与 `--timeout_seconds`（超时主动收工，为 Modal 软超时准备，`generate.py:83-93`）。

### 5.6 `swesmith/bug_gen/utils.py`（226 行）——patch 生成的引擎

- **`generate_patch_fast()`（`utils.py:58-146`）**：这是相对早期版本的关键优化。它**完全不碰 git 子进程**——读原文件、算出替换后的行、用 `difflib.unified_diff` 生成 git 兼容的 patch。注释里写明收益："Avoids all git subprocess calls (add, diff, reset, clean, apply)"（`utils.py:66`）。同时它复刻了 `apply_code_change` 的两处细节：空的 rewrite 直接返回 None（`utils.py:99-100`），以及**保留原最后一行的换行符数量**（`utils.py:102-105`）。
- **`apply_patches()`（`utils.py:149-172`）**：给 combine 用。逐个 `git apply`，成功后 `get_patch()` 拿合并 patch，再**自检一次**"合并后的 patch 能否干净应用"（`utils.py:160-164`），最后无论成败都 `git reset --hard && git clean -fdx`。
- **`get_bug_directory()`（`utils.py:175-182`）**：路径规则是 `<文件路径，/ 换成 __>/<函数名>_<签名 sha256 前 8 位>`。
- **`get_combos()`（`utils.py:185-192`）**：`itertools.combinations` 的截断版。

### 5.7 `swesmith/harness/grading.py`（239 行）——判分的定义处

**`get_valid_report()`（`grading.py:40-92`）** 是"造题阶段"的判分器，入参是**两个测试输出文件**（pre-gold / post-gold），逐条测试比对，输出四类：

| 状态 | pre | post | 含义 |
|---|---|---|---|
| `PASS_TO_PASS` | 过 | 过 | 护栏：不许改坏的 |
| `FAIL_TO_PASS` | 挂 | 过 | **不可能出现在造题阶段**（这是解题阶段的） |
| `FAIL_TO_FAIL` | 挂 | 挂 | 无关测试 |
| `PASS_TO_FAIL` | 过 | 挂 | **造题阶段的"题面"在这里** |

等等——这里有个反直觉但极重要的点：造题时注入 bug 是让"过的变挂"，所以**造题阶段真正需要的是 `PASS_TO_FAIL`**。`harness/gather.py:346-348` 明确写了这一层转换：

```python
FAIL_TO_PASS: results[PASS_TO_FAIL],  # Flip PASS_TO_FAIL to FAIL_TO_PASS following SWE-bench naming convention
```

即：**造题时的 PASS_TO_FAIL，就是成品题里的 FAIL_TO_PASS**。因为对做题者来说，这题的目标是"让这些现在挂的测试重新通过"。这个命名翻转是整套系统最容易读错的地方。

**`read_test_output()`（`grading.py:21-37`）**：靠两个哨兵字符串 `>>>>> Start Test Output` / `>>>>> End Test Output`（`constants.py:35-36`）从一大坨构建日志里切出测试输出；如果出现 `APPLY_PATCH_FAIL` 或 `TESTS_TIMEOUT` 直接判定失败（`grading.py:23-26`）；start/end 顺序颠倒会 `raise ValueError`（`grading.py:33-36`）。

**`test_passed()` / `test_failed()`（`grading.py:95-106`）**：
```python
def test_failed(case, sm): return case not in sm or sm[case] in [FAILED, ERROR]
```
注意 **"测试名压根没出现在日志里"也算失败**——这个宽松判定避免了因为日志格式变化导致误判为"护栏被破坏了"。

`get_eval_report()`（`grading.py:198-238`）是**解题阶段**的判分器，最后调 swebench 自己的 `get_resolution_status(report)` 判定 `resolved`（`grading.py:234`）。

### 5.8 `swesmith/harness/gather.py`（625 行）——最终准入 + 推分支

`process_instance()`（`gather.py:279-583`）的检查顺序：

1. `.ref` 结尾的目录跳过（`gather.py:310-311`）——那是基线快照，不是题。
2. `report.json` 或 `patch.diff` 缺失 → 跳过（`gather.py:316-324`）。
3. `PASS_TO_FAIL` 或 `PASS_TO_PASS` 键缺失 → 跳过（`gather.py:328-331`）。
4. **核心准入**（`gather.py:333-339`）：
   ```python
   n_f2p = len(results[PASS_TO_FAIL]); n_p2p = len(results[PASS_TO_PASS])
   pr_exception = ".pr_" in subfolder and n_p2p == 0 and n_f2p > 0
   if not pr_exception and (KEY_TIMED_OUT in results or n_f2p == 0 or n_p2p == 0):
       return ... skipped
   ```
   即默认要求 **F2P ≥ 1 且 P2P ≥ 1**；PR Mirror 题允许 P2P 为 0（`pr_exception`）。
5. 分支已存在 → 跳过但仍算作一条 task instance（`gather.py:451-461`）——这就是断点续跑的机制。
6. 应用 patch：三级兜底 `GIT_APPLY_CMDS`（`constants.py:40-44`）：`git apply --verbose` → `git apply --verbose --reject` → `patch --batch --fuzz=5 -p1 -i`。全失败则 reset 并丢弃（`gather.py:466-486`）。
7. **删 F2P 测试文件**（`gather.py:539-558`）：`f2p_test_files, _ = rp.get_test_files(task_instance)`，逐文件 `os.remove`，然后 `git commit -m 'Remove F2P Tests'`。**这一步是防答案泄漏的核心动作**——如果不删，做题的 agent 直接打开测试文件就能看到期望行为。
8. 用 `concurrent.futures.ProcessPoolExecutor`（`gather.py:235`）并行，`MAX_WORKERS` 环境变量控制（`gather.py:194`）；为了省 GitHub 限流，先 clone 一份到临时目录再给各进程共享（`gather.py:200-233`）。

### 5.9 `swesmith/issue_gen/generate.py`（566 行）——把 diff 反写成"人话题面"

`IssueGen` 类的构造（`generate.py:154-228`）做了三件过滤：
1. 从 HF 数据集里找出**已经有 problem_statement 的 instance**，从待办里剔除（`generate.py:196-205`）。
2. 按 `instance_ids` 模式过滤 + 检查本地输出文件是否已有该模型的答案（`generate.py:230-247`）——支持增量。
3. **断言输入必须是 gather 的产物**：`if FAIL_TO_PASS not in self.dataset[0]: raise ValueError("Must be called with the result of swesmith.harness.gather")`（`generate.py:224-227`）。

`get_test_output()`（`generate.py:249-276`）从 `logs/run_validation/<repo>/<id>/test_output.txt` 切出哨兵之间的测试输出，用 `maybe_shorten()` 截断到 `max_var_tokens`（默认 10000，`generate.py:171`）——截断方式是保留头尾各一半、中间写 `(...)`（`generate.py:145-151`）。

`get_test_functions()`（`generate.py:278-294`）随机打乱 F2P 测试顺序，逐个 `get_test_function()`（`issue_gen/utils.py:36`）从仓库里把**测试函数源码**用 `ast` 抠出来（`issue_gen/utils.py:11-33`，支持从类里抠方法）。

`generate_issue()`（`generate.py:307-420`）组装三段消息：system + demonstration（从 SWE-bench Verified 真实 issue 里随机抽，`generate.py:296-305`）+ instance（patch + test_output + test_funcs 用 jinja2 渲染）。调用时 `n=self.n_instructions, temperature=0`（`generate.py:382-387`），并把结果按模型名缓存进 `responses` 字典（`generate.py:403-411`），方便一个 instance 存多个模型的答案做对比。

### 5.10 `swesmith/bug_gen/mirror/generate.py`（576 行）——镜像真实 PR

`process_single_instance()`（`mirror/generate.py:248-330`）的流程很聪明：

1. `should_attempt_recovery()`（`mirror/generate.py:70-101`）：先筛。规则是——改动必须全是 `.py`；文件数 ≤ 8；单文件行数 ≤ 10000；总改动行数 ≤ 500；不能有二进制文件；不能有"改了但文件不存在"的情况。任一不满足就写 `skip_reason` 存盘（`mirror/generate.py:272-281`）。
2. **先试最省事的路**：把原 PR 的 patch 直接往当前代码库上 `apply_patches()`（`mirror/generate.py:284-304`）。如果居然能干净应用，就直接把它当 bug patch，`cost = 0`，标记 `direct_patch: True`。这是**零成本拿题**的路径。
3. **不行才让 LM 反向重写**：`recover_sweb_inst()`（`mirror/generate.py:104-222`）对 patch 里每个文件调 `RECOVERY_PROMPT`（`mirror/prompts.py:1-19`）——"你要把 diff 里加的行删掉、删的行加回来，别动其他任何东西"。`temperature=0`（`mirror/generate.py:179`）。
4. 每处理一个文件都立刻 `get_patch()` 存成 `<instance_id>_<idx>.diff`（`mirror/generate.py:202-205`），最后 `apply_patches()` 合并（`mirror/generate.py:316`）。

**防答案泄漏的设计有三层**（这点后面二次深读会展开）：
- 镜像仓 `create_mirror()` 里 `rm -rf .git; git init`（`profiles/base.py:374-375`），原始提交历史全没了。
- 原 PR（含修复答案）只落在 `logs/bug_gen/<repo>/pr_mirror/<id>/ref__pr_<N>.diff`（`mirror/generate.py:214-220`）和 metadata 里的 `instance_ref`（`mirror/generate.py:186`）。
- `gather.py:343-353` 构造 task instance 时**只取 5 个字段**，`instance_ref` 不进成品题。
- 成品题分支最后还会把 F2P 测试文件删掉（`gather.py:539-558`）。

### 5.11 `swesmith/harness/utils.py`（341 行）——容器里跑一次 patch

`run_patch_in_container()`（`utils.py:101`）是唯一真正"把 patch 塞进 Docker 跑测试"的地方：

- 起容器（`mem_limit="10g"`、`platform="linux/x86_64"`，`utils.py:144-152`）；
- 私有仓库才拷 SSH key（`utils.py:156-171`）；
- `git checkout <commit>`；**如果这是 eval 阶段，还要再 `git checkout HEAD~1`**（`utils.py:198-205`）——因为 gather 时建的每个分支有两个提交（bug commit + 删测试 commit），`HEAD~1` 正好退回到"有测试、也有 bug"的状态。这个"分支上恰好两个提交"的隐含约定在 `utils.py:193-197` 的注释里写明为 "Key assumption"。
- 写 `eval.sh`（用哨兵包住测试命令，`utils.py:241-256`）→ `exec_run_with_timeout` → 落 `test_output.txt`。

`run_threadpool()`（`utils.py:287-317`）是一层薄封装，把异常吞掉并打印 traceback，失败项进 `failed` 列表——**不中断整批**。

---

## 6. 文件亮点（最精巧的设计）

1. **`harness/gather.py:346-348` 的 F2P/P2P 语义翻转**——造题阶段叫 `PASS_TO_FAIL`（过→挂），成品题里重命名成 `FAIL_TO_PASS`。同一个测试列表，在两个视角下名字完全相反，且只改一个 key 就完成了视角切换。这是全仓库最容易被误读、也最省事的设计。

2. **`profiles/base.py:372-387` 的镜像仓"历史清零"**——`rm -rf .git` → `git init` → `rm -rf .github/workflows` → 把 `.gitignore` 临时改名以便 `git add .` 再改回来、最后 `git add -f .gitignore`。这一串 shell 连招的目的只有一个：让做题的 agent 在容器里 `git log` 找不到任何原始历史。

3. **`harness/gather.py:539-558` 的"删掉会泄题的测试文件"**——F2P 测试文件在推分支前被物理删除并单独提交一次。配合 `utils.py:199` 的 `HEAD~1`，做题时看不见测试、评测时又能把测试恢复出来。**同一份代码，通过两个 commit 实现了"看时没有、判时有"**。

4. **`bug_gen/utils.py:58-146` 的 `generate_patch_fast`**——用 `difflib.unified_diff` 在内存里复刻 `git diff` 的输出格式，并手工对齐了两处 git 语义（空 rewrite → None；保留原末行换行数）。把"每个候选 bug 要起 5 个 git 子进程"变成 0 个，是程序化批量造题能跑得动的直接原因。

5. **`mirror/generate.py:284-304` 的"先试直接 apply，成功就 0 成本"**——镜像题的常规路径要调 LLM 反向重写（贵、慢、可能失败），但这行 `if apply_patches(repo, [direct_patch])` 让相当一部分题直接零成本拿到，把 LLM 预算让给了真正走不通的那些。这是典型的"先做便宜的事"的工程直觉。

6. **`procedural/python/base.py:33` 的 `for _ in range(self.max_attempts)`**——modifier 是随机 flip 的，可能一次都没改到（概率由 `likelihood` 决定，Python 普遍 0.15~0.4）。循环最多试 5 次，直到 `module.code != modified.code` 才认为"改成功了"；5 次都没改动就返回 None 放弃。这个 5 是全仓库唯一对"注入成功率"的硬性兜底。

---

## 7. 跟默认做法的差异（vs「人工从真实 PR 里扒题」）

| 维度 | 人工从真实 PR 扒题（SWE-bench 路线） | SWE-smith |
|---|---|---|
| **题目来源** | GitHub 上"issue → 有人提 PR 修好"的历史记录 | 自己往当前代码里注入 bug |
| **数量上限** | 受真实历史约束（SWE-bench 2,294 条；Verified 500 条） | 由代码实体数 × modifier 数决定，README 标 52k |
| **时效性** | 题目锚定在过去某个 commit，且被训练语料污染 | 每次生成都是新题；`--seed 24` 控制可复现 |
| **判分标准从哪来** | PR 里自带的 test_patch（新增/修改的测试） | 用**仓库已有的**测试——不需要作者写测试 |
| **测试改动** | 必须有 test_patch，否则不成题 | 不要求改测试；直接看现有测试的通过状态变化 |
| **难度控制** | 由真实 bug 自然分布决定，无法调节 | 可用 `num_patches`（combine）、`likelihood`、`min_complexity` 调 |
| **语言覆盖** | Python 为主，Multimodal/Multilingual 另设 | 11 种语言 profile；8 种支持程序化注入 |
| **答案泄漏风险** | 低（原 issue 里未必有答案） | 需要专门防：删 git 历史、删测试文件、镜像题隔离 `instance_ref` |
| **成本** | 人工标注 / PR 抓取，几乎零边际成本 | 程序化近零成本；LM 路线要钱；`CONTRIBUTING.md:123` 说生成一条题面约 **$0.02** |
| **真实性** | 100% 真实 | 有明确差距：`docs/guides/difficulty_rating.md:43-47` 显示 SWE-smith 各路子平均难度 3.3~5.7，SWE-bench 为 5.014 |

**最本质的差异**：SWE-bench 是"**事后考古**"（找已经发生过的 bug），SWE-smith 是"**事前变异**"（主动制造 bug）。前者题目真但有限，后者题目假但无限——SWE-smith 的整个工程复杂度，都花在"怎么让假题也具备真题的可判分性"上。

---

## 8. 做得好的 / 不够的

### 做得好的

1. **判分标准的构建完全自动化，且卡在"跑得通"这一层而不是"看起来对"**。`harness/valid.py:56` + `harness/grading.py:40` 全程跑真实容器、真实测试，比对的是逐条测试的通过状态，不是任何模型的判断。这道关卡让它造出来的题**天然自带标准答案**。判断：这是它能上 NeurIPS D&B 的根本原因——数据集的可信度来自"每题都真跑过"。

2. **防泄漏是多层叠加的，而不是靠一条规则**：抹 git 历史（`base.py:374-375`）+ 删 F2P 测试文件（`gather.py:539-558`）+ 成品题只保留 5 个字段、把 `instance_ref` 留在日志里（`gather.py:343-353`）+ 题面提示词明令禁止提文件/函数/测试名（`configs/issue_gen/ig_v2.yaml:40-46`）。判断：分层防泄漏比单点过滤可靠得多，尤其"成品题只留 5 个字段"这条是结构性隔离，不依赖模型自觉。

### 不够的

1. **题面防泄漏只靠提示词，没有任何自动化校验**。我在 `swesmith/issue_gen/` 全目录 grep 过 `leak` / `filter` / `forbidden` 等关键词，**零命中**。`ig_v2.yaml` 里 "DO NOT ... THE SOLUTION CODE SHOULD NEVER APPEAR IN YOUR RESPONSE" 只是给模型的祈使句，生成完不会检查输出里有没有出现文件名、函数名或 `pytest`。而 prompt 里恰恰**把失败测试的源码和测试输出（含文件路径）都喂进去了**（`generate.py:353-367`），模型很容易在题面里"顺嘴"写出测试文件路径。判断：这是整条链路最薄的一环。

2. **程序化注入的语法安全在多数语言里没有保障**。二次语法校验（tree-sitter 找 `ERROR`/`MISSING` 节点）只实现了 Java（16 处调用）和 Ruby（14 处调用），JavaScript / PHP / Rust / Golang / CPP 是纯字节替换后不复检。更具体的：`adapters/c.py` 与 `adapters/c_sharp.py` 都没实现 `complexity`，继承默认值 `-1`（`constants.py:109-111`），叠加 `min_complexity = 3` 后 `can_change()` 恒为 False（`procedural/base.py:34-39`）；而 `procedural/` 下也压根没有 C/C# 目录。判断：所谓"多语言支持"在程序化这条路上，实际是"8 种语言 + 6 种无语法复检 + 2 种做不到"。不过这些都是**可以被下游验证环节兜住**的——语法错的 patch 会在 `valid.py` 阶段被测试直接判掉，代价是浪费算力而不是污染数据集。

---

## 9. AI 范式提炼

**统领级范式：把"标注"这件事从"人写答案"改写成"机器制造可验证的差异"——只要你能自动构造出「变化前 X，变化后 Y」，你就不需要标注员，只需要一个能稳定测出 X/Y 的执行环境。**

具体例子：SWE-smith 里，一道题的"标注"不是任何人写的，而是 `harness/grading.py:40-92` 的 `get_valid_report()` 逐条比对两份测试输出得到的：同一批测试，跑在原始代码上是 `PASSED`，跑在注入 bug 后是 `FAILED`，这条测试就自动成了这道题的 `FAIL_TO_PASS`（经由 `gather.py:346-348` 的命名翻转）。标注员在这个流程里的位置被一个 Docker 容器和一次 `pytest` 完全替代了。

这个范式的可迁移性在于它的**前提条件很清晰**：① 你能低成本地批量制造"变异"；② 你有一个便宜、稳定、可重复的执行器能测出变异前后差异。凡是满足这两条的任务（配置漂移、数据管线故障、性能回归），都可以套同一套壳。

---

## 10. 跟你对接（落地三问）

**问 1：我手上有没有一个"便宜、稳定、可重复的执行器"？**
SWE-smith 的全部可信度都押在这上面。它的执行器是 Docker + 仓库自带测试套件。如果你要做类似的事，先回答：我的"测试"是什么？跑一次要多久（SWE-smith 单题 90 秒、整仓基线 900 秒，`profiles/base.py:108-109`）？稳不稳（flaky 测试会让造出来的题在评测阶段失效，SWE-smith 专门写了 `harness/repair.py` 来修这个问题）？**如果执行器不稳，后面所有环节都是空转。**

**问 2：我的"变异"要多样性还是要真实性？**
两条路的成本结构完全不同：
- 程序化（`procedural/`）：零边际成本、可复现（`seed=24`）、保证"方法可枚举"，但生成的 bug 不像人写的，难度分布偏易（Scriptural 平均 3.596，见 `docs/guides/difficulty_rating.md:45`）。
- LM Modify/Rewrite（`llm/`）：像真人但不可复现（`temperature=1`，`llm/modify.py:95`）、要花钱、需要按 config 写提示词（`configs/bug_gen/`）。
- PR Mirror（`mirror/`）：真实度最高（平均 4.876），但依赖 SWE-bench 的 PR 收集管线，而且**有答案泄漏风险需要自己处理**。

**问 3：我接受不接受"题目质量由下游过滤，而不是上游保证"？**
SWE-smith 明确是"多造 + 严筛"：程序化那条路不保证语法正确、不保证 bug 能被测试抓住，全靠 `valid.py` + `gather.py` 两道关把废品丢掉。代价是算力浪费（每道题都要真跑容器），收益是上游可以写得极其宽松、语言覆盖能快速扩张。**如果你的算力紧张，就必须反过来：在上游就做足语法校验和可行性判断，这会让每条新语言的接入成本显著上升。**

---

## 11. 信息截止

**2026-09-24**。

本笔记基于 `cache/swe-smith` 的本地快照（按文件树从 `raw.githubusercontent` 抓取，**无 `.git`**），共 171 个文件、其中 138 个 `.py`。

- **未能取证**：仓库的提交历史、分支、Tag、PR 列表（无 `.git`）；`tests/` 与 `docs/assets/` 目录（未抓取）；`LICENSE` 文件本身（README 引用但未抓取到）。所有涉及"某段代码是什么时候加的"的问题，本笔记一律不回答。
- **外部事实**（README / 文档里的数字，如 52k、40.2%、$0.02）**只作为仓库自述记录**，未联网核实。
- 本笔记未执行仓库内任何代码，未安装任何依赖，未修改 cache 里的任何文件。

---

## 12. 当前版本

- **commit 短哈希**：`9b74ac0811`（无 `.git`，无法用 `git rev-parse` 复核；此哈希由任务提供）
- **包版本号**：`0.0.9`，来源 `swesmith/__init__.py:3` 的 `__version__ = "0.0.9"`。
  pyproject.toml 里 version 是动态的：`[tool.setuptools.dynamic] version = {attr = "swesmith.__version__"}`（`pyproject.toml:118-119`），所以 `0.0.9` 是唯一权威版本号。
- **Python 要求**：`requires-python = ">=3.10"`（`pyproject.toml:13`），分类器覆盖 3.10 / 3.11。
- **基础依赖为空**：`dependencies = []`，注释说明是为了给 Modal 镜像做细粒度依赖组（`pyproject.toml:23-24`）。四个可选依赖组：`all` / `docs` / `test` / `validate` / `generate`（`pyproject.toml:26-107`）。
- **依赖树的关键信号**：`tree-sitter>=0.25` + 10 个 tree-sitter 语言包（`pyproject.toml:48-58`）、`libcst`（Python 程序化改动用）、`astor`（Python stub 生成用）、`unidiff`（解析 diff）、`swebench`、`litellm` / `portkey-ai`（LM 调用）、`modal`（云端批量）、`sglang`（难度打分模型服务）。

---

### 二次深读

### 深读 1：一道题要满足什么条件才算合格？代码里在哪一步验的？

**疑问/设计点**：什么叫"造出来的题是合格的"？是不是只要代码被改坏就行？

**源码里怎么做的**（三道关，缺一不可）：

- **第一关——patch 能干净落地**：`harness/gather.py:466-486`，三级兜底的 `GIT_APPLY_CMDS`（`constants.py:40-44`）：`git apply --verbose` → `git apply --verbose --reject` → `patch --batch --fuzz=5 -p1 -i`。三次全失败就 `reset_repo` 并丢弃。combine 路径还有额外一次自检：`utils.py:160-164` 把合并后的 patch 再 `git apply` 一遍确认干净。
- **第二关——F2P 非空**：`harness/valid.py` 跑完出 `report.json`，`gather.py:333-339` 检查 `len(results[PASS_TO_FAIL]) == 0` 就丢。注意这里的语义是"**注入 bug 后从通过变失败的测试数必须 ≥ 1**"。`harness/valid.py:144-147` 还用这个数字做统计：`if len(report.get(FAIL_TO_PASS, [])) == 0: return {"status": "0_f2p"}`。
- **第三关——P2P 非空**：同一个 `if` 里 `n_p2p == 0` 也丢。P2P 是"改坏前后都通过的测试"，它代表这道题的**护栏**：如果 P2P 为空，说明这次改动把整个测试套件都搞崩了（可能是语法错误、导入失败），这种题即使 F2P 不为空也是废的。

**唯一的例外**：`gather.py:335` 的 `pr_exception = ".pr_" in subfolder and n_p2p == 0 and n_f2p > 0`——PR Mirror 题的 instance_id 里带 `.pr_`，允许 P2P 为 0。理由合理：镜像真实 PR 时，原 PR 的测试可能已经被改过或删过，找不到"未受影响的测试"是正常的。

**为什么必须这样做**：F2P 是"这题有解吗"的证据，P2P 是"这题有边界吗"的证据。只有 F2P 的题，agent 可以随便瞎改让测试通过；只有 P2P 的题，压根没有 bug。两个都非空，才构成 SWE-bench 意义上的"一道题"。

**代价**：这两条硬门槛会**大幅削减通过率**。程序化生成的候选 patch 里，能同时满足"改坏 F2P"和"不误伤 P2P"的比例并不高；再加上 `valid.py` 里那些因为基线跑不起来就整仓放弃的（`valid.py:203-219`，用 `timeout_ref=900` 秒跑整仓基线），实际从候选到成品的损耗非常大。`scripts/bug_gen_modal.py:148` 的 `MIN_PATCHES_FOR_VALIDATION = 50` 就是这个损耗的侧面证据——少于 50 个候选补丁的仓库，官方脚本直接不做验证，因为大概率筛不出一条题。

### 深读 2：程序化注入有哪些具体 operation？怎么保证改完代码还能跑？

**疑问/设计点**：机械改代码最容易出语法错误，这些 modifier 怎么避免？不同语言之间有没有差别？

**源码里怎么做的**（举 5 个 Python 的具体 operation）：

| Operation 类 | 名（`name` 字段） | 改什么 | 位置 |
|---|---|---|---|
| `OperationChangeModifier` | `func_pm_op_change` | 在运算符同类组内换了：`+`↔`-`、`*`/`/`/`//`/`%` 互相换、位运算互相换、`<<`↔`>>`、`Power`↔`Multiply` | `python/operations.py:36-86` |
| `OperationFlipOperatorModifier` | `func_pm_flip_operators` | 按 25 条映射表一对一翻转：`==`→`!=`、`<`→`>`、`and`→`or`、`In`→`NotIn` | `python/operations.py:89-110` + 表在 `:7-33` |
| `OperationSwapOperandsModifier` | `func_pm_op_swap` | `left, right = right, left` | `python/operations.py:113-131` |
| `RemoveLoopModifier` | `func_pm_remove_loop` | 用 `libcst.RemoveFromParent()` 整段删掉 `for`/`while` | `python/remove.py:8-18` |
| `RemoveWrapperModifier` | `func_pm_remove_wrapper` | 删掉 `with` / `async with` / `try` 包装 | `python/remove.py:44-60` |
| `ClassRemoveBasesModifier` | `func_pm_class_rm_base` | 删掉类的基类 | `python/classes.py:11`（`min_complexity = 10`） |

**语法安全保障——分语言看**：

- **Python：结构性保证**。唯一入口 `PythonProceduralModifier.modify()`（`python/base.py:22-49`）先用 `libcst.parse_module(src_code)` 解析原代码，解析失败就返回 None（`base.py:24-27`）；改动是对 libcst 的 CST 结构做替换，再用 `modified.code` 回写成字符串。**libcst 只渲染合法 Python**，所以在解析成功的前提下不可能产出语法错误的代码。另外 `base.py:33-39` 把 `module.visit()` 包在 `try/except (AttributeError, TypeError, ValueError)` 里，异常直接放弃这个候选。

- **Java：显式复检**。`java/base.py:20-43` 的 `has_syntax_errors()` 用 tree-sitter 重新解析修改后的代码，递归找 `ERROR` 或 `MISSING` 节点；`validate_syntax()`（`java/base.py:45-60`）在代码未变时返回 `None`（让调用方区分"没改"和"改坏了"）。全目录 **16 处**调用点（control_flow / returns / literals / boolean / loops / operations / remove 等）。

- **Ruby：显式复检**。`ruby/base.py:14-27` 的 `validate_syntax()` 同样找 `ERROR`/`MISSING` 节点，**14 处**调用点。

- **JavaScript / PHP / Rust / Golang / CPP：没有复检**（各 0 处）。这 5 种语言的 modifier 模式是：`Parser(LANG).parse(bytes(src, "utf8"))` → 收集要改的节点的 `start_byte`/`end_byte` → **倒序遍历（`for change in reversed(changes)`）直接对字节串做切片拼接** → `_safe_decode()` 返回。JS 的例子见 `procedural/javascript/operations.py:89-100`。倒序遍历是为了防止前面的替换让后面的字节偏移失效——但这只解决了偏移问题，**改完的字符串没有重新解析过**。举个具体的风险点：`php/operations.py:234` 的 `swapped = f"{right_text} {change['operator']} {left_text}"` 先把左右操作数文本取出来再用空格拼回去，如果原文里 `a+b`（无空格）结果会变成 `b + a`——这不是错误但改变了格式；如果原文是宏或多行表达式，拼接就可能直接破坏语法。

**为什么必须这样做**：Python 走 libcst 是因为 libcst 本来就是"保留格式的 CST"，天生做这件事；tree-sitter 是做**语法高亮/增量解析**用的，它能把文本变成树，但不提供"把树写回文本"的能力，所以只能拿到偏移后手工拼字符串。这就是为什么 Java/Ruby 作者额外写了 `validate_syntax` 兜底——他们意识到了这个问题。

**代价**：不做复检的那 5 种语言，垃圾 patch 的比例会明显更高，全靠 `valid.py` 阶段用测试跑一遍把它们筛掉。**这不是数据质量问题，是算力成本问题**——每条垃圾 patch 都要真的起一次容器、跑一次测试。

### 深读 3：大模型造 bug 和程序化造 bug，在判分可信度上差在哪？

**疑问/设计点**：两条路造出来的 patch 最终都要过 `valid.py` 的同一套判分。那"可信度"还有区别吗？

**源码里怎么做的**：

- **两者的判分流程完全一样**。`harness/valid.py:56-147` 不区分 patch 来自哪条路——它只认 `instance[KEY_PATCH]`，跑测试、比对、出 `report.json`。这是有意的设计，也是 SWE-smith 的一个优点：**判分器对生成方式无感知**。

- **差别出现在"patch 是怎么被确认生成成功的"这一步**：

  **程序化（`procedural/generate.py:35-64`）**：`pm.modify(candidate)` 返回的 `BugRewrite.rewrite` 是**内存里算出来的完整新代码**，然后 `generate_patch_fast()` 保证 `original_lines != modified_lines`（`bug_gen/utils.py:115-116`），否则返回 None。**整个链路是确定性的**：同一份源码 + 同一个 `seed=24` + 同一个 modifier，永远产出同一个 diff。哈希也是确定的（`constants.py:174-176`：`sha256(rewrite)` 再映射成 8 位小写字母数字）。

  **大模型（`llm/modify.py:173-192`）**：LM 返回的文本要先 `extract_code_block()`（`llm/utils.py:7-10`，正则 ` ```(?:\w+)?\n(.*?)``` `）抠出代码块——**如果模型没按格式输出代码块，抠出来就是空字符串**；然后 `apply_code_change()` 写回文件；再 `get_patch(repo, reset_changes=True)` 真的起 git 子进程算 diff；`if not patch: raise ValueError("Patch is empty.")`。失败时 `(bug_dir / metadata_path).unlink(missing_ok=True)` 把 metadata 也删掉，保证不留下"半个 bug"（`llm/modify.py:182-190`）。**这条链路带着三重不确定性**：模型是否遵守输出格式、模型改的代码是否语法正确、模型改的代码跟原文件结构是否兼容。

  **大模型 rewrite 路线额外还有一步**：`llm/rewrite.py:97-142` 先把函数体清空（`candidate.stub`，即 `TODO: Implement this function` + `pass`，见 `adapters/python.py:114-149`），把这个空壳喂给模型让它重写，然后 `git reset --hard` 撤回空壳、再应用模型的版本（`llm/rewrite.py:136-151`）。`candidate.stub` 用 `astor.to_source()` 生成（`adapters/python.py:149`），**它保证空壳本身是合法 Python**（有 `pass` 占位），这样模型的起点一定是能跑的。

**为什么必须这样做**：程序化那条路的"可信"来自**可复现**——你可以用 seed 重跑出完全一样的题；大模型那条路的"可信"来自**结构约束**（stub 是合法代码、代码块正则抽取、空 patch 抛异常），但它的最终质量仍然要靠 `valid.py` 兜底。

**代码里的体现**（这是最能说明差别的几行）：
- 程序化：`generate.py:44-51`，`if not bug: return False` / `if not patch: return False`——**两层早退，都是静默丢弃，不重试**。
- 大模型：`llm/modify.py:163-197`，**统计而非丢弃**——`n_bugs_generated` 和 `n_generation_failed` 两个计数器（`generate.py` 的对应物里根本没有这两个字段）。也就是说，官方对 LM 路线的预期就是"会有一部分生成失败，记下来就行"。
- 还有一个信号：`llm/modify.py:95` 用 `temperature=1`，`llm/rewrite.py:125` 用 `temperature=0`。Modify 故意要多样性，Rewrite 要稳定性。

**代价**：LM 路线的每条题都带 `cost` 字段（`llm/modify.py:107` 按 response 调用 `completion_cost`），并且要在根目录放 `.env` 配 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`（`CONTRIBUTING.md:106`）。程序化路线的 metadata 里 `cost` 恒为 `0.0`（`python/base.py:47`）。规模化时这个成本差是决定性的——这也是为什么 `scripts/bug_gen_modal.py` 的批量流水线只走程序化（`bug_gen_modal.py:563` 直接 import `procedural.generate.main`）。

### 深读 4：镜像真实 PR 怎么防止「把原 PR 的答案泄漏进题目」？

**疑问/设计点**：PR Mirror 路线的输入就是"某个真实的修复提交"，这道题的答案 = 反向操作。怎么保证答案不被做题的 agent 看到？

**源码里怎么做的**（四道隔离）：

1. **镜像仓没有历史**。`profiles/base.py:362-389` 的 `create_mirror()`：
   ```python
   git_cmds = [
       "rm -rf .git",
       "git init",
       'git config user.name "swesmith"',
       "git commit --no-gpg-sign -m 'Initial commit'",
       "git branch -M main",
   ]
   ```
   原仓库 clone 下来后**先删 `.git` 再重新 init**。所以 agent 在容器里 `git log` 只能看到 `Initial commit`，没有任何原始提交信息、没有 commit message 里可能出现的 issue 链接。同时 `rm -rf .github/workflows` 和 `rm -rf .github/dependabot.y*` 也一并清掉（`base.py:378-379`）。

2. **成品题的字段白名单**。`gather.py:343-353` 构造 task instance 时**只写 5 个字段**：
   ```python
   task_instance = {KEY_INSTANCE_ID, KEY_PATCH, FAIL_TO_PASS, PASS_TO_PASS}
   task_instance[KEY_IMAGE_NAME] = rp.image_name
   task_instance["repo"] = rp.mirror_name
   ```
   而包含了**原 PR 完整 patch（含修复代码）+ 原始 problem_statement**的 `instance_ref` 字典（`mirror/generate.py:186` 的 `metadata[INSTANCE_REF] = inst`）**不在其中**。它只落在日志里：`metadata__pr_<N>.json` 和 `ref__pr_<N>.diff`（`mirror/generate.py:213-220`）。

3. **分支上只有两个提交，且删掉了测试**。gather 建分支时依次 commit `'Bug Patch'`（`gather.py:531-537`）和 `'Remove F2P Tests'`（`gather.py:549-558`）。所以分支的历史里既有 bug 的引入记录（"Bug Patch" 这个 commit message 本身就是个提示，但至少不含修复内容），又**物理上不含会暴露答案的测试文件**。

4. **`instance_ref` 只在"选测试文件"时被用**。`profiles/base.py:592-607` 用它来定位 PR 改了哪些测试文件，从而在 `min_testing` 模式下只跑相关测试。这是一次**只读的、内部的使用**，不进入任何会被推出去的产物。

**为什么必须这样做**：PR Mirror 的题目"真实度最高"（难度打分 4.876，`docs/guides/difficulty_rating.md:46`），但它的构造方式决定了答案就在手边——原 patch 就是答案。不隔离的话，agent 只要 `git log` 或者读一下上游的 GitHub 就能拿到修复代码。

**代价**：
- `ref__pr_<N>.diff` 和 `metadata__pr_<N>.json` **仍然躺在 `logs/bug_gen/` 里**（`mirror/generate.py:214`）。如果这个日志目录被打包公开，答案就跟着走了。`CONTRIBUTING.md:108-109` 描述贡献流程时是"把 `logs/bug_gen/<repo>/` 整个 zip 上传"，**这一步的泄漏风险取决于打包前有没有清理** —— 代码里没有自动清理逻辑。
- 因为要删 `.git` 重建，镜像仓和原仓库**完全脱钩**：agent 无法从环境里学到任何"这是哪个项目"的上下文信息。

### 深读 5：issue 文本生成怎么防止泄漏（不能提文件名/函数名/修改位置）？

**疑问/设计点**：题面是从"代码 diff"反写出来的，模型天然会倾向于描述"你改了哪个文件的哪一行"。怎么防？

**源码里怎么做的**：

- **提示词层面（唯一的手段）**，三处硬约束：
  - `configs/issue_gen/ig_v2.yaml:24-25`（system role）："DO NOT explain the fix/what caused the bug itself, focus on how to reproduce the issue it introduces" + "Do not mention pytest or what exact test failed. Instead, generate a realistic issue."
  - `configs/issue_gen/ig_v2.yaml:40-46`（instance role，用 `<IMPORTANT>` 标签包起来）："DO NOT GIVE AWAY THE FIX! THE SOLUTION CODE SHOULD NEVER APPEAR IN YOUR RESPONSE." / "DO NOT SAY THAT EXISTING TEST(s) FAILED." / "DO NOT SUGGEST RUNNING ANY TESTING COMMANDS (e.g., pytest)."
  - `configs/issue_gen/ig_v1.yaml:31-33` 是同一组约束的早期版本。

- **示范对齐策略**（这个设计很巧）：`generate.py:296-305` 的 `get_demo_issues()` 从 SWE-bench Verified（`generate.py:228`）随机抽真实 issue 做示范，`ig_v2.yaml:18-23` 明确要求模型**模仿示范的"不规整"**："If the demonstration issues are not well structured, your output should also be not well structured... If the demonstrations include human 'flavor text' or 'fluff', your output should also include human 'flavor text' or 'fluff'." 目的是让合成题面在**文本分布上**贴近真实 issue，避免训练出"一看题面就知道是合成的"的模型。

- **示范只取前 2 条、测试源码只取前 5 条**：`ig_v2.yaml:32` 的 `demo_problem_statements[:2]`、`ig_v2.yaml:57` 的 `test_funcs[:5]`。控制 prompt 长度。

- **测试输出截断**：`generate.py:269-276` 用 `maybe_shorten()` 把 test_output 压到 `max_var_tokens`（默认 10000，`generate.py:171`），方式是**保留头尾各一半、中间插 `(...)`**（`generate.py:151`）。这个截断反而可能泄漏更多——因为 pytest 输出的头部往往含文件路径。

- **注意模型看到的东西**：prompt 里同时给了 `patch`（含被改的文件路径和函数上下文的 hunk 头）、`test_output`（含测试文件路径）、`test_funcs`（**失败测试的完整源码**）。**约束完全靠提示词，靠模型自觉不写进输出。**

**为什么必须这样做**：如果题面里出现文件名/函数名/行号，agent 就能跳过"定位"这一步直接改，这题考的就不是 SWE 能力而是照抄能力。所以这是个"必须防"的点。

**代价 / 漏洞**（这是我认为最值得说的一点）：
1. **没有任何输出侧校验**。我对 `swesmith/issue_gen/` 全目录做了 `leak` / `filter` / `forbidden` / `def validate` 关键词检索，**零命中**。生成出来的 `problem_statement` 会被直接写进 `instance["problem_statement"]`（`generate.py:516`）并作为数据集的一部分输出（`generate.py:519-525`），中间**零过滤**。
2. **`temperature=0`（`generate.py:386`）并不保证不泄漏**——它只保证同一 prompt 下输出稳定，模型仍可能在输出里写 "I noticed the bug in `src/utils.py`"。
3. **降级路线全都在泄漏**：`issue_gen/get_static.py` 的题面**故意**包含文件名、函数名、测试名——`PROMPT_FILES` 写 "likely located in the following file(s): {gold_files}"（`get_static.py:30-33`），`PROMPT_FILES_FUNCS` 还加函数名（`get_static.py:36-42`），`PROMPT_TESTS_F2P` 直接列出失败测试（`get_static.py:48-53`）。这些是**有意为之的对照组**（用来在论文里对比"给多少提示"的效果），不是 bug。但混用时容易误伤。
4. **修复办法很直接但代码里没有**：拿到 `problem_statement` 后，用 `instance["patch"]` 里的文件路径、`FAIL_TO_PASS` 里的测试名做一次子串检查，命中就重新生成或丢弃。这套材料在 `gather` 之后**已经在内存里了**（`gather.py:540` 就调了 `rp.get_test_files()` 拿测试文件名），补这个检查的成本极低。

### 深读 6：profile 基类里「怎么判定一条测试通过」的默认策略，各语言怎么覆盖？

**疑问/设计点**：不同语言的测试框架输出格式天差地别（pytest / go test / cargo test / vitest / phpunit / mvn / gradle），怎么统一成一张"测试名 → 状态"的表？

**源码里怎么做的**：

- **统一接口**：`log_parser(self, log: str) -> dict[str, str]`（`profiles/base.py:664-667`，`@abstractmethod`）。返回值是 `{测试用例标识: 状态字符串}`，状态字符串**必须**取自 swebench 的 `TestStatus` 枚举（`TestStatus.PASSED.value` = `"PASSED"`、`FAILED`、`ERROR`、`SKIPPED`、`XFAIL` 等，`profiles/python.py:6-11` 里 import）。

- **Python 默认实现**（`profiles/python.py:93-102`）：
  ```python
  for line in log.split("\n"):
      for status in TestStatus:
          is_match = re.match(rf"^(\S+)(\s+){status.value}", line)
          if is_match:
              test_status_map[is_match.group(1)] = status.value
  ```
  正则要求"行首非空白串 + 空白 + 状态词"。这是为了匹配 pytest verbose 的输出（`test_file.py::test_name PASSED`）。**所以 Python 默认 test_cmd 里必须带 `--verbose`**（`python.py:35`），否则一行都解析不出来。

- **覆盖的例子（Python 内部就有 6 处）**：
  | Profile | 覆盖方式 | 位置 |
  |---|---|---|
  | `AutogradAc044f0d` | 匹配 pytest-xdist 的 `[gw0] PASSED test_name` 格式 | `python.py:164-172` |
  | `Paramiko23f92003` | 用 `-rA` 的短格式 `^PASSED\s(\S+)` | `python.py:604-612` |
  | `PythonSlugify872b3750` | 完全自己写：匹配 `name ... ok` / `name ... FAIL` | `python.py:812-828` |
  | `TornadoD5ac65c1` | 匹配 `... ok` / ` ... skipped ` / `FAIL:` / `ERROR:` 三种前缀 | `python.py:1066-1078` |
  | `MypyE93f06ce` | 只看行里有没有 `PASSED`/`FAILED`，取行尾 token | `python.py:1193-1204` |
  | `Gpxpy09fc46b3` 等 | 不覆盖 parser，改 `test_cmd` 指向 `test.py` | `python.py:422-426` |

- **其他语言的**：
  - Go：`test_cmd = "go test -v ./..."`（`profiles/golang.py:26`），配套一个 `_test_name_to_files_cache` 做测试名→文件的反查（`golang.py:27-29`）。
  - Rust：`test_cmd = "cargo test --verbose"`（`profiles/rust.py:22`），`rust_version = "1.88"`（`profiles/rust.py:24`）。
  - JS：`test_cmd = "./node_modules/.bin/vitest --no-color --reporter verbose"`（`profiles/javascript.py:329`）；另一个 profile 用 Node 内置 runner `NO_COLOR=1 node --test`（`javascript.py:362`）。还有为 Jasmine 专门写的汇总行解析——从 `N specs, M failures, K pending` 里反推出通过数，再**合成**出 `jasmine_spec_1..N` 这种假测试名（`javascript.py:300-317`）。
  - PHP：`test_cmd = "vendor/bin/phpunit --testdox --colors=never"`（`profiles/php.py:23`），parser 是 `parse_log_phpunit_testdox()`（`php.py:132-160+`），用 `✔` / `✘` / `↩` 三个 Unicode 符号匹配，并维护 `current_class` 状态来把测试名限定成 `FQCN::Testdox name`。
  - Java（Maven）：`test_cmd = "mvn test -B -T 1C -Dsurefire.useFile=false -Dsurefire.printSummary=true -Dsurefire.reportFormat=plain"`（`java.py:211`）。
  - Java（Gradle）：`./gradlew test --rerun-tasks --continue --no-daemon --console=plain || true; find . -type f -name 'TEST-*.xml' -exec cat {} \;`（`java.py:238`）——**先跑 gradle，再直接 cat XML 结果文件**。因为 Gradle 的 console 输出不可靠，XML 才是权威。它同时把 `timeout` 从默认 90 秒抬到 300 秒（`java.py:239`），Maven 那条则抬到 400 秒（`java.py:264`）。**这不是个例**：全仓库共有 115 处 profile 覆盖 `timeout`（见下）。
  - Cpp：有一整套 `parse_log_lit`（`profiles/cpp.py:26-40+`）解析 LLVM lit 的 `FAIL: SUITE :: TestName (N of M)` 和 `Expected Passes: N` / `Passed: N (M%)` 两种汇总格式。

- **`timeout` 是被覆盖最多的默认值**（真跑 `grep -rn "^\s*timeout: int = " swesmith/profiles/*.py`）：默认 `timeout = 90` / `timeout_ref = 900`（`profiles/base.py:108-109`），但 profile 层共 **115 处**覆盖 `timeout`——`java.py` 独占 105 处（Maven 400 秒 ×65、Gradle 300 秒 ×40，注释统一写 `# Maven/Gradle tests can be slow`），`ruby.py` 6 处（180 ×5、300 ×1）、`golang.py` 2 处（120）、`rust.py:219` 1 处（180）、`javascript.py:2547` 1 处（300）。取值分布：**400×65、300×42、180×6、120×2**。`timeout_ref` 也有一处覆盖：`golang.py:403` 把整仓基线从 900 秒砍到 120 秒。**含义**：不同语言/构建系统的测试耗时差异是硬约束，90 秒只对 Python 这类轻量 pytest 成立；Java 这种 JVM 冷启动 + 依赖解析的重活必须单独放宽。

- **"通过"的最终定义在判分器里**（`harness/grading.py:95-106`）：
  ```python
  def test_passed(case, sm): return case in sm and sm[case] in ["PASSED", "XFAIL"]
  def test_failed(case, sm): return case not in sm or sm[case] in ["FAILED", "ERROR"]
  ```
  注意 `XFAIL`（预期失败）算**通过**——这是对的，因为它在语义上确实是"符合预期"。而"测试名不在表里"算**失败**——宽松兜底。

**为什么必须这样做**：`valid.py` 和 `gather.py` 对测试状态的判断全部依赖这张表。表错了，题就错了。而且 `grading.py:68-70` 有一个关键过滤：`for test_case in postgold_sm: if test_case not in pregold_sm: continue`——**只比对两次都出现过的测试**。新增的测试（只在 post 出现）直接忽略。这防止了"注入 bug 时顺便加了新测试"这种异常情况污染判分。

**代价**：每种语言、每个测试框架、甚至同一框架的不同版本都要单独调 parser。所以 Profile 文件才长得这么臃肿——`python.py` 1359 行里，超过 90% 是同一种模式的重复（`owner`/`repo`/`commit` 三个字符串 + 偶尔一个 `install_cmds` 或 `log_parser` 覆盖）。这是"用配置而非抽象"换来的直接可读性，代价是人工维护成本。

### 深读 7：难度打分用什么信号？

**疑问/设计点**：怎么证明合成题"难度接近真实题"？

**源码里怎么做的**：

- **信号来源不是执行结果，而是模型判断**。`train/difficulty_rater/get_difficulties.py` 起一个 OpenAI 兼容的 LLM 服务（`openai.Client(base_url=f"{base_url}/v1", api_key="swesmith")`，`get_difficulties.py:52`），把 **problem_statement + patch** 拼进 prompt（`create_datasets.py:29-37` 的 `PROMPT_INSTANCE`），让模型四选一：`<15 min fix` / `15 min - 1 hour` / `1-4 hours` / `>4 hours`（`create_datasets.py:19-27`）。

- **这个模型本身是微调出来的**。`docs/guides/difficulty_rating.md:1` 写明："We LoRA Fine-Tuned a Qwen 2.5 32B Coder Instruct model on 1.5k human ratings of the difficulty of real world bugs."训练数据来自 SWE-bench 的人工难度标注 CSV：`create_datasets.py:42-43` 读 `ensembled_annotations_public.csv` 和 `samples_with_3_annotations_public.csv`，用 `df.sample(frac=0.2, random_state=42)` 切 20% 做测试集（`create_datasets.py:46-47`）。

- **标注只有 3 档**：训练时把 `>4 hours` 合并成 `1-4 hours`（`create_datasets.py:59-60`），所以模型实际输出 3 类。推理时 `max_tokens=64`（`get_difficulties.py:36`）、`temperature=0`（`get_difficulties.py:35`）。

- **分数映射**（`get_difficulties.py:25`）：
  ```python
  DIFFICULTY_SCORE = {"15 min - 1 hour": 5, "1-4 hours": 9, "<15 min fix": 1}
  ```
  **注意：档中值是 5 和 9，不是 2 和 3**——这是个"故意拉开"的非线性映射，让 hard 任务对均值的拉动更明显。最终分数是加权平均（`get_difficulties.py:101-108`），保留 3 位小数。

- **推理是 4 线程并发**（`get_difficulties.py:79`，`num_threads = 4`），支持断点续跑（读已有的 `*_difficulties.jsonl`，跳过已完成的，`get_difficulties.py:68-76`）。失败时返回 `"difficulty": "error"`（`get_difficulties.py:44-48`），统计时被 `DIFFICULTY_SCORE` 的 key 过滤掉（`get_difficulties.py:99-100`）。

**算出来的结果**（`docs/guides/difficulty_rating.md:35-47`）：

| 数据集 | 条数 | 分数 | easy | mid | hard |
|---|---|---|---|---|---|
| SWE-bench | 2294 | **5.014** | 438 | 1408 | 446 |
| └ Verified | 500 | 3.960 | 173 | 284 | 43 |
| SWE-gym | 2438 | 5.625 | 288 | 1456 | 664 |
| SWE-smith (LM Modify) | 1000 | 3.304 | 441 | 542 | 17 |
| SWE-smith (LM Rewrite) | 1000 | **5.272** | 68 | 796 | 136 |
| SWE-smith (Procedural) | 1000 | 3.596 | 374 | 603 | 23 |
| SWE-smith (PR Mirror) | 1000 | 4.876 | 206 | 619 | 175 |
| SWE-smith (Combine) | 1000 | **5.720** | 52 | 716 | 232 |

**为什么必须这样做**：合成数据的最大质疑是"你造的题是不是太简单了"。用"和 SWE-bench Verified 在同一个标尺上打分"来回应这个质疑，是这篇论文最有说服力的一招。表格里 LM Rewrite (5.272) 和 Combine (5.720) 都**高于** SWE-bench Verified (3.960)，而 LM Modify (3.304) 和 Procedural (3.596) 明显低于它——**数据本身诚实地暴露了各路线的难度差异**。

**代价**：
- 打分器是自己训的，**没有独立的第三方验证**，存在"用模型评自己的数据"的循环风险。`docs/guides/difficulty_rating.md:9` 的 HuggingFace 链接是**空的**（`[HuggingFace checkpoint]()`），所以外部无法复现这套打分。
- 打分信号只来自"读题面 + 读 patch"，**不包含真实解题结果**（比如某个 agent 的实际成功率）。所以它是"人类感知难度"的代理，不是"机器可解性"的度量。

### 深读 8：失败 / 异常怎么兜住？（造题跑挂了怎么办）

**疑问/设计点**：批量造 5 万道题，中间各种失败是常态。系统怎么保证"挂了一个不拖垮全批"？

**源码里怎么做的**（按层级列，全部带具体值）：

- **单次造题失败 → 静默丢弃 + 计数**：
  - 程序化：`procedural/generate.py:44-51`，`if not bug: return False`、`if not patch: return False`（不计入成功数，不重试，不报错）。
  - 单次 modifier 内：`python/base.py:33` `for _ in range(self.max_attempts)`（**5 次**），改不动就返回 None。`python/base.py:38-39` 捕获 `(AttributeError, TypeError, ValueError)`。
  - LM：`llm/modify.py:160-197` 把异常包在 `try/except` 里，失败时 `unlink(missing_ok=True)` 删掉半个 metadata，`n_generation_failed += 1`。
  - LM 重写：`llm/rewrite.py:103-104` 空壳替换失败返回 `{"n_generation_failed": 1}`；`llm/rewrite.py:127-128` 遇到 `litellm.ContextWindowExceededError`（上下文超长）同样计数返回。
  - **重试策略**：LM 调用的重试在 `issue_gen/generate.py:112-118` 的 `@retry` 装饰器上——`stop_after_attempt(10)`（**10 次**）、`wait_exponential(multiplier=1, min=4, max=60)`（**指数退避，4~60 秒**）、`retry_if_not_exception_type((KeyboardInterrupt, TypeError, ValueError))`（**不重试这三类**，因为重试也不会好）。

- **持久化 / 断点续跑**（这是真正让 5 万道题能跑完的机制）：
  - `gather.py:177-189`：如果 `logs/task_insts/<run>.json` 已存在，读进来、**剔除已不存在的 bug**、只处理剩下的。
  - `gather.py:451-461`：分支已存在则跳过，但**照样把它算进最终结果**——所以重跑不会丢题。
  - `valid.py:173-185`：已有 `report.json` 的 instance 跳过，`--redo_existing` 强制重跑。
  - `eval.py:171-181`：同理。
  - Modal 层更彻底：`scripts/bug_gen_modal.py:982-989` 用 `done.txt` / `error.txt` / `*_all_patches.json` 三个标记文件判断仓库状态，已完成的直接跳过。

- **仓库级失败 → 整仓放弃**：
  - `valid.py:203-219`：基线跑不起来或 `timeout_ref=900` 秒超时，`shutil.rmtree(ref_dir)` 并 `continue`，**整个仓库的所有候选补丁都不验证**。注释写得很直白："If timed out, skip this repo/commit (remove log directory)"。
  - `scripts/bug_gen_modal.py:1362-1368`（预金阶段）：解析出来的 `PASSED` 数为 0 → 写 `error.txt`，加进 `failed_repos`，**后续 post-gold 阶段直接过滤掉这个仓库的所有补丁**（`bug_gen_modal.py:1649-1654`）。

- **批量执行层 → 不中断**：
  - `harness/utils.py:287-317` 的 `run_threadpool()`：每个 future 的异常被 `except Exception` 吞掉、`traceback.print_exc()` 打印、塞进 `failed` 列表，**循环继续**。
  - Modal 层用 `return_exceptions=True`（`bug_gen_modal.py:1048`）+ `wrap_returned_exceptions=False`（`bug_gen_modal.py:1050`），且 `generate_bugs_remote` 内部的 `_safe_execute()` 包住所有子步骤（`bug_gen_modal.py:605-613`），连"保存结果"这一步失败都不影响进程退出。
  - 更细的：`bug_gen_modal.py:1538-1554` 在验证失败时**故意写一份 `{valid: False, error: ..., skipped: True}` 的 report.json**，注释说明目的是 "so this patch won't be retried on subsequent runs"——**用写"失败报告"的方式把失败也变成幂等的**。

- **超时 → 主动收工而非被杀**：
  - `procedural/generate.py:83-93` 的 `check_timeout()` 每处理一个候选检查一次，到点打印 `TIMEOUT` 并 `return local_total`。
  - Modal 层给它留缓冲：`soft_timeout = MODAL_TIMEOUT - timeout_buffer_seconds`（`bug_gen_modal.py:686`），其中 `MODAL_TIMEOUT = 10 * 60`、`timeout_buffer_seconds = 60`（默认，`bug_gen_modal.py:549`）。**留 60 秒给"收集结果 + 写 Volume"**。

- **flaky 测试导致的"坏题" → 专门写了个修复脚本**：`harness/repair.py`。它的逻辑是：拿 `harness/eval.py` 用 gold patch 跑的 `ids_unresolved`（本该被解出来的题却没解出来 → 说明题目本身有问题），然后分三种处理：
  - 报告里 `KEY_TIMED_OUT` → **删掉整道题**（`repair.py:122-136`）；
  - `FAIL_TO_PASS.failure` 和 `PASS_TO_PASS.failure` 都为空 → 保留不动（`repair.py:142-145`）；
  - `FAIL_TO_PASS.success` 为空（F2P 测试一条都没过）→ **不可修复，删掉**（`repair.py:147-173`）；
  - 否则 → 把那些"失败了的测试"从 F2P/P2P 列表里**剔除**，保留题目（`repair.py:186-215`），并且 `assert len(new_f2p) > 0`（`repair.py:187-189`）保证剔完还有。
  删除动作是三步全做（`repair.py:41-79`）：删 `logs/run_validation/<repo>/<id>` 目录、从 `logs/task_insts/<repo>.json` 里删条目、`git push --delete origin <branch>` 删远程分支。
  还有 `--dry-run` 模式（`repair.py:91-94`）和执行前的 `input("Continue? [y/N] ")` 确认（`repair.py:106-108`）。

**为什么必须这样做**：造题是有损的（大量候选会被筛掉），批量执行必然会挂。**如果不做幂等 + 不落盘中间状态，一次 Modal 任务超时就得从头再来**，5 万道题的规模下这是不可接受的。

**代价**：
- **大量失败被静默吞掉**。程序化路径只在一处会打印警告：`bug_gen/utils.py:36-42`，当 `bug.rewrite` 为空时打一行 `WARNING: Empty rewrite detected for ... Skipping.` 到 stderr。除此之外失败不留痕迹，所以要回答"程序化造题的成功率是多少"这个问题，**代码里没有直接答案**——只能靠 `logs/bug_gen/<repo>/` 里实际落盘的文件数反推。
- **`repair.py` 会静默降低题目难度**：把"失败的 F2P 测试"剔除，等于承认"这题有部分测试判不准"，但题目本身仍然保留。如果同一个 instance 反复被修，它的 F2P 集合会越来越小，**最终可能只剩 1 条测试**——这种题在难度上和原始设计已经不是一回事了，而 `repair.py` 不会留下这个退化过程的记录。

---

### 取证台账

| 事实 / 数值 | 取证方式（文件:行号 或 命令） | 时点 |
|---|---|---|
| 包版本 `0.0.9` | `swesmith/__init__.py:3` | 2026-09-24 |
| 仓库文件总数 171，其中 `.py` 138 个 | `find . -type f \| wc -l`；`find . -name '*.py' \| wc -l` | 2026-09-24 |
| 具体 RepoProfile 子类 **835** 个 | python 脚本对 `swesmith/profiles/*.py` 按 `@dataclass` 切块 + 排除 12 个基类名 | 2026-09-24 |
| 唯一 `owner/repo` **832** 个，唯一 owner **725** 个 | 同上，抽取 `owner:` / `repo:` 字段去重 | 2026-09-24 |
| 各语言 profile 数：python 133 / typescript 135 / cpp 212 / java 106 / golang 88 / javascript 82 / rust 51 / ruby 22 / php 3 / c 2 / csharp 1 | 同上脚本逐文件输出 | 2026-09-24 |
| 文档称"300+ 仓库（截至 12/2025）" | `docs/guides/env_construction.md:37` | 2026-09-24 |
| 程序化注入语言数 **8**（python/js/ts/php/java/ruby/rust/golang/cpp 目录，TS 复用 JS） | `ls swesmith/bug_gen/procedural/`；`procedural/typescript/__init__.py:8` | 2026-09-24 |
| `MAP_EXT_TO_MODIFIERS` 覆盖 **14** 个扩展名 | `procedural/__init__.py:20-35` | 2026-09-24 |
| Modifier 类去重总数 **50** | `grep -rhn "^class .*Modifier" swesmith/bug_gen/procedural/ \| sed ... \| sort -u \| wc -l` | 2026-09-24 |
| Python modifiers **13** 个 | `procedural/python/__init__.py:25-39` | 2026-09-24 |
| JavaScript **14** / PHP **14** / Java **15** / Cpp **15** / Ruby **20** / Rust **10** / Golang **10** 个 modifier | 各语言 `__init__.py` 的 `MODIFIERS_*` 列表 | 2026-09-24 |
| `MODIFIERS_TYPESCRIPT = MODIFIERS_JAVASCRIPT`（TS 无独立实现） | `procedural/typescript/__init__.py:8` | 2026-09-24 |
| `CommonPMs` 枚举 **17** 个成员 | `procedural/base.py:58-145`，脚本计 `CommonPMProp(` 出现数 | 2026-09-24 |
| `DEFAULT_PM_LIKELIHOOD = 0.2` | `swesmith/constants.py:15` | 2026-09-24 |
| `max_attempts = 5` / `min_complexity = 3` / `max_complexity = inf` | `procedural/base.py:17-19` | 2026-09-24 |
| 随机种子默认 `seed=24` | `procedural/base.py:26`；`procedural/generate.py:201`；`issue_gen/get_static.py:86` | 2026-09-24 |
| `FLIPPED_OPERATORS` 映射 **25** 条 | `procedural/python/operations.py:7-33` | 2026-09-24 |
| `timeout = 90` 秒（单题）/ `timeout_ref = 900` 秒（整仓基线）为**默认值**；但 profile 层有 **115 处**覆盖 `timeout`（java 105 / ruby 6 / golang 2 / rust 1 / javascript 1），取值 **400×65、300×42、180×6、120×2** | `profiles/base.py:108-109`；`grep -rn "^\s*timeout: int = " swesmith/profiles/*.py` | 2026-09-24 |
| `timeout_ref` 亦有一处覆盖：`golang.py:403` 把 900 秒改为 120 秒 | `profiles/golang.py:403` | 2026-09-24 |
| Python 默认 `test_cmd`（pytest --disable-warnings --color=no --tb=no --verbose） | `profiles/python.py:32-36` | 2026-09-24 |
| 各语言默认 test_cmd：Go `go test -v ./...` / Rust `cargo test --verbose` / JS vitest / PHP `vendor/bin/phpunit --testdox` / Java mvn + gradle | `golang.py:26`、`rust.py:22`、`javascript.py:329,362`、`php.py:23`、`java.py:211,238` | 2026-09-24 |
| Java(Gradle) 覆盖 `timeout = 300`、Java(Maven) 覆盖 `timeout = 400`（115 处覆盖中的样例，不是唯一覆盖处） | `profiles/java.py:239`、`profiles/java.py:264` | 2026-09-24 |
| `min_testing = True` 的 Python profile **13** 个 | `grep -c "min_testing: bool = True" swesmith/profiles/python.py` | 2026-09-24 |
| `min_pregold = True` 的 profile **4** 个 | `grep -rn "min_pregold: bool = True" swesmith/profiles/*.py \| wc -l` | 2026-09-24 |
| `eval_sets` 标注出现 **22** 处 | `grep -rn "eval_sets" swesmith/profiles/*.py \| wc -l` | 2026-09-24 |
| 有效题门槛 `n_f2p == 0 or n_p2p == 0` → 丢弃 | `harness/gather.py:336` | 2026-09-24 |
| PR Mirror 例外 `pr_exception`（允许 P2P 为 0） | `harness/gather.py:335` | 2026-09-24 |
| 造题判分四分类 `FAIL_TO_PASS / PASS_TO_PASS / FAIL_TO_FAIL / PASS_TO_FAIL` | `harness/grading.py:61-90` | 2026-09-24 |
| 造题阶段 `PASS_TO_FAIL` 重命名为成品题 `FAIL_TO_PASS` | `harness/gather.py:346-348` | 2026-09-24 |
| 测试输出哨兵 `>>>>> Start Test Output` / `>>>>> End Test Output` | `constants.py:35-36`；`harness/utils.py:249-251` | 2026-09-24 |
| `GIT_APPLY_CMDS` 三级兜底（含 `patch --batch --fuzz=5 -p1 -i`） | `constants.py:40-44` | 2026-09-24 |
| F2P 测试文件在推分支前被删除并单独提交 | `harness/gather.py:539-558` | 2026-09-24 |
| eval 阶段用 `git checkout HEAD~1` 找回"有测试 + 有 bug"状态 | `harness/utils.py:193-205` | 2026-09-24 |
| 镜像仓创建时 `rm -rf .git; git init` | `profiles/base.py:372-387` | 2026-09-24 |
| PR Mirror 先尝试直接 apply 原 patch，成功则 `cost: 0` / `direct_patch: True` | `mirror/generate.py:284-304` | 2026-09-24 |
| PR Mirror 筛选阈值 `max_files=8` / `max_lines=500` / `max_file_lines=10000` | `mirror/generate.py:70-101` | 2026-09-24 |
| PR Mirror 恢复用 LM，`temperature=0` | `mirror/generate.py:168-181` | 2026-09-24 |
| PR Mirror 原 PR 存为 `ref__pr_<N>.diff` + metadata 的 `instance_ref` | `mirror/generate.py:186, 214-220` | 2026-09-24 |
| `instance_ref` 不进成品题（成品只写 6 个字段） | `harness/gather.py:343-353` | 2026-09-24 |
| issue_gen `n_instructions` 默认 1、`max_var_tokens` 默认 10000 | `issue_gen/generate.py:170-171` | 2026-09-24 |
| issue_gen 推理 `temperature=0`；demonstration 取前 2 条；test_funcs 取前 5 条 | `issue_gen/generate.py:386`；`configs/issue_gen/ig_v2.yaml:32,57` | 2026-09-24 |
| issue_gen 断言输入必须是 gather 的产物 | `issue_gen/generate.py:224-227` | 2026-09-24 |
| **issue_gen 目录无任何输出侧泄漏校验**（`leak`/`forbidden`/`filter` 关键词零命中） | `grep -rn "leak\|filter.*problem_statement\|def validate\|forbidden" swesmith/issue_gen/` → 无输出 | 2026-09-24 |
| 静态题面**故意**包含文件名 / 函数名 / 测试名 | `issue_gen/get_static.py:30-53`；权重池 `:74-84`（9 个模板，权重 0.05~0.15） | 2026-09-24 |
| 二次语法校验只有 Java(16 处) / Ruby(14 处)，其余语言 0 处 | `grep -rc "validate_syntax" swesmith/bug_gen/procedural/<lang>/` 逐语言统计 | 2026-09-24 |
| `adapters/c.py` / `adapters/c_sharp.py` 无 `complexity` 实现 → 继承 `-1` | `grep -c "def complexity" swesmith/bug_gen/adapters/c.py c_sharp.py` → 0；`constants.py:109-111` | 2026-09-24 |
| `procedural/` 下无 C / C# 目录 | `ls swesmith/bug_gen/procedural/` | 2026-09-24 |
| Modal 批量：`MODAL_TIMEOUT = 10*60`、`SANDBOX_RATE_LIMIT = 4`、`PREGOLD_TIMEOUT = 500`、`MIN_PATCHES_FOR_VALIDATION = 50` | `scripts/bug_gen_modal.py:127,128,147,148` | 2026-09-24 |
| Modal 软超时留 60 秒缓冲 | `scripts/bug_gen_modal.py:549, 686` | 2026-09-24 |
| LM 调用重试：10 次、指数退避 4~60 秒 | `issue_gen/generate.py:112-118` | 2026-09-24 |
| 难度映射 `<15 min`=1 / `15min-1h`=5 / `1-4h`=9 | `train/difficulty_rater/get_difficulties.py:25` | 2026-09-24 |
| 难度训练集用 `frac=0.2, random_state=42` 切分，`>4 hours` 并入 `1-4 hours` | `train/difficulty_rater/create_datasets.py:46-47, 59-60` | 2026-09-24 |
| 难度推理并发 4 线程、`max_tokens=64` | `get_difficulties.py:79, 36` | 2026-09-24 |
| 难度对比表：SWE-bench 5.014 / Verified 3.960 / LM Modify 3.304 / LM Rewrite 5.272 / Procedural 3.596 / PR Mirror 4.876 / Combine 5.720 | `docs/guides/difficulty_rating.md:37-47` | 2026-09-24 |
| combine 默认 `num_patches=2` / `max_combos=100` / `depth=3` | `combine/same_file.py:137-153`；`combine/same_module.py:230-256` | 2026-09-24 |
| combine 只吃已验证补丁（`validated_inst_ids`） | `combine/same_file.py:55-60`；`combine/same_module.py:152-158` | 2026-09-24 |
| README 自述：52k task instances | `README.md:51` | 2026-09-24 |
| README 自述：SWE-agent-LM-32B 在 SWE-bench Verified 上 40.2% pass@1 | `README.md:65` | 2026-09-24 |
| README 自述：相比基线 +32% | `README.md:60` | 2026-09-24 |
| README 自述：26k trajectories（其中 5k 用于训练） | `README.md:66` | 2026-09-24 |
| README 自述：250+ Docker 环境 | `README.md:67` | 2026-09-24 |
| CONTRIBUTING 自述：约 4 万条任务缺题面，生成一条约 $0.02 | `CONTRIBUTING.md:122-123` | 2026-09-24 |
| 文档称程序化手法"13 (and counting)" （只符合 Python） | `docs/guides/create_instances.md:108` | 2026-09-24 |
| 不支持 Windows / macOS | `README.md:37-38` | 2026-09-24 |
| HF 数据集标识 `SWE-bench/SWE-smith` | `constants.py:17` | 2026-09-24 |
| 镜像 image_name 格式 `{org_dh}/swesmith.{arch}.{owner}_1776_{repo}.{commit[:8]}` | `profiles/base.py:207` | 2026-09-24 |
| 容器内存上限 `10g`、平台 `linux/x86_64` | `profiles/base.py:508-509`；`harness/utils.py:150-151` | 2026-09-24 |
| 仓库无 `.git`，无法取提交历史 | `ls -la` 输出无 `.git` | 2026-09-24 |
| `AGENTS.md` 全文 2 行（含一条 `modal run` 命令） | `AGENTS.md:1-3` | 2026-09-24 |
| 难度打分 HF 检查点链接为空 | `docs/guides/difficulty_rating.md:9` → `[HuggingFace checkpoint]()` | 2026-09-24 |
| 程序化造题的整体成功率 | **未确认**（代码只在 `bug_gen/utils.py:36-42` 打一行 warning，无汇总统计） | 2026-09-24 |
| `scripts/cheatsheet.sh` 内容 | **未确认**（`CONTRIBUTING.md:103` 引用，但文件未在快照中） | 2026-09-24 |
| `swesmith/bug_gen/llm/criteria.py` | **未确认**（`configs/bug_gen/README.md:13,22` 引用，但快照中不存在；`class_basic.yml:2` 写 `criteria: all`） | 2026-09-24 |
| 各语言 tree-sitter 语法错误率 | **未确认**（无统计代码） | 2026-09-24 |

---

### 取舍台账

### 取舍 1：合成题 vs 真题的真实性差距

- **选了什么**：用"注入 bug + 复用现有测试"替代"等待真实 PR"。换来了数量从 2,294（SWE-bench）到 52,000（README 自述）的跃升。
- **放弃了什么**：题目与真实开发者困境的对应关系。真实 issue 背后的 bug 往往来自跨模块的、有历史包袱的设计问题；注入 bug 是单点、局部的改动。
- **代价具体落在哪**：`docs/guides/difficulty_rating.md:37-47` 的量化表——Procedural 路线平均 **3.596** 分，SWE-bench 是 **5.014**，Verified 是 3.960。也就是说程序化合成题**比 SWE-bench Verified 还简单**，hard 类只占 2.3%（23/1000），而 SWE-bench 的 hard 占 19.4%（446/2294）。用这批数据训出来的模型，可能在"简单 bug 的快速定位"上很强，但在"复杂重构"上没被训练到。论文自己的应对是把 LM Rewrite（5.272）和 Combine（5.720）两条路一起上，靠 **Combine 的高难度来拉平分布**——但这意味着数据集的难度形状是**人为调出来的**，不是自然分布。

### 取舍 2：程序化注入 vs 大模型注入

- **选了什么**：程序化作为主力（`scripts/bug_gen_modal.py:563` 的批量流水线只调 `procedural.generate.main`），LM 作为补充。
- **放弃了什么**：程序化的"可复现 + 零成本 + 可枚举"换掉了 LM 的"像真人"。
- **代价具体落在哪**：
  - **成本**：程序化 metadata 里 `cost = 0.0`（`procedural/python/base.py:47`）；LM 路线每条都带真实 `cost`（`llm/modify.py:107` 调 `completion_cost`）。规模化时这是数量级差距，也是 Modal 流水线只走程序化的直接原因。
  - **多样性质量**：程序化的改法是有清单的（`CommonPMs` 17 种 + 各语言特有的），**一个聪明点的模型只要记住"这题是把 `<=` 改成 `<`"，就能反向猜出答案**。LM 的改法理论上无上限（`lm_modify.yml:3-12` 列了 9 类建议但加了 "please do!" 鼓励模型自由发挥）。
  - **可复现性**：程序化 `seed=24` 写死在多处（`procedural/base.py:26`、`procedural/generate.py:201`、`issue_gen/get_static.py:86`），任何人能重跑出完全一样的题；LM 的 `temperature=1`（`llm/modify.py:95`）意味着**每次跑出的题都不一样**，论文里的实验无法精确复现。

### 取舍 3：覆盖多语言（11 种 profile / 8 种程序化）vs 每种都做深

- **选了什么**：广覆盖。profile 层支持 11 种语言（835 个具体类），程序化注入支持 8 种。
- **放弃了什么**：每种语言的工程深度。最明显的证据是**语法安全只做了 2/8**：Java 16 处 `validate_syntax` 调用、Ruby 14 处，JavaScript / PHP / Rust / Golang / CPP 全 0 处。
- **代价具体落在哪**：
  - **无效 patch 被下游兜住**：不做复检的语言产出的语法错误 patch，要在 `valid.py` 阶段起容器跑测试才能被发现——**每条垃圾 patch 消耗一次 90 秒容器**。没有复检，这个损耗比例就不可控。
  - **C / C# 只有 profile、没有程序化**：`procedural/` 下无对应目录；且 `adapters/c.py`、`adapters/c_sharp.py` 都缺 `complexity` 实现（`constants.py:109-111` 的默认 `-1` + `procedural/base.py:18` 的 `min_complexity = 3`），导致 `can_change()` 恒 False。这两门语言的题只能靠 LM / PR Mirror 路线出。
  - **文档口径漂移**：`docs/guides/create_instances.md:108` 说"13 (and counting) 种程序化手法"——那是 Python 的数量，全语言是 50 个类。文档跟不上代码的扩张速度。

### 取舍 4：题目难度分布可控 vs 自然

- **选了什么**：难度**可控**。`--num_patches`（combine 几个 bug）、`likelihood`（0.15~0.4 的动手概率）、`min_complexity`（3，或 Python 某些 modifier 提到 5/10）、`min_testing`（只跑相关测试，能提高通过率从而让更多题活下来）——都是可调的旋钮。
- **放弃了什么**：难度分布的自然性。真实 bug 的难度由软件工程规律决定；SWE-smith 的难度由**筛选题的护栏强度**决定——P2P 越多的题越难通过（因为改动容易碰到护栏），F2P 越多的题越难解。
- **代价具体落在哪**：
  - **难度变成筛选的副产品，而不是设计的产物**。`gather.py:336` 的 `n_p2p == 0 → 丢掉` 这一条，直接把"改动面很窄但很致命"的题留下了，把"改动面很宽"的题滤掉了。也就是说**系统在无意中偏向了"小范围精准破坏"这一类 bug**。
  - **`repair.py` 会进一步扭曲难度**：它把失败的 F2P 测试从题里剔除（`repair.py:186-190`），保留题目。反复修之后，一道题可能只剩 1 条 F2P——**这题的难度已经名不副实，但代码里不留退化记录**。
  - **Combine 是唯一"故意的加难"旋钮**：`--num_patches 3` 把同一文件里 3 个 bug 合成一道题（`combine/same_file.py:84-88`），难度分 5.720 是全表最高。但这个旋钮的代价是**能组合的题数量急剧下降**（要求同一文件里有多条已验证的 patch，`combine/same_file.py:79-81`：`if len(patch_files) <= 1: continue`）。

### 取舍 5：判分只依赖仓库自带测试

- **选了什么**：完全不新增测试。判分标准 = 仓库现有测试套件的通过状态变化。
- **放弃了什么**：对"测试覆盖率低的仓库"的适配能力。测试跑不到的地方，注入的 bug 无法被验证，题就被丢掉。
- **代价具体落在哪**：
  - **有效的只测"被测试覆盖的代码"**。`extract_entities()` 会排除测试文件本身（`profiles/base.py:466-467` 调 `self._is_test_path`），所以注入点都在业务代码里；但**能不能被验证取决于测试是否覆盖到**，这完全由上游仓库决定。
  - **基线必须能跑起来，否则整仓报废**。`valid.py:203-219`：整仓跑一次基线（`timeout_ref = 900` 秒），超时就 `shutil.rmtree(ref_dir)` 并 `continue`——**连一条题都不再验证**。同一个逻辑在 Modal 层是 `PREGOLD_TIMEOUT = 500` 秒 + 0 个测试通过就写 `error.txt`（`scripts/bug_gen_modal.py:1362-1368`）。
  - **`min_testing` 是应对手段，但它自己引入风险**。它在 `profiles/python.py` 里开了 13 处，作用是"只跑相关测试文件"（`profiles/base.py:577-581`）。这缩短了验证时间，但**缩小的测试范围也可能漏掉真实的 P2P 回归**——`base.py:616-642` 那套"按文件名猜测试文件"的启发式，猜错就会让 P2P 列表不完整。
  - **引入了一整套"修坏题"的运维成本**。flaky 测试是这个设计的直接副作用，于是要额外写 `harness/repair.py`（285 行）来事后清理，而且它要同时改动三处状态（`logs/run_validation/` 目录、`logs/task_insts/*.json`、远程 git 分支，`repair.py:41-79`）——**这份运维复杂度，全部是"复用现有测试"这个决定带来的**。

---

### 给写稿人的「硬数字清单」

> 全部可从本地快照复核。格式：**数字 / 常量 / 函数名 —— 出处 —— 一句话说它是什么**

**A. 规模类**

1. **52k task instances** —— `README.md:51` —— SWE-smith 数据集总题量自述（对比 SWE-bench 的 2,294）。
2. **835 个 RepoProfile 类 / 832 个唯一 `owner/repo`** —— 对 `swesmith/profiles/*.py` 正则统计 —— 覆盖的真实仓库数（文档 `env_construction.md:37` 说"300+"，已过时）。
3. **11 种语言 profile + 8 种语言程序化注入** —— `swesmith/profiles/`（11 个语言基类）/ `swesmith/bug_gen/procedural/`（9 个目录，TS 复用 JS）。
4. **50 个 Modifier 类 / 17 个通用改错动作** —— `bug_gen/procedural/*/` 去重计数 / `procedural/base.py:58-145` 的 `CommonPMs` 枚举。
5. **Python 13 个 / JavaScript 14 / PHP 14 / Java 15 / Cpp 15 / Ruby 20 / Rust 10 / Golang 10 个 modifier** —— 各语言 `procedural/<lang>/__init__.py` 的 `MODIFIERS_*` 列表。
6. **26k trajectories（其中 5k 用于训练）** —— `README.md:66`。

**B. 判分类（最值钱的一组）**

7. **`n_f2p == 0 or n_p2p == 0` → 丢题** —— `harness/gather.py:336` —— 一道题合格的最低门槛：至少 1 条"改坏后变失败" + 1 条"改坏前后都通过"。
8. **`PASS_TO_FAIL` 重命名为 `FAIL_TO_PASS`** —— `harness/gather.py:346-348` —— 造题视角与解题视角的语义翻转，全仓库最易读错的一行。
9. **四分类 `PASS_TO_PASS` / `FAIL_TO_PASS` / `FAIL_TO_FAIL` / `PASS_TO_FAIL`** —— `harness/grading.py:61-90` 的 `get_valid_report()` —— 判分的基本数据结构。
10. **"测试名不在日志里"也算失败** —— `harness/grading.py:102-106` 的 `test_failed()` —— 宽松兜底，防止日志格式变化导致误判。
11. **F2P 测试文件在推分支前被 `os.remove`** —— `harness/gather.py:539-558` —— 防答案泄漏的核心动作。
12. **`git checkout HEAD~1` 找回"有测试 + 有 bug"状态** —— `harness/utils.py:193-205` —— 配合"每条分支两个 commit"的隐含约定。

**C. 阈值 / 超时类**

13. **`timeout = 90` 秒 / `timeout_ref = 900` 秒** —— `profiles/base.py:108-109` —— 单题测试超时 / 整仓基线超时的**默认值**（注意会被 profile 覆盖，见第 19 条）。
14. **`DEFAULT_PM_LIKELIHOOD = 0.2` / `max_attempts = 5` / `min_complexity = 3`** —— `constants.py:15` / `procedural/base.py:17-19` —— 默认动手概率 / 单次修改重试上限 / 实体复杂度下限。
15. **`seed = 24`** —— `procedural/base.py:26`、`procedural/generate.py:201`、`issue_gen/get_static.py:86` —— 全套随机性的固定种子，"同一仓库可复现"的基础。
16. **`MODAL_TIMEOUT = 600` / `SANDBOX_RATE_LIMIT = 4` / `PREGOLD_TIMEOUT = 500` / `MIN_PATCHES_FOR_VALIDATION = 50`** —— `scripts/bug_gen_modal.py:127,128,147,148` —— 云端批量造题的四个硬闸门。
17. **LM 重试 10 次、指数退避 4~60 秒** —— `issue_gen/generate.py:112-118` —— API 抖动兜底。
18. **PR Mirror 筛选：≤8 文件 / ≤500 行 / 单文件 ≤10000 行** —— `mirror/generate.py:70-101` 的 `should_attempt_recovery()`。
19. **Java(Gradle) `timeout = 300`（`profiles/java.py:239`）、Java(Maven) `timeout = 400`（`profiles/java.py:264`）** —— 注意：这**不是**全仓库唯一的 timeout 覆盖处。真跑统计：profile 层共 **115 处**覆盖 `timeout`（java 105 / ruby 6 / golang 2 / rust 1 / javascript 1），取值 **400×65、300×42、180×6、120×2**；另有 `timeout_ref` 一处覆盖 `golang.py:403`=120。

**D. 难度类**

20. **1 / 5 / 9 三档难度分** —— `train/difficulty_rater/get_difficulties.py:25` 的 `DIFFICULTY_SCORE` —— `<15 min fix`=1、`15 min-1 hour`=5、`1-4 hours`=9（注意是 5 和 9，不是 2 和 3）。
21. **SWE-bench 5.014 vs Procedural 3.596 vs LM Rewrite 5.272 vs Combine 5.720** —— `docs/guides/difficulty_rating.md:37-47` —— 合成题与真题的难度对比（Combine 最难的 5.720 > SWE-bench 的 5.014，Procedural 最易的 3.596）。
22. **程序化题里 hard 只占 2.3%（23/1000）** —— `docs/guides/difficulty_rating.md:45` —— 分布严重偏易的直接证据。

**E. 成本 / 泄漏类**

23. **生成一条题面约 $0.02；约 4 万条任务缺题面** —— `CONTRIBUTING.md:122-123`。
24. **`pm.name` + 8 位哈希构成 instance_id** —— `procedural/generate.py:56`、`constants.py:174-176` 的 `generate_hash()` —— 每一道题的唯一 ID 生成规则（`sha256 → random.Random → 8 位小写字母数字`）。
25. **二次语法校验只有 Java（16 处）/ Ruby（14 处）** —— `grep -rc "validate_syntax" swesmith/bug_gen/procedural/<lang>/` —— 8 种程序化语言里只有 2 种复查了语法。
26. **`rm -rf .git; git init`** —— `profiles/base.py:374-375` —— 镜像仓创建时抹掉原始历史，防 agent 从 `git log` 翻答案。
27. **镜像 image_name：`swebench/swesmith.x86_64.<owner>_1776_<repo>.<commit前8位>`** —— `profiles/base.py:207`。

---

*笔记完。所有数字均已用 `grep` / `wc` / 正则脚本在本地快照上实跑复核；无法取证的一律标注「未确认」，未做任何推测性填补。*


---

## 跨项目汇总 · 三级台阶对照

| 维度 | SWE-bench（真题） | OSWorld（真环境） | SWE-smith（自己造题） |
|---|---|---|---|
| 题面从哪来 | 真实 issue + 真实 PR | 人写的任务说明 | 代码改动反写成的 issue |
| 判分靠什么 | 仓库自带测试（F2P/P2P） | 用完之后的机器状态 | 仓库自带测试（F2P/P2P） |
| 判据最怕什么 | 测试**没跑起来**被当成通过 | 状态**取不到**被当成没做 | 答案**泄漏**在测试文件里 |
| 对应补丁 | `SUITE_RAN` 正则 + 退出码交叉验证 | `infeasible` 哨兵 + 三层 None 兜底 | 推分支前删测试文件 |
| 规模上限 | 受真实 PR 数量限制 | 受人工写题速度限制 | 目前 52k 题、26k 轨迹 |
| 单题成本 | 一次容器 + 一次测试 | 固定 80 秒等待 + 一次测试 | 程序化 0 成本 / 大模型约 $0.02 一条题面 |

**落点**：**考的越像真的，判据越要假设自己会被骗。** 这张表里最刺眼的一列是「判据最怕什么」——三家怕的东西各不相同，而它们各自都写下了针对性的补丁。一份能信的考卷，不是因为它难，是因为它的作者写下过「我在什么情况下会骗你」。
