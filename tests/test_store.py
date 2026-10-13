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
