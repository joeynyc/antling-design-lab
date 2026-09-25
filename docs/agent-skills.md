# Local Ming agent skills

The published `ling-ui-design` and `image-to-editable-ppt` skills from [inclusionAI/ling-cookbook](https://github.com/inclusionAI/ling-cookbook/tree/main/resources/recommended-skills) can use AntLing's local image API. Install them in your agent's skill directory and configure their local `.env` files to point to `http://127.0.0.1:8765/v1` through the SSH tunnel. Their image API key can be a local placeholder; AntLing's image routes do not use a paid image provider. These skill integrations are optional and separate from the Lab's prompt-expansion provider dropdown.

The web server implements two compatibility routes:

- `POST /v1/images/generations` accepts the Design skill's JSON request and returns a base64 image. It creates a normal Design job, so the result remains in `jobs/<job-id>/design.png` on Spark 2.
- `POST /v1/images/edits` accepts the skills' multipart image and numbered layer plan and returns ordered, base64 RGBA layers. It creates a normal Layers job, so the PNGs and ZIP remain in the usual Spark 2 job folder.

The `ling-ui-design` helper is configured for 12 steps and 512 px decomposition. Each skill has a private `.venv` in its installed directory with its declared dependencies; invoke its scripts with that skill's `.venv/bin/python`. The PPT renderer can use macOS Quick Look, with LibreOffice available as a fallback.

For example, from a target application root:

```bash
~/.codex/skills/ling-ui-design/.venv/bin/python \
  ~/.codex/skills/ling-ui-design/scripts/generate_image.py \
  --prompt 'An editorial landing-page visual reference' \
  --format png --out artifacts/reference.png
~/.codex/skills/ling-ui-design/.venv/bin/python \
  ~/.codex/skills/ling-ui-design/scripts/decompose_layers.py \
  --image artifacts/reference.png --outdir artifacts/reference-layers --no-pe
```

For a slide, run the installed `image-to-editable-ppt` workflow with its virtual environment, then inspect and assemble the resulting slide as its `SKILL.md` directs. Give it an image and a numbered front-to-back layer plan; the local endpoint supports both its compact `4 layers: 1 ..., 2 ...` form and the UI skill's `Layer 1 (text): ...` lines.

## Local limits

- `auto` and `512` layer requests use the tested 512 px path and can reuse the dual-model cache. `1k` uses 1024 px and unloads the inactive checkpoint first. The local Layer model does not offer a 2K output size.
- The adapter uses the model's validated 12 sampling steps. It accepts the UI skill's original 14-step field for compatibility but runs 12; the installed UI skill is already configured to send 12.
- The local adapter does **not** run a VLM prompt enhancer, super-resolution, or the external service's asset detector. Supply a precise numbered plan, use `--no-pe` with the UI helper, and inspect each layer or crop before using it. The PPT skill performs its own planning and crop analysis.
- Image-to-editable-PPT can run locally, but its default 512 px decomposition may limit fidelity of fine text and artwork. For a higher-resolution PPT run, set `DECOMPOSE_SIZE_FINAL=1024x1024` and `DECOMPOSE_TIMEOUT_FINAL_S=1800` in the shell that invokes its decomposition script; this unloads the other checkpoint and runs substantially longer.
- The compatibility routes share the existing single-GPU queue, local-only host binding, and persistent `jobs/` directory. Keep the SSH tunnel connected while running skills on the Mac.

Installed skills become discoverable to Codex on a new task turn. Their `.env` files and generated artifacts are not committed to this repository.

## Verified on Spark 2

On 2026-09-23, the installed Ling UI helper generated a 1024 px PNG through `/v1/images/generations`, then decomposed it into four valid 512 px RGBA layers through `/v1/images/edits`. Its crop helper produced three candidate assets. The installed PPT skill submitted the same image with its compact layer plan, received four layers, and reused the loaded Layer checkpoint with **0.0 seconds** of model loading. Its first-pass preview and report were written locally. A one-slide test scene compiled, passed PPTX structure checks (two editable text boxes, three native shapes, one picture), and rendered through macOS Quick Look. The test slide verifies the pipeline and editability, not production visual fidelity; the source layers still require inspection and may need refinement. The Ling UI skill's own 123 tests and the local adapter's eight contract/cache tests also passed.
