from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .errors import CapabilityUnavailable, ValidationError
from .store import ProjectStore


VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SOURCE_SECONDS = 30 * 60
MIN_IMAGE_COUNT = 2
MAX_IMAGE_COUNT = 10_000


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _managed_source_path(project: ProjectStore, source: dict[str, Any]) -> Path | None:
    managed = source.get("managedPath")
    if not managed:
        return None
    candidate = (project.root / str(managed)).resolve()
    source_root = (project.root / "source").resolve()
    return candidate if candidate.is_relative_to(source_root) else None


def _replace_frames(project: ProjectStore, frames: list[dict[str, Any]]) -> None:
    with project.connect() as db:
        db.execute("DELETE FROM frames")
        for frame in frames:
            db.execute(
                "INSERT INTO frames(id,timestamp,path,segment,accepted,metadata_json) VALUES(?,?,?,?,?,?)",
                (frame["id"], frame["timestamp"], frame["path"], 0, 1, json.dumps(frame.get("metadata", {}), sort_keys=True)),
            )


def _install_managed_source(
    project: ProjectStore,
    temporary: Path,
    destination: Path,
    source_config: dict[str, Any],
    trims: dict[str, float] | None,
    frames: list[dict[str, Any]],
) -> None:
    previous_config = project.config()
    previous_path = _managed_source_path(project, previous_config.get("source") or {})
    backup = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.backup")
    had_destination = destination.exists()
    try:
        if had_destination:
            destination.replace(backup)
        temporary.replace(destination)
        try:
            project.update_config({"source": source_config, "trims": trims})
            try:
                _replace_frames(project, frames)
            except Exception:
                project.update_config({"source": previous_config.get("source"), "trims": previous_config.get("trims")})
                raise
        except Exception:
            _remove_path(destination)
            if had_destination and backup.exists():
                backup.replace(destination)
            raise
        _remove_path(backup)
        if previous_path is not None and previous_path != destination:
            _remove_path(previous_path)
    finally:
        _remove_path(temporary)
        _remove_path(backup)


def inspect(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValidationError("source must be an existing MP4, MOV, or WebM file")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return {"path": str(source), "bytes": source.stat().st_size, "duration": None, "warning": "ffprobe is unavailable; duration must be validated during packaged analysis"}
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(source)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise ValidationError(f"ffprobe could not inspect the video: {result.stderr.strip()}")
    metadata = json.loads(result.stdout)
    duration = float(metadata.get("format", {}).get("duration", 0))
    video_stream = next((stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"), {})
    return {"path": str(source), "bytes": source.stat().st_size, "duration": duration, "width": video_stream.get("width"), "height": video_stream.get("height"), "requiresTrim": duration > 1800}


def _natural_name(path: Path) -> list[tuple[int, int | str]]:
    return [(0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", path.name.casefold())]


def _image_files(path: str | Path) -> tuple[Path, list[Path]]:
    folder = Path(path).expanduser().resolve()
    if not folder.is_dir():
        raise ValidationError("picture source must be an existing folder")
    images = sorted((item for item in folder.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES), key=_natural_name)
    if not images:
        raise ValidationError("picture folder contains no JPG, JPEG, PNG, or WebP images")
    if len(images) < MIN_IMAGE_COUNT:
        raise ValidationError("picture folder must contain at least two supported images for multi-view reconstruction")
    if len(images) > MAX_IMAGE_COUNT:
        raise ValidationError(f"picture folder exceeds the {MAX_IMAGE_COUNT:,}-image import limit")
    return folder, images


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    start_of_frame = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        if marker in start_of_frame and length >= 7:
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return width, height
        offset += length
    return None


def _image_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        data = source.read(1024 * 1024)
    dimensions = None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        dimensions = (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    elif path.suffix.lower() in {".jpg", ".jpeg"}:
        dimensions = _jpeg_dimensions(data)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        if data[12:16] == b"VP8X":
            dimensions = (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
        elif data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            dimensions = (int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF)
        elif data[12:16] == b"VP8L" and data[20] == 0x2F:
            packed = int.from_bytes(data[21:25], "little")
            dimensions = ((packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1)
    if dimensions is None or min(dimensions) <= 0:
        raise ValidationError(f"could not read picture dimensions: {path.name}")
    return dimensions


def inspect_images(path: str | Path) -> dict[str, Any]:
    folder, images = _image_files(path)
    dimensions = [_image_dimensions(image) for image in images]
    resolutions = sorted(set(dimensions))
    uniform = resolutions[0] if len(resolutions) == 1 else (None, None)
    return {
        "path": str(folder),
        "folderName": folder.name,
        "count": len(images),
        "bytes": sum(image.stat().st_size for image in images),
        "width": uniform[0],
        "height": uniform[1],
        "mixedResolutions": len(resolutions) > 1,
        "resolutions": [{"width": width, "height": height} for width, height in resolutions],
        "order": "natural_filename",
    }


def _validate_trim(trim: dict[str, float] | None, duration: float | None) -> dict[str, float] | None:
    if trim is None:
        return None
    try:
        start = float(trim["start"])
        end = float(trim["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("trim must include numeric start and end times") from exc
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValidationError("trim times must be finite")
    if start < 0 or start >= end:
        raise ValidationError("trim must satisfy 0 <= start < end")
    if duration is not None and end > duration:
        raise ValidationError("trim end must not exceed the video duration")
    if end - start > MAX_SOURCE_SECONDS:
        raise ValidationError("selected trim must not exceed 30 minutes")
    return {"start": start, "end": end}


def import_local(project: ProjectStore, path: str | Path, trim: dict[str, float] | None = None) -> dict[str, Any]:
    metadata = inspect(path)
    validated_trim = _validate_trim(trim, metadata.get("duration"))
    if metadata.get("requiresTrim") and validated_trim is None:
        raise ValidationError("footage over 30 minutes must be trimmed before import")
    source = Path(path).expanduser().resolve()
    destination = project.root / "source" / ("original" + source.suffix.lower())
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.importing")
    try:
        shutil.copy2(source, temporary)
        source_config = {
            "kind": "local",
            "managedPath": str(destination.relative_to(project.root)),
            "originalName": source.name,
            "metadata": metadata,
        }
        _install_managed_source(project, temporary, destination, source_config, validated_trim, [])
    finally:
        _remove_path(temporary)
    return {**metadata, "managedPath": str(destination)}


def import_images(project: ProjectStore, path: str | Path) -> dict[str, Any]:
    metadata = inspect_images(path)
    folder, images = _image_files(path)
    destination = project.root / "source" / "images"
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.importing")
    temporary.mkdir()
    frames = []
    try:
        for index, image in enumerate(images, start=1):
            width, height = _image_dimensions(image)
            managed_name = f"{index:06d}{image.suffix.lower()}"
            managed = temporary / managed_name
            shutil.copy2(image, managed)
            relative = (destination / managed_name).relative_to(project.root)
            frames.append({
                "id": index,
                "timestamp": float(index - 1),
                "path": str(relative),
                "metadata": {"originalName": image.name, "width": width, "height": height, "sourceKind": "image_folder"},
            })
        source_config = {
            "kind": "image_folder",
            "managedPath": str(destination.relative_to(project.root)),
            "originalName": folder.name,
            "metadata": metadata,
        }
        _install_managed_source(project, temporary, destination, source_config, None, frames)
    finally:
        _remove_path(temporary)
    return {**metadata, "managedPath": str(destination), "frameCount": len(frames)}


def fetch_youtube(project: ProjectStore, url: str, rights_acknowledged: bool) -> dict[str, Any]:
    if not rights_acknowledged:
        raise ValidationError("rights acknowledgement is required before downloading third-party footage")
    yt_dlp = shutil.which("yt-dlp")
    if yt_dlp is None:
        raise CapabilityUnavailable("yt-dlp is unavailable; import a local video instead")
    output = project.root / "source" / "youtube.%(ext)s"
    command = [yt_dlp, "--no-playlist", "--no-audio", "-f", "bestvideo[height<=1080]", "--merge-output-format", "mp4", "--print", "after_move:filepath", "-o", str(output), url]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    if result.returncode != 0:
        raise CapabilityUnavailable("YouTube extraction failed; import a local copy of the video instead")
    path = Path(result.stdout.strip().splitlines()[-1])
    metadata = inspect(path)
    project.update_config({"source": {"kind": "youtube", "managedPath": str(path.relative_to(project.root)), "metadata": metadata}})
    return {**metadata, "managedPath": str(path)}
