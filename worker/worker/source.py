from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from worker.config import load_settings
from worker.models import BuildRequest, ContentManifest

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 500
MAX_TOTAL_BYTES = 20 * 1024 * 1024


class SourceError(RuntimeError):
    def __init__(self, message: str, manifest: ContentManifest | None = None) -> None:
        super().__init__(message)
        self.manifest = manifest


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SourceError(detail or f"git {' '.join(args)} failed")
    return result


def _resolve_commit(source_dir: Path, ref: str) -> str:
    candidates = [ref]
    if ref not in {"HEAD", "FETCH_HEAD"} and not ref.startswith("refs/"):
        candidates.append(f"refs/remotes/origin/{ref}")
    for candidate in candidates:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(source_dir),
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{candidate}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    raise SourceError(f"Ref does not resolve to a commit: {ref}")


def _first_added_times(
    source_dir: Path, content_subdir: str, current_paths: list[str]
) -> dict[str, int]:
    result = _git(
        [
            "-C",
            str(source_dir),
            "log",
            "--reverse",
            "--format=%x1e%ct",
            "--name-status",
            "-z",
            "--find-renames",
            "--",
        ]
    )
    tokens = iter(result.stdout.split("\0"))
    timestamp = None
    dates: dict[str, int] = {}
    for token in tokens:
        token = token.lstrip("\n")
        if not token:
            continue
        if token.startswith("\x1e"):
            timestamp = int(token[1:])
            continue
        if timestamp is None:
            raise SourceError("Missing timestamp in Git history")
        path = next(tokens)
        if token.startswith("R"):
            new_path = next(tokens)
            dates[new_path] = dates.get(path, timestamp)
        elif token.startswith("C"):
            new_path = next(tokens)
            dates.setdefault(new_path, timestamp)
        elif token == "A":
            dates.setdefault(path, timestamp)
    return {path: dates[path] for path in current_paths if path in dates}


def _content_root(source_dir: Path, content_subdir: str) -> Path:
    relative = Path(content_subdir)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise SourceError("content_subdir must stay inside the repository")
    root = source_dir
    for part in relative.parts:
        root = root / part
        if root.is_symlink():
            raise SourceError("content_subdir cannot contain symlinks")
    try:
        info = root.lstat()
    except FileNotFoundError as error:
        raise SourceError(f"Content directory does not exist: {content_subdir}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SourceError(f"Content path is not a regular directory: {content_subdir}")
    resolved = root.resolve(strict=True)
    if not resolved.is_relative_to(source_dir.resolve()):
        raise SourceError("content_subdir resolves outside the repository")
    return root


def fetch_content(request: BuildRequest) -> tuple[Path, ContentManifest]:
    settings = load_settings()
    build_dir = settings.build_root / str(request.build_id)
    source_dir = build_dir / "src"
    content_dir = build_dir / "content"
    build_dir.mkdir(parents=True, exist_ok=False)
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--",
                request.repo_url,
                str(source_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise SourceError(detail or f"Could not clone repository: {request.repo_url}")

        commit = _resolve_commit(source_dir, request.ref)
        _git(["-C", str(source_dir), "checkout", "--force", "--detach", commit])
        source_root = _content_root(source_dir, request.content_subdir)
        root_real = source_root.resolve()
        manifest = ContentManifest(sha=commit)
        content_dir.mkdir(parents=True)
        total_bytes = 0
        candidates: list[tuple[Path, str, str, int]] = []

        for current, dirs, files in os.walk(source_root, followlinks=False):
            current_path = Path(current)
            dirs.sort()
            files.sort()
            for dirname in list(dirs):
                path = current_path / dirname
                if path == source_dir / ".git":
                    dirs.remove(dirname)
                    continue
                try:
                    info = path.lstat()
                except OSError:
                    dirs.remove(dirname)
                    manifest.skipped.append(
                        {
                            "path": path.relative_to(source_root).as_posix(),
                            "reason": "unreadable entry",
                        }
                    )
                    continue
                if stat.S_ISLNK(info.st_mode):
                    dirs.remove(dirname)
                    manifest.skipped.append(
                        {
                            "path": path.relative_to(source_root).as_posix(),
                            "reason": "symlink not permitted",
                        }
                    )
                elif not stat.S_ISDIR(info.st_mode):
                    dirs.remove(dirname)
                    manifest.skipped.append(
                        {
                            "path": path.relative_to(source_root).as_posix(),
                            "reason": "not a regular directory",
                        }
                    )

            for filename in files:
                path = current_path / filename
                relative_path = path.relative_to(source_root).as_posix()
                try:
                    info = path.lstat()
                except OSError:
                    manifest.skipped.append({"path": relative_path, "reason": "unreadable entry"})
                    continue
                if stat.S_ISLNK(info.st_mode):
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "symlink not permitted"}
                    )
                    continue
                if not stat.S_ISREG(info.st_mode):
                    manifest.skipped.append({"path": relative_path, "reason": "not a regular file"})
                    continue
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root_real):
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "path escapes content directory"}
                    )
                    continue
                if any(part.startswith(".") for part in Path(relative_path).parts):
                    manifest.skipped.append({"path": relative_path, "reason": "hidden path"})
                    continue
                if path.suffix.lower() == ".mdx":
                    manifest.skipped.append({"path": relative_path, "reason": "mdx not permitted"})
                    continue
                if path.suffix != ".md":
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "not a markdown file"}
                    )
                    continue
                if info.st_size > MAX_FILE_BYTES:
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "file exceeds 2 MB limit"}
                    )
                    raise SourceError(
                        f"File size limit is 2 MB; {relative_path} is {info.st_size} bytes",
                        manifest,
                    )
                if len(candidates) + 1 > MAX_FILES:
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "file count exceeds 500 limit"}
                    )
                    raise SourceError(
                        f"File count limit is 500; exceeded at {relative_path}", manifest
                    )
                if total_bytes + info.st_size > MAX_TOTAL_BYTES:
                    manifest.skipped.append(
                        {"path": relative_path, "reason": "content exceeds 20 MB total limit"}
                    )
                    raise SourceError(
                        f"Total content size limit is 20 MB; exceeded at {relative_path}", manifest
                    )
                total_bytes += info.st_size
                candidates.append(
                    (path, relative_path, path.relative_to(source_dir).as_posix(), info.st_size)
                )

        first_added = _first_added_times(
            source_dir,
            request.content_subdir,
            [repo_relative for _, _, repo_relative, _ in candidates],
        )
        for path, relative_path, repo_relative, _ in candidates:
            timestamp = first_added.get(repo_relative)
            if timestamp is None:
                raise SourceError(
                    f"Could not find the first-add commit timestamp for {relative_path}", manifest
                )
            destination = content_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination, follow_symlinks=False)
            os.utime(destination, (timestamp, timestamp), follow_symlinks=False)
            manifest.files.append(relative_path)

        manifest_path = build_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.__dict__, indent=2), encoding="utf8")
        shutil.rmtree(source_dir)
        return content_dir, manifest
    except SourceError:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise SourceError(str(error)) from error
