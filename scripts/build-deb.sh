#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "该脚本仅用于 Linux deb 打包"
  exit 2
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "缺少 dpkg-deb，请先安装 dpkg-dev"
  exit 1
fi

if [[ "${SKIP_BINARY_BUILD:-0}" != "1" ]]; then
  ./scripts/build-linux.sh
fi

APP_SOURCE="$ROOT_DIR/dist/AutomationToolbox"
if [[ ! -x "$APP_SOURCE/automation-toolbox" ]]; then
  echo "缺少已构建的程序：$APP_SOURCE/automation-toolbox"
  exit 1
fi

VERSION="$(sed -n 's/^Version: //p' packaging/linux/deb/control)"
ARCHITECTURE="$(sed -n 's/^Architecture: //p' packaging/linux/deb/control)"
HOST_ARCHITECTURE="$(dpkg --print-architecture)"
if [[ "$ARCHITECTURE" != "$HOST_ARCHITECTURE" ]]; then
  echo "目标架构 $ARCHITECTURE 与当前系统 $HOST_ARCHITECTURE 不一致"
  exit 1
fi

mkdir -p "$ROOT_DIR/build" "$ROOT_DIR/dist"
STAGE_ROOT="$(mktemp -d "$ROOT_DIR/build/automation-toolbox-deb.XXXXXX")"
trap 'rm -rf "$STAGE_ROOT"' EXIT

install -d \
  "$STAGE_ROOT/DEBIAN" \
  "$STAGE_ROOT/opt/automation-toolbox" \
  "$STAGE_ROOT/usr/bin" \
  "$STAGE_ROOT/usr/share/applications" \
  "$STAGE_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$STAGE_ROOT/usr/share/doc/automation-toolbox"

cp -a "$APP_SOURCE/." "$STAGE_ROOT/opt/automation-toolbox/"
chmod -R go-w "$STAGE_ROOT/opt/automation-toolbox"
find "$STAGE_ROOT/opt/automation-toolbox" -type d -exec chmod 0755 {} +
install -m 0644 packaging/linux/deb/control "$STAGE_ROOT/DEBIAN/control"
install -m 0755 packaging/linux/deb/automation-toolbox "$STAGE_ROOT/usr/bin/automation-toolbox"
install -m 0644 \
  packaging/linux/deb/automation-toolbox.desktop \
  "$STAGE_ROOT/usr/share/applications/automation-toolbox.desktop"
install -m 0644 \
  packaging/linux/deb/automation-toolbox.svg \
  "$STAGE_ROOT/usr/share/icons/hicolor/scalable/apps/automation-toolbox.svg"
install -m 0644 \
  packaging/linux/deb/README \
  "$STAGE_ROOT/usr/share/doc/automation-toolbox/README"

INSTALLED_SIZE="$(du -sk "$STAGE_ROOT" | cut -f1)"
sed -i "/^Architecture:/a Installed-Size: $INSTALLED_SIZE" "$STAGE_ROOT/DEBIAN/control"

OUTPUT="$ROOT_DIR/dist/automation-toolbox_${VERSION}_${ARCHITECTURE}.deb"
dpkg-deb --build --root-owner-group "$STAGE_ROOT" "$OUTPUT"
echo "deb 打包完成：$OUTPUT"
