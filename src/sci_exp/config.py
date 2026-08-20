from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    config["_config_path"] = str(config_path)
    config["_project_root"] = str(_resolve_project_root(config, config_path))
    return config


def _resolve_project_root(config: dict[str, Any], config_path: Path) -> Path:
    raw_root = config.get("project_root")
    if raw_root:
        root = Path(raw_root).expanduser()
        if root.exists():
            return root.resolve()
    return config_path.parent.parent.resolve()


def project_path(config: dict[str, Any], value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return Path(config["_project_root"]) / candidate

