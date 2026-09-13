from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("huggingface_hub is required: pip install huggingface_hub", file=sys.stderr)
        return 2

    repo_root = Path(os.environ.get("PIXELPILOT_ROOT", Path(__file__).resolve().parents[1]))
    comfy_dir = Path(os.environ.get("COMFY_DIR", "/workspace/ComfyUI"))
    manifest_path = Path(os.environ.get("MODEL_MANIFEST", repo_root / "resources/model_manifest.json"))
    hf_token = os.environ.get("HF_TOKEN") or None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    if not files:
        raise RuntimeError("Model manifest is empty")

    for index, item in enumerate(files, start=1):
        repo_id = item["repo_id"]
        filename = item["filename"]
        target_subdir = item["target_subdir"]
        gated = bool(item.get("requires_hf_token"))
        min_bytes = int(item.get("min_bytes") or 1)
        if gated and not hf_token:
            raise RuntimeError(f"HF_TOKEN is required for gated file {repo_id}/{filename}")

        target_dir = comfy_dir / "models" / target_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / Path(filename).name
        if target_file.exists():
            current_size = target_file.stat().st_size
            if current_size >= min_bytes:
                print(f"[{index}/{len(files)}] exists: {target_file} ({current_size} bytes)")
                continue
            print(
                f"[{index}/{len(files)}] incomplete file detected: {target_file} "
                f"({current_size} < {min_bytes}); re-downloading"
            )
            target_file.unlink()

        print(f"[{index}/{len(files)}] downloading {repo_id}/{filename} -> {target_dir}")
        downloaded = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                token=hf_token,
                local_dir=target_dir,
            )
        )
        if downloaded.resolve() != target_file.resolve():
            # Compatibility fallback across huggingface_hub versions. Stream/copy on disk
            # instead of loading multi-gigabyte model files into RAM.
            shutil.copy2(downloaded, target_file)
        size = target_file.stat().st_size
        if size < min_bytes:
            raise RuntimeError(
                f"Downloaded file looks incomplete: {target_file} ({size} bytes; expected >= {min_bytes})"
            )
        print(f"[{index}/{len(files)}] ready: {target_file} ({size} bytes)")

    print("All model files are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
