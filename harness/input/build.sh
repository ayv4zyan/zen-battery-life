#!/bin/sh
# Builds bin/MFGA Input.app: a background-only app so macOS grants Accessibility to it directly
# (a plain binary would inherit the permission of whatever launched it).
set -e
cd "$(dirname "$0")/../.."
APP="bin/MFGA Input.app"
mkdir -p "$APP/Contents/MacOS"
swiftc -O harness/input/main.swift -o "$APP/Contents/MacOS/mfga-input"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>local.mfga.input</string>
  <key>CFBundleName</key><string>MFGA Input</string>
  <key>CFBundleExecutable</key><string>mfga-input</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
codesign --force --sign - -r='designated => identifier "local.mfga.input"' "$APP"
ln -sf "MFGA Input.app/Contents/MacOS/mfga-input" bin/mfga-input
