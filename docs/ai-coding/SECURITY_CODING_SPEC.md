# 安全编码规范

## English summary

Seven rules: the DevTools port listens on loopback only (it stays open while TradingView Desktop runs with it, so the user can keep using it); no caller-supplied scripts ever run in the page, and only `switch.js` and `history.js` change the chart; a TradingView Desktop that was already running is never stopped, only one this tool started to quit again; outputs are owner-only and create-only; no network beyond the local DevTools connection; logs and diagnostics carry no chart contents; nothing private reaches the repository.

## 1. 调试端口

- 接上已开着的桌面版前检查：监听这个端口的就是 TradingView 进程（`pgrep -x TradingView` 列出的进程之一），而且只监听 127.0.0.1 / [::1]；不是 TradingView 在监听报 `TV_ALREADY_RUNNING`（桌面版开着但没带端口）或 `PORT_IN_USE`（桌面版没开、端口被别的程序占着），不在本机回环上报 `CDP_NOT_LOCAL`，都不碰那个进程。
- 自己启动前检查端口未被占用（`PORT_IN_USE`），启动后检查只监听 127.0.0.1 / [::1]（否则 `CDP_NOT_LOCAL` 并立刻停掉刚启动的进程）。源码里不得出现 `--remote-debugging-address`（`tests/test_scope.py` 把关）。
- 端口随桌面版开着：`keep_open = true`（默认）时本工具打开的桌面版采完留给用户，端口一直开着；`keep_open = false` 时采完退出本工具启动的桌面版，端口随之关闭。端口开着时本机任何进程都能控制这个 TradingView 会话，README 写明这一风险。

## 2. 页面脚本

- 只运行 `page/` 下随版本固定的脚本；参数只以 `json.dumps` 生成的 JSON 字面量传入，绝不拼接进代码。
- `tests/test_scope.py` 扫描页面脚本：只有 `switch.js` 调切换品种和周期、只有 `history.js` 调 `requestMoreData`，任何脚本都不调改指标、绘图、视图、窗格的方法，不碰网络、存储、cookie 和 `eval`；DevTools 客户端只发 `Runtime.evaluate`。
- 除 `switch.js` 和 `history.js` 外的脚本都不得改变图表状态。`switch.js` 只切换品种和周期，收尾恢复；`history.js` 只在调用方传了 `history_from` 时向数据源要更早的 K 线（主图序列的 `requestMoreData`），不移动视图、不改缩放和任何属性，换品种即丢弃，所以不需要恢复。

## 3. 进程

- 桌面版用固定参数列表启动，不经 shell。要留着的用 `/usr/bin/open -a <app> --args …` 打开（macOS 的启动方式，它不继承本进程的环境，也不是本进程的子进程）；`keep_open = false` 时直接启动可执行文件，环境去掉 `ELECTRON_*`、`DYLD_*`、`NODE_OPTIONS`、`NODE_PATH`，免得宿主传下来的变量让它以纯 Node 启动或载入别的代码。两种都只带调试端口和三个不放慢后台页面的开关。
- 停止只有两种：`keep_open = false` 时对自己持有的 `Popen` 对象发信号（先 SIGTERM，超时 SIGKILL）；刚用 `open` 打开的桌面版发现端口不在本机回环上时，对监听这个端口的那个 TradingView 进程发 SIGTERM（打开前没有任何 TradingView 在运行，所以它就是刚打开的那个）。
- 已经在运行的桌面版绝不结束：带端口的接上去用，没带端口的报 `TV_ALREADY_RUNNING`，请用户自己 ⌘Q。
- `install-launcher` 用固定参数调 `/usr/bin/osacompile` 生成启动器；嵌进 AppleScript 的程序路径按 AppleScript 字符串转义，运行时由 `quoted form of` 交给 shell，不拼接未转义的文本；已有同名文件时报 `OUTPUT_EXISTS`，不覆盖。
- 禁止 `pkill`、`killall` 和任何按进程名结束进程的做法。

## 4. 文件

- 输出文件 0600、`O_CREAT | O_EXCL`，目录 0700；例外只有 `job.json` 与续跑时的 `capture-manifest.json`，用临时文件加原子 `rename` 替换。
- 所有写入路径必须在本机配置的输出根目录之下，父目录经 `resolve(strict=True)` 解析，拒绝符号链接逃逸。
- 本机配置文件不得可被组或其他人写。
- 清理（`prune.py`）只处理输出根目录之下、本工具在原处写下的批次：有本工具的 `batch.json`，且批次自己的 `job.json` 记的就是这个目录（`os.path.samefile`）；副本和里面还套着别的批次的目录不动。遍历不跟随符号链接，用固定参数列表调用 `/usr/bin/trash` 移到废纸篓，不经 shell，不永久删除；命令超时或起不来记为 `TRASH_FAILED`，接着处理下一个；执行时持有批次锁，采集进行中不动任何目录。新批次不能建在另一个批次里面。

## 5. 网络

- 只连本机 DevTools；HTTP 与 WebSocket 都显式不走系统代理。
- 不上传、不调用任何外部服务；不读取、不保存 TradingView 账号凭据。

## 6. 日志与诊断

- 日志和 `diagnose` 只写结构信息（检查项、字段名、数量、版本），不写表格原文、标签文字、截图或调用方的业务参数。

## 7. 私有内容

- 仓库、提交信息、issue、PR、测试夹具里不得出现：真实布局 ID、TradingView 用户名、私有指标名与表格内容、真实截图、本机绝对路径、IP 地址、令牌。
- `scripts/check-private-content.sh` 在提交前钩子与 CI 中运行；维护者的私有词清单放在 `~/.config/tradingview-capture-mcp/private-terms.txt`。确需在测试里放类似的字符串时，整行加 `private-content: allow` 标记。
