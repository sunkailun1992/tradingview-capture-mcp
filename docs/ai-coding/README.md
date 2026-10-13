# AI 编码规范索引

## English summary

These guides are written for this project only: a Python package that drives TradingView Desktop over CDP, runs fixed page scripts and writes private, create-only files. Read them in the order below; `AGENTS.md` at the repository root is the entry point and the single source of rules.

## 阅读顺序

| 顺序 | 文件 | 管什么 |
|---|---|---|
| 1 | [AI_CODING_GUIDE.md](AI_CODING_GUIDE.md) | 模块关系、数据流、新增页面脚本与 MCP 工具的步骤、版本号 |
| 2 | [AI_ENGINEERING_GUARDRAILS.md](AI_ENGINEERING_GUARDRAILS.md) | 风险分级、完成标准、本机与云端分工 |
| 3 | [SECURITY_CODING_SPEC.md](SECURITY_CODING_SPEC.md) | 端口、脚本、进程、文件、网络、日志、私有内容七条规则 |
| 4 | [TESTING_SPEC.md](TESTING_SPEC.md) | 单元、页面脚本、活体三层测试与夹具规则 |
| 5 | [AI_DIRECTORY_STRUCTURE_GUIDE.md](AI_DIRECTORY_STRUCTURE_GUIDE.md) | 每个目录放什么 |
| 6 | [AI_DESIGN_PATTERN_GUIDE.md](AI_DESIGN_PATTERN_GUIDE.md) | 接缝、纯函数、该避免的抽象 |
| 7 | [AI_COMMENT_STYLE_GUIDE.md](AI_COMMENT_STYLE_GUIDE.md) | 注释、docstring、文档语言 |

规则冲突时以根目录 `AGENTS.md` 为准；改规则改 `AGENTS.md` 或这里的对应文件，不在别处另写一套。
