# Performance on GX10

These are individual runs on one 128 GB GX10 using the original validated inference stack on 2026-09-23. They are observations, not speed guarantees; updated dependencies and different images can change timings.

| Run | Generation time | Notes |
| --- | ---: | --- |
| Design, 1024 px, 12 steps | 21.83 s | Warm model |
| Design, 2048 px, 12 steps | 130.68 s | Warm model, structured prompt |
| Layers, 512 px, four layers, 12 steps | 71.46 s | Warm model |
| Layers, 1024 px, six-layer official sample | 11m 25s | 15m 47s including startup |

Cold checkpoint loads typically took 4–6 minutes. The clearest improvement was keeping both models loaded for repeat 1024 px Design / 512 px Layers jobs: a repeat pair took about 92 seconds versus 630 seconds with cold loads. This speeds up switching; it does not reduce sampling time.

The app runs inference sequentially. It loads a second checkpoint only with at least 55 GiB available and drops the inactive checkpoint below 14 GiB before a job. Design at 2048 px or Layers at 1024 px also unloads the inactive checkpoint. The cache releases after 15 idle minutes.

Other tested options did not become defaults: parallel shard loading did not reliably reduce load time; FlashAttention 2 produced mixed small timing changes; eight sampling steps were faster but introduced visible artifacts. The default remains 12 steps with eager attention.
