# Issue tracker: GitHub

本项目的任务和规格存放于 GitHub Issues，使用 gh CLI 操作。
仓库：f4de01/video-to-text。从本地 origin 推断目标仓库。

## 常用操作

- 创建：gh issue create --title "标题" --body-file <正文文件>
- 读取：gh issue view <编号> --json number,title,body,labels,comments
- 列表：gh issue list --state open
- 评论：gh issue comment <编号> --body-file <正文文件>
- 标签：gh issue edit <编号> --add-label <标签> 或 --remove-label <标签>
- 关闭：gh issue close <编号>

多行正文写入临时文件，通过 --body-file 传入。
子任务优先使用 GitHub 原生子任务；不可用时在子任务正文标注
“Part of #父任务编号”，并在父任务正文添加任务列表。

技能要求“发布到任务跟踪系统”时，创建 GitHub Issue；
要求“获取相关任务”时，读取对应 Issue。

## Pull requests as a triage surface

PRs as a request surface: no.
