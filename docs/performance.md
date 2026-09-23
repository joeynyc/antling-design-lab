# Spark 2 speed tests

On 2026-09-23, we tested the pinned Ming Design and Design-Layer checkpoints on Spark 2 (GX10), using the same Design 1024 px prompt and seed and the same four-layer 512 px decomposition. The normal interface still uses 12 sampling steps. These are single-run measurements, so differences of a few seconds do not establish a speed gain.

| Variant | Design generation | Layer generation | Finding |
| --- | ---: | ---: | --- |
| 12 steps, eager attention | 21.83 s | 71.46 s | Original integrated workflow; 630.00 s including both cold loads |
| Parallel shard loading, four workers | 22.86 s | 73.56 s | Combined cold Design + Layer run took 640.09 s versus the earlier 630.00 s; no reliable load improvement |
| 8 steps | 13.67 s | 50.36 s | Faster, but visible artifacts and worse layer recomposition; not the default |
| FlashAttention 2 | 20.50 s | 75.82 s | Byte-identical output, mixed small generation-time changes; no reliable gain |

The best measured improvement is **keeping both checkpoints resident** for Design 1024 px and Layers 512 px. With the guarded cache enabled, the first Design and Layer jobs still loaded in 352.86 and 266.97 seconds. On the return Design → Layers sequence, each load took **0.0 seconds**; the two jobs took **20.50 + 71.42 = 91.92 seconds** end to end. The earlier cold-switch pair took 630.00 seconds. This is about **6.85× faster for a repeat pair after both models are loaded**; it does not accelerate a cold start or the sampling itself.

The cache run produced byte-identical Design, layer, and recomposed PNGs on repetition. Both layer ZIPs passed integrity checks, and recomposition RGB mean absolute error stayed at 2.5956 / 255. Available system memory was sampled every two seconds; its low point during dual-model generation was **11.95 GiB**. The app runs one GPU job at a time, only tries to load the second checkpoint when at least 55 GiB is available, and drops the inactive model below 14 GiB before a job. It also drops the inactive checkpoint for Design 2048 px or Layers 1024 px. These larger combinations have not been benchmarked with the dual cache and are intentionally run with one resident checkpoint.

The default on Spark 2 is 12 steps, eager attention, sequential inference, parallel shard loading off, and guarded dual caching on. Cached models unload after 15 idle minutes or when **Release GPU** is clicked. All measurements came from individual runs on this machine; cold-load time varied substantially across runs.

A separate structured-prompt Design test at 2048 px and 12 steps took 130.68 seconds with the model already loaded. It produced clearer main copy than the earlier one-sentence 1024 px example, but still invented small labels; this is a visual observation from one prompt, not a controlled quality benchmark.
