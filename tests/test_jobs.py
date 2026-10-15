import dataclasses
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


@pytest.fixture(autouse=True)
def tradingview_closed(monkeypatch):
    """Keep the tests independent of whether TradingView happens to be open on this machine."""
    monkeypatch.setattr(jobs, "running_pids", lambda: [])


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


def test_start_fails_at_once_while_tradingview_is_open(config, stub_python, monkeypatch):
    monkeypatch.setattr(jobs, "running_pids", lambda: [4242])
    with pytest.raises(CaptureError) as err:
        jobs.start(config, request(config), python=stub_python)
    assert (err.value.code, err.value.detail) == ("TV_ALREADY_RUNNING", {"pids": [4242]})
    # Nothing was created, so the same capture_start works once TradingView is quit.
    assert not (config.output_root / "batch").exists()
    assert not list(config.output_root.glob(f"{jobs.JOBS_DIR}/*"))


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
    assert rebuilt.history_from is None  # batches written before history_from existed


def test_a_retry_keeps_the_batch_history_date(config):
    out = config.output_root / "batch"
    out.mkdir()
    original = dataclasses.replace(request(config), history_from="2019-01-02")
    write_json_new(out / "batch.json", {"request": original.to_dict()})
    assert jobs.retry_request(config, str(out)).history_from == "2019-01-02"


def test_retry_needs_a_batch_with_something_left(config, stub_python):
    out = config.output_root / "batch"
    out.mkdir()
    with pytest.raises(CaptureError) as err:
        jobs.retry(config, str(out), python=stub_python)
    assert err.value.code == "NOT_FOUND"
    write_json_new(out / "batch.json", {"request": request(config).to_dict()})
    assert jobs.retry(config, str(out), python=stub_python)["jobId"]  # no manifest yet: resumable
    write_json_new(
        out / "capture-manifest.json", {"symbols": [{"symbol": "BINANCE:AAAUSDT.P", "status": "ok"}]}
    )
    with pytest.raises(CaptureError) as err:
        jobs.retry(config, str(out), python=stub_python)
    assert err.value.code == "NOT_FOUND"
    assert "every symbol already has a capture" in err.value.message
