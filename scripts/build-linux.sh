#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "该脚本仅用于 Linux 打包"
  exit 2
fi

if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  echo "依赖尚未初始化，请先运行 ./scripts/bootstrap.sh"
  exit 1
fi

for package in python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0; do
  if ! dpkg-query -W "$package" >/dev/null 2>&1; then
    echo "缺少 Ubuntu 系统依赖：$package"
    echo "请运行：sudo apt install python3-gi gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0"
    exit 1
  fi
done

if [[ ! -x .venv/bin/pyinstaller ]]; then
  echo "缺少 PyInstaller，请运行：.venv/bin/pip install -e '.[build]'"
  exit 1
fi

pnpm --dir frontend build
export PYTHONPATH="$ROOT_DIR/packaging/linux${PYTHONPATH:+:$PYTHONPATH}"
.venv/bin/pyinstaller --noconfirm --clean packaging/linux/toolbox.spec
cp packaging/linux/start-toolbox.sh dist/AutomationToolbox/start-toolbox.sh
cp packaging/linux/PACKAGE_README.txt dist/AutomationToolbox/README.txt
chmod +x dist/AutomationToolbox/start-toolbox.sh

echo "打包完成：$ROOT_DIR/dist/AutomationToolbox/automation-toolbox"
