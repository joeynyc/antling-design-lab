#!/usr/bin/env python3
"""Local Mac bridge from AntLing Design Lab to the signed-in Codex CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web.prompting import expansion_request, validate_prompt
HOST = "127.0.0.1"
PORT = int(os.environ.get("MING_REWRITER_PORT", "8766"))
ALLOWED_ORIGIN = "http://127.0.0.1:8765"
CODEX = os.environ.get("MING_CODEX_BIN") or shutil.which("codex") or str(Path.home() / ".local/bin/codex")
MODEL = os.environ.get("MING_REWRITER_MODEL", "gpt-6-luna")
BUSY = threading.Lock()


def rewrite(user_prompt: str) -> dict:
    request = expansion_request(user_prompt)
    with tempfile.TemporaryDirectory(prefix="ming-codex-") as work:
        output = Path(work) / "response.json"
        command = [
            CODEX, "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
            "--sandbox", "read-only", "-C", work, "-m", MODEL,
            "-c", 'model_reasoning_effort="low"', "-o", str(output), "-",
        ]
        result = subprocess.run(command, input=request, text=True, capture_output=True, timeout=180)
        if result.returncode != 0 or not output.exists():
            raise RuntimeError("Codex could not expand the prompt. Check that the Codex CLI is signed in.")
        try:
            return validate_prompt(json.loads(output.read_text()))
        except json.JSONDecodeError as exc:
            raise ValueError("Codex did not return valid JSON") from exc


class Handler(BaseHTTPRequestHandler):
    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self) -> bool:
        return self.headers.get("Origin") == ALLOWED_ORIGIN

    def do_OPTIONS(self) -> None:
        if self.path != "/rewrite" or not self._allowed():
            self._respond(403, {"error": "Origin not allowed"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health" and self._allowed():
            self._respond(200, {"status": "ready", "model": MODEL})
        else:
            self._respond(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/rewrite" or not self._allowed():
            self._respond(403, {"error": "Origin not allowed"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= 12000:
            self._respond(413, {"error": "Prompt request is too large"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str):
                raise ValueError("A prompt is required")
            if not BUSY.acquire(blocking=False):
                self._respond(429, {"error": "Codex is expanding another prompt"})
                return
            try:
                structured = rewrite(payload["prompt"].strip())
            finally:
                BUSY.release()
            self._respond(200, {"prompt": json.dumps(structured, ensure_ascii=False), "model": MODEL})
        except subprocess.TimeoutExpired:
            self._respond(504, {"error": "Codex prompt expansion timed out"})
        except OSError:
            self._respond(503, {"error": "Codex CLI is unavailable. Check MING_CODEX_BIN and your installation."})
        except (ValueError, RuntimeError) as exc:
            self._respond(422, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
