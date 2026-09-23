# Ming Image Design Layer Workspace

A local interface for exploring [Ming-Image-0.1-Design-Layer](https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer). The upstream model takes a flattened design and a layer plan, then produces separate transparent raster layers. See the [official inference repository](https://github.com/inclusionAI/Ming-Image) for model setup and requirements.

## Project status

Early planning. This repository does not yet contain a working model integration or web interface. The first milestone is to validate inference on the target hardware and inspect the resulting layers. If those results are useful, the interface will support image upload, a numbered layer plan, layer previews, visual comparison, and PNG export.

Generated layers are raster images. Text within them remains pixels rather than editable font text.

This project is independent of the upstream model and its maintainers.
