import json

import pytest
from helpers import make_batch, write_config

from tradingview_capture_mcp import jobs
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


def test_prune_lists_without_moving_anything(root, capsys):
    code, payload = run(capsys, "prune")
    assert code == 0
    assert (payload["apply"], payload["keepDays"], payload["batches"]) == (False, 1, [])


@pytest.mark.parametrize(
    "argv",
    [
        ["capture", "--layout", "../bad", "--symbol", SYMBOL, "--output-dir", "{root}/x"],
        ["crop", "--output-dir", "{root}/day", "--symbol", SYMBOL, "--box", "1,2,3", "--out", "{root}/c.png"],
        ["status", "--job-id", "c" * 31],
        [
            "capture",
            "--layout",
            "Layout01",
            "--symbol",
            SYMBOL,
            "--output-dir",
            "{root}/x",
            "--history-from",
            "1/2/2019",
        ],
    ],
)
def test_errors_are_json_with_exit_code_2(root, capsys, argv):
    code, payload = run(capsys, *[a.format(root=root) for a in argv])
    assert code == 2
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_capture_takes_history_from(root, capsys, monkeypatch):
    seen = []
    monkeypatch.setattr(jobs, "start", lambda config, request: seen.append(request) or {"jobId": "j"})
    argv = ["capture", "--layout", "Layout01", "--symbol", SYMBOL, "--output-dir", str(root / "x")]
    run(capsys, *argv, "--timeframe", "60", "--history-from", "2019-01-02")
    run(capsys, *argv)
    assert [(r.timeframe, r.history_from) for r in seen] == [("60", "2019-01-02"), ("1D", None)]
