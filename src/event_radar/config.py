from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def find_root() -> Path:
    env = os.environ.get("EVENT_RADAR_ROOT")
    if env:
        return Path(env).resolve()
    search = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    for candidate in search:
        if (candidate / "config" / "sources.yaml").exists():
            return candidate
    return Path.cwd()


ROOT = find_root()
CONFIG_DIR = ROOT / "config"
DATA_DIR = Path(os.environ["EVENT_RADAR_DATA"]).resolve() if os.environ.get("EVENT_RADAR_DATA") else ROOT / "data"


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_profile(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or CONFIG_DIR / "profile.yaml")


def load_sources(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or CONFIG_DIR / "sources.yaml")


def load_keywords(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or CONFIG_DIR / "keywords.yaml")


def load_series(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or CONFIG_DIR / "series.yaml")
