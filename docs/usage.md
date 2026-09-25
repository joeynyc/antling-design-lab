# User guide

## Generate

Describe the image in plain language. Quote words that must appear exactly. Leave **Prompt expansion** on direct mode, or select a [configured provider](providers.md) to build a structured layout first. Choose 2048 for detail or 1024 for speed.

After generation, download the PNG, choose **Send to Layers**, or open **Finish this design**. The job keeps your original request; expanded jobs also offer the structured prompt in their manifest. Timings distinguish prompt expansion, queue wait, model load, and generation.

## Separate

Upload a PNG, JPEG, or WebP, or transfer a generated design. Inputs are limited to 20 MB and 16 megapixels. Describe 2–8 layers in front-to-back order, with the background last.

Choose a 512 or 1024 px working size. **1024 is the model's maximum layer output size.** A larger input is resized for inference. You can toggle or solo layers, compare the recomposed result to the input, and download individual PNGs or a ZIP.

The Difference tab amplifies pixel differences by 8×. Its error value is a diagnostic measure, not a score of editing quality. Check edges, lettering, and overlapping objects before reuse.

For larger source images, **source-size cutouts** apply resized model alpha masks to the original pixels. They preserve original image detail but do not reconstruct hidden content or create higher-resolution model layers.

## Finish

Open **Finish this design** or **Finish with layers**. Choose X landscape (1600 × 900) or square (1080 × 1080), position the image, and add editable text. For split jobs, move and resize individual layers. **Clean edges** lets you erase unwanted pixels, undo strokes, and inspect on light, dark, or checker backgrounds.

Save the project and export a PNG. The exported image is flattened; reopen the project in the Lab to edit it. Keep its original job assets in `jobs/` so it can reopen. Enlarging a model layer can reveal soft edges.

## Model memory

One GPU job runs at a time; up to three jobs can wait. At smaller sizes, both checkpoints can stay loaded when enough memory is available. Larger jobs unload the inactive model first. The cache unloads after 15 idle minutes; **Release GPU** unloads it sooner when the queue is empty. See [performance](performance.md) for measured timings.
