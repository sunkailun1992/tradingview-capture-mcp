# 安全政策

## English summary

- Report security problems privately: open the Security tab and click "Report a vulnerability". Never open a public issue for them.
- Include the affected version or commit, the steps to reproduce and the impact. Do not attach real screenshots, layout IDs or tokens.
- Supported versions: `main` until the first release; after that the latest release and `main`.
- In scope: the DevTools port listening beyond loopback or staying open, arbitrary script execution in the page, stopping processes the tool did not start, output files that others can read or that get overwritten, private content reaching the repository or logs, and anything that sends data off the machine.
- Out of scope: bugs in TradingView Desktop, Claude Code or Codex themselves, and what a caller does with the exported files.
- This is a volunteer project. We aim to acknowledge a report within 7 days and publish an advisory after the fix.

## 支持的版本

- 发布第一版之前：只支持 `main`。
- 发布之后：支持最新发布版本和 `main`。

## 如何报告

请私下报告，不要开公开 issue。

1. 打开本仓库的 Security 页面，点「Report a vulnerability」。
2. 写清影响的版本或提交、复现步骤、影响范围。
3. 报告里不要附真实截图、布局 ID、表格内容或令牌。

## 关注范围

下面这类问题在范围内，它们对应 [AGENTS.md](AGENTS.md) 的硬规则和 [SECURITY_CODING_SPEC.md](docs/ai-coding/SECURITY_CODING_SPEC.md)：

- 调试端口监听在 127.0.0.1 / [::1] 以外，或采集结束后仍然开着；
- 能让页面执行调用方传入的任意脚本；
- 结束了不是本工具启动的进程；
- 输出文件或目录能被其他用户读取，或已有文件被覆盖；
- 私有内容（布局 ID、用户名、指标名、表格内容、截图、本机路径、令牌）进入仓库、提交信息或日志，且 `scripts/check-private-content.sh` 没拦住；
- 工具把任何数据发到本机以外。

## 不在范围内

- TradingView 桌面版、Claude Code、Codex 自身的漏洞：请报给对应厂商。
- 调用方拿到导出文件之后怎么使用、上传到哪里。
- 采集期间调试端口开着这件事本身：这是文档写明的已知风险，见 [README.md](README.md) 的「安全边界」。
