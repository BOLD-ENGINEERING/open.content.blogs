import os
import subprocess

import pytest

from worker.models import BuildRequest
from worker.source import SourceError, fetch_content


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path / "builds"))
    root = tmp_path / "repo"
    root.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Unit",
        "GIT_AUTHOR_EMAIL": "unit@localhost",
        "GIT_COMMITTER_NAME": "Unit",
        "GIT_COMMITTER_EMAIL": "unit@localhost",
        "GIT_AUTHOR_DATE": "2020-02-03T04:05:06Z",
        "GIT_COMMITTER_DATE": "2020-02-03T04:05:06Z",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--initial-branch=main")

    def commit():
        git("add", "--all")
        git("commit", "--allow-empty", "-m", "fixture")

    return root, git, commit


def test_history_unicode_rename_and_single_log(repository, monkeypatch):
    root, git, commit = repository
    (root / "café\tname.md").write_text("undated")
    commit()
    git("mv", "café\tname.md", "renamed.md")
    commit()
    calls = []
    from worker import source

    original = source._git

    def record(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)

    monkeypatch.setattr(source, "_git", record)
    request = BuildRequest(repo_url=root.as_uri(), slug="test")
    content, manifest = fetch_content(request)
    assert manifest.files == ["renamed.md"]
    assert int((content / "renamed.md").stat().st_mtime) == 1580702706
    assert sum("log" in args for args in calls) == 1
    assert not (content.parent / "src").exists()


@pytest.mark.parametrize(
    "kind,count,size,expected",
    [
        ("file", 1, 2 * 1024 * 1024 + 1, "2 MB"),
        ("count", 501, 1, "500"),
        ("total", 11, 2 * 1024 * 1024, "20 MB"),
    ],
)
def test_limits_are_failures(repository, kind, count, size, expected):
    root, _, commit = repository
    for n in range(count):
        (root / f"{n:03}.md").write_bytes(b"x" * size)
    commit()
    request = BuildRequest(repo_url=root.as_uri(), slug="test")
    with pytest.raises(SourceError, match=expected) as error:
        fetch_content(request)
    assert error.value.manifest.skipped
    assert not (root.parent / "builds" / str(request.build_id)).exists()


@pytest.mark.parametrize("subdir", ["../escape", "/etc", "linked/nested", "missing"])
def test_reject_content_path(repository, subdir):
    root, _, commit = repository
    (root / "linked").symlink_to(root.parent)
    commit()
    with pytest.raises(SourceError):
        fetch_content(BuildRequest(repo_url=root.as_uri(), slug="test", content_subdir=subdir))


def test_existing_build_is_not_destroyed(repository):
    root, _, commit = repository
    (root / "a.md").write_text("a")
    commit()
    request = BuildRequest(repo_url=root.as_uri(), slug="test")
    content, _ = fetch_content(request)
    with pytest.raises(FileExistsError):
        fetch_content(request)
    assert (content / "a.md").read_text() == "a"


def test_uuid_cannot_escape():
    with pytest.raises(ValueError):
        BuildRequest(repo_url="file:///tmp/repo", slug="test", build_id="../../escape")
