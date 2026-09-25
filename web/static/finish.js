const $ = (id) => document.getElementById(id);
const FORMATS = {landscape: [1600, 900], square: [1080, 1080]};
const editor = {project: null, job: null, original: null, layers: [], bounds: [], selected: null,
  cleaning: false, backdrop: "checker", drag: null, stroke: null, scheduled: false,
  prepared: new Map(), saveTimer: null, savePending: false, saving: false};

function label(message) { $("save-state").textContent = message; }
function sourceUrl(job) { return job.design_url || job.input_url; }
function image(url) { return new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error("Could not load a saved image.")); img.src = url; }); }
async function getJson(url) { const response = await fetch(url); if (!response.ok) throw new Error("Could not load saved work."); return response.json(); }
function dimensions() { return FORMATS[editor.project?.size || "landscape"]; }
function current() { return editor.project?.elements.find((item) => item.id === editor.selected); }
function updateUrl() { const params = new URLSearchParams(); if (editor.project?.id) params.set("project", editor.project.id); else if (editor.job) params.set("job", editor.job.id); history.replaceState(null, "", `/finish${params.size ? `?${params}` : ""}`); }

function defaultProject(job) { return {title: job.kind === "design" ? "New design asset" : "New layered asset", source_job_id: job.id,
  size: "landscape", background: "original", background_color: "#16172e", focal_x: .5, focal_y: .5, elements: []}; }

async function loadSource(jobId, project = null) {
  while (editor.saving) await new Promise(resolve => setTimeout(resolve, 25));
  if (editor.saveTimer) { clearTimeout(editor.saveTimer); editor.saveTimer = null; await saveProject(); }
  while (editor.saving) await new Promise(resolve => setTimeout(resolve, 25));
  label("Loading…");
  const job = await getJson(`/api/jobs/${jobId}`);
  if (job.status !== "done") throw new Error("Select a completed job.");
  const original = await image(sourceUrl(job));
  const layers = job.layer_urls ? await Promise.all(job.layer_urls.map(image)) : [];
  editor.job = job; editor.original = original; editor.layers = layers;
  editor.bounds = layers.map(layerBounds); editor.prepared.clear();
  editor.project = project || defaultProject(job); editor.selected = null; editor.cleaning = false;
  if (![...$("source-select").options].some(option => option.value === job.id)) {
    $("source-select").add(new Option(`${job.kind === "design" ? "Design" : "Split"} · ${job.id.slice(0, 8)}`, job.id));
  }
  $("source-select").value = job.id;
  $("project-select").value = project?.id || "";
  $("finish-empty").hidden = true; $("finish-canvas").hidden = false;
  $("layer-source").hidden = layers.length === 0;
  syncForm(); renderAvailableLayers(); renderElements(); renderInspector(); scheduleDraw(); updateUrl(); label(project ? "Saved" : "New project");
}

function layerBounds(img) {
  const probe = document.createElement("canvas"); probe.width = img.naturalWidth; probe.height = img.naturalHeight;
  const ctx = probe.getContext("2d", {willReadFrequently: true}); ctx.drawImage(img, 0, 0);
  const pixels = ctx.getImageData(0, 0, probe.width, probe.height).data;
  let left = probe.width, top = probe.height, right = -1, bottom = -1;
  for (let y = 0; y < probe.height; y++) for (let x = 0; x < probe.width; x++) {
    if (pixels[(y * probe.width + x) * 4 + 3] < 8) continue;
    left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
  }
  return right < left ? {x: 0, y: 0, width: probe.width, height: probe.height} :
    {x: left, y: top, width: right - left + 1, height: bottom - top + 1};
}

function syncForm() {
  const p = editor.project; if (!p) return;
  $("project-title").value = p.title; $("background-select").value = p.background;
  $("background-color").value = p.background_color;
  $("background-color-wrap").hidden = p.background !== "solid";
  $("focal-controls").hidden = p.background !== "original";
  $("focal-x").value = Math.round(p.focal_x * 100); $("focal-y").value = Math.round(p.focal_y * 100);
  document.querySelectorAll("[data-size]").forEach(button => button.classList.toggle("active", button.dataset.size === p.size));
  const [w, h] = dimensions(); $("canvas-size").textContent = `${w} × ${h}`;
  $("finish-canvas").width = w; $("finish-canvas").height = h;
  applyZoom();
}

function applyZoom() {
  const canvas = $("finish-canvas"), zoom = $("canvas-zoom").value;
  if (zoom === "fit") { canvas.style.width = "auto"; canvas.style.height = "auto"; canvas.style.maxWidth = "100%"; canvas.style.maxHeight = "100%"; }
  else { const [w, h] = dimensions(); canvas.style.width = `${w * Number(zoom)}px`; canvas.style.height = `${h * Number(zoom)}px`; canvas.style.maxWidth = "none"; canvas.style.maxHeight = "none"; }
}

function renderAvailableLayers() {
  const wrap = $("available-layers"); wrap.replaceChildren();
  editor.layers.forEach((_, index) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "available-layer";
    const thumb = document.createElement("img"); thumb.src = editor.job.layer_urls[index]; thumb.alt = "";
    const span = document.createElement("span"); span.textContent = `+ ${editor.job.layers[index] || `Layer ${index + 1}`}`;
    button.title = editor.job.layers[index] || "Add layer"; button.append(thumb, span);
    button.addEventListener("click", () => addLayer(index)); wrap.append(button);
  });
}

function renderElements() {
  const wrap = $("element-list"); wrap.replaceChildren();
  for (let i = editor.project.elements.length - 1; i >= 0; i--) {
    const item = editor.project.elements[i]; const button = document.createElement("button");
    button.type = "button"; button.className = `element-row${item.id === editor.selected ? " active" : ""}`;
    button.textContent = `${item.type === "text" ? "T" : "▧"}  ${item.type === "text" ? item.text.split("\n")[0] || "Text" : editor.job.layers[item.layer_index] || `Layer ${item.layer_index + 1}`}`;
    button.title = button.textContent; button.addEventListener("click", () => select(item.id)); wrap.append(button);
  }
}

function select(id) { editor.selected = id; editor.cleaning = false; $("finish-canvas").classList.remove("cleaning"); renderElements(); renderInspector(); scheduleDraw(); }
function renderInspector() {
  const item = current();
  $("inspect-empty").hidden = !!item; $("text-inspector").hidden = item?.type !== "text";
  $("layer-inspector").hidden = item?.type !== "layer"; $("element-actions").hidden = !item;
  $("inspect-heading").textContent = item ? item.type === "text" ? "Edit text" : "Inspect layer" : "Select an element";
  $("edge-tools").hidden = !editor.cleaning || item?.type !== "layer";
  if (item?.type === "text") { $("text-copy").value = item.text; $("text-size").value = item.font_size;
    $("text-weight").value = String(item.weight); $("text-color").value = item.color; }
  if (item?.type === "layer") { $("layer-inspector-name").textContent = editor.job.layers[item.layer_index] || "Raster layer";
    $("layer-width").value = Math.round(item.width); $("layer-height").value = Math.round(item.height); }
}

function addText() {
  if (!editor.project) return;
  const [w, h] = dimensions(); const item = {id: crypto.randomUUID().replaceAll("-", ""), type: "text", text: "Your headline here",
    x: Math.round(w * .08), y: Math.round(h * .18), width: Math.round(w * .7), font_size: Math.round(w * .055), color: "#ffffff", weight: 700};
  editor.project.elements.push(item); changed(); select(item.id);
}

function coverPlacement() {
  const [w, h] = dimensions(), img = editor.original;
  const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
  const drawnW = img.naturalWidth * scale, drawnH = img.naturalHeight * scale;
  return {x: (w - drawnW) * editor.project.focal_x, y: (h - drawnH) * editor.project.focal_y, width: drawnW, height: drawnH};
}

function addLayer(index) {
  if (!editor.project) return;
  const bound = editor.bounds[index], img = editor.layers[index], place = coverPlacement();
  const x = place.x + bound.x / img.naturalWidth * place.width;
  const y = place.y + bound.y / img.naturalHeight * place.height;
  const width = bound.width / img.naturalWidth * place.width;
  const height = bound.height / img.naturalHeight * place.height;
  const item = {id: crypto.randomUUID().replaceAll("-", ""), type: "layer", layer_index: index,
    x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height), erase: []};
  editor.project.elements.push(item); changed(); select(item.id);
}

function drawText(ctx, item) {
  ctx.save(); ctx.fillStyle = item.color; ctx.textBaseline = "top";
  ctx.font = `${item.weight} ${item.font_size}px Inter, Arial, sans-serif`;
  const lineHeight = item.font_size * 1.14, maxWidth = item.width || dimensions()[0] - item.x - 40;
  let y = item.y;
  for (const paragraph of item.text.split("\n")) {
    let line = "";
    for (const word of paragraph.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(next).width > maxWidth) { ctx.fillText(line, item.x, y); y += lineHeight; line = word; }
      else line = next;
    }
    ctx.fillText(line, item.x, y); y += lineHeight;
  }
  ctx.restore();
  return Math.max(item.font_size, y - item.y);
}

function preparedLayer(item) {
  const signature = JSON.stringify(item.erase || []);
  const cached = editor.prepared.get(item.id); if (cached?.signature === signature) return cached.canvas;
  const bound = editor.bounds[item.layer_index], img = editor.layers[item.layer_index];
  const canvas = document.createElement("canvas"); canvas.width = bound.width; canvas.height = bound.height;
  const ctx = canvas.getContext("2d"); ctx.drawImage(img, bound.x, bound.y, bound.width, bound.height, 0, 0, bound.width, bound.height);
  ctx.globalCompositeOperation = "destination-out"; ctx.lineCap = "round"; ctx.lineJoin = "round";
  for (const stroke of item.erase || []) {
    ctx.lineWidth = stroke.radius * 2; ctx.beginPath();
    stroke.points.forEach(([x, y], i) => { if (i === 0) ctx.moveTo(x * bound.width, y * bound.height); else ctx.lineTo(x * bound.width, y * bound.height); });
    ctx.stroke(); const [x, y] = stroke.points[0]; ctx.beginPath(); ctx.arc(x * bound.width, y * bound.height, stroke.radius, 0, Math.PI * 2); ctx.fill();
  }
  editor.prepared.set(item.id, {signature, canvas}); return canvas;
}

function draw(checker = true) {
  if (!editor.project || !editor.original) return;
  const canvas = $("finish-canvas"), [w, h] = dimensions();
  const ctx = canvas.getContext("2d"); ctx.clearRect(0, 0, w, h);
  if (editor.cleaning && checker) {
    ctx.fillStyle = editor.backdrop === "dark" ? "#151728" : "#ffffff"; ctx.fillRect(0, 0, w, h);
    if (editor.backdrop === "checker") {
      ctx.fillStyle = "#dddce4"; for (let y = 0; y < h; y += 40) for (let x = (Math.floor(y / 40) % 2) * 40; x < w; x += 80) ctx.fillRect(x, y, 40, 40);
    }
  } else if (editor.project.background === "solid") { ctx.fillStyle = editor.project.background_color; ctx.fillRect(0, 0, w, h); }
  else { const place = coverPlacement(); ctx.drawImage(editor.original, place.x, place.y, place.width, place.height); }
  const items = editor.cleaning ? editor.project.elements.filter(item => item.id === editor.selected) : editor.project.elements;
  for (const item of items) {
    if (item.type === "text") drawText(ctx, item);
    else if (editor.layers[item.layer_index]) ctx.drawImage(preparedLayer(item), item.x, item.y, item.width, item.height);
  }
  const selected = current();
  if (checker && selected && !editor.cleaning) {
    ctx.save(); ctx.strokeStyle = "#28d8d7"; ctx.lineWidth = 3; ctx.setLineDash([9, 5]);
    const height = selected.type === "text" ? textHeight(selected) : selected.height;
    ctx.strokeRect(selected.x - 5, selected.y - 5, selected.width + 10, height + 10); ctx.restore();
  }
}

function textHeight(item) { const scratch = document.createElement("canvas").getContext("2d"); return drawText(scratch, item); }
function scheduleDraw() { if (editor.scheduled) return; editor.scheduled = true; requestAnimationFrame(() => { editor.scheduled = false; draw(); }); }
function changed() { label("Unsaved changes"); clearTimeout(editor.saveTimer); editor.saveTimer = setTimeout(() => { editor.saveTimer = null; saveProject(); }, 1400); scheduleDraw(); }

async function saveProject() {
  if (!editor.project) return;
  if (editor.saving) { editor.savePending = true; return; }
  editor.saving = true; label("Saving…");
  const p = editor.project, url = p.id ? `/api/projects/${p.id}` : "/api/projects";
  try {
    const response = await fetch(url, {method: p.id ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(p)});
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Could not save project.");
    if (editor.project === p) { p.id = result.id; p.created_at = result.created_at; p.updated_at = result.updated_at; updateUrl(); label("Saved"); await refreshProjects(); }
  } catch (error) { label(`Save failed: ${error.message}`); }
  finally { editor.saving = false; if (editor.savePending) { editor.savePending = false; saveProject(); } }
}

function exportPng() {
  if (!editor.project) return;
  const selected = editor.selected, cleaning = editor.cleaning;
  editor.selected = null; editor.cleaning = false; draw(false);
  $("finish-canvas").toBlob(blob => {
    editor.selected = selected; editor.cleaning = cleaning; scheduleDraw();
    if (!blob) { label("Export failed"); return; }
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${editor.project.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "antling-design"}.png`;
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  }, "image/png");
}

function pointerPosition(event) { const rect = $("finish-canvas").getBoundingClientRect(), [w, h] = dimensions(); return {x: (event.clientX - rect.left) / rect.width * w, y: (event.clientY - rect.top) / rect.height * h}; }
function strokePoint(point, item) { return [Math.max(0, Math.min(1, (point.x - item.x) / item.width)), Math.max(0, Math.min(1, (point.y - item.y) / item.height))]; }
function pointerDown(event) {
  if (!editor.project) return;
  const point = pointerPosition(event), canvas = $("finish-canvas");
  if (editor.cleaning) {
    const item = current(); if (!item || item.type !== "layer") return;
    if (item.erase.length >= 100) { label("Cleanup limit reached; undo a stroke to continue."); return; }
    const bound = editor.bounds[item.layer_index]; const scale = item.width / bound.width;
    const stroke = {radius: Math.max(1, Math.min(200, Math.round(Number($("edge-brush").value) / Math.max(.1, scale)))), points: [strokePoint(point, item)]};
    item.erase.push(stroke); editor.stroke = stroke; editor.prepared.delete(item.id); changed(); canvas.setPointerCapture(event.pointerId); return;
  }
  const items = [...editor.project.elements].reverse();
  const hit = items.find(item => point.x >= item.x - 5 && point.x <= item.x + item.width + 5 && point.y >= item.y - 5 && point.y <= item.y + (item.type === "text" ? textHeight(item) : item.height) + 5);
  if (hit) { select(hit.id); editor.drag = {start: point, x: hit.x, y: hit.y}; canvas.setPointerCapture(event.pointerId); }
  else select(null);
}
function pointerMove(event) {
  if (!editor.drag && !editor.stroke) return;
  const point = pointerPosition(event), item = current(); if (!item) return;
  if (editor.drag) { item.x = Math.round(editor.drag.x + point.x - editor.drag.start.x); item.y = Math.round(editor.drag.y + point.y - editor.drag.start.y); changed(); }
  else if (editor.stroke) { if (editor.stroke.points.length < 500) editor.stroke.points.push(strokePoint(point, item)); editor.prepared.delete(item.id); changed(); }
}
function pointerUp() { editor.drag = null; editor.stroke = null; }

async function refreshProjects() {
  const projects = await getJson("/api/projects"); const select = $("project-select"), selected = editor.project?.id || "";
  select.replaceChildren(new Option("New project", ""));
  projects.forEach(p => select.add(new Option(`${p.title} · ${p.size}`, p.id)));
  select.value = selected;
}
async function refreshSources() {
  const jobs = await getJson("/api/jobs"), select = $("source-select");
  for (const job of jobs.filter(item => item.status === "done")) {
    select.add(new Option(`${job.kind === "design" ? "Design" : "Split"} · ${job.id.slice(0, 8)} · ${(job.created_at || "").slice(0, 10)}`, job.id));
  }
}
function bind() {
  $("source-select").addEventListener("change", async e => { if (!e.target.value) return; try { await loadSource(e.target.value); } catch (error) { label(error.message); } });
  $("project-select").addEventListener("change", async e => { if (!e.target.value) return; try { const p = await getJson(`/api/projects/${e.target.value}`); await loadSource(p.source_job_id, p); } catch (error) { label(error.message); } });
  $("project-title").addEventListener("input", e => { if (editor.project) { editor.project.title = e.target.value; changed(); } });
  document.querySelectorAll("[data-size]").forEach(button => button.addEventListener("click", () => { if (!editor.project || editor.project.size === button.dataset.size) return;
    const old = dimensions(); editor.project.size = button.dataset.size; const next = dimensions();
    for (const item of editor.project.elements) { item.x = Math.round(item.x * next[0] / old[0]); item.y = Math.round(item.y * next[1] / old[1]); item.width = Math.round(item.width * next[0] / old[0]); if (item.type === "layer") item.height = Math.round(item.height * next[1] / old[1]); }
    syncForm(); changed(); }));
  $("background-select").addEventListener("change", e => { if (editor.project) { editor.project.background = e.target.value; syncForm(); changed(); } });
  $("background-color").addEventListener("input", e => { if (editor.project) { editor.project.background_color = e.target.value; changed(); } });
  for (const axis of ["x", "y"]) $( `focal-${axis}` ).addEventListener("input", e => { if (editor.project) { editor.project[`focal_${axis}`] = Number(e.target.value) / 100; changed(); } });
  $("add-text").addEventListener("click", addText);
  $("canvas-zoom").addEventListener("change", applyZoom);
  $("text-copy").addEventListener("input", e => { const item = current(); if (item?.type === "text") { item.text = e.target.value; renderElements(); changed(); } });
  $("text-size").addEventListener("input", e => { const item = current(); if (item?.type === "text") { item.font_size = Math.max(12, Math.min(300, Number(e.target.value) || 12)); changed(); } });
  $("text-weight").addEventListener("change", e => { const item = current(); if (item?.type === "text") { item.weight = Number(e.target.value); changed(); } });
  $("text-color").addEventListener("input", e => { const item = current(); if (item?.type === "text") { item.color = e.target.value; changed(); } });
  $("layer-width").addEventListener("change", e => { const item = current(); if (item?.type === "layer") { const ratio = item.height / item.width; item.width = Math.max(1, Number(e.target.value) || item.width); item.height = Math.round(item.width * ratio); renderInspector(); changed(); } });
  $("layer-height").addEventListener("change", e => { const item = current(); if (item?.type === "layer") { const ratio = item.width / item.height; item.height = Math.max(1, Number(e.target.value) || item.height); item.width = Math.round(item.height * ratio); renderInspector(); changed(); } });
  $("edge-mode").addEventListener("click", () => { editor.cleaning = true; $("finish-canvas").classList.add("cleaning"); renderInspector(); scheduleDraw(); });
  $("done-edges").addEventListener("click", () => { editor.cleaning = false; $("finish-canvas").classList.remove("cleaning"); renderInspector(); scheduleDraw(); });
  $("edge-backdrop").addEventListener("change", e => { editor.backdrop = e.target.value; scheduleDraw(); });
  $("undo-erase").addEventListener("click", () => { const item = current(); if (item?.erase?.length) { item.erase.pop(); editor.prepared.delete(item.id); changed(); } });
  $("clear-erase").addEventListener("click", () => { const item = current(); if (item?.erase?.length) { item.erase = []; editor.prepared.delete(item.id); changed(); } });
  $("element-delete").addEventListener("click", () => { editor.project.elements = editor.project.elements.filter(item => item.id !== editor.selected); editor.prepared.delete(editor.selected); select(null); changed(); });
  for (const [id, delta] of [["element-back", -1], ["element-front", 1]]) $(id).addEventListener("click", () => { const list = editor.project.elements, index = list.findIndex(item => item.id === editor.selected), next = index + delta; if (next < 0 || next >= list.length) return; [list[index], list[next]] = [list[next], list[index]]; renderElements(); changed(); });
  const canvas = $("finish-canvas"); canvas.addEventListener("pointerdown", pointerDown); canvas.addEventListener("pointermove", pointerMove); canvas.addEventListener("pointerup", pointerUp); canvas.addEventListener("pointercancel", pointerUp);
  $("save-button").addEventListener("click", () => { clearTimeout(editor.saveTimer); editor.saveTimer = null; saveProject(); }); $("export-button").addEventListener("click", exportPng);
}
async function boot() {
  bind(); try {
    await Promise.all([refreshSources(), refreshProjects()]);
    const params = new URLSearchParams(location.search);
    if (params.has("project")) { const p = await getJson(`/api/projects/${params.get("project")}`); await loadSource(p.source_job_id, p); }
    else if (params.has("job")) await loadSource(params.get("job"));
  } catch (error) { label(error.message); }
}
boot();
