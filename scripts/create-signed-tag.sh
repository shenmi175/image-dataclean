#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="$(.venv/bin/python -c 'from backend.version import __version__; print(__version__)')"
TAG="v${VERSION}"
SIGNING_KEY="$(git config --get user.signingkey || true)"

if [[ "$(git config --get gpg.format || true)" != "ssh" || -z "$SIGNING_KEY" ]]; then
  echo "请先配置 SSH 签名："
  echo "  git config gpg.format ssh"
  echo "  git config user.signingkey ~/.ssh/id_ed25519.pub"
  exit 2
fi

if [[ "$SIGNING_KEY" == key::* ]]; then
  PUBLIC_KEY="${SIGNING_KEY#key::}"
elif [[ "$SIGNING_KEY" == *.pub && -f "$SIGNING_KEY" ]]; then
  PUBLIC_KEY="$(<"$SIGNING_KEY")"
elif [[ -f "${SIGNING_KEY}.pub" ]]; then
  PUBLIC_KEY="$(<"${SIGNING_KEY}.pub")"
else
  echo "无法读取 SSH 签名公钥: $SIGNING_KEY"
  exit 2
fi

ALLOWED_SIGNERS="$(mktemp)"
trap 'rm -f "$ALLOWED_SIGNERS"' EXIT
printf 'release %s\n' "$PUBLIC_KEY" > "$ALLOWED_SIGNERS"

.venv/bin/python scripts/check-version.py --tag "$TAG"
git tag -s "$TAG" -m "Automation Toolbox ${TAG}"
git -c gpg.ssh.allowedSignersFile="$ALLOWED_SIGNERS" verify-tag "$TAG"
echo "已创建签名标签 $TAG；确认后运行: git push origin $TAG"
