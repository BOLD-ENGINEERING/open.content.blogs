from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

TargetName = Literal["local", "cloudflare"]
BuildStatus = Literal["success", "failed", "timeout"]
DeployStatus = Literal["success", "failed"]


@dataclass
class BuildRequest:
    repo_url: str
    slug: str
    ref: str = "main"
    content_subdir: str = "."
    site_config: dict[str, Any] = field(default_factory=dict)
    build_id: UUID = field(default_factory=uuid4)
    target: TargetName = "local"

    def __post_init__(self) -> None:
        self.build_id = UUID(str(self.build_id))


@dataclass
class ContentManifest:
    sha: str
    files: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


@dataclass
class BuildResult:
    status: BuildStatus
    sha: str | None
    dist_dir: str | None
    log_path: str
    report: dict[str, Any] | None
    manifest: ContentManifest | None
    duration_seconds: float
    error: str | None = None


@dataclass
class DeployResult:
    status: DeployStatus
    deployment_url: str | None
    alias_url: str | None
    log_path: str
    error: str | None = None


@dataclass
class PipelineResult:
    status: BuildStatus = "failed"
    stages: list[dict[str, Any]] = field(default_factory=list)
    build: BuildResult | None = None
    deploy: DeployResult | None = None
    manifest: ContentManifest | None = None
    alias_url: str | None = None
    error: str | None = None
    site_url: str | None = None
    log_paths: list[str] = field(default_factory=list)
