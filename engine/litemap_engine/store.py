from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import SCHEMA_VERSION
from .catalog import catalog_digest, version_info
from .errors import InvalidProject, ValidationError


AIR = {"id": "minecraft:air", "properties": {}}
PROJECT_DIRS = ("source", "frames", "artifacts", "previews", "exports", "cache")


def canonical_state(state: dict[str, Any]) -> dict[str, Any]:
    block_id = str(state.get("id", ""))
    if not block_id or ":" not in block_id:
        raise ValidationError("block state id must be namespaced, for example minecraft:stone")
    properties = state.get("properties", {})
    if not isinstance(properties, dict):
        raise ValidationError("block state properties must be an object")
    return {"id": block_id, "properties": {str(k): str(v) for k, v in sorted(properties.items())}}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class ProjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.config_path = self.root / "project.json"
        self.db_path = self.root / "project.sqlite3"

    @classmethod
    def create(cls, root: str | Path, name: str, minecraft_version: str, source: dict[str, Any] | None = None) -> "ProjectStore":
        path = Path(root).expanduser().resolve()
        if path.suffix != ".litemap":
            raise ValidationError("project directory must end in .litemap")
        existed_empty = False
        if path.exists():
            if not path.is_dir():
                raise ValidationError(f"project destination is an existing file: {path}")
            if any(path.iterdir()):
                raise ValidationError(f"project directory is not empty: {path}")
            existed_empty = True
        if not path.parent.is_dir():
            raise ValidationError(f"project parent directory does not exist: {path.parent}")
        info = version_info(minecraft_version)
        staging = path.parent / f".{path.name}.{uuid.uuid4().hex}.creating"
        try:
            staging.mkdir()
            for directory in PROJECT_DIRS:
                (staging / directory).mkdir()
            now = int(time.time() * 1000)
            config = {
                "schemaVersion": SCHEMA_VERSION,
                "id": str(uuid.uuid4()),
                "name": name.strip() or "Untitled Reconstruction",
                "createdAt": now,
                "updatedAt": now,
                "source": source,
                "targetJavaVersion": minecraft_version,
                "minecraftDataVersion": info["data_version"],
                "catalogSha256": catalog_digest(),
                "trims": None,
                "masks": [],
                "calibration": {},
                "pipelineHashes": {},
            }
            (staging / "project.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            cls(staging)._initialize_db()
            if existed_empty:
                path.rmdir()
            staging.replace(path)
            return cls(path)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if existed_empty and not path.exists():
                path.mkdir()
            raise

    def ensure_valid(self) -> dict[str, Any]:
        if not self.root.is_dir() or not self.config_path.is_file() or not self.db_path.is_file():
            raise InvalidProject(f"not a LiteMaptica project: {self.root}")
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidProject(f"invalid project.json: {exc}") from exc
        if config.get("schemaVersion") != SCHEMA_VERSION:
            raise InvalidProject(f"unsupported project schema {config.get('schemaVersion')}; expected {SCHEMA_VERSION}")
        version_info(config.get("targetJavaVersion", ""))
        with self.connect() as db:
            result = db.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise InvalidProject(f"SQLite integrity check failed: {result}")
        return config

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _initialize_db(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO meta VALUES('schema_version', '1'), ('edit_cursor', '0');
                CREATE TABLE frames(
                    id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, path TEXT NOT NULL,
                    segment INTEGER NOT NULL DEFAULT 0, accepted INTEGER NOT NULL DEFAULT 1,
                    blur REAL, coverage REAL, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE cameras(
                    frame_id INTEGER PRIMARY KEY REFERENCES frames(id) ON DELETE CASCADE,
                    pose_json TEXT NOT NULL, intrinsics_json TEXT NOT NULL, confidence REAL NOT NULL
                );
                CREATE TABLE automated_voxels(
                    x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
                    state_json TEXT NOT NULL, occupancy_confidence REAL NOT NULL,
                    material_confidence REAL NOT NULL, alternatives_json TEXT NOT NULL DEFAULT '[]',
                    pipeline_hash TEXT NOT NULL, PRIMARY KEY(x,y,z)
                );
                CREATE TABLE evidence(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
                    frame_id INTEGER, kind TEXT NOT NULL, strength REAL NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(frame_id) REFERENCES frames(id) ON DELETE SET NULL,
                    FOREIGN KEY(x,y,z) REFERENCES automated_voxels(x,y,z) ON DELETE CASCADE
                );
                CREATE TABLE manual_overlay(
                    x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
                    state_json TEXT NOT NULL, PRIMARY KEY(x,y,z)
                );
                CREATE TABLE edit_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
                    before_json TEXT, after_json TEXT, kind TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE jobs(
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    progress REAL NOT NULL, request_json TEXT NOT NULL, report_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE checkpoints(
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    stage TEXT NOT NULL, pipeline_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                    completed_at INTEGER NOT NULL, PRIMARY KEY(job_id,stage)
                );
                CREATE INDEX evidence_position ON evidence(x,y,z);
                """
            )

    def config(self) -> dict[str, Any]:
        return self.ensure_valid()

    def update_config(self, changes: dict[str, Any]) -> dict[str, Any]:
        config = self.ensure_valid()
        immutable = {"schemaVersion", "id", "createdAt"}
        if immutable.intersection(changes):
            raise ValidationError("immutable project fields cannot be changed")
        config.update(changes)
        config["updatedAt"] = int(time.time() * 1000)
        temp = self.config_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.config_path)
        return config

    def compact(self) -> dict[str, Any]:
        self.ensure_valid()
        with self.connect() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with sqlite3.connect(self.db_path) as db:
            db.execute("VACUUM")
        removed = 0
        for path in (self.root / "cache").iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        return {"project": str(self.root), "cacheEntriesRemoved": removed}

    def replace_automated(self, proposals: list[dict[str, Any]], pipeline_hash: str) -> int:
        """Atomically replace automation. Every occupied proposal must carry evidence."""
        with self.connect() as db:
            db.execute("DELETE FROM evidence")
            db.execute("DELETE FROM automated_voxels")
            for proposal in proposals:
                position = proposal["position"]
                state = canonical_state(proposal["state"])
                if state["id"] == "minecraft:air":
                    continue
                evidence = proposal.get("evidence", [])
                if not evidence:
                    raise ValidationError(f"automated block at {position} has no stored evidence")
                x, y, z = map(int, position)
                occupancy = float(proposal.get("occupancyConfidence", 0))
                material = float(proposal.get("materialConfidence", 0))
                if not (0 <= occupancy <= 1 and 0 <= material <= 1):
                    raise ValidationError("confidence must be between zero and one")
                db.execute(
                    "INSERT INTO automated_voxels VALUES(?,?,?,?,?,?,?,?)",
                    (x, y, z, _json(state), occupancy, material, _json(proposal.get("alternatives", [])[:8]), pipeline_hash),
                )
                for item in evidence:
                    db.execute(
                        "INSERT INTO evidence(x,y,z,frame_id,kind,strength,details_json) VALUES(?,?,?,?,?,?,?)",
                        (x, y, z, item.get("frameId"), item.get("kind", "surface"), float(item.get("strength", 1)), _json(item.get("details", {}))),
                    )
        return len([p for p in proposals if p.get("state", {}).get("id") != "minecraft:air"])

    def _cursor(self, db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT value FROM meta WHERE key='edit_cursor'").fetchone()[0])

    def edit(self, position: list[int] | tuple[int, int, int], state: dict[str, Any] | None, kind: str) -> dict[str, Any]:
        x, y, z = map(int, position)
        after = None if state is None else _json(canonical_state(state))
        with self.connect() as db:
            cursor = self._cursor(db)
            db.execute("DELETE FROM edit_history WHERE id > ?", (cursor,))
            before_row = db.execute("SELECT state_json FROM manual_overlay WHERE x=? AND y=? AND z=?", (x, y, z)).fetchone()
            before = before_row[0] if before_row else None
            created = int(time.time() * 1000)
            result = db.execute(
                "INSERT INTO edit_history(x,y,z,before_json,after_json,kind,created_at) VALUES(?,?,?,?,?,?,?)",
                (x, y, z, before, after, kind, created),
            )
            edit_id = int(result.lastrowid)
            self._apply_overlay(db, x, y, z, after)
            db.execute("UPDATE meta SET value=? WHERE key='edit_cursor'", (str(edit_id),))
        return {"id": edit_id, "position": [x, y, z], "kind": kind, "state": None if after is None else json.loads(after)}

    @staticmethod
    def _apply_overlay(db: sqlite3.Connection, x: int, y: int, z: int, state_json: str | None) -> None:
        if state_json is None:
            db.execute("DELETE FROM manual_overlay WHERE x=? AND y=? AND z=?", (x, y, z))
        else:
            db.execute(
                "INSERT INTO manual_overlay VALUES(?,?,?,?) ON CONFLICT(x,y,z) DO UPDATE SET state_json=excluded.state_json",
                (x, y, z, state_json),
            )

    def undo(self) -> dict[str, Any] | None:
        with self.connect() as db:
            cursor = self._cursor(db)
            row = db.execute("SELECT * FROM edit_history WHERE id=?", (cursor,)).fetchone()
            if row is None:
                return None
            self._apply_overlay(db, row["x"], row["y"], row["z"], row["before_json"])
            previous = db.execute("SELECT COALESCE(MAX(id),0) FROM edit_history WHERE id < ?", (cursor,)).fetchone()[0]
            db.execute("UPDATE meta SET value=? WHERE key='edit_cursor'", (str(previous),))
            return {"id": cursor, "position": [row["x"], row["y"], row["z"]]}

    def redo(self) -> dict[str, Any] | None:
        with self.connect() as db:
            cursor = self._cursor(db)
            row = db.execute("SELECT * FROM edit_history WHERE id > ? ORDER BY id LIMIT 1", (cursor,)).fetchone()
            if row is None:
                return None
            self._apply_overlay(db, row["x"], row["y"], row["z"], row["after_json"])
            db.execute("UPDATE meta SET value=? WHERE key='edit_cursor'", (str(row["id"]),))
            return {"id": row["id"], "position": [row["x"], row["y"], row["z"]]}

    def voxels(self, include_evidence: bool = False) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT a.x,a.y,a.z,COALESCE(m.state_json,a.state_json) state_json,
                       a.occupancy_confidence,a.material_confidence,a.alternatives_json,
                       CASE WHEN m.state_json IS NULL THEN 0 ELSE 1 END manual
                FROM automated_voxels a LEFT JOIN manual_overlay m USING(x,y,z)
                UNION ALL
                SELECT m.x,m.y,m.z,m.state_json,1,1,'[]',1 FROM manual_overlay m
                WHERE NOT EXISTS(SELECT 1 FROM automated_voxels a WHERE a.x=m.x AND a.y=m.y AND a.z=m.z)
                ORDER BY x,y,z
                """
            ).fetchall()
            output = []
            for row in rows:
                state = json.loads(row["state_json"])
                if state["id"] == "minecraft:air":
                    continue
                item = {
                    "position": [row["x"], row["y"], row["z"]], "state": state,
                    "occupancyConfidence": row["occupancy_confidence"], "materialConfidence": row["material_confidence"],
                    "alternatives": json.loads(row["alternatives_json"]), "manual": bool(row["manual"]),
                }
                if include_evidence:
                    evidence = db.execute("SELECT frame_id,kind,strength,details_json FROM evidence WHERE x=? AND y=? AND z=?", tuple(item["position"])).fetchall()
                    item["evidence"] = [{"frameId": e[0], "kind": e[1], "strength": e[2], "details": json.loads(e[3])} for e in evidence]
                output.append(item)
            return output

    def summary(self) -> dict[str, Any]:
        voxels = self.voxels()
        low = sum(1 for v in voxels if min(v["occupancyConfidence"], v["materialConfidence"]) < 0.5)
        with self.connect() as db:
            frames = db.execute("SELECT COUNT(*), COALESCE(SUM(accepted),0) FROM frames").fetchone()
        return {"blockCount": len(voxels), "lowConfidenceBlocks": low, "frameCount": frames[0], "acceptedFrames": frames[1]}

    def pipeline_hash(self, stage: str, inputs: dict[str, Any]) -> str:
        config = self.config()
        payload = {"stage": stage, "inputs": inputs, "version": config["targetJavaVersion"], "schema": SCHEMA_VERSION}
        return hashlib.sha256(_json(payload).encode()).hexdigest()
