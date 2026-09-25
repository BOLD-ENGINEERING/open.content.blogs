from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from worker.models import DeployResult
from worker.naming import sanitize_branch, validate_slug

DEPLOY_TIMEOUT = 300
URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?")


class CloudflareConfigurationError(RuntimeError):
    pass


def parse_deployment_url(output: str) -> str | None:
    match = re.search(
        r"Deployment complete! Take a peek over at\s+(" + URL_PATTERN.pattern + r")",
        output,
    )
    if not match:
        return None
    return match.group(1 if match.lastindex else 0).rstrip(".,!;)")


class CloudflareTarget:
    def __init__(self, worker_root: Path | None = None) -> None:
        root = worker_root or Path(__file__).resolve().parents[2]
        self.wrangler = root / "node_modules" / ".bin" / "wrangler"
        self.token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        missing = [
            name
            for name, value in (
                ("CLOUDFLARE_API_TOKEN", self.token),
                ("CLOUDFLARE_ACCOUNT_ID", self.account_id),
            )
            if not value
        ]
        if missing:
            raise CloudflareConfigurationError(
                "Missing required Cloudflare environment variables: " + ", ".join(missing)
            )
        if not self.wrangler.is_file():
            raise CloudflareConfigurationError(f"Wrangler is not installed at {self.wrangler}")

    def site_url(self, slug: str, branch: str) -> str:
        validate_slug(slug)
        branch_name = sanitize_branch(branch)
        host = f"{slug}.pages.dev" if branch_name == "main" else f"{branch_name}.{slug}.pages.dev"
        return f"https://{host}"

    def _environment(self) -> dict[str, str]:
        node = shutil.which("node")
        node_dir = str(Path(node).resolve().parent) if node else ""
        return {
            "PATH": os.pathsep.join(part for part in (node_dir, os.defpath) if part),
            "HOME": str(Path(os.environ.get("BUILD_ROOT", "/tmp/ocb-builds")).resolve()),
            "CI": "true",
            "WRANGLER_SEND_METRICS": "false",
            "CLOUDFLARE_API_TOKEN": self.token,
            "CLOUDFLARE_ACCOUNT_ID": self.account_id,
        }

    def _safe_output(self, output: str) -> str:
        return output.replace(self.token, "[REDACTED]").replace(self.account_id, "[REDACTED]")

    def deploy(self, dist_dir: str, slug: str, branch: str, sha: str) -> DeployResult:
        validate_slug(slug)
        sanitize_branch(branch)
        log_path = Path(dist_dir).parent / "deploy.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        environment = self._environment()
        (Path(environment["HOME"]) / ".config").mkdir(parents=True, exist_ok=True)
        try:
            project = subprocess.run(
                [
                    str(self.wrangler),
                    "pages",
                    "project",
                    "create",
                    slug,
                    "--production-branch",
                    "main",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=DEPLOY_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            log_path.write_text(
                f"Wrangler project setup failed: {self._safe_output(str(error))}\n", encoding="utf8"
            )
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error=self._safe_output(str(error)),
            )
        project_output = self._safe_output(project.stdout + project.stderr)
        lines.append(project_output)
        if project.returncode and "already exists" not in project_output.lower():
            log_path.write_text("".join(lines), encoding="utf8")
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error=f"Could not ensure Cloudflare Pages project {slug}",
            )

        try:
            result = subprocess.run(
                [
                    str(self.wrangler),
                    "pages",
                    "deploy",
                    str(Path(dist_dir).resolve()),
                    "--project-name",
                    slug,
                    "--branch",
                    sanitize_branch(branch),
                    "--commit-hash",
                    sha,
                    "--commit-dirty=false",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=DEPLOY_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            log_path.write_text("\n".join(lines + [self._safe_output(str(error))]), encoding="utf8")
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error=self._safe_output(str(error)),
            )
        output = self._safe_output(result.stdout + result.stderr)
        lines.append(output)
        log_path.write_text("\n".join(lines), encoding="utf8")
        if result.returncode:
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error=f"Wrangler deploy exited with code {result.returncode}",
            )
        deployment_url = parse_deployment_url(output)
        if not deployment_url:
            return DeployResult(
                status="failed",
                deployment_url=None,
                alias_url=None,
                log_path=str(log_path),
                error="Wrangler completed without a deployment URL in its output",
            )
        return DeployResult(
            status="success",
            deployment_url=deployment_url,
            alias_url=self.site_url(slug, branch),
            log_path=str(log_path),
        )
