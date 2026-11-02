"""Resumable Hub snapshots and measured cache growth without weight prefetching."""
from __future__ import annotations

import fnmatch
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

ALLOW = ['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model', '*.tiktoken']
progress: dict[str, Any] = {'stage': 'starting', 'model': None}
_lock = threading.Lock()

def status() -> dict[str, Any]:
    with _lock: return dict(progress)

def phase(stage: str, model: str, **extra: Any) -> None:
    with _lock: progress.update(stage=stage, model=model, **extra)

def cached_bytes(directory: Path) -> int:
    return sum(p.stat().st_size for p in directory.glob('*') if p.is_file()) if directory.exists() else 0

def prepare_model(model_id: str) -> str:
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.constants import HF_HUB_CACHE
    phase('checking-cache', model_id, downloaded_bytes=None, total_bytes=None, mbps=None, percent=None, error=None)
    cache = Path(HF_HUB_CACHE)
    cache.mkdir(parents=True, exist_ok=True)
    blobs = cache / ('models--' + model_id.replace('/', '--')) / 'blobs'
    total = None
    try:
        info = HfApi().model_info(model_id, files_metadata=True)
        total = sum(f.size or 0 for f in info.siblings if any(fnmatch.fnmatch(f.rfilename, p) for p in ALLOW))
    except Exception:
        # Hub may be temporarily unavailable while a complete snapshot is cached.
        pass
    initial = cached_bytes(blobs)
    required = max(0, (total or 0) - initial) + 4 * 1024**3
    if shutil.disk_usage(cache).free < required:
        raise RuntimeError(f'Insufficient model-cache space: need approximately {required / 1024**3:.1f} GiB free')
    phase('downloading', model_id, total_bytes=total)
    stop = threading.Event()
    def measure():
        previous, started = initial, time.monotonic()
        while not stop.wait(2):
            current, now = cached_bytes(blobs), time.monotonic()
            phase('downloading', model_id, downloaded_bytes=current, total_bytes=total,
                  mbps=round(max(0, current-previous)*8/(now-started)/1e6, 2),
                  percent=round(min(100, current/total*100), 1) if total else None)
            previous, started = current, now
    observer = threading.Thread(target=measure, daemon=True)
    observer.start()
    try:
        local = snapshot_download(model_id, allow_patterns=ALLOW,
            max_workers=max(1, min(8, int(os.environ.get('HF_DOWNLOAD_WORKERS', '4')))))
    except Exception:
        phase('download-failed', model_id, error='Hub download failed; partial cache retained for retry')
        raise
    finally:
        stop.set(); observer.join(timeout=3)
    phase('loading-vram', model_id, downloaded_bytes=cached_bytes(blobs), total_bytes=total, percent=100 if total else None, mbps=None)
    return local
