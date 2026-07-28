from __future__ import annotations

import gzip
import io
import math
import struct
import time
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .store import ProjectStore


TAG_END = 0
TAG_BYTE = 1
TAG_INT = 3
TAG_LONG = 4
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_LONG_ARRAY = 12


def _name(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def _payload(tag_type: int, value: Any) -> bytes:
    if tag_type == TAG_BYTE:
        return struct.pack(">b", int(value))
    if tag_type == TAG_INT:
        return struct.pack(">i", int(value))
    if tag_type == TAG_LONG:
        return struct.pack(">q", int(value))
    if tag_type == TAG_STRING:
        return _name(str(value))
    if tag_type == TAG_COMPOUND:
        return b"".join(bytes([child_type]) + _name(child_name) + _payload(child_type, child_value) for child_name, (child_type, child_value) in value.items()) + bytes([TAG_END])
    if tag_type == TAG_LIST:
        child_type, children = value
        return bytes([child_type]) + struct.pack(">i", len(children)) + b"".join(_payload(child_type, child) for child in children)
    if tag_type == TAG_LONG_ARRAY:
        converted = [item if item < (1 << 63) else item - (1 << 64) for item in value]
        return struct.pack(">i", len(converted)) + b"".join(struct.pack(">q", item) for item in converted)
    raise ValueError(f"unsupported NBT tag {tag_type}")


def encode_root(name: str, compound: dict[str, tuple[int, Any]]) -> bytes:
    return bytes([TAG_COMPOUND]) + _name(name) + _payload(TAG_COMPOUND, compound)


def pack_palette_indices(indices: list[int], palette_size: int) -> tuple[int, list[int]]:
    bits = max(2, math.ceil(math.log2(max(1, palette_size))))
    words = [0] * math.ceil(len(indices) * bits / 64)
    mask = (1 << bits) - 1
    for index, value in enumerate(indices):
        if value < 0 or value >= palette_size:
            raise ValidationError(f"palette index {value} outside palette of size {palette_size}")
        bit_index = index * bits
        word = bit_index // 64
        offset = bit_index % 64
        words[word] |= (value & mask) << offset
        if offset + bits > 64:
            words[word + 1] |= (value & mask) >> (64 - offset)
    return bits, [word & ((1 << 64) - 1) for word in words]


def unpack_palette_indices(words: list[int], count: int, palette_size: int) -> list[int]:
    bits = max(2, math.ceil(math.log2(max(1, palette_size))))
    mask = (1 << bits) - 1
    result = []
    unsigned = [word & ((1 << 64) - 1) for word in words]
    for index in range(count):
        bit_index = index * bits
        word = bit_index // 64
        offset = bit_index % 64
        value = unsigned[word] >> offset
        if offset + bits > 64:
            value |= unsigned[word + 1] << (64 - offset)
        result.append(value & mask)
    return result


def _block_state_tag(state: dict[str, Any]) -> dict[str, tuple[int, Any]]:
    result: dict[str, tuple[int, Any]] = {"Name": (TAG_STRING, state["id"])}
    if state.get("properties"):
        result["Properties"] = (TAG_COMPOUND, {key: (TAG_STRING, value) for key, value in sorted(state["properties"].items())})
    return result


def build_litematic(project: ProjectStore, author: str = "LiteMaptica") -> tuple[bytes, dict[str, Any]]:
    config = project.config()
    voxels = project.voxels()
    if not voxels:
        raise ValidationError("project has no exportable evidenced or manually placed blocks")
    positions = [voxel["position"] for voxel in voxels]
    minimum = [min(p[axis] for p in positions) for axis in range(3)]
    maximum = [max(p[axis] for p in positions) for axis in range(3)]
    size = [maximum[axis] - minimum[axis] + 1 for axis in range(3)]
    if any(value > 256 for value in size):
        raise ValidationError(f"working volume {size} exceeds the 256-block axis limit")
    if len(voxels) > 2_000_000:
        raise ValidationError("project exceeds the two-million-block export limit")

    palette = [{"id": "minecraft:air", "properties": {}}]
    palette_lookup = {("minecraft:air", ()): 0}
    cells: dict[tuple[int, int, int], int] = {}
    for voxel in voxels:
        state = voxel["state"]
        key = (state["id"], tuple(sorted(state.get("properties", {}).items())))
        palette_index = palette_lookup.get(key)
        if palette_index is None:
            palette_index = len(palette)
            palette_lookup[key] = palette_index
            palette.append(state)
        local = tuple(voxel["position"][axis] - minimum[axis] for axis in range(3))
        cells[local] = palette_index

    indices: list[int] = []
    for y in range(size[1]):
        for z in range(size[2]):
            for x in range(size[0]):
                indices.append(cells.get((x, y, z), 0))
    bits, words = pack_palette_indices(indices, len(palette))
    now = int(time.time() * 1000)
    xyz = lambda values: {"x": (TAG_INT, values[0]), "y": (TAG_INT, values[1]), "z": (TAG_INT, values[2])}
    empty_compounds = (TAG_LIST, (TAG_COMPOUND, []))
    region = {
        "Position": (TAG_COMPOUND, xyz(minimum)),
        "Size": (TAG_COMPOUND, xyz(size)),
        "BlockStatePalette": (TAG_LIST, (TAG_COMPOUND, [_block_state_tag(state) for state in palette])),
        "BlockStates": (TAG_LONG_ARRAY, words),
        "TileEntities": empty_compounds,
        "Entities": empty_compounds,
        "PendingBlockTicks": empty_compounds,
        "PendingFluidTicks": empty_compounds,
    }
    metadata = {
        "Name": (TAG_STRING, config["name"]),
        "Author": (TAG_STRING, author),
        "Description": (TAG_STRING, "Evidence-backed reconstruction exported by LiteMaptica"),
        "RegionCount": (TAG_INT, 1),
        "TimeCreated": (TAG_LONG, config["createdAt"]),
        "TimeModified": (TAG_LONG, now),
        "TotalBlocks": (TAG_INT, len(voxels)),
        "TotalVolume": (TAG_LONG, size[0] * size[1] * size[2]),
        "EnclosingSize": (TAG_COMPOUND, xyz(size)),
    }
    from .catalog import version_info

    version = version_info(config["targetJavaVersion"])
    root = {
        "Version": (TAG_INT, version["litematic_version"]),
        "SubVersion": (TAG_INT, version["litematic_subversion"]),
        "MinecraftDataVersion": (TAG_INT, config["minecraftDataVersion"]),
        "Metadata": (TAG_COMPOUND, metadata),
        "Regions": (TAG_COMPOUND, {"Reconstruction": (TAG_COMPOUND, region)}),
    }
    raw = encode_root("", root)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as archive:
        archive.write(raw)
    report = {"blocks": len(voxels), "paletteSize": len(palette), "size": size, "origin": minimum, "bitsPerBlock": bits, "dataVersion": config["minecraftDataVersion"]}
    return buffer.getvalue(), report


class _Reader:
    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.position = 0

    def take(self, count: int) -> bytes:
        if self.position + count > len(self.data):
            raise ValidationError("truncated NBT payload")
        result = self.data[self.position : self.position + count].tobytes()
        self.position += count
        return result

    def number(self, fmt: str) -> int:
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self) -> str:
        return self.take(self.number(">H")).decode("utf-8")

    def payload(self, tag_type: int) -> Any:
        if tag_type == TAG_BYTE:
            return self.number(">b")
        if tag_type == TAG_INT:
            return self.number(">i")
        if tag_type == TAG_LONG:
            return self.number(">q")
        if tag_type == TAG_STRING:
            return self.string()
        if tag_type == TAG_COMPOUND:
            result = {}
            while True:
                child_type = self.number(">B")
                if child_type == TAG_END:
                    return result
                # Assignment evaluates its right-hand side first in Python, so read
                # the tag name explicitly before consuming the payload.
                child_name = self.string()
                result[child_name] = self.payload(child_type)
        if tag_type == TAG_LIST:
            child_type = self.number(">B")
            count = self.number(">i")
            if count < 0:
                raise ValidationError("negative NBT list length")
            return [self.payload(child_type) for _ in range(count)]
        if tag_type == TAG_LONG_ARRAY:
            count = self.number(">i")
            if count < 0:
                raise ValidationError("negative NBT long-array length")
            return [self.number(">q") for _ in range(count)]
        raise ValidationError(f"unsupported NBT tag {tag_type}")

    def root(self) -> dict[str, Any]:
        if self.number(">B") != TAG_COMPOUND:
            raise ValidationError("NBT root is not a compound")
        self.string()
        result = self.payload(TAG_COMPOUND)
        if self.position != len(self.data):
            raise ValidationError("unexpected bytes after NBT root")
        return result


def read_litematic(data: bytes) -> dict[str, Any]:
    try:
        raw = gzip.decompress(data)
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ValidationError(f"invalid gzip stream: {exc}") from exc
    return _Reader(raw).root()


def validate_litematic(data: bytes, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    root = read_litematic(data)
    required = {"Version", "SubVersion", "MinecraftDataVersion", "Metadata", "Regions"}
    missing = required.difference(root)
    if missing:
        raise ValidationError(f"Litematic is missing tags: {', '.join(sorted(missing))}")
    if set(root["Regions"]) != {"Reconstruction"}:
        raise ValidationError("export must contain one Reconstruction region")
    region = root["Regions"]["Reconstruction"]
    size_tag = region["Size"]
    size = [size_tag[axis] for axis in ("x", "y", "z")]
    palette_size = len(region["BlockStatePalette"])
    indices = unpack_palette_indices(region["BlockStates"], math.prod(size), palette_size)
    if any(index >= palette_size for index in indices):
        raise ValidationError("bit-packed storage contains an invalid palette index")
    result = {"valid": True, "version": root["Version"], "dataVersion": root["MinecraftDataVersion"], "blocks": root["Metadata"]["TotalBlocks"], "size": size, "paletteSize": palette_size}
    if expected:
        for key in ("blocks", "size", "dataVersion"):
            if key in expected and result[key] != expected[key]:
                raise ValidationError(f"round-trip mismatch for {key}: {result[key]} != {expected[key]}")
    return result


def export_project(project: ProjectStore, destination: str | Path, author: str = "LiteMaptica") -> dict[str, Any]:
    data, build_report = build_litematic(project, author)
    validation = validate_litematic(data, build_report)
    path = Path(destination).expanduser().resolve()
    if path.suffix != ".litematic":
        raise ValidationError("export filename must end in .litematic")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".litematic.tmp")
    temporary.write_bytes(data)
    validate_litematic(temporary.read_bytes(), build_report)
    temporary.replace(path)
    return {**build_report, **validation, "path": str(path), "bytes": len(data)}
