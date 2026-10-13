# 目录结构规范

## English summary

Source lives in `src/tradingview_capture_mcp/`, page scripts in its `page/` folder, Python tests in `tests/` (one `test_<module>.py` per module, shared builders in `helpers.py` and `fakes.py`), JavaScript tests in `tests/js/`, maintenance scripts in `scripts/`, and design records in `docs/superpowers/`. Nothing private and no generated output belongs in the repository.

## 目录

| 路径 | 放什么 |
|---|---|
| `src/tradingview_capture_mcp/` | 包源码，一个模块一种职责（见 AI_CODING_GUIDE 的模块关系） |
| `src/tradingview_capture_mcp/page/` | 随版本固定的页面脚本，随包一起发布 |
| `tests/` | `test_<模块>.py`；`helpers.py` 放构造 PNG、配置和批次的辅助函数，`fakes.py` 放假图表与假桌面版 |
| `tests/js/` | 页面脚本测试；`fake_tv.mjs` 是假的 TradingView 图表模型 |
| `scripts/` | 维护脚本：私有内容扫描、CSV 比对 |
| `.githooks/` | 提交前钩子，`git config core.hooksPath .githooks` 启用 |
| `.github/` | CI、依赖更新、CODEOWNERS、PR 与 issue 模板 |
| `docs/ai-coding/` | 本组规范 |
| `docs/superpowers/specs/`、`plans/` | 设计与实施计划，按日期命名 |

## 规则

- 测试文件与被测模块一一对应；跨模块的流程测试放在流程所属模块的测试文件里（例如批次流程在 `test_capture.py`）。
- 不提交采集输出、真实截图、`.venv/`、缓存、`.superpowers/` 工作区。
- 新增目录必须被构建、测试、CI 或文档引用，不留孤儿目录。
- 本机配置与私有词清单只放在 `~/.config/tradingview-capture-mcp/`，不进仓库。
