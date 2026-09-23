const byId = (id) => document.getElementById(id);

const DEFAULT_LAYERS = [
  "Visible headline and all lettering, preserving the exact words.",
  "Main subject or product, including its visible outline.",
  "Card, panel, or badge directly behind the text.",
  "Background and supporting environment, including remaining shadows.",
];

const state = {
  file: null,
  localUrl: null,
  inputSize: null,
  layers: [...DEFAULT_LAYERS],
  resolution: 1024,
  view: "input",
  zoom: "fit",
  job: null,
  layerImages: [],
  visible: [],
  pollHandle: null,
};

function makeElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderPlan() {
  const editor = byId("layer-editor");
  editor.replaceChildren();
  byId("layer-count").textContent = `${state.layers.length} layers`;
  state.layers.forEach((description, index) => {
    const row = makeElement("div", "plan-row");
    const number = makeElement("span", "plan-index", String(index + 1).padStart(2, "0"));
    const text = makeElement("textarea");
    text.value = description;
    text.setAttribute("aria-label", `Layer ${index + 1} description`);
    text.addEventListener("input", () => { state.layers[index] = text.value; });
    const actions = makeElement("div", "row-actions");
    const up = makeElement("button", "", "↑");
    up.type = "button";
    up.title = "Move up";
    up.disabled = index === 0;
    up.addEventListener("click", () => moveLayer(index, -1));
    const down = makeElement("button", "", "↓");
    down.type = "button";
    down.title = "Move down";
    down.disabled = index === state.layers.length - 1;
    down.addEventListener("click", () => moveLayer(index, 1));
    const remove = makeElement("button", "", "×");
    remove.type = "button";
    remove.title = "Remove layer";
    remove.disabled = state.layers.length <= 2;
    remove.addEventListener("click", () => {
      state.layers.splice(index, 1);
      renderPlan();
    });
    actions.append(up, down, remove);
    row.append(number, text, actions);
    editor.append(row);
  });
  byId("add-layer").disabled = state.layers.length >= 8;
}

function moveLayer(index, delta) {
  const next = index + delta;
  [state.layers[index], state.layers[next]] = [state.layers[next], state.layers[index]];
  renderPlan();
  byId("layer-editor").querySelectorAll("textarea")[next]?.focus();
}

function setInputFile(file) {
  if (!file) return;
  if (["queued", "loading", "running", "saving"].includes(state.job?.status)) {
    showError("Wait for the current run to finish before changing the input.");
    return;
  }
  if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
    showError("Choose a PNG, JPEG, or WebP image.");
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    showError("The image is larger than 20 MB.");
    return;
  }
  if (state.localUrl) URL.revokeObjectURL(state.localUrl);
  state.job = null;
  state.layerImages = [];
  state.visible = [];
  state.file = file;
  state.localUrl = URL.createObjectURL(file);
  const probe = new Image();
  probe.onload = () => {
    state.inputSize = [probe.naturalWidth, probe.naturalHeight];
    byId("input-thumb").src = state.localUrl;
    byId("input-name").textContent = file.name;
    byId("input-dimensions").textContent = `${probe.naturalWidth} × ${probe.naturalHeight} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
    byId("input-summary").hidden = false;
    byId("upload-zone").hidden = true;
    state.view = "input";
    byId("metric-status").textContent = "Ready for input";
    byId("metric-time").textContent = "—";
    byId("metric-error").textContent = "—";
    renderResults();
    renderPreview();
  };
  probe.onerror = () => showError("This image could not be previewed.");
  probe.src = state.localUrl;
}

function displaySize(size) {
  return size ? `${size[0]} × ${size[1]}` : "—";
}

function secondsLabel(value) {
  if (value === null || value === undefined) return "—";
  const seconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}

function setView(view) {
  if (view !== "input" && state.job?.status !== "done") return;
  state.view = view;
  renderPreview();
}

function renderPreview() {
  const job = state.job;
  const finished = job?.status === "done";
  document.querySelectorAll(".view-tabs button").forEach((tab) => {
    tab.disabled = tab.dataset.view !== "input" && !finished;
    tab.classList.toggle("active", tab.dataset.view === state.view);
  });
  const source = state.localUrl || job?.input_url;
  const empty = !source;
  byId("canvas-empty").hidden = !empty;
  byId("artwork-frame").hidden = empty;
  if (empty) return;

  const frame = byId("artwork-frame");
  const image = byId("artwork-image");
  const canvas = byId("layer-canvas");
  const split = byId("split-stack");
  const outputSize = finished ? job.metrics.output_size : state.inputSize || job.input_size;
  const width = outputSize?.[0] || 1024;
  const height = outputSize?.[1] || 1024;
  frame.style.aspectRatio = `${width} / ${height}`;
  frame.style.width = state.zoom === "fit" ? `min(100%, ${width}px)` : `${width * Number(state.zoom)}px`;
  image.hidden = state.view === "layers" || state.view === "split";
  canvas.hidden = state.view !== "layers";
  split.hidden = state.view !== "split";
  byId("split-control").hidden = state.view !== "split";

  if (state.view === "input") {
    image.src = source;
    image.alt = "Flattened input design";
    byId("canvas-caption").textContent = "Original flattened design";
  } else if (state.view === "recomposed") {
    image.src = job.recomposed_url;
    image.alt = "Recomposed design from generated layers";
    byId("canvas-caption").textContent = "Generated layers recomposed back to front";
  } else if (state.view === "difference") {
    image.src = job.difference_url;
    image.alt = "Amplified pixel difference between input and recomposition";
    byId("canvas-caption").textContent = "Pixel difference amplified 8× for visibility";
  } else if (state.view === "split") {
    byId("split-before").src = job.input_url;
    byId("split-after").src = job.recomposed_url;
    updateSplit();
    byId("canvas-caption").textContent = "Drag the slider to compare input and recomposition";
  } else {
    drawLayers();
    byId("canvas-caption").textContent = "Visible transparent layers · front to back order";
  }
  byId("metric-size").textContent = displaySize(outputSize);
}

function updateSplit() {
  const position = Number(byId("split-range").value);
  byId("split-after").style.clipPath = `inset(0 0 0 ${position}%)`;
  byId("split-line").style.left = `${position}%`;
}

function drawLayers() {
  const size = state.job?.metrics?.output_size;
  if (!size) return;
  const canvas = byId("layer-canvas");
  canvas.width = size[0];
  canvas.height = size[1];
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  for (let index = state.layerImages.length - 1; index >= 0; index--) {
    if (state.visible[index]) context.drawImage(state.layerImages[index], 0, 0);
  }
}

async function loadLayerImages(urls) {
  state.layerImages = await Promise.all(urls.map((src) => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = src;
  })));
  state.visible = urls.map(() => true);
}

function renderResults() {
  const list = byId("result-list");
  list.replaceChildren();
  const job = state.job;
  byId("result-actions").hidden = job?.status !== "done";
  if (job?.status !== "done") {
    const placeholder = makeElement("div", "result-placeholder");
    placeholder.append(makeElement("span", "", "▧"), makeElement("p", "", "Nothing separated yet"));
    list.append(placeholder);
    return;
  }
  byId("download-zip").href = job.zip_url;
  job.layers.forEach((description, index) => {
    const card = makeElement("div", "result-card");
    card.classList.toggle("hidden-layer", !state.visible[index]);
    const thumbnail = makeElement("img");
    thumbnail.src = job.layer_urls[index];
    thumbnail.alt = `Layer ${index + 1}`;
    const copy = makeElement("div", "result-card-copy");
    copy.append(makeElement("strong", "", `Layer ${String(index + 1).padStart(2, "0")}`), makeElement("span", "", description));
    const actions = makeElement("div", "result-card-actions");
    const toggle = makeElement("button", "", state.visible[index] ? "◉" : "○");
    toggle.type = "button";
    toggle.title = state.visible[index] ? "Hide layer" : "Show layer";
    toggle.setAttribute("aria-label", toggle.title);
    toggle.addEventListener("click", () => {
      state.visible[index] = !state.visible[index];
      state.view = "layers";
      renderResults();
      renderPreview();
    });
    const solo = makeElement("button", "", "S");
    solo.type = "button";
    solo.title = "Solo layer";
    solo.setAttribute("aria-label", `Solo layer ${index + 1}`);
    solo.addEventListener("click", () => {
      state.visible = state.visible.map((_, item) => item === index);
      state.view = "layers";
      renderResults();
      renderPreview();
    });
    const download = makeElement("a", "", "↓");
    download.href = job.layer_urls[index];
    download.download = `layer_${String(index + 1).padStart(2, "0")}.png`;
    download.title = "Download PNG";
    download.setAttribute("aria-label", `Download layer ${index + 1}`);
    actions.append(toggle, solo, download);
    card.append(thumbnail, copy, actions);
    list.append(card);
  });
}

function renderJob() {
  const job = state.job;
  const card = byId("job-card");
  card.className = "job-card";
  if (!job) return;
  card.classList.add(job.status);
  const names = {
    queued: "Queued for Spark 2",
    loading: "Loading model",
    running: "Generating layers",
    saving: "Saving PNGs",
    done: "Layers ready",
    error: "Run failed",
  };
  const messages = {
    queued: "Your design is waiting for the single GPU worker.",
    loading: "The checkpoint is loading into GPU memory. This can take several minutes.",
    running: "The model is working. The timer shows elapsed time; step progress is not available here.",
    saving: "Generation finished. Writing layers, comparison, and ZIP.",
    done: "Inspect individual layers and compare the recomposition with your input.",
    error: job.error || "Something went wrong. Your input and layer plan are still here.",
  };
  byId("job-stage").textContent = names[job.status] || job.status;
  byId("job-message").textContent = messages[job.status] || "";
  byId("metric-status").textContent = names[job.status] || job.status;
  byId("metric-time").textContent = secondsLabel(job.generation_seconds);
  byId("metric-error").textContent = job.metrics ? `${job.metrics.rgb_mae_0_to_255} / 255` : "—";
  byId("generate-button").disabled = ["queued", "loading", "running", "saving"].includes(job.status);
  updateClock();
}

function updateClock() {
  const job = state.job;
  if (!job) return;
  let seconds = job.total_seconds;
  if (seconds === undefined && job.created_at) seconds = (Date.now() - Date.parse(job.created_at)) / 1000;
  byId("job-clock").textContent = secondsLabel(seconds) + (job.status === "done" ? " total" : " elapsed");
}

function showError(message) {
  const card = byId("job-card");
  card.className = "job-card error";
  byId("job-stage").textContent = "Check your input";
  byId("job-message").textContent = message;
  byId("job-clock").textContent = "";
  byId("metric-status").textContent = "Needs attention";
}

async function pollJob() {
  if (!state.job) return;
  try {
    const response = await fetch(`/api/jobs/${state.job.id}`);
    if (!response.ok) throw new Error("Could not check the job status.");
    state.job = await response.json();
    renderJob();
    if (state.job.status === "done") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      await loadLayerImages(state.job.layer_urls);
      state.view = "recomposed";
      renderResults();
      renderPreview();
    } else if (state.job.status === "error") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      renderResults();
    }
  } catch (error) {
    showError(`${error.message} The server may be restarting; this job is still saved.`);
  }
}

function startPolling() {
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = setInterval(pollJob, 2000);
  pollJob();
}

async function submitJob(event) {
  event.preventDefault();
  if (!state.file) { showError("Choose a design image first."); return; }
  const descriptions = state.layers.map((item) => item.trim());
  if (descriptions.some((item) => item.length < 3 || item.length > 300)) {
    showError("Each layer needs a description between 3 and 300 characters.");
    return;
  }
  const seed = Number(byId("seed-input").value);
  if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295) {
    showError("Choose a whole-number seed from 0 to 4294967295.");
    return;
  }
  const data = new FormData();
  data.append("image", state.file);
  data.append("layers", JSON.stringify(descriptions));
  data.append("resolution", String(state.resolution));
  data.append("seed", String(seed));
  byId("generate-button").disabled = true;
  try {
    const response = await fetch("/api/jobs", { method: "POST", body: data });
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The job could not start.");
    state.job = body;
    state.visible = [];
    state.layerImages = [];
    state.view = "input";
    renderJob();
    renderResults();
    renderPreview();
    startPolling();
  } catch (error) {
    byId("generate-button").disabled = false;
    showError(error.message);
  }
}

async function updateHealth() {
  const status = byId("server-status");
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("offline");
    const body = await response.json();
    status.className = `server-status ${body.active_job ? "busy" : "online"}`;
    status.lastChild.textContent = body.active_job ? "GPU working" : body.model_loaded ? "Model ready" : "GPU available";
    byId("release-gpu").disabled = !body.model_loaded || Boolean(body.active_job) || body.queued_jobs > 0;
  } catch {
    status.className = "server-status offline";
    status.lastChild.textContent = "Server offline";
    byId("release-gpu").disabled = true;
  }
}

async function restoreRecentJob() {
  try {
    const response = await fetch("/api/jobs");
    if (!response.ok) return;
    const jobs = await response.json();
    if (!jobs.length) return;
    state.job = jobs[0];
    state.inputSize = state.job.input_size;
    state.layers = [...state.job.layers];
    state.resolution = state.job.resolution;
    byId("seed-input").value = String(state.job.seed);
    document.querySelectorAll("[data-resolution]").forEach((button) => {
      button.classList.toggle("selected", Number(button.dataset.resolution) === state.resolution);
    });
    renderPlan();
    byId("input-thumb").src = state.job.input_url;
    byId("input-name").textContent = "Previous input";
    byId("input-dimensions").textContent = displaySize(state.job.input_size);
    byId("input-summary").hidden = false;
    byId("upload-zone").hidden = true;
    renderJob();
    if (state.job.status === "done") {
      await loadLayerImages(state.job.layer_urls);
      state.view = "recomposed";
      renderResults();
      renderPreview();
    } else if (["queued", "loading", "running", "saving"].includes(state.job.status)) {
      startPolling();
      renderPreview();
    }
    const inputResponse = await fetch(state.job.input_url);
    if (inputResponse.ok) {
      state.file = new File([await inputResponse.blob()], "previous-input.png", {type: "image/png"});
    }
  } catch {
    // The uploader remains usable if history is unavailable.
  }
}

function attachEvents() {
  byId("image-input").addEventListener("change", (event) => setInputFile(event.target.files[0]));
  byId("change-image").addEventListener("click", () => byId("image-input").click());
  const dropZone = byId("upload-zone");
  dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("dragover"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragover");
    setInputFile(event.dataTransfer.files[0]);
  });
  byId("add-layer").addEventListener("click", () => {
    if (state.layers.length >= 8) return;
    state.layers.splice(state.layers.length - 1, 0, "Describe one visible layer.");
    renderPlan();
  });
  byId("reset-plan").addEventListener("click", () => { state.layers = [...DEFAULT_LAYERS]; renderPlan(); });
  document.querySelectorAll("[data-resolution]").forEach((button) => button.addEventListener("click", () => {
    state.resolution = Number(button.dataset.resolution);
    document.querySelectorAll("[data-resolution]").forEach((item) => item.classList.toggle("selected", item === button));
  }));
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  byId("zoom-select").addEventListener("change", (event) => { state.zoom = event.target.value; renderPreview(); });
  byId("split-range").addEventListener("input", updateSplit);
  byId("show-all").addEventListener("click", () => { state.visible = state.visible.map(() => true); state.view = "layers"; renderResults(); renderPreview(); });
  byId("job-form").addEventListener("submit", submitJob);
  byId("release-gpu").addEventListener("click", async () => {
    try {
      const response = await fetch("/api/model/unload", { method: "POST" });
      if (!response.ok) throw new Error("The GPU is currently in use.");
      byId("release-gpu").disabled = true;
      setTimeout(updateHealth, 6000);
    } catch (error) { showError(error.message); }
  });
}

renderPlan();
attachEvents();
updateHealth();
restoreRecentJob();
setInterval(updateHealth, 10000);
setInterval(updateClock, 1000);
