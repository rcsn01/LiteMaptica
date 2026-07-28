from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

from .errors import ValidationError


def _catalog_bytes() -> bytes:
    return files("litemap_engine").joinpath("data/supported_versions.json").read_bytes()


def catalog() -> dict[str, Any]:
    return json.loads(_catalog_bytes())


def catalog_digest() -> str:
    """Repository-pinned digest used in projects and update signatures."""
    return hashlib.sha256(_catalog_bytes()).hexdigest()


def supported_versions() -> list[dict[str, Any]]:
    return catalog()["versions"]


def version_info(version: str) -> dict[str, Any]:
    for item in supported_versions():
        if item["id"] == version:
            return item
    raise ValidationError(f"Minecraft Java {version!r} is not in the tested stable catalog")
