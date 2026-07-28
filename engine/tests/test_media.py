import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from litemap_engine import media
from litemap_engine.errors import ValidationError
from litemap_engine.store import ProjectStore


class MediaTests(unittest.TestCase):
    PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.store = ProjectStore.create(root / "video.litemap", "Video", "1.21.4")
        self.first = root / "first.mp4"
        self.first.write_bytes(b"first video")

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def metadata(path, duration=120):
        return {"path": str(path), "bytes": path.stat().st_size, "duration": duration, "width": 1920, "height": 1080, "requiresTrim": duration > 1800}

    def test_reimport_atomically_replaces_and_removes_previous_source(self):
        with patch("litemap_engine.media.inspect", side_effect=lambda path: self.metadata(Path(path))):
            first_result = media.import_local(self.store, self.first)
            second = Path(self.temporary.name) / "second.mov"
            second.write_bytes(b"second video")
            second_result = media.import_local(self.store, second)
        self.assertFalse(Path(first_result["managedPath"]).exists())
        self.assertEqual(Path(second_result["managedPath"]).read_bytes(), b"second video")
        self.assertEqual(self.store.config()["source"]["originalName"], "second.mov")

    def test_copy_failure_preserves_previous_managed_source(self):
        with patch("litemap_engine.media.inspect", side_effect=lambda path: self.metadata(Path(path))):
            result = media.import_local(self.store, self.first)
            replacement = Path(self.temporary.name) / "replacement.mp4"
            replacement.write_bytes(b"replacement")
            with patch("litemap_engine.media.shutil.copy2", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    media.import_local(self.store, replacement)
        self.assertEqual(Path(result["managedPath"]).read_bytes(), b"first video")
        self.assertEqual(self.store.config()["source"]["originalName"], "first.mp4")

    def test_oversized_footage_requires_a_valid_trim(self):
        with patch("litemap_engine.media.inspect", return_value=self.metadata(self.first, 2000)):
            with self.assertRaisesRegex(ValidationError, "must be trimmed"):
                media.import_local(self.store, self.first)
            with self.assertRaisesRegex(ValidationError, "video duration"):
                media.import_local(self.store, self.first, {"start": 100, "end": 2100})
            with self.assertRaisesRegex(ValidationError, "30 minutes"):
                media.import_local(self.store, self.first, {"start": 0, "end": 1801})
            result = media.import_local(self.store, self.first, {"start": 100, "end": 1900})
        self.assertTrue(Path(result["managedPath"]).is_file())
        self.assertEqual(self.store.config()["trims"], {"start": 100.0, "end": 1900.0})

    def test_inspect_rejects_unsupported_extensions(self):
        unsupported = Path(self.temporary.name) / "source.avi"
        unsupported.write_bytes(b"video")
        with self.assertRaisesRegex(ValidationError, "MP4, MOV, or WebM"):
            media.inspect(unsupported)

    def picture_folder(self, name="pictures", filenames=("view10.png", "view2.png", "view1.png")):
        folder = Path(self.temporary.name) / name
        folder.mkdir()
        for filename in filenames:
            (folder / filename).write_bytes(self.PNG)
        return folder

    def test_picture_folder_import_registers_naturally_ordered_frames(self):
        folder = self.picture_folder()
        (folder / "notes.txt").write_text("ignored", encoding="utf-8")
        metadata = media.inspect_images(folder)
        self.assertEqual(metadata["count"], 3)
        self.assertEqual((metadata["width"], metadata["height"]), (1, 1))

        result = media.import_images(self.store, folder)
        self.assertEqual(result["frameCount"], 3)
        self.assertEqual(self.store.summary()["frameCount"], 3)
        with self.store.connect() as db:
            rows = db.execute("SELECT path,metadata_json FROM frames ORDER BY timestamp").fetchall()
        self.assertEqual([json.loads(row["metadata_json"])["originalName"] for row in rows], ["view1.png", "view2.png", "view10.png"])
        self.assertTrue(all((self.store.root / row["path"]).is_file() for row in rows))
        self.assertEqual(self.store.config()["source"]["kind"], "image_folder")

    def test_empty_picture_folder_is_rejected(self):
        folder = Path(self.temporary.name) / "empty"
        folder.mkdir()
        with self.assertRaisesRegex(ValidationError, "contains no"):
            media.inspect_images(folder)

        (folder / "only.png").write_bytes(self.PNG)
        with self.assertRaisesRegex(ValidationError, "at least two"):
            media.inspect_images(folder)

    def test_failed_picture_reimport_preserves_existing_frames_and_files(self):
        first = self.picture_folder("first-pictures", ("one.png", "two.png"))
        media.import_images(self.store, first)
        managed = self.store.root / self.store.config()["source"]["managedPath"]
        previous_files = sorted(path.read_bytes() for path in managed.iterdir())
        replacement = self.picture_folder("replacement-pictures", ("three.png", "four.png"))
        with patch("litemap_engine.media.shutil.copy2", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                media.import_images(self.store, replacement)
        self.assertEqual(self.store.summary()["frameCount"], 2)
        self.assertEqual(self.store.config()["source"]["originalName"], "first-pictures")
        self.assertEqual(sorted(path.read_bytes() for path in managed.iterdir()), previous_files)

    def test_video_replacement_clears_picture_frames_and_managed_folder(self):
        folder = self.picture_folder("replace-me", ("one.png", "two.png"))
        imported = media.import_images(self.store, folder)
        managed_folder = Path(imported["managedPath"])
        with patch("litemap_engine.media.inspect", side_effect=lambda path: self.metadata(Path(path))):
            media.import_local(self.store, self.first)
        self.assertFalse(managed_folder.exists())
        self.assertEqual(self.store.summary()["frameCount"], 0)
        self.assertEqual(self.store.config()["source"]["kind"], "local")


if __name__ == "__main__":
    unittest.main()
