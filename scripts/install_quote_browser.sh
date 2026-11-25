#!/bin/bash
# Install Chromium for the Progressive quote browser.
# Run on the server as the same Linux user that runs gunicorn, after pip install.
# The app reads the profile from QUOTE_BROWSER_PROFILE_DIR, or /var/lib/regi/progressive-profile.
#
#   cd "$HOME/RegiManager"
#   ./venv/bin/python -m pip install -r requirements.txt
#   bash scripts/install_quote_browser.sh
#
# By hand, the same steps are:
#   ./venv/bin/python -m playwright install chromium
#   sudo ./venv/bin/python -m playwright install-deps chromium
#   sudo mkdir -p /var/lib/regi/progressive-profile
#   sudo chown "$USER:$USER" /var/lib/regi/progressive-profile
#   chmod 700 /var/lib/regi/progressive-profile
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No venv python at $PY. Install requirements.txt into that venv first." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
"$PY" -m playwright install chromium

install_os_libs() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$PY" -m playwright install-deps chromium
    return
  fi
  if "$PY" -m playwright install-deps chromium --dry-run; then
    echo "OS libraries for Chromium are already installed."
    return
  fi
  if sudo -n true; then
    sudo -n "$PY" -m playwright install-deps chromium
    return
  fi
  echo "Chromium is downloaded, but its OS libraries are missing and this user cannot sudo without a password." >&2
  echo "Run once as root, then deploy again:" >&2
  echo "  sudo $PY -m playwright install-deps chromium" >&2
  exit 1
}
install_os_libs

PROFILE="${QUOTE_BROWSER_PROFILE_DIR:-/var/lib/regi/progressive-profile}"
if [[ ! -d "$PROFILE" ]]; then
  if mkdir -p "$PROFILE" 2>/dev/null; then
    :
  elif sudo -n mkdir -p "$PROFILE" && sudo -n chown "$(id -un):$(id -gn)" "$PROFILE"; then
    :
  else
    echo "Could not create $PROFILE." >&2
    echo "Run: sudo mkdir -p $PROFILE && sudo chown $(id -un):$(id -gn) $PROFILE && chmod 700 $PROFILE" >&2
    exit 1
  fi
fi
chmod 700 "$PROFILE"
if [[ ! -w "$PROFILE" ]]; then
  echo "Profile directory is not writable: $PROFILE" >&2
  exit 1
fi

"$PY" - <<'PY'
import tempfile
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
try:
    with tempfile.TemporaryDirectory() as profile:
        ctx = pw.chromium.launch_persistent_context(profile, headless=True)
        ctx.close()
finally:
    pw.stop()
print("Chromium launches.")
PY
