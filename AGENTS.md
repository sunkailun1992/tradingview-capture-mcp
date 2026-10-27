# AGENTS.md

本文件是 `tradingview-capture-mcp` 的 AI 编码入口，Claude Code 与 Codex 都读这一份。修改代码前先读本文件，再按改动的风险读对应规范和真实代码。

## English summary

- This repository is public. Never commit real layout IDs, TradingView usernames, private indicator names or table contents, real screenshots, local absolute paths, IP addresses or tokens. Test fixtures are made up.
- The tool only exports chart data and screenshots. It never decides which symbols to capture and never uploads anything; callers do that.
- Hard rules: no arbitrary page scripts; the only page actions that change state are switching symbol and resolution (restored at the end) and, when a caller passes `history_from`, asking TradingView for older bars (`history.js`, which never moves the view or the zoom); stop only the process this tool started; files 0600 and create-only.
- Verify with `uv run pytest -q`, `node --test "tests/js/*.test.mjs"`, `uv run ruff check`, `uv run ruff format --check` and `bash scripts/check-private-content.sh`.
- `TV_ALREADY_RUNNING` means the user has TradingView Desktop open (full screen or not). The debugging port can only be opened at launch, so ask the user to quit it with Cmd+Q, never kill it, then call `capture_retry` on the same `output_dir`. See "常见情况" below.
- Keep only the current day's batches: after the day's captures (or before a new day's first one) call `output_prune` without `apply`, then with `apply=true`. It moves this tool's older batch folders to the macOS Trash and never deletes for good; never empty the Trash for the user.
- A required study hidden on the layout fails with `STUDY_HIDDEN`; `notExported` lists what the tool could not export, so an empty part of the data is never mistaken for nothing drawn.
- `history_from` (YYYY-MM-DD) loads each chart's history back to 00:00 UTC on that date before the read. `reached: false` together with an `endOfData` flag means TradingView sent everything it gives (`limit`: this account or timeframe gets no older bars; `end`: the data starts there); a load that does not finish fails that symbol with `NOT_READY_TIMEOUT`, reason `history`. See "常见情况".
- Each symbol's `image` evidence lists `collapsedStudies`: studies whose own pane is collapsed (or hidden behind a maximized pane), so `image.png` lacks that pane although their data is complete. `LAYOUT_NOT_FOUND` at startup usually means the network was down or the layout ID is wrong; retry with `capture_retry`. A chart may show a symbol under its feed (`BATS:AAPL` for `NASDAQ:AAPL`); `identity.listedSymbol` keeps the listing. See "常见情况".
- `tests/test_scope.py` checks the hard rules on the source (which scripts may change the chart, no network or storage in the page, only `Runtime.evaluate`, no `pkill`); change it together with the rules.
- The maintainer and the maintainer's own Claude/Codex sessions may merge to `main` directly; everyone else opens a PR that the maintainer reviews. Squash only, never force-push.

## 项目定位

- 名称：`tradingview-capture-mcp`；Python 包 `tradingview_capture_mcp`；命令行 `tradingview-capture`。
- 职责：驱动 TradingView 桌面版，把调用方指定品种的渲染图、与原生导出同列的 CSV、指标的表格 / 标签 / 线 / 框 / 绘图导出成文件，交给 AI 代理。
- 边界：不决定采哪些品种，不分析，不上传。数据怎么核对、怎么用、提交到哪里，都是调用方的事。
- 技术栈：Python 3.12+、uv、MCP Python SDK 2.x、websockets 17（同步客户端）、Pillow；页面脚本是 JavaScript。
- 设计与计划：`docs/superpowers/specs/`、`docs/superpowers/plans/`。

## 修改前阅读顺序

1. `README.md`：用法、输出、安全边界。
2. `docs/ai-coding/README.md`：规范索引。
3. `docs/ai-coding/AI_CODING_GUIDE.md`：模块关系、数据流、新增页面脚本的步骤。
4. `docs/ai-coding/AI_ENGINEERING_GUARDRAILS.md`：风险分级与完成标准。
5. `docs/ai-coding/SECURITY_CODING_SPEC.md`：端口、脚本、进程、文件、网络、日志、私有内容七条规则。
6. `docs/ai-coding/TESTING_SPEC.md`：三层测试与夹具规则。
7. 其余规范：目录结构、注释风格、设计模式。

## 硬规则

- 不执行调用方传入的任意脚本。页面脚本只有 `src/tradingview_capture_mcp/page/` 下随版本固定的几个，参数只以 JSON 字面量传入。
- 页面里会改变状态的动作只有两种：切换品种和周期（`switch.js`），收尾必须恢复原值；调用方传 `history_from` 时向 TradingView 要更早的 K 线（`history.js`，主图序列的 `requestMoreData`，与往左拖动图表时它自己发的请求相同），只多载入历史，不移动视图、不改缩放和任何属性，换品种就丢掉，所以不需要恢复。不点菜单，不改指标参数，不动绘图，不建警报，不打开 Pine 编辑器。
- 调试端口只能监听 127.0.0.1 / [::1]，只在采集期间开着。
- 只停止本工具启动的那个进程；禁止 `pkill`、`killall`，禁止按进程名结束进程；用户自己开着的桌面版一律不碰，报 `TV_ALREADY_RUNNING`。
- 输出文件一律 0600、只新建（`O_EXCL`），目录 0700；例外只有 `job.json` 和续跑时的 `capture-manifest.json`，两者原子替换。
- 子进程只用固定参数列表，不经 shell。
- 清理只把 `output_root` 下本工具在原处写下的批次（有本工具的 `batch.json`，且批次自己的 `job.json` 记的就是这个目录）交给 `/usr/bin/trash` 移到废纸篓，不永久删除，不跟随符号链接；副本、套着别的批次的目录和别的文件一律不碰；工具和代理都不清空废纸篓。新批次不能建在另一个批次里面。
- 不访问桌面版自身连接以外的网络；不读取、不保存 TradingView 凭据。
- 启动桌面版时去掉 `ELECTRON_*`、`DYLD_*`、`NODE_OPTIONS`、`NODE_PATH`，其余环境照传：宿主传下来的 `ELECTRON_RUN_AS_NODE` 会让桌面版以纯 Node 启动，没有窗口也没有调试端口。
- 上面关于页面脚本、DevTools 方法和结束进程的规则由 `tests/test_scope.py` 扫描源码把关；改规则时同步改它，不要为了让它通过而放宽。

## 验证命令

```bash
uv run pytest -q
node --test "tests/js/*.test.mjs"
uv run ruff check
uv run ruff format --check
bash scripts/check-private-content.sh
```

活体测试只在本机、桌面版已登录时运行：`TRADINGVIEW_CAPTURE_LIVE=1 uv run pytest -m live -q`，私有输入从 `TRADINGVIEW_CAPTURE_LIVE_*` 环境变量读，不写进仓库。

## 提交与合并

- 提交信息与 PR 标题用英文 Conventional Commits，例如 `fix(page): match the native export header`。
- 维护者本人，以及维护者本机用维护者账号运行的 Claude / Codex 会话，可以直接合并到 `main`；合并前本机验证命令必须全过，合并后看 CI，红了马上修。
- 其他人都要走 PR：CI 全绿、维护者审核确认是有益的改动并批准、评审对话全部解决。
- 只允许 squash 合并；禁止强推（含 `--force-with-lease`）和删除 `main`；任何代理都不得修改 ruleset 或仓库权限。
- 推送被拒时先 `git fetch`，在最新远端上 rebase 并重跑验证。

## 常见情况

使用或修改本工具时遇到下面这些情况，先按这里处理，不要自己猜。

- **`TV_ALREADY_RUNNING`**：用户自己开着 TradingView 桌面版。调试端口只能在启动时打开，工具只能控制自己带端口启动的那个桌面版，所以已经开着的连不上，全屏还是窗口都一样。`capture_start` / `capture_retry` 会当场报这个错，什么都不建：请用户用 ⌘Q 完全退出（只关窗口不够），再用同样的参数调一次。采集开始后才打开 TradingView、或命令行 `--foreground` 这类批次已经建好又因此停下的，对同一个 `output_dir` 调 `capture_retry`。不要替用户结束进程。
- **本机 MCP 跑的是独立副本**：`uv tool install` 装在 `~/.local/bin/tradingview-capture`，不是仓库目录。修复合并进 `main` 后运行 `uv tool upgrade tradingview-capture-mcp`，再重开会话才生效；只想试本地改动时，临时把注册的命令换成 `uv --directory <仓库路径> run tradingview-capture mcp`。
- **全屏**：不影响采集，工具不点界面；只影响截图尺寸（PNG 等于窗口大小乘以屏幕像素比）。
- **采集进行中**：不要打开或操作 TradingView。批次结束时工具会退出它，之后用户照常打开即可。活体测试（`TRADINGVIEW_CAPTURE_LIVE=1 uv run pytest -m live -q`）同样要求桌面版先完全退出。
- **`STUDY_MISSING`**：布局里找不到 `required_studies` 里的指标（按子串匹配指标名）。对照错误明细里的 `missing` 和 `found` 核对传入的名字，或请用户在 TradingView 里把指标加回布局；这不是页面脚本的问题，不要去改 `page/*.js`。
- **`STUDY_HIDDEN`**：要求的指标还在布局里，但图例上的眼睛被关掉了。隐藏的指标照样计算，数据会有、截图里却没有，所以工具当场停下。请用户在 TradingView 里把它重新显示，再调一次；不要把它从 `required_studies` 里去掉来绕过。
- **只保留当天的批次**：每天采集用完后（或新一天第一次采集前），先调 `output_prune` 看清单，再带 `apply=true` 调一次。它只把今天以前、本工具建的批次目录移到废纸篓，从不永久删除；空间要等用户清空废纸篓才释放，代理不要替用户清空，也不要用 `rm` 代替它。采集进行中会报 `BATCH_LOCKED`，等批次结束。系统没有 `/usr/bin/trash`（macOS 15 以前）时报 `TRASH_UNAVAILABLE`，什么都没动，请用户手动处理。
- **价格轴上的标签**：主图价格轴上的标签来自主图窗格里的曲线，以及别的窗格里 `forceOverlay` 为真的曲线；`display` 含价格轴位（4）且指标的 `showLabelsOnPriceScale` 为真才显示。标签显示的是 `lastValid`：线在过去某根 K 停了，轴上就一直挂着那根 K 的值。K 线组（`plotcandle`）只在轴上显示收盘那一个值。数值按指标的 `format` 印，`volume` 格式会显示成 83.42K 这种样子。
- **`notExported` 不为空**：图上有工具还读不了的东西（例如渐变填色的上下沿、折线）。按缺口处理，不要当作图上没有；需要时再开发导出。
- **就绪证据**：开盘时 `digestMovingAtRead` 有值是正常的；`unchangedAfterSwitch` 有值时，要对照截图确认表格不是上一个品种的；`resolvedSymbol` 的交易所名以 `_DL` / `_DLY` 结尾表示延迟行情。
- **图表显示的是数据源名**：账户没有某交易所自己的实时数据时，图表用别的数据源显示它，例如请求 `NASDAQ:AAPL`、图上是 `BATS:AAPL`。这不是切错品种：`identity.listedSymbol`（TradingView 的 `pro_name`）仍是 `NASDAQ:AAPL`，工具按它认定切换成功，`resolvedSymbol` 照实记 `BATS:AAPL`。上市名也对不上时才报 `SYMBOL_NOT_FOUND`。
- **`collapsedStudies` 不为空**：这些指标所在的窗格在布局里被收起（或别的窗格被最大化），截图里没有那个窗格，数据照常导出（`forceOverlay` 的曲线仍画在主图上）。有的布局故意收起某个窗格，这不算失败，工具也不会停；但要对照截图核对的指标出现在这里时，请用户在 TradingView 里把窗格拉开，再重采。各窗格的高度、收起与最大化状态在 `data.json` 的 `view.panes`。
- **`LAYOUT_NOT_FOUND`**：桌面版启动了，却没有标签页显示这个布局。布局要从 TradingView 的服务器载入，启动时网络断了就会停在这里（2026-10-26 网络不稳时出现过）；布局 ID 写错或不在这个账户也一样。看明细：`targetList` 为 `false` 是调试端口的标签页列表都没取到；`chartPages` 大于 0 是开着别的布局。网络恢复后对同一个 `output_dir` 调 `capture_retry`；不要去改页面脚本。
- **`history_from`（载入历史）**：日期按 UTC 当天 00:00 算。结果看每个品种的 `history`：`firstBarTime` 和 `barsCount` 与 `chart.csv` 一致；`reached` 为 `false` 而 `endOfData` 有值（`limit`：TradingView 对这个账户、这个周期只给到这里；`end`：数据本来就从这里开始）不是失败，那就是 TradingView 能给的全部，照实告诉用户起点。载入和指标重算没在 `ready_timeout_sec` 内完成时，该品种报 `NOT_READY_TIMEOUT`（`detail.reason` 为 `history`；卡在指标重算时 `detail.studyReason` 写明哪个条件没满足）。`capture_retry` 沿用原批次的参数（同一个 `history_from` 和 `ready_timeout_sec`），只能补上偶发的慢；每次都超时，就把失败的品种用更大的 `ready_timeout_sec` 另开一批。不要为了拿历史去改页面脚本、拖动图表或调 TradingView 的"跳转到日期"：后者会移动视图、改缩放，截图就不是平常那一屏了。
- **单元测试全过、真实桌面版却报 `TV_INTERNALS_CHANGED`**：多半是 `tests/js/fake_tv.mjs` 没模拟到真实结构。先用 `doctor` 找到失效项，再用本机临时脚本读出相关对象的结构（只读类型、键名和数量，不读内容；脚本不提交，工具运行时仍只执行随版本固定的页面脚本），把假数据改成真实结构、看测试失败，再修页面脚本。2026-10-14 的 `studies.primitives` 误判就是这样：真实图表上，指标没画标签、线或框时，那里是一个空表，而假数据没有模拟。

## 桌面版升级后的修复流程

桌面版不锁版本。自检失败时工具报 `TV_INTERNALS_CHANGED` 并停止，不会自动退回截图读图。Claude / Codex 可以按下面五步修：

1. 运行 `uv run tradingview-capture doctor --layout <布局ID>`（或 MCP `diagnose`），拿到失效的检查项和附近的字段结构；报告里没有图表内容。
2. 在分支上修改 `src/tradingview_capture_mcp/page/*.js`，先在 `tests/js/` 补一个能复现结构变化的用例（用编造的数据），看它失败，再修到通过。
3. 跑全部验证命令，再用一个品种做活体自检。
4. 按"提交与合并"合并，发版并在 `CHANGELOG.md` 记下对应的桌面版版本；本机运行 `uv tool upgrade tradingview-capture-mcp` 更新 MCP 用的副本。
5. 新版本的第一批会在 manifest 里标 `desktopVersionChanged`，提醒调用方逐项核对。

修复只改"怎么读"，不改输出格式；确实要改输出格式时升主版本号并在 PR 里写明。

## 禁止事项

- 禁止把真实布局 ID、TradingView 用户名、私有指标名、真实表格内容、真实截图、本机绝对路径、IP 地址、令牌写进代码、测试、文档、提交信息、issue 或 PR。维护者的私有词清单放在 `~/.config/tradingview-capture-mcp/private-terms.txt`，由提交前钩子和 `scripts/check-private-content.sh` 检查。
- 禁止新增上传、提交或调用外部业务接口的功能；这超出本项目的职责。
- 禁止为了让测试通过而放宽端口、进程、文件权限或私有内容检查。
- 禁止在 `diagnose` 或日志里输出表格原文、标签文字或截图。
