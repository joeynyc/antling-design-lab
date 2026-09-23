# Two Ming models on one Spark 2

On 2026-09-23, a DGX Spark GX10 ran Ming-Image-0.1-Design and Ming-Image-0.1-Design-Layer at the same time. This was a direct load and overlapping inference test, not an estimate from checkpoint size.

## Test setup

- Spark 2 reported 121 GiB usable unified memory and no swap. Spark 1 was not used.
- Layer checkpoint: `inclusionAI/Ming-Image-0.1-Design-Layer` at `650448783505b103af305ce347bf60d8889e655a`, already running in the local web service.
- Design checkpoint: `inclusionAI/Ming-Image-0.1-Design` at `16ed0bafe7491ee93c90da5825f54b52bbbc5617`, downloaded to `design-model/` on Spark 2.
- Both processes used the GX10 Docker runtime, one GB10 GPU, BF16, eager attention, and the official inference helpers from upstream commit `62c6072e1ff15af83f7c4963a0a1954c1424e80e`.
- Design generated one 1024×1024 image at 12 steps, CFG 1.0. Layers decomposed a 1024×1024 input into two 512×512 RGBA layers at 12 steps, CFG 2.0. The generation phases overlapped.

## Observed result

- Both checkpoints loaded at once. Before inference, `nvidia-smi` reported about 48.4 GiB allocated to the Layer process and 48.3 GiB to Design; `MemAvailable` was about 17 GiB.
- Both generations completed without an out-of-memory error. The Design image contains the requested geometric layout and exact “MING TEST” text. The Layer web job returned two RGBA layers and a completed result bundle; the web service remained healthy.
- The Design checkpoint took 308.81 seconds to load and 51.26 seconds to generate. The overlapping Layer generation took 78.05 seconds; a nearby Layers-only two-layer 512 px run took 45.90 seconds. These are single-run observations, not stable benchmarks.
- At the tightest observed point, `MemAvailable` was **6.18 GiB** and combined reported GPU allocation was **104.5 GiB**. This is a narrow margin.

## Implication

Spark 2 can run both models simultaneously at the **tested 1024 Design / 512 Layers settings**. This does not establish that 2048 Design or 1024 Layers generation is safe concurrently. For the web product, keep one job queue and offer sequential generation as the reliable path; treat concurrent runs as an optional, resolution-limited mode until larger settings are measured. The Design checkpoint is stored locally but is not yet connected to the web UI. The temporary test jobs were removed afterward, and the existing Layer web service was restored.
