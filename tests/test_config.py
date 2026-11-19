import os
from pathlib import Path

import pytest

from tradingview_capture_mcp import config as config_module
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
    text = (
        f'app_path = "{tmp_path / "TV.app"}"\ndebug_port = 9444\noutput_root = "{root}"\nkeep_open = false\n'
    )
    config = load_config(write(tmp_path / "c.toml", text))
    assert (config.app_path, config.debug_port, config.keep_open) == (tmp_path / "TV.app", 9444, False)


def test_tradingview_is_kept_open_unless_the_config_says_otherwise(tmp_path):
    # Callers that write their own config with only app_path, debug_port and output_root get the new default.
    root = tmp_path / "out"
    root.mkdir()
    assert load_config(write(tmp_path / "c.toml", f'output_root = "{root}"\n')).keep_open is True
    text = f'output_root = "{root}"\nkeep_open = true\n'
    assert load_config(write(tmp_path / "d.toml", text)).keep_open is True


@pytest.mark.parametrize(
    "body, needle",
    [
        ("", "output_root is required"),
        ('output_root = "{missing}"\n', "existing directory"),
        ('output_root = "{root}"\ndebug_port = 80\n', "debug_port"),
        ('output_root = "{root}"\ndebug_port = true\n', "debug_port"),
        ('output_root = "{root}"\nextra = 1\n', "unknown config keys"),
        ('output_root = "{root}"\nkeep_open = "no"\n', "keep_open"),
        ('output_root = "{root}"\nkeep_open = 0\n', "keep_open"),
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


def _volume_root(tmp_path, monkeypatch):
    volumes = tmp_path.resolve() / "Volumes"
    root = volumes / "Archive" / "captures"
    root.mkdir(parents=True)
    monkeypatch.setattr(config_module, "VOLUMES", volumes)
    return volumes, write(tmp_path / "c.toml", f'output_root = "{root}"\n')


def test_rejects_an_output_root_left_behind_by_an_unmounted_disk(tmp_path, monkeypatch):
    volumes, path = _volume_root(tmp_path, monkeypatch)
    with pytest.raises(CaptureError) as err:
        load_config(path)
    assert err.value.code == "CONFIG_INVALID"
    assert "not mounted" in err.value.message
    assert err.value.detail["volume"] == str(volumes / "Archive")


def test_accepts_an_output_root_on_a_mounted_disk(tmp_path, monkeypatch):
    volumes, path = _volume_root(tmp_path, monkeypatch)
    monkeypatch.setattr(os.path, "ismount", lambda p: Path(p) == volumes / "Archive")
    assert load_config(path).output_root == volumes / "Archive" / "captures"
