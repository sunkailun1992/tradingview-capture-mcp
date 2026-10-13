# 更新记录

本文件记录每个版本的变化，以及验证过的 TradingView 桌面版版本。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号用[语义化版本](https://semver.org/lang/zh-CN/)。

## 0.1.0 — 未发布

### 新增

- 以只监听本机的调试端口启动 TradingView 桌面版，按调用方给的 TradingView 代码逐个切换布局里的图表。
- 每个品种导出 `image.png`（TradingView 渲染）、`chart.csv`（与原生导出同列）、`data.json`（表格、标签、线、框、绘图、曲线最后值）和 `capture.json`（时间、SHA256、版本）。
- 开工自检：内部接口不可用时报 `TV_INTERNALS_CHANGED` 并整批停止；桌面版版本变化时在 manifest 标记。
- 切换后的就绪判断：等指标算完、两次读取一致、输出与上一个品种不同（或过了宽限期）。
- 后台任务、续跑失败的品种、批次锁；所有文件 0600、只新建。
- 7 个 MCP 工具（stdio）和对应的命令行。
- 私有内容扫描（提交前钩子与 CI）。

### 已知限制

- 只支持 macOS 与 TradingView 桌面版。
- 斐波各档价位的换算约定尚待用真实斐波验证。
