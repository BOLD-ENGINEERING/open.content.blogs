from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import signal
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from worker.config import load_settings


class LocalSiteHandler(BaseHTTPRequestHandler):
    server_version = "OpenContentBlogs/1.0"

    def __init__(self, *args: object, serve_root: Path, **kwargs: object) -> None:
        self.serve_root = serve_root
        super().__init__(*args, **kwargs)

    def log_message(self, format_string: str, *args: object) -> None:
        return

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def do_GET(self) -> None:
        self._serve(head_only=False)

    def _serve(self, head_only: bool) -> None:
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        request_path = unquote(urlsplit(self.path).path)
        if host == "localhost" and request_path == "/":
            self._send_listing(head_only)
            return
        if host == "localhost" and request_path == "/_listing/alpine.js":
            self._send_file(
                load_settings().template_dir / "node_modules/alpinejs/dist/cdn.min.js",
                200,
                head_only,
            )
            return
        route = self._route(host)
        if not route:
            self._send_bytes(404, b"Not Found\n", "text/plain; charset=utf-8", head_only)
            return
        slug, branch = route
        site_root = self.serve_root / slug / branch
        if not site_root.is_dir():
            self._send_bytes(404, b"Not Found\n", "text/plain; charset=utf-8", head_only)
            return
        try:
            relative = self._relative_path(request_path)
            target = (site_root / relative).resolve(strict=False)
            if not target.is_relative_to(site_root.resolve()):
                raise ValueError("Path escapes the site")
        except OSError, ValueError:
            self._send_site_not_found(site_root, head_only)
            return
        if any(part.startswith(".") for part in relative.parts):
            self._send_site_not_found(site_root, head_only)
            return
        if target.is_dir():
            target = target / "index.html"
        if target.is_file():
            self._send_file(target, 200, head_only)
            return
        self._send_site_not_found(site_root, head_only)

    @staticmethod
    def _relative_path(request_path: str) -> Path:
        if "\x00" in request_path:
            raise ValueError("Invalid path")
        parts = [part for part in request_path.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            raise ValueError("Invalid path")
        return Path(*parts) if parts else Path("index.html")

    @staticmethod
    def _route(host: str) -> tuple[str, str] | None:
        parts = host.split(".")
        if len(parts) == 2 and parts[1] == "localhost":
            slug = parts[0]
            branch = "main"
        elif len(parts) == 3 and parts[2] == "localhost":
            branch, slug = parts[0], parts[1]
        else:
            return None
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", slug):
            return None
        if not re.fullmatch(r"[a-z0-9-]+", branch):
            return None
        return slug, branch

    def _send_listing(self, head_only: bool) -> None:
        entries: list[str] = []
        if self.serve_root.is_dir():
            for slug_dir in sorted(self.serve_root.iterdir()):
                if not slug_dir.is_dir() or slug_dir.name.startswith("."):
                    continue
                for branch_dir in sorted(slug_dir.iterdir()):
                    if not branch_dir.is_dir() or branch_dir.name.startswith("."):
                        continue
                    metadata = _read_metadata(branch_dir)
                    if not metadata:
                        continue
                    slug = html.escape(slug_dir.name)
                    branch = html.escape(branch_dir.name)
                    sha = html.escape(str(metadata.get("sha", "unknown")))
                    deployed_at = html.escape(str(metadata.get("deployed_at", "unknown")))
                    host = f"{slug}.localhost" if branch == "main" else f"{branch}.{slug}.localhost"
                    url = html.escape(f"http://{host}:{self.server.server_port}/", quote=True)
                    entries.append(
                        f'<li><a href="{url}">{slug}/{branch}</a> '
                        f"<code>{sha}</code> <time>{deployed_at}</time></li>"
                    )
        theme = "{ theme: localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'), toggleTheme() { this.theme = this.theme === 'dark' ? 'light' : 'dark'; localStorage.setItem('theme', this.theme); document.documentElement.dataset.theme = this.theme; } }"
        body = (
            f'<!doctype html><html lang="en" x-data="{theme}" '
            'x-init="document.documentElement.dataset.theme = theme"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width">'
            '<meta name="description" content="Local blog deployments">'
            '<meta property="og:title" content="Local blog deployments">'
            f'<meta property="og:url" content="http://localhost:{self.server.server_port}/">'
            f'<link rel="canonical" href="http://localhost:{self.server.server_port}/">'
            '<link rel="icon" href="data:,">'
            '<script defer src="/_listing/alpine.js"></script>'
            "<title>Local blog deployments</title><style>"
            ":root {color-scheme:light dark;font:16px/1.6 system-ui;--bg:#faf9f6;--fg:#242424;--link:#155b91;--line:#bbb}"
            "@media(prefers-color-scheme:dark){:root{--bg:#17191b;--fg:#eee;--link:#8fcaff;--line:#555}}"
            "[data-theme=light]{color-scheme:light;--bg:#faf9f6;--fg:#242424;--link:#155b91;--line:#bbb}"
            "[data-theme=dark]{color-scheme:dark;--bg:#17191b;--fg:#eee;--link:#8fcaff;--line:#555}"
            "body{background:var(--bg);color:var(--fg);margin:0;padding:24px}"
            "main{max-width:900px;margin:24px auto}h1{line-height:1.2}a{color:var(--link)}"
            "ul{list-style:none;padding:0}li{padding:20px 0;border-bottom:1px solid var(--line)}"
            "li a,code,time{display:block;overflow-wrap:anywhere}code,time{font-size:.875rem}"
            "button{font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px 12px}"
            ":focus-visible{outline:3px solid var(--link);outline-offset:4px}"
            '</style></head><body><main><button class="theme-toggle" x-on:click="toggleTheme()">Toggle theme</button>'
            "<h1>Local blog deployments</h1><p>Published sites and branch previews on this machine.</p><ul>"
            + "".join(entries)
            + "</ul></main></body></html>"
        ).encode("utf8")
        self._send_bytes(200, body, "text/html; charset=utf-8", head_only)

    def _send_site_not_found(self, site_root: Path, head_only: bool) -> None:
        missing_page = site_root / "404.html"
        if missing_page.is_file():
            self._send_file(missing_page, 404, head_only)
        else:
            self._send_bytes(404, b"Not Found\n", "text/plain; charset=utf-8", head_only)

    def _send_file(self, path: Path, status: int, head_only: bool) -> None:
        content_type, encoding = mimetypes.guess_type(path.name)
        if not content_type:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "application/xml",
            "image/svg+xml",
        }:
            content_type = f"{content_type}; charset=utf-8"
        try:
            data = path.read_bytes()
        except OSError:
            self._send_bytes(404, b"Not Found\n", "text/plain; charset=utf-8", head_only)
            return
        self._send_bytes(status, data, content_type, head_only, encoding=encoding)

    def _send_bytes(
        self,
        status: int,
        data: bytes,
        content_type: str,
        head_only: bool,
        encoding: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)


def _read_metadata(path: Path) -> dict[str, object]:
    try:
        value = json.loads((path / ".deploy.json").read_text(encoding="utf8"))
    except OSError, ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def serve(serve_root: Path, host: str, port: int) -> None:
    serve_root.mkdir(parents=True, exist_ok=True)
    handler = partial(LocalSiteHandler, serve_root=serve_root)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    shutdown = threading.Event()

    def request_shutdown(signum: int, frame: object) -> None:
        shutdown.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    old_int = signal.signal(signal.SIGINT, request_shutdown)
    old_term = signal.signal(signal.SIGTERM, request_shutdown)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        shutdown.set()


def configured_root() -> Path:
    return Path(os.environ.get("SERVE_ROOT", "/tmp/ocb-serve")).expanduser().resolve()
