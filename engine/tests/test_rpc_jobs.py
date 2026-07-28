import json
import tempfile
import unittest
from pathlib import Path

from litemap_engine.rpc import response
from litemap_engine.service import EngineService


class RpcAndJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temporary.name) / "rpc.litemap")
        self.service = EngineService()
        self.service.dispatch("project.create", {"path": self.path, "name": "RPC", "minecraftVersion": "1.20.4"})

    def tearDown(self):
        self.temporary.cleanup()

    def test_json_rpc_success_and_expected_error(self):
        success = response(self.service, {"jsonrpc": "2.0", "id": 1, "method": "engine.ping"})
        self.assertEqual(success["result"]["protocol"], 1)
        failure = response(self.service, {"jsonrpc": "2.0", "id": 2, "method": "not.real"})
        self.assertEqual(failure["error"]["code"], -32020)

    def test_job_lifecycle_is_persistent_and_cancel_safe(self):
        job = self.service.dispatch("jobs.start", {"project": self.path, "kind": "quality_report"})
        self.assertEqual(job["status"], "queued")
        cancelled = self.service.dispatch("jobs.cancel", {"project": self.path, "jobId": job["id"]})
        self.assertEqual(cancelled["status"], "cancelled")
        inspected = self.service.dispatch("jobs.inspect", {"project": self.path, "jobId": job["id"]})
        self.assertEqual(inspected["status"], "cancelled")

    def test_calibration_is_transactionally_stored(self):
        calibration = self.service.dispatch("calibration.submit_scale_anchors", {"project": self.path, "value": {"a": [0, 0], "b": [16, 0]}})
        self.assertIn("anchors", calibration)
        opened = self.service.dispatch("project.open", {"project": self.path})
        self.assertEqual(opened["config"]["calibration"]["anchors"]["b"], [16, 0])


if __name__ == "__main__":
    unittest.main()
