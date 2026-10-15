# 更新记录

本文件记录每个版本的变化，以及验证过的 TradingView 桌面版版本。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号用[语义化版本](https://semver.org/lang/zh-CN/)。

## 0.3.0 — 2026-10-15

只新增一个可选参数，以及只在用到它时才出现的字段；不传 `history_from` 时，行为和输出与 0.2.0 逐字节相同（工具版本号除外）。

### 新增

- `history_from`（MCP `capture_start` 的参数，命令行 `--history-from`，写成 `YYYY-MM-DD`）：每个品种就绪后，先把历史载入到那一天 UTC 00:00，或 TradingView 给得到的最早一根，再等指标在更长的历史上算完，然后照常导出；`chart.csv` 包含全部载入的 K 线。做法是向主图序列要更早的 K 线（`requestMoreData`，与往左拖动图表时 TradingView 自己发的请求相同）：按已载入 K 线的平均间隔估算还差多少，多要一成，每次最多 5000 根。视图和缩放不动，截图仍是平常那一屏。新的页面脚本 `history.js` 是 `switch.js` 之外唯一会改变图表的脚本，规则见 AGENTS.md。
- 用到时，`capture.json` 和 manifest 里每个成功品种的条目多一个 `history`：`from`、`targetTime`、`reached`、`endOfData`、`firstBarTime`、`barsCount`、`barsBefore`、`requests`、`waitedSec`；`symbol_data` 的 `capture` 块同样带上。manifest 顶层多 `historyFrom`，`batch.json` 的参数里多 `history_from`，`capture_retry` 沿用它。
- 载入和重算没在 `ready_timeout_sec` 内完成时，只这个品种记 `NOT_READY_TIMEOUT`（`detail.reason` 为 `history`，卡在重算时另有 `studyReason`）；载入途中图表离开了这个品种记 `SYMBOL_NOT_FOUND`。
- `diagnose` 多一项 `mainSeriesHistory`（主图序列载入历史要用的方法）。只有传了 `history_from` 的批次和 `doctor` 把它算作问题，别的批次不受影响。
- 活体测试多一项：设了 `TRADINGVIEW_CAPTURE_LIVE_HISTORY_FROM` 时，再采一次并载入日线历史。

### 已核对

- TradingView 桌面版 3.4.1：比较了图表接口的 `setVisibleRange`（桌面版未实现）、"跳转到日期"（能载入，但会移动视图、改缩放）、按日期范围载入（重新请求整个序列，没有采用）和 `requestMoreData`（采用），记录在设计文档附录 B。
- 1 小时图、`history_from` 2019-01-02，采一只韩股和一只港股：分别 11638 根（第一根 2020-01-02 10:00 首尔时间）和 11426 根（第一根 2019-01-02 09:30 香港时间），`endOfData` 都是 `limit`，每只载入加重算约 15 秒。与同一账户在网页版"下载图表数据"的导出逐根比对：第一根相同，time / open / high / low / close 在重叠段 0 处差异。
- 新的活体测试载入日线历史，停在品种上线那天，`endOfData` 为 `end`。
- 不传 `history_from` 时，用 0.2.0 和 0.3.0 跑同一组假图表批次：页面调用顺序相同，36 个输出文件逐字节相同（工具版本号除外）。

## 0.2.0 — 2026-10-14

只新增字段，原有字段和 `chart.csv` 的列都不变。

### 新增

- 逐根 K 的颜色：每个着色器（曲线、填色、K 线组、整根 K 线、背景、文字）的颜色压成 `[起始 K 时间, 结束 K 时间, 颜色]` 连续段，写在指标的 `colors` 里。RGB 脚本的颜色是 ARGB 数字（透明度在最高字节），其他脚本的颜色是调色板下标，两种都换成 CSS 颜色；查不到的计入 `unresolved`。
- 指标的 `fills`（两条曲线或两条水平线之间的填色）、`bands`（水平线的名字、数值、颜色、是否显示）、`visible`、`showLabelsOnPriceScale` 和 `format`。
- 曲线的 `display`、`forceOverlay`（Pine v6 `force_overlay`：指标在别的窗格，这条却画在主图上；活体图表把这些 id 存在 Set 里，K 线组的各列也在其中）和 `lastValid`（最后一根有值的 K；价格轴上一直显示的就是它）。
- 表格的 `position` 与 `cellColors`；标签的 `yloc`、`textAlign`、`colorCss`、`textColorCss`；线的 `colorCss`；这些颜色查不到的个数记在 `unresolvedGraphicColors`（查不到也写 `null`，靠这个数与"没颜色"区分）。CSS 字符串形式的颜色原样输出。
- `notExported`：工具没能导出的曲线类型（例如渐变填色的上下沿）和图元种类，不为空就是数据有缺口；读不了的图元种类（结构变了、读取出错）也算有，不当成空。
- `STUDY_HIDDEN`：要求的指标在布局里被隐藏时，第一个品种就整批停下。
- `output_prune` / `prune`：列出 `output_root` 下今天以前的批次，`apply` 时用 `/usr/bin/trash` 移到废纸篓；从不永久删除，采集进行中不动。只动本工具在原处写下的批次（批次的 `job.json` 记的就是这个目录），副本和套着别的批次的目录不动；新批次不能建在另一个批次里面。MCP 说明里写明只保留当天的批次。
- `symbol_data` 可以取 `plots`、`colors`、`fills`、`bands`、`notExported`，每个指标都带 `pane` 和 `visible`。
- `diagnose` 报告每个指标的属性节点，缺少样式或显示开关时报 `studies.properties`。

### 已核对

- TradingView 桌面版 3.4.1：先 3 个、2 个品种，再整批 63 个品种活体采集，全部成功；没有被隐藏的指标、没有导不出的图元，颜色全部解析（`unresolved` 为 0）；按 `lastValid`、`display`、`forceOverlay` 推出的主图价格轴标签与截图逐个一致（24 个）。

## 0.1.0 — 2026-10-14

### 新增

- 以只监听本机的调试端口启动 TradingView 桌面版，按调用方给的 TradingView 代码逐个切换布局里的图表。
- 每个品种导出 `image.png`（TradingView 渲染）、`chart.csv`（与原生导出同列）、`data.json`（表格、标签、线、框、绘图、曲线最后值）和 `capture.json`（时间、SHA256、版本）。
- 开工自检：内部接口最多等 30 秒，仍不可用时报 `TV_INTERNALS_CHANGED` 并整批停止；桌面版版本变化时在 manifest 标记。
- 开工时先等布局恢复的图表加载稳定再切换；等不到也不停批次，在 manifest 的 `startup` 里记明。
- 切换后的就绪判断：等指标算完、相邻两次读取的结构一致（开盘时输出每秒在变，不要求指纹一致）、输出与上一个品种不同（或过了 10 秒宽限期）；接受延迟行情名（`_DL` / `_DLY`）；布局把品种改回去时最多重新切换 3 次。就绪证据写进 `data.json`。
- 后台任务、续跑失败的品种、批次锁；所有文件 0600、只新建。
- 7 个 MCP 工具（stdio）和对应的命令行。
- 私有内容扫描（提交前钩子与 CI）。
- 斐波回撤各档价位：从第二个端点量向第一个端点（`reverse` 时对调），已与图上的价位标签逐档核对一致。

### 修复

- 标签、线、框的 K 线位置：图元的 x 是指标图形索引表（`_graphics._indexes`）的下标，表里才是 K 线序号；以前直接把 x 当 K 线序号，日期都会算错。现在 `index` 是 K 线序号，K 线在已加载范围之外或画在未来位置时 `index` / `time` 为 null。`diagnose` 增加这张表的检查（`studies.indexes`）。

### 新增（续）

- `identity` 增加 `priceScale`、`minMove`（价格按 minMove / priceScale 的步长显示，priceScale 100 即两位小数）。
- 每个指标增加 `plots`：原生导出会带的每条曲线一项，含 `id`、标题、类型、在 `chart.csv` 里的列号（`csvColumn`），以及形状（`plotType`）、位置（`location`）、颜色、文字、大小和是否隐藏。形状类曲线（如三角、字符标记）在 CSV 里有值的那根 K 就是画了标记的 K，调用方可以按样式认出是哪一种标记。

### 已核对

- 在 TradingView 桌面版 3.4.1 上整批采集 50 个品种：全部成功，约 3 分钟。
- 生成的 CSV 与原生「下载图表数据」的表头、列序和数字写法一致（抽查 5 个品种）；历史行里的少量差异来自依赖低周期或多周期数据、会重新计算的指标列。

### 已知限制

- PNG 尺寸等于桌面版窗口大小乘以像素比；CDP 的视口模拟对桌面版的截图不起作用，所以没有提供视口参数。
- 只支持 macOS 与 TradingView 桌面版。
