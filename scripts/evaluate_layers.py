"""Recompose Ming RGBA layers and compare them with the flattened input."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-image", type=Path, required=True)
    parser.add_argument("--layer-dir", type=Path, required=True)
    parser.add_argument("--expected-layers", type=int, required=True)
    args = parser.parse_args()

    layer_paths = sorted(args.layer_dir.glob("layer_*.png"))
    if len(layer_paths) != args.expected_layers:
        raise ValueError(
            f"Expected {args.expected_layers} layers, found {len(layer_paths)}"
        )

    layers = [Image.open(path).convert("RGBA") for path in layer_paths]
    size = layers[0].size
    if any(layer.size != size for layer in layers):
        raise ValueError("Output layers have different dimensions")

    # The model numbers layers front to back; alpha-over composites back to front.
    composite = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in reversed(layers):
        composite = Image.alpha_composite(composite, layer)

    reference = Image.open(args.input_image).convert("RGB")
    if reference.size != size:
        reference = reference.resize(size, Image.Resampling.LANCZOS)
    recomposed = composite.convert("RGB")
    difference = ImageChops.difference(reference, recomposed)
    mae_rgb = ImageStat.Stat(difference).mean

    recomposed.save(args.layer_dir / "recomposed.png")
    difference.save(args.layer_dir / "difference.png")
    metrics = {
        "input_size": list(Image.open(args.input_image).size),
        "output_size": list(size),
        "layer_count": len(layers),
        "rgb_mae_0_to_255": round(sum(mae_rgb) / 3, 4),
        "comparison": "Input resized with Lanczos to output dimensions if needed; RGB mean absolute error",
    }
    (args.layer_dir / "comparison.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
