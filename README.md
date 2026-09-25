# AntLing Design Lab

A local interface for [Ming-Image-0.1-Design](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design) and [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer). Expand a plain prompt into Ming's structured design format with the Codex CLI on your Mac, generate a design, then send it directly into layer splitting. The Layer model also accepts an uploaded image and produces separate transparent raster layers. See the [official inference repository](https://github.com/inclusionAI/Ming-Image) for model details.

The official [Ling UI Design and Image-to-Editable-PPT agent skills](docs/agent-skills.md) can use these local models through the same Spark 2 web service.

## Working website demo

The [local AI website demo](demos/local-ai-website/README.md) turns a 2048px Design image into a responsive page with live text and a viewer for cropped Design-Layer output. It runs as a separate static site on the Mac while both image models run on Spark 2.

## Project status

The [official six-layer sample](docs/gx10-smoke.md) completed on a DGX Spark GX10. The [local web tool](docs/web-tool.md) runs both checkpoints on Spark 2 in one workflow. The model weights and generated jobs stay on the device and are ignored by Git.

A structured 2048 px landing-page test made the main headline and button much clearer than a one-sentence 1024 px run, though Ming still invented some small labels. More design-quality testing is needed.

The web worker queues one GPU job at a time and [caches both checkpoints for the tested 1024 px Design and 512 px Layers workflow](docs/performance.md). Larger resolutions or low available memory cause it to discard the inactive checkpoint before generating.

Generated layers are raster images. Text within them remains pixels rather than editable font text.

For inputs larger than the Layer model's 1024 px maximum, the Lab can also export source-size cutouts by applying the model's alpha masks to the original image. These retain original pixels but are not newly generated high-resolution layers; inspect edges and overlapping content before reuse.

This project is independent of the upstream model and its maintainers.
