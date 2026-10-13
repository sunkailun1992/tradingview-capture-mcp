# 参与贡献

## English summary

- Small fixes (typos, docs, clearly scoped bugs) can go straight to a PR. For new features or anything that changes the output format, open an issue first.
- Set up with `uv sync` and `git config core.hooksPath .githooks`; before pushing run `uv run pytest -q`, `node --test "tests/js/*.test.mjs"`, `uv run ruff check`, `uv run ruff format --check` and `bash scripts/check-private-content.sh`.
- Write commit messages and PR titles as English Conventional Commits, for example `fix(page): match the native export header`.
- External PRs are squash-merged after CI is green, the maintainer has reviewed and approved them, and every review conversation is resolved. First-time contributors' CI runs after the maintainer approves it.
- This repository is public. Never post real layout IDs, TradingView usernames, private indicator names or table contents, real screenshots, local paths or tokens in issues, PRs, logs or fixtures.

## 可以贡献什么

- TradingView 桌面版升级后的兼容修复（按 [AGENTS.md](AGENTS.md) 的修复流程）；
- 采集流程的缺陷修复、测试补强、文档改进；
- 对其他平台或网页版的支持：先开 issue 讨论范围。

本项目只负责导出图表数据和截图。上传、提交到外部服务、分析或交易相关的功能不在范围内，这类 PR 不会合并。

## 开始之前

- 新功能、改输出格式、改 MCP 工具参数：先开 issue 说明用途和方案。
- 错别字、文档小修、范围明确的缺陷修复：可以直接开 PR。

## 开发环境

```bash
git clone https://github.com/sunkailun1992/tradingview-capture-mcp.git
cd tradingview-capture-mcp
uv sync
git config core.hooksPath .githooks
```

需要 macOS 和 Node（页面脚本测试用内置测试运行器）。活体测试还需要已登录的 TradingView 桌面版，见 [TESTING_SPEC.md](docs/ai-coding/TESTING_SPEC.md)。

## 提交前检查

```bash
uv run pytest -q
node --test "tests/js/*.test.mjs"
uv run ruff check
uv run ruff format --check
bash scripts/check-private-content.sh
```

CI 跑两项检查：`test (macos-latest)` 与 `private-content`。

## 分支、提交与 PR

- **分支**：从最新 `main` 切分支，命名 `feat/<主题>` 或 `fix/<主题>`，一个 PR 只做一件事。
- **提交信息与 PR 标题**：英文 Conventional Commits，类型取 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`、`ci`，可带范围。
- **PR 描述**：按模板填写，中文或英文都可以。
- **合并条件**：CI 全绿、维护者审核确认是有益的改动并批准、评审对话全部解决，然后 squash 合并。首次贡献者的 CI 由维护者批准后运行。
- **已推送的分支不要 rebase 或强推**；需要更新就追加提交。

## 不要公开的内容

issue、PR、评论、日志、截图和测试夹具里都不能出现：真实布局 ID、TradingView 用户名、私有指标名与表格内容、真实图表截图、本机绝对路径、IP 地址、任何令牌。提交前钩子和 CI 会扫描，但请先自己确认。
