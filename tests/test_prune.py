import os
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from tradingview_capture_mcp import prune
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import BatchLock, write_json_new

CST = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 14, 19, 0, tzinfo=CST)


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())


def at(day: int, hour: int = 10) -> dict:
    return {"unix": datetime(2026, 10, day, hour, 0, tzinfo=CST).timestamp()}


def make(root, relative, *, started, finished=None, updated=None, tool="tradingview-capture-mcp", size=0):
    out = root / relative
    out.mkdir(parents=True)
    write_json_new(out / "batch.json", {"tool": {"name": tool}, "startedAt": started})
    if finished:
        write_json_new(out / "capture-manifest.json", {"tool": {"name": tool}, "finishedAt": finished})
    # Every batch's own progress file names the folder it was written to.
    write_json_new(
        out / "job.json", {"state": "finished", "outputDir": str(out), "updatedAt": updated or started}
    )
    if size:
        (out / "raw").mkdir()
        (out / "raw" / "image.png").write_bytes(b"x" * size)
    return out


class FakeTrash:
    """Moves folders into a stand-in Trash so a test can see what left the output root."""

    def __init__(self, folder):
        self.folder = folder
        self.folder.mkdir()
        self.moved = []

    def __call__(self, path):
        self.moved.append(path)
        shutil.move(path, self.folder / f"{len(self.moved)}-{path.name}")


def actions(report):
    return [(b["path"], b["day"], b["action"]) for b in report["batches"]]


def test_a_dry_run_lists_older_batches_and_moves_nothing(config):
    root = config.output_root
    make(root, "live/2026-10-14/capture", started=at(14), finished=at(14, 11), size=10)
    make(root, "live/2026-10-13/capture", started=at(13), finished=at(13, 11), size=20)
    make(root, "trials/rehearsal/2026-10-11/capture", started=at(11), size=30)
    make(root, "other/batch", started=at(1), tool="someone-else")  # not this tool's batch: never listed
    (root / "notes").mkdir()
    report = prune.prune(config, now=NOW)
    assert actions(report) == [
        ("live/2026-10-13/capture", "2026-10-13", "wouldTrash"),
        ("live/2026-10-14/capture", "2026-10-14", "keep"),
        ("trials/rehearsal/2026-10-11/capture", "2026-10-11", "wouldTrash"),
    ]
    assert (report["today"], report["keepFrom"], report["apply"]) == ("2026-10-14", "2026-10-14", False)
    assert report["totals"]["wouldTrash"] == 2
    assert report["totals"]["bytesToFree"] >= 50
    assert (root / "live/2026-10-13/capture").is_dir()


def test_apply_moves_older_batches_to_the_trash_and_keeps_today(config, tmp_path):
    root = config.output_root
    today = make(root, "live/2026-10-14/capture", started=at(14))
    older = make(root, "live/2026-10-13/capture", started=at(13))
    trash = FakeTrash(tmp_path / "Trash")
    report = prune.prune(config, apply=True, now=NOW, trash=trash)
    assert trash.moved == [older]
    assert actions(report) == [
        ("live/2026-10-13/capture", "2026-10-13", "trashed"),
        ("live/2026-10-14/capture", "2026-10-14", "keep"),
    ]
    assert today.is_dir() and not older.exists()
    assert report["totals"]["trashed"] == 1


def test_keep_days_keeps_more_days(config):
    make(config.output_root, "a", started=at(13))
    make(config.output_root, "b", started=at(12))
    report = prune.prune(config, keep_days=2, now=NOW)
    assert actions(report) == [("a", "2026-10-13", "keep"), ("b", "2026-10-12", "wouldTrash")]


def test_a_batch_retried_or_finished_today_counts_as_today(config):
    make(config.output_root, "retried", started=at(11), updated=at(14, 9))
    make(config.output_root, "overnight", started=at(13, 23), finished=at(14, 0))
    assert [b["action"] for b in prune.prune(config, now=NOW)["batches"]] == ["keep", "keep"]


def test_a_batch_without_a_readable_date_is_kept(config):
    out = config.output_root / "odd"
    out.mkdir()
    write_json_new(out / "batch.json", {"tool": {"name": "tradingview-capture-mcp"}})
    write_json_new(out / "job.json", {"outputDir": str(out)})
    [entry] = prune.prune(config, now=NOW)["batches"]
    assert (entry["action"], entry["day"], entry["reason"]) == ("keep", None, "no readable date")


def test_a_copy_of_a_batch_is_left_to_whoever_made_it(config):
    # A caller's own copy (cp -R) still names the original folder in its job.json.
    original = make(config.output_root, "live/2026-10-11/capture", started=at(11))
    shutil.copytree(original, config.output_root / "archive" / "copy")
    report = prune.prune(config, now=NOW)
    entries = {b["path"]: b for b in report["batches"]}
    assert entries["live/2026-10-11/capture"]["action"] == "wouldTrash"
    assert entries["archive/copy"]["action"] == "keep"
    assert "copy" in entries["archive/copy"]["reason"]


def test_a_folder_holding_another_batch_is_kept(config):
    make(config.output_root, "live/2026-10-11", started=at(11))
    make(config.output_root, "live/2026-10-11/rerun", started=at(14))
    [entry] = prune.prune(config, now=NOW)["batches"]
    assert (entry["path"], entry["action"]) == ("live/2026-10-11", "keep")
    assert "another batch" in entry["reason"]


def test_a_trash_command_that_hangs_or_fails_to_start_is_a_trash_failure(monkeypatch, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    monkeypatch.setattr(prune, "TRASH_COMMAND", tmp_path / "trash")
    (tmp_path / "trash").write_text("")
    for error in (prune.subprocess.TimeoutExpired(["trash"], 300), OSError("cannot start")):

        def broken(argv, error=error, **kwargs):
            raise error

        monkeypatch.setattr(prune.subprocess, "run", broken)
        with pytest.raises(CaptureError) as err:
            prune.move_to_trash(folder)
        assert err.value.code == "TRASH_FAILED"


def test_symlinks_are_never_followed(config, tmp_path):
    outside = make(tmp_path, "outside", started=at(1))
    os.symlink(outside, config.output_root / "link")
    assert prune.prune(config, now=NOW)["batches"] == []


def test_apply_needs_the_trash_command_and_moves_nothing_without_it(config, monkeypatch, tmp_path):
    older = make(config.output_root, "old", started=at(1))
    monkeypatch.setattr(prune, "TRASH_COMMAND", tmp_path / "no-such-trash")
    with pytest.raises(CaptureError) as err:
        prune.prune(config, apply=True, now=NOW)
    assert err.value.code == "TRASH_UNAVAILABLE"
    assert older.is_dir()


def test_apply_waits_for_a_running_capture(config, tmp_path):
    make(config.output_root, "old", started=at(1))
    with BatchLock(config.output_root), pytest.raises(CaptureError) as err:
        prune.prune(config, apply=True, now=NOW, trash=FakeTrash(tmp_path / "Trash"))
    assert err.value.code == "BATCH_LOCKED"


def test_a_folder_the_trash_refused_is_reported_and_the_rest_go_on(config, tmp_path):
    make(config.output_root, "a", started=at(1))
    make(config.output_root, "b", started=at(2))
    trash = FakeTrash(tmp_path / "Trash")

    def picky(path):
        if path.name == "a":
            raise CaptureError("TRASH_FAILED", "the Trash did not take the folder", {"path": str(path)})
        trash(path)

    report = prune.prune(config, apply=True, now=NOW, trash=picky)
    assert [(b["path"], b["action"]) for b in report["batches"]] == [("a", "failed"), ("b", "trashed")]
    assert report["batches"][0]["error"]["code"] == "TRASH_FAILED"
    assert (report["totals"]["failed"], report["totals"]["trashed"]) == (1, 1)


@pytest.mark.parametrize("keep_days", [0, 400])
def test_keep_days_must_be_sane(config, keep_days):
    with pytest.raises(CaptureError) as err:
        prune.prune(config, keep_days=keep_days, now=NOW)
    assert err.value.code == "INVALID_ARGUMENT"


def test_move_to_trash_runs_the_system_command_with_a_fixed_argument_list(monkeypatch, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs.get("shell", False)))
        shutil.rmtree(folder)  # what the real command does: the folder leaves its place
        return prune.subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(prune, "TRASH_COMMAND", tmp_path / "trash")
    (tmp_path / "trash").write_text("")
    monkeypatch.setattr(prune.subprocess, "run", fake_run)
    prune.move_to_trash(folder)
    assert calls == [([str(tmp_path / "trash"), str(folder)], False)]


def test_move_to_trash_reports_a_folder_that_stayed(monkeypatch, tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    monkeypatch.setattr(prune, "TRASH_COMMAND", tmp_path / "trash")
    (tmp_path / "trash").write_text("")
    monkeypatch.setattr(
        prune.subprocess, "run", lambda argv, **kw: prune.subprocess.CompletedProcess(argv, 1, "", "denied")
    )
    with pytest.raises(CaptureError) as err:
        prune.move_to_trash(folder)
    assert err.value.code == "TRASH_FAILED"
