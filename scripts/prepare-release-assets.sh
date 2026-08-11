#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="$(.venv/bin/python -c 'from backend.version import __version__; print(__version__)')"
PROVIDER_VERSION="$(.venv/bin/python -c 'import tomllib; print(tomllib.load(open("components/dinov3-provider/pyproject.toml", "rb"))["project"]["version"])')"
MAIN_ARCHIVE="dist/automation-toolbox_${VERSION}_ubuntu24.04_amd64.tar.gz"
DEB="dist/automation-toolbox_${VERSION}_amd64.deb"
PROVIDER="dist/automation-toolbox-provider-dinov3-cpu_${PROVIDER_VERSION}_ubuntu24.04_amd64.tar.gz"

for path in "$DEB" "$PROVIDER"; do
  [[ -f "$path" ]] || { echo "缺少发布资产: $path"; exit 1; }
done

tar -C dist/AutomationToolbox -czf "$MAIN_ARCHIVE" .
.venv/bin/python scripts/generate-component-catalog.py \
  --asset-dir dist --output dist/components-v1.json
uv export --quiet --preview-features sbom-export --frozen --no-dev --format cyclonedx1.5 \
  --output-file "dist/automation-toolbox_${VERSION}.cdx.json"
uv export --quiet --preview-features sbom-export \
  --project components/dinov3-provider --frozen --no-dev \
  --format cyclonedx1.5 \
  --output-file "dist/automation-toolbox-provider-dinov3-cpu_${PROVIDER_VERSION}.cdx.json"

sha256sum \
  "$MAIN_ARCHIVE" \
  "$DEB" \
  "$PROVIDER" \
  dist/components-v1.json \
  "dist/automation-toolbox_${VERSION}.cdx.json" \
  "dist/automation-toolbox-provider-dinov3-cpu_${PROVIDER_VERSION}.cdx.json" \
  > dist/SHA256SUMS

echo "Release Assets 已准备在 $ROOT_DIR/dist"
