from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    template_dir: Path
    build_root: Path
    serve_root: Path
    build_timeout: int
    serve_port: int


def load_settings() -> Settings:
    return Settings(
        template_dir=Path(os.environ.get("TEMPLATE_DIR", str(REPOSITORY_ROOT / "web")))
        .expanduser()
        .resolve(),
        build_root=Path(os.environ.get("BUILD_ROOT", "/tmp/ocb-builds")).expanduser().resolve(),
        serve_root=Path(os.environ.get("SERVE_ROOT", "/tmp/ocb-serve")).expanduser().resolve(),
        build_timeout=int(os.environ.get("BUILD_TIMEOUT", "300")),
        serve_port=int(os.environ.get("SERVE_PORT", "8787")),
    )
