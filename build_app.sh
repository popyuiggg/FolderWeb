#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
app_dir="$project_dir/dist/FolderWeb.app"
contents_dir="$app_dir/Contents"
machine_arch="$(uname -m)"

case "$machine_arch" in
  arm64|x86_64) ;;
  *)
    echo "Unsupported macOS architecture: $machine_arch" >&2
    exit 1
    ;;
esac

rm -rf "$app_dir"
mkdir -p "$contents_dir/MacOS" "$contents_dir/Resources"

swiftc \
  -O \
  -target "$machine_arch-apple-macos13.0" \
  "$project_dir/ServerApp.swift" \
  -o "$contents_dir/MacOS/FolderWeb"

install -m 644 "$project_dir/Info.plist" "$contents_dir/Info.plist"
install -m 755 "$project_dir/headless_server.py" "$contents_dir/Resources/headless_server.py"

codesign --force --deep --sign - "$app_dir"
codesign --verify --deep --strict "$app_dir"

echo "Built: $app_dir"

