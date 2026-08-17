#!/usr/bin/env bash
# Build a .deb package for the Keydous NJ81 driver.
# Usage: ./build-deb.sh [version]   (default 1.0.0)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VER="${1:-1.0.0}"
ARCH="all"
PKG="keydous-nj81_${VER}_${ARCH}.deb"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

ROOT="$STAGE/pkg"
mkdir -p "$ROOT/usr/lib/keydous-nj81" \
         "$ROOT/usr/bin" \
         "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/doc/keydous-nj81" \
         "$ROOT/usr/share/icons/hicolor/128x128/apps" \
         "$ROOT/usr/share/icons/hicolor/64x64/apps" \
         "$ROOT/usr/share/icons/hicolor/48x48/apps" \
         "$ROOT/usr/share/icons/hicolor/32x32/apps" \
         "$ROOT/lib/udev/rules.d" \
         "$STAGE/debian"

# --- package payload -------------------------------------------------------
cp -r "$SRC/keydous" "$ROOT/usr/lib/keydous-nj81/keydous"
cp "$SRC/keydous-driver" "$ROOT/usr/lib/keydous-nj81/keydous-driver"
cp -r "$SRC/docs" "$ROOT/usr/lib/keydous-nj81/docs"
cp -r "$SRC/icons" "$ROOT/usr/lib/keydous-nj81/icons"
chmod +x "$ROOT/usr/lib/keydous-nj81/keydous-driver"

cat > "$ROOT/usr/bin/keydous-nj81" <<'EOF'
#!/usr/bin/env bash
exec python3 /usr/lib/keydous-nj81/keydous/appwindow.py "$@"
EOF
chmod +x "$ROOT/usr/bin/keydous-nj81"

cat > "$ROOT/usr/bin/keydous-driver" <<'EOF'
#!/usr/bin/env bash
exec python3 /usr/lib/keydous-nj81/keydous-driver "$@"
EOF
chmod +x "$ROOT/usr/bin/keydous-driver"

cat > "$ROOT/usr/share/applications/keydous-nj81.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Keydous NJ81 Driver
GenericName=Keyboard configuration
Comment=Control the Keydous NJ81 keyboard: key mapping, RGB lighting, screen image upload, profiles, power, backup/restore and music/screen follow
Comment[zh_CN]=配置 Keydous NJ81 键盘：按键映射、RGB 灯效、屏幕上传、配置文件、电源、备份与恢复、音乐/屏幕跟随
Exec=/usr/bin/keydous-nj81
Icon=keydous-nj81
Terminal=false
Categories=Settings;
Keywords=keydous;nj81;keyboard;rgb;mechanical;driver;settings;key remapping;lighting;profile;backup;
StartupNotify=true
StartupWMClass=keydousnj81
EOF

cp "$SRC/icons/keydous-nj81.png"        "$ROOT/usr/share/icons/hicolor/128x128/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-64.png"     "$ROOT/usr/share/icons/hicolor/64x64/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-48.png"     "$ROOT/usr/share/icons/hicolor/48x48/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-32.png"     "$ROOT/usr/share/icons/hicolor/32x32/apps/keydous-nj81.png"
cp "$SRC/udev/50-keydous.rules"         "$ROOT/lib/udev/rules.d/50-keydous.rules"
cp "$SRC/README.md"                     "$ROOT/usr/share/doc/keydous-nj81/README.md"

# --- control -----------------------------------------------------------------
cat > "$STAGE/debian/control" <<EOF
Package: keydous-nj81
Version: $VER
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: YappLeCunt <yapplecunt@users.noreply.github.com>
Depends: python3 (>= 3.8), python3-gi, gir1.2-webkit2-4.1
Recommends: dbus-next | bleak
Homepage: https://github.com/YappLeCunt/keydous-nj81-linux
Description: Open-source Linux driver and web GUI for the Keydous NJ81 keyboard
 Key mapping, Fn-layer editing, all RGB lighting effects with Dazzle color
 cycling, 160x80 screen image upload, per-key picture layers, 6 onboard
 profiles, power/debounce/sleep settings, backup and restore, music and
 screen follow streams. Reverse-engineered from the vendor software and
 verified on hardware (firmware 0x0513). Talks to the keyboard over raw USB
 feature reports; no vendor daemon required.
EOF

cat > "$STAGE/debian/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: keydous-nj81-linux
Source: https://github.com/YappLeCunt/keydous-nj81-linux

Files: *
Copyright: 2026 YappLeCunt and contributors
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
EOF

cat > "$STAGE/debian/changelog" <<EOF
keydous-nj81 ($VER) stable; urgency=medium

  * First release: desktop GUI + CLI for the Keydous NJ81 keyboard.

 -- YappLeCunt <yapplecunt@users.noreply.github.com>  $(date -R)
EOF

# --- build --------------------------------------------------------------------
(
  cd "$ROOT"
  find . -type f -not -path './DEBIAN/*' -exec md5sum {} \; \
    | sed 's|  ./|  |' > "$STAGE/debian/md5sums"
  find . -type d -exec chmod 755 {} \;
  mkdir -p DEBIAN
  cp "$STAGE/debian/control" DEBIAN/control
  cp "$STAGE/debian/copyright" DEBIAN/copyright
  cp "$STAGE/debian/changelog" DEBIAN/changelog
  cp "$STAGE/debian/md5sums" DEBIAN/md5sums
  gzip -9n -c "$STAGE/debian/changelog" > DEBIAN/changelog.gz && rm -f DEBIAN/changelog
)
dpkg-deb --root-owner-group -Z xz -b "$ROOT" "$PKG"
echo "built: $PKG"
echo "verify: dpkg-deb --info $PKG | head -20"
