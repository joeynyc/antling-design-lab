"""Source-size exports reuse original pixels without a second model run."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from web import server


class SourceCutoutTests(unittest.TestCase):
    def test_existing_low_resolution_split_exports_source_size_cutouts(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = "c" * 32
            job_dir = Path(directory) / job_id
            job_dir.mkdir()
            source = Image.new("RGB", (8, 8))
            for y in range(8):
                for x in range(8):
                    source.putpixel((x, y), (x * 20, y * 20, 90))
            source.save(job_dir / "input.png")
            foreground = Image.new("RGBA", (2, 2), (255, 0, 0, 0))
            foreground.putpixel((0, 0), (255, 0, 0, 255))
            foreground.save(job_dir / "layer_01.png")
            Image.new("RGBA", (2, 2), (0, 0, 255, 255)).save(job_dir / "layer_02.png")
            job = {
                "id": job_id,
                "kind": "layers",
                "status": "done",
                "input_size": [8, 8],
                "metrics": {"output_size": [2, 2]},
                "layers": ["Foreground", "Background"],
            }

            with (
                patch.object(server, "JOBS_DIR", Path(directory)),
                patch.object(server.runtime, "get_job", return_value=job),
            ):
                self.assertIn("source_zip_url", server.public_job(job))
                response = TestClient(server.app, base_url="http://127.0.0.1").get(
                    f"/api/jobs/{job_id}/assets/source-cutouts.zip"
                )
                self.assertEqual(response.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    self.assertEqual(
                        set(archive.namelist()),
                        {"README.txt", "original.png", "source_layer_01.png", "source_layer_02.png"},
                    )
                    layers = [
                        Image.open(io.BytesIO(archive.read(f"source_layer_{i:02d}.png"))).convert("RGBA")
                        for i in (1, 2)
                    ]
                    self.assertEqual(layers[0].size, source.size)
                    self.assertEqual(layers[0].getpixel((0, 0))[:3], source.getpixel((0, 0)))
                    composite = Image.alpha_composite(layers[1], layers[0]).convert("RGB")
                    self.assertEqual(composite.tobytes(), source.tobytes())

    def test_same_size_split_has_no_source_cutout_export(self):
        self.assertFalse(server.source_cutouts_available({
            "kind": "layers", "status": "done", "input_size": [512, 512],
            "metrics": {"output_size": [512, 512]},
        }))


if __name__ == "__main__":
    unittest.main()
