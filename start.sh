#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODE="${1:-desktop}"

if [[ "$MODE" =~ ^(dev|desktop|backend|build|test)$ ]] \
  && { [[ ! -x .venv/bin/python ]] || [[ ! -d frontend/node_modules ]]; }; then
  echo "依赖尚未初始化，请先运行 ./scripts/bootstrap.sh"
  exit 1
fi

case "$MODE" in
  dev)
    .venv/bin/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8765 &
    BACKEND_PID=$!
    trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
    pnpm --dir frontend dev
    ;;
  desktop)
    pnpm --dir frontend build
    .venv/bin/python -m desktop.launcher
    ;;
  backend)
    exec .venv/bin/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8765
    ;;
  build)
    pnpm --dir frontend build
    ;;
  package)
    exec ./scripts/build-linux.sh
    ;;
  deb)
    exec ./scripts/build-deb.sh
    ;;
  test)
    .venv/bin/ruff check backend desktop tests scripts components/dinov3-provider/src components/dinov3-provider/tests
    PYTHONPATH=components/dinov3-provider/src .venv/bin/pytest
    pnpm --dir frontend typecheck
    ;;
  *)
    echo "用法: ./start.sh [dev|desktop|backend|build|package|deb|test]"
    exit 2
    ;;
esac
