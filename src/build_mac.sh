#!/usr/bin/env bash
# Build InkReady.app for macOS
# Run this from the src/ directory: bash build_mac.sh
#
# Produces: ../build/mac/InkReady.app
# Requires: pip install -r requirements.txt

set -e

pyinstaller \
  --name InkReady \
  --windowed \
  --onedir \
  --clean \
  app.py

mkdir -p ../build/mac
rm -rf ../build/mac/InkReady.app
mv dist/InkReady.app ../build/mac/InkReady.app

# Clean up PyInstaller artifacts
rm -rf build dist InkReady.spec

echo "Done → ../build/mac/InkReady.app"
