# Podcastfy 借鉴与双人试播

2026-10-24。用户要求参考 Podcastfy，把适合现有播客的东西取下来。本轮增加独立双人合成与一份中文试播，保留当前每日节目。

## 取了哪些东西

参考版本固定为 [`053b54a`](https://github.com/souzatharsis/podcastfy/tree/053b54a0917e35edb2808049499292361ccaae7b)。13 份原始文件在 `references/podcastfy/upstream/`，包括许可与 NOTICE，校验清单在 `references/podcastfy/manifest.json`。

| 上游做法与出处 | 判断 | 本地落点 |
| --- | --- | --- |
| [角色分工与风格配置](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/conversation_config.yaml)，一个解释，一个追问澄清 | 值得用，追问要改变后续回答 | `config/dialogue.json`、`scripts/write-dialogue-prompt.md` |
| [长稿续写携带前文](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/content_generator.py)，区分开场、中段与结尾 | 借鉴写稿方法，保留当前宿主会话，不另装模型框架 | `scripts/write-dialogue-prompt.md`，属于执行规范，尚无自动长稿生成器 |
| [Person1/Person2 标签与双音色合成](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/tts/base.py)、[音频拼接](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/text_to_speech.py) | 适合现有 MiMo；按真实顺序处理，拒绝静默丢台词 | `scripts/tts_dialogue.py` |
| [多位说话者原生合成](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/tts/providers/geminimulti.py) | 保留代码参考，需要另一套模型与凭据；本轮没有接入或实测 | 仅下载源码，不把分角色拼接宣称为同等听感 |
| [网页、PDF、YouTube 资料入口](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/podcastfy/content_parser/content_extractor.py) | 可参考分工；抓到正文仍须核验，不能覆盖已有研究流程 | 仅保存参考，未新增自动资料导入 |
| [整套依赖](https://github.com/souzatharsis/podcastfy/blob/053b54a0917e35edb2808049499292361ccaae7b/pyproject.toml) | 现有宿主负责研究写稿、MiMo 负责声音，暂不需要再装 LangChain 等依赖 | 新入口只使用标准库、现有脚本和 ffmpeg |

## 怎么运行

输入是纯台词，沿用上游标签格式。

```xml
<Person2>分成几段以后，怎么接上前文？</Person2>
<Person1>下一段生成时，把已经写过的对话一起交给模型。</Person1>
```

必须有两个角色，标签必须闭合。允许 Person2 开场、同一个人接着补充，不强制按问答配对。未知标签、标签外的文字、空台词和嵌套标签均报错，防止有内容没被念出来。来源和双链放阅读页，不塞入口播。

先校验，**不读 Key、不调用合成、不创建音频**。

```bash
env -u PYTHONPATH python3 scripts/tts_dialogue.py \
  --input output/podcastfy-pilot/dialogue.txt \
  --output output/podcastfy-pilot/双人试播-AI合成.m4a --dry-run
```

实际合成。

```bash
env -u PYTHONPATH python3 scripts/tts_dialogue.py \
  --input output/podcastfy-pilot/dialogue.txt \
  --output output/podcastfy-pilot/双人试播-AI合成.m4a
```

`--config <json>` 换角色配置，`--limit 2` 只合成前两个发言轮次，报告会标为试听。其他稿件必须明确指定新的输出路径。入口不上传、不发消息，不改 `latest-script.md`、`latest-status.txt`、`episodes.log` 或定时任务。

## 声音与缓存

默认 Person1 为既有 MiMo 王振宇克隆音色，Person2 为 MiMo 预置「冰糖」，两者共用现有 Keychain 凭据。配置与风格指令只在内存覆盖，不修改云控制台配置。更换参考音必须使用项目内的人声文件。

音频保留原速，不用旧声线的 175 汉字每分钟估时，也不为试播套整期字数门槛。每段转为 24kHz 单声道 PCM，裁掉两端静音、统一到约 -18 LUFS 目标响度。换角色时留 160ms 间隔，连续同角色的分段不额外加间隔；最终再限幅并编码 m4a。这些是音频处理参数，不代表主观听感已通过。

段缓存放在输出目录旁的 `.dialogue-segments-<指纹>/`。指纹包含台词、角色、模型、音色、风格、参考音频内容哈希、分段结果和音频处理参数。中断或请求失败后同命令续跑，只调用尚未成功的段。缓存 WAV 会检查格式和实际帧数，半截文件不算完成。

所有段成功后才拼成隐藏的临时音频，完整解码成功后移到指定成品路径，同时写同名 `.json`，包含声音配置、稿件计划指纹、音频 SHA-256、每段时间点和实测秒数。成品存在且指纹、音频哈希匹配时直接复用；已有成品与本次输入不一致时要求另选输出名。

## 试播与验收

试播题目是「换成两个人聊天，真的更容易听懂吗」，用此次实际读取的代码说明分段衔接与追问的作用。854 汉字、12 个发言轮次。口播含 AI 合成和克隆音色声明；来源取舍在本页，台词文件不含非口播内容。

音频 `output/podcastfy-pilot/双人试播-AI合成.m4a`，实测 **199.64 秒，约 3 分 20 秒**。AAC、24kHz 单声道；完整解码通过，整体响度 -18.4 LUFS、真峰值 -2.0 dB。实际重跑复用了成品，额外合成调用为 0。

逐段时间点在同名 `.json`。独立验收与生产文件保护核对在 `output/podcastfy-pilot/verification.json`，9 份生产输入、状态、台账与配置的内容、大小、修改时间均未变化；上游 13 份文件校验一致。

测试入口 `env -u PYTHONPATH python3 -m unittest tests.test_tts_dialogue -v`，5 项通过，覆盖漏标签不丢稿、发言顺序、换声或换参考文件时缓存失效，以及真 ffmpeg 下模拟中断后续跑、完整成品零合成复用。既有 `tests.test_tts_mimo` 的 8 项也通过。技术通过与本人听感认可分开，本轮不据此切换日常节目。

## 相关

- [[write-dialogue-prompt]]
- [[AI周节目定时任务]]
- [[agent-map]]
