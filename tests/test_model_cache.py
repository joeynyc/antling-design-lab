"""Check checkpoint reuse and the memory guard without loading model weights."""

import sys
import types
import unittest
from unittest.mock import patch

from web import server


class ModelCacheTests(unittest.TestCase):
    def setUp(self):
        self.runtime = server.JobRuntime()
        self.loads = []

        def load_model(model_dir, _args):
            self.loads.append(model_dir)
            return object(), object()

        self.modules = patch.dict(
            sys.modules,
            {
                "infer": types.SimpleNamespace(load_model_and_processor=load_model),
                "inference_profile": types.SimpleNamespace(
                    load_checkpoint_capabilities=lambda _model_dir: object()
                ),
                "torch": types.SimpleNamespace(
                    cuda=types.SimpleNamespace(empty_cache=lambda: None)
                ),
            },
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)
        dual = patch.object(server, "DUAL_MODEL_CACHE", True)
        dual.start()
        self.addCleanup(dual.stop)

    def test_small_jobs_reuse_both_checkpoints(self):
        with patch.object(server, "available_memory_gib", return_value=18):
            self.runtime._load_model("design", 1024)
            # Loading a second checkpoint requires more initial headroom.
            with patch.object(server, "available_memory_gib", return_value=60):
                self.runtime._load_model("layers", 512)
            self.assertEqual(self.runtime._load_model("design", 1024), 0.0)
            self.assertEqual(self.runtime._load_model("layers", 512), 0.0)
        self.assertEqual(len(self.loads), 2)
        self.assertEqual(set(self.runtime.model_cache), {"design", "layers"})

    def test_high_resolution_evicts_inactive_checkpoint(self):
        with patch.object(server, "available_memory_gib", return_value=60):
            self.runtime._load_model("design", 1024)
            self.runtime._load_model("layers", 512)
        self.assertEqual(self.runtime._load_model("design", 2048), 0.0)
        self.assertEqual(set(self.runtime.model_cache), {"design"})
        self.assertEqual(self.runtime.model_kind, "design")

    def test_low_memory_discards_inactive_checkpoint(self):
        with patch.object(server, "available_memory_gib", return_value=60):
            self.runtime._load_model("design", 1024)
            self.runtime._load_model("layers", 512)
        with patch.object(server, "available_memory_gib", return_value=13):
            self.assertEqual(self.runtime._load_model("layers", 512), 0.0)
        self.assertEqual(set(self.runtime.model_cache), {"layers"})

    def test_insufficient_headroom_prevents_second_checkpoint(self):
        self.runtime._load_model("design", 1024)
        with patch.object(server, "available_memory_gib", return_value=54):
            self.runtime._load_model("layers", 512)
        self.assertEqual(set(self.runtime.model_cache), {"layers"})
        self.assertEqual(len(self.loads), 2)

    def test_release_gpu_clears_both_checkpoints(self):
        with patch.object(server, "available_memory_gib", return_value=60):
            self.runtime._load_model("design", 1024)
            self.runtime._load_model("layers", 512)
        self.runtime._release_model()
        self.assertEqual(self.runtime.model_cache, {})
        self.assertIsNone(self.runtime.model)
        self.assertIsNone(self.runtime.model_kind)


if __name__ == "__main__":
    unittest.main()
