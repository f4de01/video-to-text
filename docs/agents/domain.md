# Domain docs

## 布局与读取规则

本项目采用 single-context 布局：
- 根目录 GLOSSARY.md：项目领域术语。
- docs/adr/：架构决策记录。

探索代码前读取 GLOSSARY.md，并阅读与当前工作相关的 ADR。
文档不存在时直接继续；待术语或决策确定后，由 domain-modeling
按需创建，不预先生成占位文档。

## 使用术语

任务标题、方案、假设和测试名称使用 GLOSSARY.md 定义的术语。
遇到缺失概念时，先判断是否已有对应术语；确有缺口则记录，
交由 domain-modeling 完善。

## 决策冲突

方案与既有 ADR 冲突时，明确指出对应 ADR 和重新讨论的理由。
