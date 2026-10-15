# 测试规范

## English summary

Three layers: Python unit tests with fakes (`pytest`, warnings are errors), page-script tests in Node against a made-up TradingView chart model, and a local-only live test against a logged-in TradingView Desktop. Fixtures are always invented; never record real charts into the repository.

## 三层测试

| 层 | 命令 | 测什么 |
|---|---|---|
| 单元 | `uv run pytest -q` | 配置、写文件、CDP 客户端（本机假 WebSocket 服务）、启停（假桌面版脚本）、就绪判断、载入历史（假序列：按请求延迟应答、有最早时间、永不应答）、批次流程（`FakeChart` / `FakeDesktop` / `FakeClock`）、任务、读取、命令行、MCP |
| 页面脚本 | `node --test "tests/js/*.test.mjs"` | 每个页面脚本在 `fake_tv.mjs` 假图表模型上的返回值，包装方式与 `page.build()` 一致 |
| 活体 | `TRADINGVIEW_CAPTURE_LIVE=1 uv run pytest -m live -q` | 已登录的桌面版上采一个品种，私有输入来自 `TRADINGVIEW_CAPTURE_LIVE_*` 环境变量；另设 `TRADINGVIEW_CAPTURE_LIVE_HISTORY_FROM`（`YYYY-MM-DD`）时再采一次并载入日线历史到那一天。只在维护者本机运行，CI 不跑 |

## 规则

- 先写失败的测试，再写实现；修缺陷先写能复现的测试。
- pytest 把警告当错误（`filterwarnings = ["error"]`）：资源没关、弃用接口都会让测试失败。
- 测试里不真等：时间通过 `sleep` / `clock` 注入假时钟。
- 测试不碰真实 TradingView、真实输出根目录或用户配置；配置用 `TRADINGVIEW_CAPTURE_CONFIG` 指向临时文件。

## 夹具

- 一律编造：指标名用 `Alpha`、`Assist` 这类，代码用 `BINANCE:AAAUSDT.P` 这类，表格内容自拟。
- 不把真实页面录下来的数据、截图或表格放进仓库；需要用真实数据排查时放在仓库外的私有目录。

## TradingView 内部结构变了怎么补夹具

1. 用 `doctor` 找到失效的检查项和附近字段结构（只有字段名与数量）。
2. 在 `fake_tv.mjs` 里按新结构加一个变体（编造数据），在 `page.test.mjs` 写一个用新结构的失败用例。
3. 修页面脚本让新旧两种结构都通过（或明确放弃旧结构并升版本），再跑全部测试和一次活体检查。
