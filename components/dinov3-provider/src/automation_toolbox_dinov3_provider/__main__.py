from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from automation_toolbox_dinov3_provider import __version__
from automation_toolbox_dinov3_provider.model import (
    MODEL_ID,
    MODEL_REVISION,
    ensure_model_files,
    model_dir,
)

PROTOCOL_VERSION = 1


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def ready_message() -> dict[str, Any]:
    return {
        "event": "ready",
        "protocol_version": PROTOCOL_VERSION,
        "provider_id": "dinov3-cpu",
        "provider_version": __version__,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_dir": str(model_dir()),
        "devices": ["cpu"],
    }


def embed(request: dict[str, Any]) -> None:
    if request.get("device", "cpu") != "cpu":
        raise ValueError("DINOv3 CPU Provider 仅支持 CPU")
    paths = [Path(str(item)) for item in request.get("paths", [])]
    batch_size = max(1, min(128, int(request.get("batch_size", 16))))
    model_path = ensure_model_files()

    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModel

    processor = AutoImageProcessor.from_pretrained(str(model_path), local_files_only=True)
    model = AutoModel.from_pretrained(str(model_path), local_files_only=True).to("cpu")
    model.eval()
    for offset in range(0, len(paths), batch_size):
        selected = paths[offset : offset + batch_size]
        loaded: list[Image.Image] = []
        loaded_paths: list[Path] = []
        rows: list[dict[str, Any]] = []
        for path in selected:
            try:
                with Image.open(path) as image:
                    loaded.append(image.convert("RGB"))
                loaded_paths.append(path)
            except Exception as exc:
                rows.append({"path": str(path), "error": str(exc) or exc.__class__.__name__})
        if loaded:
            try:
                inputs = processor(images=loaded, return_tensors="pt")
                with torch.inference_mode():
                    outputs = model(**inputs)
                    features = outputs.pooler_output
                    if features is None:
                        features = outputs.last_hidden_state[:, 0]
                    features = torch.nn.functional.normalize(features.float(), dim=1)
                for path, vector in zip(loaded_paths, features.cpu().tolist(), strict=True):
                    rows.append({"path": str(path), "embedding": vector})
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                rows.extend({"path": str(path), "error": error} for path in loaded_paths)
            finally:
                for image in loaded:
                    image.close()
        emit({"event": "batch", "batch_size": batch_size, "items": rows})
    emit({"event": "complete", "batch_size": batch_size, "device": "cpu"})


def serve_stdio() -> int:
    emit(ready_message())
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            if method == "shutdown":
                return 0
            if method != "embed":
                raise ValueError(f"未知方法: {method}")
            embed(request)
        except Exception as exc:
            emit({"event": "error", "error": str(exc) or exc.__class__.__name__})
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-stdio", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return
    if args.self_test:
        print(json.dumps(ready_message(), ensure_ascii=False))
        return
    if args.serve_stdio:
        raise SystemExit(serve_stdio())
    parser.error("请指定 --serve-stdio、--self-test 或 --version")


if __name__ == "__main__":
    main()

