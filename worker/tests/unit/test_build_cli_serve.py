import argparse
import io
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from worker import build, cli
from worker.models import BuildRequest
from worker.serve import LocalSiteHandler


@pytest.fixture
def setup_build(tmp_path, monkeypatch):
    template = tmp_path / "template"
    (template / "node_modules").mkdir(parents=True)
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path / "builds"))
    monkeypatch.setenv("TEMPLATE_DIR", str(template))
    monkeypatch.setattr(build.shutil, "which", lambda name: f"/usr/bin/{name}")
    request = BuildRequest(repo_url="file:///repo", slug="test", site_config={"title": "Test"})
    directory = tmp_path / "builds" / str(request.build_id)
    content = directory / "content"
    content.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps({"sha": "a" * 40, "files": ["a.md"], "skipped": []})
    )
    return request, content, template


@pytest.mark.parametrize(
    "code,report,status", [(0, True, "success"), (2, False, "failed"), (0, False, "failed")]
)
def test_build_contract(setup_build, monkeypatch, code, report, status):
    request, content, template = setup_build
    calls = []

    def popen(args, **kwargs):
        calls.append((args, kwargs))
        dist = content.parent / "dist"
        dist.mkdir()
        if report:
            (dist / "_build-report.json").write_text('{"loaded": 1}')
        return SimpleNamespace(wait=lambda **kwargs: code)

    monkeypatch.setattr(build.subprocess, "Popen", popen)
    result = build.run_build(request, content, "http://test.localhost:8787")
    assert result.status == status and result.sha == "a" * 40
    args, options = calls[0]
    assert args == ["pnpm", "build"] and options["cwd"] == template
    assert options["start_new_session"] and not options.get("shell", False)
    assert options["env"]["CONTENT_DIR"] == str(content)
    assert options["env"]["SITE_URL"] == "http://test.localhost:8787"
    assert "CLOUDFLARE_API_TOKEN" not in options["env"]
    assert json.loads((content.parent / "blog.config.json").read_text()) == request.site_config
    assert Path(result.log_path).is_file()
    if report:
        assert result.report == {"loaded": 1}


def test_timeout_kills_group(setup_build, monkeypatch):
    request, content, _ = setup_build
    calls = []

    class Process:
        pid = 4321

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("pnpm", timeout)
            return -9

    monkeypatch.setattr(build.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(build.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    result = build.run_build(request, content, "http://test.localhost")
    assert result.status == "timeout"
    assert calls == [(4321, build.signal.SIGTERM), (4321, build.signal.SIGKILL)]


def test_missing_template_raises(setup_build, monkeypatch, tmp_path):
    request, content, _ = setup_build
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "missing"))
    with pytest.raises(build.BuildConfigurationError, match="Template directory"):
        build.run_build(request, content, "http://test.localhost")


def test_dependency_install_once(setup_build, monkeypatch):
    _, content, template = setup_build
    (template / "node_modules").rmdir()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        (template / "node_modules").mkdir()
        return subprocess.CompletedProcess(args, 0, "installed")

    monkeypatch.setattr(build.subprocess, "run", run)
    for _ in range(2):
        build._ensure_node_dependencies(template, content.parent / "build.log", {})
    assert calls == [["pnpm", "install", "--frozen-lockfile"]]


def test_locks_shared_across_build_roots(tmp_path):
    assert build._template_lock(tmp_path, "build") == build._template_lock(tmp_path / ".", "build")
    assert build._template_lock(tmp_path, "build") != build._template_lock(
        tmp_path / "other", "build"
    )


def test_clean_finished_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path))
    for name in ("old", "recent", "active"):
        (tmp_path / name).mkdir()
    for name in ("old", "recent"):
        (tmp_path / name / ".finished").touch()
    os.utime(tmp_path / "old/.finished", (0, 0))
    assert cli._clean(argparse.Namespace(older_than=86400)) == 0
    assert {p.name for p in tmp_path.iterdir()} == {"recent", "active"}
    assert cli._duration("1d2h3m4s") == 93784
    with pytest.raises(argparse.ArgumentTypeError):
        cli._duration("24")
    assert cli._node_supported("v22.12.0") and not cli._node_supported("v22.11.0")


def test_http_routes_mime_404_and_traversal(tmp_path):
    site = tmp_path / "blog/main"
    site.mkdir(parents=True)
    (site / "index.html").write_text("INDEX")
    (site / "404.html").write_text("BRANDED 404")
    (site / "style.css").write_text("body {}")
    (site / ".deploy.json").write_text("SECRET")
    handler = object.__new__(LocalSiteHandler)
    handler.serve_root = tmp_path
    handler.headers = {"Host": "blog.localhost:8787"}
    result = []
    handler._send_bytes = lambda *args, **kwargs: result.append(args)
    for path, status, body in [
        ("/", 200, b"INDEX"),
        ("/missing", 404, b"BRANDED 404"),
        ("/../etc/passwd", 404, b"BRANDED 404"),
        ("/.deploy.json", 404, b"BRANDED 404"),
    ]:
        handler.path = path
        handler._serve(False)
        assert result[-1][:2] == (status, body)
    handler.path = "/style.css"
    handler._serve(False)
    assert result[-1][2] == "text/css; charset=utf-8"
    handler.headers = {"Host": "unknown.example"}
    handler._serve(False)
    assert result[-1][0] == 404
    assert handler._route("staging.blog.localhost") == ("blog", "staging")
    handler.wfile = io.BytesIO()
    headers = {}
    handler.send_response = lambda status: None
    handler.send_header = lambda key, value: headers.update({key: value})
    handler.end_headers = lambda: None
    LocalSiteHandler._send_bytes(handler, 200, b"body", "text/plain", True)
    assert headers["Cache-Control"] == "no-store" and handler.wfile.getvalue() == b""
