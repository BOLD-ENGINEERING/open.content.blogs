import errno
import json
from unittest.mock import Mock

import pytest

from worker import cli
from worker.naming import sanitize_branch, validate_slug
from worker.targets import local


@pytest.mark.parametrize("slug", ["../x", "a/b", ".history", "", "a" * 59, "UPPER", "-a", "a-"])
def test_invalid_slugs(slug, monkeypatch, tmp_path):
    with pytest.raises(ValueError):
        validate_slug(slug)
    target = local.LocalTarget(tmp_path)
    with pytest.raises(ValueError):
        target.site_url(slug, "main")
    with pytest.raises(ValueError):
        target.deploy("missing", slug, "main", "a" * 40)
    load = Mock(side_effect=AssertionError("work began before validation"))
    monkeypatch.setattr(cli, "load_settings", load)
    assert cli._build(Mock(slug=slug)) == 1
    load.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("Feature/Test", "feature-test"),
        ("Release.V1", "release-v1"),
        ("UPPER", "upper"),
        ("/a/", "a"),
    ],
)
def test_branches(branch, expected):
    assert sanitize_branch(branch) == expected


@pytest.mark.parametrize("branch", ["", "...", "/", "---"])
def test_empty_branch(branch):
    with pytest.raises(ValueError):
        sanitize_branch(branch)


@pytest.mark.parametrize("force", [False, True])
def test_exchange_paths(tmp_path, monkeypatch, force):
    def native(left, right):
        temporary = left.parent / "swap"
        left.rename(temporary)
        right.rename(left)
        temporary.rename(right)

    exchange = Mock(side_effect=native)
    monkeypatch.setattr(local, "_native_exchange", exchange)
    monkeypatch.setenv("OCB_FORCE_RENAME_FALLBACK", "1" if force else "0")
    local._ACTIVATION_MODES.clear()
    left, right = tmp_path / "new", tmp_path / "live"
    for path, sha in ((left, "a" * 40), (right, "b" * 40)):
        path.mkdir()
        (path / ".deploy.json").write_text(json.dumps({"sha": sha}))
    mode = local.activation_mode(tmp_path)
    assert mode == ("rename-fallback" if force else "rename-exchange")
    local._exchange(left, right)
    assert local._read_deploy_metadata(right)["sha"] == "a" * 40
    assert local._read_deploy_metadata(left)["sha"] == "b" * 40
    assert len(list(tmp_path.iterdir())) == 2
    assert exchange.call_count == (0 if force else 2)
    local._ACTIVATION_MODES.clear()


@pytest.mark.parametrize("error", [errno.ENOSYS, errno.ENOTSUP, errno.EINVAL])
def test_unavailable_native(tmp_path, monkeypatch, error):
    monkeypatch.delenv("OCB_FORCE_RENAME_FALLBACK", raising=False)
    local._ACTIVATION_MODES.clear()
    monkeypatch.setattr(local, "_native_exchange", Mock(side_effect=OSError(error, "unsupported")))
    assert local.activation_mode(tmp_path) == "rename-fallback"
    local._ACTIVATION_MODES.clear()


def test_fallback_restores_live_on_activation_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("OCB_FORCE_RENAME_FALLBACK", "1")
    live = tmp_path / "live"
    live.mkdir()
    (live / ".deploy.json").write_text(json.dumps({"sha": "b" * 40}))
    with pytest.raises(FileNotFoundError):
        local._exchange(tmp_path / "missing", live)
    assert local._read_deploy_metadata(live)["sha"] == "b" * 40
    assert list(tmp_path.iterdir()) == [live]


def test_missing_libc_symbol(monkeypatch):
    local._rename_function.cache_clear()
    monkeypatch.setattr(local.ctypes, "CDLL", lambda *args, **kwargs: object())
    assert local._rename_function() is None
    local._rename_function.cache_clear()


def test_native_errors_are_not_hidden(tmp_path, monkeypatch):
    monkeypatch.delenv("OCB_FORCE_RENAME_FALLBACK", raising=False)
    local._ACTIVATION_MODES.clear()
    monkeypatch.setattr(
        local, "_native_exchange", Mock(side_effect=PermissionError(errno.EACCES, "denied"))
    )
    with pytest.raises(PermissionError):
        local.activation_mode(tmp_path)
    assert not local._ACTIVATION_MODES
