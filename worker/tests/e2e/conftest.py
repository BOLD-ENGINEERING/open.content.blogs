from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "worker"


def command(args, cwd, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


class Repository:
    def __init__(self, root):
        self.bare = root / "remote.git"
        self.work = root / "work"
        root.mkdir(parents=True)
        command(["git", "init", "--bare", "--initial-branch=main", str(self.bare)], root)
        command(["git", "clone", self.bare.as_uri(), str(self.work)], root)
        self.git("config", "user.email", "fixture@localhost")
        self.git("config", "user.name", "Fixture Author")

    def git(self, *args, date=None):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return command(["git", *args], self.work, env)

    def write(self, name, body):
        target = self.work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf8")

    def commit(self, date="2024-01-01T12:00:00+00:00"):
        self.git("add", "--all")
        self.git("commit", "--allow-empty", "-m", "fixture change", date=date)
        self.git("push", "origin", "HEAD")
        return self.git("rev-parse", "HEAD")


def post(number, tag=None):
    return (
        f"---\ntitle: Post {number:02d}\ndescription: A useful description for post {number}.\n"
        f"date: 2024-02-{1 if number < 6 else 2:02d}\ntags: [{tag or f'tag-{number % 4}'}]\n---\n\n"
        f"Readable prose for post {number}. This local fixture exercises publishing.\n"
    )


class Harness:
    def __init__(self, root, port):
        self.root, self.port = root, port
        self.build_root, self.serve_root = root / "builds", root / "serve"
        self.env = {
            **os.environ,
            "BUILD_ROOT": str(self.build_root),
            "SERVE_ROOT": str(self.serve_root),
            "SERVE_PORT": str(port),
            "TEMPLATE_DIR": str(ROOT / "web"),
            "ASTRO_TELEMETRY_DISABLED": "1",
            "OCB_E2E_SESSION": str(root),
        }
        self.sequence = 0

    def repo(self, name):
        self.sequence += 1
        return Repository(self.root / "repos" / f"{name}-{self.sequence}")

    def cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-m", "worker", *args],
            cwd=WORKER,
            env={**self.env, **(env or {})},
            capture_output=True,
            text=True,
        )

    def build(self, repo, slug, ref="main", extra=(), success=True, env=None):
        result = self.cli(
            "build",
            "--repo",
            repo.bare.as_uri(),
            "--slug",
            slug,
            "--ref",
            ref,
            "--json",
            *extra,
            env=env,
        )
        assert result.returncode == (0 if success else 1), result.stdout + result.stderr
        try:
            data = json.loads(result.stdout)
        except ValueError:
            pytest.fail(result.stdout + result.stderr)
        if success:
            assert data["build"]["status"] == "success", data
            assert data["deploy"]["status"] == "success", data
        return data

    def get(self, url, path="/"):
        address = urlsplit(url)
        request = Request(f"http://127.0.0.1:{self.port}{path}", headers={"Host": address.netloc})
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode("utf8"), response.headers


@pytest.fixture(scope="session")
def harness(tmp_path_factory):
    configured = os.environ.get("OCB_E2E_ROOT")
    root = Path(configured) if configured else tmp_path_factory.mktemp("ocb-e2e")
    root.mkdir(parents=True, exist_ok=True)
    assert not (root / "builds").exists() and not (root / "serve").exists(), (
        "Use a clean OCB_E2E_ROOT"
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    harness = Harness(root, port)
    log = (root / "serve.log").open("w")
    process = subprocess.Popen(
        [sys.executable, "-m", "worker", "serve", "--port", str(port)],
        cwd=WORKER,
        env=harness.env,
        stdout=log,
        stderr=log,
    )
    try:
        for _ in range(100):
            try:
                if harness.get(f"http://localhost:{port}")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("Server did not start")
        yield harness
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()
        leftovers = []
        marker = f"OCB_E2E_SESSION={root}".encode()
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                environment = (entry / "environ").read_bytes().split(b"\0")
                cmd = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            owned = marker in environment or any(
                value.startswith(f"BUILD_OUT_DIR={harness.build_root}/".encode())
                for value in environment
            )
            if owned and any(name in cmd for name in (b"node", b"pnpm", b"chromium")):
                leftovers.append((entry.name, cmd))
        assert not leftovers, leftovers


@pytest.fixture(scope="session")
def happy(harness):
    repo = harness.repo("happy")
    for n in range(12):
        repo.write(f"post-{n:02d}.md", post(n))
    repo.commit()
    return repo, harness.build(repo, "happy")


@pytest.fixture(scope="session")
def edges(harness):
    repo = harness.repo("edges")
    for source in (ROOT / "test-fixtures/sample-content").iterdir():
        if source.is_file():
            shutil.copyfile(source, repo.work / source.name)
    repo.commit()
    return repo, harness.build(repo, "edges")


@pytest.fixture(scope="session")
def empty(harness):
    repo = harness.repo("empty")
    repo.write("README.txt", "No markdown content")
    repo.commit()
    return repo, harness.build(repo, "empty")


@pytest.fixture(scope="session")
def browser(harness):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        bundled = Path(playwright.chromium.executable_path)
        executable = str(bundled) if bundled.is_file() else shutil.which("chromium")
        assert executable, "Install Playwright Chromium or system chromium"
        browser = playwright.chromium.launch(
            executable_path=executable,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            env=harness.env,
        )
        yield browser
        browser.close()


def snapshot(root):
    result = {}
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        digest = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() and not path.is_symlink()
            else None
        )
        result[str(path.relative_to(root))] = [
            info.st_size,
            info.st_mtime_ns,
            digest,
            os.readlink(path) if path.is_symlink() else None,
        ]
    return result
