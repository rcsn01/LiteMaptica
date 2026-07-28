from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ValidationError


@dataclass(frozen=True)
class ModelApplication:
    model: str
    x: int = 0
    y: int = 0
    uvlock: bool = False
    weight: int = 1


def _identifier(value: str, default_kind: str) -> tuple[str, str]:
    namespace, separator, path = value.partition(":")
    if not separator:
        namespace, path = "minecraft", namespace
    if path.startswith("block/") or path.startswith("item/"):
        return namespace, path
    return namespace, f"{default_kind}/{path}"


def _variant_matches(expression: str, properties: dict[str, str]) -> bool:
    if not expression:
        return True
    for clause in expression.split(","):
        key, separator, choices = clause.partition("=")
        if not separator or properties.get(key) not in choices.split("|"):
            return False
    return True


def _multipart_matches(condition: Any, properties: dict[str, str]) -> bool:
    if not condition:
        return True
    if "OR" in condition:
        return any(_multipart_matches(value, properties) for value in condition["OR"])
    if "AND" in condition:
        return all(_multipart_matches(value, properties) for value in condition["AND"])
    return all(properties.get(key) in str(value).split("|") for key, value in condition.items())


def _applications(value: dict[str, Any] | list[dict[str, Any]]) -> list[ModelApplication]:
    values = value if isinstance(value, list) else [value]
    return [ModelApplication(model=item["model"], x=int(item.get("x", 0)), y=int(item.get("y", 0)), uvlock=bool(item.get("uvlock", False)), weight=max(1, int(item.get("weight", 1)))) for item in values]


class VanillaModelResolver:
    """Resolve vanilla JSON blockstates and inherited block models without rendering."""

    def __init__(self, extracted_root: str | Path):
        self.root = Path(extracted_root)
        self.assets = self.root / "assets"
        self._model_cache: dict[str, dict[str, Any]] = {}

    def _json(self, namespace: str, relative: str) -> dict[str, Any]:
        path = self.assets / namespace / f"{relative}.json"
        if not path.is_file():
            raise ValidationError(f"missing vanilla asset JSON: {namespace}:{relative}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValidationError(f"invalid vanilla asset JSON {path}: {exc}") from exc

    def resolve_model(self, identifier: str, stack: tuple[str, ...] = ()) -> dict[str, Any]:
        namespace, relative = _identifier(identifier, "block")
        canonical = f"{namespace}:{relative}"
        if canonical in self._model_cache:
            return self._model_cache[canonical]
        if canonical in stack:
            raise ValidationError(f"cyclic model inheritance: {' -> '.join((*stack, canonical))}")
        child = self._json(namespace, f"models/{relative}")
        if "parent" in child:
            parent = self.resolve_model(child["parent"], (*stack, canonical))
            merged = {**parent, **{key: value for key, value in child.items() if key != "textures"}}
            merged["textures"] = {**parent.get("textures", {}), **child.get("textures", {})}
        else:
            merged = child
        merged = json.loads(json.dumps(merged))
        merged["identifier"] = canonical
        self._model_cache[canonical] = merged
        return merged

    @staticmethod
    def resolve_texture(reference: str, textures: dict[str, str]) -> str:
        seen = set()
        value = reference
        while value.startswith("#"):
            key = value[1:]
            if key in seen:
                raise ValidationError(f"cyclic texture reference #{key}")
            seen.add(key)
            if key not in textures:
                raise ValidationError(f"unresolved texture reference #{key}")
            value = textures[key]
        namespace, separator, path = value.partition(":")
        return value if separator else f"minecraft:{namespace}"

    def applications(self, block_id: str, properties: dict[str, str]) -> list[ModelApplication]:
        namespace, _, path = block_id.partition(":")
        if not path:
            namespace, path = "minecraft", namespace
        state = self._json(namespace, f"blockstates/{path}")
        result: list[ModelApplication] = []
        for expression, value in state.get("variants", {}).items():
            if _variant_matches(expression, properties):
                result.extend(_applications(value))
        for part in state.get("multipart", []):
            if _multipart_matches(part.get("when", {}), properties):
                result.extend(_applications(part["apply"]))
        if not result:
            raise ValidationError(f"no rendered model matches {block_id} properties {properties}")
        return result

    def visual_property_values(self, block_id: str) -> dict[str, list[str]]:
        namespace, _, path = block_id.partition(":")
        if not path:
            namespace, path = "minecraft", namespace
        state = self._json(namespace, f"blockstates/{path}")
        values: dict[str, set[str]] = {}

        def collect(condition: Any) -> None:
            if not isinstance(condition, dict):
                return
            for key, value in condition.items():
                if key in {"OR", "AND"}:
                    for child in value:
                        collect(child)
                else:
                    values.setdefault(key, set()).update(str(value).split("|"))

        for expression in state.get("variants", {}):
            for clause in expression.split(","):
                key, separator, choice = clause.partition("=")
                if separator:
                    values.setdefault(key, set()).update(choice.split("|"))
        for part in state.get("multipart", []):
            collect(part.get("when", {}))
        return {key: sorted(items) for key, items in sorted(values.items())}

    def enumerate_visual_states(self, block_id: str) -> list[dict[str, str]]:
        values = self.visual_property_values(block_id)
        if not values:
            return [{}]
        keys = list(values)
        return [dict(zip(keys, combination)) for combination in itertools.product(*(values[key] for key in keys))]

    def canonical_template(self, block_id: str, properties: dict[str, str]) -> dict[str, Any]:
        applications = self.applications(block_id, properties)
        resolved = []
        for application in applications:
            model = self.resolve_model(application.model)
            textures = model.get("textures", {})
            elements = []
            for element in model.get("elements", []):
                faces = {}
                for direction, face in element.get("faces", {}).items():
                    faces[direction] = {**face, "texture": self.resolve_texture(face["texture"], textures)}
                elements.append({"from": element["from"], "to": element["to"], "rotation": element.get("rotation"), "shade": element.get("shade", True), "faces": faces})
            resolved.append({"application": application.__dict__, "elements": elements, "ambientOcclusion": model.get("ambientocclusion", True)})
        signature_payload = [{"x": item["application"]["x"], "y": item["application"]["y"], "elements": [{"from": e["from"], "to": e["to"], "faces": sorted(e["faces"])} for e in item["elements"]]} for item in resolved]
        signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"state": {"id": block_id, "properties": dict(sorted(properties.items()))}, "models": resolved, "geometrySignature": signature}
