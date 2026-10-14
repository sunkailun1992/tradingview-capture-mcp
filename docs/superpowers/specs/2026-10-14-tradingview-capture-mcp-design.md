# tradingview-capture-mcp 设计文档

- 日期：2026-10-14
- 状态：待用户审阅
- 名称：`tradingview-capture-mcp`（仓库与 PyPI 发行名）；Python 包 `tradingview_capture_mcp`；命令行 `tradingview-capture`
- 许可：Apache-2.0。本项目不是 TradingView 官方项目，与 TradingView, Inc. 没有关联。

## 一页概览

- **做什么**：在本机驱动 TradingView 桌面版，按调用方给的品种清单逐个切换图表，每个品种采集三样东西：TradingView 自己渲染的图表 PNG；按原生「下载图表数据」列生成的 CSV；指标画出的表格、标签、线、框、绘图，以及每根 K 线的曲线值（`data.json`）。
- **给谁用**：Claude Code、Codex 等 MCP 客户端，以及命令行。代理只负责发起采集、读取结果，不再一步步截图和点击。
- **不做什么**：不分析行情，不下结论，不调用任何外部服务的写接口，不保存调用方的业务规则或私有信息。品种清单、布局、必需指标都由调用方在调用时传入。
- **怎么连**：Chrome DevTools Protocol（CDP）。桌面版带调试端口启动，端口只监听 `127.0.0.1`，只在采集期间开着。
- **平台与技术**：首版只支持 macOS；Python 3.12+，用 `uv` 管理依赖；MCP 用官方 Python SDK；页面内运行的是随版本固定的 JavaScript。
- **里程碑**：M0 可行性验证（2026-10-14 已完成，见附录 A）→ M1 采集核心与命令行 → M2 MCP 服务 → M3 与原生文件比对、整批演练 → M4 公开发布。

## 1. 背景与目标

让代理靠截图和点击去操作图表应用、再从像素里读数值，有两个问题：

1. **贵**：每个品种都要来回截图、确认、点菜单；如果要多遍读图，每个品种要看几十张图。
2. **不准**：曲线压住表格里的字、面板挡住标记、数字被截断的地方，只能记成"读不出"。

TradingView 桌面版是 Electron 应用，页面里的图表有完整的数据模型：指标表格的逐格文字、标签的文字和位置、每根 K 线的曲线值、绘图端点。直接读这些数据，采集过程可以不花代理的 token，读出的值也是准的。

**目标**

1. 一次调用采完一批品种，过程中不消耗代理的 token。
2. 输出可以审计：每个文件都有 SHA256、采集时间、工具和桌面版的版本号、就绪证据。
3. 代理只做轻量核对：读结构化数据，需要时裁图对照。
4. 桌面版升级导致内部结构变化时，自检能发现；代理可以照诊断报告修好。

**非目标**：分析和判断；替调用方决定采哪些品种；写入任何业务系统；Windows / Linux 和网页版 TradingView（首版不做，结构上不排斥）。

## 2. 调用方式

每次采集的参数都由调用方传入，工具本身不带任何业务配置：

| 参数 | 说明 |
|---|---|
| `layout` | TradingView 布局 ID，用来在桌面版的多个标签页里选中目标页，必须唯一命中 |
| `symbols` | 要采集的 TradingView 代码列表，例如 `BINANCE:BTCUSDT.P`，按给定顺序采 |
| `timeframe` | 周期，例如 `1D`。当前周期不符时先切换，收尾时恢复 |
| `output_dir` | 本批的输出目录，必须是绝对路径；父目录已存在且在本机配置的输出根目录之下；目录本身必须还不存在（续跑同一批除外），由工具创建 |
| `required_studies` | 自检时要求必须存在的指标名（按子串匹配），可不传 |
| `ready_timeout_sec` | 单个品种最长等待就绪的秒数，默认 60 |

MCP 工具名和参数名用 snake_case，输出文件里的 JSON 键用 camelCase。

本机配置放在仓库外的 `~/.config/tradingview-capture-mcp/config.toml`（0600），只放和这台机器有关、和业务无关的项：桌面版路径、调试端口、输出根目录。

## 3. 架构

| 模块 | 职责 |
|---|---|
| `desktop.py` | 启动、发现和退出桌面版：带 `--remote-debugging-port` 启动，核对端口只监听 127.0.0.1，记下自己启动的 PID；退出只针对这个 PID，先正常退出，超时再按 PID 结束，从不按进程名结束进程。桌面版已经在普通模式下运行时报错停止，不关用户的程序 |
| `cdp.py` | 最小 CDP 客户端：列出页面目标、按布局 ID 选页、`Runtime.evaluate`；HTTP 与 WebSocket 都不走系统代理 |
| `page/*.js` | 页面内的只读脚本，随版本固定：`alive`、`ready`、`switch`、`extract`（身份、指标、表格 / 标签 / 线 / 框、绘图、曲线，一次调用读完）、`screenshot`、`diagnose`。调用方不能传入任意脚本 |
| `capture.py` | 批次流程：开工自检、逐品种切换并判断就绪、提取、写文件、收尾恢复 |
| `store.py` | 写文件：0600、只新建（`O_EXCL`）、写完算 SHA256；批次锁；manifest |
| `jobs.py` | 后台任务：采集在独立子进程里跑，进度写进批次目录的 `job.json`，调用方断开也不影响采集 |
| `cli.py` | 命令行：`capture`、`status`、`read`、`crop`、`doctor`，以及 `mcp`（启动 stdio MCP 服务） |
| `mcp_server.py` | MCP 工具定义，和命令行调用同一套函数 |

## 4. 采集流程

### 4.1 开工（每批一次）

1. 校验参数，拿批次锁，建 `output_dir`，写 `batch.json`（开工时间、参数、工具版本）。`symbols` 原样存档并算 SHA256。
2. 启动桌面版，等 CDP 就绪，核对监听地址，选中 `layout` 对应的页面。
3. 等内部接口：页面刚打开时图表接口已经能应答，内部模型却还没建好，所以 `diagnose` 的各项检查（图表接口、截图接口、主图 K 线、指标数量、每个指标的表格 / 标签 / 线 / 框集合、绘图端点）最多轮询 30 秒。30 秒后仍有不过的，整批停止，返回 `TV_INTERNALS_CHANGED` 并附上失效的检查项。
4. 等开工时的图表稳定：布局还在加载时做的切换，会被布局自己的加载覆盖回去；加载过程中品种还可能被改名成延迟行情的名字（例如 `SSE:000001` 变成 `SSE_DLY:000001`，2026-10-14 实测）。所以先跟着图表当前显示的品种等，直到相邻两次读取的结构一致（规则同 4.2 第 2 步），最多等 `ready_timeout_sec`。这时的品种和周期就是收尾要恢复的原值，记在 manifest 的 `startup` 里。等不到也不停批次：照样往下采，`startup.settled` 记 `false` 并写明原因。
5. 不改视口：桌面版里 TradingView 的截图尺寸跟着窗口大小走，CDP 的视口模拟对它不起作用（2026-10-14 整批演练实测），实际尺寸记在 `capture.json`。
6. 自检：在第一个走到提取这一步的品种上完整检查一遍：身份可读、有指标、`required_studies` 都在、曲线序列行数大于 0、截图是有效的 PNG。任何一项不过，整批停止，返回错误码 `TV_INTERNALS_CHANGED` 并附上失效点，不留半成品。品种在提取之前就失败（例如就绪超时、代码无效）时只记这个品种失败，自检顺延到下一个品种。
7. 记下桌面版版本。如果和输出根目录下最近一次成功批次的版本不同，在 manifest 里标 `desktopVersionChanged: true`。

### 4.2 逐品种

1. **切换**：`setSymbol(code)`。周期按图表报告的写法发送（`D` 发成 `1D`），周期已经一致就不再设置。
2. **判断就绪**：每秒读一次，以下条件全部满足才往下走；超过 `ready_timeout_sec` 就记 `NOT_READY_TIMEOUT`，附上最后一次没过的条件和图表当时的品种：
   - 当前品种是目标代码，或是它的延迟行情名（交易所名加 `_DL` / `_DLY`，例如 `SSE_DLY:000001` 对应 `SSE:000001`）。布局在切换后把品种改回去时重新切换，每个品种最多 3 次；
   - 周期一致（`D` 与 `1D` 视为相同）；
   - 主图有 K 线；各指标计算完成，没有加载中或报错状态；各指标序列的最后一根和主图最后一根是同一时间；
   - 相邻两次读取的结构一致：品种、周期、主图最后一根的时间，以及各指标的 ID、状态和最后一根的时间。指标输出（最后一根的值、表格、标签）的指纹不要求一致，因为开盘时正在形成的那根 K 线每秒都在变（2026-10-14 实测）；读取时仍在变的指标记进 `digestMovingAtRead`；
   - 各指标的输出指纹和切换前的品种不同（切换前已经是目标品种时不比）。切换后 10 秒仍有指标和上一个品种完全相同时也放行，但把它记进 `unchangedAfterSwitch`，由调用方核对。

   这几条是为了防止读到上一个品种残留的表格。
3. **提取**（一次页面调用）：
   - 身份：代码、交易所、描述、周期、主图最后一根 K 线的时间和 OHLC；
   - 指标清单：名称、ID、输入参数；
   - 表格：每个指标每张表 `[行][列]` 的原文，emoji、空格、`NaN` 都原样保留；
   - 标签：文字、K 线时间（由序号换算）、价位、朝向样式、颜色；
   - 线与框：端点的时间和价位；
   - 绘图：类型、端点、各档位的系数；斐波回撤另给各档价位，从第二个端点量向第一个端点（`reverse` 时对调），2026-10-14 已与图上标签核对；
   - 曲线：图表已加载的每根 K 线（不只是可见范围），每个指标里原生导出会带的每条曲线（跳过 `alertcondition`、`data` 和各类配色曲线），列名、列序和数字写法与原生 CSV 一致；
   - 截图：TradingView 渲染的 PNG。
4. **写入** `raw/<代码安全名>/`：`image.png`、`chart.csv`、`data.json`、`capture.json`，格式见第 5 节。
5. **单个品种失败**：记下错误码和原因，接着采下一个。

### 4.3 收尾

- 恢复开工前的品种和周期，退出本工具启动的桌面版，写 `capture-manifest.json`，释放锁。
- 返回汇总：成功数、失败数和原因、`desktopVersionChanged`。

### 4.4 续跑

对已有批次调用 `capture_retry`（命令行 `capture --retry-failed`），只重跑失败和未完成的品种。每次尝试追加记录到 `attempts/`，已成功品种的文件不动。

## 5. 输出格式

```text
<outputDir>/
├── batch.json              # 开工参数、symbols 原文与 SHA256、工具版本
├── job.json                # 后台任务进度（运行中持续更新）
├── capture-manifest.json   # 每个品种的状态、文件 SHA256、时间；desktopVersionChanged
├── attempts/               # 续跑时每次尝试的记录
└── raw/<SAFE_CODE>/
    ├── image.png           # TradingView 渲染的图表
    ├── chart.csv           # 由曲线数据按原生列生成；time 为 UNIX 秒
    ├── data.json           # 结构化数据
    └── capture.json        # 各步时间、文件 SHA256、版本、就绪证据、采集方式
```

- `capture.json` 里 `captureMethod` 固定为 `CDP_DESKTOP`，并写明 PNG 来自页面渲染接口、CSV 由曲线数据生成，不是菜单下载的文件；另有 `tool`（名称、版本）、`desktop`（桌面版版本）、`resolvedSymbol`（图表实际显示的代码，可能是延迟行情名）。
- `data.json` 的顶层是 `identity`、`studies[]`（每项含 `tables`、`labels`、`lines`、`boxes`，以及每条曲线的最后值）、`drawings[]`、`readiness`（读取次数 `polls`、等待秒数 `waitedSec`、最后一根 K 线时间 `lastBarTime`、重新切换次数 `reswitches`、`unchangedAfterSwitch`、`digestMovingAtRead`，以及就绪那一刻各指标的 ID、名称、状态、最后一根时间和输出指纹）。逐 K 的曲线值只放在 `chart.csv`，不在 `data.json` 里重复。
- 文件一律 0600，目录 0700；写入用 `O_CREAT | O_EXCL`。
- 时间同时写两种：带时区的 ISO 8601（本机时区）和 UNIX 秒。

## 6. MCP 工具与命令行

| MCP 工具 | 命令行 | 作用 |
|---|---|---|
| `capture_start` | `tradingview-capture capture` | 按第 2 节的参数开始一批，立即返回任务 ID |
| `capture_retry` | `tradingview-capture capture --retry-failed` | 只重跑已有批次里失败和未完成的品种，立即返回任务 ID |
| `capture_status` | `tradingview-capture status` | 进度：完成数 / 总数、当前品种、失败原因、版本是否变化 |
| `batch_summary` | `tradingview-capture status --summary` | 一批的总览：每个品种的状态和文件 SHA256 |
| `symbol_data` | `tradingview-capture read` | 读某个品种的 `data.json`，可以只取 `identity` / `tables` / `labels` / `lines` / `drawings`；要曲线值时从 `chart.csv` 取最近 N 根 |
| `image_crop` | `tradingview-capture crop` | 按像素框从 `image.png` 裁图。MCP 返回 PNG 图像内容；另存为文件只在命令行 `crop --out`（0600） |
| `diagnose` | `tradingview-capture doctor` | 只读的兼容诊断：每条提取路径是否可用、失效点附近的字段名和数量、桌面版版本。不输出表格原文这类内容数据 |

- 返回内容尽量紧凑：默认不返回逐 K 曲线，表格按行文本返回。
- MCP 只走 stdio，不开网络端口。
- 会写文件的只有 `capture_start`、`capture_retry` 和命令行的 `crop --out`，而且只能写在输出根目录里。

## 7. 错误码

| 错误码 | 含义 | 处理 |
|---|---|---|
| `TV_NOT_INSTALLED` | 找不到桌面版 | 停止 |
| `TV_ALREADY_RUNNING` | 桌面版已在普通模式下运行，没有调试端口 | 停止，提示用户退出后重试 |
| `CDP_NOT_LOCAL` | 调试端口不是只监听 127.0.0.1 | 停止，并退出本工具启动的进程 |
| `LAYOUT_NOT_FOUND` / `LAYOUT_NOT_UNIQUE` | 布局标签页不存在或不唯一 | 停止 |
| `TV_INTERNALS_CHANGED` | 自检失败 | 停止，附失效点，见第 8 节 |
| `SYMBOL_NOT_FOUND` | 切换失败或身份不符 | 该品种失败，继续下一个 |
| `NOT_READY_TIMEOUT` | 超过就绪等待上限 | 该品种失败，继续下一个 |
| `STUDY_MISSING` | 必需指标缺失 | 该品种失败，继续下一个 |
| `OUTPUT_EXISTS` / `OUTPUT_OUTSIDE_ROOT` | 输出目录已存在，或不在输出根目录下 | 停止 |
| `BATCH_LOCKED` | 另一个采集正在运行 | 停止 |
| `TV_STARTUP_TIMEOUT` | 桌面版启动后调试端口迟迟不应答，或启动中途退出 | 停止 |
| `PORT_IN_USE` | 调试端口已被别的程序占用 | 停止 |
| `CDP_ERROR` | 与页面的 DevTools 通信失败，或页面脚本报错 | 该品种失败；开工阶段则停止 |
| `INVALID_ARGUMENT` | 参数格式不对 | 停止，不启动桌面版 |
| `CONFIG_INVALID` | 本机配置缺失、格式不对、可被他人写，或输出根目录不存在（例如外置盘没挂载） | 停止 |
| `NOT_FOUND` | 要读的批次、品种或任务不存在；续跑时没有失败的品种 | 停止 |
| `INTERNAL_ERROR` | 工具自身的意外错误；仍会写出 manifest | 停止 |

## 8. 桌面版升级与兼容修复

- 不锁定桌面版版本。每批都记录版本，版本变了就标 `desktopVersionChanged`，调用方对这一批要逐项核对。
- 自检不过就停用，工具不会自动退回截图读图。
- 修复流程（Claude / Codex 可以执行，规则写进 `AGENTS.md`）：
  1. 运行 `diagnose`，拿到失效的路径和附近的字段结构；
  2. 在分支上改 `page/*.js`，跑单元测试；
  3. 拿一个品种做活体自检；
  4. 用编造的数据把这次的结构变化补进测试夹具，防止以后回归；
  5. 按 10.2 节合并（维护者一侧可直接合并），发版，`CHANGELOG.md` 记下对应的桌面版版本。
- 修复只改"怎么读"，不改输出格式。确实要改输出格式时，按语义化版本升主版本号，并在 PR 里说明。

## 9. 安全边界

- 调试端口只在采集期间开着，只监听 127.0.0.1；采集结束就退出本工具启动的桌面版。端口开着的时候，本机任何进程都能连上并控制这个 TradingView 会话。这是已知风险，靠尽量缩短开启时间来控制。
- 不提供任意脚本执行，`diagnose` 用的也是固定脚本。
- 页面里唯一会改变状态的动作是切换品种和周期，这会被布局自动保存，所以收尾时恢复原值。不改指标参数，不移动或新建绘图，不建警报，不打开 Pine 编辑器，不点任何菜单。
- 只退出自己启动的 PID，从不按进程名结束进程。
- 除桌面版自身的连接外不访问网络；不读取也不保存 TradingView 账号凭据；不上传任何数据。
- 日志里不记表格原文和截图，也不记调用方传入的业务内容；`diagnose` 只报结构。

## 10. 仓库与协作

### 10.1 文件

- `README.md`（中文为主，附英文摘要）、`LICENSE`（Apache-2.0）、`CHANGELOG.md`
- `AGENTS.md`：AI 编码入口，规则只维护这一份；`CLAUDE.md` 只写一行 `@AGENTS.md` 导入
- `docs/ai-coding/`：`README.md`、`AI_CODING_GUIDE.md`、`AI_DIRECTORY_STRUCTURE_GUIDE.md`、`AI_COMMENT_STYLE_GUIDE.md`、`AI_DESIGN_PATTERN_GUIDE.md`、`AI_ENGINEERING_GUARDRAILS.md`、`SECURITY_CODING_SPEC.md`、`TESTING_SPEC.md`。按本项目自己的职责来写（Python、CDP、页面脚本、TradingView 内部结构容易变、开源边界），不照搬别的仓库
- `CONTRIBUTING.md`（附英文摘要）、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`MAINTAINERS.md`
- `.github/`：`CODEOWNERS`、PR 和 issue 模板、CI 工作流、`dependabot.yml`
- `scripts/check-private-content.sh`：提交前钩子和 CI 共用

### 10.2 合并规则（main 分支的 ruleset）

- **维护者一侧可以直接合并**：维护者本人，以及维护者本机用维护者账号运行的 Claude / Codex 会话，可以直接合并到 main（ruleset 对仓库管理员设"始终绕过"）。合并前本机测试必须全部通过，合并后看 CI 结果，红了马上修。
- **其他人都要审核**：外部贡献者 fork 后提 PR，合并条件是 CI 全绿、维护者本人审核确认是有益的改动并批准、评审对话全部解决。首次贡献者的 CI 要维护者批准后才运行。
- 所有合并只允许 squash；禁止强推和删除 main；任何代理都不得修改 ruleset 或仓库权限。
- 提交信息和 PR 标题用英文 Conventional Commits。

### 10.3 开源边界

仓库里只放通用代码、编造的测试夹具和通用示例。真实布局 ID、TradingView 用户名、真实指标名和表格内容、真实截图、本机路径、任何令牌，都不能进入仓库、issue、PR 或日志。

`check-private-content.sh` 扫描以下内容：
- 长得像令牌的字符串、本机绝对路径、IP 地址；
- 维护者在本机 `~/.config/tradingview-capture-mcp/private-terms.txt` 里列出的私有词（这个文件不进仓库）。

## 11. 测试

- **单元测试**（pytest）：
  - CDP 客户端，用假的 WebSocket 服务测；
  - 就绪判断：旧表格残留、超时、两次读取结构不一致、开盘时输出仍在跳动、延迟行情改名、布局把品种改回去；
  - CSV 生成：列顺序、`NaN`、时间格式；
  - 写文件：0600、拒绝覆盖、越界；
  - 批次锁、续跑、错误码。
- **页面脚本测试**：用 Node 内置的测试运行器，配合模拟 TradingView 内部对象结构的假对象，不需要浏览器。
- **CI**：在 macOS 上跑 pytest、页面脚本测试、ruff 和私有内容扫描。
- **活体测试**：设 `TRADINGVIEW_CAPTURE_LIVE=1`，只在本机、桌面版已登录时运行，做单品种采集和自检；CI 不跑。

## 12. 已知限制与风险

- 依赖 TradingView 未公开的内部结构，桌面版升级可能导致失效。靠自检发现，按第 8 节修复。
- 自动化使用可能和 TradingView 的服务条款冲突，由使用者自行判断并承担。
- PNG 的尺寸等于桌面版窗口大小乘以像素比；要前后一致，需要保持窗口大小不变。
- 生成的 CSV 和原生下载的 CSV 是否逐值一致，要在 M3 用原生文件比对确认。
- 首版只支持 macOS 和 TradingView 桌面版。

## 附录 A：2026-10-14 可行性验证

验证环境：已登录的 TradingView 桌面版 3.4.1（Electron 41.7.1，Chromium 146），带 `--remote-debugging-port` 启动，端口只监听 127.0.0.1。全部为只读验证。

| 项 | 结果 |
|---|---|
| 身份 | `activeChart().symbol()` / `resolution()` 可读，切换后读到目标代码和 `1D` |
| 指标清单 | `getAllStudies()` 可读 |
| 表格 | 从指标的图形集合（`dwgtablecells`）逐格读出原文；三个私有 Pine 指标的表格都完整可读 |
| 标签 | `dwglabels` 可读：文字、K 线序号、价位、样式 |
| 曲线 | 指标的 `data()` 可读，每行是 `[时间, 各曲线值…]`，曲线标题和原生 CSV 列名一致 |
| 切换 | `setSymbol` 回调用时 172 ms，表格约 3 秒就绪；就绪判断需要按 4.2 节加严 |
| 截图 | `takeClientScreenshot()` 用时 174 ms，返回完整画面的 PNG（1835×1142，随窗口变化） |
| 数据导出 | 页面的 `exportData()` 返回 "Data export is not supported"，所以 CSV 改由曲线数据生成 |
| 绘图 | 接口可用；验证的两个品种上没有能读到端点的斐波（同日在画了斐波的品种上补验：各档价位与图上标签一致） |

验证结束时切回了原来的品种，正常退出桌面版，调试端口随之关闭。
