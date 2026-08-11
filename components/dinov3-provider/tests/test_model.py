from __future__ import annotations

import hashlib
from pathlib import Path

from automation_toolbox_dinov3_provider.model import ModelFile, ensure_model_files


def test_model_files_are_verified_and_reused(tmp_path: Path) -> None:
    payload = b"local model bytes"
    expected = ModelFile("weights.bin", hashlib.sha256(payload).hexdigest(), len(payload))
    downloads: list[str] = []

    def downloader(model_file: ModelFile, target: Path, checkpoint) -> None:  # type: ignore[no-untyped-def]
        downloads.append(model_file.name)
        target.write_bytes(payload)

    model_dir = tmp_path / "models"
    assert ensure_model_files(model_dir, [expected], downloader=downloader) == model_dir
    assert downloads == ["weights.bin"]

    ensure_model_files(model_dir, [expected], downloader=downloader)
    assert downloads == ["weights.bin"]

    (model_dir / "weights.bin").write_bytes(b"corrupt")
    ensure_model_files(model_dir, [expected], downloader=downloader)
    assert downloads == ["weights.bin", "weights.bin"]

