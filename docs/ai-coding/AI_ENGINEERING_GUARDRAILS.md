# 工程门禁

## English summary

- Critical: page scripts, starting and stopping processes, how files are written, the DevTools port, the private-content scan. High: readiness, CSV column rules, MCP tools and output formats. Medium: readers, CLI parsing, docs that describe behaviour. Low: wording, comments.
- Done means: a test that failed first and now passes, the full suite and both linters green, the private-content scan clean, docs and CHANGELOG updated, and for Critical or High changes that touch TradingView a live check on the maintainer's machine.
- Live tests and anything that starts TradingView Desktop run only on the maintainer's machine; cloud sessions change code, run unit tests and CI only.

## 风险分级

| 等级 | 范围 | 额外要求 |
|---|---|---|
| 极高 | `page/*.js`、`desktop.py` 的启停、`store.py` 的写入方式、`prune.py` 移动目录的范围、调试端口、`scripts/check-private-content.sh` | 维护者审核；改页面脚本或启停逻辑时做一次活体自检 |
| 高 | `readiness.py`、CSV 列规则（`common.js` 的 `exportedPlots` / `plotTitle`）、MCP 工具与参数、输出文件结构 | 补齐失败用例；改输出结构要升主版本号 |
| 中 | `results.py`、`jobs.py` 的状态读取、命令行解析、描述行为的文档 | 单元测试 |
| 低 | 措辞、注释、不影响行为的整理 | 验证命令全过 |

## 完成标准（Definition of Done）

1. 先写的测试先失败、后通过；修缺陷时测试能复现原问题。
2. `uv run pytest -q`、`node --test "tests/js/*.test.mjs"`、`uv run ruff check`、`uv run ruff format --check` 全过；警告按错误处理，不能靠忽略警告过关。
3. `bash scripts/check-private-content.sh` 无输出。
4. 行为变化同步 README、相关规范与 `CHANGELOG.md`。
5. 极高、高风险且涉及 TradingView 行为的改动：在维护者本机做一次活体检查，PR 里写明桌面版版本和结果（不贴截图和表格内容）。

## 本机与云端分工

- 本机会话：可以启动 TradingView 桌面版做活体测试、`doctor` 和整批演练。
- 云端会话（没有已登录的桌面版）：只读改代码、跑单元测试与 CI；结论里写明"活体未验证，需本机执行"。
- 两边都要：开工、提交前、推送前各 `git fetch` 一次；远端前进了就在最新远端上 rebase 并重跑验证；禁止强推。

## 回滚

- 发布出问题时回退到上一个版本标签；输出格式不兼容时在 `CHANGELOG.md` 写明，提醒调用方。
