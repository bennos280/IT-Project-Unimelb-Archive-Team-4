#!/bin/sh
# Installs PrestCribe on a Mac, or updates it, from the latest GitHub release. Paste this in Terminal:
#   curl -LsSf https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest/download/install.sh | sh
# It installs uv (which brings Python) if it's missing, puts the app in ~/Library/Application Support/PrestCribe (an update
# keeps its database, scans and results: none are in a release), installs its libraries, adds a PrestCribe launcher to the Desktop and starts it.
# PRESTCRIBE_ZIP: a release zip on this computer instead of the latest download; PRESTCRIBE_HOME: another folder;
# PRESTCRIBE_NO_LAUNCHER, PRESTCRIBE_NO_START: skip those steps.
set -eu
RELEASE="https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4/releases/latest/download/PrestCribe.zip"
if [ "$(uname -s)" = Darwin ]; then DEFAULT="$HOME/Library/Application Support/PrestCribe"; else DEFAULT="$HOME/.local/share/PrestCribe"; fi
FOLDER="${PRESTCRIBE_HOME:-$DEFAULT}"

# its libraries are built for macOS 14 or later
if [ "$(uname -s)" = Darwin ]; then
    if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 14 ]; then
        echo "PrestCribe needs macOS 14 Sonoma or later." >&2
        exit 1
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="${UV_INSTALL_DIR:-$HOME/.local/bin}:$PATH"
    export PATH
fi
UV="$(command -v uv)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ZIP="${PRESTCRIBE_ZIP:-}"
if [ -z "$ZIP" ]; then
    echo "Downloading PrestCribe..."
    ZIP="$WORK/PrestCribe.zip"
    curl -LsSf "$RELEASE" -o "$ZIP"
fi
mkdir -p "$WORK/app" "$FOLDER"
unzip -q "$ZIP" -d "$WORK/app"  # no database in it: the one here is kept, or made on first run
cp -R "$WORK/app/." "$FOLDER/"

echo "Installing its libraries (the first time downloads a few hundred MB)..."
"$UV" sync --directory "$FOLDER"

# what starts it: PrestCribe.command in its folder, which runs it in a Terminal window (close the window to stop it); on a Mac,
# PrestCribe.app in ~/Applications opens that, with PrestCribe's icon, in Launchpad, Spotlight and the Dock, and a link to it on
# the Desktop. Both are made here, not downloaded, so macOS opens them without asking.
LAUNCHER="$FOLDER/PrestCribe.command"
printf '#!/bin/sh\n# Starts PrestCribe; close this window to stop it.\ncd "%s" && exec "%s" run prestcribe\n' "$FOLDER" "$UV" > "$LAUNCHER"
chmod +x "$LAUNCHER"
APP="$HOME/Applications/PrestCribe.app"
if [ -z "${PRESTCRIBE_NO_LAUNCHER:-}" ] && [ "$(uname -s)" = Darwin ]; then
    rm -rf "$APP"
    mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
    printf '#!/bin/sh\nexec open -a Terminal "%s"\n' "$LAUNCHER" > "$APP/Contents/MacOS/PrestCribe"
    chmod +x "$APP/Contents/MacOS/PrestCribe"
    cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>PrestCribe</string>
  <key>CFBundleDisplayName</key><string>PrestCribe</string>
  <key>CFBundleIdentifier</key><string>io.github.bennos280.prestcribe</string>
  <key>CFBundleExecutable</key><string>PrestCribe</string>
  <key>CFBundleIconFile</key><string>PrestCribe</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
</dict></plist>
PLIST
    ICONS="$WORK/PrestCribe.iconset"  # the icon in every size macOS asks for, from the 1024 px one
    mkdir -p "$ICONS"
    [ -f "$FOLDER/frontend/dist/app-icon.png" ] && for size in 16 32 128 256 512; do
        sips -z "$size" "$size" "$FOLDER/frontend/dist/app-icon.png" --out "$ICONS/icon_${size}x${size}.png" >/dev/null
        sips -z "$((size * 2))" "$((size * 2))" "$FOLDER/frontend/dist/app-icon.png" --out "$ICONS/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONS" -o "$APP/Contents/Resources/PrestCribe.icns" 2>/dev/null || echo "(PrestCribe's icon couldn't be made; the app works without it)"
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true
    rm -f "$HOME/Desktop/PrestCribe.command"  # the launcher an earlier install put there
    if [ -d "$HOME/Desktop" ]; then ln -sfn "$APP" "$HOME/Desktop/PrestCribe"; fi
    echo "Added PrestCribe to your Applications (Launchpad) and Desktop."
fi

if ! command -v claude >/dev/null 2>&1 && ! command -v codex >/dev/null 2>&1; then
    echo "Note: reading pages needs Claude Code or the Codex CLI signed in. PrestCribe's Settings page shows how."
fi
echo "PrestCribe is installed in $FOLDER."
if [ -z "${PRESTCRIBE_NO_START:-}" ]; then
    if [ "$(uname -s)" = Darwin ]; then
        open -a Terminal "$LAUNCHER"  # in its own Terminal window, as opening the app would
    else
        cd "$FOLDER" && exec "$UV" run prestcribe
    fi
fi
