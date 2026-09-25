"""Boundary checks for a loopback service that can start GPU and API jobs."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from web import server


class LocalAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app, base_url="http://127.0.0.1")

    def test_foreign_browser_cannot_start_jobs(self):
        with patch.object(server.runtime, "add_job") as queue:
            for headers in ({"Origin": "https://untrusted.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
                response = self.client.post("/api/design-jobs", data={"prompt": "A red poster"}, headers=headers)
                self.assertEqual(response.status_code, 403)
            queue.assert_not_called()

    def test_dns_rebinding_host_is_rejected(self):
        self.assertEqual(self.client.get("/", headers={"Host": "untrusted.example"}).status_code, 400)
        self.assertEqual(self.client.get("/", headers={"Host": "localhost.attacker.example"}).status_code, 400)

    def test_origin_must_match_scheme_host_and_port(self):
        for origin in ("http://127.0.0.1:9000", "https://127.0.0.1", "http://127.0.0.1@attacker.example", "http://127.0.0.1/path"):
            self.assertEqual(self.client.get("/api/jobs", headers={"Origin": origin}).status_code, 403)
        self.assertEqual(self.client.get("/", headers={"Host": "localhost:invalid"}).status_code, 400)

    def test_local_browser_and_native_client_are_allowed(self):
        for headers in ({}, {"Origin": "http://127.0.0.1"}):
            response = self.client.get("/api/prompt-providers", headers=headers)
            self.assertEqual(response.status_code, 200)
        response = self.client.get("/")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_request_limit_covers_declared_and_chunked_bodies(self):
        response = self.client.post("/api/projects", content=b"{}", headers={"Content-Length": str(5 * 1024 * 1024)})
        self.assertEqual(response.status_code, 413)
        chunks = (b"x" * (1024 * 1024) for _ in range(5))
        response = self.client.post("/api/projects", content=chunks)
        self.assertEqual(response.status_code, 413)

    def test_skill_generation_uses_real_job_validation(self):
        # Calling a FastAPI handler directly must not pass Form objects as values.
        with tempfile.TemporaryDirectory() as directory:
            async def completed(job_id):
                Image.new("RGB", (64, 64), "red").save(Path(directory) / job_id / "design.png")
                return {"id": job_id, "status": "done"}
            with patch.object(server, "JOBS_DIR", Path(directory)), patch.object(server.runtime, "add_job") as queue, patch.object(server, "wait_for_skill_job", completed):
                response = self.client.post("/v1/images/generations", json={"prompt": "A red editorial poster"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(queue.call_args.args[0]["enhancement"], "none")

    def test_expansion_is_serialized(self):
        with server.PROMPT_EXPANSION_LOCK:
            response = self.client.post("/api/prompts/expand", json={"prompt": "A red poster", "provider": "compatible"})
        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
