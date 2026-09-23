"""Local, single-GPU web interface for Ming Design and Design-Layer."""

from __future__ import annotations

import asyncio
import base64
import gc
import io
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError

WEB_DIR = Path(__file__).resolve().parent
UPSTREAM_DIR = Path(os.environ.get("MING_UPSTREAM_DIR", "/upstream"))
LAYER_MODEL_DIR = Path(os.environ.get("MING_MODEL_DIR", "/model"))
DESIGN_MODEL_DIR = Path(os.environ.get("MING_DESIGN_MODEL_DIR", "/design-model"))
JOBS_DIR = Path(os.environ.get("MING_JOBS_DIR", "/jobs"))
LAYER_MODEL_REVISION = os.environ.get(
    "MING_MODEL_REVISION", "650448783505b103af305ce347bf60d8889e655a"
)
DESIGN_MODEL_REVISION = os.environ.get(
    "MING_DESIGN_MODEL_REVISION", "16ed0bafe7491ee93c90da5825f54b52bbbc5617"
)
UPSTREAM_REVISION = os.environ.get(
    "MING_UPSTREAM_REVISION", "62c6072e1ff15af83f7c4963a0a1954c1424e80e"
)
IDLE_UNLOAD_SECONDS = int(os.environ.get("MING_IDLE_UNLOAD_SECONDS", "900"))
ATTENTION_IMPLEMENTATION = os.environ.get("MING_ATTENTION_IMPLEMENTATION", "eager")
DUAL_MODEL_CACHE = os.environ.get("MING_DUAL_MODEL_CACHE", "true").lower() == "true"
MIN_MEMORY_TO_ADD_SECOND_GIB = 55
MIN_MEMORY_TO_RUN_DUAL_GIB = 14
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_PENDING_JOBS = 3
JOB_ID_PATTERN = re.compile(r"[a-f0-9]{32}\Z")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def available_memory_gib() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / (1024 * 1024)
    raise RuntimeError("Could not read available system memory")


def make_prompt(layers: list[str]) -> str:
    count = len(layers)
    header = (
        f"Decompose this image into {count} layers with the following specifications:\n\n"
        f"Number of layers: {count}\n"
    )
    return header + "\n" + "\n".join(
        f"Layer {index}: {description}"
        for index, description in enumerate(layers, start=1)
    )


def parse_skill_layers(prompt: str) -> list[str]:
    """Read the two layer-plan formats used by inclusionAI's agent skills."""
    numbered_lines = re.findall(
        r"^\s*Layer\s+(\d+)(?:\s*\(([^)]*)\))?\s*:\s*(.+?)\s*$",
        prompt,
        re.IGNORECASE | re.MULTILINE,
    )
    if numbered_lines:
        numbers = [int(number) for number, _, _ in numbered_lines]
        if numbers != list(range(1, len(numbers) + 1)):
            raise HTTPException(422, "Layer numbers must start at 1 and be consecutive")
        declared = re.search(r"Number of layers:\s*(\d+)", prompt, re.IGNORECASE)
        if declared and int(declared.group(1)) != len(numbered_lines):
            raise HTTPException(422, "Declared layer count differs from the layer plan")
        return [
            f"{role.strip()}: {description.strip()}" if role else description.strip()
            for _, role, description in numbered_lines
        ]

    match = re.match(
        r"^\s*(\d+)\s+layers?\s*:\s*(.+)$", prompt, re.IGNORECASE | re.DOTALL
    )
    if not match:
        raise HTTPException(
            422, "Use numbered Layer lines or a compact '4 layers: 1 ..., 2 ...' plan"
        )
    expected = int(match.group(1))
    chunks = re.split(r"[,;]\s*(?=\d+\s)", match.group(2).strip())
    parsed = [
        re.match(r"^\s*(\d+)\s*(?:[.):\-]\s*)?(.+?)\s*$", chunk, re.DOTALL)
        for chunk in chunks
    ]
    if any(item is None for item in parsed) or [
        int(item.group(1)) for item in parsed
    ] != list(range(1, expected + 1)):
        raise HTTPException(422, "Compact layer plan must number every layer in order")
    return [item.group(2).strip() for item in parsed]


def compare_layers(input_path: Path, layer_paths: list[Path], output_dir: Path) -> dict:
    layers = [Image.open(path).convert("RGBA") for path in layer_paths]
    size = layers[0].size
    if any(layer.size != size for layer in layers):
        raise ValueError("The model returned layers with different dimensions")

    composite = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in reversed(layers):
        composite = Image.alpha_composite(composite, layer)
    composite.convert("RGB").save(output_dir / "recomposed.png")

    with Image.open(input_path) as source:
        input_size = source.size
        reference = source.convert("RGB")
    if reference.size != size:
        reference = reference.resize(size, Image.Resampling.LANCZOS)
    difference = ImageChops.difference(reference, composite.convert("RGB"))
    difference.save(output_dir / "difference.png")
    difference.point(lambda value: min(255, value * 8)).save(
        output_dir / "difference-visible.png"
    )
    channel_means = ImageStat.Stat(difference).mean
    return {
        "input_size": list(input_size),
        "output_size": list(size),
        "rgb_mae_0_to_255": round(sum(channel_means) / 3, 4),
        "difference_display_scale": 8,
    }


def public_job(job: dict) -> dict:
    job_id = job["id"]
    base = f"/api/jobs/{job_id}/assets"
    result = {key: value for key, value in job.items() if key != "prompt"}
    if job.get("kind", "layers") == "design":
        if job["status"] == "done":
            result["design_url"] = f"{base}/design.png"
        return result
    result["input_url"] = f"{base}/input.png"
    if job["status"] == "done":
        result["layer_urls"] = [
            f"{base}/layer_{index:02d}.png"
            for index in range(1, len(job["layers"]) + 1)
        ]
        result["recomposed_url"] = f"{base}/recomposed.png"
        result["difference_url"] = f"{base}/difference-visible.png"
        result["zip_url"] = f"{base}/bundle.zip"
    return result


class JobRuntime:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.pending: queue.Queue[str | None] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stopping = threading.Event()
        self.unload_requested = threading.Event()
        self.model = None
        self.processor = None
        self.profile = None
        self.model_kind: str | None = None
        self.model_cache: dict[str, tuple] = {}
        self.active_id: str | None = None
        self.last_used = 0.0

    def start(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        for manifest_path in JOBS_DIR.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text())
                if JOB_ID_PATTERN.fullmatch(manifest["id"]):
                    self.jobs[manifest["id"]] = manifest
            except (KeyError, ValueError, OSError):
                continue
        self.worker = threading.Thread(target=self._work_loop, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stopping.set()
        self.pending.put(None)
        if self.worker:
            self.worker.join(timeout=2)

    def add_job(self, job: dict) -> None:
        with self.lock:
            if self.pending.qsize() >= MAX_PENDING_JOBS:
                raise HTTPException(429, "The GPU queue is full. Try again later.")
            self.jobs[job["id"]] = job
            self.pending.put(job["id"])

    def get_job(self, job_id: str) -> dict:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise HTTPException(404, "Job not found")
        with self.lock:
            if job_id not in self.jobs:
                raise HTTPException(404, "Job not found")
            return dict(self.jobs[job_id])

    def update(self, job_id: str, **values) -> None:
        with self.lock:
            self.jobs[job_id].update(values)

    def _release_model(self) -> None:
        self.model_cache.clear()
        self.model = None
        self.processor = None
        self.profile = None
        self.model_kind = None
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass
        self.unload_requested.clear()

    def _drop_other_model(self, keep_kind: str) -> None:
        for kind in list(self.model_cache):
            if kind != keep_kind:
                del self.model_cache[kind]
        if self.model_kind != keep_kind:
            self.model = None
            self.processor = None
            self.profile = None
            self.model_kind = None
        gc.collect()
        import torch

        torch.cuda.empty_cache()

    def _work_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                job_id = self.pending.get(timeout=5)
            except queue.Empty:
                if self.model is not None and (
                    self.unload_requested.is_set()
                    or time.monotonic() - self.last_used > IDLE_UNLOAD_SECONDS
                ):
                    self._release_model()
                continue
            if job_id is None:
                break
            with self.lock:
                self.active_id = job_id
            try:
                if self.get_job(job_id).get("kind", "layers") == "design":
                    self._run_design_job(job_id)
                else:
                    self._run_layer_job(job_id)
            except Exception as exc:
                traceback.print_exc()
                self.update(
                    job_id,
                    status="error",
                    error=f"{type(exc).__name__}: {str(exc)[:500]}",
                    finished_at=now_iso(),
                )
                self._release_model()
            finally:
                with self.lock:
                    self.active_id = None
                self.last_used = time.monotonic()
                self.pending.task_done()

    def _load_model(self, kind: str, resolution: int) -> float:
        use_dual_cache = DUAL_MODEL_CACHE and (
            (kind == "design" and resolution == 1024)
            or (kind == "layers" and resolution == 512)
        )
        if use_dual_cache and len(self.model_cache) > 1 and (
            available_memory_gib() < MIN_MEMORY_TO_RUN_DUAL_GIB
        ):
            self._drop_other_model(kind)
        if not use_dual_cache and any(
            cached_kind != kind for cached_kind in self.model_cache
        ):
            self._drop_other_model(kind)
        if self.model is not None and self.model_kind == kind:
            return 0.0
        if kind in self.model_cache:
            self.model, self.processor, self.profile = self.model_cache[kind]
            self.model_kind = kind
            return 0.0
        if self.model is not None and (
            not use_dual_cache or available_memory_gib() < MIN_MEMORY_TO_ADD_SECOND_GIB
        ):
            self._release_model()
        elif self.model is not None:
            self.model_cache[self.model_kind] = (
                self.model, self.processor, self.profile
            )
        started = time.monotonic()
        if str(UPSTREAM_DIR) not in sys.path:
            sys.path.insert(0, str(UPSTREAM_DIR))
        from infer import load_model_and_processor
        from inference_profile import load_checkpoint_capabilities

        model_dir = DESIGN_MODEL_DIR if kind == "design" else LAYER_MODEL_DIR
        self.profile = load_checkpoint_capabilities(model_dir)
        args = SimpleNamespace(
            processor=None,
            dtype="bfloat16",
            attn_implementation=ATTENTION_IMPLEMENTATION,
            device="cuda:0",
            device_map="balanced",
            num_gpus=1,
        )
        self.model, self.processor = load_model_and_processor(model_dir, args)
        self.model_kind = kind
        self.model_cache[kind] = (self.model, self.processor, self.profile)
        if use_dual_cache and len(self.model_cache) > 1 and (
            available_memory_gib() < MIN_MEMORY_TO_RUN_DUAL_GIB
        ):
            self._drop_other_model(kind)
        return round(time.monotonic() - started, 2)

    def _run_layer_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job_dir = JOBS_DIR / job_id
        started = time.monotonic()
        self.update(job_id, status="loading", started_at=now_iso())
        load_seconds = self._load_model("layers", job["resolution"])
        self.profile.validate_task(
            "layer-decompose", has_reference_image=True, num_layers=len(job["layers"])
        )
        from infer import run_generation
        import torch

        sampling = self.profile.resolve_sampling_parameters(steps=job["steps"], cfg=2.0)
        self.update(job_id, status="running", load_seconds=load_seconds)
        generation_started = time.monotonic()
        with torch.inference_mode():
            images = run_generation(
                self.model,
                self.processor,
                self.profile,
                task="layer-decompose",
                prompt=job["prompt"],
                input_image=job_dir / "input.png",
                resolution=job["resolution"],
                sampling=sampling,
                seed=job["seed"],
                num_layers=len(job["layers"]),
                dtype=torch.bfloat16,
            )
        generation_seconds = round(time.monotonic() - generation_started, 2)
        self.update(job_id, status="saving", generation_seconds=generation_seconds)
        images[0].save(job_dir / "model-composite.png")
        layer_paths = []
        for index, image in enumerate(images[1:], start=1):
            path = job_dir / f"layer_{index:02d}.png"
            image.save(path)
            layer_paths.append(path)
        del images
        metrics = compare_layers(job_dir / "input.png", layer_paths, job_dir)
        manifest = self.get_job(job_id)
        manifest.update(
            status="done",
            metrics=metrics,
            total_seconds=round(time.monotonic() - started, 2),
            finished_at=now_iso(),
        )
        (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        archive_names = [
            "input.png",
            "model-composite.png",
            "recomposed.png",
            "difference.png",
            "difference-visible.png",
            "manifest.json",
        ] + [path.name for path in layer_paths]
        with zipfile.ZipFile(job_dir / "bundle.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in archive_names:
                bundle.write(job_dir / name, name)
        self.update(
            job_id,
            status="done",
            metrics=metrics,
            total_seconds=round(time.monotonic() - started, 2),
            finished_at=manifest["finished_at"],
        )
        torch.cuda.empty_cache()

    def _run_design_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job_dir = JOBS_DIR / job_id
        started = time.monotonic()
        self.update(job_id, status="loading", started_at=now_iso())
        load_seconds = self._load_model("design", job["resolution"])
        self.profile.validate_task(
            "text-to-image", has_reference_image=False, num_layers=1
        )
        from infer import run_generation
        import torch

        sampling = self.profile.resolve_sampling_parameters(steps=job["steps"], cfg=1.0)
        self.update(job_id, status="running", load_seconds=load_seconds)
        generation_started = time.monotonic()
        with torch.inference_mode():
            images = run_generation(
                self.model,
                self.processor,
                self.profile,
                task="text-to-image",
                prompt=job["design_prompt"],
                input_image=None,
                resolution=job["resolution"],
                sampling=sampling,
                seed=job["seed"],
                num_layers=1,
                dtype=torch.bfloat16,
            )
        generation_seconds = round(time.monotonic() - generation_started, 2)
        self.update(job_id, status="saving", generation_seconds=generation_seconds)
        output = images[0]
        output.save(job_dir / "design.png")
        output_size = list(output.size)
        del images, output
        manifest = self.get_job(job_id)
        manifest.update(
            status="done",
            output_size=output_size,
            total_seconds=round(time.monotonic() - started, 2),
            finished_at=now_iso(),
        )
        (job_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        self.update(
            job_id,
            status="done",
            output_size=output_size,
            total_seconds=manifest["total_seconds"],
            finished_at=manifest["finished_at"],
        )
        torch.cuda.empty_cache()


runtime = JobRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime.start()
    try:
        yield
    finally:
        runtime.stop()


app = FastAPI(title="Ming Layer Lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    with runtime.lock:
        return {
            "model_loaded": runtime.model is not None,
            "loaded_model": runtime.model_kind,
            "loaded_models": sorted(runtime.model_cache),
            "dual_model_cache": DUAL_MODEL_CACHE,
            "available_memory_gib": round(available_memory_gib(), 2),
            "active_job": runtime.active_id,
            "queued_jobs": runtime.pending.qsize(),
            "idle_unload_seconds": IDLE_UNLOAD_SECONDS,
            "model_revision": LAYER_MODEL_REVISION,
            "design_model_revision": DESIGN_MODEL_REVISION,
            "attention_implementation": ATTENTION_IMPLEMENTATION,
            "parallel_loading": os.environ.get("HF_ENABLE_PARALLEL_LOADING", "false"),
        }


@app.get("/api/jobs")
def list_jobs():
    with runtime.lock:
        jobs = sorted(runtime.jobs.values(), key=lambda job: job["created_at"], reverse=True)
        return [public_job(dict(job)) for job in jobs[:20]]


@app.post("/api/jobs", status_code=202)
async def create_job(
    image: UploadFile = File(...),
    layers: str = Form(...),
    resolution: int = Form(1024),
    seed: int = Form(42),
    steps: int = Form(12),
):
    try:
        layer_descriptions = json.loads(layers)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "Layer plan must be a JSON array") from exc
    if not isinstance(layer_descriptions, list) or not 2 <= len(layer_descriptions) <= 8:
        raise HTTPException(422, "Choose between 2 and 8 layers")
    if any(
        not isinstance(item, str) or not 3 <= len(item.strip()) <= 300
        for item in layer_descriptions
    ):
        raise HTTPException(422, "Each layer needs a description of 3–300 characters")
    layer_descriptions = [item.strip() for item in layer_descriptions]
    if resolution not in (512, 1024):
        raise HTTPException(422, "Resolution must be 512 or 1024")
    if not 0 <= seed <= 2**32 - 1:
        raise HTTPException(422, "Seed is out of range")
    if steps not in (8, 12):
        raise HTTPException(422, "Steps must be 8 or 12")

    data = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image exceeds the 20 MB limit")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            if opened.format not in ("PNG", "JPEG", "WEBP"):
                raise HTTPException(415, "Use a PNG, JPEG, or WebP image")
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise HTTPException(413, "Image exceeds the 16 megapixel limit")
            if min(opened.size) < 64:
                raise HTTPException(422, "Image must be at least 64 pixels on each side")
            input_image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HTTPException(415, "Could not read this image") from exc

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    input_image.save(job_dir / "input.png")
    job = {
        "id": job_id,
        "kind": "layers",
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "layers": layer_descriptions,
        "prompt": make_prompt(layer_descriptions),
        "resolution": resolution,
        "seed": seed,
        "steps": steps,
        "cfg": 2.0,
        "model_revision": LAYER_MODEL_REVISION,
        "upstream_revision": UPSTREAM_REVISION,
        "input_size": list(input_image.size),
    }
    try:
        runtime.add_job(job)
    except HTTPException:
        shutil.rmtree(job_dir)
        raise
    return public_job(job)


@app.post("/api/design-jobs", status_code=202)
def create_design_job(
    prompt: str = Form(...),
    resolution: int = Form(1024),
    seed: int = Form(42),
    steps: int = Form(12),
):
    prompt = prompt.strip()
    if not 5 <= len(prompt) <= 5000:
        raise HTTPException(422, "Describe the design in 5–5000 characters")
    if resolution not in (1024, 2048):
        raise HTTPException(422, "Design resolution must be 1024 or 2048")
    if not 0 <= seed <= 2**32 - 1:
        raise HTTPException(422, "Seed is out of range")
    if steps not in (8, 12):
        raise HTTPException(422, "Steps must be 8 or 12")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    job = {
        "id": job_id,
        "kind": "design",
        "status": "queued",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "design_prompt": prompt,
        "resolution": resolution,
        "seed": seed,
        "steps": steps,
        "cfg": 1.0,
        "model_revision": DESIGN_MODEL_REVISION,
        "upstream_revision": UPSTREAM_REVISION,
    }
    try:
        runtime.add_job(job)
    except HTTPException:
        shutil.rmtree(job_dir)
        raise
    return public_job(job)


async def wait_for_skill_job(job_id: str) -> dict:
    """Return a finished queued job while leaving the GPU worker free to run it."""
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        job = runtime.get_job(job_id)
        if job["status"] == "done":
            return job
        if job["status"] == "error":
            raise HTTPException(
                422, f"Ming job failed: {job.get('error', 'unknown error')}"
            )
        await asyncio.sleep(0.5)
    raise HTTPException(504, f"Ming job {job_id} did not finish in 30 minutes")


@app.post("/v1/images/generations")
async def skill_generate_design(payload: dict):
    """OpenAI-shaped local response for inclusionAI's ling-ui-design helper."""
    model = str(payload.get("model", "ming-image-0.1-design")).lower()
    if model not in {"ming-image-0.1-design", "inclusionai/ming-image-0.1-design"}:
        raise HTTPException(422, "This local endpoint serves Ming-Image-0.1-Design only")
    size = str(payload.get("size", "1024")).lower()
    if size not in {"1024", "1k", "2048", "2k", "auto"}:
        raise HTTPException(422, "Design size must be 1024 or 2048")
    resolution = 2048 if size in {"2048", "2k"} else 1024
    output_format = str(payload.get("output_format", "png")).lower()
    if output_format not in {"png", "jpeg", "jpg", "webp"}:
        raise HTTPException(422, "Output format must be png, jpeg, or webp")
    try:
        seed = int(payload.get("seed", 42))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Seed must be an integer") from exc
    created = create_design_job(
        prompt=str(payload.get("prompt", "")), resolution=resolution, seed=seed, steps=12
    )
    job = await wait_for_skill_job(created["id"])
    with Image.open(JOBS_DIR / job["id"] / "design.png") as image:
        buffer = io.BytesIO()
        if output_format in {"jpeg", "jpg"}:
            image.convert("RGB").save(buffer, format="JPEG", quality=95)
        elif output_format == "webp":
            image.save(buffer, format="WEBP", quality=95)
        else:
            image.save(buffer, format="PNG")
    return {
        "data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode("ascii")}],
        "job_id": job["id"],
    }


@app.post("/v1/images/edits")
async def skill_decompose_image(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    model: str = Form("ming-image-0.1-design-layer"),
    size: str = Form("auto"),
    seed: int = Form(42),
    num_inference_steps: int = Form(12),
    num_layers: int | None = Form(None),
):
    """Accept the multipart layer requests sent by both inclusionAI skills."""
    if model.lower() not in {
        "ming-image-0.1-design-layer",
        "inclusionai/ming-image-0.1-design-layer",
    }:
        raise HTTPException(
            422, "This local endpoint serves Ming-Image-0.1-Design-Layer only"
        )
    resolution_map = {
        "auto": 512,
        "512": 512,
        "512x512": 512,
        "1k": 1024,
        "1024": 1024,
        "1024x1024": 1024,
    }
    if size.lower() not in resolution_map:
        raise HTTPException(422, "Layer size must be auto, 512, or 1k")
    if num_inference_steps not in (12, 14):
        raise HTTPException(422, "This local workflow uses 12 inference steps")
    layers = parse_skill_layers(prompt)
    if num_layers is not None and num_layers != len(layers):
        raise HTTPException(422, "num_layers differs from the numbered layer plan")
    created = await create_job(
        image=image,
        layers=json.dumps(layers),
        resolution=resolution_map[size.lower()],
        seed=seed,
        steps=12,
    )
    job = await wait_for_skill_job(created["id"])
    return {
        "data": [
            {
                "b64_json": base64.b64encode(
                    (JOBS_DIR / job["id"] / f"layer_{index:02d}.png").read_bytes()
                ).decode("ascii")
            }
            for index in range(1, len(layers) + 1)
        ],
        "job_id": job["id"],
        "actual_resolution": job["resolution"],
        "actual_steps": 12,
        "prompt_enhancement": False,
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return public_job(runtime.get_job(job_id))


@app.get("/api/jobs/{job_id}/assets/{filename}")
def get_asset(job_id: str, filename: str):
    job = runtime.get_job(job_id)
    if job.get("kind", "layers") == "design":
        allowed = {"design.png", "manifest.json"} if job["status"] == "done" else set()
    else:
        allowed = {"input.png"}
    if job.get("kind", "layers") == "layers" and job["status"] == "done":
        allowed.update(
            {
                "recomposed.png",
                "model-composite.png",
                "difference.png",
                "difference-visible.png",
                "manifest.json",
                "bundle.zip",
            }
        )
        allowed.update(f"layer_{index:02d}.png" for index in range(1, len(job["layers"]) + 1))
    if filename not in allowed:
        raise HTTPException(404, "File not found")
    path = JOBS_DIR / job_id / filename
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename if filename == "bundle.zip" else None)


@app.post("/api/model/unload", status_code=202)
def unload_model():
    with runtime.lock:
        if runtime.active_id is not None or runtime.pending.qsize():
            raise HTTPException(409, "The model is in use")
        runtime.unload_requested.set()
    return {"status": "releasing"}
