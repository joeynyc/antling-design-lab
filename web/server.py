"""Local, single-GPU web interface for Ming Design and Design-Layer."""

from __future__ import annotations

import asyncio
import base64
import gc
import io
import json
import math
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
PROJECTS_DIR = JOBS_DIR / "projects"
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
SOURCE_EXPORT_LOCK = threading.Lock()


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


def source_cutouts_available(job: dict) -> bool:
    """A source-size export can reuse model masks when the input is larger."""
    if job.get("kind", "layers") != "layers" or job.get("status") != "done":
        return False
    source_size = job.get("input_size")
    output_size = (job.get("metrics") or {}).get("output_size")
    return bool(
        source_size
        and output_size
        and any(source > output for source, output in zip(source_size, output_size))
    )


def create_source_cutouts(job_id: str, job: dict) -> Path:
    """Apply model alpha masks to the original pixels without claiming 2K inference."""
    job_dir = JOBS_DIR / job_id
    target = job_dir / "source-cutouts.zip"
    with SOURCE_EXPORT_LOCK:
        if target.is_file():
            return target
        temporary = job_dir / f".source-cutouts-{uuid.uuid4().hex}.zip"
        try:
            with Image.open(job_dir / "input.png") as opened:
                source = opened.convert("RGB")
            transparent_rgb = Image.new("RGB", source.size)
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(
                    "README.txt",
                    "Source-size masked cutouts from AntLing Design Lab.\n"
                    "The Layer model ran at its selected working size, not at the source size.\n"
                    "Its alpha masks were resized and applied to the original pixels.\n"
                    "These are raster cutouts, not newly generated high-resolution layers.\n"
                    "Edges and overlapping content may need cleanup before reuse.\n"
                    "Lettering remains pixels, not editable font text.\n",
                )
                bundle.write(job_dir / "input.png", "original.png")
                for index in range(1, len(job["layers"]) + 1):
                    with Image.open(job_dir / f"layer_{index:02d}.png") as layer:
                        alpha = layer.convert("RGBA").getchannel("A")
                    if alpha.size != source.size:
                        alpha = alpha.resize(source.size, Image.Resampling.LANCZOS)
                    visible_pixels = alpha.point(lambda value: 255 if value else 0)
                    cutout = Image.composite(
                        source, transparent_rgb, visible_pixels
                    ).convert("RGBA")
                    cutout.putalpha(alpha)
                    with io.BytesIO() as data:
                        cutout.save(data, format="PNG")
                        bundle.writestr(f"source_layer_{index:02d}.png", data.getvalue())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def public_job(job: dict) -> dict:
    job_id = job["id"]
    base = f"/api/jobs/{job_id}/assets"
    result = {key: value for key, value in job.items() if key not in ("prompt", "generation_prompt")}
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
        if source_cutouts_available(job):
            result["source_zip_url"] = f"{base}/source-cutouts.zip"
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
                prompt=job.get("generation_prompt", job["design_prompt"]),
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


app = FastAPI(title="AntLing Design Lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/finish")
def finish_page():
    return FileResponse(WEB_DIR / "finish.html")


def validate_project(payload: dict, existing: dict | None = None) -> dict:
    """Accept only bounded editor data; saved projects never contain image bytes."""
    if not isinstance(payload, dict):
        raise HTTPException(422, "Expected a project object")
    source_id = payload.get("source_job_id")
    if not isinstance(source_id, str) or not JOB_ID_PATTERN.fullmatch(source_id):
        raise HTTPException(422, "Choose a completed source job")
    if existing and source_id != existing["source_job_id"]:
        raise HTTPException(422, "A project's source cannot be changed")
    job = runtime.get_job(source_id)
    if job.get("status") != "done" or job.get("kind", "layers") not in {"design", "layers"}:
        raise HTTPException(422, "Choose a completed design or layer job")
    title = payload.get("title")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
        raise HTTPException(422, "Project title must be 1–120 characters")
    size = payload.get("size")
    if size not in {"landscape", "square"}:
        raise HTTPException(422, "Choose landscape or square")
    background = payload.get("background", "original")
    background_color = payload.get("background_color", "#16172e")
    if background not in {"original", "solid"} or not isinstance(background_color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", background_color):
        raise HTTPException(422, "Invalid background")
    try:
        focal_x, focal_y = float(payload.get("focal_x")), float(payload.get("focal_y"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Invalid image position") from exc
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (focal_x, focal_y)):
        raise HTTPException(422, "Invalid image position")
    elements = payload.get("elements")
    if not isinstance(elements, list) or len(elements) > 24:
        raise HTTPException(422, "A project supports up to 24 elements")
    clean_elements = []
    seen = set()
    for element in elements:
        if not isinstance(element, dict):
            raise HTTPException(422, "Invalid element")
        element_id = element.get("id")
        if not isinstance(element_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", element_id) or element_id in seen:
            raise HTTPException(422, "Invalid or duplicate element ID")
        seen.add(element_id)
        kind = element.get("type")
        if kind not in {"text", "layer"}:
            raise HTTPException(422, "Unknown element type")
        numeric = {}
        for key, low, high in (("x", -3200, 3200), ("y", -3200, 3200), ("width", 1, 6400), ("height", 1, 6400)):
            if key in element or key in {"x", "y"}:
                try:
                    value = float(element[key])
                except (KeyError, TypeError, ValueError) as exc:
                    raise HTTPException(422, f"Invalid {key}") from exc
                if not math.isfinite(value) or not low <= value <= high:
                    raise HTTPException(422, f"Invalid {key}")
                numeric[key] = value
        clean = {"id": element_id, "type": kind, **numeric}
        if kind == "text":
            copy = element.get("text")
            color = element.get("color")
            if not isinstance(copy, str) or len(copy) > 500 or not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise HTTPException(422, "Invalid text or color")
            try:
                font_size = int(element.get("font_size"))
                weight = int(element.get("weight"))
            except (TypeError, ValueError) as exc:
                raise HTTPException(422, "Invalid font setting") from exc
            if not 12 <= font_size <= 300 or weight not in {400, 500, 600, 700, 800, 900}:
                raise HTTPException(422, "Invalid font setting")
            clean.update(text=copy, color=color, font_size=font_size, weight=weight)
        else:
            if job.get("kind", "layers") != "layers":
                raise HTTPException(422, "This source has no layers")
            index = element.get("layer_index")
            if not isinstance(index, int) or not 0 <= index < len(job["layers"]):
                raise HTTPException(422, "Invalid layer index")
            strokes = element.get("erase", [])
            if not isinstance(strokes, list) or len(strokes) > 100:
                raise HTTPException(422, "Too many cleanup strokes")
            cleaned_strokes = []
            for stroke in strokes:
                if not isinstance(stroke, dict) or not isinstance(stroke.get("points"), list) or not 1 <= len(stroke["points"]) <= 500:
                    raise HTTPException(422, "Invalid cleanup stroke")
                try:
                    radius = float(stroke.get("radius"))
                    points = [[float(x), float(y)] for x, y in stroke["points"]]
                except (TypeError, ValueError) as exc:
                    raise HTTPException(422, "Invalid cleanup stroke") from exc
                if not math.isfinite(radius) or not 1 <= radius <= 200 or any(not math.isfinite(v) or not 0 <= v <= 1 for point in points for v in point):
                    raise HTTPException(422, "Invalid cleanup stroke")
                cleaned_strokes.append({"radius": radius, "points": points})
            clean.update(layer_index=index, erase=cleaned_strokes)
        clean_elements.append(clean)
    return {"title": title.strip(), "source_job_id": source_id, "size": size,
            "background": background, "background_color": background_color,
            "focal_x": focal_x, "focal_y": focal_y, "elements": clean_elements}


def project_path(project_id: str) -> Path:
    if not JOB_ID_PATTERN.fullmatch(project_id):
        raise HTTPException(404, "Project not found")
    return PROJECTS_DIR / f"{project_id}.json"


def read_project(project_id: str) -> dict:
    path = project_path(project_id)
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Project not found") from exc


def write_project(project: dict) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    temporary = PROJECTS_DIR / f".{project['id']}-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(project, ensure_ascii=False, separators=(",", ":")))
        os.replace(temporary, project_path(project["id"]))
    finally:
        temporary.unlink(missing_ok=True)


@app.get("/api/projects")
def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for path in PROJECTS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text())
            projects.append({key: item[key] for key in ("id", "title", "source_job_id", "size", "updated_at")})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(projects, key=lambda item: item["updated_at"], reverse=True)[:100]


@app.post("/api/projects", status_code=201)
def create_project(payload: dict):
    document = validate_project(payload)
    timestamp = now_iso()
    project = {"id": uuid.uuid4().hex, "created_at": timestamp, "updated_at": timestamp, **document}
    write_project(project)
    return project


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    return read_project(project_id)


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, payload: dict):
    previous = read_project(project_id)
    document = validate_project(payload, previous)
    project = {**previous, **document, "updated_at": now_iso()}
    write_project(project)
    return project


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
    source_prompt: str | None = Form(None),
    enhancement: str = Form("none"),
    rewrite_seconds: float | None = Form(None),
):
    prompt = prompt.strip()
    if enhancement not in ("none", "codex"):
        raise HTTPException(422, "Unknown prompt enhancement")
    if enhancement == "codex" and source_prompt is None:
        raise HTTPException(422, "Original prompt is required for Codex enhancement")
    if rewrite_seconds is not None and (
        enhancement != "codex"
        or not math.isfinite(rewrite_seconds)
        or not 0 <= rewrite_seconds <= 190
    ):
        raise HTTPException(422, "Codex timing must be between 0 and 190 seconds")
    if source_prompt is not None:
        source_prompt = source_prompt.strip()
        if not 5 <= len(source_prompt) <= 5000:
            raise HTTPException(422, "Original prompt must be 5–5000 characters")
        if enhancement != "codex":
            raise HTTPException(422, "Enhanced prompt must identify its source")
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
        "design_prompt": source_prompt or prompt,
        "enhancement": enhancement,
        "resolution": resolution,
        "seed": seed,
        "steps": steps,
        "cfg": 1.0,
        "model_revision": DESIGN_MODEL_REVISION,
        "upstream_revision": UPSTREAM_REVISION,
    }
    if source_prompt:
        job["generation_prompt"] = prompt
    if rewrite_seconds is not None:
        job["rewrite_seconds"] = round(rewrite_seconds, 2)
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
        prompt=str(payload.get("prompt", "")), resolution=resolution, seed=seed,
        steps=12, source_prompt=None, enhancement="none"
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
        if source_cutouts_available(job):
            allowed.add("source-cutouts.zip")
    if filename not in allowed:
        raise HTTPException(404, "File not found")
    path = (
        create_source_cutouts(job_id, job)
        if filename == "source-cutouts.zip"
        else JOBS_DIR / job_id / filename
    )
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename if filename.endswith(".zip") else None)


@app.post("/api/model/unload", status_code=202)
def unload_model():
    with runtime.lock:
        if runtime.active_id is not None or runtime.pending.qsize():
            raise HTTPException(409, "The model is in use")
        runtime.unload_requested.set()
    return {"status": "releasing"}
