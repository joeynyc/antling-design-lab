# GX10 inference smoke test

A DGX Spark GX10 completed the upstream six-layer card sample at 1024×1024. This confirms that the local runtime can load the published checkpoint and save layer PNGs. It is one official example, not an independent quality benchmark.

## Reproduce

The official source checkout was pinned to `62c6072e1ff15af83f7c4963a0a1954c1424e80e`; the Layer checkpoint was pinned to `650448783505b103af305ce347bf60d8889e655a`.

```bash
git clone https://github.com/inclusionAI/Ming-Image.git upstream
git -C upstream checkout 62c6072e1ff15af83f7c4963a0a1954c1424e80e
docker build -f Dockerfile.gx10 -t ming-image-layer:gx10 .
python3 scripts/download_layer_model.py \
  --revision 650448783505b103af305ce347bf60d8889e655a \
  --local-dir model
bash scripts/run_official_sample_gx10.sh 1024
```

The script uses the official `card_making_input.png` and six-layer prompt. Settings: BF16, eager attention, 12 steps, CFG 2.0, seed 42. The Dockerfile uses NVIDIA's PyTorch 26.08 container with an adapted dependency set for GB10. It removes the base image's `torchao` package because that version fails when `diffusers==0.36.0` imports its autoencoder. This is an environment adaptation; the upstream repository pins a different validated stack.

## Observed result

- Six 1024×1024 RGBA PNGs were saved, matching the requested count.
- Alpha channels contain transparency; the final red-background layer is nearly opaque.
- Recomposition from back to front yielded RGB mean absolute error **3.3976 / 255** against the official input. This is our comparison metric, not the publisher's benchmark.
- Process start to saved output: **946.82 seconds** (15 minutes 47 seconds). The 12 sampling steps took **11 minutes 25 seconds** within that total. This single run is not a stable performance estimate.
- The GPU returned to idle after export. There was no out-of-memory error.

Visual inspection found the requested roles in separate layers: text, top illustration, bottom art, ribbon, card, and red background. Raster text is still pixels. No editing or independent design test has been completed.

The adapted runtime emitted `vision.*._extra_state` initialization warnings while loading. The output appeared coherent in this sample, but the warning and the use of newer PyTorch/Transformer Engine remain compatibility caveats for further tests.

## Next check

Run a self-created flattened design with a known layer source, then assess text fidelity, alpha edges, occlusion, and actual edit time. Compare 512 and 1024 only after choosing a representative input; report process startup separately from repeated inference.
