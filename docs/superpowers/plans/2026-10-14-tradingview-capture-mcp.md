# tradingview-capture-mcp 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一个本机 MCP 服务和命令行，驱动 TradingView 桌面版逐品种采集渲染图、与原生导出同列的 CSV，以及指标的表格、标签、线、框和绘图数据，让 Claude / Codex 直接读文件，不再靠截图点击。

**Architecture:** Python 包经 CDP（调试端口只监听 127.0.0.1）连桌面版的布局标签页，只运行随版本固定的页面脚本；采集在独立后台进程里跑，逐品种写 0600、只新建的文件；MCP（stdio）和命令行调用同一套函数。

**Tech Stack:** Python 3.12+、uv、MCP Python SDK 2.x（`MCPServer`）、websockets 17（同步客户端）、Pillow 12、pytest、ruff；页面脚本是 JavaScript，用 Node 内置测试运行器测。

**Spec:** `docs/superpowers/specs/2026-10-14-tradingview-capture-mcp-design.md`

## 文件块约定

每个要原样落盘的代码块，前一行写 `<!-- file: 相对路径 -->`。执行时可以用脚本按这个标记把代码块写成文件；同一路径在后面的任务里再出现时，以后出现的为准。

## Global Constraints

- Python `>=3.12`；依赖 `mcp>=2.3,<3`、`websockets>=17.2,<18`、`pillow>=12.3,<13`；开发依赖 `pytest>=9.1,<10`、`ruff>=0.17,<0.18`；构建 `hatchling>=1.32,<2`。
- 只支持 macOS 和 TradingView 桌面版；调试端口只允许监听 `127.0.0.1` / `[::1]`。
- 文件一律 0600、只新建（`O_EXCL`）；目录 0700。例外只有进度文件 `job.json`，以及续跑时的 `capture-manifest.json`，两者原子替换。
- 不执行调用方传入的任意脚本；页面脚本固定为 `alive`、`ready`、`switch`、`extract`、`screenshot`、`diagnose`。
- 只停止自己启动的那个进程（`Popen` 对象），从不按进程名结束进程，不用 `pkill` / `killall`。
- 仓库会公开：不得出现真实布局 ID、TradingView 用户名、私有指标名、本机绝对路径、IP 地址、令牌；测试夹具一律编造。
- 代码注释用英文；文档中文为主、附英文摘要；提交信息与 PR 标题用英文 Conventional Commits。
- MCP 工具名、参数名用 snake_case；输出 JSON 的键用 camelCase（如 `captureMethod`、`desktopVersionChanged`）。
- 时间戳写成 `{"iso": 带本机时区偏移的 ISO 8601, "unix": 秒}`；`captureMethod` 固定为 `CDP_DESKTOP`。
- 错误码固定：`TV_NOT_INSTALLED`、`TV_ALREADY_RUNNING`、`TV_STARTUP_TIMEOUT`、`PORT_IN_USE`、`CDP_NOT_LOCAL`、`CDP_ERROR`、`LAYOUT_NOT_FOUND`、`LAYOUT_NOT_UNIQUE`、`TV_INTERNALS_CHANGED`、`SYMBOL_NOT_FOUND`、`NOT_READY_TIMEOUT`、`STUDY_MISSING`、`OUTPUT_EXISTS`、`OUTPUT_OUTSIDE_ROOT`、`BATCH_LOCKED`、`INVALID_ARGUMENT`、`CONFIG_INVALID`、`NOT_FOUND`、`INTERNAL_ERROR`。
- `output_dir` 必须是绝对路径，父目录已存在且在本机配置的输出根目录之下；目录本身必须还不存在（续跑除外），由工具创建。

## Review Focus

1. **超大的 CDP 消息**：一张 PNG 的 base64 有几 MB，一个指标可能有几百个标签。用户期望照常采集，不能因为消息上限而失败。Task 4 的测试用 5 MB 的值验证。
2. **批次中途遇到 TradingView 不认识的代码**：期望这个品种记 `SYMBOL_NOT_FOUND` 或 `NOT_READY_TIMEOUT`，其余品种照常采完。Task 9 的测试覆盖。
3. **切换后读到上一个品种残留的表格**：期望工具等到数据真正换代才读；万一某个指标前后确实不变，宽限期过后照样读，并记录在 `unchangedAfterSwitch`。Task 6、Task 9 的测试覆盖。
4. **用户自己已经开着桌面版**：期望工具报 `TV_ALREADY_RUNNING` 并停下，不碰用户的程序。Task 8 的测试覆盖。
5. **输出根目录在没挂载的外置盘上**：期望报 `CONFIG_INVALID`，不在别处新建目录。Task 2 的测试覆盖。

## 文件结构

| 路径 | 职责 |
|---|---|
| `pyproject.toml`、`uv.lock` | 包定义、依赖、ruff 与 pytest 配置 |
| `src/tradingview_capture_mcp/__init__.py` | 版本号与工具名 |
| `errors.py` | `CaptureError` 与错误码 |
| `validation.py` | 布局 ID、TradingView 代码、周期的格式 |
| `config.py` | 读本机配置 |
| `store.py` | 0600 只新建写入、根目录检查、批次锁、时间戳 |
| `cdp.py` | 最小同步 CDP 客户端、选页 |
| `page.py` + `page/*.js` | 固定页面脚本的加载与包装 |
| `readiness.py` | 切换后何时可读 |
| `images.py` | PNG 尺寸与裁图 |
| `desktop.py` | 启动 / 检查 / 停止桌面版 |
| `driver.py` | `ChartDriver` / `DesktopControl` 接口与真实实现 |
| `diagnostics.py` | 内部结构自检、doctor |
| `capture.py` | 批次流程 |
| `jobs.py` | 后台任务与进度 |
| `results.py` | 读批次、读品种数据、裁图 |
| `cli.py`、`mcp_server.py` | 两个入口 |
| `tests/`、`tests/js/` | Python 与页面脚本测试 |
| `scripts/check-private-content.sh`、`.githooks/pre-commit` | 私有内容扫描 |
| `scripts/compare_csv.py` | 生成 CSV 与原生 CSV 的逐行比对 |
| 根目录文档、`docs/ai-coding/`、`.github/` | 开源协作与 AI 编码规范 |

---

### Task 1: 项目骨架、错误码、格式校验与 spec 修订

**Files:**
- Create: `pyproject.toml`、`.gitignore`、`README.md`（最小版，Task 13 扩写）、`LICENSE`、`src/tradingview_capture_mcp/__init__.py`、`src/tradingview_capture_mcp/errors.py`、`src/tradingview_capture_mcp/validation.py`
- Test: `tests/test_errors.py`、`tests/test_validation.py`
- Modify: `docs/superpowers/specs/2026-10-14-tradingview-capture-mcp-design.md`

**Interfaces:**
- Produces: `CaptureError(code, message, detail=None)`，属性 `code` / `message` / `detail`，方法 `to_dict()`；全部错误码常量；`LAYOUT_RE`、`SYMBOL_RE`、`TIMEFRAME_RE`（用 `fullmatch`）；`check_layout(layout) -> str`；`__version__ = "0.1.0"`、`TOOL_NAME = "tradingview-capture-mcp"`。

- [ ] **Step 1: 写骨架文件**

<!-- file: pyproject.toml -->
```toml
[project]
name = "tradingview-capture-mcp"
version = "0.1.0"
description = "Capture TradingView Desktop charts for AI agents over MCP: rendered PNG, export-compatible CSV, and indicator tables, labels, lines and drawings."
readme = "README.md"
license = "Apache-2.0"
license-files = ["LICENSE"]
requires-python = ">=3.12"
keywords = ["tradingview", "mcp", "cdp", "charts"]
classifiers = ["Programming Language :: Python :: 3", "Operating System :: MacOS"]
dependencies = [
  "mcp>=2.3,<3",
  "websockets>=17.2,<18",
  "pillow>=12.3,<13",
]

[project.scripts]
tradingview-capture = "tradingview_capture_mcp.cli:main"

[dependency-groups]
dev = [
  "pytest>=9.1,<10",
  "ruff>=0.17,<0.18",
]

[build-system]
requires = ["hatchling>=1.32,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/tradingview_capture_mcp"]

[tool.ruff]
line-length = 110
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "S"]
# Fixed argv lists are how this tool starts TradingView Desktop and reads pgrep/lsof.
ignore = ["S603", "S607"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106", "S108", "S310"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["tests"]
addopts = "-m 'not live'"
markers = ["live: needs a logged-in TradingView Desktop; run with TRADINGVIEW_CAPTURE_LIVE=1 pytest -m live"]
```

<!-- file: .gitignore -->
```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.DS_Store
```

<!-- file: README.md -->
```text
# tradingview-capture-mcp

驱动 TradingView 桌面版，为 AI 代理采集图表数据的 MCP 服务（开发中）。

*An MCP server that drives TradingView Desktop to capture chart data for AI agents (work in progress).*
```

<!-- file: src/tradingview_capture_mcp/__init__.py -->
```python
"""Capture TradingView Desktop charts for AI agents over MCP."""

__version__ = "0.1.0"
TOOL_NAME = "tradingview-capture-mcp"
```

<!-- file: src/tradingview_capture_mcp/errors.py -->
```python
"""Error codes shared by the command line, the MCP tools and the capture process."""

from __future__ import annotations

from typing import Any

TV_NOT_INSTALLED = "TV_NOT_INSTALLED"
TV_ALREADY_RUNNING = "TV_ALREADY_RUNNING"
TV_STARTUP_TIMEOUT = "TV_STARTUP_TIMEOUT"
PORT_IN_USE = "PORT_IN_USE"
CDP_NOT_LOCAL = "CDP_NOT_LOCAL"
CDP_ERROR = "CDP_ERROR"
LAYOUT_NOT_FOUND = "LAYOUT_NOT_FOUND"
LAYOUT_NOT_UNIQUE = "LAYOUT_NOT_UNIQUE"
TV_INTERNALS_CHANGED = "TV_INTERNALS_CHANGED"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
NOT_READY_TIMEOUT = "NOT_READY_TIMEOUT"
STUDY_MISSING = "STUDY_MISSING"
OUTPUT_EXISTS = "OUTPUT_EXISTS"
OUTPUT_OUTSIDE_ROOT = "OUTPUT_OUTSIDE_ROOT"
BATCH_LOCKED = "BATCH_LOCKED"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
CONFIG_INVALID = "CONFIG_INVALID"
NOT_FOUND = "NOT_FOUND"
INTERNAL_ERROR = "INTERNAL_ERROR"


class CaptureError(Exception):
    """A failure with a stable code that callers and agents can act on."""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}
```

<!-- file: src/tradingview_capture_mcp/validation.py -->
```python
"""Input formats accepted from callers."""

from __future__ import annotations

import re

from .errors import INVALID_ARGUMENT, CaptureError

LAYOUT_RE = re.compile(r"[A-Za-z0-9]{4,32}")
SYMBOL_RE = re.compile(r"[A-Z0-9_]{1,32}:[A-Za-z0-9._!&-]{1,64}")
TIMEFRAME_RE = re.compile(r"[1-9][0-9]{0,3}[SDWM]?|[DWM]")


def check_layout(layout: str) -> str:
    if not isinstance(layout, str) or not LAYOUT_RE.fullmatch(layout):
        raise CaptureError(
            INVALID_ARGUMENT, "layout must be 4-32 letters or digits", {"layout": str(layout)[:64]}
        )
    return layout
```

`LICENSE`：从本机 issuerelay 仓库原样复制 Apache-2.0 标准全文（202 行）：`cp ../issuerelay/LICENSE LICENSE`，再用 `head -3 LICENSE` 确认开头是 `Apache License / Version 2.0, January 2004`。

- [ ] **Step 2: 写测试**

<!-- file: tests/test_errors.py -->
```python
from tradingview_capture_mcp.errors import OUTPUT_EXISTS, CaptureError


def test_capture_error_carries_code_message_and_detail():
    exc = CaptureError(OUTPUT_EXISTS, "refusing to overwrite", {"path": "batch"})
    assert exc.code == "OUTPUT_EXISTS"
    assert str(exc) == "OUTPUT_EXISTS: refusing to overwrite"
    assert exc.to_dict() == {
        "code": "OUTPUT_EXISTS",
        "message": "refusing to overwrite",
        "detail": {"path": "batch"},
    }


def test_detail_defaults_to_an_empty_dict():
    assert CaptureError(OUTPUT_EXISTS, "x").detail == {}
```

<!-- file: tests/test_validation.py -->
```python
import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.validation import SYMBOL_RE, TIMEFRAME_RE, check_layout


@pytest.mark.parametrize("code", ["BINANCE:BTCUSDT.P", "NYMEX:CL1!", "SSE_DLY:000001", "OANDA:XAUUSD"])
def test_accepts_tradingview_codes(code):
    assert SYMBOL_RE.fullmatch(code)


@pytest.mark.parametrize("code", ["BTCUSDT", "binance:BTCUSDT", "BINANCE:", "BINANCE:BTC USDT", "A:B;rm"])
def test_rejects_other_symbol_strings(code):
    assert not SYMBOL_RE.fullmatch(code)


@pytest.mark.parametrize("value", ["1D", "D", "240", "1W", "1M", "15S"])
def test_accepts_resolutions(value):
    assert TIMEFRAME_RE.fullmatch(value)


@pytest.mark.parametrize("value", ["4H", "0", "1d", "", "10000"])
def test_rejects_other_resolutions(value):
    assert not TIMEFRAME_RE.fullmatch(value)


def test_check_layout():
    assert check_layout("Abc12345") == "Abc12345"
    with pytest.raises(CaptureError) as err:
        check_layout("../x")
    assert err.value.code == "INVALID_ARGUMENT"
```

- [ ] **Step 3: 锁定依赖并运行**

Run: `uv lock && uv sync && uv run pytest -q && uv run ruff check && uv run ruff format --check`
Expected: 测试全部 PASS，ruff 无输出。

- [ ] **Step 4: 修订 spec，与本计划对齐**

在 spec 中改五处：
1. 第 2 节参数表：参数名改为 snake_case（`layout`、`symbols`、`timeframe`、`output_dir`、`required_studies`、`viewport`、`ready_timeout_sec`）；`output_dir` 说明改成 Global Constraints 的最后一条。
2. 第 3 节：页面脚本列表改成 `alive`、`ready`、`switch`、`extract`、`screenshot`、`diagnose`。
3. 第 6 节：MCP 工具增加 `capture_retry(output_dir)`，`capture_start` 不再带 `retryFailed`；`image_crop` 在 MCP 里只返回图像，另存文件只在命令行 `crop --out`。
4. 第 7 节：错误码表补 `TV_STARTUP_TIMEOUT`、`PORT_IN_USE`、`CDP_ERROR`、`INVALID_ARGUMENT`、`CONFIG_INVALID`、`NOT_FOUND`、`INTERNAL_ERROR`。
5. 第 4.2 节第 3 步：斐波各档价位在 Task 16 用真实斐波验证换算约定后再输出。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "build: add the package skeleton, error codes and input formats"
```

### Task 2: 本机配置

**Files:**
- Create: `src/tradingview_capture_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `CaptureError`、`CONFIG_INVALID`。
- Produces: `Config(app_path: Path, debug_port: int, output_root: Path)`（frozen），属性 `app_binary`；`config_path() -> Path`；`load_config(path: Path | None = None) -> Config`；`DEFAULT_DEBUG_PORT = 9333`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_config.py -->
```python
import os
from pathlib import Path

import pytest

from tradingview_capture_mcp.config import DEFAULT_DEBUG_PORT, Config, config_path, load_config
from tradingview_capture_mcp.errors import CaptureError


def write(path: Path, text: str, mode: int = 0o600) -> Path:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)
    return path


def test_defaults_and_resolved_output_root(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    config = load_config(write(tmp_path / "c.toml", f'output_root = "{root}"\n'))
    assert config == Config(
        app_path=Path("/Applications/TradingView.app"),
        debug_port=DEFAULT_DEBUG_PORT,
        output_root=root.resolve(),
    )
    assert config.app_binary == Path("/Applications/TradingView.app/Contents/MacOS/TradingView")


def test_reads_every_key(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    text = f'app_path = "{tmp_path / "TV.app"}"\ndebug_port = 9444\noutput_root = "{root}"\n'
    config = load_config(write(tmp_path / "c.toml", text))
    assert (config.app_path, config.debug_port) == (tmp_path / "TV.app", 9444)


@pytest.mark.parametrize(
    "body, needle",
    [
        ("", "output_root is required"),
        ('output_root = "{missing}"\n', "existing directory"),
        ('output_root = "{root}"\ndebug_port = 80\n', "debug_port"),
        ('output_root = "{root}"\ndebug_port = true\n', "debug_port"),
        ('output_root = "{root}"\nextra = 1\n', "unknown config keys"),
        ("output_root = [\n", "not valid TOML"),
    ],
)
def test_rejects_invalid_config(tmp_path, body, needle):
    root = tmp_path / "out"
    root.mkdir()
    path = write(tmp_path / "c.toml", body.format(root=root, missing=tmp_path / "unmounted" / "disk"))
    with pytest.raises(CaptureError) as err:
        load_config(path)
    assert err.value.code == "CONFIG_INVALID"
    assert needle in err.value.message


def test_rejects_a_config_others_can_write(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    path = write(tmp_path / "c.toml", f'output_root = "{root}"\n', mode=0o620)
    with pytest.raises(CaptureError) as err:
        load_config(path)
    assert "writable" in err.value.message


def test_missing_file(tmp_path):
    with pytest.raises(CaptureError) as err:
        load_config(tmp_path / "nope.toml")
    assert err.value.code == "CONFIG_INVALID"


def test_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGVIEW_CAPTURE_CONFIG", str(tmp_path / "x.toml"))
    assert config_path() == tmp_path / "x.toml"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'tradingview_capture_mcp.config'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/config.py -->
```python
"""The local configuration file: where TradingView Desktop is and where batches go."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import CONFIG_INVALID, CaptureError

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "tradingview-capture-mcp" / "config.toml"
DEFAULT_APP_PATH = Path("/Applications/TradingView.app")
DEFAULT_DEBUG_PORT = 9333
KNOWN_KEYS = {"app_path", "debug_port", "output_root"}


@dataclass(frozen=True)
class Config:
    app_path: Path
    debug_port: int
    output_root: Path

    @property
    def app_binary(self) -> Path:
        return self.app_path / "Contents" / "MacOS" / "TradingView"


def config_path() -> Path:
    override = os.environ.get("TRADINGVIEW_CAPTURE_CONFIG")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.is_file():
        raise CaptureError(CONFIG_INVALID, f"config file not found: {path}", {"path": str(path)})
    mode = path.stat().st_mode & 0o777
    if mode & 0o022:
        raise CaptureError(
            CONFIG_INVALID,
            "the config file must not be writable by group or others",
            {"path": str(path), "mode": oct(mode)},
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CaptureError(
            CONFIG_INVALID, f"the config is not valid TOML: {exc}", {"path": str(path)}
        ) from exc
    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        raise CaptureError(CONFIG_INVALID, "unknown config keys", {"keys": unknown})
    output_root = raw.get("output_root")
    if not isinstance(output_root, str) or not output_root:
        raise CaptureError(CONFIG_INVALID, "output_root is required", {})
    root = Path(output_root).expanduser()
    if not root.is_dir():
        raise CaptureError(
            CONFIG_INVALID,
            "output_root must be an existing directory (is the disk mounted?)",
            {"output_root": str(root)},
        )
    port = raw.get("debug_port", DEFAULT_DEBUG_PORT)
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise CaptureError(
            CONFIG_INVALID, "debug_port must be an integer between 1024 and 65535", {"debug_port": port}
        )
    app = raw.get("app_path", str(DEFAULT_APP_PATH))
    if not isinstance(app, str) or not app:
        raise CaptureError(CONFIG_INVALID, "app_path must be a non-empty string", {})
    return Config(app_path=Path(app).expanduser(), debug_port=port, output_root=root.resolve())
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(config): read the local config file and refuse unsafe or unmounted settings"
```

### Task 3: 文件写入、根目录检查与批次锁

**Files:**
- Create: `src/tradingview_capture_mcp/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `sha256_bytes(data) -> str`；`write_new(path, data) -> str`；`dumps_json(value) -> bytes`；`write_json_new(path, value) -> str`；`replace_json(path, value) -> None`；`read_json(path)`；`make_dir_new(path)`；`ensure_dir(path)`；`resolve_inside_root(root, value) -> Path`；`safe_name(code) -> str`；`stamp(moment=None) -> dict`；`BatchLock(root)`（上下文管理器，`acquire()` / `release()`）；`lock_is_held(root) -> bool`；常量 `FILE_MODE = 0o600`、`DIR_MODE = 0o700`、`LOCK_NAME`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_store.py -->
```python
import stat
from datetime import datetime, timedelta, timezone

import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import (
    BatchLock,
    ensure_dir,
    lock_is_held,
    make_dir_new,
    read_json,
    replace_json,
    resolve_inside_root,
    safe_name,
    sha256_bytes,
    stamp,
    write_json_new,
    write_new,
)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_write_new_is_owner_only_and_returns_the_sha(tmp_path):
    path = tmp_path / "a.bin"
    assert write_new(path, b"abc") == sha256_bytes(b"abc")
    assert path.read_bytes() == b"abc"
    assert mode(path) == 0o600


def test_write_new_refuses_to_overwrite(tmp_path):
    path = tmp_path / "a.bin"
    write_new(path, b"one")
    with pytest.raises(CaptureError) as err:
        write_new(path, b"two")
    assert err.value.code == "OUTPUT_EXISTS"
    assert path.read_bytes() == b"one"


def test_json_helpers_round_trip(tmp_path):
    path = tmp_path / "x.json"
    write_json_new(path, {"名称": 1})
    assert read_json(path) == {"名称": 1}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_replace_json_swaps_content_and_keeps_the_mode(tmp_path):
    path = tmp_path / "job.json"
    replace_json(path, {"n": 1})
    replace_json(path, {"n": 2})
    assert read_json(path) == {"n": 2}
    assert mode(path) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["job.json"]


def test_make_dir_new_is_private_and_exclusive(tmp_path):
    target = tmp_path / "batch"
    make_dir_new(target)
    assert mode(target) == 0o700
    with pytest.raises(CaptureError) as err:
        make_dir_new(target)
    assert err.value.code == "OUTPUT_EXISTS"
    ensure_dir(target)


@pytest.mark.parametrize("value", ["relative/dir", "/no/such/parent/dir"])
def test_resolve_rejects_bad_paths(tmp_path, value):
    with pytest.raises(CaptureError) as err:
        resolve_inside_root(tmp_path, value)
    assert err.value.code == "INVALID_ARGUMENT"


def test_resolve_accepts_paths_inside_the_root(tmp_path):
    (tmp_path / "day").mkdir()
    assert (
        resolve_inside_root(tmp_path, tmp_path / "day" / "capture")
        == (tmp_path / "day" / "capture").resolve()
    )


def test_resolve_rejects_paths_outside_the_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(CaptureError) as err:
        resolve_inside_root(root, tmp_path / "elsewhere")
    assert err.value.code == "OUTPUT_OUTSIDE_ROOT"
    with pytest.raises(CaptureError):
        resolve_inside_root(root, root)


def test_resolve_follows_symlinked_parents(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(CaptureError) as err:
        resolve_inside_root(root, root / "link" / "batch")
    assert err.value.code == "OUTPUT_OUTSIDE_ROOT"


def test_safe_name():
    assert safe_name("BINANCE:BTCUSDT.P") == "BINANCE_BTCUSDT.P"
    assert safe_name("NYMEX:CL1!") == "NYMEX_CL1_"


def test_stamp_has_iso_with_offset_and_unix_seconds():
    moment = datetime(2026, 10, 14, 1, 2, 3, 456000, tzinfo=timezone(timedelta(hours=8)))
    assert stamp(moment) == {"iso": "2026-10-14T01:02:03.456+08:00", "unix": round(moment.timestamp(), 3)}


def test_batch_lock_is_exclusive(tmp_path):
    with BatchLock(tmp_path):
        assert lock_is_held(tmp_path)
        with pytest.raises(CaptureError) as err:
            BatchLock(tmp_path).acquire()
        assert err.value.code == "BATCH_LOCKED"
    assert not lock_is_held(tmp_path)
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_store.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.store'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/store.py -->
```python
"""Owner-only, create-only file writes, output-root checks and the batch lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import BATCH_LOCKED, INVALID_ARGUMENT, OUTPUT_EXISTS, OUTPUT_OUTSIDE_ROOT, CaptureError

FILE_MODE = 0o600
DIR_MODE = 0o700
LOCK_NAME = ".tradingview-capture.lock"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]
    os.fsync(fd)


def write_new(path: Path, data: bytes) -> str:
    """Create `path` with mode 0600 and return the SHA-256 of `data`; never overwrite."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    except FileExistsError as exc:
        raise CaptureError(OUTPUT_EXISTS, f"refusing to overwrite {path.name}", {"path": str(path)}) from exc
    try:
        _write_all(fd, data)
    finally:
        os.close(fd)
    return sha256_bytes(data)


def dumps_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json_new(path: Path, value: Any) -> str:
    return write_new(path, dumps_json(value))


def replace_json(path: Path, value: Any) -> None:
    """Atomically replace a progress file; the only kind of file this tool rewrites."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        _write_all(fd, dumps_json(value))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_dir_new(path: Path) -> None:
    try:
        path.mkdir(mode=DIR_MODE)
    except FileExistsError as exc:
        raise CaptureError(OUTPUT_EXISTS, f"{path.name} already exists", {"path": str(path)}) from exc
    os.chmod(path, DIR_MODE)


def ensure_dir(path: Path) -> None:
    path.mkdir(mode=DIR_MODE, exist_ok=True)
    os.chmod(path, DIR_MODE)


def resolve_inside_root(root: Path, value: str | Path) -> Path:
    """Resolve an absolute path whose parent exists inside `root`; the leaf may not exist yet."""
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() or candidate.name in ("", ".", ".."):
        raise CaptureError(INVALID_ARGUMENT, "the path must be absolute", {"path": str(value)})
    try:
        parent = candidate.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise CaptureError(INVALID_ARGUMENT, "the parent directory must exist", {"path": str(value)}) from exc
    resolved = parent / candidate.name
    real_root = root.resolve()
    if parent != real_root and real_root not in parent.parents:
        raise CaptureError(
            OUTPUT_OUTSIDE_ROOT, "the path must be inside the output root", {"path": str(resolved)}
        )
    if resolved.is_symlink():
        raise CaptureError(OUTPUT_OUTSIDE_ROOT, "the path must not be a symlink", {"path": str(resolved)})
    return resolved


def safe_name(code: str) -> str:
    """Folder name for a TradingView code, e.g. BINANCE:BTCUSDT.P -> BINANCE_BTCUSDT.P."""
    return _UNSAFE.sub("_", code)


def stamp(moment: datetime | None = None) -> dict[str, Any]:
    """A timestamp in both forms the outputs use: local ISO 8601 with offset, and UNIX seconds."""
    moment = moment or datetime.now().astimezone()
    return {"iso": moment.isoformat(timespec="milliseconds"), "unix": round(moment.timestamp(), 3)}


class BatchLock:
    """One capture at a time per output root, held with flock for the whole batch."""

    def __init__(self, root: Path) -> None:
        self.path = root / LOCK_NAME
        self._fd: int | None = None

    def acquire(self) -> None:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise CaptureError(BATCH_LOCKED, "another capture is running", {"lock": str(self.path)}) from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> BatchLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def lock_is_held(root: Path) -> bool:
    lock = BatchLock(root)
    try:
        lock.acquire()
    except CaptureError:
        return True
    lock.release()
    return False
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_store.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(store): add create-only private writes, root checks and the batch lock"
```

### Task 4: CDP 客户端

**Files:**
- Create: `src/tradingview_capture_mcp/cdp.py`
- Test: `tests/test_cdp.py`

**Interfaces:**
- Produces: `http_json(port, path, *, timeout=3.0)`（不走代理）；`select_chart_page(targets, layout) -> dict`；`CdpSession(ws_url, *, open_timeout=10.0)`，方法 `call(method, params=None, *, timeout=60.0) -> dict`、`evaluate(expression, *, timeout=60.0)`、`close()`，支持 `with`。页面异常的第一行含 `TV_INTERNALS_CHANGED` 时错误码为 `TV_INTERNALS_CHANGED`，否则 `CDP_ERROR`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_cdp.py -->
```python
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from websockets.sync.server import serve

from tradingview_capture_mcp import cdp
from tradingview_capture_mcp.errors import CaptureError


@pytest.fixture
def devtools():
    """A fake DevTools page endpoint; tests register replies per method."""
    replies = {}

    def handler(connection):
        for raw in connection:
            message = json.loads(raw)
            connection.send(json.dumps({"method": "Runtime.consoleAPICalled", "params": {}}))
            reply = replies.get(message["method"], {"error": {"code": -32601, "message": "unknown method"}})
            if callable(reply):
                reply = reply(message.get("params", {}))
            if reply is None:
                continue
            connection.send(json.dumps({"id": message["id"], **reply}))

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.socket.getsockname()[1]
    yield f"ws://127.0.0.1:{port}/devtools/page/TEST", replies
    server.shutdown()
    thread.join(timeout=5)


def test_call_skips_events_and_returns_the_result(devtools):
    url, replies = devtools
    replies["Browser.getVersion"] = {"result": {"product": "Chrome/146"}}
    with cdp.CdpSession(url) as session:
        assert session.call("Browser.getVersion") == {"product": "Chrome/146"}


def test_evaluate_returns_the_value(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = lambda params: {
        "result": {"result": {"type": "object", "value": {"byValue": params["returnByValue"]}}}
    }
    with cdp.CdpSession(url) as session:
        assert session.evaluate("1") == {"byValue": True}


def test_evaluate_carries_large_values(devtools):
    url, replies = devtools
    big = "x" * (5 * 1024 * 1024)
    replies["Runtime.evaluate"] = {"result": {"result": {"type": "string", "value": big}}}
    with cdp.CdpSession(url) as session:
        assert len(session.evaluate("big")) == len(big)


def test_page_exceptions_become_cdp_errors(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = {
        "result": {
            "result": {},
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "TypeError: x is undefined\n    at <anonymous>:1:1"},
            },
        }
    }
    with cdp.CdpSession(url) as session, pytest.raises(CaptureError) as err:
        session.evaluate("x.y")
    assert (err.value.code, err.value.message) == ("CDP_ERROR", "TypeError: x is undefined")


def test_the_internals_marker_has_its_own_code(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = {
        "result": {
            "result": {},
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "Error: TV_INTERNALS_CHANGED: window.TradingViewApi is missing"},
            },
        }
    }
    with cdp.CdpSession(url) as session, pytest.raises(CaptureError) as err:
        session.evaluate("x")
    assert err.value.code == "TV_INTERNALS_CHANGED"


def test_protocol_errors_and_timeouts(devtools):
    url, replies = devtools
    replies["Never.answers"] = lambda params: None
    with cdp.CdpSession(url) as session:
        with pytest.raises(CaptureError) as err:
            session.call("No.such")
        assert err.value.message == "unknown method"
        with pytest.raises(CaptureError) as err:
            session.call("Never.answers", timeout=0.3)
        assert "timed out" in err.value.message


def test_a_refused_connection_is_a_cdp_error():
    with pytest.raises(CaptureError) as err:
        cdp.CdpSession("ws://127.0.0.1:9/devtools/page/none", open_timeout=1)
    assert err.value.code == "CDP_ERROR"


def test_select_chart_page():
    targets = [
        {"type": "page", "url": "https://www.tradingview.com/chart/AbCd1234/"},
        {"type": "page", "url": "https://www.tradingview.com/chart/Other999/"},
        {"type": "worker", "url": "https://www.tradingview.com/chart/AbCd1234/"},
    ]
    assert cdp.select_chart_page(targets, "AbCd1234") is targets[0]
    with pytest.raises(CaptureError) as err:
        cdp.select_chart_page(targets, "Missing1")
    assert err.value.code == "LAYOUT_NOT_FOUND"
    with pytest.raises(CaptureError) as err:
        cdp.select_chart_page([*targets, dict(targets[0])], "AbCd1234")
    assert err.value.code == "LAYOUT_NOT_UNIQUE"


def test_http_json_reads_loopback():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert cdp.http_json(server.server_address[1], "/json/version") == {"path": "/json/version"}
    finally:
        server.shutdown()
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_cdp.py -q`
Expected: FAIL，`cannot import name 'cdp'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/cdp.py -->
```python
"""A small synchronous Chrome DevTools Protocol client for one page."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .errors import CDP_ERROR, LAYOUT_NOT_FOUND, LAYOUT_NOT_UNIQUE, TV_INTERNALS_CHANGED, CaptureError

# DevTools only listens on loopback; never send these requests through a system proxy.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(port: int, path: str, *, timeout: float = 3.0) -> Any:
    with _LOCAL_OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def select_chart_page(targets: list[dict[str, Any]], layout: str) -> dict[str, Any]:
    needle = f"/chart/{layout}/"
    pages = [t for t in targets if t.get("type") == "page" and needle in str(t.get("url", ""))]
    if not pages:
        raise CaptureError(LAYOUT_NOT_FOUND, "no TradingView tab shows this layout", {"layout": layout})
    if len(pages) > 1:
        raise CaptureError(
            LAYOUT_NOT_UNIQUE, "more than one tab shows this layout", {"layout": layout, "tabs": len(pages)}
        )
    return pages[0]


class CdpSession:
    """One WebSocket connection to a page target; calls run one at a time."""

    def __init__(self, ws_url: str, *, open_timeout: float = 10.0) -> None:
        try:
            # No proxy, no compression, no size limit: screenshots arrive as multi-megabyte strings.
            self._ws = connect(
                ws_url,
                proxy=None,
                compression=None,
                max_size=None,
                open_timeout=open_timeout,
                ping_interval=None,
            )
        except (OSError, WebSocketException) as exc:
            raise CaptureError(CDP_ERROR, f"cannot connect to the page: {exc}", {}) from exc
        self._next_id = 0

    def call(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 60.0
    ) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        deadline = time.monotonic() + timeout
        try:
            self._ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                reply = json.loads(self._ws.recv(timeout=remaining))
                if reply.get("id") != message_id:
                    continue  # an event, or the late reply to an earlier call that timed out
                if "error" in reply:
                    raise CaptureError(
                        CDP_ERROR, str(reply["error"].get("message", "DevTools error")), {"method": method}
                    )
                return reply.get("result") or {}
        except TimeoutError as exc:
            raise CaptureError(
                CDP_ERROR, f"{method} timed out after {timeout:g}s", {"method": method}
            ) from exc
        except WebSocketException as exc:
            raise CaptureError(
                CDP_ERROR, f"the DevTools connection failed: {exc}", {"method": method}
            ) from exc

    def evaluate(self, expression: str, *, timeout: float = 60.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": int(timeout * 1000),
            },
            timeout=timeout + 5.0,
        )
        details = result.get("exceptionDetails")
        if details:
            text = (
                (details.get("exception") or {}).get("description")
                or details.get("text")
                or "page script failed"
            )
            first_line = str(text).splitlines()[0][:300]
            code = TV_INTERNALS_CHANGED if "TV_INTERNALS_CHANGED" in first_line else CDP_ERROR
            raise CaptureError(code, first_line, {"source": "page"})
        return (result.get("result") or {}).get("value")

    def close(self) -> None:
        self._ws.close()

    def __enter__(self) -> CdpSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_cdp.py -q`
Expected: PASS（含 5 MB 消息用例）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(cdp): add a proxy-free DevTools client that selects the layout tab"
```

### Task 5: 页面脚本

**Files:**
- Create: `src/tradingview_capture_mcp/page.py`、`src/tradingview_capture_mcp/page/common.js`、`alive.js`、`ready.js`、`switch.js`、`extract.js`、`screenshot.js`、`diagnose.js`
- Test: `tests/test_page.py`、`tests/js/fake_tv.mjs`、`tests/js/page.test.mjs`

**Interfaces:**
- Produces: `page.SCRIPTS`；`page.build(name, args=None) -> str`，产出 `(async () => {\nconst ARGS = <json>;\n<common.js>\n<script>\n})()`，`alive` 和 `diagnose` 不含 `common.js`。各脚本返回值：
  - `alive` → `{api, symbol}`
  - `ready` → `{symbol, resolution, lastBarTime, studies: [{id, name, status, lastTime, digest}]}`
  - `switch`（`ARGS.symbol`、`ARGS.timeframe`、可选 `ARGS.waitMs`）→ `{before, after, timedOut}`
  - `extract` → `{identity, studies: [{id, name, pane, status, inputs, tables, labels, lines, boxes, lastValues}], drawings, series: {columns, rows, csv}}`
  - `screenshot` → `{width, height, base64}`
  - `diagnose` → `{tradingViewApi, checks: [{name, ok, detail | error}]}`
- 导出规则（2026-10-14 实测，与原生 CSV 的 96 列一致）：指标按窗格序号、再按 z-order 排序；跳过 `alertcondition`、`data` 和所有 `*colorer` 类型；蜡烛图列名是组标题加 ` (Open)` / ` (High` / ` (Low)` / ` (Close)`；数字用 JS 的 `String()`，缺值写空串；没有结尾换行。

- [ ] **Step 1: 写 Python 包装与公共脚本**

<!-- file: src/tradingview_capture_mcp/page.py -->
```python
"""Load the fixed page scripts and wrap them for Runtime.evaluate."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

SCRIPTS = ("alive", "ready", "switch", "extract", "screenshot", "diagnose")
_STANDALONE = {"alive", "diagnose"}


@cache
def _source(name: str) -> str:
    return (
        resources.files("tradingview_capture_mcp").joinpath("page", f"{name}.js").read_text(encoding="utf-8")
    )


def build(name: str, args: dict[str, Any] | None = None) -> str:
    """The expression for one page script; arguments travel as a JSON literal, never as code."""
    if name not in SCRIPTS:
        raise ValueError(f"unknown page script: {name}")
    parts = ["(async () => {", f"const ARGS = {json.dumps(args or {}, ensure_ascii=False)};"]
    if name not in _STANDALONE:
        parts.append(_source("common"))
    parts.append(_source(name))
    parts.append("})()")
    return "\n".join(parts)
```

<!-- file: src/tradingview_capture_mcp/page/common.js -->
```javascript
// Shared helpers for the page scripts. Nothing here changes chart state.
const TV = window.TradingViewApi;
if (!TV) throw new Error('TV_INTERNALS_CHANGED: window.TradingViewApi is missing');
const chart = TV.activeChart();
const model = TV._activeChartWidgetWV.value()._chartWidget.model();
const bars = model.mainSeries().bars();

// Plot types TradingView's own "Export chart data" leaves out.
const SKIPPED_PLOT_TYPES = new Set(['alertcondition', 'data']);
// The export header names candle plots like this, including the missing ")" after "High";
// the generated CSV mirrors it so headers match native exports column for column.
const OHLC_SUFFIX = { ohlc_open: ' (Open)', ohlc_high: ' (High', ohlc_low: ' (Low)', ohlc_close: ' (Close)' };

function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value) {
  return value === null || value === undefined ? null : String(value);
}

function barTime(index) {
  if (typeof index !== 'number') return null;
  const bar = bars.valueAt(index);
  return bar ? bar[0] : null;
}

function studyName(source) {
  const meta = source.metaInfo();
  return meta.description || meta.shortDescription || '';
}

function studyStatus(source) {
  try {
    const status = source.status();
    return status && typeof status.type === 'number' ? status.type : null;
  } catch (e) {
    return null;
  }
}

function paneIndexOf(source) {
  const panes = model.model().panes();
  for (let i = 0; i < panes.length; i += 1) {
    if (panes[i].dataSources().indexOf(source) >= 0) return i;
  }
  return -1;
}

// The user's indicators in the order TradingView's export uses: by pane, then by z-order.
function orderedStudies() {
  const ids = new Set(chart.getAllStudies().map((s) => String(s.id)));
  return model.model().dataSources()
    .filter((s) => typeof s.metaInfo === 'function' && typeof s.id === 'function' && ids.has(String(s.id())))
    .map((source) => ({ source, pane: paneIndexOf(source), z: source.zorder() }))
    .sort((a, b) => a.pane - b.pane || a.z - b.z)
    .map((entry) => entry.source);
}

function plotTitle(meta, plot) {
  if (OHLC_SUFFIX[plot.type]) {
    const group = meta.ohlcPlots && meta.ohlcPlots[plot.target];
    return ((group && group.title) || plot.target || plot.id) + OHLC_SUFFIX[plot.type];
  }
  const style = meta.styles && meta.styles[plot.id];
  return (style && style.title) || plot.id;
}

// Plots the native CSV includes, with their position in a data row (position 0 is the time).
function exportedPlots(meta) {
  const out = [];
  meta.plots.forEach((plot, index) => {
    if (SKIPPED_PLOT_TYPES.has(plot.type) || /colorer$/.test(plot.type)) return;
    out.push({ column: index + 1, title: plotTitle(meta, plot) });
  });
  return out;
}

function primitives(source, collection, key) {
  const all = source._graphics && source._graphics._primitivesCollection;
  if (!all || !all[collection] || typeof all[collection].get !== 'function') return [];
  const outer = all[collection].get(key);
  if (!outer) return [];
  const inner = typeof outer.get === 'function' ? outer.get(false) || outer : outer;
  const byId = inner && inner._primitivesDataById;
  return byId ? Array.from(byId.values()) : [];
}
```

<!-- file: src/tradingview_capture_mcp/page/alive.js -->
```javascript
// Standalone: is the chart API there yet? Polled while TradingView Desktop starts.
let symbol = null;
try {
  symbol = window.TradingViewApi.activeChart().symbol() || null;
} catch (e) {
  symbol = null;
}
return { api: typeof window.TradingViewApi, symbol };
```

<!-- file: src/tradingview_capture_mcp/page/ready.js -->
```javascript
// A cheap fingerprint of the chart, polled after a switch until it settles.
const lastIndex = bars.lastIndex();
const lastBar = bars.valueAt(lastIndex);
const studies = orderedStudies().map((source) => {
  const data = source.data();
  const row = data && data.size() > 0 ? data.valueAt(lastIndex) : null;
  const cells = primitives(source, 'dwgtablecells', 'tableCells')
    .map((c) => [c.tid || 0, c.row, c.col, c.t])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => [l.x, l.y, l.t]);
  return {
    id: String(source.id()),
    name: studyName(source),
    status: studyStatus(source),
    lastTime: row ? row[0] : null,
    digest: JSON.stringify([row ? row.slice(1) : null, cells, labels]),
  };
});
return { symbol: chart.symbol(), resolution: chart.resolution(), lastBarTime: lastBar ? lastBar[0] : null, studies };
```

<!-- file: src/tradingview_capture_mcp/page/switch.js -->
```javascript
// The only script that changes the chart: it sets the resolution and the symbol.
const target = ARGS.symbol;
const timeframe = ARGS.timeframe;
const waitMs = ARGS.waitMs || 20000;

function settle(start) {
  return Promise.race([
    new Promise((resolve) => start(() => resolve(false))),
    new Promise((resolve) => setTimeout(() => resolve(true), waitMs)),
  ]);
}

const before = { symbol: chart.symbol(), resolution: chart.resolution() };
let timedOut = false;
if (timeframe && chart.resolution() !== timeframe) {
  timedOut = (await settle((done) => chart.setResolution(timeframe, done))) || timedOut;
}
if (chart.symbol() !== target) {
  timedOut = (await settle((done) => chart.setSymbol(target, done))) || timedOut;
}
return { before, after: { symbol: chart.symbol(), resolution: chart.resolution() }, timedOut };
```

- [ ] **Step 2: 写提取、截图与诊断脚本**

<!-- file: src/tradingview_capture_mcp/page/extract.js -->
```javascript
// Reads everything a capture keeps, in one call so the parts describe the same moment.
const lastIndex = bars.lastIndex();
const last = bars.valueAt(lastIndex);
let info = null;
try {
  info = model.mainSeries().symbolInfo();
} catch (e) {
  info = null;
}
const identity = {
  symbol: chart.symbol(),
  resolution: chart.resolution(),
  description: (info && info.description) || null,
  exchange: (info && (info.exchange || info.listed_exchange)) || null,
  barsCount: bars.size(),
  firstBarTime: barTime(bars.firstIndex()),
  lastBar: last ? { time: last[0], open: num(last[1]), high: num(last[2]), low: num(last[3]), close: num(last[4]) } : null,
};

function plain(value) {
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (e) {
    return null;
  }
}

const ordered = orderedStudies();
const studies = ordered.map((source) => {
  const meta = source.metaInfo();
  const tables = new Map();
  for (const cell of primitives(source, 'dwgtablecells', 'tableCells')) {
    const id = String(cell.tid || 0);
    if (!tables.has(id)) tables.set(id, []);
    const rows = tables.get(id);
    while (rows.length <= cell.row) rows.push([]);
    const row = rows[cell.row];
    while (row.length <= cell.col) row.push(null);
    row[cell.col] = text(cell.t);
  }
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => ({
    id: l.id, index: l.x, time: barTime(l.x), price: num(l.y), text: text(l.t) || '',
    style: l.st || null, color: l.ci === undefined ? null : l.ci, textColor: l.tci === undefined ? null : l.tci,
    size: l.sz || null, tooltip: l.tt || null,
  }));
  const lines = primitives(source, 'dwglines', 'lines').map((l) => ({
    id: l.id, index1: l.x1, time1: barTime(l.x1), price1: num(l.y1), index2: l.x2, time2: barTime(l.x2), price2: num(l.y2),
    extend: l.ex || null, style: l.st === undefined ? null : l.st, color: l.ci === undefined ? null : l.ci,
    width: l.w === undefined ? null : l.w,
  }));
  const boxes = primitives(source, 'dwgboxes', 'boxes').map((b) => plain(b) || { id: b.id });
  const data = source.data();
  const row = data && data.size() > 0 ? data.valueAt(lastIndex) : null;
  const lastValues = exportedPlots(meta).map((p) => [p.title, row ? num(row[p.column]) : null]);
  let inputs = null;
  try {
    inputs = source.inputs ? plain(source.inputs()) : null;
  } catch (e) {
    inputs = null;
  }
  return {
    id: String(source.id()), name: studyName(source), pane: paneIndexOf(source), status: studyStatus(source), inputs,
    tables: Array.from(tables, ([id, rows]) => ({ id, rows })), labels, lines, boxes, lastValues,
  };
});

const drawings = chart.getAllShapes().map((shape) => {
  const api = chart.getShapeById(shape.id);
  let points = [];
  try {
    points = api._source.points().map((p) => ({ index: p.index, time: barTime(p.index), price: num(p.price) }));
  } catch (e) {
    points = [];
  }
  let props = {};
  try {
    props = api.getProperties() || {};
  } catch (e) {
    props = {};
  }
  const levels = [];
  for (let i = 1; i <= 24; i += 1) {
    const level = props['level' + i];
    if (Array.isArray(level)) levels.push({ coeff: num(level[0]), visible: level[2] === true, text: text(level[3]) || '' });
  }
  return { id: String(shape.id), type: shape.name, points, levels, reverse: props.reverse === true };
});

function csvCell(value) {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
}

function csvHeader(title) {
  return /[",\n\r]/.test(title) ? '"' + title.replace(/"/g, '""') + '"' : title;
}

const plotSets = ordered.map((source) => ({ data: source.data(), plots: exportedPlots(source.metaInfo()) }));
const header = ['time', 'open', 'high', 'low', 'close'];
plotSets.forEach((set) => set.plots.forEach((p) => header.push(p.title)));
const csvLines = [header.map(csvHeader).join(',')];
for (let i = bars.firstIndex(); i <= lastIndex; i += 1) {
  const bar = bars.valueAt(i);
  if (!bar) continue;
  const cells = [String(bar[0]), csvCell(bar[1]), csvCell(bar[2]), csvCell(bar[3]), csvCell(bar[4])];
  for (const set of plotSets) {
    const values = set.data && set.data.size() > 0 ? set.data.valueAt(i) : null;
    for (const p of set.plots) cells.push(values ? csvCell(values[p.column]) : '');
  }
  csvLines.push(cells.join(','));
}

return { identity, studies, drawings, series: { columns: header.length, rows: csvLines.length - 1, csv: csvLines.join('\n') } };
```

<!-- file: src/tradingview_capture_mcp/page/screenshot.js -->
```javascript
// TradingView's own rendering of the chart, as PNG bytes in base64.
const canvas = await TV.takeClientScreenshot();
const url = canvas.toDataURL('image/png');
return { width: canvas.width, height: canvas.height, base64: url.slice(url.indexOf(',') + 1) };
```

<!-- file: src/tradingview_capture_mcp/page/diagnose.js -->
```javascript
// Standalone: reports which internal paths a capture relies on, never chart contents.
const report = { tradingViewApi: typeof window.TradingViewApi, checks: [] };

function check(name, fn) {
  try {
    const detail = fn();
    report.checks.push({ name, ok: true, detail: detail === undefined ? null : detail });
  } catch (e) {
    report.checks.push({ name, ok: false, error: String((e && e.message) || e).slice(0, 200) });
  }
}

const TV = window.TradingViewApi;
let chart = null;
let model = null;
check('activeChart', () => {
  chart = TV.activeChart();
  return ['symbol', 'resolution', 'setSymbol', 'setResolution', 'getAllStudies', 'getAllShapes', 'getShapeById']
    .filter((name) => typeof chart[name] !== 'function');
});
check('takeClientScreenshot', () => typeof TV.takeClientScreenshot);
check('chartWidget', () => {
  model = TV._activeChartWidgetWV.value()._chartWidget.model();
  return Object.keys(model).length;
});
check('mainSeriesBars', () => {
  const b = model.mainSeries().bars();
  return { size: b.size(), firstIndex: typeof b.firstIndex, lastIndex: typeof b.lastIndex, valueAt: typeof b.valueAt };
});
check('dataSources', () => model.model().dataSources().length);
check('panes', () => model.model().panes().length);
check('studies', () => {
  const ids = new Set(chart.getAllStudies().map((s) => String(s.id)));
  return model.model().dataSources()
    .filter((s) => typeof s.id === 'function' && ids.has(String(s.id())))
    .map((s) => {
      const all = s._graphics && s._graphics._primitivesCollection;
      const data = typeof s.data === 'function' ? s.data() : null;
      return {
        hasMetaInfo: typeof s.metaInfo === 'function',
        plots: typeof s.metaInfo === 'function' ? (s.metaInfo().plots || []).length : null,
        zorder: typeof s.zorder,
        status: typeof s.status,
        data: data ? { size: typeof data.size === 'function' ? data.size() : null, valueAt: typeof data.valueAt } : null,
        collections: all
          ? ['dwgtablecells', 'dwglabels', 'dwglines', 'dwgboxes'].filter((k) => all[k] && typeof all[k].get === 'function')
          : [],
      };
    });
});
check('shapes', () => chart.getAllShapes().map((s) => s.name));
return report;
```

- [ ] **Step 3: 写测试**

<!-- file: tests/test_page.py -->
```python
import json

import pytest

from tradingview_capture_mcp import page


def test_build_wraps_common_and_script_with_json_args():
    code = page.build("switch", {"symbol": 'BINANCE:"X"', "timeframe": "1D"})
    assert code.startswith("(async () => {\nconst ARGS = ")
    assert code.endswith("\n})()")
    args_line = code.splitlines()[1]
    assert json.loads(args_line[len("const ARGS = ") : -1]) == {"symbol": 'BINANCE:"X"', "timeframe": "1D"}
    assert "function orderedStudies" in code


@pytest.mark.parametrize("name", ["alive", "diagnose"])
def test_standalone_scripts_leave_out_common(name):
    assert "function orderedStudies" not in page.build(name)


def test_every_script_is_packaged():
    assert all(page.build(name) for name in page.SCRIPTS)


def test_unknown_scripts_are_rejected():
    with pytest.raises(ValueError):
        page.build("eval")
```

<!-- file: tests/js/fake_tv.mjs -->
```javascript
// A minimal stand-in for the parts of TradingView Desktop's chart model the page scripts read.
export function plotList(rows, firstIndex = 0) {
  return {
    size: () => rows.length,
    firstIndex: () => firstIndex,
    lastIndex: () => firstIndex + rows.length - 1,
    valueAt: (index) => rows[index - firstIndex] || null,
  };
}

function primitiveCollection(key, items) {
  const byId = new Map(items.map((item) => [item.id, item]));
  return { get: (name) => (name === key ? { get: () => ({ _primitivesDataById: byId }) } : null) };
}

export function makeStudy({ id, name, zorder, plots, rows, styles = {}, ohlcPlots, cells = [], labels = [], lines = [], boxes = [], status = 2 }) {
  return {
    id: () => id,
    zorder: () => zorder,
    status: () => ({ type: status }),
    metaInfo: () => ({ description: name, plots, styles, ohlcPlots }),
    data: () => plotList(rows),
    inputs: () => ({ length: 14 }),
    _graphics: {
      _primitivesCollection: {
        dwgtablecells: primitiveCollection('tableCells', cells),
        dwglabels: primitiveCollection('labels', labels),
        dwglines: primitiveCollection('lines', lines),
        dwgboxes: primitiveCollection('boxes', boxes),
      },
    },
  };
}

export function makeTradingView({ symbol = 'BINANCE:BTCUSDT.P', resolution = '1D', bars, panes, shapes = [], onSetSymbol }) {
  const state = { symbol, resolution };
  const studies = panes.flat();
  const builtin = { id: () => 'builtin', zorder: () => 10000006, metaInfo: () => ({ description: 'Dividends', plots: [] }) };
  const chart = {
    symbol: () => state.symbol,
    resolution: () => state.resolution,
    setSymbol: (value, done) => {
      state.symbol = value;
      if (onSetSymbol) onSetSymbol(value, done);
      else done();
    },
    setResolution: (value, done) => {
      state.resolution = value;
      done();
    },
    getAllStudies: () => studies.map((s) => ({ id: s.id(), name: s.metaInfo().description })),
    getAllShapes: () => shapes.map((s) => ({ id: s.id, name: s.name })),
    getShapeById: (id) => {
      const shape = shapes.find((s) => s.id === id);
      return { _source: { points: () => shape.points }, getProperties: () => shape.properties };
    },
  };
  const model = {
    mainSeries: () => ({ bars: () => bars, symbolInfo: () => ({ description: 'Bitcoin / TetherUS', exchange: 'Binance' }) }),
    model: () => ({
      dataSources: () => [...studies].reverse().concat([builtin]),
      panes: () => panes.map((list) => ({ dataSources: () => list })),
    }),
  };
  return {
    TradingViewApi: {
      activeChart: () => chart,
      _activeChartWidgetWV: { value: () => ({ _chartWidget: { model: () => model } }) },
      takeClientScreenshot: async () => ({ width: 2, height: 1, toDataURL: () => 'data:image/png;base64,iVBORw0KGgo=' }),
    },
  };
}
```

<!-- file: tests/js/page.test.mjs -->
```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { makeStudy, makeTradingView, plotList } from './fake_tv.mjs';

const PAGE = new URL('../../src/tradingview_capture_mcp/page/', import.meta.url);
const STANDALONE = new Set(['alive', 'diagnose']);
const source = (name) => readFileSync(new URL(`${name}.js`, PAGE), 'utf8');

// Mirrors tradingview_capture_mcp.page.build(): the expression Runtime.evaluate receives.
async function run(name, args, window) {
  const parts = ['(async () => {', `const ARGS = ${JSON.stringify(args || {})};`];
  if (!STANDALONE.has(name)) parts.push(source('common'));
  parts.push(source(name), '})()');
  const value = await vm.runInNewContext(parts.join('\n'), { window, setTimeout });
  return JSON.parse(JSON.stringify(value)); // returnByValue hands back plain JSON
}

function fixture(overrides = {}) {
  const assist = makeStudy({
    id: 'a1', name: 'Assist', zorder: -20000,
    plots: [{ id: 'plot_0', type: 'line' }, { id: 'plot_1', type: 'colorer' }, { id: 'plot_2', type: 'shapes' }, { id: 'plot_3', type: 'alertcondition' }],
    styles: { plot_0: { title: 'Quarter' }, plot_2: { title: 'Shapes' } },
    rows: [[1000, 10.5, 0, 1, 1], [2000, 11.25, 1, null, 0]],
    cells: [{ id: 1, tid: 0, row: 0, col: 0, t: 'Head' }, { id: 2, tid: 0, row: 1, col: 2, t: 'NaN' }],
    labels: [{ id: 7, x: 1, y: 2.5, t: '9.5', st: 'lup', ci: null, tci: 4278226175, sz: 'small', tt: '' }],
    lines: [{ id: 9, x1: 0, y1: 1, x2: 1, y2: 2, ex: 'n', st: 0, ci: 255, w: 1 }],
  });
  const band = makeStudy({
    id: 'b1', name: 'Band', zorder: -10000, plots: [{ id: 'plot_0', type: 'line' }],
    styles: { plot_0: { title: 'Upper, Inner' } }, rows: [[1000, Number.NaN], [2000, 3]],
  });
  const delta = makeStudy({
    id: 'c1', name: 'Delta', zorder: -10000,
    plots: [{ id: 'plot_0', type: 'ohlc_open', target: 'plotcandle_0' }, { id: 'plot_1', type: 'ohlc_high', target: 'plotcandle_0' }, { id: 'plot_2', type: 'data' }],
    ohlcPlots: { plotcandle_0: { title: 'Body' } }, rows: [[1000, 5, 6, 7], [2000, 8, 9, 10]],
  });
  return makeTradingView({
    bars: plotList([[1000, 1, 2, 0.5, 1.5], [2000, 1.5, 2.5, 1, 2]]),
    panes: [[assist, band], [delta]],
    shapes: [{
      id: 's1', name: 'fib_retracement', points: [{ index: 0, price: 1 }, { index: 1, price: 2 }],
      properties: { level1: [0, '#808080', true, ''], level2: [0.236, '#F23645', false, ''], reverse: false },
    }],
    ...overrides,
  });
}

test('extract orders studies by pane then z-order and writes export-shaped CSV', async () => {
  const result = await run('extract', {}, fixture());
  assert.deepEqual(result.studies.map((s) => s.name), ['Assist', 'Band', 'Delta']);
  assert.equal(result.series.csv, [
    'time,open,high,low,close,Quarter,Shapes,"Upper, Inner",Body (Open),Body (High',
    '1000,1,2,0.5,1.5,10.5,1,,5,6',
    '2000,1.5,2.5,1,2,11.25,,3,8,9',
  ].join('\n'));
  assert.equal(result.series.rows, 2);
  assert.equal(result.series.columns, 10);
});

test('extract returns tables, labels, lines, last values, drawings and identity', async () => {
  const result = await run('extract', {}, fixture());
  const [assist] = result.studies;
  assert.deepEqual(assist.tables, [{ id: '0', rows: [['Head'], [null, null, 'NaN']] }]);
  assert.deepEqual(assist.labels, [{ id: 7, index: 1, time: 2000, price: 2.5, text: '9.5', style: 'lup', color: null, textColor: 4278226175, size: 'small', tooltip: null }]);
  assert.deepEqual(assist.lines, [{ id: 9, index1: 0, time1: 1000, price1: 1, index2: 1, time2: 2000, price2: 2, extend: 'n', style: 0, color: 255, width: 1 }]);
  assert.deepEqual(assist.lastValues, [['Quarter', 11.25], ['Shapes', null]]);
  assert.deepEqual(result.drawings, [{
    id: 's1', type: 'fib_retracement',
    points: [{ index: 0, time: 1000, price: 1 }, { index: 1, time: 2000, price: 2 }],
    levels: [{ coeff: 0, visible: true, text: '' }, { coeff: 0.236, visible: false, text: '' }], reverse: false,
  }]);
  assert.deepEqual(result.identity, {
    symbol: 'BINANCE:BTCUSDT.P', resolution: '1D', description: 'Bitcoin / TetherUS', exchange: 'Binance',
    barsCount: 2, firstBarTime: 1000, lastBar: { time: 2000, open: 1.5, high: 2.5, low: 1, close: 2 },
  });
});

test('ready reports status, last time and a digest per study', async () => {
  const result = await run('ready', {}, fixture());
  assert.equal(result.symbol, 'BINANCE:BTCUSDT.P');
  assert.equal(result.lastBarTime, 2000);
  assert.deepEqual(result.studies.map((s) => [s.id, s.name, s.status, s.lastTime]), [['a1', 'Assist', 2, 2000], ['b1', 'Band', 2, 2000], ['c1', 'Delta', 2, 2000]]);
  assert.equal(typeof result.studies[0].digest, 'string');
});

test('switch changes resolution and symbol and reports a stuck callback', async () => {
  const moved = await run('switch', { symbol: 'BINANCE:ETHUSDT.P', timeframe: '1D' }, fixture({ resolution: '240' }));
  assert.deepEqual(moved, {
    before: { symbol: 'BINANCE:BTCUSDT.P', resolution: '240' },
    after: { symbol: 'BINANCE:ETHUSDT.P', resolution: '1D' },
    timedOut: false,
  });
  const stuck = await run('switch', { symbol: 'BINANCE:ETHUSDT.P', timeframe: '1D', waitMs: 20 }, fixture({ onSetSymbol: () => {} }));
  assert.equal(stuck.timedOut, true);
});

test('screenshot returns the PNG payload without the data URL prefix', async () => {
  assert.deepEqual(await run('screenshot', {}, fixture()), { width: 2, height: 1, base64: 'iVBORw0KGgo=' });
});

test('alive and diagnose never throw', async () => {
  assert.deepEqual(await run('alive', {}, {}), { api: 'undefined', symbol: null });
  const broken = await run('diagnose', {}, {});
  assert.equal(broken.tradingViewApi, 'undefined');
  assert.ok(broken.checks.every((c) => c.ok === false));
  const report = await run('diagnose', {}, fixture());
  assert.ok(report.checks.every((c) => c.ok), JSON.stringify(report.checks));
  const studies = report.checks.find((c) => c.name === 'studies').detail;
  assert.equal(studies.length, 3);
  assert.deepEqual(studies[0].collections, ['dwgtablecells', 'dwglabels', 'dwglines', 'dwgboxes']);
});

test('common throws a recognisable error when the chart API is missing', async () => {
  await assert.rejects(run('ready', {}, {}), /TV_INTERNALS_CHANGED/);
});
```

- [ ] **Step 4: 运行**

Run: `uv run pytest tests/test_page.py -q && node --test "tests/js/*.test.mjs"`
Expected: 两边全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(page): add the fixed read-only page scripts with export-compatible CSV"
```

### Task 6: 就绪判断

**Files:**
- Create: `src/tradingview_capture_mcp/readiness.py`
- Test: `tests/test_readiness.py`

**Interfaces:**
- Consumes: `ready` 脚本的返回值。
- Produces: `StudyState(id, name, status, last_time, digest)`、`ReadySnapshot(symbol, resolution, last_bar_time, studies)`，`ReadySnapshot.from_page(raw)`（digest 存成 SHA-256）；`ReadyVerdict(ready, reason, unchanged)`；`normalize_resolution(value)`；`judge(*, target, timeframe, current, previous, before_switch, elapsed, grace_sec=10.0) -> ReadyVerdict`；`wait_until_ready(read, *, target, timeframe, before_switch, timeout, sleep, clock, interval=1.0, grace_sec=10.0) -> (verdict, snapshot, polls, waited)`，超时抛 `NOT_READY_TIMEOUT`；`STATUS_COMPLETED = 2`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_readiness.py -->
```python
import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.readiness import ReadySnapshot, judge, normalize_resolution, wait_until_ready

TARGET = "BINANCE:AAAUSDT.P"


def snap(symbol=TARGET, resolution="1D", last=2000, studies=(("s1", "Alpha", 2, 2000, "new"),)):
    return ReadySnapshot.from_page(
        {
            "symbol": symbol,
            "resolution": resolution,
            "lastBarTime": last,
            "studies": [
                {"id": i, "name": n, "status": st, "lastTime": lt, "digest": d} for i, n, st, lt, d in studies
            ],
        }
    )


def verdict(current, *, previous="same", before=None, elapsed=0.0):
    return judge(
        target=TARGET,
        timeframe="1D",
        current=current,
        previous=current if previous == "same" else previous,
        before_switch=before,
        elapsed=elapsed,
    )


def test_ready_when_everything_lines_up():
    assert verdict(snap()).ready


@pytest.mark.parametrize(
    "current, reason",
    [
        (snap(symbol="BINANCE:OLDUSDT.P"), "symbol"),
        (snap(resolution="240"), "resolution"),
        (snap(last=None), "bars"),
        (snap(studies=(("s1", "Alpha", 1, 2000, "new"),)), "status:Alpha"),
        (snap(studies=(("s1", "Alpha", 2, 1000, "new"),)), "lastTime:Alpha"),
    ],
)
def test_each_unmet_condition_is_named(current, reason):
    result = verdict(current)
    assert (result.ready, result.reason) == (False, reason)


def test_daily_resolutions_compare_equal():
    assert normalize_resolution("D") == normalize_resolution("1D") == "1D"
    assert verdict(snap(resolution="D")).ready


def test_two_identical_reads_are_required():
    assert verdict(snap(), previous=None).reason == "unstable"
    assert verdict(snap(), previous=snap(studies=(("s1", "Alpha", 2, 2000, "older"),))).reason == "unstable"


def test_stale_tables_wait_for_the_grace_period():
    before = snap(symbol="BINANCE:OLDUSDT.P", studies=(("s1", "Alpha", 2, 2000, "new"),))
    early = verdict(snap(), before=before, elapsed=3.0)
    assert (early.ready, early.reason, early.unchanged) == (False, "unchanged:Alpha", ("Alpha",))
    late = verdict(snap(), before=before, elapsed=10.0)
    assert (late.ready, late.unchanged) == (True, ("Alpha",))


def test_unchanged_data_is_fine_when_the_symbol_did_not_change():
    assert verdict(snap(), before=snap(), elapsed=0.0).ready


def test_wait_until_ready_polls_until_stable():
    reads = iter([snap(studies=(("s1", "Alpha", 1, 2000, "new"),)), snap(), snap()])
    now = [0.0]
    result, snapshot, polls, waited = wait_until_ready(
        lambda: next(reads),
        target=TARGET,
        timeframe="1D",
        before_switch=None,
        timeout=30,
        sleep=lambda s: now.__setitem__(0, now[0] + s),
        clock=lambda: now[0],
    )
    assert result.ready and snapshot == snap() and polls == 3 and waited == 2.0


def test_wait_until_ready_times_out_with_the_reason():
    now = [0.0]
    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            lambda: snap(symbol="BINANCE:OLDUSDT.P"),
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            timeout=5,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail["reason"] == "symbol"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_readiness.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.readiness'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/readiness.py -->
```python
"""Decide when a freshly switched chart is safe to read."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import NOT_READY_TIMEOUT, CaptureError

STATUS_COMPLETED = 2


@dataclass(frozen=True)
class StudyState:
    id: str
    name: str
    status: int | None
    last_time: int | None
    digest: str


@dataclass(frozen=True)
class ReadySnapshot:
    symbol: str
    resolution: str
    last_bar_time: int | None
    studies: tuple[StudyState, ...]

    @classmethod
    def from_page(cls, raw: dict[str, Any]) -> ReadySnapshot:
        return cls(
            symbol=str(raw.get("symbol") or ""),
            resolution=str(raw.get("resolution") or ""),
            last_bar_time=raw.get("lastBarTime"),
            studies=tuple(
                StudyState(
                    id=str(s.get("id") or ""),
                    name=str(s.get("name") or ""),
                    status=s.get("status"),
                    last_time=s.get("lastTime"),
                    digest=hashlib.sha256(str(s.get("digest")).encode("utf-8")).hexdigest(),
                )
                for s in raw.get("studies") or []
            ),
        )


@dataclass(frozen=True)
class ReadyVerdict:
    ready: bool
    reason: str | None
    unchanged: tuple[str, ...] = ()


def normalize_resolution(value: str) -> str:
    upper = value.strip().upper()
    return "1" + upper if upper in {"D", "W", "M"} else upper


def judge(
    *,
    target: str,
    timeframe: str,
    current: ReadySnapshot,
    previous: ReadySnapshot | None,
    before_switch: ReadySnapshot | None,
    elapsed: float,
    grace_sec: float = 10.0,
) -> ReadyVerdict:
    """Ready means: right symbol and resolution, every study finished on the last bar, two equal reads,
    and the studies' output differs from the previous symbol's (or the grace period has passed)."""
    if current.symbol != target:
        return ReadyVerdict(False, "symbol")
    if normalize_resolution(current.resolution) != normalize_resolution(timeframe):
        return ReadyVerdict(False, "resolution")
    if current.last_bar_time is None:
        return ReadyVerdict(False, "bars")
    for study in current.studies:
        if study.status is not None and study.status != STATUS_COMPLETED:
            return ReadyVerdict(False, f"status:{study.name}")
        if study.last_time != current.last_bar_time:
            return ReadyVerdict(False, f"lastTime:{study.name}")
    if previous != current:
        return ReadyVerdict(False, "unstable")
    unchanged: tuple[str, ...] = ()
    if before_switch is not None and before_switch.symbol != target:
        old = {s.id: s.digest for s in before_switch.studies}
        unchanged = tuple(s.name for s in current.studies if old.get(s.id) == s.digest)
        if unchanged and elapsed < grace_sec:
            return ReadyVerdict(False, f"unchanged:{unchanged[0]}", unchanged)
    return ReadyVerdict(True, None, unchanged)


def wait_until_ready(
    read: Callable[[], ReadySnapshot],
    *,
    target: str,
    timeframe: str,
    before_switch: ReadySnapshot | None,
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    interval: float = 1.0,
    grace_sec: float = 10.0,
) -> tuple[ReadyVerdict, ReadySnapshot, int, float]:
    start = clock()
    previous: ReadySnapshot | None = None
    polls = 0
    while True:
        current = read()
        polls += 1
        elapsed = clock() - start
        verdict = judge(
            target=target,
            timeframe=timeframe,
            current=current,
            previous=previous,
            before_switch=before_switch,
            elapsed=elapsed,
            grace_sec=grace_sec,
        )
        if verdict.ready:
            return verdict, current, polls, elapsed
        if elapsed >= timeout:
            raise CaptureError(
                NOT_READY_TIMEOUT,
                f"the chart was not ready after {timeout:g}s",
                {"reason": verdict.reason, "polls": polls},
            )
        previous = current
        sleep(interval)
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_readiness.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(readiness): wait for settled, refreshed studies before reading a chart"
```

### Task 7: PNG 检查与裁图

**Files:**
- Create: `src/tradingview_capture_mcp/images.py`、`tests/helpers.py`
- Test: `tests/test_images.py`

**Interfaces:**
- Produces: `png_size(data) -> tuple[int, int] | None`；`crop_png(path, x, y, width, height) -> bytes`（越界或不是 PNG 抛 `INVALID_ARGUMENT`）。测试辅助 `helpers.png_bytes(width=8, height=6, color=(10, 20, 30))`、`helpers.write_config(tmp_path, output_root, **extra)`、`helpers.make_batch(out, symbol, *, csv_text=..., png=None)`。

- [ ] **Step 1: 写测试辅助与失败的测试**

<!-- file: tests/helpers.py -->
```python
"""Builders shared by the Python tests: PNG bytes, config files and finished batches."""

import io
import json
import os
from pathlib import Path

from PIL import Image

from tradingview_capture_mcp.store import ensure_dir, safe_name, write_json_new, write_new

DEFAULT_CSV = "time,open,high,low,close\n1000,1,2,0.5,1.5\n2000,1.5,2.5,1,2"


def png_bytes(width=8, height=6, color=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def write_config(tmp_path: Path, output_root: Path, **extra) -> Path:
    lines = [f'output_root = "{output_root}"'] + [
        f"{key} = {json.dumps(value)}" for key, value in extra.items()
    ]
    path = tmp_path / "config.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def make_batch(out: Path, symbol: str, *, csv_text: str = DEFAULT_CSV, png: bytes | None = None) -> Path:
    """A finished one-symbol batch shaped like the capture output."""
    ensure_dir(out)
    ensure_dir(out / "raw")
    folder = out / "raw" / safe_name(symbol)
    ensure_dir(folder)
    data = {
        "schemaVersion": 1,
        "identity": {"symbol": symbol, "resolution": "1D"},
        "studies": [
            {
                "id": "s1",
                "name": "Alpha",
                "tables": [{"id": "0", "rows": [["Head", None]]}],
                "labels": [{"text": "9.5", "time": 2000}],
                "lines": [],
                "boxes": [],
                "lastValues": [["Quarter", 11.25]],
                "inputs": {"length": 14},
            }
        ],
        "drawings": [],
        "readiness": {"polls": 3},
    }
    write_new(folder / "image.png", png or png_bytes(40, 30))
    write_new(folder / "chart.csv", csv_text.encode("utf-8"))
    write_json_new(folder / "data.json", data)
    write_json_new(
        folder / "capture.json",
        {
            "captureMethod": "CDP_DESKTOP",
            "desktop": {"version": "3.4.1"},
            "times": {"finishedAt": {"iso": "2026-10-14T02:00:00.000+08:00", "unix": 1791914400.0}},
            "files": {},
        },
    )
    write_json_new(
        out / "capture-manifest.json",
        {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "finished",
            "symbols": [{"symbol": symbol, "status": "ok"}],
            "totals": {"succeeded": 1},
        },
    )
    return folder
```

<!-- file: tests/test_images.py -->
```python
import io

import pytest
from helpers import png_bytes
from PIL import Image

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.images import crop_png, png_size


def test_png_size_reads_the_header():
    assert png_size(png_bytes(12, 7)) == (12, 7)
    assert png_size(b"not a png at all, just some text") is None
    assert png_size(b"") is None


def test_crop_returns_the_requested_region(tmp_path):
    path = tmp_path / "image.png"
    image = Image.new("RGB", (10, 8), (0, 0, 0))
    image.putpixel((3, 2), (255, 0, 0))
    image.save(path)
    with Image.open(io.BytesIO(crop_png(path, 3, 2, 4, 5))) as cropped:
        assert cropped.size == (4, 5)
        assert cropped.getpixel((0, 0))[:3] == (255, 0, 0)


@pytest.mark.parametrize("box", [(0, 0, 11, 1), (-1, 0, 2, 2), (0, 0, 0, 2), (9, 7, 2, 2)])
def test_crop_rejects_boxes_outside_the_image(tmp_path, box):
    path = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(path)
    with pytest.raises(CaptureError) as err:
        crop_png(path, *box)
    assert err.value.code == "INVALID_ARGUMENT"


def test_crop_rejects_other_formats(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(path, format="JPEG")
    with pytest.raises(CaptureError) as err:
        crop_png(path, 0, 0, 2, 2)
    assert err.value.code == "INVALID_ARGUMENT"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_images.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.images'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/images.py -->
```python
"""PNG checks and crops."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image

from .errors import INVALID_ARGUMENT, CaptureError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int] | None:
    """Width and height from the IHDR chunk, or None when the bytes are not a PNG."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return (width, height) if width > 0 and height > 0 else None


def crop_png(path: Path, x: int, y: int, width: int, height: int) -> bytes:
    with Image.open(path) as image:
        if image.format != "PNG":
            raise CaptureError(INVALID_ARGUMENT, "the image is not a PNG", {"path": path.name})
        image_width, image_height = image.size
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > image_width
            or y + height > image_height
        ):
            raise CaptureError(
                INVALID_ARGUMENT,
                "the crop box is outside the image",
                {"image": [image_width, image_height], "box": [x, y, width, height]},
            )
        buffer = io.BytesIO()
        image.crop((x, y, x + width, y + height)).save(buffer, format="PNG")
        return buffer.getvalue()
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_images.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(images): check PNG sizes and crop regions for agent checks"
```

### Task 8: 启停桌面版与驱动层

**Files:**
- Create: `src/tradingview_capture_mcp/desktop.py`、`src/tradingview_capture_mcp/driver.py`
- Test: `tests/test_desktop.py`、`tests/test_driver.py`

**Interfaces:**
- Consumes: `Config`、`cdp.http_json`、`cdp.select_chart_page`、`cdp.CdpSession`、`page.build`。
- Produces（desktop）：`DesktopSession(process, port, version, browser)`，属性 `pid`；`running_pids(process_name="TradingView") -> list[int]`；`listening_addresses(port) -> list[str]`；`parse_version(info) -> str`；`launch(config, *, startup_timeout=40.0, poll=0.5) -> DesktopSession`；`wait_for_chart_page(port, layout, *, timeout=60.0, poll=1.0) -> dict`；`stop_process(process, *, timeout=20.0)`。
- Produces（driver）：`Viewport(width, height, scale=1.0)`、`DesktopInfo(version, browser)`、`ChartDriver` 与 `DesktopControl` 两个 Protocol、`CdpDriver(session)`（`run(script, args=None, *, timeout=60.0)`、`set_viewport(viewport)`、`clear_viewport()`）、`RealDesktop(config, layout, *, page_timeout=60.0)`（`start() -> (DesktopInfo, ChartDriver)`、`stop()`）、`_wait_for_chart_api(driver, timeout)`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_desktop.py -->
```python
import socket
import stat
import subprocess
import sys

import pytest

from tradingview_capture_mcp import desktop
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError

FAKE_APP = """import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int([a for a in sys.argv[1:] if a.startswith("--remote-debugging-port=")][0].split("=", 1)[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        info = {"Browser": "Chrome/146.0.7680.216", "User-Agent": "Mozilla/5.0 Electron/41.7.1 TVDesktop/9.9.9"}
        body = json.dumps(info if self.path == "/json/version" else []).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def fake_app(tmp_path, monkeypatch):
    app = tmp_path / "TradingView.app"
    binary = app / "Contents" / "MacOS" / "TradingView"
    binary.parent.mkdir(parents=True)
    binary.write_text(f"#!{sys.executable}\n" + FAKE_APP, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [])
    return Config(app_path=app, debug_port=free_port(), output_root=tmp_path)


def test_launch_reports_the_version_and_stops_its_own_process(fake_app):
    session = desktop.launch(fake_app, startup_timeout=15)
    try:
        assert (session.version, session.browser) == ("9.9.9", "Chrome/146.0.7680.216")
        assert desktop.listening_addresses(fake_app.debug_port) == ["127.0.0.1"]
    finally:
        desktop.stop_process(session.process, timeout=5)
    assert session.process.poll() is not None


def test_refuses_when_tradingview_already_runs(fake_app, monkeypatch):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [4242])
    with pytest.raises(CaptureError) as err:
        desktop.launch(fake_app)
    assert err.value.code == "TV_ALREADY_RUNNING"


def test_refuses_when_the_port_is_taken(fake_app):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", fake_app.debug_port))
        busy.listen()
        with pytest.raises(CaptureError) as err:
            desktop.launch(fake_app)
    assert err.value.code == "PORT_IN_USE"


def test_refuses_a_port_open_beyond_loopback_and_stops_the_app(fake_app, monkeypatch):
    calls = []

    def addresses(port):
        calls.append(port)
        return [] if len(calls) == 1 else ["*"]

    started = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    monkeypatch.setattr(desktop, "listening_addresses", addresses)
    monkeypatch.setattr(desktop.subprocess, "Popen", popen)
    with pytest.raises(CaptureError) as err:
        desktop.launch(fake_app, startup_timeout=15)
    assert err.value.code == "CDP_NOT_LOCAL"
    assert started[0].poll() is not None


def test_missing_app(tmp_path):
    with pytest.raises(CaptureError) as err:
        desktop.launch(Config(app_path=tmp_path / "Nope.app", debug_port=free_port(), output_root=tmp_path))
    assert err.value.code == "TV_NOT_INSTALLED"


def test_parse_version():
    assert desktop.parse_version({"User-Agent": "Mozilla/5.0 TVDesktop/3.4.1"}) == "3.4.1"
    assert desktop.parse_version({}) == "unknown"


def test_listening_addresses_parses_lsof(monkeypatch):
    output = "p100\nf20\nn127.0.0.1:9333\np100\nf21\nn[::1]:9333\n"
    monkeypatch.setattr(
        desktop.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=output, stderr="")
    )
    assert desktop.listening_addresses(9333) == ["127.0.0.1", "[::1]"]


def test_wait_for_chart_page_retries_until_the_tab_appears(monkeypatch):
    answers = [
        [],
        [
            {
                "type": "page",
                "url": "https://www.tradingview.com/chart/AbCd1234/",
                "webSocketDebuggerUrl": "ws://x",
            }
        ],
    ]
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: answers.pop(0))
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: None)
    assert desktop.wait_for_chart_page(9333, "AbCd1234", timeout=5)["webSocketDebuggerUrl"] == "ws://x"
```

<!-- file: tests/test_driver.py -->
```python
import pytest

from tradingview_capture_mcp import driver as driver_module
from tradingview_capture_mcp.driver import CdpDriver, Viewport, _wait_for_chart_api
from tradingview_capture_mcp.errors import CaptureError


class FakeSession:
    def __init__(self, values=None):
        self.calls = []
        self.values = list(values or [])

    def evaluate(self, expression, *, timeout=60.0):
        self.calls.append(("evaluate", expression, timeout))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def call(self, method, params=None, *, timeout=60.0):
        self.calls.append(("call", method, params))
        return {}


def test_run_sends_the_built_page_script():
    session = FakeSession([{"api": "object"}])
    assert CdpDriver(session).run("alive", timeout=7) == {"api": "object"}
    assert "typeof window.TradingViewApi" in session.calls[0][1]
    assert session.calls[0][2] == 7


def test_viewport_override_and_reset():
    session = FakeSession()
    chart = CdpDriver(session)
    chart.set_viewport(Viewport(800, 600, 2.0))
    chart.clear_viewport()
    assert session.calls == [
        (
            "call",
            "Emulation.setDeviceMetricsOverride",
            {"width": 800, "height": 600, "deviceScaleFactor": 2.0, "mobile": False},
        ),
        ("call", "Emulation.clearDeviceMetricsOverride", None),
    ]


def test_wait_for_chart_api_retries_while_the_page_loads(monkeypatch):
    monkeypatch.setattr(driver_module.time, "sleep", lambda seconds: None)
    session = FakeSession(
        [
            CaptureError("CDP_ERROR", "not yet"),
            {"api": "undefined", "symbol": None},
            {"api": "object", "symbol": "BINANCE:BTCUSDT.P"},
        ]
    )
    _wait_for_chart_api(CdpDriver(session), timeout=30)
    assert len(session.calls) == 3


def test_wait_for_chart_api_gives_up():
    session = FakeSession([{"api": "undefined", "symbol": None}])
    with pytest.raises(CaptureError) as err:
        _wait_for_chart_api(CdpDriver(session), timeout=0)
    assert err.value.code == "TV_INTERNALS_CHANGED"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_desktop.py tests/test_driver.py -q`
Expected: FAIL，`cannot import name 'desktop'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/desktop.py -->
```python
"""Start, check and stop TradingView Desktop with a loopback-only DevTools port."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from . import cdp
from .config import Config
from .errors import (
    CDP_NOT_LOCAL,
    LAYOUT_NOT_FOUND,
    PORT_IN_USE,
    TV_ALREADY_RUNNING,
    TV_NOT_INSTALLED,
    TV_STARTUP_TIMEOUT,
    CaptureError,
)

LOCAL_ADDRESSES = {"127.0.0.1", "[::1]", "localhost"}
_TV_VERSION = re.compile(r"TVDesktop/(\S+)")


@dataclass
class DesktopSession:
    process: subprocess.Popen
    port: int
    version: str
    browser: str

    @property
    def pid(self) -> int:
        return self.process.pid


def running_pids(process_name: str = "TradingView") -> list[int]:
    result = subprocess.run(
        ["/usr/bin/pgrep", "-x", process_name], capture_output=True, text=True, check=False
    )
    return [int(pid) for pid in result.stdout.split()]


def listening_addresses(port: int) -> list[str]:
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "n"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line[1:].rsplit(":", 1)[0] for line in result.stdout.splitlines() if line.startswith("n")]


def parse_version(info: dict[str, Any]) -> str:
    match = _TV_VERSION.search(str(info.get("User-Agent", "")))
    return match.group(1) if match else "unknown"


def launch(config: Config, *, startup_timeout: float = 40.0, poll: float = 0.5) -> DesktopSession:
    """Start TradingView Desktop with the DevTools port; refuse to touch a copy the user already runs."""
    if not config.app_binary.is_file():
        raise CaptureError(
            TV_NOT_INSTALLED, "TradingView Desktop was not found", {"app_path": str(config.app_path)}
        )
    if running_pids():
        raise CaptureError(
            TV_ALREADY_RUNNING, "TradingView Desktop is already running; quit it and retry", {}
        )
    if listening_addresses(config.debug_port):
        raise CaptureError(PORT_IN_USE, "the debug port is already in use", {"port": config.debug_port})
    process = subprocess.Popen(
        [str(config.app_binary), f"--remote-debugging-port={config.debug_port}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        info = _wait_for_devtools(process, config.debug_port, startup_timeout, poll)
        addresses = listening_addresses(config.debug_port)
        if not addresses or any(address not in LOCAL_ADDRESSES for address in addresses):
            raise CaptureError(
                CDP_NOT_LOCAL, "the debug port must listen on loopback only", {"addresses": addresses}
            )
        return DesktopSession(
            process=process,
            port=config.debug_port,
            version=parse_version(info),
            browser=str(info.get("Browser", "")),
        )
    except BaseException:
        stop_process(process)
        raise


def _wait_for_devtools(process: subprocess.Popen, port: int, timeout: float, poll: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CaptureError(
                TV_STARTUP_TIMEOUT,
                "TradingView Desktop exited during startup",
                {"returncode": process.returncode},
            )
        try:
            return cdp.http_json(port, "/json/version", timeout=2.0)
        except (OSError, ValueError):
            time.sleep(poll)
    raise CaptureError(TV_STARTUP_TIMEOUT, f"DevTools did not answer within {timeout:g}s", {"port": port})


def wait_for_chart_page(
    port: int, layout: str, *, timeout: float = 60.0, poll: float = 1.0
) -> dict[str, Any]:
    """Wait until the restored tab for `layout` is listed, then return its DevTools target."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return cdp.select_chart_page(cdp.http_json(port, "/json/list"), layout)
        except CaptureError as exc:
            if exc.code != LAYOUT_NOT_FOUND or time.monotonic() >= deadline:
                raise
        except (OSError, ValueError) as exc:
            if time.monotonic() >= deadline:
                raise CaptureError(
                    LAYOUT_NOT_FOUND, "the DevTools target list never loaded", {"layout": layout}
                ) from exc
        time.sleep(poll)


def stop_process(process: subprocess.Popen, *, timeout: float = 20.0) -> None:
    """Stop only the process this tool started: SIGTERM first, SIGKILL after the timeout."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
```

<!-- file: src/tradingview_capture_mcp/driver.py -->
```python
"""Seams between the capture flow and TradingView Desktop, with the real implementations."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Any, Protocol

from . import cdp, desktop, page
from .config import Config
from .errors import CDP_ERROR, TV_INTERNALS_CHANGED, CaptureError


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    scale: float = 1.0


@dataclass(frozen=True)
class DesktopInfo:
    version: str
    browser: str


class ChartDriver(Protocol):
    def run(self, script: str, args: dict[str, Any] | None = None, *, timeout: float = 60.0) -> Any: ...

    def set_viewport(self, viewport: Viewport) -> None: ...

    def clear_viewport(self) -> None: ...


class DesktopControl(Protocol):
    def start(self) -> tuple[DesktopInfo, ChartDriver]: ...

    def stop(self) -> None: ...


class CdpDriver:
    """Runs the fixed page scripts in one chart tab."""

    def __init__(self, session: cdp.CdpSession) -> None:
        self._session = session

    def run(self, script: str, args: dict[str, Any] | None = None, *, timeout: float = 60.0) -> Any:
        return self._session.evaluate(page.build(script, args), timeout=timeout)

    def set_viewport(self, viewport: Viewport) -> None:
        self._session.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": viewport.width,
                "height": viewport.height,
                "deviceScaleFactor": viewport.scale,
                "mobile": False,
            },
        )

    def clear_viewport(self) -> None:
        self._session.call("Emulation.clearDeviceMetricsOverride")


class RealDesktop:
    """Starts the installed TradingView Desktop and connects to one layout's tab."""

    def __init__(self, config: Config, layout: str, *, page_timeout: float = 60.0) -> None:
        self._config = config
        self._layout = layout
        self._page_timeout = page_timeout
        self._session: desktop.DesktopSession | None = None
        self._cdp: cdp.CdpSession | None = None

    def start(self) -> tuple[DesktopInfo, ChartDriver]:
        self._session = desktop.launch(self._config)
        target = desktop.wait_for_chart_page(
            self._config.debug_port, self._layout, timeout=self._page_timeout
        )
        self._cdp = cdp.CdpSession(target["webSocketDebuggerUrl"])
        driver = CdpDriver(self._cdp)
        _wait_for_chart_api(driver, self._page_timeout)
        return DesktopInfo(version=self._session.version, browser=self._session.browser), driver

    def stop(self) -> None:
        if self._cdp is not None:
            with contextlib.suppress(Exception):
                self._cdp.close()
            self._cdp = None
        if self._session is not None:
            desktop.stop_process(self._session.process)
            self._session = None


def _wait_for_chart_api(driver: ChartDriver, timeout: float) -> None:
    """The tab exists before TradingView's chart API does; poll until a symbol is loaded."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            state: Any = driver.run("alive", timeout=10.0)
            if isinstance(state, dict) and state.get("api") == "object" and state.get("symbol"):
                return
        except CaptureError as exc:
            if exc.code != CDP_ERROR:
                raise
            state = {"error": exc.message}
        if time.monotonic() >= deadline:
            raise CaptureError(
                TV_INTERNALS_CHANGED, "the chart API did not become available", {"state": state}
            )
        time.sleep(1.0)
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_desktop.py tests/test_driver.py -q`
Expected: PASS（假桌面版是一个只回答 `/json/version` 的 Python 脚本）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(desktop): start TradingView Desktop on a loopback port and stop only that process"
```

### Task 9: 内部结构自检与批次流程

**Files:**
- Create: `src/tradingview_capture_mcp/diagnostics.py`、`src/tradingview_capture_mcp/capture.py`、`tests/fakes.py`
- Test: `tests/test_diagnostics.py`、`tests/test_capture.py`

**Interfaces:**
- Consumes: Task 3 的 store 函数、Task 6 的 `ReadySnapshot` / `wait_until_ready`、Task 7 的 `png_size`、Task 8 的 `ChartDriver` / `DesktopControl` / `DesktopInfo` / `Viewport` / `RealDesktop`。
- Produces（diagnostics）：`problems(report) -> list[str]`；`run_doctor(config, layout) -> {"desktop", "problems", "report"}`。
- Produces（capture）：`CaptureRequest(layout, symbols, timeframe, output_dir, required_studies=(), viewport=None, ready_timeout_sec=60.0, retry_failed=False)`，方法 `to_dict()`、类方法 `from_dict(raw)`；`validate_request(request)`；`previous_desktop_version(output_root, exclude) -> str | None`；`run_capture(request, config, *, job_id, desktop, pid=0, sleep=time.sleep, clock=time.monotonic) -> dict`，返回 `{jobId, outputDir, state, totals, failures, desktopVersionChanged, error}`；`capture_symbol(...) -> dict`；常量 `CAPTURE_METHOD = "CDP_DESKTOP"`。

- [ ] **Step 1: 写测试替身与 diagnostics 的失败测试**

<!-- file: tests/fakes.py -->
```python
"""In-memory stand-ins for TradingView Desktop used by the capture tests."""

import base64

from helpers import png_bytes

from tradingview_capture_mcp.driver import DesktopInfo

OK_DIAGNOSE = {
    "tradingViewApi": "object",
    "checks": [
        {"name": "activeChart", "ok": True, "detail": []},
        {"name": "takeClientScreenshot", "ok": True, "detail": "function"},
        {"name": "chartWidget", "ok": True, "detail": 2},
        {
            "name": "mainSeriesBars",
            "ok": True,
            "detail": {"size": 2, "firstIndex": "function", "lastIndex": "function", "valueAt": "function"},
        },
        {"name": "dataSources", "ok": True, "detail": 4},
        {"name": "panes", "ok": True, "detail": 2},
        {
            "name": "studies",
            "ok": True,
            "detail": [
                {
                    "hasMetaInfo": True,
                    "plots": 2,
                    "zorder": "function",
                    "status": "function",
                    "data": {"size": 2, "valueAt": "function"},
                    "collections": ["dwgtablecells", "dwglabels", "dwglines", "dwgboxes"],
                }
            ],
        },
        {"name": "shapes", "ok": True, "detail": []},
    ],
}
CSV = "time,open,high,low,close,Quarter\n1000,1,2,0.5,1.5,10.5\n2000,1.5,2.5,1,2,11.25"


class FakeChart:
    """Plays the page scripts. After a switch the studies keep the old output for `settle_polls` reads."""

    def __init__(
        self,
        *,
        start_symbol="SSE_DLY:000001",
        settle_polls=2,
        studies=("Alpha", "Beta"),
        unknown=(),
        never_ready=(),
        missing_study=None,
        static_study=None,
        diagnose=None,
    ):
        self.symbol = start_symbol
        self.previous = start_symbol
        self.resolution = "1D"
        self.settle_polls = settle_polls
        self.polls = 10**6
        self.studies = studies
        self.unknown = set(unknown)
        self.never_ready = set(never_ready)
        self.missing_study = missing_study
        self.static_study = static_study
        self.diagnose_report = diagnose or OK_DIAGNOSE
        self.viewport = None
        self.calls = []

    def run(self, script, args=None, *, timeout=60.0):
        self.calls.append((script, dict(args or {})))
        return getattr(self, "_" + script)(args or {})

    def set_viewport(self, viewport):
        self.viewport = viewport

    def clear_viewport(self):
        self.viewport = None

    def _diagnose(self, args):
        return self.diagnose_report

    def _ready(self, args):
        self.polls += 1
        settled = self.polls > self.settle_polls and self.symbol not in self.never_ready
        source = self.symbol if settled else self.previous
        return {
            "symbol": self.symbol,
            "resolution": self.resolution,
            "lastBarTime": 2000,
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "status": 2 if settled else 1,
                    "lastTime": 2000,
                    "digest": f"{name}:static" if name == self.static_study else f"{name}:{source}",
                }
                for i, name in enumerate(self.studies)
            ],
        }

    def _switch(self, args):
        before = {"symbol": self.symbol, "resolution": self.resolution}
        if args["symbol"] not in self.unknown:
            self.previous, self.symbol, self.polls = self.symbol, args["symbol"], 0
        self.resolution = args.get("timeframe") or self.resolution
        return {
            "before": before,
            "after": {"symbol": self.symbol, "resolution": self.resolution},
            "timedOut": False,
        }

    def _extract(self, args):
        names = [name for name in self.studies if (self.symbol, name) != self.missing_study]
        return {
            "identity": {"symbol": self.symbol, "resolution": self.resolution, "lastBar": {"time": 2000}},
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "tables": [{"id": "0", "rows": [[name, self.symbol]]}],
                    "labels": [],
                    "lines": [],
                    "boxes": [],
                    "lastValues": [["Quarter", 11.25]],
                }
                for i, name in enumerate(names)
            ],
            "drawings": [],
            "series": {"columns": 6, "rows": 2, "csv": CSV},
        }

    def _screenshot(self, args):
        return {"width": 40, "height": 30, "base64": base64.b64encode(png_bytes(40, 30)).decode()}


class FakeDesktop:
    def __init__(self, chart, *, version="3.4.1", fail=None):
        self.chart = chart
        self.version = version
        self.fail = fail
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        if self.fail:
            raise self.fail
        return DesktopInfo(version=self.version, browser="Chrome/146.0.7680.216"), self.chart

    def stop(self):
        self.stopped += 1


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
```

<!-- file: tests/test_diagnostics.py -->
```python
import copy

import pytest
from fakes import OK_DIAGNOSE

from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.diagnostics import problems, run_doctor
from tradingview_capture_mcp.errors import CaptureError


def test_a_healthy_report_has_no_problems():
    assert problems(OK_DIAGNOSE) == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (
            lambda r: r["checks"].__setitem__(0, {"name": "activeChart", "ok": False, "error": "gone"}),
            "activeChart",
        ),
        (lambda r: r["checks"][0].__setitem__("detail", ["setSymbol"]), "activeChart.methods"),
        (lambda r: r["checks"][1].__setitem__("detail", "undefined"), "takeClientScreenshot.function"),
        (lambda r: r["checks"][3]["detail"].__setitem__("valueAt", "undefined"), "mainSeriesBars.methods"),
        (lambda r: r["checks"][6]["detail"][0].__setitem__("collections", ["dwglabels"]), "studies.shape"),
        (lambda r: r["checks"].pop(), "shapes"),
    ],
)
def test_each_missing_piece_is_named(mutate, expected):
    report = copy.deepcopy(OK_DIAGNOSE)
    mutate(report)
    assert expected in problems(report)


def test_doctor_checks_the_layout_before_starting_anything(tmp_path):
    config = Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=tmp_path)
    with pytest.raises(CaptureError) as err:
        run_doctor(config, "../bad")
    assert err.value.code == "INVALID_ARGUMENT"
```

- [ ] **Step 2: 实现 diagnostics 并确认通过**

<!-- file: src/tradingview_capture_mcp/diagnostics.py -->
```python
"""Checks of the TradingView internals a capture relies on, and the doctor command."""

from __future__ import annotations

from typing import Any

from .config import Config
from .driver import RealDesktop
from .store import BatchLock
from .validation import check_layout

REQUIRED_CHECKS = (
    "activeChart",
    "takeClientScreenshot",
    "chartWidget",
    "mainSeriesBars",
    "dataSources",
    "panes",
    "studies",
    "shapes",
)
GRAPHICS_COLLECTIONS = 4


def problems(report: dict[str, Any]) -> list[str]:
    """Names of the checks that failed; an empty list means a capture can run."""
    checks = {c.get("name"): c for c in report.get("checks", []) if isinstance(c, dict)}
    found = [name for name in REQUIRED_CHECKS if not (checks.get(name) or {}).get("ok")]
    if "activeChart" not in found and checks["activeChart"].get("detail"):
        found.append("activeChart.methods")
    if "takeClientScreenshot" not in found and checks["takeClientScreenshot"].get("detail") != "function":
        found.append("takeClientScreenshot.function")
    if "mainSeriesBars" not in found:
        bars = checks["mainSeriesBars"].get("detail") or {}
        if not all(bars.get(key) == "function" for key in ("firstIndex", "lastIndex", "valueAt")):
            found.append("mainSeriesBars.methods")
    if "studies" not in found:
        for study in checks["studies"].get("detail") or []:
            data = study.get("data") or {}
            if not (
                study.get("hasMetaInfo")
                and study.get("zorder") == "function"
                and data.get("valueAt") == "function"
                and len(study.get("collections") or []) >= GRAPHICS_COLLECTIONS
            ):
                found.append("studies.shape")
                break
    return found


def run_doctor(config: Config, layout: str) -> dict[str, Any]:
    check_layout(layout)
    desktop = RealDesktop(config, layout)
    with BatchLock(config.output_root):
        try:
            info, driver = desktop.start()
            report = driver.run("diagnose")
        finally:
            desktop.stop()
    return {
        "desktop": {"version": info.version, "browser": info.browser},
        "problems": problems(report),
        "report": report,
    }
```

Run: `uv run pytest tests/test_diagnostics.py -q`
Expected: PASS

- [ ] **Step 3: 写批次流程的失败测试**

<!-- file: tests/test_capture.py -->
```python
import dataclasses
import json
import stat

import pytest
from fakes import OK_DIAGNOSE, FakeChart, FakeClock, FakeDesktop

from tradingview_capture_mcp.capture import CaptureRequest, run_capture, validate_request
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.driver import Viewport
from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import BatchLock, read_json, safe_name, sha256_bytes, write_json_new

SYMBOLS = ("BINANCE:AAAUSDT.P", "BINANCE:BBBUSDT.P", "NYMEX:CL1!")


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())


def make_request(config, **changes):
    base = CaptureRequest(
        layout="Layout01",
        symbols=SYMBOLS,
        timeframe="1D",
        output_dir=str(config.output_root / "batch"),
        required_studies=("Alpha",),
        viewport=Viewport(800, 600, 2.0),
    )
    return dataclasses.replace(base, **changes)


def capture(config, request, chart=None, **desktop_options):
    chart = chart or FakeChart()
    desktop = FakeDesktop(chart, **desktop_options)
    clock = FakeClock()
    summary = run_capture(
        request, config, job_id="a" * 32, desktop=desktop, pid=4242, sleep=clock.sleep, clock=clock
    )
    return summary, chart, desktop


def test_captures_every_symbol_and_restores_the_chart(config):
    summary, chart, desktop = capture(config, make_request(config))
    out = config.output_root / "batch"
    assert summary["state"] == "finished"
    assert summary["totals"] == {"requested": 3, "succeeded": 3, "failed": 0, "pending": 0}
    assert (desktop.started, desktop.stopped) == (1, 1)
    assert (chart.symbol, chart.viewport) == ("SSE_DLY:000001", None)
    for code in SYMBOLS:
        folder = out / "raw" / safe_name(code)
        for name in ("image.png", "chart.csv", "data.json", "capture.json"):
            assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600
        record = read_json(folder / "capture.json")
        assert (record["symbol"], record["captureMethod"], record["desktop"]["version"]) == (
            code,
            "CDP_DESKTOP",
            "3.4.1",
        )
        assert record["files"]["chart.csv"]["sha256"] == sha256_bytes((folder / "chart.csv").read_bytes())
        assert record["files"]["image.png"]["width"] == 40
    data = read_json(out / "raw" / safe_name(SYMBOLS[0]) / "data.json")
    assert data["readiness"]["polls"] >= 2
    assert data["readiness"]["unchangedAfterSwitch"] == []
    manifest = read_json(out / "capture-manifest.json")
    assert (manifest["state"], manifest["desktopVersionChanged"], manifest["attempts"]) == (
        "finished",
        False,
        1,
    )
    job = read_json(out / "job.json")
    assert (job["state"], job["succeeded"], job["pid"]) == ("finished", 3, 4242)
    assert read_json(out / "batch.json")["request"]["symbols"] == list(SYMBOLS)
    assert [p.name for p in (out / "raw").iterdir() if p.name.startswith(".")] == []


def test_stops_before_any_symbol_when_the_internals_changed(config):
    broken = json.loads(json.dumps(OK_DIAGNOSE))
    broken["checks"][0] = {"name": "activeChart", "ok": False, "error": "gone"}
    summary, _, desktop = capture(config, make_request(config), FakeChart(diagnose=broken))
    out = config.output_root / "batch"
    assert (summary["state"], summary["error"]["code"]) == ("stopped", "TV_INTERNALS_CHANGED")
    assert summary["error"]["detail"]["failedChecks"] == ["activeChart"]
    assert summary["totals"]["pending"] == 3
    assert list((out / "raw").iterdir()) == []
    assert desktop.stopped == 1
    assert read_json(out / "job.json")["state"] == "failed"


def test_the_self_check_stops_the_batch_when_the_first_symbol_lacks_a_required_study(config):
    chart = FakeChart(missing_study=(SYMBOLS[0], "Alpha"))
    summary, _, _ = capture(config, make_request(config), chart)
    assert summary["state"] == "stopped"
    assert summary["error"]["detail"]["failedChecks"] == ["requiredStudies"]
    assert chart.symbol == "SSE_DLY:000001"


def test_later_failures_are_recorded_and_the_batch_goes_on(config):
    chart = FakeChart(missing_study=(SYMBOLS[1], "Alpha"), never_ready={SYMBOLS[2]})
    summary, _, _ = capture(config, make_request(config), chart)
    assert summary["state"] == "finished"
    assert summary["totals"] == {"requested": 3, "succeeded": 1, "failed": 2, "pending": 0}
    assert [(f["symbol"], f["code"]) for f in summary["failures"]] == [
        (SYMBOLS[1], "STUDY_MISSING"),
        (SYMBOLS[2], "NOT_READY_TIMEOUT"),
    ]
    assert not (config.output_root / "batch" / "raw" / safe_name(SYMBOLS[1])).exists()


def test_an_unknown_symbol_fails_alone(config):
    summary, _, _ = capture(config, make_request(config), FakeChart(unknown={SYMBOLS[1]}))
    assert [(f["symbol"], f["code"]) for f in summary["failures"]] == [(SYMBOLS[1], "SYMBOL_NOT_FOUND")]
    assert summary["totals"]["succeeded"] == 2


def test_output_that_looks_unchanged_is_accepted_after_the_grace_period(config):
    summary, _, _ = capture(config, make_request(config, symbols=SYMBOLS[:1]), FakeChart(static_study="Beta"))
    data = read_json(config.output_root / "batch" / "raw" / safe_name(SYMBOLS[0]) / "data.json")
    assert summary["state"] == "finished"
    assert data["readiness"]["unchangedAfterSwitch"] == ["Beta"]
    assert data["readiness"]["waitedSec"] >= 10


def test_retry_runs_only_failed_symbols_and_keeps_earlier_files(config):
    chart = FakeChart(unknown={SYMBOLS[1]})
    capture(config, make_request(config), chart)
    out = config.output_root / "batch"
    first = (out / "raw" / safe_name(SYMBOLS[0]) / "capture.json").read_bytes()
    chart.unknown.clear()
    chart.calls.clear()
    summary, _, _ = capture(config, make_request(config, retry_failed=True), chart)
    assert summary["totals"]["succeeded"] == 3
    assert read_json(out / "capture-manifest.json")["attempts"] == 2
    assert read_json(out / "attempts" / "2" / "attempt.json")["symbols"] == [SYMBOLS[1]]
    assert (out / "raw" / safe_name(SYMBOLS[0]) / "capture.json").read_bytes() == first
    assert [args["symbol"] for script, args in chart.calls if script == "switch"] == [
        SYMBOLS[1],
        "SSE_DLY:000001",
    ]


def test_retry_with_nothing_left_to_do(config):
    capture(config, make_request(config))
    with pytest.raises(CaptureError) as err:
        capture(config, make_request(config, retry_failed=True))
    assert err.value.code == "NOT_FOUND"


def test_refuses_an_existing_output_dir_and_a_held_lock(config):
    (config.output_root / "batch").mkdir()
    with pytest.raises(CaptureError) as err:
        capture(config, make_request(config))
    assert err.value.code == "OUTPUT_EXISTS"
    with BatchLock(config.output_root), pytest.raises(CaptureError) as err:
        capture(config, make_request(config, output_dir=str(config.output_root / "other")))
    assert err.value.code == "BATCH_LOCKED"


def test_a_failed_start_still_leaves_a_manifest(config):
    summary, _, desktop = capture(
        config, make_request(config), fail=CaptureError("TV_ALREADY_RUNNING", "quit it first")
    )
    out = config.output_root / "batch"
    assert (summary["state"], summary["error"]["code"]) == ("stopped", "TV_ALREADY_RUNNING")
    assert read_json(out / "capture-manifest.json")["desktop"]["version"] is None
    assert read_json(out / "job.json")["state"] == "failed"
    assert desktop.stopped == 1


def test_a_desktop_version_change_is_flagged(config):
    for name, manifest in {
        "old": {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "finished",
            "totals": {"succeeded": 1},
            "finishedAt": {"unix": 5},
            "desktop": {"version": "3.4.0"},
        },
        "stopped": {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "stopped",
            "totals": {"succeeded": 0},
            "finishedAt": {"unix": 9},
            "desktop": {"version": "1.0.0"},
        },
        "foreign": {"schemaVersion": 1, "records": []},
    }.items():
        (config.output_root / name).mkdir()
        write_json_new(config.output_root / name / "capture-manifest.json", manifest)
    summary, _, _ = capture(config, make_request(config))
    manifest = read_json(config.output_root / "batch" / "capture-manifest.json")
    assert summary["desktopVersionChanged"] is True
    assert manifest["desktop"]["previousVersion"] == "3.4.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"layout": "bad/layout"},
        {"symbols": ()},
        {"symbols": (SYMBOLS[0], SYMBOLS[0])},
        {"symbols": ("btcusdt",)},
        {"symbols": ("A:B!", "A:B&")},
        {"timeframe": "4H"},
        {"ready_timeout_sec": 1.0},
        {"viewport": Viewport(10, 10, 1.0)},
        {"required_studies": ("",)},
    ],
)
def test_invalid_requests_are_rejected(config, changes):
    with pytest.raises(CaptureError) as err:
        validate_request(make_request(config, **changes))
    assert err.value.code == "INVALID_ARGUMENT"


def test_requests_round_trip_through_json(config):
    request = make_request(config)
    assert CaptureRequest.from_dict(json.loads(json.dumps(request.to_dict()))) == request
    with pytest.raises(CaptureError):
        CaptureRequest.from_dict({"layout": "Layout01"})
```

- [ ] **Step 4: 确认失败**

Run: `uv run pytest tests/test_capture.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.capture'`

- [ ] **Step 5: 实现批次流程**

<!-- file: src/tradingview_capture_mcp/capture.py -->
```python
"""Run one capture batch: switch, wait, extract, screenshot and write every symbol."""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import TOOL_NAME, __version__
from .config import Config
from .diagnostics import problems
from .driver import ChartDriver, DesktopControl, DesktopInfo, Viewport
from .errors import (
    CDP_ERROR,
    INTERNAL_ERROR,
    INVALID_ARGUMENT,
    NOT_FOUND,
    OUTPUT_EXISTS,
    STUDY_MISSING,
    SYMBOL_NOT_FOUND,
    TV_INTERNALS_CHANGED,
    CaptureError,
)
from .images import png_size
from .readiness import ReadySnapshot, wait_until_ready
from .store import (
    BatchLock,
    dumps_json,
    ensure_dir,
    make_dir_new,
    read_json,
    replace_json,
    resolve_inside_root,
    safe_name,
    sha256_bytes,
    stamp,
    write_json_new,
    write_new,
)
from .validation import SYMBOL_RE, TIMEFRAME_RE, check_layout

CAPTURE_METHOD = "CDP_DESKTOP"
PNG_SOURCE = "TradingViewApi.takeClientScreenshot"
CSV_SOURCE = "generated from the chart series in the column order of TradingView's own export"
MAX_SYMBOLS = 500


@dataclass(frozen=True)
class CaptureRequest:
    layout: str
    symbols: tuple[str, ...]
    timeframe: str
    output_dir: str
    required_studies: tuple[str, ...] = ()
    viewport: Viewport | None = None
    ready_timeout_sec: float = 60.0
    retry_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout": self.layout,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "output_dir": self.output_dir,
            "required_studies": list(self.required_studies),
            "viewport": asdict(self.viewport) if self.viewport else None,
            "ready_timeout_sec": self.ready_timeout_sec,
            "retry_failed": self.retry_failed,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CaptureRequest:
        try:
            viewport = raw.get("viewport")
            return cls(
                layout=str(raw["layout"]),
                symbols=tuple(str(s) for s in raw["symbols"]),
                timeframe=str(raw["timeframe"]),
                output_dir=str(raw["output_dir"]),
                required_studies=tuple(str(s) for s in raw.get("required_studies") or ()),
                viewport=Viewport(
                    int(viewport["width"]), int(viewport["height"]), float(viewport.get("scale", 1.0))
                )
                if viewport
                else None,
                ready_timeout_sec=float(raw.get("ready_timeout_sec", 60.0)),
                retry_failed=bool(raw.get("retry_failed", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptureError(INVALID_ARGUMENT, f"invalid capture request: {exc}", {}) from exc


def validate_request(request: CaptureRequest) -> None:
    def bad(message: str, **detail: Any) -> None:
        raise CaptureError(INVALID_ARGUMENT, message, detail)

    check_layout(request.layout)
    if not request.symbols:
        bad("symbols must not be empty")
    if len(request.symbols) > MAX_SYMBOLS:
        bad(f"at most {MAX_SYMBOLS} symbols per batch")
    if len(set(request.symbols)) != len(request.symbols):
        bad("symbols must be unique")
    for code in request.symbols:
        if not SYMBOL_RE.fullmatch(code):
            bad("a symbol must be a TradingView code such as EXCHANGE:TICKER", symbol=code)
    if len({safe_name(code) for code in request.symbols}) != len(request.symbols):
        bad("two symbols map to the same folder name")
    if not TIMEFRAME_RE.fullmatch(request.timeframe):
        bad("timeframe must be a TradingView resolution such as 1D, 240 or 1W", timeframe=request.timeframe)
    if not 5 <= request.ready_timeout_sec <= 600:
        bad("ready_timeout_sec must be between 5 and 600")
    if len(request.required_studies) > 32 or any(not s or len(s) > 128 for s in request.required_studies):
        bad("required_studies must be up to 32 non-empty names")
    viewport = request.viewport
    if viewport is not None and not (
        200 <= viewport.width <= 8000 and 200 <= viewport.height <= 8000 and 0.5 <= viewport.scale <= 4
    ):
        bad("viewport must be 200-8000 pixels per side with a scale of 0.5-4")


class Progress:
    """The job.json file that status calls read while a batch runs."""

    def __init__(self, path: Path, *, job_id: str, pid: int, output_dir: Path, total: int) -> None:
        self._path = path
        now = stamp()
        self.state: dict[str, Any] = {
            "schemaVersion": 1,
            "jobId": job_id,
            "pid": pid,
            "state": "running",
            "outputDir": str(output_dir),
            "startedAt": now,
            "updatedAt": now,
            "total": total,
            "done": 0,
            "succeeded": 0,
            "failed": 0,
            "current": None,
            "failures": [],
            "desktopVersionChanged": None,
            "error": None,
        }
        replace_json(self._path, self.state)

    def update(self, **fields: Any) -> None:
        self.state.update(fields)
        self.state["updatedAt"] = stamp()
        replace_json(self._path, self.state)

    def record(self, result: dict[str, Any]) -> None:
        self.state["done"] += 1
        if result["status"] == "ok":
            self.state["succeeded"] += 1
        else:
            self.state["failed"] += 1
            self.state["failures"].append({"symbol": result["symbol"], **result["error"]})
        self.update(current=None)


def previous_desktop_version(output_root: Path, exclude: Path) -> str | None:
    """Desktop version of the newest finished batch from this tool under the output root."""
    best: tuple[float, str | None] | None = None
    for path in [
        *output_root.glob("*/capture-manifest.json"),
        *output_root.glob("*/*/capture-manifest.json"),
    ]:
        if path.parent == exclude:
            continue
        try:
            manifest = read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, dict) or (manifest.get("tool") or {}).get("name") != TOOL_NAME:
            continue
        if manifest.get("state") != "finished" or (manifest.get("totals") or {}).get("succeeded", 0) <= 0:
            continue
        finished = float((manifest.get("finishedAt") or {}).get("unix") or 0)
        if best is None or finished > best[0]:
            best = (finished, (manifest.get("desktop") or {}).get("version"))
    return best[1] if best else None


def run_capture(
    request: CaptureRequest,
    config: Config,
    *,
    job_id: str,
    desktop: DesktopControl,
    pid: int = 0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    validate_request(request)
    out = resolve_inside_root(config.output_root, request.output_dir)
    with BatchLock(config.output_root):
        if request.retry_failed:
            manifest_path = out / "capture-manifest.json"
            if not manifest_path.is_file():
                raise CaptureError(NOT_FOUND, "this batch has no manifest to retry", {"output_dir": str(out)})
            previous = read_json(manifest_path)
            results: dict[str, dict[str, Any]] = {s["symbol"]: s for s in previous.get("symbols", [])}
            todo = [code for code in request.symbols if results.get(code, {}).get("status") != "ok"]
            if not todo:
                raise CaptureError(
                    NOT_FOUND, "this batch has no failed or pending symbols", {"output_dir": str(out)}
                )
            attempt = int(previous.get("attempts", 1)) + 1
            started_at = previous.get("startedAt") or stamp()
        else:
            make_dir_new(out)
            ensure_dir(out / "raw")
            ensure_dir(out / "attempts")
            started_at = stamp()
            write_json_new(
                out / "batch.json",
                {
                    "schemaVersion": 1,
                    "tool": {"name": TOOL_NAME, "version": __version__},
                    "jobId": job_id,
                    "startedAt": started_at,
                    "request": request.to_dict(),
                    "symbolsSha256": sha256_bytes("\n".join(request.symbols).encode("utf-8")),
                },
            )
            results, todo, attempt = {}, list(request.symbols), 1
        attempt_dir = out / "attempts" / str(attempt)
        make_dir_new(attempt_dir)
        progress = Progress(out / "job.json", job_id=job_id, pid=pid, output_dir=out, total=len(todo))
        info: DesktopInfo | None = None
        previous_version: str | None = None
        changed: bool | None = None
        stopped: CaptureError | None = None
        try:
            info, driver = desktop.start()
            previous_version = previous_desktop_version(config.output_root, exclude=out)
            changed = previous_version is not None and previous_version != info.version
            progress.update(desktopVersionChanged=changed)
            issues = problems(driver.run("diagnose"))
            if issues:
                raise CaptureError(
                    TV_INTERNALS_CHANGED, "TradingView's internals changed", {"failedChecks": issues}
                )
            original = driver.run("ready")
            try:
                if request.viewport is not None:
                    driver.set_viewport(request.viewport)
                    sleep(1.0)
                for index, code in enumerate(todo):
                    progress.update(current=code)
                    try:
                        result = capture_symbol(
                            driver,
                            request,
                            out,
                            code,
                            attempt=attempt,
                            attempt_dir=attempt_dir,
                            self_check=index == 0,
                            info=info,
                            sleep=sleep,
                            clock=clock,
                        )
                    except CaptureError as exc:
                        if index == 0 and exc.code == TV_INTERNALS_CHANGED:
                            raise
                        result = {
                            "symbol": code,
                            "safeName": safe_name(code),
                            "status": "failed",
                            "attempt": attempt,
                            "error": exc.to_dict(),
                        }
                    results[code] = result
                    progress.record(result)
            finally:
                _restore(driver, original, request)
        except CaptureError as exc:
            stopped = exc
        except Exception as exc:  # a bug must still leave a manifest and a final job state behind
            stopped = CaptureError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}", {})
        finally:
            desktop.stop()
        symbols = [
            results.get(code) or {"symbol": code, "safeName": safe_name(code), "status": "pending"}
            for code in request.symbols
        ]
        totals = {
            "requested": len(symbols),
            "succeeded": sum(1 for s in symbols if s["status"] == "ok"),
            "failed": sum(1 for s in symbols if s["status"] == "failed"),
            "pending": sum(1 for s in symbols if s["status"] == "pending"),
        }
        state = "stopped" if stopped else "finished"
        error = stopped.to_dict() if stopped else None
        manifest = {
            "schemaVersion": 1,
            "tool": {"name": TOOL_NAME, "version": __version__},
            "jobId": job_id,
            "state": state,
            "error": error,
            "startedAt": started_at,
            "finishedAt": stamp(),
            "attempts": attempt,
            "layout": request.layout,
            "timeframe": request.timeframe,
            "viewport": asdict(request.viewport) if request.viewport else None,
            "desktop": {
                "version": info.version if info else None,
                "browser": info.browser if info else None,
                "previousVersion": previous_version,
            },
            "desktopVersionChanged": changed,
            "totals": totals,
            "symbols": symbols,
        }
        write_json_new(
            attempt_dir / "attempt.json",
            {
                "attempt": attempt,
                "jobId": job_id,
                "symbols": todo,
                "results": [results[c] for c in todo if c in results],
                "error": error,
            },
        )
        if request.retry_failed:
            replace_json(out / "capture-manifest.json", manifest)
        else:
            write_json_new(out / "capture-manifest.json", manifest)
        progress.update(state="failed" if stopped else "finished", current=None, error=error)
        failures = [
            {"symbol": s["symbol"], "code": s["error"]["code"], "message": s["error"]["message"]}
            for s in symbols
            if s["status"] == "failed"
        ]
        return {
            "jobId": job_id,
            "outputDir": str(out),
            "state": state,
            "totals": totals,
            "failures": failures,
            "desktopVersionChanged": changed,
            "error": error,
        }


def _restore(driver: ChartDriver, original: Any, request: CaptureRequest) -> None:
    """Put the chart back on the symbol and resolution it showed before the batch."""
    if isinstance(original, dict) and original.get("symbol"):
        with contextlib.suppress(CaptureError):
            driver.run(
                "switch",
                {"symbol": original["symbol"], "timeframe": original.get("resolution") or request.timeframe},
                timeout=40.0,
            )
    if request.viewport is not None:
        with contextlib.suppress(CaptureError):
            driver.clear_viewport()


def capture_symbol(
    driver: ChartDriver,
    request: CaptureRequest,
    out: Path,
    code: str,
    *,
    attempt: int,
    attempt_dir: Path,
    self_check: bool,
    info: DesktopInfo,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, Any]:
    started_at = stamp()
    before = ReadySnapshot.from_page(driver.run("ready"))
    switched = driver.run("switch", {"symbol": code, "timeframe": request.timeframe}, timeout=40.0) or {}
    after = switched.get("after") or {}
    if switched.get("timedOut") or after.get("symbol") != code:
        raise CaptureError(SYMBOL_NOT_FOUND, "the chart did not switch to this symbol", {"after": after})
    switched_at = stamp()
    verdict, snapshot, polls, waited = wait_until_ready(
        lambda: ReadySnapshot.from_page(driver.run("ready")),
        target=code,
        timeframe=request.timeframe,
        before_switch=before,
        timeout=request.ready_timeout_sec,
        sleep=sleep,
        clock=clock,
    )
    ready_at = stamp()
    extracted = driver.run("extract", timeout=120.0) or {}
    extracted_at = stamp()
    shot = driver.run("screenshot", timeout=60.0) or {}
    screenshot_at = stamp()
    try:
        png = base64.b64decode(str(shot.get("base64") or ""), validate=True)
    except (binascii.Error, ValueError):
        png = b""
    size = png_size(png)
    identity = extracted.get("identity") or {}
    studies = extracted.get("studies") or []
    series = extracted.get("series") or {}
    names = [str(s.get("name") or "") for s in studies]
    missing = [want for want in request.required_studies if not any(want in name for name in names)]
    if self_check:
        failed = [
            name
            for name, ok in (
                ("identity", bool(identity.get("symbol"))),
                ("studies", bool(studies)),
                ("requiredStudies", not missing),
                ("series", bool(series.get("rows"))),
                ("screenshot", size is not None),
            )
            if not ok
        ]
        if failed:
            raise CaptureError(
                TV_INTERNALS_CHANGED,
                "the self-check on the first symbol failed",
                {"failedChecks": failed, "missingStudies": missing},
            )
    if identity.get("symbol") != code:
        raise CaptureError(
            SYMBOL_NOT_FOUND, "the extracted chart is not this symbol", {"symbol": identity.get("symbol")}
        )
    if missing:
        raise CaptureError(STUDY_MISSING, "required studies are missing", {"missing": missing})
    if size is None:
        raise CaptureError(CDP_ERROR, "the screenshot is not a PNG", {})
    if not series.get("rows"):
        raise CaptureError(CDP_ERROR, "the chart returned no bars", {})
    name = safe_name(code)
    final = out / "raw" / name
    if final.exists():
        raise CaptureError(OUTPUT_EXISTS, "this symbol already has a capture", {"symbol": code})
    partial = out / "raw" / f".{name}.partial-{attempt}"
    make_dir_new(partial)
    try:
        csv_bytes = str(series.get("csv") or "").encode("utf-8")
        data = {
            "schemaVersion": 1,
            "identity": identity,
            "studies": studies,
            "drawings": extracted.get("drawings") or [],
            "readiness": {
                "polls": polls,
                "waitedSec": round(waited, 3),
                "lastBarTime": snapshot.last_bar_time,
                "unchangedAfterSwitch": list(verdict.unchanged),
                "studies": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "status": s.status,
                        "lastTime": s.last_time,
                        "digest": s.digest,
                    }
                    for s in snapshot.studies
                ],
            },
        }
        data_bytes = dumps_json(data)
        files = {
            "image.png": {
                "sha256": write_new(partial / "image.png", png),
                "bytes": len(png),
                "width": size[0],
                "height": size[1],
            },
            "chart.csv": {
                "sha256": write_new(partial / "chart.csv", csv_bytes),
                "bytes": len(csv_bytes),
                "rows": series.get("rows"),
                "columns": series.get("columns"),
            },
            "data.json": {"sha256": write_new(partial / "data.json", data_bytes), "bytes": len(data_bytes)},
        }
        finished_at = stamp()
        capture = {
            "schemaVersion": 1,
            "tool": {"name": TOOL_NAME, "version": __version__},
            "desktop": {"version": info.version, "browser": info.browser},
            "captureMethod": CAPTURE_METHOD,
            "pngSource": PNG_SOURCE,
            "csvSource": CSV_SOURCE,
            "symbol": code,
            "layout": request.layout,
            "timeframe": request.timeframe,
            "attempt": attempt,
            "viewport": asdict(request.viewport) if request.viewport else None,
            "times": {
                "startedAt": started_at,
                "switchedAt": switched_at,
                "readyAt": ready_at,
                "extractedAt": extracted_at,
                "screenshotAt": screenshot_at,
                "finishedAt": finished_at,
            },
            "files": files,
        }
        capture_sha = write_json_new(partial / "capture.json", capture)
        os.rename(partial, final)
    except BaseException:
        if partial.exists():
            os.rename(partial, attempt_dir / f"{name}.failed")  # keep the evidence; never delete
        raise
    return {
        "symbol": code,
        "safeName": name,
        "status": "ok",
        "attempt": attempt,
        "captureSha256": capture_sha,
        "finishedAt": finished_at,
    }
```

- [ ] **Step 6: 确认通过**

Run: `uv run pytest tests/test_capture.py tests/test_diagnostics.py -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "feat(capture): run a batch with a self-check, per-symbol files, retries and a manifest"
```

### Task 10: 后台任务与结果读取

**Files:**
- Create: `src/tradingview_capture_mcp/jobs.py`、`src/tradingview_capture_mcp/results.py`
- Test: `tests/test_jobs.py`、`tests/test_results.py`

**Interfaces:**
- Consumes: `CaptureRequest`、`validate_request`、`run_capture`、`RealDesktop`、store 函数、`crop_png`。
- Produces（jobs）：`JOBS_DIR = ".tradingview-capture-jobs"`；`start(config, request, *, python=None) -> {jobId, outputDir, pid}`；`retry_request(config, output_dir) -> CaptureRequest`；`retry(config, output_dir, *, python=None)`；`status(config, *, job_id=None, output_dir=None) -> dict`（进程不在而状态仍是 running/starting 时改报 `crashed` 并给出日志路径）；`run_job(config, job_id) -> dict`。
- Produces（results）：`batch_summary(config, output_dir)`；`symbol_data(config, output_dir, symbol, parts=None, series_last=None)`；`crop(config, output_dir, symbol, x, y, width, height) -> bytes`；`save_crop(config, output_dir, symbol, box, destination) -> {path, sha256, bytes}`；`DEFAULT_PARTS`、`ALL_PARTS`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_jobs.py -->
```python
import os
import stat
import time

import pytest

from tradingview_capture_mcp import jobs
from tradingview_capture_mcp.capture import CaptureRequest
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import BatchLock, read_json, write_json_new


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())


@pytest.fixture
def stub_python(tmp_path):
    stub = tmp_path / "python-stub"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o700)
    return str(stub)


def request(config, name="batch"):
    return CaptureRequest(
        layout="Layout01",
        symbols=("BINANCE:AAAUSDT.P",),
        timeframe="1D",
        output_dir=str(config.output_root / name),
    )


def wait_for(config, job_id, state, seconds=5.0):
    deadline = time.monotonic() + seconds
    while True:
        current = jobs.status(config, job_id=job_id)
        if current["state"] == state or time.monotonic() > deadline:
            return current
        time.sleep(0.05)


def test_start_records_the_request_and_a_dead_child_reads_as_crashed(config, stub_python):
    started = jobs.start(config, request(config), python=stub_python)
    folder = config.output_root / jobs.JOBS_DIR
    for suffix in (".request.json", ".json", ".log"):
        assert stat.S_IMODE((folder / f"{started['jobId']}{suffix}").stat().st_mode) == 0o600
    assert read_json(folder / f"{started['jobId']}.request.json")["symbols"] == ["BINANCE:AAAUSDT.P"]
    current = wait_for(config, started["jobId"], "crashed")
    assert current["state"] == "crashed"
    assert current["log"].endswith(".log")


def test_start_refuses_an_existing_batch_and_a_held_lock(config, stub_python):
    (config.output_root / "batch").mkdir()
    with pytest.raises(CaptureError) as err:
        jobs.start(config, request(config), python=stub_python)
    assert err.value.code == "OUTPUT_EXISTS"
    with BatchLock(config.output_root), pytest.raises(CaptureError) as err:
        jobs.start(config, request(config, "other"), python=stub_python)
    assert err.value.code == "BATCH_LOCKED"


def test_status_by_output_dir_reads_job_json(config):
    out = config.output_root / "batch"
    out.mkdir()
    write_json_new(out / "job.json", {"jobId": "a" * 32, "pid": os.getpid(), "state": "running", "done": 1})
    assert jobs.status(config, output_dir=str(out))["state"] == "running"


def test_status_rejects_bad_and_unknown_jobs(config):
    for kwargs, code in (
        ({"job_id": "../x"}, "INVALID_ARGUMENT"),
        ({"job_id": "b" * 32}, "NOT_FOUND"),
        ({}, "INVALID_ARGUMENT"),
    ):
        with pytest.raises(CaptureError) as err:
            jobs.status(config, **kwargs)
        assert err.value.code == code


def test_retry_request_rebuilds_the_original_request(config):
    out = config.output_root / "batch"
    out.mkdir()
    write_json_new(out / "batch.json", {"request": request(config).to_dict()})
    rebuilt = jobs.retry_request(config, str(out))
    assert rebuilt.retry_failed
    assert (rebuilt.symbols, rebuilt.output_dir) == (("BINANCE:AAAUSDT.P",), str(out))


def test_retry_needs_failed_or_pending_symbols(config, stub_python):
    out = config.output_root / "batch"
    out.mkdir()
    write_json_new(out / "batch.json", {"request": request(config).to_dict()})
    with pytest.raises(CaptureError) as err:
        jobs.retry(config, str(out), python=stub_python)
    assert err.value.code == "NOT_FOUND"
    write_json_new(
        out / "capture-manifest.json", {"symbols": [{"symbol": "BINANCE:AAAUSDT.P", "status": "ok"}]}
    )
    with pytest.raises(CaptureError) as err:
        jobs.retry(config, str(out), python=stub_python)
    assert err.value.code == "NOT_FOUND"
```

<!-- file: tests/test_results.py -->
```python
import io
import stat

import pytest
from helpers import make_batch, png_bytes
from PIL import Image

from tradingview_capture_mcp import results
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import ensure_dir, write_json_new

SYMBOL = "BINANCE:AAAUSDT.P"


@pytest.fixture
def batch(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    config = Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())
    out = config.output_root / "day"
    make_batch(out, SYMBOL, png=png_bytes(40, 30))
    return config, out


def test_batch_summary_returns_the_manifest(batch):
    config, out = batch
    assert results.batch_summary(config, str(out))["state"] == "finished"


def test_batch_summary_while_running_and_when_missing(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    config = Config(app_path=tmp_path / "TV.app", debug_port=9333, output_root=root.resolve())
    out = config.output_root / "day"
    ensure_dir(out)
    with pytest.raises(CaptureError) as err:
        results.batch_summary(config, str(out))
    assert err.value.code == "NOT_FOUND"
    write_json_new(out / "job.json", {"state": "running", "done": 0})
    assert results.batch_summary(config, str(out))["state"] == "running"


def test_symbol_data_defaults(batch):
    config, out = batch
    data = results.symbol_data(config, str(out), SYMBOL)
    assert set(data) == {"symbol", "capture", "identity", "studies", "drawings"}
    assert data["studies"][0] == {
        "name": "Alpha",
        "id": "s1",
        "tables": [{"id": "0", "rows": [["Head", None]]}],
        "lastValues": [["Quarter", 11.25]],
    }
    assert data["capture"]["captureMethod"] == "CDP_DESKTOP"


def test_symbol_data_parts_and_series(batch):
    config, out = batch
    data = results.symbol_data(config, str(out), SYMBOL, parts=["labels"], series_last=1)
    assert data["studies"][0]["labels"] == [{"text": "9.5", "time": 2000}]
    assert data["series"] == {
        "columns": ["time", "open", "high", "low", "close"],
        "rows": [["2000", "1.5", "2.5", "1", "2"]],
    }
    assert "identity" not in data


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"symbol": SYMBOL, "parts": ["secret"]}, "INVALID_ARGUMENT"),
        ({"symbol": SYMBOL, "series_last": 0}, "INVALID_ARGUMENT"),
        ({"symbol": "BINANCE:ZZZUSDT.P"}, "NOT_FOUND"),
    ],
)
def test_symbol_data_rejects_bad_requests(batch, kwargs, code):
    config, out = batch
    with pytest.raises(CaptureError) as err:
        results.symbol_data(config, str(out), **kwargs)
    assert err.value.code == code


def test_crop_and_save(batch):
    config, out = batch
    with Image.open(io.BytesIO(results.crop(config, str(out), SYMBOL, 5, 5, 10, 8))) as image:
        assert image.size == (10, 8)
    saved = results.save_crop(config, str(out), SYMBOL, (0, 0, 4, 4), str(out / "crop.png"))
    assert saved["path"] == str((out / "crop.png").resolve())
    assert stat.S_IMODE((out / "crop.png").stat().st_mode) == 0o600


def test_saved_crops_stay_inside_the_root(batch, tmp_path):
    config, out = batch
    with pytest.raises(CaptureError) as err:
        results.save_crop(config, str(out), SYMBOL, (0, 0, 4, 4), str(tmp_path / "crop.png"))
    assert err.value.code == "OUTPUT_OUTSIDE_ROOT"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_jobs.py tests/test_results.py -q`
Expected: FAIL，`cannot import name 'jobs'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/jobs.py -->
```python
"""Start capture batches in a background process and report their progress."""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .capture import CaptureRequest, run_capture, validate_request
from .config import Config
from .driver import RealDesktop
from .errors import BATCH_LOCKED, INVALID_ARGUMENT, NOT_FOUND, OUTPUT_EXISTS, CaptureError
from .store import FILE_MODE, ensure_dir, lock_is_held, read_json, resolve_inside_root, stamp, write_json_new

JOBS_DIR = ".tradingview-capture-jobs"
_JOB_ID = re.compile(r"[0-9a-f]{32}")


def _jobs_dir(config: Config) -> Path:
    path = config.output_root / JOBS_DIR
    ensure_dir(path)
    return path


def _check_job_id(job_id: str) -> str:
    if not _JOB_ID.fullmatch(job_id or ""):
        raise CaptureError(INVALID_ARGUMENT, "job_id must be 32 hex characters", {})
    return job_id


def start(config: Config, request: CaptureRequest, *, python: str | None = None) -> dict[str, Any]:
    """Validate, then run the batch in a detached process; return at once with the job id."""
    validate_request(request)
    out = resolve_inside_root(config.output_root, request.output_dir)
    if request.retry_failed:
        manifest = out / "capture-manifest.json"
        if not manifest.is_file() or all(
            s.get("status") == "ok" for s in read_json(manifest).get("symbols", [])
        ):
            raise CaptureError(
                NOT_FOUND, "this batch has no failed or pending symbols", {"output_dir": str(out)}
            )
    elif out.exists():
        raise CaptureError(OUTPUT_EXISTS, "output_dir already exists", {"output_dir": str(out)})
    if lock_is_held(config.output_root):
        raise CaptureError(BATCH_LOCKED, "another capture is running", {})
    job_id = uuid.uuid4().hex
    folder = _jobs_dir(config)
    write_json_new(folder / f"{job_id}.request.json", request.to_dict())
    log = os.open(folder / f"{job_id}.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        process = subprocess.Popen(
            [python or sys.executable, "-m", "tradingview_capture_mcp.cli", "run-job", "--job-id", job_id],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    finally:
        os.close(log)
    write_json_new(
        folder / f"{job_id}.json",
        {"jobId": job_id, "pid": process.pid, "outputDir": str(out), "startedAt": stamp()},
    )
    return {"jobId": job_id, "outputDir": str(out), "pid": process.pid}


def retry_request(config: Config, output_dir: str) -> CaptureRequest:
    out = resolve_inside_root(config.output_root, output_dir)
    batch = out / "batch.json"
    if not batch.is_file():
        raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})
    raw = dict(read_json(batch)["request"])
    raw.update(output_dir=str(out), retry_failed=True)
    return CaptureRequest.from_dict(raw)


def retry(config: Config, output_dir: str, *, python: str | None = None) -> dict[str, Any]:
    return start(config, retry_request(config, output_dir), python=python)


def _alive(pid: int) -> bool:
    with contextlib.suppress(ChildProcessError):
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False  # our own child, and it has exited
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(config: Config, *, job_id: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
    if job_id:
        _check_job_id(job_id)
        index_path = config.output_root / JOBS_DIR / f"{job_id}.json"
        if not index_path.is_file():
            raise CaptureError(NOT_FOUND, "unknown job", {"job_id": job_id})
        index = read_json(index_path)
        out, pid = Path(index["outputDir"]), int(index["pid"])
    elif output_dir:
        out, pid = resolve_inside_root(config.output_root, output_dir), None
    else:
        raise CaptureError(INVALID_ARGUMENT, "pass job_id or output_dir", {})
    job_path = out / "job.json"
    job: dict[str, Any] = read_json(job_path) if job_path.is_file() else {}
    if not job or (job_id and job.get("jobId") != job_id):
        job = {"jobId": job_id, "state": "starting", "outputDir": str(out)}  # the child has not written yet
    pid = pid or job.get("pid")
    if job.get("state") in ("running", "starting") and pid and not _alive(int(pid)):
        job["state"] = "crashed"
        job["log"] = str(config.output_root / JOBS_DIR / f"{job.get('jobId')}.log")
    return job


def run_job(config: Config, job_id: str) -> dict[str, Any]:
    """Body of the background process that start() launches."""
    request = CaptureRequest.from_dict(
        read_json(config.output_root / JOBS_DIR / f"{_check_job_id(job_id)}.request.json")
    )
    return run_capture(
        request, config, job_id=job_id, desktop=RealDesktop(config, request.layout), pid=os.getpid()
    )
```

<!-- file: src/tradingview_capture_mcp/results.py -->
```python
"""Read batches: summaries, per-symbol data, CSV rows and crops."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from .config import Config
from .errors import INVALID_ARGUMENT, NOT_FOUND, CaptureError
from .images import crop_png
from .store import read_json, resolve_inside_root, safe_name, write_new

DEFAULT_PARTS = ("identity", "tables", "lastValues", "drawings")
STUDY_PARTS = ("tables", "labels", "lines", "boxes", "lastValues", "inputs")
ALL_PARTS = ("identity", "drawings", "readiness", *STUDY_PARTS)
MAX_SERIES_ROWS = 1000


def batch_summary(config: Config, output_dir: str) -> dict[str, Any]:
    out = resolve_inside_root(config.output_root, output_dir)
    if (out / "capture-manifest.json").is_file():
        return read_json(out / "capture-manifest.json")
    if (out / "job.json").is_file():
        return {"state": "running", "job": read_json(out / "job.json")}
    raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})


def _symbol_dir(config: Config, output_dir: str, symbol: str) -> Path:
    folder = resolve_inside_root(config.output_root, output_dir) / "raw" / safe_name(symbol)
    if not (folder / "capture.json").is_file():
        raise CaptureError(NOT_FOUND, "this symbol has no capture in the batch", {"symbol": symbol})
    return folder


def symbol_data(
    config: Config,
    output_dir: str,
    symbol: str,
    parts: list[str] | None = None,
    series_last: int | None = None,
) -> dict[str, Any]:
    wanted = tuple(parts) if parts else DEFAULT_PARTS
    unknown = [p for p in wanted if p not in ALL_PARTS]
    if unknown:
        raise CaptureError(
            INVALID_ARGUMENT, "unknown parts", {"unknown": unknown, "allowed": list(ALL_PARTS)}
        )
    if series_last is not None and not 1 <= series_last <= MAX_SERIES_ROWS:
        raise CaptureError(INVALID_ARGUMENT, f"series_last must be between 1 and {MAX_SERIES_ROWS}", {})
    folder = _symbol_dir(config, output_dir, symbol)
    data = read_json(folder / "data.json")
    capture = read_json(folder / "capture.json")
    result: dict[str, Any] = {
        "symbol": symbol,
        "capture": {
            "capturedAt": (capture.get("times") or {}).get("finishedAt"),
            "captureMethod": capture.get("captureMethod"),
            "desktopVersion": (capture.get("desktop") or {}).get("version"),
            "files": capture.get("files"),
        },
    }
    for part in ("identity", "drawings", "readiness"):
        if part in wanted:
            result[part] = data.get(part)
    study_parts = [p for p in STUDY_PARTS if p in wanted]
    if study_parts:
        result["studies"] = [
            {"name": s.get("name"), "id": s.get("id"), **{p: s.get(p) for p in study_parts}}
            for s in data.get("studies", [])
        ]
    if series_last:
        rows = list(csv.reader(io.StringIO((folder / "chart.csv").read_text(encoding="utf-8"))))
        result["series"] = {"columns": rows[0] if rows else [], "rows": rows[1:][-series_last:]}
    return result


def crop(config: Config, output_dir: str, symbol: str, x: int, y: int, width: int, height: int) -> bytes:
    return crop_png(_symbol_dir(config, output_dir, symbol) / "image.png", x, y, width, height)


def save_crop(
    config: Config, output_dir: str, symbol: str, box: tuple[int, int, int, int], destination: str
) -> dict[str, Any]:
    data = crop(config, output_dir, symbol, *box)
    target = resolve_inside_root(config.output_root, destination)
    return {"path": str(target), "sha256": write_new(target, data), "bytes": len(data)}
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_jobs.py tests/test_results.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(jobs): run batches in a detached process and read their results"
```

### Task 11: 命令行

**Files:**
- Create: `src/tradingview_capture_mcp/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `jobs`、`results`、`diagnostics`、`run_capture`、`RealDesktop`、`load_config`。
- Produces: `main(argv=None) -> int`（stdout 输出 JSON；`CaptureError` 时输出 `{"error": {...}}` 并返回 2）；子命令 `capture`（默认后台，`--foreground` 前台）、`run-job`（后台进程入口，帮助里不显示）、`status`、`read`、`crop`、`doctor`、`mcp`。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_cli.py -->
```python
import json

import pytest
from helpers import make_batch, write_config

from tradingview_capture_mcp.cli import main

SYMBOL = "BINANCE:AAAUSDT.P"


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("TRADINGVIEW_CAPTURE_CONFIG", str(write_config(tmp_path, root)))
    return root.resolve()


def run(capsys, *argv):
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_status_summary_and_read(root, capsys):
    out = root / "day"
    make_batch(out, SYMBOL)
    code, payload = run(capsys, "status", "--output-dir", str(out), "--summary")
    assert (code, payload["state"]) == (0, "finished")
    code, payload = run(capsys, "read", "--output-dir", str(out), "--symbol", SYMBOL, "--part", "identity")
    assert payload["identity"]["symbol"] == SYMBOL


def test_crop_writes_a_private_file(root, capsys):
    out = root / "day"
    make_batch(out, SYMBOL)
    code, payload = run(
        capsys,
        "crop",
        "--output-dir",
        str(out),
        "--symbol",
        SYMBOL,
        "--box",
        "0,0,4,4",
        "--out",
        str(out / "c.png"),
    )
    assert code == 0 and payload["bytes"] > 0


@pytest.mark.parametrize(
    "argv",
    [
        ["capture", "--layout", "../bad", "--symbol", SYMBOL, "--output-dir", "{root}/x"],
        [
            "capture",
            "--layout",
            "Layout01",
            "--symbol",
            SYMBOL,
            "--output-dir",
            "{root}/x",
            "--viewport",
            "10x10",
        ],
        [
            "capture",
            "--layout",
            "Layout01",
            "--symbol",
            SYMBOL,
            "--output-dir",
            "{root}/x",
            "--viewport",
            "wide",
        ],
        ["crop", "--output-dir", "{root}/day", "--symbol", SYMBOL, "--box", "1,2,3", "--out", "{root}/c.png"],
        ["status", "--job-id", "c" * 31],
    ],
)
def test_errors_are_json_with_exit_code_2(root, capsys, argv):
    code, payload = run(capsys, *[a.format(root=root) for a in argv])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.cli'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/cli.py -->
```python
"""Command line: capture, status, read, crop, doctor, and the stdio MCP server."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from . import diagnostics, jobs, results
from .capture import CaptureRequest, run_capture
from .config import load_config
from .driver import RealDesktop, Viewport
from .errors import INVALID_ARGUMENT, CaptureError


def _viewport(value: str | None) -> Viewport | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+)x(\d+)(?:@(\d+(?:\.\d+)?))?", value)
    if not match:
        raise CaptureError(INVALID_ARGUMENT, "viewport must look like 1835x821@2", {"viewport": value})
    return Viewport(int(match[1]), int(match[2]), float(match[3] or 1.0))


def _box(value: str) -> tuple[int, int, int, int]:
    parts = value.split(",")
    if len(parts) != 4 or not all(p.strip().isdigit() for p in parts):
        raise CaptureError(INVALID_ARGUMENT, "box must be x,y,width,height in pixels", {"box": value})
    x, y, width, height = (int(p) for p in parts)
    return x, y, width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingview-capture", description="Capture TradingView Desktop charts for AI agents."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="start a batch (in the background unless --foreground)")
    cap.add_argument("--output-dir", required=True)
    cap.add_argument("--layout")
    cap.add_argument("--symbol", action="append", default=[], help="a TradingView code; repeat for more")
    cap.add_argument("--symbols-file", help="a file with one TradingView code per line")
    cap.add_argument("--timeframe", default="1D")
    cap.add_argument("--required-study", action="append", default=[])
    cap.add_argument("--viewport", help="WIDTHxHEIGHT[@SCALE], for example 1835x821@2")
    cap.add_argument("--ready-timeout", type=float, default=60.0)
    cap.add_argument("--retry-failed", action="store_true", help="retry the failed symbols of --output-dir")
    cap.add_argument("--foreground", action="store_true")
    job = sub.add_parser("run-job", help=argparse.SUPPRESS)
    job.add_argument("--job-id", required=True)
    status = sub.add_parser("status", help="progress of a job, or a batch summary")
    which = status.add_mutually_exclusive_group(required=True)
    which.add_argument("--job-id")
    which.add_argument("--output-dir")
    status.add_argument(
        "--summary", action="store_true", help="print the batch manifest (needs --output-dir)"
    )
    read = sub.add_parser("read", help="structured data for one symbol")
    read.add_argument("--output-dir", required=True)
    read.add_argument("--symbol", required=True)
    read.add_argument("--part", action="append")
    read.add_argument("--series-last", type=int)
    crop = sub.add_parser("crop", help="save a crop of a symbol's image")
    crop.add_argument("--output-dir", required=True)
    crop.add_argument("--symbol", required=True)
    crop.add_argument("--box", required=True, help="x,y,width,height")
    crop.add_argument("--out", required=True)
    doctor = sub.add_parser("doctor", help="check the TradingView Desktop internals a capture needs")
    doctor.add_argument("--layout", required=True)
    sub.add_parser("mcp", help="run the MCP server on stdio")
    return parser


def _capture(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config = load_config()
    if args.retry_failed:
        request = jobs.retry_request(config, args.output_dir)
    else:
        symbols = list(args.symbol)
        if args.symbols_file:
            lines = Path(args.symbols_file).read_text(encoding="utf-8").splitlines()
            symbols += [line.strip() for line in lines if line.strip()]
        request = CaptureRequest(
            layout=args.layout or "",
            symbols=tuple(symbols),
            timeframe=args.timeframe,
            output_dir=args.output_dir,
            required_studies=tuple(args.required_study),
            viewport=_viewport(args.viewport),
            ready_timeout_sec=args.ready_timeout,
        )
    if not args.foreground:
        return jobs.start(config, request), 0
    summary = run_capture(
        request, config, job_id=uuid.uuid4().hex, desktop=RealDesktop(config, request.layout), pid=os.getpid()
    )
    return summary, 0 if summary["state"] == "finished" else 1


def _dispatch(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "capture":
        return _capture(args)
    config = load_config()
    if args.command == "run-job":
        summary = jobs.run_job(config, args.job_id)
        return summary, 0 if summary["state"] == "finished" else 1
    if args.command == "status":
        if args.summary:
            if not args.output_dir:
                raise CaptureError(INVALID_ARGUMENT, "--summary needs --output-dir", {})
            return results.batch_summary(config, args.output_dir), 0
        return jobs.status(config, job_id=args.job_id, output_dir=args.output_dir), 0
    if args.command == "read":
        return results.symbol_data(
            config, args.output_dir, args.symbol, parts=args.part, series_last=args.series_last
        ), 0
    if args.command == "crop":
        return results.save_crop(config, args.output_dir, args.symbol, _box(args.box), args.out), 0
    if args.command == "doctor":
        report = diagnostics.run_doctor(config, args.layout)
        return report, 0 if not report["problems"] else 1
    raise CaptureError(INVALID_ARGUMENT, f"unknown command {args.command}", {})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        from .mcp_server import main as serve

        serve()
        return 0
    try:
        payload, code = _dispatch(args)
    except CaptureError as exc:
        payload, code = {"error": exc.to_dict()}, 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(cli): add capture, status, read, crop and doctor commands with JSON output"
```

### Task 12: MCP 服务

**Files:**
- Create: `src/tradingview_capture_mcp/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `jobs.start` / `retry` / `status`、`results.*`、`diagnostics.run_doctor`、`load_config`。
- Produces: `app`（`MCPServer`），7 个工具：`capture_start`、`capture_retry`、`capture_status`、`batch_summary`、`symbol_data`、`image_crop`（返回 PNG 图像内容）、`diagnose`；`CaptureError` 变成 `ToolError`，消息是错误对象的 JSON；`main()` 走 stdio。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_mcp_server.py -->
```python
import asyncio
import json

import pytest
from helpers import make_batch, write_config
from mcp.server.mcpserver.exceptions import ToolError

from tradingview_capture_mcp.mcp_server import app

SYMBOL = "BINANCE:AAAUSDT.P"


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("TRADINGVIEW_CAPTURE_CONFIG", str(write_config(tmp_path, root)))
    return root.resolve()


def call(name, arguments):
    return asyncio.run(app.call_tool(name, arguments))


def test_the_seven_tools_are_listed():
    tools = asyncio.run(app.list_tools())
    assert {tool.name for tool in tools} == {
        "capture_start",
        "capture_retry",
        "capture_status",
        "batch_summary",
        "symbol_data",
        "image_crop",
        "diagnose",
    }


def test_batch_summary_and_symbol_data(root):
    out = root / "day"
    make_batch(out, SYMBOL)
    summary = json.loads(call("batch_summary", {"output_dir": str(out)}).content[0].text)
    assert summary["state"] == "finished"
    data = json.loads(
        call("symbol_data", {"output_dir": str(out), "symbol": SYMBOL, "parts": ["identity"]}).content[0].text
    )
    assert data["identity"]["resolution"] == "1D"


def test_image_crop_returns_an_image(root):
    out = root / "day"
    make_batch(out, SYMBOL)
    result = call(
        "image_crop", {"output_dir": str(out), "symbol": SYMBOL, "x": 0, "y": 0, "width": 8, "height": 8}
    )
    assert (result.content[0].type, result.content[0].mime_type) == ("image", "image/png")


def test_errors_carry_the_code(root):
    with pytest.raises(ToolError) as err:
        call("capture_start", {"layout": "../bad", "symbols": [SYMBOL], "output_dir": str(root / "x")})
    assert "INVALID_ARGUMENT" in str(err.value)
    with pytest.raises(ToolError) as err:
        call("capture_status", {"job_id": "c" * 32})
    assert "NOT_FOUND" in str(err.value)
```

- [ ] **Step 2: 确认失败**

Run: `uv run pytest tests/test_mcp_server.py -q`
Expected: FAIL，`No module named 'tradingview_capture_mcp.mcp_server'`

- [ ] **Step 3: 实现**

<!-- file: src/tradingview_capture_mcp/mcp_server.py -->
```python
"""MCP tools on stdio; every tool calls the same functions as the command line."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, diagnostics, jobs, results
from .capture import CaptureRequest
from .config import load_config
from .driver import Viewport
from .errors import INVALID_ARGUMENT, CaptureError

INSTRUCTIONS = (
    "Captures TradingView Desktop charts into files. capture_start returns at once with a job id; poll "
    "capture_status until the state is finished, failed or crashed, then read the batch with batch_summary, "
    "symbol_data and image_crop. Errors carry a stable code such as TV_ALREADY_RUNNING or TV_INTERNALS_CHANGED."
)

app = MCPServer(name="tradingview-capture", version=__version__, instructions=INSTRUCTIONS)
F = TypeVar("F", bound=Callable[..., Any])


def _coded(fn: F) -> F:
    """Turn CaptureError into a tool error whose text is the JSON error object."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except CaptureError as exc:
            raise ToolError(json.dumps(exc.to_dict(), ensure_ascii=False)) from exc

    return wrapper  # type: ignore[return-value]


@app.tool(
    description="Start capturing TradingView codes from one TradingView Desktop layout into output_dir. "
    "Returns a job id at once."
)
@_coded
def capture_start(
    layout: str,
    symbols: list[str],
    output_dir: str,
    timeframe: str = "1D",
    required_studies: list[str] | None = None,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    viewport_scale: float = 1.0,
    ready_timeout_sec: float = 60.0,
) -> dict[str, Any]:
    viewport = None
    if viewport_width is not None or viewport_height is not None:
        if viewport_width is None or viewport_height is None:
            raise CaptureError(INVALID_ARGUMENT, "pass both viewport_width and viewport_height", {})
        viewport = Viewport(viewport_width, viewport_height, viewport_scale)
    request = CaptureRequest(
        layout=layout,
        symbols=tuple(symbols),
        timeframe=timeframe,
        output_dir=output_dir,
        required_studies=tuple(required_studies or ()),
        viewport=viewport,
        ready_timeout_sec=ready_timeout_sec,
    )
    return jobs.start(load_config(), request)


@app.tool(description="Retry the failed and pending symbols of an existing batch. Returns a job id at once.")
@_coded
def capture_retry(output_dir: str) -> dict[str, Any]:
    return jobs.retry(load_config(), output_dir)


@app.tool(description="Progress of a capture job, by job_id or by output_dir.")
@_coded
def capture_status(job_id: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
    return jobs.status(load_config(), job_id=job_id, output_dir=output_dir)


@app.tool(description="The manifest of a batch: per-symbol status, errors and file hashes.")
@_coded
def batch_summary(output_dir: str) -> dict[str, Any]:
    return results.batch_summary(load_config(), output_dir)


@app.tool(
    description="Structured data for one symbol. parts: identity, tables, labels, lines, boxes, lastValues, "
    "drawings, readiness, inputs (default identity, tables, lastValues, drawings). "
    "series_last adds the last N CSV rows."
)
@_coded
def symbol_data(
    output_dir: str, symbol: str, parts: list[str] | None = None, series_last: int | None = None
) -> dict[str, Any]:
    return results.symbol_data(load_config(), output_dir, symbol, parts=parts, series_last=series_last)


@app.tool(description="Crop a pixel region of a symbol's image.png and return it as a PNG image.")
@_coded
def image_crop(output_dir: str, symbol: str, x: int, y: int, width: int, height: int) -> Image:
    return Image(data=results.crop(load_config(), output_dir, symbol, x, y, width, height), format="png")


@app.tool(
    description="Start TradingView Desktop briefly and report which internal paths a capture needs are "
    "available. Returns no chart contents."
)
@_coded
def diagnose(layout: str) -> dict[str, Any]:
    return diagnostics.run_doctor(load_config(), layout)


def main() -> None:
    app.run("stdio")
```

- [ ] **Step 4: 确认通过**

Run: `uv run pytest tests/test_mcp_server.py -q`，再跑全量 `uv run pytest -q && node --test "tests/js/*.test.mjs" && uv run ruff check && uv run ruff format --check`
Expected: 全部 PASS，ruff 无输出。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(mcp): expose capture, status, data, crop and diagnose tools on stdio"
```

### Task 13: 开源协作文件、AI 编码规范、私有内容扫描与 CI

**Files:**
- Create: `scripts/check-private-content.sh`、`.githooks/pre-commit`、`.github/workflows/ci.yml`、`.github/dependabot.yml`、`.github/CODEOWNERS`、`.github/pull_request_template.md`、`.github/ISSUE_TEMPLATE/bug_report.yml`、`.github/ISSUE_TEMPLATE/feature_request.yml`、`.github/ISSUE_TEMPLATE/config.yml`、`AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`MAINTAINERS.md`、`CHANGELOG.md`、`docs/ai-coding/`（8 份）
- Modify: `README.md`
- Test: `tests/test_private_scan.py`

**Interfaces:**
- Produces: `bash scripts/check-private-content.sh [--staged]`：发现令牌形字符串、本机绝对路径、非回环 IPv4、本机私有词清单（默认 `~/.config/tradingview-capture-mcp/private-terms.txt`，可用 `TRADINGVIEW_CAPTURE_PRIVATE_TERMS` 指定）里的词时，逐行输出 `文件:行: 类别` 并退出 1；整行含 `private-content: allow` 的跳过。CI 两个检查名：`test (macos-latest)`、`private-content`。

- [ ] **Step 1: 写扫描脚本的失败测试**

<!-- file: tests/test_private_scan.py -->
```python
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-private-content.sh"


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / SCRIPT.name)
    return tmp_path


def scan(repo, *args, terms=None):
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(repo),
        "TRADINGVIEW_CAPTURE_PRIVATE_TERMS": str(terms or repo / "none.txt"),
    }
    return subprocess.run(
        ["bash", "scripts/check-private-content.sh", *args], cwd=repo, env=env, capture_output=True, text=True
    )


def add(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=repo, check=True)


def test_a_clean_repository_passes(repo):
    add(repo, "ok.py", 'HOST = "127.0.0.1"\nBROWSER = "Chrome/146.0.7680.216"\n')
    assert scan(repo).returncode == 0


@pytest.mark.parametrize(
    "text, category",
    [
        ("path = '/Users/someone/project'\n", "local-path"),  # private-content: allow
        ("server = '10.1.2.3'\n", "ip-address"),  # private-content: allow
        ("token = 'ghp_" + "a" * 36 + "'\n", "token"),
    ],
)
def test_findings_fail_the_scan(repo, text, category):
    add(repo, "bad.py", text)
    result = scan(repo)
    assert result.returncode == 1
    assert f"bad.py:1: {category}" in result.stdout


def test_private_terms_come_from_the_local_list(repo):
    terms = repo / "terms.txt"
    terms.write_text("# comment\nSecretLayout42\n\n", encoding="utf-8")
    add(repo, "doc.md", "see SecretLayout42 here\n")
    result = scan(repo, terms=terms)
    assert result.returncode == 1
    assert "doc.md:1: private-term" in result.stdout


def test_staged_mode_checks_the_index(repo):
    add(repo, "a.txt", "fine\n")
    (repo / "a.txt").write_text("/Users/x/y\n", encoding="utf-8")  # private-content: allow
    assert scan(repo, "--staged").returncode == 0
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    assert scan(repo, "--staged").returncode == 1
```

- [ ] **Step 2: 写扫描脚本、钩子与 CI**

<!-- file: scripts/check-private-content.sh -->
```bash
#!/usr/bin/env bash
# Fail when files that would be published contain things that must stay private:
# token-shaped strings, local absolute paths, IPv4 addresses other than loopback, and the
# maintainer's private terms, kept outside the repository (one per line, # for comments).
# A line containing the marker "private-content: allow" is skipped; use it only for test fixtures.
set -euo pipefail

mode="${1:-tracked}"
terms_file="${TRADINGVIEW_CAPTURE_PRIVATE_TERMS:-$HOME/.config/tradingview-capture-mcp/private-terms.txt}"
cd "$(git rev-parse --show-toplevel)"

token_re='(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|xox[abprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
path_re='(/Users/[A-Za-z0-9._-]+/|/Volumes/[A-Za-z0-9._-]+/|/home/[a-z_][a-z0-9_-]*/)'
octet='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])'
ip_re="(^|[^/A-Za-z0-9.])(${octet}\\.){3}${octet}([^0-9.]|\$)"
allow='private-content: allow'
status=0

report() {
  printf '%s:%s: %s\n' "$1" "$2" "$3"
  status=1
}

matching_lines() {  # pattern flags; content in $content
  grep -n "$1" -- "$2" <<<"$content" | grep -vF -- "$allow" || true
}

scan_file() {  # file name; content on stdin
  local file="$1" hit term
  content="$(cat; printf x)"
  content="${content%x}"
  while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" token; done < <(matching_lines -E "$token_re")
  while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" local-path; done < <(matching_lines -E "$path_re")
  while IFS= read -r hit; do
    [[ -z "$hit" ]] && continue
    if grep -Eo -- "$ip_re" <<<"${hit#*:}" | grep -Eqv '(127\.0\.0\.1|0\.0\.0\.0)'; then
      report "$file" "${hit%%:*}" ip-address
    fi
  done < <(matching_lines -E "$ip_re")
  if [[ -f "$terms_file" ]]; then
    while IFS= read -r term || [[ -n "$term" ]]; do
      [[ -z "$term" || "$term" == \#* ]] && continue
      while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" private-term; done < <(matching_lines -F "$term")
    done <"$terms_file"
  fi
}

if [[ "$mode" == "--staged" ]]; then
  list_files() { git diff --cached --name-only --diff-filter=ACMR; }
  show_file() { git show ":$1"; }
else
  list_files() { git ls-files; }
  show_file() { cat -- "$1"; }
fi

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  case "$file" in *.png|*.jpg|*.jpeg|*.gif|*.ico|*.pdf|*.woff|*.woff2) continue ;; esac
  [[ "$mode" != "--staged" && ! -f "$file" ]] && continue
  scan_file "$file" < <(show_file "$file")
done < <(list_files)

if [[ $status -ne 0 ]]; then
  echo "private-content check failed: remove these lines, or mark deliberate test fixtures with \"$allow\"" >&2
fi
exit $status
```

<!-- file: .githooks/pre-commit -->
```bash
#!/usr/bin/env bash
# Enable once per clone with: git config core.hooksPath .githooks
exec bash scripts/check-private-content.sh --staged
```

<!-- file: .github/workflows/ci.yml -->
```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    name: test (macos-latest)
    runs-on: macos-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
      - uses: actions/setup-node@v7
        with:
          node-version: 24
      - run: uv sync --locked
      - run: uv run ruff check
      - run: uv run ruff format --check
      - run: uv run pytest -q
      - run: node --test "tests/js/*.test.mjs"

  private-content:
    name: private-content
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v7
      - run: bash scripts/check-private-content.sh
```

<!-- file: .github/dependabot.yml -->
```yaml
version: 2
updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
    # Delay version updates by 7 days as a supply-chain safeguard; security updates are not delayed.
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    commit-message:
      prefix: chore
      include: scope
    groups:
      python-minor-and-patch:
        update-types: [minor, patch]
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    cooldown:
      default-days: 7
    commit-message:
      prefix: ci
    groups:
      github-actions:
        patterns: ["*"]
```

<!-- file: .github/CODEOWNERS -->
```text
# Code owners are requested for review automatically. High-risk paths are listed explicitly so
# they stay covered when more maintainers join.
*                                            @sunkailun1992
/AGENTS.md                                   @sunkailun1992
/docs/ai-coding/                             @sunkailun1992
/src/tradingview_capture_mcp/page/           @sunkailun1992
/src/tradingview_capture_mcp/desktop.py      @sunkailun1992
/src/tradingview_capture_mcp/store.py        @sunkailun1992
/scripts/check-private-content.sh            @sunkailun1992
/.github/                                    @sunkailun1992
```

- [ ] **Step 3: 写协作与规范文档**

每份都按本项目职责写，不照搬别的仓库；中文为主，开头附 `## English summary`。内容要求：

- `README.md`：做什么、不做什么；要求（macOS、TradingView 桌面版且已登录、Python 3.12+、uv）；本机配置 `config.toml` 示例（只用 `~/...` 写法）；注册到 Claude Code（`claude mcp add --scope user tradingview-capture -- uv --directory <仓库路径> run tradingview-capture mcp`）和 Codex（`~/.codex/config.toml` 的 `[mcp_servers.tradingview-capture]`，`command = "uv"`，`args = ["--directory", "<仓库路径>", "run", "tradingview-capture", "mcp"]`）；7 个 MCP 工具和命令行对照表；输出目录结构；安全边界（端口只在本机、只停自己的进程、文件 0600）；同账号在别处登录可能被 TradingView 挤下线；非官方声明与服务条款提示；许可证。
- `AGENTS.md`：项目定位；修改前阅读顺序（README → `docs/ai-coding/README.md` → 各规范）；硬规则（不执行任意脚本、页面里只许切换品种和周期、只停自己的进程、文件 0600 只新建、仓库不进私有内容、子进程用固定参数）；验证命令（`uv run pytest -q`、`node --test "tests/js/*.test.mjs"`、`uv run ruff check`、`uv run ruff format --check`、`bash scripts/check-private-content.sh`）；合并规则（维护者本人及其 Claude/Codex 会话可直接合并 main，其余 PR 经维护者审核；只 squash；禁止强推）；桌面版升级后的修复流程（spec 第 8 节五步）；禁止事项。
- `CLAUDE.md`：只有 `@AGENTS.md` 一行导入加一句"规则只维护在 AGENTS.md"。
- `docs/ai-coding/README.md`（索引与阅读顺序）、`AI_CODING_GUIDE.md`（模块关系、数据流、新增页面脚本的步骤、版本号用语义化版本）、`AI_DIRECTORY_STRUCTURE_GUIDE.md`（每个目录放什么、测试与源码对应）、`AI_COMMENT_STYLE_GUIDE.md`（英文注释写"为什么"，Python 一行 docstring，JS 文件头一句职责，文档中文附英文摘要）、`AI_DESIGN_PATTERN_GUIDE.md`（Protocol 接缝 `ChartDriver` / `DesktopControl`、纯函数判断就绪、不建插件系统）、`AI_ENGINEERING_GUARDRAILS.md`（风险分级：页面脚本、启停进程、写文件模式、私有扫描为极高；就绪判断、CSV 列规则、MCP 工具面为高；Definition of Done；活体测试只在本机）、`SECURITY_CODING_SPEC.md`（端口、任意脚本、进程、文件、网络、日志、私有内容七条规则）、`TESTING_SPEC.md`（单元、页面脚本、活体三层；夹具只用编造数据；TradingView 结构变化时如何补夹具）。
- `CONTRIBUTING.md`：可以贡献什么、开发环境（`uv sync`、`git config core.hooksPath .githooks`）、提交前检查、分支命名 `feat/<主题>` / `fix/<主题>`、英文 Conventional Commits、合并条件（同 AGENTS.md）、不要在 issue / PR 里贴真实布局、截图、表格内容。
- `CODE_OF_CONDUCT.md`：沿用 issuerelay 的结构（英文摘要 + 承诺 + 期望 + 不可接受 + 报告渠道 + 处理方式），项目名改成本仓库。
- `SECURITY.md`：用 GitHub 私密漏洞报告；范围（调试端口、文件权限、私有内容泄露）；不在公开 issue 里写细节。
- `MAINTAINERS.md`：维护者 `@sunkailun1992`；合并规则。
- `CHANGELOG.md`：`## 0.1.0 — 未发布`，列出首版能力。
- `.github/pull_request_template.md`：改动说明、关联 issue、风险等级（引用 AI_ENGINEERING_GUARDRAILS）、验证清单（上面五条命令）、是否做了活体测试。
- `.github/ISSUE_TEMPLATE/bug_report.yml`、`feature_request.yml`：表单里提醒不要贴真实布局 ID、截图和表格内容；`config.yml` 关闭空白 issue，安全问题指向 SECURITY.md。

- [ ] **Step 4: 运行**

Run: `chmod +x scripts/check-private-content.sh .githooks/pre-commit && git config core.hooksPath .githooks && uv run pytest tests/test_private_scan.py -q && bash scripts/check-private-content.sh`
Expected: 测试 PASS；对整个仓库的扫描无输出、退出 0。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "docs: add the contribution, security and AI coding guides with a private-content scan and CI"
```

### Task 14: 真机冒烟（只在本机）

**Files:**
- Create: `tests/test_live.py`
- 仓库外：`~/.config/tradingview-capture-mcp/config.toml`、`~/.config/tradingview-capture-mcp/private-terms.txt`、`~/.config/tradingview-capture-mcp/live.env`（三者 0600，都不进仓库）

**Interfaces:**
- Consumes: `run_capture`、`RealDesktop`、`load_config`。私有输入只从环境变量读：`TRADINGVIEW_CAPTURE_LIVE_LAYOUT`、`TRADINGVIEW_CAPTURE_LIVE_SYMBOL`、`TRADINGVIEW_CAPTURE_LIVE_STUDIES`（逗号分隔）、`TRADINGVIEW_CAPTURE_LIVE_PARENT`（输出根目录下已存在的目录）。

- [ ] **Step 1: 写活体测试**

<!-- file: tests/test_live.py -->
```python
"""End-to-end check against a logged-in TradingView Desktop. Local only; private inputs come from the environment."""

import os
from pathlib import Path

import pytest

from tradingview_capture_mcp.capture import CaptureRequest, run_capture
from tradingview_capture_mcp.config import load_config
from tradingview_capture_mcp.driver import RealDesktop
from tradingview_capture_mcp.store import read_json, safe_name

pytestmark = pytest.mark.live


def _env(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def test_capture_one_symbol_end_to_end():
    if os.environ.get("TRADINGVIEW_CAPTURE_LIVE") != "1":
        pytest.skip("set TRADINGVIEW_CAPTURE_LIVE=1 to run against TradingView Desktop")
    config = load_config()
    layout = _env("TRADINGVIEW_CAPTURE_LIVE_LAYOUT")
    symbol = _env("TRADINGVIEW_CAPTURE_LIVE_SYMBOL")
    studies = tuple(s for s in os.environ.get("TRADINGVIEW_CAPTURE_LIVE_STUDIES", "").split(",") if s)
    out = Path(_env("TRADINGVIEW_CAPTURE_LIVE_PARENT")) / f"live-{os.getpid()}"
    request = CaptureRequest(
        layout=layout, symbols=(symbol,), timeframe="1D", output_dir=str(out), required_studies=studies
    )
    summary = run_capture(
        request, config, job_id="f" * 32, desktop=RealDesktop(config, layout), pid=os.getpid()
    )
    assert summary["state"] == "finished", summary
    assert summary["totals"]["succeeded"] == 1, summary
    folder = out / "raw" / safe_name(symbol)
    data = read_json(folder / "data.json")
    assert data["identity"]["symbol"] == symbol
    assert any(study["tables"] for study in data["studies"])
    assert (folder / "chart.csv").read_text(encoding="utf-8").startswith("time,open,high,low,close")
```

- [ ] **Step 2: 准备仓库外的私有文件**

- `config.toml` 写桌面版路径、调试端口 9333、输出根目录（放在外置盘的私有研究目录下；外置盘没挂载就停下报告，不在内置盘新建）。
- `private-terms.txt` 写入：采集布局 ID 和桌面版里其余布局 ID、TradingView 用户名、私有指标名、外置盘卷名、调用方私有项目名。然后运行 `bash scripts/check-private-content.sh`，确认整个仓库对这些词零命中。
- `live.env` 写四个 `TRADINGVIEW_CAPTURE_LIVE_*` 变量。

- [ ] **Step 3: 先跑诊断，再跑一个品种**

确认桌面版没有在运行（`pgrep -x TradingView` 无输出），然后：

Run: `uv run tradingview-capture doctor --layout "$TRADINGVIEW_CAPTURE_LIVE_LAYOUT"`
Expected: `"problems": []`，退出 0；结束后 `pgrep -x TradingView` 无输出，`lsof -nP -iTCP:9333 -sTCP:LISTEN` 无输出。

Run: `set -a && . ~/.config/tradingview-capture-mcp/live.env && set +a && TRADINGVIEW_CAPTURE_LIVE=1 uv run pytest -m live -q`
Expected: PASS；桌面版已退出、端口已关，布局切回原来的品种。

- [ ] **Step 4: 人工核对一次输出**

读那个品种的 `capture.json`（版本号、各步时间、SHA256）、`data.json`（每张表的行数、标签数、曲线最后值）、`chart.csv`（列数、行数，是否以 `time,open,high,low,close` 开头、无结尾换行），并看一次 `image.png` 的缩略图，确认三张表、图例和 K 线都在。发现的问题按 TDD 先补测试再修。

- [ ] **Step 5: 提交**

```bash
git add tests/test_live.py && git commit -m "test: add a local-only end-to-end capture check"
```

### Task 15: 整批演练与原生文件比对

**Files:**
- Create: `scripts/compare_csv.py`
- Test: `tests/test_compare_csv.py`
- 仓库外：演练用的品种清单、演练批次、比对报告都放在私有输出根目录下

**Interfaces:**
- Produces: `python scripts/compare_csv.py A.csv B.csv [--skip-last N]`：按 `time` 对齐两份 CSV，输出 `{headerEqual, columns, headerDiff, rows, overlap, checked, mismatchedColumns}`；表头不同或任一重叠行不同时退出 1。`--skip-last` 默认 1，跳过最新的形成中 K 线。

- [ ] **Step 1: 写失败的测试**

<!-- file: tests/test_compare_csv.py -->
```python
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_csv.py"
spec = importlib.util.spec_from_file_location("compare_csv", SCRIPT)
compare_csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_csv)


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_identical_overlap_passes(tmp_path):
    a = write(tmp_path / "a.csv", "time,open,x\n1,1,5\n2,2,6\n3,3,7")
    b = write(tmp_path / "b.csv", "time,open,x\n2,2,6\n3,3,9\n4,4,1")
    report = compare_csv.compare(a, b, skip_last=1)
    assert report["headerEqual"]
    assert (report["overlap"], report["checked"], report["mismatchedColumns"]) == (2, 1, {})


def test_header_and_value_differences_are_reported(tmp_path):
    a = write(tmp_path / "a.csv", "time,open,x\n1,1,5\n2,2,6")
    b = write(tmp_path / "b.csv", "time,open,y\n1,1,5\n2,2,7")
    report = compare_csv.compare(a, b, skip_last=0)
    assert not report["headerEqual"]
    assert report["headerDiff"] == [[3, "x", "y"]]
    assert report["mismatchedColumns"] == {"3:x": {"count": 1, "first": {"time": "2", "a": "6", "b": "7"}}}
    assert compare_csv.main([str(a), str(b), "--skip-last", "0"]) == 1
```

- [ ] **Step 2: 实现**

<!-- file: scripts/compare_csv.py -->
```python
"""Compare two TradingView-style CSV exports row by row, keyed by the time column.

Used to check generated CSVs against TradingView's own export. Prints a JSON report and exits 1
when the headers differ or any compared row differs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], {row[0]: row for row in rows[1:] if row}


def compare(a: Path, b: Path, skip_last: int = 1) -> dict[str, Any]:
    header_a, rows_a = load(a)
    header_b, rows_b = load(b)
    shared = sorted(set(rows_a) & set(rows_b), key=float)
    checked = shared[:-skip_last] if skip_last else shared
    width = min(len(header_a), len(header_b))
    mismatches: dict[str, dict[str, Any]] = {}
    for time in checked:
        row_a, row_b = rows_a[time], rows_b[time]
        for i in range(width):
            value_a = row_a[i] if i < len(row_a) else ""
            value_b = row_b[i] if i < len(row_b) else ""
            if value_a != value_b:
                entry = mismatches.setdefault(
                    f"{i + 1}:{header_a[i]}",
                    {"count": 0, "first": {"time": time, "a": value_a, "b": value_b}},
                )
                entry["count"] += 1
    return {
        "headerEqual": header_a == header_b,
        "columns": [len(header_a), len(header_b)],
        "headerDiff": [
            [i + 1, x, y] for i, (x, y) in enumerate(zip(header_a, header_b, strict=False)) if x != y
        ],
        "rows": [len(rows_a), len(rows_b)],
        "overlap": len(shared),
        "checked": len(checked),
        "mismatchedColumns": mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two TradingView-style CSV exports by time.")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument(
        "--skip-last", type=int, default=1, help="ignore the newest N shared rows (the forming bar)"
    )
    args = parser.parse_args(argv)
    report = compare(args.a, args.b, args.skip_last)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["headerEqual"] and not report["mismatchedColumns"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

Run: `uv run pytest tests/test_compare_csv.py -q`
Expected: PASS；提交 `git add -A && git commit -m "feat(scripts): compare generated CSVs with native TradingView exports"`。

- [ ] **Step 3: 整批演练**

用私有品种清单（一行一个 TradingView 代码，放在私有输出根目录下），在私有输出根目录里建一个演练批次：

Run: `uv run tradingview-capture capture --foreground --layout "$TRADINGVIEW_CAPTURE_LIVE_LAYOUT" --symbols-file <私有清单> --output-dir <私有演练目录> --required-study <各必需指标> --viewport 1835x821@2`
Expected: `state` 为 `finished`；记下总耗时、成功数、失败数及原因、`desktopVersionChanged`。结束后桌面版已退出、端口已关、布局切回原品种。

- [ ] **Step 4: 与原生导出比对**

挑 3–5 个品种，拿维护者本机此前用菜单下载的原生 CSV（私有路径，不写进仓库），逐个运行 `uv run python scripts/compare_csv.py <原生.csv> <生成的 chart.csv> --skip-last 1`。
Expected: `headerEqual: true`、列数相同。重叠行若有差异：
- 列名或列序不同 → 修 `common.js` 的 `plotTitle` / `exportedPlots`，在 `tests/js/page.test.mjs` 先补用例，再修；
- 只集中在最近几根、且是跨周期曲线 → 记为指标重绘，写进私有比对报告，不算工具缺陷。

同时各看一次原生 PNG 和生成 PNG 的缩略图，确认是同一套面板；检查生成 PNG 的尺寸是否为 3670×1642，不是就调整 `--viewport` 的缩放并在 README 写明。比对结论写进私有报告；仓库里只在 `CHANGELOG.md` 记一句"表头与列序已与原生导出核对一致"（或写明尚存的差异类别），不写任何私有列名。

- [ ] **Step 5: 提交修正**

```bash
git add -A && git commit -m "fix(page): match the native export header and column order"
```
（没有需要修正的就跳过本步。）

### Task 16: 斐波各档价位

**Files:**
- Modify: `src/tradingview_capture_mcp/page/extract.js`（`drawings` 一段）
- Test: `tests/js/page.test.mjs`

**Interfaces:**
- Produces: `drawings[].levels[]` 增加 `price`：类型为 `fib_retracement` 且两个端点都有价位时，非反向为 `p2 + (p1 - p2) * coeff`，反向（`reverse: true`）为 `p1 + (p2 - p1) * coeff`；其余情况为 `null`。

- [ ] **Step 1: 先用真实斐波核对换算约定**

从 Task 15 演练批次的 `data.json` 里找出 `drawings` 中 `type` 为 `fib_retracement` 且 `points` 有两个点的品种；用 `image_crop` 裁出图上斐波的价位标签，记下 0 档和 1 档旁边写的价格，与两个端点价对照：0 档等于第二个点、1 档等于第一个点，就是上面的非反向公式；如果相反，把公式里的两点对调后再写代码。没有任何品种画了斐波时，本任务挂起，在 CHANGELOG 写明"斐波价位未验证"。

- [ ] **Step 2: 写失败的测试**

新建 `tests/js/fib.test.mjs`：

<!-- file: tests/js/fib.test.mjs -->
```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { makeTradingView, plotList } from './fake_tv.mjs';

const PAGE = new URL('../../src/tradingview_capture_mcp/page/', import.meta.url);
const source = (name) => readFileSync(new URL(`${name}.js`, PAGE), 'utf8');

async function extract(window) {
  const code = ['(async () => {', 'const ARGS = {};', source('common'), source('extract'), '})()'].join('\n');
  return JSON.parse(JSON.stringify(await vm.runInNewContext(code, { window, setTimeout })));
}

function fib(reverse) {
  return makeTradingView({
    bars: plotList([[1000, 1, 2, 0.5, 1.5], [2000, 1.5, 2.5, 1, 2]]),
    panes: [[]],
    shapes: [{ id: 'f', name: 'fib_retracement', points: [{ index: 0, price: 100 }, { index: 1, price: 200 }],
      properties: { level1: [0, '#000', true, ''], level2: [0.382, '#000', true, ''], level3: [1, '#000', true, ''], reverse } }],
  });
}

test('fib retracement levels are measured from the second point', async () => {
  const [drawing] = (await extract(fib(false))).drawings;
  assert.deepEqual(drawing.levels.map((l) => l.price), [200, 161.8, 100]);
});

test('reversed fib retracements are measured from the first point', async () => {
  const [drawing] = (await extract(fib(true))).drawings;
  assert.deepEqual(drawing.levels.map((l) => l.price), [100, 138.2, 200]);
});
```

Run: `node --test tests/js/fib.test.mjs`
Expected: FAIL（`price` 为 `undefined`）

- [ ] **Step 3: 实现**

把 `extract.js` 里 `drawings` 一段整体换成：

```javascript
const drawings = chart.getAllShapes().map((shape) => {
  const api = chart.getShapeById(shape.id);
  let points = [];
  try {
    points = api._source.points().map((p) => ({ index: p.index, time: barTime(p.index), price: num(p.price) }));
  } catch (e) {
    points = [];
  }
  let props = {};
  try {
    props = api.getProperties() || {};
  } catch (e) {
    props = {};
  }
  const reverse = props.reverse === true;
  const [first, second] = points;
  const span = shape.name === 'fib_retracement' && first && second && first.price !== null && second.price !== null
    ? (reverse ? { from: first.price, to: second.price } : { from: second.price, to: first.price })
    : null;
  const levels = [];
  for (let i = 1; i <= 24; i += 1) {
    const level = props['level' + i];
    if (!Array.isArray(level)) continue;
    const coeff = num(level[0]);
    // Rounded to 10 decimals so 200 + (100 - 200) * 0.382 reads 161.8 rather than 161.79999999999998.
    const price = span && coeff !== null ? Math.round((span.from + (span.to - span.from) * coeff) * 1e10) / 1e10 : null;
    levels.push({ coeff, visible: level[2] === true, text: text(level[3]) || '', price });
  }
  return { id: String(shape.id), type: shape.name, points, levels, reverse };
});
```

并把 `tests/js/page.test.mjs` 里原有的斐波断言补上 `price`：`levels: [{ coeff: 0, visible: true, text: '', price: 2 }, { coeff: 0.236, visible: false, text: '', price: 1.764 }]`。

- [ ] **Step 4: 确认通过并活体复核**

Run: `node --test "tests/js/*.test.mjs"`
Expected: PASS。再对 Step 1 找到的那个品种单独采一次（新的私有输出目录），确认各档 `price` 与图上标签一致。

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat(page): add verified price levels to Fibonacci retracement drawings"
```

### Task 17: 最终审查与公开发布

- [ ] **Step 1: 全量验证**

Run: `uv run pytest -q && node --test "tests/js/*.test.mjs" && uv run ruff check && uv run ruff format --check && bash scripts/check-private-content.sh`
Expected: 全部通过，扫描无输出。

- [ ] **Step 2: 一次独立审查**

派一个全新的审查代理（最强模型）通读整个仓库：spec 覆盖、正确性、安全边界（端口、进程、文件模式、任意脚本）、私有内容。提示里写明"不要调用 llm-wiki MCP 工具"。按审查结果先补测试再修，逐条提交。

- [ ] **Step 3: 公开发布前先问维护者**

发布是对外动作，执行前必须得到维护者明确同意。同意后：

```bash
gh repo create sunkailun1992/tradingview-capture-mcp --public --source . --remote origin \
  --description "Capture TradingView Desktop charts for AI agents over MCP"
git push -u origin main
gh api -X PATCH repos/sunkailun1992/tradingview-capture-mcp -F allow_squash_merge=true -F allow_merge_commit=false \
  -F allow_rebase_merge=false -F delete_branch_on_merge=true
gh api -X PUT repos/sunkailun1992/tradingview-capture-mcp/private-vulnerability-reporting
```

再用 `gh api -X POST repos/sunkailun1992/tradingview-capture-mcp/rulesets --input <ruleset.json>` 建 main 分支规则，内容与 issuerelay 一致：禁止删除与强推；PR 必须 1 人批准、评审对话全部解决、只允许 squash；必需检查 `test (macos-latest)` 和 `private-content`；仓库管理员角色（`actor_id: 5`、`RepositoryRole`）始终可绕过。

- [ ] **Step 4: 看 CI**

Run: `gh run watch --exit-status`
Expected: 两个检查都通过；红了就修，修完再推。
