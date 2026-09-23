# Ming Image Design Layer Workspace

A local interface for exploring [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer). The upstream model takes a flattened design and a layer plan, then produces separate transparent raster layers. See the [official inference repository](https://github.com/inclusionAI/Ming-Image) for model details.

## Project status

The [official six-layer sample](docs/gx10-smoke.md) completed on a DGX Spark GX10. This repository contains an experimental runtime and scripts for downloading, running, and checking that sample. It does not yet contain a web interface. The next milestone is an independent design test before shaping the interface around the results.

Generated layers are raster images. Text within them remains pixels rather than editable font text.

This project is independent of the upstream model and its maintainers.
