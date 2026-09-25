# Security

AntLing Design Lab is a single-user application. Keep its port bound to loopback and use an SSH tunnel for remote access. It has no authentication or tenant isolation; do not expose it publicly or run it on a shared, untrusted host.

## Boundaries

- The server checks Host and Origin, limits request sizes before parsing uploads, restricts image decoders, and prevents framing by other sites.
- Provider keys come from the Spark's environment. They are not sent to the browser. Provider redirects are rejected, responses are bounded, and errors omit provider response bodies.
- Only the configured provider receives a prompt when expansion is selected. Direct prompts stay on the Spark; the optional Codex helper uses its configured Codex service.
- Runtime code and model checkpoints are mounted read-only. Hugging Face downloads are disabled at runtime. The downloader pins checkpoint revisions; setup pins the upstream code revision. Do not substitute untrusted models or Python code.
- Generated work stays in `jobs/`. Keep this directory, `.env`, local credentials, and their backups private. The Docker build context excludes them.

## Dependency audit — 2026-09-25

`pip-audit -r requirements-web.txt` found no known vulnerabilities in the resolved web dependencies. CI repeats this scan and runs the application tests. It does not scan the entire NVIDIA container or establish that the app is vulnerability-free.

The inference stack still requires Transformers 4.57.6, which has known advisories. Before opening this source preview, we checked the app's loading path against the reported cases. The web API accepts images and prompts, not model files or configuration. Setup downloads two fixed checkpoint revisions; runtime mounts them read-only and sets Hugging Face offline mode. The pinned checkpoints' configuration files contain neither `auto_map` nor `_attn_implementation_internal`. The app does not invoke the reported X-CLIP conversion, LightGlue loading, Trainer state restoration, or tokenizer serialization paths. This limits the attack preconditions described in the [configuration-loading advisory](https://github.com/advisories/GHSA-29pf-2h5f-8g72) and [Trainer advisory](https://github.com/advisories/GHSA-69w3-r845-3855); the package findings remain open.

Transformers 5.17.0 was tested in an isolated container and failed the upstream model import (`is_torch_fx_available` was removed). A validated upstream migration is needed to remove this dependency exception. **This repository is a source preview for trusted, single-user local installations, not a production or public-facing service.** Do not substitute untrusted checkpoints, expose the server beyond loopback, suppress the findings, or describe the inference stack as having a clean vulnerability scan.

See [Transformers security guidance](https://github.com/huggingface/transformers/security) for the upstream trust model. Recheck dependencies before release and after changing models, providers, or the NVIDIA base image.

## Reporting

Do not post credentials or private prompts in public issues. Use this repository's GitHub private vulnerability reporting channel when available; otherwise contact the maintainer privately before sharing exploit details.
