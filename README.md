# tradingview-capture-mcp

驱动 TradingView 桌面版，把图表数据和截图导出成文件，交给 Claude Code、Codex 等 AI 代理读取的 MCP 服务。

*An MCP server that drives TradingView Desktop and exports chart data and screenshots to files for AI agents such as Claude Code and Codex.*

> 非 TradingView 官方项目，与 TradingView, Inc. 没有关联。自动化使用 TradingView 可能与其服务条款冲突，请自行判断。
>
> *Not affiliated with TradingView, Inc. Automating TradingView may conflict with its terms of service; use it at your own discretion.*

## English summary

- **What it does:** starts TradingView Desktop with a loopback-only DevTools port, switches one layout through the TradingView codes you pass in, and writes per symbol: the chart as TradingView renders it (`image.png`), a CSV with the same columns as TradingView's own "Export chart data" (`chart.csv`), and the indicators' tables, labels, lines, boxes and drawings (`data.json`), including per-bar colours, fills, horizontal levels, which plots draw on the main chart from another pane, and each plot's last valid value (what the price scale keeps showing after a line stops).
- **Older history:** pass `history_from` (`YYYY-MM-DD`; CLI `--history-from`) and each chart first loads its older bars back to 00:00 UTC on that date, as scrolling left does, without moving the view. `chart.csv` then holds every loaded bar, and each symbol's `history` block says where the data starts (`firstBarTime`, `barsCount`), whether the date was reached (`reached`) and whether TradingView stopped sending older bars (`endOfData`). Without it nothing changes.
- **What it does not do:** choose symbols, analyse anything, or upload anything. The caller decides what to capture and how to check and use the data.
- **Requirements:** macOS, a logged-in TradingView Desktop that is fully quit before a capture (Cmd+Q; full screen or not makes no difference, the tool starts it with its own debugging port), Python 3.12+ and uv.
- **Keep only today:** `output_prune` (CLI `prune`) lists the batches from before today and, with `apply`, moves them to the macOS Trash; it never deletes anything for good.
- **Use it:** install with `uv tool install git+https://github.com/sunkailun1992/tradingview-capture-mcp`, register `~/.local/bin/tradingview-capture mcp` (absolute path) as a stdio MCP server, call `capture_start`, poll `capture_status`, then read with `batch_summary`, `symbol_data` and `image_crop`. Update with `uv tool upgrade tradingview-capture-mcp`.

## 它做什么

- 按调用方给出的 TradingView 代码清单逐个切换图表，每个品种导出四个文件：
  - `image.png`：TradingView 自己渲染的图表；
  - `chart.csv`：列名、列序和数字写法与 TradingView 的"下载图表数据"一致；
  - `data.json`：指标画出的表格（逐格原文与颜色）、标签、线、框、绘图端点与档位，每条曲线的样式、最后值和最后一个有效值，逐根 K 的颜色（曲线、填色、K 线、背景），填色带与水平线，以及工具没能导出的部分（`notExported`）；
  - `capture.json`：各步时间、文件 SHA256、工具与桌面版版本。
- 切换后等图表真正就绪才读：指标算完、相邻两次读取的结构一致、输出和上一个品种不同。就绪证据（等了多久、是否重新切换、哪些指标读取时仍在跳动、哪些和上一个品种相同）写进 `data.json`，供调用方核对。
- 要多年历史时（例如校准要的 1 小时 K 线从 2019 年起），传 `history_from`：每个品种就绪后先把历史载入到那一天（或 TradingView 给得到的最早一根），再照常读取，`chart.csv` 里就是全部载入的 K 线。不传时行为和输出与以前完全一样。
- 采集在后台进程里跑，过程中不消耗代理的 token；代理只发起采集、读结果。
- 布局里要求的指标缺了（`STUDY_MISSING`）或被隐藏了（`STUDY_HIDDEN`，图例上的眼睛被关掉）都会当场停下，不会产出缺一块的数据。
- 只保留当天的批次：`output_prune` 列出今天以前的批次，加 `apply` 时把它们移到废纸篓，从不永久删除。

## 它不做什么

- **不决定采什么**：品种清单、布局 ID、必需指标都由调用方在调用时传入，工具不保存任何业务配置。
- **不分析、不上传**：数据怎么核对、怎么用、要不要提交到别处，都由调用方负责。工具没有任何上传或写外部服务的接口。
- **不乱动图表**：页面里的改动只有两种：切换品种和周期，收尾时恢复原值；传了 `history_from` 时向 TradingView 要更早的 K 线，和往左拖动图表时它自己做的一样，只是多载入历史，不移动视图、不改缩放，换品种就丢掉。不点菜单、不改指标参数、不动绘图、不建警报。

## 要求

- macOS，已安装并登录 TradingView 桌面版；
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)；
- 开始采集前，桌面版必须完全退出（⌘Q，只关窗口不够；全屏还是窗口都一样）：调试端口只能在启动时打开，工具会自己用只监听本机的调试端口启动它，采完再退出。已经开着时 `capture_start` 当场报 `TV_ALREADY_RUNNING`、什么都不建，退出后再调一次即可；采集中途才打开导致停下的批次，用 `capture_retry` 续跑。工具不会替你关掉它。

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
| `output_prune` | `prune` | 列出 `output_root` 下今天以前的批次；`apply` 时移到废纸篓（不永久删除） |

`output_dir` 必须是绝对路径，父目录已存在且在 `output_root` 之下，目录本身还不存在。命令行示例：

```bash
uv run tradingview-capture doctor --layout <布局ID>
uv run tradingview-capture capture --foreground --layout <布局ID> \
  --symbol BINANCE:BTCUSDT.P --symbol BINANCE:ETHUSDT.P \
  --output-dir ~/tradingview-captures/2026-10-14
uv run tradingview-capture read --output-dir ~/tradingview-captures/2026-10-14 \
  --symbol BINANCE:BTCUSDT.P --part tables --series-last 5
```

错误一律带固定的错误码，例如 `TV_ALREADY_RUNNING`（桌面版已开着）、`TV_INTERNALS_CHANGED`（桌面版升级后内部结构变了）、`STUDY_MISSING`（布局里没有要求的指标）、`STUDY_HIDDEN`（要求的指标在布局里被隐藏）、`NOT_READY_TIMEOUT`（某品种迟迟没加载完，载入历史没完成时明细里 `reason` 为 `history`）、`TRASH_UNAVAILABLE`（系统没有 `/usr/bin/trash`，清理什么都没动）。

### 载入历史（history_from）

图表切到一个品种时只载入最近一段 K 线（1 小时图约 300 根）。要更长的历史时，`capture_start` 传 `history_from`（命令行 `--history-from`），写成 `YYYY-MM-DD`：

```bash
uv run tradingview-capture capture --foreground --layout <布局ID> --timeframe 60 \
  --history-from 2019-01-02 --symbol BINANCE:BTCUSDT.P --output-dir ~/tradingview-captures/history-2026-10-15
```

- 日期按 UTC 当天 00:00 算（`chart.csv` 的时间也是 UTC 秒），1800-01-01 及以后。
- 每个品种照常切换并就绪后，工具向 TradingView 要更早的 K 线，和往左拖动图表时它自己发的请求一样：每次最多 5000 根，按已载入 K 线的平均间隔估算到目标日期还差多少再多要一成，回来了再要，直到第一根不晚于目标日期，或 TradingView 表示不再给更早的。然后等各指标在更长的历史上重新算完，再导出。视图和缩放不动，截图仍是平常那一屏；换下一个品种时这些历史随之丢掉。
- 载入和指标重算共用一个 `ready_timeout_sec`；没在时限内完成时只这个品种失败（`NOT_READY_TIMEOUT`，`detail.reason` 为 `history`，卡在指标重算时 `detail.studyReason` 写明哪个条件没满足）。`capture_retry` 沿用原批次的参数（同一个 `history_from` 和 `ready_timeout_sec`），能补上偶发的慢；每次都超时，就把失败的品种用更大的 `ready_timeout_sec` 另开一批。
- `chart.csv` 包含全部载入的 K 线；有更早数据的品种，第一根可能比目标日期早一点（最多约最后一段差距的一成）。
- 每个品种的 `capture.json` 和 manifest 条目里多一个 `history`，`symbol_data` 的 `capture` 块里也有：

| 字段 | 含义 |
|---|---|
| `from` / `targetTime` | 调用方给的日期，和它在 UTC 00:00 的 UNIX 秒 |
| `firstBarTime` / `barsCount` | 导出时第一根 K 线的时间和总根数，与 `chart.csv` 一致 |
| `reached` | 第一根不晚于 `targetTime` |
| `endOfData` | TradingView 不再给更早的 K 线时带的标记（它自己的 `data_completed`），没有就是 `null`。实测见过两种：`end`，数据本来就从这里开始（例如合约的上市日）；`limit`，TradingView 只给到这里，更早的可能存在，但这个账户、这个周期拿不到（2026-10-15 实测：韩国交易所股票的 1 小时图只给到 2020-01-02，香港交易所股票到 2019-01-02） |
| `barsBefore` / `requests` / `waitedSec` | 载入前的根数、请求次数、载入加重算用的秒数 |

`reached` 为 `false` 而 `endOfData` 有值，说明 TradingView 已经给出它能给的全部历史，`firstBarTime` 就是数据的起点；两者都没有时品种会失败，不会悄悄只导出一部分。不传 `history_from` 时以上都不出现，输出与 0.2.0 逐字节相同（工具版本号除外）。

## 输出目录

```text
<output_dir>/
├── batch.json              # 开工参数（传了才有 history_from）、品种清单与其 SHA256、工具版本
├── job.json                # 后台任务进度
├── capture-manifest.json   # 每个品种的状态、文件 SHA256、就绪证据摘要（和载入历史的 history）；桌面版版本是否变化
├── attempts/               # 每次尝试的记录（含续跑）
└── raw/<代码安全名>/        # 例如 BINANCE_BTCUSDT.P
    ├── image.png
    ├── chart.csv
    ├── data.json
    └── capture.json
```

所有文件权限为 600、只新建不覆盖，目录为 700。

### data.json 里的指标数据

每个指标（`studies[]`）除了表格、标签、线、框和最后值，还有：

- `plots[]`：原生导出会带的每条曲线，含 CSV 列号、样式、`display`（Pine 的显示位：1 图上、2 数据窗口、4 价格轴、8 状态行）、`forceOverlay`（指标在别的窗格，这条却画在主图上）和 `lastValid`（最后一根有值的 K 的时间与数值；线停在过去时，价格轴上一直显示的就是它）。
- `colors[]`：每个着色器逐根 K 的颜色，压成 `[起始 K 时间, 结束 K 时间, 颜色]` 的连续段；`target` 指向它着色的曲线、填色或 K 线组，没有 `target` 的是整根 K 线或背景的颜色。颜色是 CSS 字符串，`null` 表示那几根 K 不画；`unresolved` 是调色板里查不到的次数。
- `fills[]`：两条曲线或两条水平线之间的填色（`between`），逐根 K 的颜色在 `colors` 里按 `target` 找。
- `bands[]`：水平线的名字、数值、颜色、是否显示。
- `visible`、`showLabelsOnPriceScale`、`format`：指标是否显示、是否在价格轴上标值、数值格式（`volume` 时 83424 显示成 83.42K）。
- `tables[]` 的 `position` 与 `cellColors`（逐格文字色和底色），标签的 `yloc`、`textAlign` 与 `colorCss` / `textColorCss`，线的 `colorCss`。这些颜色查不到时也写 `null`，所以另记一个数：`unresolvedGraphicColors`，不为 0 时 `null` 不一定是"没颜色"。
- `notExported`：工具没能导出的曲线类型和图元种类。不为空就是数据有缺口，不能当作"图上没有"。

## 只保留当天的批次

批次会越积越多。每天的采集用完以后（或者新一天第一次采集之前），先不带 `apply` 调一次看清单，再带 `apply` 调一次：

```bash
uv run tradingview-capture prune              # 只列出：今天的保留，今天以前的标成 wouldTrash
uv run tradingview-capture prune --apply      # 把今天以前的批次移到废纸篓
```

- 只动本工具在原处写下的批次：目录里有本工具的 `batch.json`，且批次自己的 `job.json` 记的就是这个目录。复制出来的副本（`job.json` 记的是原目录）、里面还套着别的批次的目录都不动，不跟随符号链接，不碰别的文件。新批次也不能建在另一个批次里面（`INVALID_ARGUMENT`）。
- "今天"按本机时区；一个批次最后一次开工、完成或续跑在哪天，就算哪天的。`--keep-days 2` 连昨天一起保留。
- 只移到废纸篓，从不永久删除；需要时可以从废纸篓放回。空间要等用户清空废纸篓才会释放，代理不要替用户清空。
- 采集进行中时 `--apply` 会报 `BATCH_LOCKED`，等批次结束再来。
- 调用方自己从批次里做出来、放在批次目录以外的文件（裁图、报告等），按调用方自己的规则清理。

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
