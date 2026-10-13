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
