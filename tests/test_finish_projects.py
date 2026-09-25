"""Finish projects persist editor state without starting a GPU job."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web import server


class FinishProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.job = {
            "id": "a" * 32,
            "kind": "layers",
            "status": "done",
            "layers": ["Monitor", "Background"],
            "input_size": [2048, 2048],
            "metrics": {"output_size": [1024, 1024]},
        }
        self.patch_root = patch.object(server, "PROJECTS_DIR", Path(self.directory.name))
        self.patch_job = patch.object(server.runtime, "get_job", return_value=self.job)
        self.patch_root.start()
        self.patch_job.start()
        self.addCleanup(self.patch_root.stop)
        self.addCleanup(self.patch_job.stop)
        self.client = TestClient(server.app)

    def document(self):
        return {
            "title": "Studio X graphic", "source_job_id": self.job["id"],
            "size": "landscape", "focal_x": 0.5, "focal_y": 0.65,
            "elements": [{"id": "headline", "type": "text", "text": "Local AI, put to work",
                          "x": 100, "y": 260, "font_size": 90, "color": "#ffffff", "weight": 700}],
        }

    def test_create_update_and_reopen_after_new_client(self):
        created = self.client.post("/api/projects", json=self.document())
        self.assertEqual(created.status_code, 201, created.text)
        project = created.json()
        self.assertEqual(project["title"], "Studio X graphic")
        self.assertEqual(len(self.client.get("/api/projects").json()), 1)
        project["elements"][0]["text"] = "A real headline"
        updated = self.client.put(f"/api/projects/{project['id']}", json=project)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(TestClient(server.app).get(f"/api/projects/{project['id']}").json()["elements"][0]["text"], "A real headline")

    def test_invalid_source_and_unsafe_editor_data_are_rejected(self):
        bad = self.document()
        bad["elements"][0]["color"] = "url(javascript:alert(1))"
        self.assertEqual(self.client.post("/api/projects", json=bad).status_code, 422)
        bad = self.document()
        bad["source_job_id"] = "not-a-job"
        self.assertEqual(self.client.post("/api/projects", json=bad).status_code, 422)
        self.assertEqual(self.client.get("/api/projects/../../etc/passwd").status_code, 404)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_layer_cleanup_and_solid_background_survive_reopen(self):
        document = self.document()
        document.update(background="solid", background_color="#151728")
        document["elements"] = [{
            "id": "screen", "type": "layer", "layer_index": 0,
            "x": 450, "y": 180, "width": 680, "height": 520,
            "erase": [{"radius": 12, "points": [[0.02, 0.03], [0.04, 0.03]]}],
        }]
        created = self.client.post("/api/projects", json=document)
        self.assertEqual(created.status_code, 201, created.text)
        restored = TestClient(server.app).get(f"/api/projects/{created.json()['id']}").json()
        self.assertEqual(restored["background"], "solid")
        self.assertEqual(restored["elements"][0]["erase"][0]["points"][1], [0.04, 0.03])


if __name__ == "__main__":
    unittest.main()
