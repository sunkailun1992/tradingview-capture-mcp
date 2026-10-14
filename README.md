# tradingview-capture-mcp

驱动 TradingView 桌面版，把图表数据和截图导出成文件，交给 Claude Code、Codex 等 AI 代理读取的 MCP 服务。

*An MCP server that drives TradingView Desktop and exports chart data and screenshots to files for AI agents such as Claude Code and Codex.*

> 非 TradingView 官方项目，与 TradingView, Inc. 没有关联。自动化使用 TradingView 可能与其服务条款冲突，请自行判断。
>
> *Not affiliated with TradingView, Inc. Automating TradingView may conflict with its terms of service; use it at your own discretion.*

## English summary

- **What it does:** starts TradingView Desktop with a loopback-only DevTools port, switches one layout through the TradingView codes you pass in, and writes per symbol: the chart as TradingView renders it (`image.png`), a CSV with the same columns as TradingView's own "Export chart data" (`chart.csv`), and the indicators' tables, labels, lines, boxes and drawings (`data.json`).
- **What it does not do:** choose symbols, analyse anything, or upload anything. The caller decides what to capture and how to check and use the data.
- **Requirements:** macOS, a logged-in TradingView Desktop that is fully quit before a capture (Cmd+Q; full screen or not makes no difference, the tool starts it with its own debugging port), Python 3.12+ and uv.
- **Use it:** install with `uv tool install git+https://github.com/sunkailun1992/tradingview-capture-mcp`, register `~/.local/bin/tradingview-capture mcp` (absolute path) as a stdio MCP server, call `capture_start`, poll `capture_status`, then read with `batch_summary`, `symbol_data` and `image_crop`. Update with `uv tool upgrade tradingview-capture-mcp`.

## 它做什么

- 按调用方给出的 TradingView 代码清单逐个切换图表，每个品种导出四个文件：
  - `image.png`：TradingView 自己渲染的图表；
  - `chart.csv`：列名、列序和数字写法与 TradingView 的"下载图表数据"一致；
  - `data.json`：指标画出的表格（逐格原文）、标签、线、框、绘图端点与档位，以及每条曲线的最后值；
  - `capture.json`：各步时间、文件 SHA256、工具与桌面版版本。
- 切换后等图表真正就绪才读：指标算完、相邻两次读取的结构一致、输出和上一个品种不同。就绪证据（等了多久、是否重新切换、哪些指标读取时仍在跳动、哪些和上一个品种相同）写进 `data.json`，供调用方核对。
- 采集在后台进程里跑，过程中不消耗代理的 token；代理只发起采集、读结果。

## 它不做什么

- **不决定采什么**：品种清单、布局 ID、必需指标都由调用方在调用时传入，工具不保存任何业务配置。
- **不分析、不上传**：数据怎么核对、怎么用、要不要提交到别处，都由调用方负责。工具没有任何上传或写外部服务的接口。
- **不乱动图表**：页面里唯一的改动是切换品种和周期，收尾时恢复原值；不点菜单、不改指标参数、不动绘图、不建警报。

## 要求

- macOS，已安装并登录 TradingView 桌面版；
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)；
- 开始采集前，桌面版必须完全退出（⌘Q，只关窗口不够；全屏还是窗口都一样）：调试端口只能在启动时打开，工具会自己用只监听本机的调试端口启动它，采完再退出。已经开着时报 `TV_ALREADY_RUNNING`，退出后对同一目录调 `capture_retry` 即可；工具不会替你关掉它。

## 安装与配置

用 uv 装一份独立副本，命令 `tradingview-capture` 会出现在 `~/.local/bin`：

```bash
uv tool install git+https://github.com/sunkailun1992/tradingview-capture-mcp
```

MCP 跑的是这份副本，不是开发目录，所以在仓库里切分支、改代码不会影响正在用的 MCP。`main` 有了新提交后更新：

```bash
uv tool upgrade tradingview-capture-mcp
```

本机配置写在 `~/.config/tradingview-capture-mcp/config.toml`，权限设为 600：

```toml
output_root = "~/tradingview-captures"        # 所有批次都写在这个目录之下，必须已存在；在 /Volumes 下的外置盘上时，盘必须已挂载
debug_port = 9333                             # 可选，默认 9333
app_path = "/Applications/TradingView.app"    # 可选
```

## 注册到 Claude Code 与 Codex

两边都写可执行文件的绝对路径（下面的 `<home>` 换成你的 home 目录），桌面应用启动 MCP 时不一定带着 shell 的 PATH：

```bash
claude mcp add --scope user tradingview-capture -- <home>/.local/bin/tradingview-capture mcp
codex mcp add tradingview-capture -- <home>/.local/bin/tradingview-capture mcp
```

`claude mcp get tradingview-capture` 显示 Connected、`codex mcp list` 里显示 enabled 就是注册好了；已经开着的会话要重开才看得到新工具。

## 用法

| MCP 工具 | 命令行 | 作用 |
|---|---|---|
| `capture_start` | `capture` | 开始一批采集，立即返回任务 ID |
| `capture_retry` | `capture --retry-failed` | 只重跑已有批次里失败和未完成的品种 |
| `capture_status` | `status` | 任务进度：完成数、当前品种、失败原因 |
| `batch_summary` | `status --summary` | 一批的总览：每个品种的状态和文件 SHA256 |
| `symbol_data` | `read` | 某个品种的结构化数据，可只取表格、标签、绘图等部分，或最近 N 根 K 线 |
| `image_crop` | `crop` | 按像素框裁 `image.png`；MCP 返回图像，命令行另存为文件 |
| `diagnose` | `doctor` | 检查桌面版里采集要用的内部接口是否可用，不返回图表内容 |

`output_dir` 必须是绝对路径，父目录已存在且在 `output_root` 之下，目录本身还不存在。命令行示例：

```bash
uv run tradingview-capture doctor --layout <布局ID>
uv run tradingview-capture capture --foreground --layout <布局ID> \
  --symbol BINANCE:BTCUSDT.P --symbol BINANCE:ETHUSDT.P \
  --output-dir ~/tradingview-captures/2026-10-14
uv run tradingview-capture read --output-dir ~/tradingview-captures/2026-10-14 \
  --symbol BINANCE:BTCUSDT.P --part tables --series-last 5
```

错误一律带固定的错误码，例如 `TV_ALREADY_RUNNING`（桌面版已开着）、`TV_INTERNALS_CHANGED`（桌面版升级后内部结构变了）、`NOT_READY_TIMEOUT`（某品种迟迟没加载完）。

## 输出目录

```text
<output_dir>/
├── batch.json              # 开工参数、品种清单与其 SHA256、工具版本
├── job.json                # 后台任务进度
├── capture-manifest.json   # 每个品种的状态、文件 SHA256 与就绪证据摘要；桌面版版本是否变化
├── attempts/               # 每次尝试的记录（含续跑）
└── raw/<代码安全名>/        # 例如 BINANCE_BTCUSDT.P
    ├── image.png
    ├── chart.csv
    ├── data.json
    └── capture.json
```

所有文件权限为 600、只新建不覆盖，目录为 700。

## 安全边界

- 调试端口只在采集期间开着，只监听 127.0.0.1；采完就退出由本工具启动的桌面版。端口开着时，本机任何进程都能连上并控制这个 TradingView 会话，这是已知风险。
- 只执行随版本固定的页面脚本，不接受调用方传入任意脚本。
- 只停止自己启动的那个进程，从不按进程名结束进程。
- 不读取也不保存 TradingView 账号凭据，不上传任何数据。

## 注意

- 同一个 TradingView 账号在别处（例如浏览器）同时在线时，可能被提示"在另一台设备上使用"而断开实时数据。
- 桌面版升级后若内部结构变了，工具会报 `TV_INTERNALS_CHANGED` 并停止；修复流程见 [AGENTS.md](AGENTS.md)。
- PNG 的尺寸等于桌面版窗口大小乘以屏幕像素比，实际尺寸记在 `capture.json`。需要每批一致，就保持桌面版窗口大小不变。
- 只采布局里当前激活的那个图表；多图布局里的其他图表不采。
- 采集进行中不要自己打开或操作 TradingView：macOS 上它只有一个实例，打开会激活采集用的窗口，批次结束时这个窗口会被关掉。

## 开发

```bash
git clone https://github.com/sunkailun1992/tradingview-capture-mcp.git
cd tradingview-capture-mcp
uv sync
git config core.hooksPath .githooks        # 提交前自动扫描私有内容
uv run pytest -q
node --test "tests/js/*.test.mjs"
uv run ruff check && uv run ruff format --check
bash scripts/check-private-content.sh
```

要让 MCP 临时跑本地改动，把注册的命令换成 `uv --directory <仓库路径> run tradingview-capture mcp`，试完再换回 `~/.local/bin/tradingview-capture mcp`。

规则与阅读顺序见 [AGENTS.md](AGENTS.md) 和 [docs/ai-coding/](docs/ai-coding/README.md)，参与方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache-2.0](LICENSE)
