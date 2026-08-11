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
  echo "仅支持在 Ubuntu 24.04 amd64 上生成官方安装包"
  exit 2
fi

command -v uv >/dev/null 2>&1 || { echo "缺少 uv"; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "缺少 pnpm"; exit 1; }

for package in python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 libgtk-3-0t64; do
  if ! dpkg-query -W "$package" >/dev/null 2>&1; then
    echo "缺少 Ubuntu 系统依赖：$package"
    echo "请运行：sudo apt install python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0 libgtk-3-0t64"
    exit 1
  fi
done

uv sync --frozen --no-dev --group build
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
.venv/bin/pyinstaller --noconfirm --clean packaging/linux/toolbox.spec
cp packaging/linux/start-toolbox.sh dist/AutomationToolbox/start-toolbox.sh
cp packaging/linux/PACKAGE_README.txt dist/AutomationToolbox/README.txt
chmod +x dist/AutomationToolbox/start-toolbox.sh

echo "打包完成：$ROOT_DIR/dist/AutomationToolbox/automation-toolbox"
