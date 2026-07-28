import json
import tempfile
import unittest
from pathlib import Path

from litemap_engine.vanilla import VanillaModelResolver


class VanillaResolverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name) / "assets/minecraft"
        (root / "blockstates").mkdir(parents=True)
        (root / "models/block").mkdir(parents=True)
        (root / "blockstates/test.json").write_text(json.dumps({
            "multipart": [
                {"when": {"north": "true"}, "apply": {"model": "minecraft:block/child", "y": 90, "uvlock": True}},
                {"when": {"OR": [{"lit": "true"}, {"powered": "true"}]}, "apply": [{"model": "minecraft:block/glow", "weight": 2}]},
            ]
        }))
        (root / "models/block/base.json").write_text(json.dumps({
            "textures": {"all": "minecraft:block/stone"},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {"north": {"texture": "#all", "uv": [0, 0, 16, 16]}}}]
        }))
        (root / "models/block/child.json").write_text(json.dumps({"parent": "minecraft:block/base", "textures": {"all": "minecraft:block/bricks"}}))
        (root / "models/block/glow.json").write_text(json.dumps({"parent": "minecraft:block/base"}))
        self.resolver = VanillaModelResolver(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_parent_texture_and_multipart_resolution(self):
        template = self.resolver.canonical_template("minecraft:test", {"north": "true", "lit": "true", "powered": "false"})
        self.assertEqual(len(template["models"]), 2)
        first = template["models"][0]
        self.assertTrue(first["application"]["uvlock"])
        self.assertEqual(first["application"]["y"], 90)
        self.assertEqual(first["elements"][0]["faces"]["north"]["texture"], "minecraft:block/bricks")
        self.assertEqual(len(template["geometrySignature"]), 64)

    def test_visual_property_enumeration(self):
        values = self.resolver.visual_property_values("minecraft:test")
        self.assertEqual(values, {"lit": ["true"], "north": ["true"], "powered": ["true"]})
        self.assertEqual(len(self.resolver.enumerate_visual_states("minecraft:test")), 1)


if __name__ == "__main__":
    unittest.main()
