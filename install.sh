#!/usr/bin/env bash
# Install the Keydous NJ81 driver as a desktop app.
#   - copies the app to ~/.local/lib/keydous-nj81
#   - launcher to ~/.local/bin/keydous-nj81
#   - .desktop entry + app icon
#   - optionally installs the udev rule (needs sudo)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/lib/keydous-nj81"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"

echo "==> Copying app to $DEST"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/keydous" "$SRC/keydous-driver" "$SRC/docs" "$SRC/icons" "$DEST/"

echo "==> Creating launcher $BIN/keydous-nj81"
mkdir -p "$BIN"
cat > "$BIN/keydous-nj81" <<EOF
#!/usr/bin/env bash
exec python3 "$DEST/keydous/appwindow.py" "\$@"
EOF
chmod +x "$BIN/keydous-nj81"

echo "==> Installing desktop entry + icon"
mkdir -p "$APPS"
cat > "$APPS/keydous-nj81.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Keydous NJ81 Driver
GenericName=Keyboard configuration
Comment=Control the Keydous NJ81 keyboard: key mapping, RGB lighting, screen image upload, profiles, power, backup/restore and music/screen follow
Comment[zh_CN]=配置 Keydous NJ81 键盘：按键映射、RGB 灯效、屏幕上传、配置文件、电源、备份与恢复、音乐/屏幕跟随
Exec=$BIN/keydous-nj81
Icon=keydous-nj81
Terminal=false
Categories=Settings;
Keywords=keydous;nj81;keyboard;rgb;mechanical;driver;settings;key remapping;lighting;profile;backup;
StartupNotify=true
StartupWMClass=keydousnj81
EOF

mkdir -p "$ICONS/scalable/apps" "$ICONS/128x128/apps" "$ICONS/64x64/apps" "$ICONS/48x48/apps" "$ICONS/32x32/apps"
cp "$SRC/icons/keydous-nj81.png" "$ICONS/128x128/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-64.png" "$ICONS/64x64/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-48.png" "$ICONS/48x48/apps/keydous-nj81.png"
cp "$SRC/icons/keydous-nj81-32.png" "$ICONS/32x32/apps/keydous-nj81.png"

echo "==> Refreshing desktop databases"
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "==> udev rule"
if command -v sudo >/dev/null 2>&1; then
    read -r -p "Install udev rule (allows unprivileged USB access)? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        sudo cp "$SRC/udev/50-keydous.rules" /etc/udev/rules.d/50-keydous.rules
        sudo udevadm control --reload && sudo udevadm trigger
        echo "udev rule installed."
    fi
else
    echo "sudo not found - copy udev/50-keydous.rules to /etc/udev/rules.d/ manually."
fi

echo
echo "Done. Launch it from your app menu, or run: $BIN/keydous-nj81"
echo "Terminal usage: $BIN/keydous-driver --help"