# AI 编码指南

## English summary

- Data flows one way: caller arguments → `capture.run_capture` → `driver.ChartDriver.run(<page script>)` → files in the batch directory → `results` readers → CLI and MCP.
- Page scripts are the only code that touches TradingView's internals. Add one by writing the `.js` file, listing it in `page.SCRIPTS`, and testing it with the fake chart model in `tests/js/`.
- MCP tools and CLI commands are thin wrappers over the same functions; add both together.
- Versions follow SemVer; changing output files or MCP parameters is a breaking change.

## 模块关系

```text
cli.py / mcp_server.py        两个入口，参数校验之后调用同一套函数
        │
jobs.py                       后台进程（posix_spawn + setsid）、进度、续跑
        │
capture.py                    批次流程：自检 → 逐品种切换、等待、提取、截图、写文件 → manifest
   │        │         │
readiness.py  images.py  diagnostics.py
        │
driver.py                     ChartDriver / DesktopControl 接缝；CdpDriver、RealDesktop
   │            │
desktop.py     cdp.py         启停桌面版；DevTools 客户端
        │
page.py + page/*.js           固定页面脚本：alive、ready、switch、extract、screenshot、diagnose
        │
store.py / config.py / errors.py / validation.py   写文件、配置、错误码、输入格式
results.py                    读批次、读品种数据、裁图
```

## 数据流

1. 调用方传入布局 ID、TradingView 代码、周期、输出目录、必需指标。
2. `capture.run_capture` 拿批次锁，建目录，启动桌面版，跑 `diagnose` 自检。
3. 每个品种：`ready` 记下切换前的指纹 → `switch` → 轮询 `ready` 直到 `readiness.judge` 判定就绪 → `extract` 一次读完 → `screenshot`。
4. 文件先写进 `raw/.<名>.partial-<次>/`，全部成功后整目录改名为 `raw/<名>/`；失败的半成品移到 `attempts/<次>/`，从不删除。
5. 收尾恢复原品种和周期，退出桌面版，写 `capture-manifest.json`。

## 新增或修改页面脚本

1. 在 `tests/js/` 用 `fake_tv.mjs` 的假图表模型写一个失败的用例；数据一律编造。
2. 写或改 `src/tradingview_capture_mcp/page/<名>.js`：只读，参数只从 `ARGS` 读，返回可 JSON 化的值。
3. 新脚本要加进 `page.SCRIPTS`；不依赖 `common.js` 的脚本还要加进 `_STANDALONE`。
4. 跑 `node --test "tests/js/*.test.mjs"` 与 `uv run pytest -q`。
5. 能改变图表状态的只有 `switch.js`；任何新脚本都不得改变状态。

## 新增 MCP 工具或命令行子命令

- 先在 `results.py`、`jobs.py` 或 `capture.py` 写好函数和测试，再在 `mcp_server.py` 和 `cli.py` 各加一个薄包装。
- MCP 工具名和参数名用 snake_case；错误一律抛 `CaptureError`，入口负责转换成 `ToolError` 或 JSON 错误输出。
- 工具只能导出或读取数据；任何上传、提交或调用外部业务接口的工具都不在本项目范围内。

## 版本号

- 语义化版本：修复升修订号，兼容的新能力升次版本号，改输出文件结构或 MCP 参数升主版本号。
- 版本号同时改 `pyproject.toml` 与 `src/tradingview_capture_mcp/__init__.py`，并更新 `CHANGELOG.md`。
