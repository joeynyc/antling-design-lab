"""Prompt-provider adapters never expose keys and preserve Ming's JSON contract."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from web import prompting, server


SAMPLE = {
    "canvas_settings": {"aspect_ratio": "16:9", "ambient_lighting": "soft", "image_style": "editorial"},
    "layers": [
        {"description": "Navy background", "coordinates": "cx: 0.500, cy: 0.500, w: 1.000, h: 1.000", "hierarchy_and_relation": "Behind", "color_specs": ["#151728"]},
        {"description": "Orange vase", "coordinates": "cx: 0.500, cy: 0.500, w: 0.300, h: 0.500", "hierarchy_and_relation": "In front", "color_specs": ["#FF8500"]},
    ],
}


class PromptProviderTests(unittest.TestCase):
    def test_discovery_only_lists_configured_models_and_never_keys(self):
        with patch.dict(os.environ, {"ANTLING_OPENAI_API_KEY": "private-test-key", "ANTLING_OPENAI_MODEL": "chosen-model", "ANTLING_ANTHROPIC_MODEL": "no-key"}, clear=True):
            body = TestClient(server.app, base_url="http://127.0.0.1").get("/api/prompt-providers").json()
        self.assertEqual([entry["id"] for entry in body["providers"]], ["openai"])
        self.assertNotIn("private-test-key", json.dumps(body))

    def test_provider_shapes_and_ming_validation(self):
        responses = {
            "openai": {"output": [{"content": [{"type": "output_text", "text": json.dumps(SAMPLE)}]}]},
            "anthropic": {"content": [{"type": "text", "text": json.dumps(SAMPLE)}]},
            "zai": {"choices": [{"message": {"content": json.dumps(SAMPLE)}}]},
            "deepseek": {"choices": [{"message": {"content": json.dumps(SAMPLE)}}]},
            "compatible": {"choices": [{"message": {"content": "```json\n" + json.dumps(SAMPLE) + "\n```"}}]},
        }
        for provider, body in responses.items():
            with self.subTest(provider=provider):
                prefix = prompting.PROVIDERS[provider][1]
                env = {f"{prefix}_MODEL": "chosen-model", f"{prefix}_API_KEY": "private-test-key"}
                if provider == "compatible":
                    env["ANTLING_COMPAT_BASE_URL"] = "https://example.com/v1"
                fake_response = Mock()
                fake_response.status_code = 200
                fake_response.iter_content.return_value = [json.dumps(body).encode()]
                fake_requests = SimpleNamespace(post=Mock(return_value=fake_response), RequestException=RuntimeError)
                with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"requests": fake_requests}):
                    result, model = prompting.expand_prompt(provider, "An editorial product scene")
                self.assertEqual(result["canvas_settings"]["aspect_ratio"], "1:1, 2048 x 2048 px")
                self.assertEqual(model, "chosen-model")
                call = fake_requests.post.call_args
                self.assertNotIn("private-test-key", json.dumps(call.kwargs["json"]))
                self.assertEqual(call.kwargs["headers"].get("Authorization", call.kwargs["headers"].get("x-api-key")), "Bearer private-test-key" if provider != "anthropic" else "private-test-key")

    def test_redirects_and_large_responses_are_rejected_and_closed(self):
        for status, chunks, message in [(302, [], "redirects"), (200, [b"x" * (1024 * 1024 + 1)], "size limit")]:
            with self.subTest(status=status):
                response = Mock(status_code=status)
                response.iter_content.return_value = chunks
                request = SimpleNamespace(post=Mock(return_value=response), RequestException=RuntimeError)
                with patch.dict(os.environ, {"ANTLING_ANTHROPIC_MODEL": "test", "ANTLING_ANTHROPIC_API_KEY": "secret"}, clear=True), patch.dict(sys.modules, {"requests": request}):
                    with self.assertRaisesRegex(ValueError, message):
                        prompting.expand_prompt("anthropic", "A product image")
                self.assertFalse(request.post.call_args.kwargs["allow_redirects"])
                response.close.assert_called_once()

    def test_provider_error_never_returns_sensitive_response(self):
        response = Mock(status_code=401)
        response.raise_for_status.side_effect = RuntimeError("private prompt and secret key")
        request = SimpleNamespace(post=Mock(return_value=response), RequestException=RuntimeError)
        with patch.dict(os.environ, {"ANTLING_OPENAI_MODEL": "test", "ANTLING_OPENAI_API_KEY": "secret"}, clear=True), patch.dict(sys.modules, {"requests": request}):
            with self.assertRaises(ValueError) as caught:
                prompting.expand_prompt("openai", "A product image")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("private prompt", str(caught.exception))
        response.close.assert_called_once()

    def test_http_custom_key_is_rejected_before_network_call(self):
        with patch.dict(os.environ, {"ANTLING_COMPAT_MODEL": "local-model", "ANTLING_COMPAT_API_KEY": "secret", "ANTLING_COMPAT_BASE_URL": "http://example.com/v1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                prompting._compatible_url(os.environ["ANTLING_COMPAT_BASE_URL"], "secret")
        self.assertEqual(prompting._compatible_url("http://host.docker.internal:11434/v1", ""), "http://host.docker.internal:11434/v1/chat/completions")

    def test_api_rejects_unconfigured_provider_and_invalid_prompt(self):
        client = TestClient(server.app, base_url="http://127.0.0.1")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client.post("/api/prompts/expand", json={"provider": "openai", "prompt": "Draw a poster"}).status_code, 422)
        with patch.object(server, "expand_prompt", return_value=(SAMPLE, "chosen-model")):
            body = client.post("/api/prompts/expand", json={"provider": "openai", "prompt": "Draw a poster"}).json()
        self.assertEqual(body["provider"], "openai")
        self.assertIn("canvas_settings", body["prompt"])

    def test_non_codex_expansion_preserves_original_job_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, "JOBS_DIR", Path(directory)), patch.object(server.runtime, "add_job") as add_job:
                response = TestClient(server.app, base_url="http://127.0.0.1").post("/api/design-jobs", data={
                    "prompt": json.dumps(SAMPLE), "source_prompt": "A navy poster with a vase",
                    "enhancement": "anthropic", "rewrite_seconds": "3.2",
                })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["design_prompt"], "A navy poster with a vase")
        self.assertNotIn("generation_prompt", response.json())
        self.assertEqual(add_job.call_args.args[0]["enhancement"], "anthropic")


if __name__ == "__main__":
    unittest.main()
