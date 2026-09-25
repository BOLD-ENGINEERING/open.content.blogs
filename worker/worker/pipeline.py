from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from worker.build import run_build
from worker.config import load_settings
from worker.models import BuildRequest, BuildResult, PipelineResult
from worker.naming import sanitize_branch, validate_slug
from worker.source import SourceError, fetch_content
from worker.targets.base import DeployTarget


def run_pipeline(
    request: BuildRequest,
    target: DeployTarget,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> PipelineResult:
    settings = load_settings()
    directory = settings.build_root / str(request.build_id)
    result = PipelineResult()

    def emit(event: dict[str, Any]) -> None:
        if on_event:
            on_event(dict(event))

    def stage(name: str, action: Callable[[], Any]) -> Any:
        row = {
            "name": name,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": 0.0,
        }
        result.stages.append(row)
        started = time.monotonic()
        emit(row)
        try:
            value = action()
            row["status"] = getattr(value, "status", "success")
            return value
        except SourceError, ValueError, OSError:
            row["status"] = "failed"
            raise
        finally:
            if row["status"] == "running":
                row["status"] = "failed"
            row["ended_at"] = datetime.now(UTC).isoformat()
            row["duration_seconds"] = round(time.monotonic() - started, 6)
            emit(row)

    def site_url() -> str:
        validate_slug(request.slug)
        sanitize_branch(request.ref)
        return target.site_url(request.slug, request.ref)

    try:
        result.site_url = stage("site_url", site_url)
        content, result.manifest = stage("fetch", lambda: fetch_content(request))
        result.build = stage("build", lambda: run_build(request, content, result.site_url))
        result.log_paths.append(result.build.log_path)
        if result.build.status != "success":
            result.status, result.error = result.build.status, result.build.error
            return result
        if not result.build.dist_dir or not result.build.sha:
            raise ValueError("Successful build is missing its output directory or SHA")
        result.deploy = stage(
            "deploy",
            lambda: target.deploy(
                result.build.dist_dir, request.slug, request.ref, result.build.sha
            ),
        )
        result.log_paths.append(result.deploy.log_path)
        result.status = result.deploy.status
        result.alias_url = result.deploy.alias_url
        result.error = result.deploy.error
    except (SourceError, ValueError) as error:
        result.error = str(error)
        if isinstance(error, SourceError):
            result.manifest = error.manifest
    finally:
        directory.mkdir(parents=True, exist_ok=True)
        if result.error:
            log = directory / "pipeline.log"
            log.write_text(result.error + "\n", encoding="utf8")
            result.log_paths.append(str(log))
            if result.build is None and result.stages[-1]["name"] == "fetch":
                result.build = BuildResult(
                    status="failed",
                    sha=result.manifest.sha if result.manifest else None,
                    dist_dir=None,
                    log_path=str(log),
                    report=None,
                    manifest=result.manifest,
                    duration_seconds=result.stages[-1]["duration_seconds"],
                    error=result.error,
                )
        (directory / ".finished").touch()
    return result
