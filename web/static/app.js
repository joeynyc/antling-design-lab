const byId = (id) => document.getElementById(id);

const DEFAULT_LAYERS = [
  "Visible headline and all lettering, preserving the exact words.",
  "Main subject or product, including its visible outline.",
  "Card, panel, or badge directly behind the text.",
  "Background and supporting environment, including remaining shadows.",
];

const state = {
  mode: "design",
  jobs: {design: null, layers: null},
  designResolution: 2048,
  file: null,
  localUrl: null,
  inputSize: null,
  layers: [...DEFAULT_LAYERS],
  resolution: 1024,
  view: "input",
  zoom: "fit",
  previewSize: null,
  job: null,
  layerImages: [],
  visible: [],
  designResult: null,
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
  if (state.mode !== "layers") setMode("layers");
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
  state.jobs.layers = null;
  state.layerImages = [];
  state.visible = [];
  state.file = file;
  state.localUrl = URL.createObjectURL(file);
  const probe = new Image();
  probe.onload = () => {
    state.inputSize = [probe.naturalWidth, probe.naturalHeight];
    renderResolutionNote();
    byId("input-thumb").src = state.localUrl;
    byId("input-name").textContent = file.name;
    byId("input-dimensions").textContent = `${probe.naturalWidth} × ${probe.naturalHeight} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
    byId("input-summary").hidden = false;
    byId("upload-zone").hidden = true;
    state.view = "input";
    byId("metric-status").textContent = "Ready for input";
    byId("metric-time").textContent = "—";
    byId("metric-error").textContent = "—";
    renderJob();
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

function renderResolutionNote() {
  const input = state.inputSize ? `Input ${displaySize(state.inputSize)} → ` : "";
  byId("layer-resolution-note").textContent = `${input}${state.resolution} px working size. Ming Layers outputs up to 1024 px; larger inputs are resized for the model. Source-size masked cutouts are available after splitting larger images.`;
}

function setView(view) {
  if (state.mode === "design") return;
  if (view !== "input" && state.job?.status !== "done") return;
  state.view = view;
  renderPreview();
}

function setArtworkImage(image, source, alt) {
  image.alt = alt;
  const reveal = () => {
    const active = image.id === "design-image" ? state.mode === "design" :
      state.mode === "layers" && !["layers", "split"].includes(state.view);
    if (image.getAttribute("src") === source && active) image.hidden = false;
  };
  if (image.getAttribute("src") !== source) {
    image.hidden = true;
    image.onload = reveal;
    image.src = source;
  } else {
    image.hidden = !(image.complete && image.naturalWidth > 0);
    if (image.hidden) image.onload = reveal;
  }
}

function sizeArtworkFrame(width, height) {
  const frame = byId("artwork-frame");
  frame.style.aspectRatio = `${width} / ${height}`;
  if (state.zoom !== "fit") {
    frame.style.width = `${width * Number(state.zoom)}px`;
    return;
  }
  const viewport = byId("canvas-viewport");
  const style = getComputedStyle(viewport);
  const availableWidth = viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const availableHeight = viewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  const fittedWidth = Math.min(width, availableWidth, availableHeight * width / height);
  frame.style.width = `${Math.max(1, Math.floor(fittedWidth))}px`;
}

function renderPreview() {
  const job = state.job;
  const finished = job?.status === "done";
  const designMode = state.mode === "design";
  byId("preview-title").textContent = designMode ? "Design canvas" : "Layer canvas";
  byId("view-tabs").hidden = designMode;
  document.querySelectorAll(".view-tabs button").forEach((tab) => {
    tab.disabled = tab.dataset.view !== "input" && !finished;
    tab.classList.toggle("active", tab.dataset.view === state.view);
  });
  const source = designMode ? job?.design_url : state.localUrl || job?.input_url;
  const empty = !source;
  byId("canvas-empty").hidden = !empty;
  byId("artwork-frame").hidden = empty;
  if (empty) {
    state.previewSize = null;
    byId("split-control").hidden = true;
    byId("canvas-caption").textContent = designMode ? "Generated design will appear here" : "RGBA raster layers · text remains pixels";
    byId("metric-size").textContent = "—";
    return;
  }

  const frame = byId("artwork-frame");
  const image = byId("artwork-image");
  const designImage = byId("design-image");
  const canvas = byId("layer-canvas");
  const split = byId("split-stack");
  const outputSize = designMode ? job?.output_size : finished ? job.metrics.output_size : state.inputSize || job?.input_size;
  const width = outputSize?.[0] || 1024;
  const height = outputSize?.[1] || 1024;
  state.previewSize = [width, height];
  sizeArtworkFrame(width, height);
  image.hidden = designMode || state.view === "layers" || state.view === "split";
  designImage.hidden = !designMode;
  canvas.hidden = designMode || state.view !== "layers";
  split.hidden = designMode || state.view !== "split";
  byId("split-control").hidden = designMode || state.view !== "split";

  if (designMode) {
    setArtworkImage(designImage, source, "Generated design");
    byId("canvas-caption").textContent = "Generated design · ready to download or split";
  } else if (state.view === "input") {
    setArtworkImage(image, source, "Flattened input design");
    byId("canvas-caption").textContent = "Original flattened design";
  } else if (state.view === "recomposed") {
    setArtworkImage(image, job.recomposed_url, "Recomposed design from generated layers");
    byId("canvas-caption").textContent = "Generated layers recomposed back to front";
  } else if (state.view === "difference") {
    setArtworkImage(image, job.difference_url, "Amplified pixel difference between input and recomposition");
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
  const job = state.job;
  byId("result-actions").hidden = state.mode !== "layers" || job?.status !== "done";
  byId("design-actions").hidden = state.mode !== "design" || job?.status !== "done";
  byId("source-export").hidden = state.mode !== "layers" || job?.status !== "done" || !job.source_zip_url;
  if (!byId("source-export").hidden) {
    byId("download-source-cutouts").href = job.source_zip_url;
    byId("download-source-cutouts").textContent = `Download ${displaySize(job.input_size)} cutouts ↓`;
    byId("source-export-note").textContent = `Original pixels under ${displaySize(job.metrics.output_size)} model masks. These are source-size raster cutouts, not higher-resolution model output; edges may need cleanup.`;
  }
  if (state.mode === "design" && job?.status === "done") {
    byId("download-design").href = job.design_url;
    byId("finish-design").href = `/finish?job=${job.id}`;
    if (state.designResult?.id !== job.id) {
      const card = makeElement("div", "design-result");
      const thumbnail = makeElement("img");
      thumbnail.src = job.design_url;
      thumbnail.alt = "Generated design thumbnail";
      card.append(thumbnail, makeElement("p", "", job.design_prompt));
      if (job.enhancement === "codex") {
        const link = makeElement("a", "", "View structured prompt ↗");
        link.href = `/api/jobs/${job.id}/assets/manifest.json`;
        link.target = "_blank";
        link.rel = "noopener";
        card.append(link);
      }
      state.designResult = {id: job.id, card};
    }
    if (list.firstElementChild !== state.designResult.card) list.replaceChildren(state.designResult.card);
    return;
  }
  list.replaceChildren();
  if (job?.status !== "done") {
    const placeholder = makeElement("div", "result-placeholder");
    placeholder.append(makeElement("span", "", "▧"), makeElement("p", "", state.mode === "design" ? "No design generated yet" : "Nothing separated yet"));
    list.append(placeholder);
    return;
  }
  byId("download-zip").href = job.zip_url;
  byId("finish-layers").href = `/finish?job=${job.id}`;
  job.layers.forEach((description, index) => {
    const card = makeElement("div", "result-card");
    card.classList.toggle("hidden-layer", !state.visible[index]);
    const thumbnail = makeElement("img");
    thumbnail.src = job.layer_urls[index];
    thumbnail.alt = `Layer ${index + 1}`;
    const copy = makeElement("div", "result-card-copy");
    const descriptionText = makeElement("span", "", description);
    descriptionText.title = description;
    copy.append(makeElement("strong", "", `Layer ${String(index + 1).padStart(2, "0")}`), descriptionText);
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

function timingBreakdown(job) {
  const parts = [];
  if (job.rewrite_seconds !== undefined) parts.push(`Codex ${secondsLabel(job.rewrite_seconds)}`);
  if (job.started_at && job.created_at) {
    const queued = (Date.parse(job.started_at) - Date.parse(job.created_at)) / 1000;
    if (queued >= 1) parts.push(`Queue ${secondsLabel(queued)}`);
  }
  if (job.load_seconds !== undefined) parts.push(`Model load ${secondsLabel(job.load_seconds)}`);
  if (job.generation_seconds !== undefined) parts.push(`Generation ${secondsLabel(job.generation_seconds)}`);
  return parts.join(" · ");
}

function renderJob() {
  const job = state.job;
  const card = byId("job-card");
  card.className = "job-card";
  if (!job) {
    byId("job-stage").textContent = "No job running";
    byId("job-message").textContent = state.mode === "design" ? "Your generated design will appear here." : "Your generated layers will appear here.";
    byId("job-clock").textContent = "";
    byId("job-breakdown").textContent = "";
    byId("metric-status").textContent = "Ready";
    byId("metric-time").textContent = "—";
    byId("metric-error").textContent = "—";
    byId("generate-button").disabled = false;
    byId("generate-design-button").disabled = false;
    return;
  }
  card.classList.add(job.status);
  const names = {
    queued: "Queued for Spark 2",
    loading: "Loading model",
    running: state.mode === "design" ? "Generating design" : "Generating layers",
    saving: state.mode === "design" ? "Saving design" : "Saving PNGs",
    done: state.mode === "design" ? "Design ready" : "Layers ready",
    error: "Run failed",
  };
  const messages = {
    queued: "Your job is waiting for the single GPU worker.",
    loading: "The checkpoint is loading into GPU memory. This can take several minutes.",
    running: "The model is working. The timer shows elapsed time; step progress is not available here.",
    saving: state.mode === "design" ? "Generation finished. Saving the PNG." : "Generation finished. Writing layers, comparison, and ZIP.",
    done: state.mode === "design" ? "Download the design or send it directly to layer splitting." : "Inspect individual layers and compare the recomposition with your input.",
    error: job.error || "Something went wrong. Your input and layer plan are still here.",
  };
  byId("job-stage").textContent = names[job.status] || job.status;
  byId("job-message").textContent = messages[job.status] || "";
  byId("metric-status").textContent = names[job.status] || job.status;
  byId("metric-time").textContent = secondsLabel(job.generation_seconds);
  byId("metric-error").textContent = job.metrics ? `${job.metrics.rgb_mae_0_to_255} / 255` : "—";
  byId("job-breakdown").textContent = timingBreakdown(job);
  const active = ["queued", "loading", "running", "saving"].includes(job.status);
  byId("generate-button").disabled = state.mode === "layers" && active;
  byId("generate-design-button").disabled = state.mode === "design" && active;
  updateClock();
}

function updateClock() {
  const job = state.job;
  if (!job) return;
  let seconds = job.total_seconds;
  if (seconds === undefined && job.created_at) seconds = (Date.now() - Date.parse(job.created_at)) / 1000;
  const label = job.status === "done" ? `${state.mode === "design" ? "Ming" : "Layer"} run` : "Elapsed";
  byId("job-clock").textContent = `${label}: ${secondsLabel(seconds)}`;
}

function showError(message, stage = "Check your input") {
  const card = byId("job-card");
  card.className = "job-card error";
  byId("job-stage").textContent = stage;
  byId("job-message").textContent = message;
  byId("job-clock").textContent = "";
  byId("job-breakdown").textContent = "";
  byId("metric-status").textContent = "Needs attention";
}

function showSubmitError(error) {
  if (error instanceof TypeError) {
    showError("Could not reach Spark 2. The Mac tunnel may have disconnected. Your input is still here; try again.", "Connection lost");
  } else {
    showError(error.message);
  }
}

async function pollJob() {
  if (!state.job) return;
  const mode = state.mode;
  const jobId = state.job.id;
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) throw new Error("Could not check the job status.");
    const updated = await response.json();
    state.jobs[mode] = updated;
    if (mode !== state.mode || state.job?.id !== jobId) return;
    state.job = updated;
    renderJob();
    if (state.job.status === "done") {
      clearInterval(state.pollHandle);
      state.pollHandle = null;
      if (mode === "layers") {
        await loadLayerImages(state.job.layer_urls);
        state.view = "recomposed";
      }
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
    state.jobs.layers = body;
    state.visible = [];
    state.layerImages = [];
    state.view = "input";
    renderJob();
    renderResults();
    renderPreview();
    startPolling();
  } catch (error) {
    byId("generate-button").disabled = false;
    showSubmitError(error);
  }
}

async function submitDesignJob(event) {
  event.preventDefault();
  const prompt = byId("design-prompt").value.trim();
  if (prompt.length < 5 || prompt.length > 5000) { showError("Describe the design in 5–5000 characters."); return; }
  const seed = Number(byId("design-seed-input").value);
  if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295) { showError("Choose a whole-number seed from 0 to 4294967295."); return; }
  const data = new FormData();
  data.append("resolution", String(state.designResolution));
  data.append("seed", String(seed));
  byId("generate-design-button").disabled = true;
  try {
    const labResponse = await fetch("/api/health", {cache: "no-store"});
    if (!labResponse.ok) throw new Error("The Lab server is not ready. Try again shortly.");
    if (byId("enhance-prompt").checked) {
      const rewriteStarted = performance.now();
      byId("job-stage").textContent = "Expanding prompt with Codex";
      byId("job-message").textContent = "Codex is describing the layout, colors, and exact text before Ming draws it.";
      byId("job-clock").textContent = "";
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 190000);
      let rewritten;
      try {
        const rewriteResponse = await fetch("http://127.0.0.1:8766/rewrite", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({prompt}), signal: controller.signal,
        });
        rewritten = await rewriteResponse.json();
        if (!rewriteResponse.ok) throw new Error(rewritten.error || "Codex could not expand this prompt.");
      } catch (error) {
        if (error.name === "AbortError") throw new Error("Codex took too long to expand the prompt.");
        if (error instanceof TypeError) throw new Error("The Codex helper on this Mac is not running. Start scripts/prompt_rewriter_bridge.py or uncheck Expand with Codex.");
        throw error;
      } finally {
        clearTimeout(timeout);
      }
      data.append("prompt", rewritten.prompt);
      data.append("source_prompt", prompt);
      data.append("enhancement", "codex");
      data.append("rewrite_seconds", String(((performance.now() - rewriteStarted) / 1000).toFixed(2)));
    } else {
      data.append("prompt", prompt);
    }
    const response = await fetch("/api/design-jobs", {method: "POST", body: data});
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The design job could not start.");
    state.job = body;
    state.jobs.design = body;
    renderJob();
    renderResults();
    renderPreview();
    startPolling();
  } catch (error) {
    byId("generate-design-button").disabled = false;
    showSubmitError(error);
  }
}

function setMode(mode) {
  if (mode !== "design" && mode !== "layers") return;
  state.mode = mode;
  state.job = state.jobs[mode];
  state.view = mode === "design" ? "input" : state.job?.status === "done" ? "recomposed" : "input";
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = null;
  document.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("selected", button.dataset.mode === mode));
  byId("design-setup").hidden = mode !== "design";
  byId("layer-setup").hidden = mode !== "layers";
  byId("result-title").textContent = mode === "design" ? "Design" : "Layers";
  byId("result-description").textContent = mode === "design" ? "Generate an image, download it, or send it to layer splitting." : "Toggle, solo, inspect, and download each transparent PNG.";
  byId("metric-error").parentElement.hidden = mode === "design";
  byId("metrics-strip").classList.toggle("design-metrics", mode === "design");
  if (mode === "layers" && state.job?.status === "done" && !state.layerImages.length) {
    const jobId = state.job.id;
    loadLayerImages(state.job.layer_urls).then(() => {
      if (state.mode !== "layers" || state.job?.id !== jobId) return;
      state.view = "recomposed";
      renderResults();
      renderPreview();
    }).catch(() => showError("Could not load layer previews."));
  }
  renderJob();
  renderResults();
  renderPreview();
  if (state.job && ["queued", "loading", "running", "saving"].includes(state.job.status)) startPolling();
}

async function sendToLayers() {
  const job = state.jobs.design;
  if (job?.status !== "done") return;
  const button = byId("send-to-layers");
  button.disabled = true;
  try {
    const response = await fetch(job.design_url);
    if (!response.ok) throw new Error("Could not load the generated design.");
    const file = new File([await response.blob()], `ming-design-${job.id.slice(0, 8)}.png`, {type: "image/png"});
    setMode("layers");
    state.resolution = 1024;
    document.querySelectorAll("[data-resolution]").forEach((item) => item.classList.toggle("selected", Number(item.dataset.resolution) === state.resolution));
    state.layers = [...DEFAULT_LAYERS];
    renderPlan();
    setInputFile(file);
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; }
}

async function updateHealth() {
  const status = byId("server-status");
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("offline");
    const body = await response.json();
    status.className = `server-status ${body.active_job ? "busy" : "online"}`;
    status.lastChild.textContent = body.active_job ? "GPU working" : body.model_loaded ? `${body.loaded_model === "design" ? "Design" : "Layer"} ready` : "GPU available";
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
    state.jobs.design = jobs.find((job) => job.kind === "design") || null;
    state.jobs.layers = jobs.find((job) => (job.kind || "layers") === "layers") || null;
    const latest = jobs[0];
    const mode = latest.kind === "design" ? "design" : "layers";
    const layerJob = state.jobs.layers;
    if (layerJob) {
      state.inputSize = layerJob.input_size;
      state.layers = [...layerJob.layers];
      state.resolution = layerJob.resolution;
      byId("seed-input").value = String(layerJob.seed);
      document.querySelectorAll("[data-resolution]").forEach((button) => button.classList.toggle("selected", Number(button.dataset.resolution) === state.resolution));
      renderPlan();
      renderResolutionNote();
      byId("input-thumb").src = layerJob.input_url;
      byId("input-name").textContent = "Previous input";
      byId("input-dimensions").textContent = displaySize(layerJob.input_size);
      byId("input-summary").hidden = false;
      byId("upload-zone").hidden = true;
      const inputResponse = await fetch(layerJob.input_url);
      if (inputResponse.ok) state.file = new File([await inputResponse.blob()], "previous-input.png", {type: "image/png"});
    }
    const designJob = state.jobs.design;
    if (designJob) {
      if (designJob.status === "done" && designJob.design_url) {
        const designImage = byId("design-image");
        designImage.src = designJob.design_url;
        if (designImage.decode) designImage.decode().catch(() => {});
      }
      byId("design-prompt").value = designJob.design_prompt;
      byId("design-seed-input").value = String(designJob.seed);
      state.designResolution = designJob.resolution;
      document.querySelectorAll("[data-design-resolution]").forEach((button) => button.classList.toggle("selected", Number(button.dataset.designResolution) === state.designResolution));
    }
    if (layerJob?.status === "done") {
      await loadLayerImages(layerJob.layer_urls);
      state.view = "recomposed";
    }
    setMode(mode);
  } catch {
    // The uploader remains usable if history is unavailable.
  }
}

function attachEvents() {
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  document.querySelectorAll("[data-design-resolution]").forEach((button) => button.addEventListener("click", () => {
    state.designResolution = Number(button.dataset.designResolution);
    document.querySelectorAll("[data-design-resolution]").forEach((item) => item.classList.toggle("selected", item === button));
  }));
  byId("design-form").addEventListener("submit", submitDesignJob);
  byId("send-to-layers").addEventListener("click", sendToLayers);
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
    renderResolutionNote();
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
renderResolutionNote();
attachEvents();
updateHealth();
restoreRecentJob();
new ResizeObserver(() => {
  if (state.zoom === "fit" && state.previewSize) sizeArtworkFrame(...state.previewSize);
}).observe(byId("canvas-viewport"));
setInterval(updateHealth, 10000);
setInterval(updateClock, 1000);
