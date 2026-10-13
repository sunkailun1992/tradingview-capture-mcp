# 注释风格规范

## English summary

Comments are in English and explain why, not what. Python modules start with a one-line docstring; public functions get a one-line docstring when the name is not enough. Each page script starts with one comment line stating its job and whether it changes state. Markdown documentation is Chinese first with an English summary near the top.

## Python

- 模块第一行是一句英文 docstring，说明模块的职责。
- 函数名说不清的才写 docstring，一行为主；写行为和约束，不复述代码。
- 行内注释只写"为什么"：外部约束、反直觉的选择、与 TradingView 行为对齐的原因（例如 CSV 表头里缺右括号的 `(High`）。
- 不写过期的计划、TODO 或个人信息。

## JavaScript（页面脚本）

- 每个文件第一行一句注释：做什么，会不会改变图表状态。
- 依赖 TradingView 内部字段的地方写清依赖的是什么，便于升级后定位。

## Shell 与 YAML

- 脚本开头说明用途与退出码含义；YAML 只在不直观的设置旁注释原因（例如依赖更新延迟 7 天）。

## Markdown

- 中文为主，靠前放 `## English summary`。
- 不写真实布局 ID、用户名、指标名、本机路径；示例用 `<布局ID>`、`<仓库路径>`、`BINANCE:BTCUSDT.P` 这类通用写法。
