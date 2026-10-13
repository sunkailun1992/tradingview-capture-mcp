## 改动说明 / Summary

<!-- 做了什么、为什么。PR 标题请用英文 Conventional Commits，例如 `fix(page): match the native export header`。 -->

## 关联 issue / Related issue

<!-- 例如 Closes #<编号>；没有就写「无」 -->

## 风险等级 / Risk level

<!-- 见 docs/ai-coding/AI_ENGINEERING_GUARDRAILS.md；勾一个 -->
- [ ] 低 / Low
- [ ] 中 / Medium
- [ ] 高 / High（就绪判断、CSV 列规则、MCP 工具参数与输出格式）
- [ ] 极高 / Critical（页面脚本、启停进程、文件写入方式、调试端口、私有内容扫描）

## 验证 / Verification

- [ ] `uv run pytest -q`
- [ ] `node --test "tests/js/*.test.mjs"`
- [ ] `uv run ruff check` 与 `uv run ruff format --check`
- [ ] `bash scripts/check-private-content.sh`（无输出）

## 活体测试 / Live check

<!-- 改动影响真实 TradingView 桌面版行为时：写验证过的桌面版版本和结果；不涉及就写「不涉及」。不要贴真实截图、布局 ID 或表格内容。 -->
