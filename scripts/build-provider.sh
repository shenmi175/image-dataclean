#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "该脚本仅用于 Linux 打包"
  exit 2
fi
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" || "$(dpkg --print-architecture)" != "amd64" ]]; then
  echo "仅支持在 Ubuntu 24.04 amd64 上生成官方 Provider"
  exit 2
fi

COMPONENT_DIR="$ROOT_DIR/components/dinov3-provider"
PROVIDER_VERSION="$(.venv/bin/python -c 'import tomllib; print(tomllib.load(open("components/dinov3-provider/pyproject.toml", "rb"))["project"]["version"])')"
uv sync --project "$COMPONENT_DIR" --frozen --group build --no-dev
uv run --project "$COMPONENT_DIR" --no-sync pyinstaller \
  --noconfirm --clean --distpath "$ROOT_DIR/dist/provider" \
  --workpath "$ROOT_DIR/build/provider" \
  "$COMPONENT_DIR/provider.spec"

SOURCE="$ROOT_DIR/dist/provider/AutomationToolboxProviderDINOv3"
cp "$ROOT_DIR/LICENSE" "$SOURCE/LICENSE"
cp "$ROOT_DIR/THIRD_PARTY_NOTICES.md" "$SOURCE/THIRD_PARTY_NOTICES.md"
"$SOURCE/automation-toolbox-provider-dinov3" --self-test
OUTPUT="$ROOT_DIR/dist/automation-toolbox-provider-dinov3-cpu_${PROVIDER_VERSION}_ubuntu24.04_amd64.tar.gz"
tar -C "$SOURCE" -czf "$OUTPUT" .
echo "Provider 打包完成：$OUTPUT"
