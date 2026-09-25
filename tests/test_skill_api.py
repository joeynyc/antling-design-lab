"""Contract checks for the two published inclusionAI skill clients."""

import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from web import server


class SkillApiTests(unittest.TestCase):
    def test_both_published_layer_plan_formats(self):
        self.assertEqual(
            server.parse_skill_layers(
                "Number of layers: 2\nLayer 1 (text): Headline only.\nLayer 2 (background): Blue field."
            ),
            ["text: Headline only.", "background: Blue field."],
        )
        self.assertEqual(
            server.parse_skill_layers("2 layers: 1 headline only, 2 blue background"),
            ["headline only", "blue background"],
        )
        with self.assertRaises(HTTPException):
            server.parse_skill_layers("2 layers: 1 headline only, 3 blue background")
        with self.assertRaises(HTTPException):
            server.parse_skill_layers(
                "Number of layers: 3\nLayer 1: Headline only.\nLayer 2: Blue field."
            )

    def test_generation_returns_image_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = "a" * 32
            job_dir = Path(directory) / job_id
            job_dir.mkdir()
            Image.new("RGB", (64, 64), "red").save(job_dir / "design.png")
            with (
                patch.object(server, "JOBS_DIR", Path(directory)),
                patch.object(server, "create_design_job", return_value={"id": job_id}),
                patch.object(server.runtime, "get_job", return_value={"id": job_id, "status": "done"}),
            ):
                response = TestClient(server.app, base_url="http://127.0.0.1").post(
                    "/v1/images/generations",
                    json={
                        "model": "ming-image-0.1-design",
                        "prompt": "A red editorial poster",
                        "output_format": "jpeg",
                    },
                )
            self.assertEqual(response.status_code, 200)
            raw = base64.b64decode(response.json()["data"][0]["b64_json"])
            self.assertTrue(raw.startswith(b"\xff\xd8"))

    def test_codex_prompt_keeps_original_visible_and_structured_input_private(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(server, "JOBS_DIR", Path(directory)),
                patch.object(server.runtime, "add_job") as add_job,
            ):
                response = TestClient(server.app, base_url="http://127.0.0.1").post(
                    "/api/design-jobs",
                    data={
                        "prompt": '{"canvas_settings": {}, "layers": []}',
                        "source_prompt": "A local AI landing page",
                        "enhancement": "codex",
                        "resolution": "2048",
                        "rewrite_seconds": "22.5",
                    },
                )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["design_prompt"], "A local AI landing page")
            self.assertNotIn("generation_prompt", response.json())
            queued = add_job.call_args.args[0]
            self.assertEqual(queued["generation_prompt"], '{"canvas_settings": {}, "layers": []}')
            self.assertEqual(queued["resolution"], 2048)
            self.assertEqual(queued["rewrite_seconds"], 22.5)

    def test_edit_returns_ordered_rgba_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = "b" * 32
            job_dir = Path(directory) / job_id
            job_dir.mkdir()
            source = io.BytesIO()
            Image.new("RGB", (64, 64), "white").save(source, format="PNG")
            for index in (1, 2):
                Image.new("RGBA", (64, 64), (index, 0, 0, 255)).save(
                    job_dir / f"layer_{index:02d}.png"
                )
            create = AsyncMock(return_value={"id": job_id})
            with (
                patch.object(server, "JOBS_DIR", Path(directory)),
                patch.object(server, "create_job", create),
                patch.object(server.runtime, "get_job", return_value={"id": job_id, "status": "done", "resolution": 512}),
            ):
                response = TestClient(server.app, base_url="http://127.0.0.1").post(
                    "/v1/images/edits",
                    data={
                        "model": "ming-image-0.1-design-layer",
                        "prompt": "2 layers: 1 headline only, 2 blue background",
                        "size": "auto",
                        "num_inference_steps": "14",
                    },
                    files={"image": ("source.png", source.getvalue(), "image/png")},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["data"]), 2)
            self.assertEqual(response.json()["actual_steps"], 12)
            self.assertEqual(create.await_args.kwargs["resolution"], 512)


if __name__ == "__main__":
    unittest.main()
