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
        "pane": 0,
        "visible": True,
        "unresolvedGraphicColors": 0,
        "tables": [{"id": "0", "rows": [["Head", None]]}],
        "lastValues": [["Quarter", 11.25]],
    }
    assert data["capture"]["captureMethod"] == "CDP_DESKTOP"
    assert data["capture"]["resolvedSymbol"] == SYMBOL
    assert data["capture"]["readiness"]["unchangedAfterSwitch"] == ["Alpha"]
    assert "history" not in data["capture"]  # only batches captured with history_from have it


def test_symbol_data_shows_the_loaded_history(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    config = Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())
    history = {"from": "2019-01-02", "reached": False, "endOfData": "limit", "firstBarTime": 1546392600}
    make_batch(config.output_root / "day", SYMBOL, capture_extra={"history": history})
    data = results.symbol_data(config, str(config.output_root / "day"), SYMBOL)
    assert data["capture"]["history"] == history


def test_symbol_data_parts_and_series(batch):
    config, out = batch
    data = results.symbol_data(config, str(out), SYMBOL, parts=["labels"], series_last=1)
    assert data["studies"][0]["labels"] == [{"text": "9.5", "time": 2000}]
    assert data["series"] == {
        "columns": ["time", "open", "high", "low", "close"],
        "rows": [["2000", "1.5", "2.5", "1", "2"]],
    }
    assert "identity" not in data


def test_symbol_data_reads_colours_fills_bands_and_what_was_not_exported(batch):
    config, out = batch
    parts = ["plots", "colors", "fills", "bands", "notExported"]
    study = results.symbol_data(config, str(out), SYMBOL, parts=parts)["studies"][0]
    assert study["plots"][0]["lastValid"] == {"time": 2000, "value": 11.25}
    assert study["colors"][0]["runs"] == [[1000, 2000, "rgba(255,0,0,1)"]]
    assert study["fills"][0]["between"] == ["hline_0", "hline_1"]
    assert study["bands"][0]["value"] == 90
    assert study["notExported"] == {"plots": [], "graphics": []}


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
