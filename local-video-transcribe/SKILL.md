---
name: local-video-transcribe
description: 将本地单个视频或目录中的视频转成中英文 Markdown 文字稿。在 Windows、macOS 本地运行语音识别，再由 Codex 派出指定模型的子 agent 修复，只交付修复稿。适用于视频语音转写，不包含画面 OCR。
---

# 本地视频转写

## 运行约定

在 Codex 中编排两阶段流程：本地 ASR → 子 agent 文本复核。默认采用多语种 base、CPU INT8、beam_size=1，优先速度；中文转简体，英文保留英文，不翻译、不总结、不区分讲话人。模型可更换，轻量识别的漏听不能靠文字修复可靠补回。

读取本 skill 的 `config.json`。`repair_model` 默认保留用户指定的 `gpt5.6 luna`，`repair_reasoning_effort` 默认 `low`；这是用户偏好名称，不是已验证的工具模型 ID。先检查当前运行环境的子 agent 工具支持哪些模型和推理强度，只有明确支持时才调用。若名称无法明确匹配，列出实际可用候选并让用户选择；不得静默替换、继承主模型冒充指定模型，或改走 API。用户可以临时覆盖，或要求修改配置。

语音识别完全本地；复核只发送转写文字及时间轴给 Codex 子 agent。首次可联网安装依赖和下载模型。用户可以关闭复核，改为仅离线转写；这时须将结果明确标为未复核，不能称作修复稿。

## 工作流程

1. 确定输入路径和输出目录。默认不扫描子目录；需要时加 `--recursive`。支持格式由脚本的 `EXTENSIONS` 定义。只读取源视频，不移动或改名。先完成上述复核模型检查，避免长时间识别后才发现无法复核。
2. 首次运行或环境缺失时读 [references/setup.md](references/setup.md)，创建隔离环境并准备本地模型。运行脚本 `--help` 了解参数。以下 `PYTHON` 指环境中 Python 的绝对路径，`SCRIPT` 指本 skill 的 `scripts/transcribe.py`；调用时将它们替换成真实路径，不把占位符直接交给 shell。
3. 执行：`PYTHON SCRIPT transcribe INPUT --model-dir MODEL_DIR --output OUTPUT`。需要覆盖修复模型时传 `--repair-model MODEL_ID --repair-effort low`；关闭复核则加 `--no-repair`。脚本输出 JSON 行：`pending` 包含 job 路径；`skipped` 表示相同输入和配置已经完成；`error` 表示该视频失败，其余视频继续。非零退出码时也处理已经生成的 pending job。
4. 对每个 pending job，读取其中 `job.json` 和 `chunk-*.json`。按 [references/repair.md](references/repair.md) 派出子 agent，显式传入配置模型和推理强度。若工具支持 `fork_turns`，使用 `none`，仅提供复核规则、分块路径及写入路径；不要继承整场对话或视频路径。并行数不得超过工具额度，默认至多两个修复子 agent；多个块可由同一个 agent 顺序完成。
5. 所有块完成后执行 `PYTHON SCRIPT finalize JOB_PATH`。脚本校验每块的段落 ID、数量、文字及修改理由，时间轴始终从原始段落取；任一块失败则整件不发布。允许让子 agent 按具体校验错误修正一次；再次失败就报告并保留待处理状态，不无限重试。
6. 最终文字稿为 `transcript.md`，以视频名为标题、按原讲话顺序分段，不添加总结或改写内容；不生成 TXT 或 SRT。结果目录中的 `changes.json` 和 `complete.json` 用于疑点记录与完成校验。修改记录只记录段落 ID、时间和修改理由，不存原文或逐字差异。原始段落及修复分块在成功发布后自动删除。只有全部输出落盘且校验完成才算成功；批量结果须说明完成、跳过、失败数量。

## 中断、重新处理与清理

中间文件位于输出目录 `.work/`，用于复核和中断恢复，不是交付物。识别时中断会在下次重新识别该视频；识别完成后中断则复用 job，继续缺失的复核块。报告失败时明确临时文件还在，并给出 `PYTHON SCRIPT clean JOB_PATH` 的清理命令。用户要求立即不保留中间文件时执行该命令，之后重试须重新识别。

完成标记绑定视频内容、源路径、识别参数和复核模型配置，并校验交付文件哈希；视频、配置变化会创建新结果目录。同名但不同路径的视频不会互相覆盖。若已完成文件被用户修改，脚本拒绝覆盖并报告冲突；选另一个输出目录重跑。

## 检验边界

不能把 JSON 结构校验描述为内容正确率验证。首次在目标设备上跑一段含中文、英文、静音的真实视频，检查是否漏转、专名是否正确；Windows 和 macOS 分别验证才可声称两端实测。工具不支持指定子 agent 模型时直接说明限制。
