from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .catalog import supported_versions, version_info
from .errors import ValidationError


VERSION_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def default_asset_root() -> Path:
    override = os.environ.get("LITEMAPTICA_ASSET_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "LiteMaptica" / "assets"


def _download_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "LiteMaptica/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _download_verified(url: str, destination: Path, expected_sha1: str) -> None:
    digest = hashlib.sha1()
    request = urllib.request.Request(url, headers={"User-Agent": "LiteMaptica/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected_sha1:
        destination.unlink(missing_ok=True)
        raise ValidationError("downloaded Minecraft client hash does not match Mojang metadata")


def status(asset_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(asset_root) if asset_root else default_asset_root()
    result = []
    for item in supported_versions():
        manifest = root / item["id"] / "asset-set.json"
        result.append({**item, "installed": manifest.is_file(), "path": str(manifest.parent) if manifest.is_file() else None})
    return result


def download(version: str, asset_root: str | Path | None = None) -> dict[str, Any]:
    catalog_entry = version_info(version)
    root = Path(asset_root) if asset_root else default_asset_root()
    destination = root / version
    existing = destination / "asset-set.json"
    if existing.is_file():
        return json.loads(existing.read_text(encoding="utf-8"))
    manifest = _download_json(VERSION_MANIFEST)
    remote = next((item for item in manifest["versions"] if item["id"] == version and item["type"] == "release"), None)
    if remote is None:
        raise ValidationError(f"stable release {version} is absent from Mojang's manifest")
    metadata = _download_json(remote["url"])
    client = metadata["downloads"]["client"]
    if int(metadata.get("dataVersion", {}).get("version", catalog_entry["data_version"])) != catalog_entry["data_version"]:
        raise ValidationError("repository compatibility catalog disagrees with Mojang DataVersion")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        temp = Path(temporary)
        jar = temp / "client.jar"
        _download_verified(client["url"], jar, client["sha1"])
        extracted = temp / "extracted"
        extracted.mkdir()
        prefixes = ("assets/minecraft/blockstates/", "assets/minecraft/models/", "assets/minecraft/textures/", "assets/minecraft/atlases/")
        with zipfile.ZipFile(jar) as archive:
            client_version = json.loads(archive.read("version.json"))
            if int(client_version.get("world_version", -1)) != catalog_entry["data_version"]:
                raise ValidationError("repository compatibility catalog disagrees with the signed client DataVersion")
            for member in archive.infolist():
                if member.filename.startswith(prefixes) and not member.is_dir():
                    archive.extract(member, extracted)
        asset_set = {
            "version": version,
            "dataVersion": catalog_entry["data_version"],
            "clientSha1": client["sha1"],
            "source": "Mojang version manifest v2",
            "resourcePackSupport": False,
        }
        (extracted / "asset-set.json").write_text(json.dumps(asset_set, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        extracted.replace(destination)
    return {**asset_set, "path": str(destination)}


def remove(version: str, asset_root: str | Path | None = None) -> dict[str, Any]:
    version_info(version)
    root = Path(asset_root) if asset_root else default_asset_root()
    destination = root / version
    removed = destination.exists()
    if removed:
        shutil.rmtree(destination)
    return {"version": version, "removed": removed}
