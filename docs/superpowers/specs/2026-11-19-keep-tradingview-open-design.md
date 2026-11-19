# 让 TradingView 桌面版一直开着（0.5.0）

## English summary

Captures used to start TradingView Desktop for every batch and quit it at the end, so a scheduled caller restarted it every few minutes, startups often did not settle, and the user could not keep it open to look at charts. From 0.5.0 a batch uses a TradingView Desktop that already runs with this tool's loopback-only DevTools port as it is, opens one with the port when none runs and leaves it running (`keep_open`, default true), and refuses, without touching it, one opened without the port (`TV_ALREADY_RUNNING`). A separate capture window is not possible (CDP `Target.createTarget` answers "Not supported" in TradingView Desktop), so a batch still switches the layout's tab and puts its symbol and resolution back. The tool opens TradingView with three Chromium switches that keep background tabs from being slowed down; without them a 50 ms timer in a background tab took about one second.

## 背景

- 以前每一批都自己带调试端口启动桌面版、采完退出。定时调用方每几分钟一批，桌面版就反复重启；启动时布局常常载不稳，还要再等内部模型建好。
- 用户自己也要看图，希望桌面版一直开着；而开着的桌面版会让采集报 `TV_ALREADY_RUNNING`。

## 决定

| 桌面版当时 | 做法 |
|---|---|
| 带本工具的端口开着：监听者是 `pgrep -x TradingView` 列出的进程，地址只有 127.0.0.1 / [::1] | 接上去用，不启动、不关闭 |
| 没开 | `/usr/bin/open -g -a <app> --args --remote-debugging-port=<端口> <三个开关>`，等 DevTools 应答后再核对监听者和地址；`keep_open = true`（默认）时采完留着。`false` 时改为本进程直接启动可执行文件，采完退出 |
| 开着但没带端口 | `TV_ALREADY_RUNNING`（固定码不变），不碰它；消息里写明怎么带端口重开 |
| 端口被别的程序占着、或监听不在本机回环上 | `PORT_IN_USE` / `CDP_NOT_LOCAL`；用户的进程不停，刚打开的才停 |

- 要留着的桌面版用 `open` 打开：它成为用户会话里的普通应用（由 launchd 管、通知与权限归它自己），不继承本进程的环境，也不是某个批次进程的子进程，批次进程退出后不会留下僵尸进程。
- 给用户自己打开的入口：`tradingview-capture open`、MCP `desktop_open`，以及 `install-launcher` 生成的 `TradingView Capture.app`（AppleScript 小程序，运行 `open`，出错弹窗）。
- 清单的 `desktop` 块加 `launched`、`leftOpen`，调用方能看出这一批有没有付出启动的代价。

## 2026-11-19 探查记录（桌面版 3.4.1）

只读探查，不切换图表、不点界面；结论只记结构，不记布局、标题或内容。

- `open -g -a … --args --remote-debugging-port=<端口>` 能把端口传给桌面版：约 0.5 秒 DevTools 应答，`lsof` 显示监听者就是主进程，只在 127.0.0.1。
- 布局的每个标签页是一个独立的 page 目标；只有当前标签页 `visibilityState` 为 `visible`，其余为 `hidden`。
- 后台标签页里 `setTimeout(50)` 约 1000 毫秒才回来（每秒一次的后台限流）；前台标签页约 51 毫秒。窗口没有焦点（`-g`）不影响，被挡住或在后台标签页才影响。
- 带上 `--disable-background-timer-throttling`、`--disable-renderer-backgrounding`、`--disable-backgrounding-occluded-windows` 后，后台标签页隐藏超过 5 分钟，连续 12 次 20 毫秒定时器每次仍约 21 毫秒，没有出现每分钟一次的深度限流。
- 浏览器级 DevTools 的 `Target.createTarget` 返回 `Not supported`（Electron 没实现），`Target.getBrowserContexts` 没有额外上下文：没法给采集单开一个窗口或标签。桌面版自己的标签页只能点界面打开，超出本工具允许的动作。
- 两个空白 page 目标对 `Runtime.evaluate` 不应答；工具只在显示目标布局的标签页里运行页面脚本，不受影响。

## 不做的

- 不给采集单开窗口或标签，不点菜单，不改布局；画面在采集用的标签页里会切换，收尾恢复品种和周期，文档写明。
- 不从进程命令行里猜别的端口：几个调用方共用一个开着的桌面版时，靠各自配置里相同的 `debug_port`。
- 不强杀、不重启用户自己打开的桌面版。

## 风险

- 端口随桌面版一直开着，本机任何进程都能控制这个 TradingView 会话；不接受时设 `keep_open = false` 并照常从程序坞打开。
- 用户在采集用的标签页里切品种会和采集互相覆盖；工具最多重切 3 次。
- 桌面版会自动下载更新，重启后内部结构可能变化，照旧由 `TV_INTERNALS_CHANGED` 和 `desktopVersionChanged` 提醒。
