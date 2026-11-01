# Required Study Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 等待必要指标齐全，容忍有期限的暂态空读，持续缺指标仍拒绝输出。

**Architecture:** 保留纯函数 readiness 判断及现有 driver/clock 接缝。调用方传入必要指标；抽取重读只使用原绝对期限的剩余时间，不改页面脚本或发布调用方。

**Tech Stack:** Python、pytest、Node 页面脚本测试。

**Spec:** 本轮授权：修复采集器就绪及暂态空读；缺指标不能入库，不改部分发布或量化程序。

## Global Constraints

- 只改采集器；MCP 参数、输出字段、只新建文件规则保持原状。
- 测试均为编造图表，不包含真实布局、指标、账号或采集内容。
- 真实桌面采集仍未授权；单元验证与活体验收分别报告。

## Review Focus

- 空、缺字段、部分集合及稍后恢复。
- ready 到 extract 之间再变空，永久缺失不能留下品种输出。
- 非整秒期限、慢读、历史加载及多次重读不延长期限。
- 错误身份、隐藏指标、无主图数据及损坏截图不能被重读放行。
- 未要求指标的调用，以及 unchanged/moving 证据保留。

## Tasks

- [x] 先写 readiness 缺指标及期限反例，确认 RED，再最小实现 optional required_studies。
- [x] 先写 capture 暂空恢复、持续缺失、期限及保护用例，确认 RED，再接入所有等待边界及有期限重读。
- [x] 检查历史加载剩余预算与原输出证据，补相邻路径回归。
- [x] 独立审查、完整 Python/Node 测试、ruff、私有内容扫描（339/29项通过）。
- [x] 同步文档与0.4.2修订版本，明确未更新安装、未手动活体采集。
