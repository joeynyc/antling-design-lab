# Agent integrations

The optional [Ling UI Design and Image-to-Editable-PPT skills](https://github.com/inclusionAI/ling-cookbook/tree/main/resources/recommended-skills) can use the Lab's local image API. Install a skill according to its instructions and point its image base URL to `http://127.0.0.1:8765/v1`. These routes have no API-key authentication and are intended only for trusted local clients through the same SSH tunnel.

| Route | Input | Result |
| --- | --- | --- |
| `POST /v1/images/generations` | JSON prompt for `ming-image-0.1-design` | Base64 image and job ID |
| `POST /v1/images/edits` | Multipart image and numbered layer plan for `ming-image-0.1-design-layer` | Ordered base64 RGBA layers and job ID |

Both use the app's GPU queue and save outputs in `jobs/`. Skills handle their own prompt planning; these routes do not invoke the web UI's prompt-expansion provider.

Design accepts `1024`, `1k`, `2048`, `2k`, or `auto` size. Layers accepts `auto` or `512` for 512 px and `1k` or `1024` for 1024 px. Both use 12 sampling steps. A layer plan can use consecutive `Layer 1: ...` lines or the compact form `2 layers: 1 main subject, 2 background`. The background belongs last.

For the Ling UI helper, disable its external layer-prompt enhancer with `--no-pe`. The local adapter does not provide the external service's VLM enhancer, super-resolution, or asset detector. Inspect layer quality and raster lettering before using extracted assets.
