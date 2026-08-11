#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

uv sync --frozen --group dev
pnpm --dir frontend install --frozen-lockfile

echo "项目环境初始化完成。"
