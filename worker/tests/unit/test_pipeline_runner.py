from pathlib import Path
from unittest.mock import Mock

import pytest

from worker import pipeline
from worker.build import BuildConfigurationError
from worker.models import BuildRequest, BuildResult, ContentManifest, DeployResult
from worker.source import SourceError


@pytest.mark.parametrize(
    "outcome,stages",
    [
        ("success", 4),
        ("site_url", 1),
        ("fetch", 2),
        ("failed", 3),
        ("timeout", 3),
        ("deploy", 4),
        ("deploy-validation", 4),
        ("configuration", 3),
    ],
)
def test_terminal_paths(tmp_path, monkeypatch, outcome, stages):
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path))
    request = BuildRequest(repo_url="file:///repo", slug="blog")
    directory = tmp_path / str(request.build_id)
    manifest = ContentManifest("a" * 40)
    fetch = Mock(return_value=(directory / "content", manifest))
    build = Mock(
        return_value=BuildResult(
            status=outcome if outcome in {"failed", "timeout"} else "success",
            sha=manifest.sha,
            dist_dir=str(directory / "dist"),
            log_path=str(directory / "build.log"),
            report={},
            manifest=manifest,
            duration_seconds=1,
            error="compilation error" if outcome in {"failed", "timeout"} else None,
        )
    )
    target = Mock()
    target.site_url.return_value = "http://blog.localhost"
    target.deploy.return_value = DeployResult(
        "failed" if outcome == "deploy" else "success",
        "http://blog.localhost",
        "http://blog.localhost",
        str(directory / "deploy.log"),
        "deployment error" if outcome == "deploy" else None,
    )
    if outcome == "site_url":
        target.site_url.side_effect = ValueError("invalid site")
    if outcome == "fetch":
        fetch.side_effect = SourceError("invalid ref", manifest)
    if outcome == "deploy-validation":
        target.deploy.side_effect = ValueError("invalid deployment")
    if outcome == "configuration":
        build.side_effect = BuildConfigurationError("missing template")
    monkeypatch.setattr(pipeline, "fetch_content", fetch)
    monkeypatch.setattr(pipeline, "run_build", build)
    events = []
    if outcome == "configuration":
        with pytest.raises(BuildConfigurationError, match="missing template"):
            pipeline.run_pipeline(request, target, events.append)
    else:
        result = pipeline.run_pipeline(request, target, events.append)
        assert result.status == (
            "success" if outcome == "success" else "timeout" if outcome == "timeout" else "failed"
        )
        assert len(result.stages) == stages
        assert result.error if outcome != "success" else result.alias_url == "http://blog.localhost"
        assert all(row["ended_at"] >= row["started_at"] for row in result.stages)
        if outcome == "fetch":
            assert result.manifest == manifest
            assert Path(result.build.log_path).read_text() == "invalid ref\n"
        if outcome in {"failed", "timeout", "fetch", "site_url"}:
            target.deploy.assert_not_called()
        if outcome == "site_url":
            fetch.assert_not_called()
    assert (directory / ".finished").is_file()
    assert len(events) == stages * 2
    assert all(row["status"] == "running" and row["ended_at"] is None for row in events[::2])
    assert all(row["status"] != "running" and row["ended_at"] for row in events[1::2])


def test_invalid_slug_before_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_ROOT", str(tmp_path))
    fetch = Mock()
    monkeypatch.setattr(pipeline, "fetch_content", fetch)
    result = pipeline.run_pipeline(BuildRequest(repo_url="file:///repo", slug="../x"), Mock())
    assert result.status == "failed" and "slug" in result.error
    fetch.assert_not_called()
