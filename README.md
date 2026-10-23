# 本地视频转写 Skill

在 Codex 中指定本地视频文件或目录，agent 使用本地语音识别模型转写，再派出可配置模型的子 agent 复核，生成 Markdown 文字稿。支持中英文及批量处理，面向 Windows 和 macOS；目前实测环境为 Windows。

## 安装

在 Codex 中请求安装仓库里的 skill 子目录：

```text
$skill-installer 安装 https://github.com/f4de01/video-to-text/tree/main/local-video-transcribe 中的 skill
```

也可以将完整的 `local-video-transcribe` 文件夹复制到 `~/.agents/skills/`，或项目的 `.agents/skills/` 下。必须包含 `SKILL.md`、scripts、references 和 config.json 等文件，不能只复制 SKILL.md。安装后在 skill 选择器中确认可见；若未出现，重启 Codex。参见 [Codex 官方 skill 文档](https://learn.chatgpt.com/docs/build-skills)。

安装只放置 skill 文件；首次转写时，agent 按[环境准备说明](local-video-transcribe/references/setup.md)建立 Python 环境并下载本地模型。

## 调用

在 Codex 对话中输入，不是在终端执行：

```text
$local-video-transcribe 转写 "D:\视频\课程.mp4"，输出到 "D:\转写结果"。主要语言为中文，复核使用 gpt-6-luna，推理强度 low，生成 Markdown 文字稿。
```

目录批量处理：

```text
$local-video-transcribe 转写 "D:\视频" 下的视频，包含子目录，输出到 "D:\转写结果"。复核使用 gpt-6-luna / low。
```

macOS 使用对应本地路径，例如 `/Users/me/Movies/课程.mp4`。默认不扫描子目录，需要时明确说明。关闭复核可以直接要求“仅本地离线转写，关闭模型复核”；输出会标记为未复核。

agent 负责环境检查、本地识别、子 agent 复核及输出校验，不需要手动逐条运行脚本。运行环境需能够读取指定文件、写入输出目录并调用指定模型的子 agent；所需权限仍受当前 Codex 环境约束。仅在终端运行 Python 脚本不会自动启动 Codex 子 agent。

## 结果与模型

- 每个视频输出 `transcript.md`，不生成 TXT 或 SRT。
- `changes.json` 记录修改理由和待核对项，`complete.json` 用于重复运行时跳过已完成文件。
- 成功后清除原始转写中间稿，源视频保持不变。
- 视频、音频在本地处理；启用子 agent 复核时，转写文字会交给 Codex 模型处理。

[config.json](local-video-transcribe/config.json) 可配置识别和复核模型。默认本地识别为速度优先的多语种 base、CPU INT8。默认复核名称保留原始用户偏好 `gpt5.6 luna / low`，该名称在本次环境中不可用；上面的示例显式覆盖为已实测的 `gpt-6-luna / low`。其他环境也必须检查实际模型可用性，skill 不会擅自替换。

Windows 流程及 Markdown 输出已实测；macOS、GPU 尚未实测。轻量模型在真实视频中的专名、口音和口语识别可能较差，文字复核不能保证恢复漏听内容。详见[测试记录](docs/testing/2026-10-23-smoke.md)。
