# Ming Image Design Layer Workspace

A local interface for exploring [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer). The upstream model takes a flattened design and a layer plan, then produces separate transparent raster layers. See the [official inference repository](https://github.com/inclusionAI/Ming-Image) for model details.

## Project status

The [official six-layer sample](docs/gx10-smoke.md) completed on a DGX Spark GX10. The [local web tool](docs/web-tool.md) lets you upload a flattened design, describe the desired layers, run the model on Spark 2, compare the recomposed image, and download transparent PNGs. The model and generated jobs stay on the device and are ignored by Git.

An independent design test is still needed to judge how well the model handles real editing work.

The separate Design text-to-image checkpoint has been [tested alongside the Layer model on Spark 2](docs/gx10-coexist.md). It is not yet part of the web interface.

Generated layers are raster images. Text within them remains pixels rather than editable font text.

This project is independent of the upstream model and its maintainers.
