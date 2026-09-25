# AntLing Design Lab

Generate a square design with [Ming-Image-0.1-Design](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design), split an image into transparent raster layers with [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer), and finish a social graphic with editable text. Both image checkpoints run locally on one NVIDIA DGX Spark (GX10). The app is independent of inclusionAI and its maintainers.

Prompt expansion is **optional**. A plain prompt goes straight to the local Design model with no text-model account. If you choose an expansion provider, the Lab turns your request into Ming's structured layout format before image generation. Configure any one of OpenAI, Claude, Z.ai, DeepSeek, or an OpenAI-compatible endpoint such as a local text-model server. Codex CLI on a Mac is an optional extra, not an install requirement. Only the selected provider receives the prompt.

## Run on a DGX Spark

Prerequisites: a GX10 with NVIDIA Docker GPU support, Git, Python 3 with `venv`, enough disk space for both checkpoints and the Docker image, and access to Hugging Face and NVIDIA's NGC container registry for setup. Inference runs offline after the image and checkpoints are installed.

```bash
git clone https://github.com/joeynyc/ming-image-design-layer.git
cd ming-image-design-layer
git clone https://github.com/inclusionAI/Ming-Image.git upstream
git -C upstream checkout 62c6072e1ff15af83f7c4963a0a1954c1424e80e
python3 -m venv .venv
.venv/bin/pip install 'huggingface-hub==0.34.0'
.venv/bin/python scripts/download_models.py
docker build -t ming-image-layer:gx10 -f Dockerfile.gx10 .
bash scripts/run_web_gx10.sh
```

The download script pins the tested Design and Design-Layer revisions and writes them to ignored `design-model/` and `model/` directories. `upstream/`, `jobs/`, and `.env` are also excluded from Git and the Docker build context. The server binds to the Spark's `127.0.0.1:8765` and has no login. Keep it local; do not forward it to a public network interface.

On your computer, connect to the Spark with an SSH tunnel and open <http://127.0.0.1:8765/>:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_SPARK_SSH_HOST
```

On macOS, `bash scripts/install_web_tunnel_macos.sh YOUR_SPARK_SSH_HOST` installs a reconnecting tunnel instead. Stop the server with `docker stop ming-layer-web` on the Spark. See [web workflow and limits](docs/web-tool.md), [GX10 smoke test](docs/gx10-smoke.md), and [performance notes](docs/performance.md).

## Choose a prompt model

Direct mode works immediately. To offer other choices, copy `.env.example` to `.env` **on the Spark**, enter a model name and API key for each provider you want, run `chmod 600 .env`, and restart the container. The dropdown lists only providers with the required settings. Model names are operator-configured because provider catalogs change. API keys are read by the Spark process; the browser receives only display names and model names.

| Choice | Settings | API shape |
| --- | --- | --- |
| [OpenAI](https://platform.openai.com/docs/quickstart/make-your-first-api-request) | `ANTLING_OPENAI_API_KEY`, `ANTLING_OPENAI_MODEL` | Responses API |
| [Claude](https://platform.claude.com/docs/en/api/messages/create) | `ANTLING_ANTHROPIC_API_KEY`, `ANTLING_ANTHROPIC_MODEL` | Anthropic Messages API |
| [Z.ai](https://docs.z.ai/guides/capabilities/mcp-call) | `ANTLING_ZAI_API_KEY`, `ANTLING_ZAI_MODEL` | Chat Completions |
| [DeepSeek](https://api-docs.deepseek.com/api/create-chat-completion/) | `ANTLING_DEEPSEEK_API_KEY`, `ANTLING_DEEPSEEK_MODEL` | Chat Completions |
| Custom / local | `ANTLING_COMPAT_BASE_URL`, `ANTLING_COMPAT_MODEL`, optional `ANTLING_COMPAT_API_KEY` | OpenAI-compatible `/chat/completions` |

For a text-model server on the Spark host, a common custom base URL is `http://host.docker.internal:PORT/v1`. The app accepts HTTP for custom endpoints only when no API key is set; with a key, use HTTPS. Provider selection happens per generation. The full structured prompt is validated before sending it to Ming, and the original request stays with the job. If expansion fails, no image job starts; choose another provider or direct mode.

If you already use Codex CLI on the computer opening the browser, the [optional Mac bridge](docs/web-tool.md#optional-codex-cli-helper) adds it to the same dropdown. Its signed-in account is separate from an OpenAI API key.

## Output and limits

Design supports 1024 or 2048 px square output. Layers supports 512 or 1024 px working size and remains raster: lettering within a layer is not editable font text. For a larger input, the Lab can export source-size cutouts by applying the model's resized alpha masks to original pixels; this does not increase model resolution. The Finish editor can place editable text and export X landscape or square PNGs. Generated jobs and saved projects live in ignored `jobs/` on the Spark; back it up separately if you need them.

One GPU worker queues inference jobs. Warm models can stay cached for the measured smaller-resolution workflow; a larger run unloads the inactive checkpoint first. Initial model loads and high-resolution generations can take several minutes on GX10. See [measured runs](docs/performance.md) for the tested cases rather than treating them as speed guarantees.

## Development and licensing

Run `python -m unittest discover -s tests` with FastAPI, httpx, Pillow, requests, and python-multipart installed. The app code is MIT licensed under [LICENSE](LICENSE). The upstream code and model checkpoints have their own licenses and are downloaded separately; review their model cards and repository before redistribution. The [local AI website demo](demos/local-ai-website/README.md) and [agent skill notes](docs/agent-skills.md) are optional examples.
