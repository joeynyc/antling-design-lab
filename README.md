# Ming Image Design Layer Workspace

A local interface for [Ming-Image-0.1-Design](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design) and [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer). Generate a design from a prompt, then send it directly into layer splitting. The Layer model also accepts an uploaded image and produces separate transparent raster layers. See the [official inference repository](https://github.com/inclusionAI/Ming-Image) for model details.

## Project status

The [official six-layer sample](docs/gx10-smoke.md) completed on a DGX Spark GX10. The [local web tool](docs/web-tool.md) runs both checkpoints on Spark 2 in one workflow. The model weights and generated jobs stay on the device and are ignored by Git.

An independent design test is still needed to judge how well the model handles real editing work.

The web worker queues one GPU job at a time and [caches both checkpoints for the tested 1024 px Design and 512 px Layers workflow](docs/performance.md). Larger resolutions or low available memory cause it to discard the inactive checkpoint before generating.

Generated layers are raster images. Text within them remains pixels rather than editable font text.

This project is independent of the upstream model and its maintainers.
