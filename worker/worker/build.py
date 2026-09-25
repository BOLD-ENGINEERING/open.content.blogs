from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from worker.config import load_settings
from worker.models import BuildRequest, BuildResult, ContentManifest


class BuildConfigurationError(RuntimeError):
    pass


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _template_lock(template: Path, purpose: str) -> Path:
    digest = hashlib.sha256(str(template.resolve()).encode()).hexdigest()
    return Path("/tmp/ocb-template-locks") / f"{digest}-{purpose}.lock"


def _minimal_path() -> str:
    entries = ["/usr/bin", "/bin"]
    for executable in ("node", "pnpm"):
        resolved = shutil.which(executable)
        if resolved:
            entries.insert(0, str(Path(resolved).resolve().parent))
    return os.pathsep.join(dict.fromkeys(entries))


def _base_env(home: Path) -> dict[str, str]:
    return {
        "PATH": _minimal_path(),
        "HOME": str(home),
        "CI": "true",
        "ASTRO_TELEMETRY_DISABLED": "1",
    }


def _ensure_node_dependencies(template_dir: Path, log_path: Path, env: dict[str, str]) -> None:
    if not template_dir.is_dir():
        raise BuildConfigurationError(f"Template directory does not exist: {template_dir}")
    if not shutil.which("pnpm"):
        raise BuildConfigurationError("pnpm is required but was not found on PATH")
    if (template_dir / "node_modules").is_dir():
        return

    with _lock(_template_lock(template_dir, "install")):
        if (template_dir / "node_modules").is_dir():
            return
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile"],
            cwd=template_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        with log_path.open("a", encoding="utf8") as log:
            log.write(result.stdout)
        if result.returncode:
            raise BuildConfigurationError(
                f"pnpm install --frozen-lockfile failed with exit code {result.returncode}; "
                f"see {log_path}"
            )


def _load_manifest(path: Path) -> ContentManifest | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf8"))
    return ContentManifest(
        sha=data["sha"],
        files=data.get("files", []),
        skipped=data.get("skipped", []),
    )


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_build(request: BuildRequest, content_dir: Path, site_url: str) -> BuildResult:
    started = time.monotonic()
    settings = load_settings()
    build_dir = settings.build_root / str(request.build_id)
    build_dir.mkdir(parents=True, exist_ok=True)
    log_path = build_dir / "build.log"
    dist_dir = build_dir / "dist"
    config_path = build_dir / "blog.config.json"
    home_dir = build_dir / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(build_dir / "manifest.json")
    sha = manifest.sha if manifest else None

    if settings.build_timeout <= 0:
        raise BuildConfigurationError("BUILD_TIMEOUT must be greater than zero")
    try:
        config_path.write_text(json.dumps(request.site_config, indent=2), encoding="utf8")
    except (OSError, TypeError, ValueError) as error:
        raise BuildConfigurationError(f"Could not write site configuration: {error}") from error

    env = {
        **_base_env(home_dir),
        "CONTENT_DIR": str(content_dir.resolve()),
        "BLOG_CONFIG": str(config_path.resolve()),
        "BUILD_OUT_DIR": str(dist_dir.resolve()),
        "BUILD_CACHE_DIR": str((build_dir / ".astro").resolve()),
        "SITE_URL": site_url,
    }

    with log_path.open("w", encoding="utf8"):
        pass
    _ensure_node_dependencies(settings.template_dir, log_path, env)
    command = ["pnpm", "build"]
    with log_path.open("a", encoding="utf8", buffering=1) as log:
        log.write("$ pnpm build\n")
        process = subprocess.Popen(
            command,
            cwd=settings.template_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=settings.build_timeout)
        except subprocess.TimeoutExpired:
            _terminate_group(process)
            return BuildResult(
                status="timeout",
                sha=sha,
                dist_dir=str(dist_dir),
                log_path=str(log_path),
                report=None,
                manifest=manifest,
                duration_seconds=round(time.monotonic() - started, 3),
                error=f"Astro build exceeded BUILD_TIMEOUT={settings.build_timeout} seconds",
            )

    if return_code:
        return BuildResult(
            status="failed",
            sha=sha,
            dist_dir=str(dist_dir) if dist_dir.exists() else None,
            log_path=str(log_path),
            report=None,
            manifest=manifest,
            duration_seconds=round(time.monotonic() - started, 3),
            error=f"Astro build exited with code {return_code}",
        )

    try:
        report = json.loads((dist_dir / "_build-report.json").read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        return BuildResult(
            status="failed",
            sha=sha,
            dist_dir=str(dist_dir),
            log_path=str(log_path),
            report=None,
            manifest=manifest,
            duration_seconds=round(time.monotonic() - started, 3),
            error=f"Successful build did not produce a readable _build-report.json: {error}",
        )
    return BuildResult(
        status="success",
        sha=sha,
        dist_dir=str(dist_dir),
        log_path=str(log_path),
        report=report,
        manifest=manifest,
        duration_seconds=round(time.monotonic() - started, 3),
    )
