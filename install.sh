#!/usr/bin/env sh
# Copy the skill into Hermes' skills directory. Local only; no downloads.
set -eu
DEST="${HERMES_HOME:-$HOME/.hermes}/skills/contract-review"
SRC="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DEST"
# Keep a user-edited boilerplate library across reinstalls.
if [ -f "$DEST/assets/boilerplate.yaml" ]; then cp "$DEST/assets/boilerplate.yaml" "$DEST/.boilerplate.keep"; fi
for item in SKILL.md LICENSE requirements.txt scripts references templates assets; do
  rm -rf "$DEST/$item"
  cp -R "$SRC/$item" "$DEST/$item"
done
if [ -f "$DEST/.boilerplate.keep" ]; then mv "$DEST/.boilerplate.keep" "$DEST/assets/boilerplate.yaml"; fi
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +
echo "Installed to $DEST"
echo "Dependencies: python3 -m pip install --user -r \"$DEST/requirements.txt\""
