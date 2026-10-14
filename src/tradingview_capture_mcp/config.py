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
VOLUMES = Path("/Volumes")


@dataclass(frozen=True)
class Config:
    app_path: Path
    debug_port: int
    output_root: Path

    @property
    def app_binary(self) -> Path:
        return self.app_path / "Contents" / "MacOS" / "TradingView"


def _unmounted_volume(root: Path) -> Path | None:
    """The /Volumes/<name> a directory sits on when that disk is not mounted.

    With the disk away, an ordinary /Volumes/<name> folder can be left on the startup disk, and batches
    written there would silently land on the wrong disk."""
    try:
        relative = root.relative_to(VOLUMES)
    except ValueError:
        return None
    if not relative.parts:
        return None
    volume = VOLUMES / relative.parts[0]
    return None if os.path.ismount(volume) else volume


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
    root = root.resolve()
    volume = _unmounted_volume(root)
    if volume is not None:
        raise CaptureError(
            CONFIG_INVALID,
            "output_root is under a disk that is not mounted",
            {"output_root": str(root), "volume": str(volume)},
        )
    port = raw.get("debug_port", DEFAULT_DEBUG_PORT)
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        raise CaptureError(
            CONFIG_INVALID, "debug_port must be an integer between 1024 and 65535", {"debug_port": port}
        )
    app = raw.get("app_path", str(DEFAULT_APP_PATH))
    if not isinstance(app, str) or not app:
        raise CaptureError(CONFIG_INVALID, "app_path must be a non-empty string", {})
    return Config(app_path=Path(app).expanduser(), debug_port=port, output_root=root)
