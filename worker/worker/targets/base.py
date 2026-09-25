from __future__ import annotations

from typing import Protocol

from worker.models import DeployResult


class DeployTarget(Protocol):
    def site_url(self, slug: str, branch: str) -> str: ...

    def deploy(self, dist_dir: str, slug: str, branch: str, sha: str) -> DeployResult: ...
