# Installation

Run the backend on an NVIDIA DGX Spark / GX10 with GPU-enabled Docker. The tested device has 128 GB unified memory. Install Git and Python 3 with `venv`; model downloads and the NVIDIA container require internet access during setup.

## 1. Install on the Spark

Run these commands in a terminal **on the Spark**:

```bash
git clone https://github.com/joeynyc/antling-design-lab.git
cd antling-design-lab
git clone https://github.com/inclusionAI/Ming-Image.git upstream
git -C upstream checkout 62c6072e1ff15af83f7c4963a0a1954c1424e80e
python3 -m venv .venv
.venv/bin/pip install 'huggingface-hub==0.36.2'
.venv/bin/python scripts/download_models.py
docker build -t ming-image-layer:gx10 -f Dockerfile.gx10 .
bash scripts/run_web_gx10.sh
```

The downloader pins the tested revisions and saves both checkpoints in `model/` and `design-model/`. Downloads can be resumed by running it again. Check free disk space before starting: both checkpoints and the NVIDIA image are large.

Leave the server terminal open while using the Lab. To stop it, press Ctrl+C or run `docker stop ming-layer-web` in another Spark terminal. Start it again with `bash scripts/run_web_gx10.sh`; saved work remains in `jobs/`.

## 2. Open the browser

**Browser on the Spark:** open <http://127.0.0.1:8765/> directly. No tunnel is needed.

**Browser on another computer:** open a terminal on that computer and run:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_USER@YOUR_SPARK_IP
```

Replace `YOUR_USER@YOUR_SPARK_IP` with the SSH username and address you normally use to connect to your Spark. An existing SSH host alias also works. Leave this terminal open, then visit <http://127.0.0.1:8765/> in your computer's browser. The tunnel carries browser traffic to the app without exposing its port to your network.

## 3. Optional prompt expansion

Direct prompting works immediately. Follow [provider setup](providers.md) to add an API or local text model. The two image models always run on the Spark.

## Local access and storage

The Lab has no user accounts. Keep the Docker port mapping bound to `127.0.0.1`; do not expose it to the internet or use it as a shared service. Host and origin checks reject unrelated websites, but they are not authentication against other users or processes on your computer.

`jobs/` contains prompts, images, and saved projects. `.env` contains any provider keys. Both are ignored by Git. Keep their backups private. The Docker build sends only the Dockerfile and its dependency list as build context.

## Troubleshooting

- **Page unavailable:** check that the Spark container and, if needed, the SSH tunnel are running.
- **Port already in use:** stop the previous tunnel or container using port 8765 before starting another.
- **GPU unavailable:** confirm the NVIDIA Container Toolkit works with Docker on the Spark.
- **Low memory:** stop other GPU workloads or use smaller output sizes. The Lab processes one image job at a time.
- **Provider missing:** set both its model and key in the Spark's `.env`, then restart the container. Custom endpoints can run without a key.
