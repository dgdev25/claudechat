from __future__ import annotations

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1 << 20
_MAX_BYTES = 600 * 1024 * 1024


class IntegrityError(RuntimeError):
    """A model file did not match its pinned digest."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    url: str
    sha256: str
    size_bytes: int


KOKORO_MODEL = ModelSpec(
    name="kokoro-v1.0.onnx",
    url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    sha256="7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    size_bytes=325532387,
)
KOKORO_VOICES = ModelSpec(
    name="voices-v1.0.bin",
    url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
    sha256="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    size_bytes=28214398,
)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _fetch(url: str, dest: Path, max_bytes: int) -> None:
    if not url.startswith("https://"):
        raise IntegrityError(f"refusing non-HTTPS model URL: {url}")
    written = 0
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        for block in iter(lambda: response.read(_CHUNK), b""):
            written += len(block)
            if written > max_bytes:
                raise IntegrityError("model download exceeded the size limit")
            out.write(block)


def ensure_model(spec: ModelSpec, models_dir: Path) -> Path:
    """Return a verified local path for spec, downloading it if needed."""
    models_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = models_dir / spec.name

    if final.exists():
        if spec.sha256 and _digest(final) != spec.sha256:
            raise IntegrityError(f"{spec.name} failed digest verification")
        return final

    tmp = final.with_suffix(final.suffix + ".partial")
    try:
        _fetch(spec.url, tmp, spec.size_bytes + _CHUNK)
        if spec.sha256 and _digest(tmp) != spec.sha256:
            raise IntegrityError(f"{spec.name} failed digest verification after download")
        os.replace(tmp, final)
        final.chmod(0o600)
    finally:
        tmp.unlink(missing_ok=True)
    return final
