# Local web tool

The web interface runs on Spark 2 (GX10) with the pinned Ming Image Design-Layer checkpoint. It is a single-user, local tool. The Spark binds port 8765 to its own loopback address; an SSH tunnel makes it available on your Mac.

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

Open <http://127.0.0.1:8765/>. Leave the tunnel running while using the tool. Stop the web container with `docker stop ming-layer-web` on Spark 2. The container expects `upstream/` and `model/` in the project directory; see [the GX10 setup](gx10-smoke.md) for the pinned source and model revisions.

## Use

Upload a PNG, JPEG, or WebP design (20 MB and 16 megapixels maximum). Write 2–8 layer descriptions in **front-to-back** order, with the background last. Name text exactly where possible. Choose 512 or 1024 working size and a seed, then generate. Only one inference job runs at once; up to three can wait in the queue. The first job loads the checkpoint, which takes several minutes. The published sample at 1024 took about 16 minutes end to end on GX10; other images may differ.

After generation, inspect the recomposed image, toggle or solo layers, compare input and output with the split view, inspect the amplified difference, and download individual RGBA PNGs or a ZIP bundle. The RGB error is a pixel difference against the input, not an editing-quality score. Text remains raster pixels.

Completed jobs persist under `jobs/` on Spark 2 and can be reopened or rerun after a server restart. The model stays loaded between nearby jobs for speed and unloads after 15 idle minutes. **Release GPU** unloads it sooner when no job is running or queued.

## Verified run

On 2026-09-23, the official card input was submitted through the browser with six layer descriptions at 512 px. The web job produced six RGBA layers, a recomposition, a difference image, and a valid 12-file ZIP. The browser's solo-layer and split comparison controls worked, and the completed job reopened after a server restart. Total time was 386.85 seconds, including 285.63 seconds of first-load time and 100.69 seconds in generation. RGB mean absolute error against the resized input was 5.4104 / 255. This tests the web flow with an official example; it is not an independent quality assessment.

## Scope and access

The server has no accounts or authentication. Keep its host port bound to `127.0.0.1` and access it through the SSH tunnel. `model/`, `jobs/`, and other local inputs and outputs are excluded from Git. Do not commit private designs or generated files to the repository.
