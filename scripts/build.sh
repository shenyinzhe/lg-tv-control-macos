#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/' >&2; exit 1; }
xcrun --find swiftc >/dev/null
[ -x .build/venv/bin/python ] || uv venv --python 3.13 .build/venv
uv pip install --python .build/venv/bin/python -r requirements-build.txt
.build/venv/bin/python -m unittest discover -s tests -v
.build/venv/bin/pyinstaller --noconfirm --onedir --name lgtv-helper \
  --distpath .build/helper-dist --workpath .build/pyinstaller --specpath .build helper/controller.py
app='dist/LG TV Control.app'
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -swift-version 5 -O -module-cache-path .build/ModuleCache \
  -framework AppKit -framework Carbon app/main.swift -o "$app/Contents/MacOS/LGTVControl"
.build/venv/bin/python scripts/bundle.py
xattr -cr "$app"
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"
ditto -c -k --sequesterRsrc --keepParent "$app" 'dist/LG TV Control.zip'
printf 'Built: %s\n' "$PWD/$app"
