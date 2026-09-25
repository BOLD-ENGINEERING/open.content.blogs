from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from worker.build import BuildConfigurationError, run_build
from worker.config import Settings, load_settings
from worker.models import BuildRequest, BuildResult
from worker.serve import serve
from worker.source import SourceError, fetch_content
from worker.targets.base import DeployTarget
from worker.targets.cloudflare import CloudflareTarget
from worker.targets.local import LocalTarget

logger = logging.getLogger("worker")


def _target(name: str) -> DeployTarget:
    if name == "local":
        return LocalTarget()
    if name == "cloudflare":
        return CloudflareTarget()
    raise ValueError(f"Unsupported deployment target: {name}")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, default=_json_default))


def _tail(path: str | None, error: str | None) -> str:
    if path:
        try:
            lines = Path(path).read_text(encoding="utf8", errors="replace").splitlines()
        except OSError:
            lines = []
        if lines:
            return "\n".join(lines[-40:])
    return error or "The operation failed without a log."


def _mark_finished(build_id: str) -> None:
    settings = load_settings()
    build_dir = settings.build_root / build_id
    if build_dir.is_dir():
        (build_dir / ".finished").touch()


def _build(args: argparse.Namespace) -> int:
    settings = load_settings()
    template_config = settings.template_dir / "blog.config.json"
    try:
        site_config = json.loads(template_config.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Cannot read template blog.config.json: {error}", file=sys.stderr)
        return 1
    for key, value in (
        ("title", args.title),
        ("author", args.author),
        ("description", args.description),
    ):
        if value is not None:
            site_config[key] = value

    request = BuildRequest(
        repo_url=args.repo,
        ref=args.ref,
        content_subdir=args.subdir,
        slug=args.slug,
        site_config=site_config,
        target=args.target,
    )
    try:
        target = _target(args.target)
        site_url = target.site_url(request.slug, request.ref)
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1

    logging.debug("Fetching content for %s at ref %s", request.slug, request.ref)
    fetch_started = time.monotonic()
    try:
        content_dir, manifest = fetch_content(request)
    except SourceError as error:
        duration = round(time.monotonic() - fetch_started, 3)
        build_result = BuildResult(
            status="failed",
            sha=error.manifest.sha if error.manifest else None,
            dist_dir=None,
            log_path="",
            report=None,
            manifest=error.manifest,
            duration_seconds=duration,
            error=str(error),
        )
        if args.json:
            _print_json(
                {
                    "site_url": site_url,
                    "fetch_duration_seconds": duration,
                    "build": asdict(build_result),
                    "deploy": None,
                }
            )
        else:
            print(f"fetch failed ({duration:.3f}s)", file=sys.stderr)
            print(_tail(None, str(error)), file=sys.stderr)
        return 1
    fetch_duration = round(time.monotonic() - fetch_started, 3)
    if not args.json:
        print(f"fetch success ({fetch_duration:.3f}s, {manifest.sha})")

    logging.debug("Building %s from %s", request.slug, manifest.sha)
    try:
        build_result = run_build(request, content_dir, site_url)
    except (BuildConfigurationError, OSError, ValueError) as error:
        _mark_finished(str(request.build_id))
        if args.json:
            _print_json(
                {
                    "site_url": site_url,
                    "fetch_duration_seconds": fetch_duration,
                    "manifest": asdict(manifest),
                    "build": {
                        "status": "failed",
                        "sha": manifest.sha,
                        "dist_dir": None,
                        "log_path": str(settings.build_root / str(request.build_id) / "build.log"),
                        "report": None,
                        "manifest": asdict(manifest),
                        "duration_seconds": 0,
                        "error": str(error),
                    },
                    "deploy": None,
                }
            )
        else:
            print("build failed", file=sys.stderr)
            print(
                _tail(str(settings.build_root / str(request.build_id) / "build.log"), str(error)),
                file=sys.stderr,
            )
        return 1

    if build_result.status != "success" or not build_result.dist_dir or not build_result.sha:
        _mark_finished(str(request.build_id))
        if args.json:
            _print_json(
                {
                    "site_url": site_url,
                    "fetch_duration_seconds": fetch_duration,
                    "build": asdict(build_result),
                    "deploy": None,
                }
            )
        else:
            print(
                f"build {build_result.status} ({build_result.duration_seconds:.3f}s)",
                file=sys.stderr,
            )
            print(build_result.error, file=sys.stderr)
            print(_tail(build_result.log_path, build_result.error), file=sys.stderr)
        return 1

    if not args.json:
        print(f"build success ({build_result.duration_seconds:.3f}s)")
    deploy_started = time.monotonic()
    deploy_result = target.deploy(
        build_result.dist_dir, request.slug, request.ref, build_result.sha
    )
    deploy_duration = round(time.monotonic() - deploy_started, 3)
    _mark_finished(str(request.build_id))
    if args.json:
        _print_json(
            {
                "site_url": site_url,
                "fetch_duration_seconds": fetch_duration,
                "build": asdict(build_result),
                "deploy": asdict(deploy_result),
                "deploy_duration_seconds": deploy_duration,
            }
        )
    else:
        print(f"deploy {deploy_result.status} ({deploy_duration:.3f}s)")
        if deploy_result.status == "success" and deploy_result.alias_url:
            print(deploy_result.alias_url)
        else:
            print(_tail(deploy_result.log_path, deploy_result.error), file=sys.stderr)
    return 0 if deploy_result.status == "success" else 1


def _version(command: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False, timeout=10
    )
    if result.returncode:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def _node_supported(version: str | None) -> bool:
    if not version:
        return False
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    return bool(match and tuple(map(int, match.groups())) >= (22, 12, 0))


def _writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".doctor-{os.getpid()}"
        probe.write_text("ok", encoding="utf8")
        probe.unlink()
        return True
    except OSError:
        return False


def _doctor(settings: Settings) -> int:
    checks: list[tuple[str, bool, str]] = []
    git = _version("git")
    checks.append(("git", git is not None, git or "MISSING"))
    node = _version("node")
    checks.append(("node >=22.12", _node_supported(node), node or "MISSING"))
    pnpm = _version("pnpm")
    checks.append(("pnpm", pnpm is not None, pnpm or "MISSING"))
    worker_root = Path(__file__).resolve().parents[1]
    wrangler = worker_root / "node_modules" / ".bin" / "wrangler"
    if wrangler.is_file():
        with tempfile.TemporaryDirectory(prefix="ocb-doctor-") as home:
            result = subprocess.run(
                [str(wrangler), "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
                env={
                    "PATH": os.environ.get("PATH", os.defpath),
                    "HOME": home,
                    "XDG_CONFIG_HOME": home,
                    "WRANGLER_SEND_METRICS": "false",
                },
            )
        version = (result.stdout or result.stderr).strip().splitlines()
        checks.append(("wrangler", result.returncode == 0, version[0] if version else "FAILED"))
    else:
        checks.append(("wrangler", False, "MISSING"))
    template_ok = settings.template_dir.is_dir()
    checks.append(("TEMPLATE_DIR", template_ok, str(settings.template_dir)))
    modules_ok = template_ok and (settings.template_dir / "node_modules").is_dir()
    checks.append(("template node_modules", modules_ok, "present" if modules_ok else "MISSING"))
    for label, path in (("BUILD_ROOT", settings.build_root), ("SERVE_ROOT", settings.serve_root)):
        writable = _writable_directory(path)
        checks.append((label, writable, f"{path} ({'writable' if writable else 'not writable'})"))
    cloudflare_token = bool(os.environ.get("CLOUDFLARE_API_TOKEN"))
    cloudflare_account = bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    print(f"CLOUDFLARE_API_TOKEN: {'SET' if cloudflare_token else 'MISSING'}")
    print(f"CLOUDFLARE_ACCOUNT_ID: {'SET' if cloudflare_account else 'MISSING'}")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            system_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
            chromium_path = Path(system_chromium or playwright.chromium.executable_path)
            browser_ok = chromium_path.is_file()
            browser_detail = str(chromium_path) if browser_ok else "MISSING"
    except ImportError:
        browser_ok = False
        browser_detail = "Python Playwright is not installed"
    checks.append(("Playwright Chromium", browser_ok, browser_detail))
    for label, passed, detail in checks:
        print(f"{'OK' if passed else 'MISSING'} {label}: {detail}")
    return 0 if all(passed for _, passed, _ in checks) else 1


def _duration(value: str) -> float:
    parts = re.findall(r"(\d+)([smhd])", value.lower())
    if not parts or "".join(number + unit for number, unit in parts) != value.lower():
        raise argparse.ArgumentTypeError("duration must use s, m, h, or d units, such as 24h")
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return sum(int(number) * multipliers[unit] for number, unit in parts)


def _clean(args: argparse.Namespace) -> int:
    settings = load_settings()
    threshold = time.time() - args.older_than
    removed = 0
    if settings.build_root.is_dir():
        for build_dir in settings.build_root.iterdir():
            marker = build_dir / ".finished"
            if (
                not build_dir.is_symlink()
                and build_dir.is_dir()
                and marker.is_file()
                and marker.stat().st_mtime < threshold
            ):
                shutil.rmtree(build_dir)
                removed += 1
    print(f"Removed {removed} finished build directories.")
    return 0


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m worker")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor")

    build_parser = commands.add_parser("build")
    build_parser.add_argument("--repo", required=True)
    build_parser.add_argument("--ref", default="main")
    build_parser.add_argument("--slug", required=True)
    build_parser.add_argument("--subdir", default=".")
    build_parser.add_argument("--title")
    build_parser.add_argument("--author")
    build_parser.add_argument("--description")
    build_parser.add_argument("--target", choices=("local", "cloudflare"), default="local")
    build_parser.add_argument("--json", action="store_true")

    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--slug", required=True)
    rollback_parser.add_argument("--branch", default="main")
    rollback_parser.add_argument("--sha", required=True)

    serve_parser = commands.add_parser("serve")
    serve_parser.add_argument("--port", type=int)

    clean_parser = commands.add_parser("clean")
    clean_parser.add_argument("--older-than", type=_duration, default=_duration("24h"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    settings = load_settings()
    if args.command == "doctor":
        return _doctor(settings)
    if args.command == "build":
        return _build(args)
    if args.command == "rollback":
        try:
            target = LocalTarget()
            path = target.rollback(args.slug, args.branch, args.sha)
        except (FileNotFoundError, ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(f"Restored {args.slug}/{args.branch} to {args.sha}: {path}")
        return 0
    if args.command == "serve":
        port = args.port if args.port is not None else settings.serve_port
        if not 1 <= port <= 65535:
            print("serve port must be between 1 and 65535", file=sys.stderr)
            return 1
        serve(settings.serve_root, "127.0.0.1", port)
        return 0
    if args.command == "clean":
        return _clean(args)
    parser.error("unknown command")
    return 2
