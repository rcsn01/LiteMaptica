from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .store import ProjectStore


STAGES = ["preflight", "keyframes", "sparse", "dense", "grid", "occupancy", "block_solving", "report"]


def capabilities() -> dict[str, Any]:
    binaries = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "yt-dlp", "colmap", "OpenMVS")}
    try:
        import platform

        native_arm64 = platform.machine() == "arm64"
    except Exception:
        native_arm64 = False
    return {
        "nativeArm64": native_arm64,
        "binaries": binaries,
        "cameraMatching": "sift-fallback" if binaries["colmap"] else "unavailable",
        "denseGeometry": "openmvs" if binaries["OpenMVS"] else "unavailable",
        "depthPrior": "unavailable",
        "blockSolver": "foundation-contract",
        "completeReconstructionAvailable": bool(binaries["ffmpeg"] and binaries["colmap"] and binaries["OpenMVS"]),
    }


class JobManager:
    def __init__(self, project: ProjectStore):
        project.ensure_valid()
        self.project = project

    def start(self, kind: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        if kind not in {"reconstruct", "quality_report", "export"}:
            raise ValidationError(f"unknown job kind {kind!r}")
        job_id = str(uuid.uuid4())
        now = int(time.time() * 1000)
        report = {"events": [{"type": "progress", "stage": "preflight", "message": "Job accepted"}]}
        with self.project.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)", (job_id, kind, "queued", "preflight", 0.0, json.dumps(request or {}), json.dumps(report), now, now))
        return self.inspect(job_id)

    def advance(self, job_id: str) -> dict[str, Any]:
        job = self.inspect(job_id)
        if job["status"] in {"cancelled", "completed", "failed"}:
            return job
        if job["status"] == "paused":
            raise ValidationError("resume the job before advancing it")
        stage = job["stage"]
        stage_index = STAGES.index(stage)
        report = job["report"]
        if stage == "preflight":
            usage = shutil.disk_usage(self.project.root)
            report["preflight"] = {"diskFreeBytes": usage.free, "memoryLimitGuidanceBytes": 16 * 1024**3, "capabilities": capabilities()}
            if usage.free < 2 * 1024**3:
                return self._update(job_id, "failed", stage, job["progress"], report, {"type": "fatal_failure", "message": "At least 2 GB free disk is required for this job"})
            if self.project.config().get("source") is None and job["kind"] != "export":
                return self._update(job_id, "failed", stage, job["progress"], report, {"type": "fatal_failure", "message": "Import source video or pictures before analysis"})
        if job["kind"] == "reconstruct" and stage == "sparse" and not capabilities()["completeReconstructionAvailable"]:
            return self._update(job_id, "paused", stage, job["progress"], report, {"type": "recoverable_failure", "message": "Packaged COLMAP/OpenMVS capabilities are not installed in this development build"})
        pipeline_hash = self.project.pipeline_hash(stage, job["request"])
        with self.project.connect() as db:
            db.execute("INSERT OR REPLACE INTO checkpoints VALUES(?,?,?,?,?)", (job_id, stage, pipeline_hash, "{}", int(time.time() * 1000)))
        if stage_index == len(STAGES) - 1 or job["kind"] in {"quality_report", "export"}:
            report["summary"] = self.project.summary()
            return self._update(job_id, "completed", stage, 1.0, report, {"type": "completion", "message": "Job completed"})
        next_stage = STAGES[stage_index + 1]
        return self._update(job_id, "running", next_stage, (stage_index + 1) / len(STAGES), report, {"type": "progress", "stage": next_stage})

    def pause(self, job_id: str) -> dict[str, Any]:
        job = self.inspect(job_id)
        return self._update(job_id, "paused", job["stage"], job["progress"], job["report"], {"type": "warning", "message": "Job paused at checkpoint boundary"})

    def resume(self, job_id: str) -> dict[str, Any]:
        job = self.inspect(job_id)
        if job["status"] != "paused":
            raise ValidationError("only paused jobs can be resumed")
        return self._update(job_id, "queued", job["stage"], job["progress"], job["report"], {"type": "progress", "message": "Job resumed"})

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = self.inspect(job_id)
        return self._update(job_id, "cancelled", job["stage"], job["progress"], job["report"], {"type": "cancellation", "message": "Job cancelled; completed checkpoints were retained"})

    def _update(self, job_id: str, status: str, stage: str, progress: float, report: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        report.setdefault("events", []).append(event)
        with self.project.connect() as db:
            db.execute("UPDATE jobs SET status=?,stage=?,progress=?,report_json=?,updated_at=? WHERE id=?", (status, stage, progress, json.dumps(report), int(time.time() * 1000), job_id))
        return self.inspect(job_id)

    def inspect(self, job_id: str) -> dict[str, Any]:
        with self.project.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValidationError(f"job not found: {job_id}")
        return {"id": row["id"], "kind": row["kind"], "status": row["status"], "stage": row["stage"], "progress": row["progress"], "request": json.loads(row["request_json"]), "report": json.loads(row["report_json"]), "createdAt": row["created_at"], "updatedAt": row["updated_at"]}

    def list(self) -> list[dict[str, Any]]:
        with self.project.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM jobs ORDER BY created_at DESC")]
        return [self.inspect(job_id) for job_id in ids]
