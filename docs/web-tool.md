# Ming Design Lab

The web interface runs on Spark 2 (GX10) with pinned Ming Image Design and Design-Layer checkpoints. It is a single-user, local tool. The Spark binds port 8765 to its own loopback address; an SSH tunnel makes it available on your Mac.

## Start

On Spark 2, from this project's directory:

```bash
docker build -t ming-image-layer:gx10 -f Dockerfile.gx10 .
bash scripts/run_web_gx10.sh
```

In a separate terminal on the Mac:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 gx10
```

Open <http://127.0.0.1:8765/>. Leave the tunnel running while using the tool. Stop the web container with `docker stop ming-layer-web` on Spark 2. The container expects `upstream/`, `model/`, and `design-model/` in the project directory; see [the GX10 setup](gx10-smoke.md) and [checkpoint coexistence notes](gx10-coexist.md) for pinned revisions.

## Use

In **Generate design**, enter a plain prompt. **Expand with Codex** is on by default: the Mac helper calls the signed-in Codex CLI with the [official Ming text-to-image rewriter instructions](../resources/t2i_rewriter_system_prompt.txt), validates the structured JSON, and then sends that JSON to Ming. The original prompt remains visible in job history; the full structured prompt is saved in the job manifest. The helper uses the signed-in Codex account and does not store an API key. Select 2048 for the model-card quality setting (about 2 minutes of warm generation in the local test); 1024 is faster. The model may still invent or distort small text, so inspect each result. Download the PNG or choose **Send to Layers** to transfer it directly into the split workspace.

On the Mac that opens the Lab, install the helper once with `bash scripts/install_prompt_bridge_macos.sh`. It runs on `127.0.0.1:8766` as a LaunchAgent and accepts browser requests from the Lab at `http://127.0.0.1:8765`. If the helper is unavailable, uncheck **Expand with Codex** to send the prompt directly to Ming. This helper does not run on Spark 2; the image and layer models continue to run there.

In **Split layers**, upload a PNG, JPEG, or WebP design (20 MB and 16 megapixels maximum), or use the transferred design. Write 2–8 layer descriptions in **front-to-back** order, with the background last. Name text exactly where possible. Choose 512 or 1024 working size and a seed, then generate. Only one inference job runs at once; up to three can wait in the queue. A cold checkpoint load still takes several minutes. The published Layer sample at 1024 took about 16 minutes end to end on GX10; other images may differ.

After generation, inspect the recomposed image, toggle or solo layers, compare input and output with the split view, inspect the amplified difference, and download individual RGBA PNGs or a ZIP bundle. The RGB error is a pixel difference against the input, not an editing-quality score. Text remains raster pixels.

Completed jobs persist under `jobs/` on Spark 2 and can be reopened or rerun after a server restart. For 1024 px Design and 512 px Layers, the tool keeps both checkpoints loaded when Spark 2 has enough available memory; switching between them then skips the load. It requires at least 55 GiB available before loading the second model and retains both only while at least 14 GiB is available before a job. A 2048 px Design or 1024 px Layers job discards the inactive model first. The cache unloads after 15 idle minutes; **Release GPU** unloads it sooner when no job is running or queued. See the [measured speed tests](performance.md).

## Verified run

On 2026-09-23, the integrated browser flow generated a 1024 px design from a new prompt, transferred its PNG with **Send to Layers**, and produced four 512 px RGBA layers. Both jobs reopened after a page reload. Design took 306.95 seconds including a 285-second checkpoint load; Layer took 323.05 seconds including a 250.41-second checkpoint switch/load. The layer ZIP passed its integrity check. Its recomposition had RGB mean absolute error 2.5956 / 255 against the resized generated design. That number measures pixel difference, not whether the layers are useful for editing. This verifies the combined workflow, not general design quality or the 2048 option.

On 2026-09-23, the official card input was submitted through the browser with six layer descriptions at 512 px. The web job produced six RGBA layers, a recomposition, a difference image, and a valid 12-file ZIP. The browser's solo-layer and split comparison controls worked, and the completed job reopened after a server restart. Total time was 386.85 seconds, including 285.63 seconds of first-load time and 100.69 seconds in generation. RGB mean absolute error against the resized input was 5.4104 / 255. This tests the web flow with an official example; it is not an independent quality assessment.

## Scope and access

The server has no accounts or authentication. Keep its host port bound to `127.0.0.1` and access it through the SSH tunnel. `model/`, `design-model/`, `jobs/`, and other local inputs and outputs are excluded from Git. Do not commit private designs or generated files to the repository.
