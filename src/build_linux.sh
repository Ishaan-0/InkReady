#!/usr/bin/env bash
# Build InkReady binary for Linux
# Run this from the src/ directory: bash build_linux.sh
#
# Produces: ../build/linux/InkReady
# Requires: pip install -r requirements.txt

set -e

pyinstaller \
  --name InkReady \
  --onefile \
  --clean \
  app.py

mkdir -p ../build/linux
rm -f ../build/linux/InkReady
mv dist/InkReady ../build/linux/InkReady

# Clean up PyInstaller artifacts
rm -rf build dist InkReady.spec

echo "Done → ../build/linux/InkReady"
