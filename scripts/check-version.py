#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.version import __version__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    frontend = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    provider = (root / "components" / "dinov3-provider" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    expected_provider = 'version = "0.1.0"'
    errors: list[str] = []
    if frontend.get("version") != __version__:
        errors.append(f"前端版本 {frontend.get('version')} != {__version__}")
    if expected_provider not in provider:
        errors.append("DINOv3 Provider 版本应为 0.1.0")
    if args.tag and args.tag != f"v{__version__}":
        errors.append(f"标签 {args.tag} != v{__version__}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"版本一致: {__version__} (Provider 0.1.0)")


if __name__ == "__main__":
    main()

