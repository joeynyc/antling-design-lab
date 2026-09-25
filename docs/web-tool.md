# AntLing Design Lab

The web interface runs on Spark 2 (GX10) with pinned Ming Image Design and Design-Layer checkpoints. It is a single-user, local tool. The Spark binds port 8765 to its own loopback address; an SSH tunnel makes it available on your Mac.

## Start

On Spark 2, from this project's directory:

```bash
docker build -t ming-image-layer:gx10 -f Dockerfile.gx10 .
bash scripts/run_web_gx10.sh
```

On macOS, install the reconnecting SSH tunnel once (replace the SSH host alias if needed):

```bash
bash scripts/install_web_tunnel_macos.sh YOUR_SPARK_SSH_HOST
```

For a temporary tunnel instead, run this in a separate terminal:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_SPARK_SSH_HOST
```

Open <http://127.0.0.1:8765/>. The installed tunnel reconnects after a connection drop or Mac login; a temporary tunnel needs its terminal left open. Stop the web container with `docker stop ming-layer-web` on Spark 2. The container expects `upstream/`, `model/`, and `design-model/` in the project directory; follow the [README setup](../README.md#run-on-a-dgx-spark) first. See [the GX10 smoke test](gx10-smoke.md) and [checkpoint coexistence notes](gx10-coexist.md) for measured results.

## Use

In **Generate design**, enter a plain prompt and choose **Prompt expansion**. Direct mode sends the prompt unchanged to Ming and needs no text-model account. Any configured OpenAI, Claude, Z.ai, DeepSeek, or compatible endpoint can expand it into a structured layout using the [Ming rewriter instructions](../resources/t2i_rewriter_system_prompt.txt). The server validates the JSON format before image generation. The original prompt remains in job history; the structured prompt is saved in the job manifest. The selected external provider receives your prompt, so use direct mode or a local compatible model when the text must stay on your device. Select 2048 for detailed output or 1024 for speed; inspect lettering because the image model can still distort small text. Download the PNG or choose **Send to Layers**.

### Optional Codex CLI helper

On a Mac with a signed-in Codex CLI, `bash scripts/install_prompt_bridge_macos.sh` runs a local helper on `127.0.0.1:8766`. When the browser sees it, **Codex CLI on this Mac** appears in the provider dropdown. It uses that signed-in account, not an OpenAI API key. This helper is optional and stays on the Mac; image inference continues on the Spark. If it is unavailable, use direct mode or a Spark-configured provider. The helper currently accepts Lab requests from `http://127.0.0.1:8765`; use the default tunnel address.

In **Split layers**, upload a PNG, JPEG, or WebP design (20 MB and 16 megapixels maximum), or use the transferred design. Write 2–8 layer descriptions in **front-to-back** order, with the background last. Name text exactly where possible. Choose 512 or 1024 working size and a seed, then generate. **1024 is the largest Layer model output**; a 2048 design is resized for inference. Sending a generated design into the split workspace selects 1024 by default, while 512 remains a faster option. Only one inference job runs at once; up to three can wait in the queue. A cold checkpoint load still takes several minutes. The published Layer sample at 1024 took about 16 minutes end to end on GX10; other images may differ.

After generation, inspect the recomposed image, toggle or solo layers, compare input and output with the split view, and download individual RGBA PNGs or a ZIP bundle. Difference is an 8× amplified diagnostic view; its RGB error is a pixel difference against the input, not an editing-quality score. Text remains raster pixels. The status card distinguishes prompt expansion, model loading, generation, and any queue wait when those timings are available. Its **Ming run** time excludes prompt expansion and queue wait.

Use **Finish this design** or **Finish with layers** to open a completed job in the `/finish` editor. You can also choose a recent completed job or reopen a saved project there. Choose X landscape (1600 × 900) or square (1080 × 1080), position the original image in the crop, or use a solid background. Add editable text and, for split jobs, position and resize transparent model layers. Select a layer and **Clean edges** to inspect it on checker, light, or dark; brush away unwanted pixels, undo a stroke, or reset cleanup. Use canvas zoom to examine details at 100% or 200%. Save projects automatically or with **Save project**, then export a full-size PNG. Saved projects store the source job ID, canvas settings, text, positions, and cleanup strokes under `jobs/projects/`; reopening them does not run either model. Keep the original job assets in `jobs/` so its projects can reopen. Exported PNGs are flattened; edit text and layers by reopening the project in the Lab. Layer pixels are still limited by the model's 1024 px output, and enlarging them can expose soft edges.

When the source image is larger than the Layer model output, the result also offers a **source-size masked cutouts** ZIP. This applies the model's resized alpha masks to the original pixels, so a 2048 input produces 2048 transparent PNGs without another GPU run. It is not 2048 model inference: edges and overlapping content can need cleanup, and the background may still contain pixels hidden by foreground objects. The original 512 or 1024 model layers remain available separately. This export also works for completed jobs from before the feature was added.

Completed jobs persist under `jobs/` on Spark 2 and can be reopened or rerun after a server restart. For 1024 px Design and 512 px Layers, the tool keeps both checkpoints loaded when Spark 2 has enough available memory; switching between them then skips the load. It requires at least 55 GiB available before loading the second model and retains both only while at least 14 GiB is available before a job. A 2048 px Design or 1024 px Layers job discards the inactive model first. The cache unloads after 15 idle minutes; **Release GPU** unloads it sooner when no job is running or queued. See the [measured speed tests](performance.md).

## Verified run

On 2026-09-23, the integrated browser flow generated a 1024 px design from a new prompt, transferred its PNG with **Send to Layers**, and produced four 512 px RGBA layers. Both jobs reopened after a page reload. Design took 306.95 seconds including a 285-second checkpoint load; Layer took 323.05 seconds including a 250.41-second checkpoint switch/load. The layer ZIP passed its integrity check. Its recomposition had RGB mean absolute error 2.5956 / 255 against the resized generated design. That number measures pixel difference, not whether the layers are useful for editing. This verifies the combined workflow, not general design quality or the 2048 option.

On 2026-09-23, the official card input was submitted through the browser with six layer descriptions at 512 px. The web job produced six RGBA layers, a recomposition, a difference image, and a valid 12-file ZIP. The browser's solo-layer and split comparison controls worked, and the completed job reopened after a server restart. Total time was 386.85 seconds, including 285.63 seconds of first-load time and 100.69 seconds in generation. RGB mean absolute error against the resized input was 5.4104 / 255. This tests the web flow with an official example; it is not an independent quality assessment.

## Scope and access

The server has no accounts or authentication. Keep its host port bound to `127.0.0.1` and access it through the SSH tunnel. `model/`, `design-model/`, `jobs/`, and other local inputs and outputs are excluded from Git. Do not commit private designs or generated files to the repository.
