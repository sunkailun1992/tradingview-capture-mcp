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
        ["crop", "--output-dir", "{root}/day", "--symbol", SYMBOL, "--box", "1,2,3", "--out", "{root}/c.png"],
        ["status", "--job-id", "c" * 31],
    ],
)
def test_errors_are_json_with_exit_code_2(root, capsys, argv):
    code, payload = run(capsys, *[a.format(root=root) for a in argv])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_ARGUMENT"
