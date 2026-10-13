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
