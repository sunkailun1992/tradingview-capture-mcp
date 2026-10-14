# AGENTS.md

本文件是 `tradingview-capture-mcp` 的 AI 编码入口，Claude Code 与 Codex 都读这一份。修改代码前先读本文件，再按改动的风险读对应规范和真实代码。

## English summary

- This repository is public. Never commit real layout IDs, TradingView usernames, private indicator names or table contents, real screenshots, local absolute paths, IP addresses or tokens. Test fixtures are made up.
- The tool only exports chart data and screenshots. It never decides which symbols to capture and never uploads anything; callers do that.
- Hard rules: no arbitrary page scripts; the only page action that changes state is switching symbol and resolution; stop only the process this tool started; files 0600 and create-only.
- Verify with `uv run pytest -q`, `node --test "tests/js/*.test.mjs"`, `uv run ruff check`, `uv run ruff format --check` and `bash scripts/check-private-content.sh`.
- `TV_ALREADY_RUNNING` means the user has TradingView Desktop open (full screen or not). The debugging port can only be opened at launch, so ask the user to quit it with Cmd+Q, never kill it, then call `capture_retry` on the same `output_dir`. See "常见情况" below.
- Keep only the current day's batches: after the day's captures (or before a new day's first one) call `output_prune` without `apply`, then with `apply=true`. It moves this tool's older batch folders to the macOS Trash and never deletes for good; never empty the Trash for the user.
- A required study hidden on the layout fails with `STUDY_HIDDEN`; `notExported` lists what the tool could not export, so an empty part of the data is never mistaken for nothing drawn.
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
- 页面里唯一会改变状态的动作是切换品种和周期；收尾必须恢复原值。不点菜单，不改指标参数，不动绘图，不建警报，不打开 Pine 编辑器。
- 调试端口只能监听 127.0.0.1 / [::1]，只在采集期间开着。
- 只停止本工具启动的那个进程；禁止 `pkill`、`killall`，禁止按进程名结束进程；用户自己开着的桌面版一律不碰，报 `TV_ALREADY_RUNNING`。
- 输出文件一律 0600、只新建（`O_EXCL`），目录 0700；例外只有 `job.json` 和续跑时的 `capture-manifest.json`，两者原子替换。
- 子进程只用固定参数列表，不经 shell。
- 清理只把 `output_root` 下本工具建的批次目录交给 `/usr/bin/trash` 移到废纸篓，不永久删除，不跟随符号链接，不碰别的文件；工具和代理都不清空废纸篓。
- 不访问桌面版自身连接以外的网络；不读取、不保存 TradingView 凭据。

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
