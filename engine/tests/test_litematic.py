import tempfile
import unittest
from pathlib import Path

from litemap_engine.litematic import export_project, pack_palette_indices, read_litematic, unpack_palette_indices, validate_litematic
from litemap_engine.store import ProjectStore


class LitematicTests(unittest.TestCase):
    def test_bit_packing_crosses_long_boundaries(self):
        indices = [(index * 7) % 17 for index in range(113)]
        bits, words = pack_palette_indices(indices, 17)
        self.assertEqual(bits, 5)
        self.assertEqual(unpack_palette_indices(words, len(indices), 17), indices)

    def test_export_round_trip_and_trim(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore.create(Path(temporary) / "export.litemap", "Round Trip", "1.21.4")
            proposals = []
            for position, block in [((-2, 4, 6), "minecraft:stone"), ((0, 5, 7), "minecraft:oak_stairs")]:
                proposals.append({"position": position, "state": {"id": block, "properties": {"facing": "north"} if "stairs" in block else {}}, "occupancyConfidence": 0.9, "materialConfidence": 0.8, "evidence": [{"kind": "surface", "strength": 1}]})
            store.replace_automated(proposals, "fixture")
            destination = Path(temporary) / "result.litematic"
            report = export_project(store, destination)
            self.assertEqual(report["size"], [3, 2, 2])
            self.assertEqual(report["blocks"], 2)
            validated = validate_litematic(destination.read_bytes())
            self.assertTrue(validated["valid"])
            root = read_litematic(destination.read_bytes())
            self.assertEqual(root["Regions"]["Reconstruction"]["Position"], {"x": -2, "y": 4, "z": 6})
            self.assertEqual(root["Regions"]["Reconstruction"]["BlockStatePalette"][2]["Properties"]["facing"], "north")

    def test_26_2_export_uses_current_minecraft_data_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore.create(Path(temporary) / "current.litemap", "Current", "26.2")
            store.replace_automated([{
                "position": [0, 0, 0],
                "state": {"id": "minecraft:stone", "properties": {}},
                "occupancyConfidence": 1,
                "materialConfidence": 1,
                "evidence": [{"kind": "surface", "strength": 1}],
            }], "fixture")
            exported = Path(temporary) / "current.litematic"
            report = export_project(store, exported)
            root = read_litematic(exported.read_bytes())
            self.assertEqual(report["dataVersion"], 4903)
            self.assertEqual(root["MinecraftDataVersion"], 4903)


if __name__ == "__main__":
    unittest.main()
