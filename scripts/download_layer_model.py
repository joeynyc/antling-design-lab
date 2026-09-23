"""Download a pinned public Ming Design-Layer checkpoint for local inference."""

import argparse
from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True, help="Hugging Face commit SHA")
    parser.add_argument("--local-dir", required=True)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    path = snapshot_download(
        repo_id="inclusionAI/Ming-Image-0.1-Design-Layer",
        revision=args.revision,
        local_dir=args.local_dir,
        max_workers=args.max_workers,
    )
    print(path, flush=True)


if __name__ == "__main__":
    main()
