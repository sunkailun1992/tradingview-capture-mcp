# 设计模式规范

## English summary

Keep the seams that make the flow testable without TradingView — the `ChartDriver` and `DesktopControl` protocols — and keep decisions in pure functions such as `readiness.judge` and `diagnostics.problems`. Avoid plugin systems, configuration-driven behaviour and abstractions with a single implementation besides the test fake.

## 要用的

- **Protocol 接缝**：`ChartDriver`（跑页面脚本）与 `DesktopControl`（启停桌面版）。真实实现是 `CdpDriver` / `RealDesktop`，测试用 `tests/fakes.py` 的 `FakeChart` / `FakeDesktop`。流程代码只依赖接缝。
- **纯函数做判断**：就绪判断 `readiness.judge`、自检 `diagnostics.problems`、请求校验 `capture.validate_request` 都不碰 I/O，便于逐条件测试。
- **错误码而不是异常类型树**：只有一个 `CaptureError`，用 `code` 区分；入口按 code 转成 MCP 错误或命令行 JSON。
- **依赖注入时间**：`run_capture` 接受 `sleep` 与 `clock`，测试用假时钟，不真等。
- **先写临时目录再整体改名**：每个品种的文件写进 `.partial-<次>`，成功后一次 `rename`，保证 `raw/<名>/` 要么完整要么不存在。

## 要避免的

- 插件系统、注册表、按配置切换行为：本项目只有一种采集方式。
- 只有一个实现的抽象类（测试替身除外）。
- 在页面脚本里写业务判断（例如"这个指标算不算信号"）：页面脚本只读原始数据，含义由调用方决定。
- 为了"以后可能"加的参数和开关；需要时再加，并补测试。
