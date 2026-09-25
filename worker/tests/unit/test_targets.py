import json
import subprocess
from pathlib import Path

import pytest

from worker.targets import cloudflare
from worker.targets.cloudflare import (
    CloudflareConfigurationError,
    CloudflareTarget,
    parse_deployment_url,
)
from worker.targets.local import LocalTarget


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    binary = tmp_path / "node_modules/.bin/wrangler"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "secret-account")
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path / "home"))
    monkeypatch.setattr(cloudflare.shutil, "which", lambda _: "/usr/bin/node")
    return CloudflareTarget(tmp_path)


def test_credentials_missing(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(CloudflareConfigurationError, match="CLOUDFLARE_API_TOKEN"):
        CloudflareTarget()


@pytest.mark.parametrize(
    "slug", ["", "Upper", "-leading", "trailing-", "a_b", "a" * 59, "../escape"]
)
def test_invalid_slug_never_runs(cloud, monkeypatch, slug):
    monkeypatch.setattr(
        cloudflare.subprocess, "run", lambda *a, **kw: pytest.fail("Unexpected process")
    )
    with pytest.raises(ValueError):
        cloud.deploy("dist", slug, "main", "a" * 40)


def test_wrangler_parser():
    output = (Path(__file__).parents[1] / "fixtures/wrangler-deploy-output.txt").read_text()
    assert parse_deployment_url(output) == "https://9f84e3c1.my-blog.pages.dev"
    assert parse_deployment_url("Read https://developers.cloudflare.com/ for help") is None


def test_cloud_commands_secrets_and_existing_project(cloud, tmp_path, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if "create" in args:
            return subprocess.CompletedProcess(
                args, 1, "already exists secret-token", "secret-account"
            )
        return subprocess.CompletedProcess(
            args, 0, "Deployment complete! Take a peek over at https://abc.blog.pages.dev", ""
        )

    monkeypatch.setattr(cloudflare.subprocess, "run", run)
    result = cloud.deploy(str(tmp_path / "dist"), "my--blog", "Feature/Test", "a" * 40)
    assert result.status == "success"
    assert result.alias_url == "https://feature-test.my--blog.pages.dev"
    assert calls[0][0][1:] == [
        "pages",
        "project",
        "create",
        "my--blog",
        "--production-branch",
        "main",
    ]
    assert calls[1][0][1:] == [
        "pages",
        "deploy",
        str(tmp_path / "dist"),
        "--project-name",
        "my--blog",
        "--branch",
        "feature-test",
        "--commit-hash",
        "a" * 40,
        "--commit-dirty=false",
    ]
    for _, kwargs in calls:
        assert kwargs["timeout"] == 300 and kwargs["env"]["CLOUDFLARE_API_TOKEN"] == "secret-token"
        assert not kwargs.get("shell", False)
    log = Path(result.log_path).read_text()
    assert "secret-token" not in log and "secret-account" not in log


@pytest.mark.parametrize("failure", ["project", "deploy", "timeout", "no-url"])
def test_cloud_failures(cloud, tmp_path, monkeypatch, failure):
    def run(args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 300)
        if "create" in args:
            return subprocess.CompletedProcess(
                args, int(failure == "project"), "project result", ""
            )
        return subprocess.CompletedProcess(args, int(failure == "deploy"), "no deployment URL", "")

    monkeypatch.setattr(cloudflare.subprocess, "run", run)
    result = cloud.deploy(str(tmp_path / "dist"), "blog", "main", "a" * 40)
    assert result.status == "failed" and result.error and Path(result.log_path).is_file()


def test_local_history_rollback_and_no_copy_on_rollback(tmp_path, monkeypatch):
    target = LocalTarget(tmp_path / "serve", 8888)
    dist = tmp_path / "dist"
    dist.mkdir()
    for number in range(7):
        (dist / "index.html").write_text(str(number))
        assert (
            target.deploy(str(dist), "blog", "Feature/Test", f"{number:040x}").status == "success"
        )
    history = tmp_path / "serve/blog/.history/feature-test"
    assert {path.name for path in history.iterdir()} == {f"{n:040x}" for n in range(1, 6)}
    monkeypatch.setattr(
        "worker.targets.local.shutil.copytree", lambda *a, **k: pytest.fail("Rollback copied")
    )
    restored = target.rollback("blog", "Feature/Test", f"{2:040x}")
    assert (restored / "index.html").read_text() == "2"
    assert json.loads((restored / ".deploy.json").read_text())["sha"] == f"{2:040x}"
    assert target.site_url("blog", "main") == "http://blog.localhost:8888"
    assert target.site_url("blog", "Feature/Test") == "http://feature-test.blog.localhost:8888"
    with pytest.raises(FileNotFoundError):
        target.rollback("blog", "main", "f" * 40)
    with pytest.raises(ValueError):
        target.rollback("blog", "main", "../../escape")


def test_local_copy_failure_preserves_current(tmp_path, monkeypatch):
    target = LocalTarget(tmp_path / "serve", 8888)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("A")
    target.deploy(str(dist), "blog", "main", "a" * 40)

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("worker.targets.local.shutil.copytree", fail)
    assert target.deploy(str(dist), "blog", "main", "b" * 40).status == "failed"
    assert (tmp_path / "serve/blog/main/index.html").read_text() == "A"
