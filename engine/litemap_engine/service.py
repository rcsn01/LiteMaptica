from __future__ import annotations

from pathlib import Path
from typing import Any

from . import assets, media
from .catalog import catalog_digest, supported_versions
from .errors import ValidationError
from .jobs import JobManager, capabilities
from .litematic import export_project, validate_litematic
from .store import AIR, ProjectStore
from .vanilla import VanillaModelResolver


def _project(params: dict[str, Any]) -> ProjectStore:
    path = params.get("project") or params.get("path")
    if not path:
        raise ValidationError("project path is required")
    project = ProjectStore(path)
    project.ensure_valid()
    return project


def demo_proposals() -> list[dict[str, Any]]:
    proposals = []
    for x in range(-3, 4):
        for z in range(-3, 4):
            state = {"id": "minecraft:oak_planks", "properties": {}}
            proposals.append({"position": [x, 0, z], "state": state, "occupancyConfidence": 0.98, "materialConfidence": 0.92, "evidence": [{"kind": "multi_view_surface", "strength": 0.95, "details": {"demo": True}}]})
    for y in range(1, 4):
        for x in range(-3, 4):
            for z in (-3, 3):
                proposals.append({"position": [x, y, z], "state": {"id": "minecraft:stone_bricks", "properties": {}}, "occupancyConfidence": 0.94, "materialConfidence": 0.87, "evidence": [{"kind": "depth_surface", "strength": 0.9, "details": {"demo": True}}]})
        for z in range(-2, 3):
            for x in (-3, 3):
                if not (x == 3 and z == 0 and y < 3):
                    proposals.append({"position": [x, y, z], "state": {"id": "minecraft:stone_bricks", "properties": {}}, "occupancyConfidence": 0.94, "materialConfidence": 0.87, "evidence": [{"kind": "depth_surface", "strength": 0.9, "details": {"demo": True}}]})
    for x in range(-4, 5):
        for z in range(-4, 5):
            if abs(x) + abs(z) <= 6:
                proposals.append({"position": [x, 4, z], "state": {"id": "minecraft:dark_oak_planks", "properties": {}}, "occupancyConfidence": 0.89, "materialConfidence": 0.76, "evidence": [{"kind": "multi_view_surface", "strength": 0.82, "details": {"demo": True}}]})
    return proposals


class EngineService:
    def dispatch(self, method: str, params: dict[str, Any] | None = None) -> Any:
        p = params or {}
        if method == "engine.ping":
            return {"ok": True, "protocol": 1}
        if method == "engine.capabilities":
            return capabilities()
        if method == "project.create":
            project = ProjectStore.create(p["path"], p.get("name", "Untitled Reconstruction"), p.get("minecraftVersion", "26.2"), p.get("source"))
            return {"path": str(project.root), "config": project.config(), "summary": project.summary()}
        if method == "project.open":
            project = _project(p)
            return {"path": str(project.root), "config": project.config(), "summary": project.summary()}
        if method == "project.validate":
            project = _project(p)
            return {"valid": True, "config": project.config(), "summary": project.summary()}
        if method == "project.migrate":
            project = _project(p)
            return {"migrated": False, "schemaVersion": project.config()["schemaVersion"]}
        if method == "project.compact":
            return _project(p).compact()
        if method == "assets.list_supported":
            return {"catalogSha256": catalog_digest(), "versions": assets.status(p.get("assetRoot"))}
        if method == "assets.download":
            return assets.download(p["version"], p.get("assetRoot"))
        if method == "assets.verify":
            installed = next((item for item in assets.status(p.get("assetRoot")) if item["id"] == p["version"]), None)
            return {"version": p["version"], "valid": bool(installed and installed["installed"]), "details": installed}
        if method == "assets.remove":
            return assets.remove(p["version"], p.get("assetRoot"))
        if method == "assets.resolve_blockstate":
            resolver = VanillaModelResolver(p["assetPath"])
            return resolver.canonical_template(p["blockId"], p.get("properties", {}))
        if method == "source.inspect":
            return media.inspect(p["path"])
        if method == "source.import_local":
            return media.import_local(_project(p), p["sourcePath"], p.get("trim"))
        if method == "source.inspect_images":
            return media.inspect_images(p["path"])
        if method == "source.import_images":
            return media.import_images(_project(p), p["sourcePath"])
        if method == "source.fetch_youtube":
            return media.fetch_youtube(_project(p), p["url"], bool(p.get("rightsAcknowledged")))
        if method == "source.trim":
            project = _project(p)
            trim = p["trim"]
            if float(trim["end"]) - float(trim["start"]) > 1800:
                raise ValidationError("trim must not exceed 30 minutes")
            return project.update_config({"trims": trim})
        if method == "source.mask":
            project = _project(p)
            config = project.config()
            return project.update_config({"masks": [*config.get("masks", []), p["mask"]]})
        if method == "jobs.start":
            return JobManager(_project(p)).start(p["kind"], p.get("request"))
        if method == "jobs.advance":
            return JobManager(_project(p)).advance(p["jobId"])
        if method == "jobs.pause":
            return JobManager(_project(p)).pause(p["jobId"])
        if method == "jobs.cancel":
            return JobManager(_project(p)).cancel(p["jobId"])
        if method == "jobs.resume":
            return JobManager(_project(p)).resume(p["jobId"])
        if method == "jobs.inspect":
            return JobManager(_project(p)).inspect(p["jobId"])
        if method == "jobs.list":
            return JobManager(_project(p)).list()
        if method in {"calibration.submit_scale_anchors", "calibration.submit_axes", "calibration.submit_crop", "calibration.submit_segment_alignment"}:
            project = _project(p)
            config = project.config()
            calibration = dict(config.get("calibration", {}))
            calibration[method.rsplit("_", 1)[-1]] = p.get("value") or {key: value for key, value in p.items() if key != "project"}
            return project.update_config({"calibration": calibration})["calibration"]
        if method == "scene.voxels":
            project = _project(p)
            return {"voxels": project.voxels(bool(p.get("includeEvidence"))), "summary": project.summary()}
        if method == "scene.camera_paths":
            project = _project(p)
            with project.connect() as db:
                rows = db.execute("SELECT f.id,f.timestamp,f.segment,c.pose_json,c.intrinsics_json,c.confidence FROM frames f JOIN cameras c ON c.frame_id=f.id ORDER BY f.timestamp").fetchall()
            import json
            return [{"frameId": row[0], "timestamp": row[1], "segment": row[2], "pose": json.loads(row[3]), "intrinsics": json.loads(row[4]), "confidence": row[5]} for row in rows]
        if method == "scene.evidence":
            position = list(map(int, p["position"]))
            matches = [v for v in _project(p).voxels(True) if v["position"] == position]
            return matches[0] if matches else None
        if method == "editing.paint":
            return _project(p).edit(p["position"], p["state"], "paint")
        if method == "editing.erase":
            return _project(p).edit(p["position"], AIR, "erase")
        if method == "editing.reset":
            return _project(p).edit(p["position"], None, "reset")
        if method == "editing.undo":
            return _project(p).undo()
        if method == "editing.redo":
            return _project(p).redo()
        if method == "export.validate":
            data = Path(p["path"]).expanduser().read_bytes()
            return validate_litematic(data)
        if method == "export.write":
            project = _project(p)
            destination = p.get("destination") or str(project.root / "exports" / f"{project.config()['name']}.litematic")
            return export_project(project, destination, p.get("author", "LiteMaptica"))
        if method == "development.load_demo":
            project = _project(p)
            count = project.replace_automated(demo_proposals(), project.pipeline_hash("demo", {"fixture": 1}))
            return {"blocks": count, "summary": project.summary()}
        raise ValidationError(f"unknown engine method: {method}")
