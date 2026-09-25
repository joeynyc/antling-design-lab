"""Download the pinned Design and Design-Layer checkpoints for GX10 setup."""

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    "design": ("inclusionAI/Ming-Image-0.1-Design", "16ed0bafe7491ee93c90da5825f54b52bbbc5617", "design-model"),
    "layers": ("inclusionAI/Ming-Image-0.1-Design-Layer", "650448783505b103af305ce347bf60d8889e655a", "model"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", choices=["both", *MODELS], default="both")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for name, (repo, revision, directory) in MODELS.items():
        if args.models not in ("both", name):
            continue
        path = snapshot_download(repo_id=repo, revision=revision, local_dir=root / directory, max_workers=args.max_workers)
        print(f"{name}: {path}", flush=True)


if __name__ == "__main__":
    main()
