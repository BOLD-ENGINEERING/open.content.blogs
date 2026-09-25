from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from worker.build import _lock
from worker.config import load_settings
from worker.models import DeployResult

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def sanitize_branch(branch: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]", "-", branch.lower())
    return sanitized or "branch"


def validate_slug(slug: str) -> None:
    if len(slug) > 58 or not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            "slug must be 1-58 lowercase letters, digits or hyphens, without edge hyphens"
        )


class LocalTarget:
    def __init__(self, serve_root: Path | None = None, port: int | None = None) -> None:
        settings = load_settings()
        self.serve_root = (serve_root or settings.serve_root).resolve()
        self.port = port or settings.serve_port

    def site_url(self, slug: str, branch: str) -> str:
        validate_slug(slug)
        branch_name = sanitize_branch(branch)
        host = f"{slug}.localhost" if branch_name == "main" else f"{branch_name}.{slug}.localhost"
        return f"http://{host}:{self.port}"

    def _deployment_path(self, slug: str, branch: str) -> Path:
        validate_slug(slug)
        return self.serve_root / slug / sanitize_branch(branch)

    def deploy(self, dist_dir: str, slug: str, branch: str, sha: str) -> DeployResult:
        _metadata_sha({"sha": sha})
        destination = self._deployment_path(slug, branch)
        with _lock(destination.parent / f".{destination.name}.lock"):
            return self._deploy(dist_dir, slug, branch, sha)

    def _deploy(self, dist_dir: str, slug: str, branch: str, sha: str) -> DeployResult:
        destination = self._deployment_path(slug, branch)
        log_path = Path(dist_dir).parent / "deploy.log"
        started = datetime.now(UTC)
        temporary: Path | None = None
        old_history: Path | None = None
        try:
            source = Path(dist_dir).resolve(strict=True)
            if not source.is_dir():
                raise ValueError(f"Build output is not a directory: {dist_dir}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(
                tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
            )
            shutil.rmtree(temporary)
            shutil.copytree(source, temporary)
            (temporary / ".deploy.json").write_text(
                json.dumps({"sha": sha, "deployed_at": started.isoformat()}, indent=2),
                encoding="utf8",
            )

            if destination.exists():
                old_metadata = _read_deploy_metadata(destination)
                old_sha = _metadata_sha(old_metadata)
                history = self.serve_root / slug / ".history" / sanitize_branch(branch)
                history.mkdir(parents=True, exist_ok=True)
                old_history = history / old_sha
                if old_history.exists():
                    shutil.rmtree(old_history)
                _exchange(temporary, destination)
                os.replace(temporary, old_history)
                _trim_history(history, keep=5)
            else:
                os.replace(temporary, destination)
            temporary = None
            log_path.write_text(
                f"Deployed {slug} branch {sanitize_branch(branch)} at {sha}\n", encoding="utf8"
            )
            url = self.site_url(slug, branch)
            return DeployResult(
                status="success",
                deployment_url=url,
                alias_url=url,
                log_path=str(log_path),
            )
        except (OSError, ValueError, shutil.Error) as error:
            log_path.write_text(f"Local deployment failed: {error}\n", encoding="utf8")
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error=str(error),
            )
        finally:
            if temporary and temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)

    def rollback(self, slug: str, branch: str, sha: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{40,64}", sha) is None:
            raise ValueError("rollback sha must be a full lowercase Git object ID")
        destination = self._deployment_path(slug, branch)
        with _lock(destination.parent / f".{destination.name}.lock"):
            history = self.serve_root / slug / ".history" / sanitize_branch(branch)
            selected = history / sha
            if not selected.is_dir():
                raise FileNotFoundError(
                    f"Deployment {sha} is not present in history for {slug}/{branch}"
                )
            if destination.exists():
                old_sha = _metadata_sha(_read_deploy_metadata(destination))
                if old_sha == sha:
                    return destination
                current_history = history / old_sha
                if current_history.exists():
                    shutil.rmtree(current_history)
                _exchange(selected, destination)
                os.replace(selected, current_history)
            else:
                os.replace(selected, destination)
            _trim_history(history, keep=5)
            return destination


def _metadata_sha(metadata: dict[str, object]) -> str:
    sha = str(metadata.get("sha", ""))
    if re.fullmatch(r"[0-9a-f]{40,64}", sha) is None:
        raise ValueError("Deployment metadata has an invalid SHA")
    return sha


def _exchange(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(left), -100, os.fsencode(right), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _read_deploy_metadata(path: Path) -> dict[str, object]:
    metadata = path / ".deploy.json"
    try:
        value = json.loads(metadata.read_text(encoding="utf8"))
    except OSError, json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _trim_history(history: Path, keep: int) -> None:
    entries = [path for path in history.iterdir() if path.is_dir()]
    entries.sort(
        key=lambda path: str(_read_deploy_metadata(path).get("deployed_at", "")),
        reverse=True,
    )
    for expired in entries[keep:]:
        shutil.rmtree(expired)
