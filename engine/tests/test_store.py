import json
import tempfile
import unittest
from pathlib import Path

from litemap_engine.errors import ValidationError
from litemap_engine.store import ProjectStore


def proposal(position=(0, 0, 0), block="minecraft:stone"):
    return {
        "position": list(position),
        "state": {"id": block, "properties": {}},
        "occupancyConfidence": 0.95,
        "materialConfidence": 0.81,
        "alternatives": [],
        "evidence": [{"kind": "depth_surface", "strength": 0.9}],
    }


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "test.litemap"
        self.store = ProjectStore.create(self.path, "Test", "1.21.4")

    def tearDown(self):
        self.temporary.cleanup()

    def test_project_layout_and_validation(self):
        self.assertEqual(self.store.config()["targetJavaVersion"], "1.21.4")
        for name in ("source", "frames", "artifacts", "previews", "exports", "cache"):
            self.assertTrue((self.path / name).is_dir())
        self.assertTrue(self.store.ensure_valid())

    def test_creation_rejects_existing_file_and_nonempty_directory(self):
        existing_file = Path(self.temporary.name) / "file.litemap"
        existing_file.write_text("not a project", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "existing file"):
            ProjectStore.create(existing_file, "Invalid", "1.21.4")

        nonempty = Path(self.temporary.name) / "nonempty.litemap"
        nonempty.mkdir()
        (nonempty / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "not empty"):
            ProjectStore.create(nonempty, "Invalid", "1.21.4")
        self.assertEqual((nonempty / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_creation_rejects_invalid_suffix_without_partial_output(self):
        invalid = Path(self.temporary.name) / "bad-project"
        with self.assertRaisesRegex(ValidationError, "end in .litemap"):
            ProjectStore.create(invalid, "Invalid", "1.21.4")
        self.assertFalse(invalid.exists())

    def test_automation_requires_evidence_atomically(self):
        self.store.replace_automated([proposal()], "first")
        invalid = proposal((1, 0, 0))
        invalid["evidence"] = []
        with self.assertRaises(ValidationError):
            self.store.replace_automated([invalid], "second")
        self.assertEqual(len(self.store.voxels()), 1)

    def test_manual_edit_undo_redo_reset(self):
        self.store.replace_automated([proposal()], "first")
        self.store.edit([0, 0, 0], {"id": "minecraft:bricks", "properties": {}}, "paint")
        self.assertEqual(self.store.voxels()[0]["state"]["id"], "minecraft:bricks")
        self.store.undo()
        self.assertEqual(self.store.voxels()[0]["state"]["id"], "minecraft:stone")
        self.store.redo()
        self.assertEqual(self.store.voxels()[0]["state"]["id"], "minecraft:bricks")
        self.store.edit([0, 0, 0], None, "reset")
        self.assertEqual(self.store.voxels()[0]["state"]["id"], "minecraft:stone")

    def test_edits_survive_automated_replacement(self):
        self.store.replace_automated([proposal()], "first")
        self.store.edit([0, 0, 0], {"id": "minecraft:glass", "properties": {}}, "paint")
        self.store.replace_automated([proposal(block="minecraft:dirt")], "second")
        voxel = self.store.voxels()[0]
        self.assertEqual(voxel["state"]["id"], "minecraft:glass")
        self.assertTrue(voxel["manual"])

    def test_pipeline_hash_invalidates_changed_inputs(self):
        first = self.store.pipeline_hash("grid", {"scale": 1})
        second = self.store.pipeline_hash("grid", {"scale": 2})
        self.assertNotEqual(first, second)
        self.assertEqual(first, self.store.pipeline_hash("grid", {"scale": 1}))


if __name__ == "__main__":
    unittest.main()
