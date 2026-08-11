#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.components.catalog import BUILTIN_COMPONENTS
from backend.components.manager import sha256_file
from backend.version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a signed-release component catalog")
    parser.add_argument("--asset-dir", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    components: list[dict[str, object]] = []
    for descriptor in BUILTIN_COMPONENTS.values():
        asset = args.asset_dir / descriptor.asset_name
        if not asset.is_file():
            raise SystemExit(f"缺少组件资产: {asset}")
        entry = descriptor.as_dict()
        entry.update(
            {
                "asset_sha256": sha256_file(asset),
                "asset_size": asset.stat().st_size,
                "download_url": (
                    "https://github.com/shenmi175/image-dataclean/releases/download/"
                    f"v{__version__}/{descriptor.asset_name}"
                ),
            }
        )
        components.append(entry)

    document = {
        "schema_version": 1,
        "application_version": __version__,
        "release_tag": f"v{__version__}",
        "components": components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
