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

The inference stack still requires Transformers 4.57.6. Its dependency scan reports advisories involving untrusted checkpoints, other model architectures, training-state loading, and tokenizer serialization. This app loads pinned local checkpoints through the upstream Ming class, uses a newer NVIDIA PyTorch build, and does not expose those training/conversion/serialization operations. These restrictions reduce exposure; they do not remove the package advisories.

Transformers 5.17.0 was tested in an isolated container and failed the upstream model import (`is_torch_fx_available` was removed). Resolving this dependency exception requires a tested upstream migration. **Keep public release on hold until this exception has been reviewed or resolved.** Do not suppress the findings or describe the inference stack as having a clean vulnerability scan.

See [Transformers security guidance](https://github.com/huggingface/transformers/security) for the upstream trust model. Recheck dependencies before release and after changing models, providers, or the NVIDIA base image.

## Reporting

Do not post credentials or private prompts in public issues. Use this repository's GitHub private vulnerability reporting channel when available; otherwise contact the maintainer privately before sharing exploit details.
