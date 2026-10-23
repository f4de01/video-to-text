# 环境与模型准备

建议 Python 3.11 的 64 位环境。Windows 使用 x64 Python，macOS 使用对应 Intel/Apple Silicon 的原生 Python。先找现有解释器；没有时说明需安装 Python，再按该电脑已有的包管理器处理。不要修改全局 Python 包。

从 skill 目录执行。Windows PowerShell：

```powershell
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts/transcribe.py prepare --model base --model-dir models/base
& .\.venv\Scripts\python.exe scripts/transcribe.py transcribe 'D:\视频' --model-dir models/base --output 'D:\转写结果'
```

macOS：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/transcribe.py prepare --model base --model-dir models/base
.venv/bin/python scripts/transcribe.py transcribe '/Users/me/视频' --model-dir models/base --output '/Users/me/转写结果'
```

`prepare` 是显式联网阶段；已有模型直接指定目录。必须是 CTranslate2 Whisper 模型，包含 `model.bin`、`config.json`、`tokenizer.json` 和词表文件。不可使用 `.en` 英文专用模型处理中文。`transcribe` 设置 Hugging Face 离线标志并只加载本地目录；缺失文件时停止，不自动下载。

PyAV 提供音视频解码，一般无需另装 FFmpeg。CPU INT8 是两端通用基线；macOS 此后端使用 CPU，不承诺 Metal 加速。Windows 已具备兼容 CUDA/cuDNN 时可用 `--device cuda --compute-type float16`；失败时先说明原因，用户同意切换或已授权自动降级后再使用 CPU。GPU 依赖需按安装版本核对，不强行改动现有驱动。

`base` 是速度优先默认值；可通过 `prepare --model small` 准备更大多语种模型，并传对应 `--model-dir`。`config.json` 中 `asr_model` 控制 prepare 的默认模型；transcribe 实际使用显式指定目录，不会根据名字联网解析。先按静音停顿切分语音区域（最长约 20 秒），各区域独立识别语言并恢复全局时间轴，避免整段中文之后的英文被忽略。没有停顿的句内中英混说仍可能识别错误；特别短的片段也可能误判，可用 `--language zh` 或 `en` 固定主要语言。内部片段时间用于定位修改记录，不导出字幕。

复核不需要 API key 或另装 SDK，由当前 Codex 的子 agent 工具完成。只运行 Python 脚本不会自动启动 Codex 子 agent。

官方依据：
- [faster-whisper 安装、模型及解码](https://github.com/SYSTRAN/faster-whisper)
- [CTranslate2 平台支持](https://opennmt.net/CTranslate2/installation.html)
