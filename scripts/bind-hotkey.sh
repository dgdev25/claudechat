#!/usr/bin/env bash
# Bind a keyboard shortcut to `claudechat toggle` under GNOME.
#
# Gives you a single-key voice toggle like Claude Code's own /voice, without
# opening a terminal. Default: Super+V. Pass a different accelerator as $1,
# e.g. ./scripts/bind-hotkey.sh '<Super><Shift>v'
#
# Undo:  ./scripts/bind-hotkey.sh --remove

set -euo pipefail
ACCEL="${1:-<Super>v}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="$(command -v uv || true)"
KEY_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/claudechat/"
BASE="org.gnome.settings-daemon.plugins.media-keys"

if [[ "$(uname -s)" == "Darwin" ]]; then
  cat <<'MAC'
macOS has no scriptable global-hotkey API, so this helper cannot bind one for you.
Pick whichever you already use:

  skhd          brew install koekeishiya/formulae/skhd
                then add to ~/.skhdrc:
                    cmd + shift - v : claudechat toggle

  Karabiner     map a key to a shell command via complex modifications

  Automator     New > Quick Action > Run Shell Script:  claudechat toggle
                then assign a shortcut in
                System Settings > Keyboard > Keyboard Shortcuts > Services

The toggle itself works identically: one press starts the engine and speech,
the next stops both.
MAC
  exit 0
fi

command -v gsettings >/dev/null || { echo "gsettings not found — this helper is GNOME only" >&2; exit 1; }

current="$(gsettings get ${BASE} custom-keybindings 2>/dev/null || echo "@as []")"

if [[ "${ACCEL}" == "--remove" ]]; then
  updated="$(python3 -c "
import ast,sys
cur=sys.argv[1]
items=[] if cur.strip() in ('@as []','[]') else ast.literal_eval(cur.replace('@as ',''))
items=[i for i in items if 'claudechat' not in i]
print(str(items).replace(\"'\", '\"'))" "${current}")"
  gsettings set ${BASE} custom-keybindings "${updated}"
  echo "[ok] Removed the claudechat shortcut"
  exit 0
fi

[[ -n "${UV}" ]] || { echo "uv not found on PATH" >&2; exit 1; }

gsettings set "${BASE}.custom-keybinding:${KEY_PATH}" name  "claudechat toggle"
gsettings set "${BASE}.custom-keybinding:${KEY_PATH}" command \
  "${UV} run --project ${ROOT} claudechat toggle"
gsettings set "${BASE}.custom-keybinding:${KEY_PATH}" binding "${ACCEL}"

updated="$(python3 -c "
import ast,sys
cur,path=sys.argv[1],sys.argv[2]
items=[] if cur.strip() in ('@as []','[]') else ast.literal_eval(cur.replace('@as ',''))
if path not in items: items.append(path)
print(str(items).replace(\"'\", '\"'))" "${current}" "${KEY_PATH}")"
gsettings set ${BASE} custom-keybindings "${updated}"

echo "[ok] ${ACCEL} now toggles claudechat speech on and off"
echo "     First press starts the engine; it speaks from then until you press again."
echo "     Remove with: ./scripts/bind-hotkey.sh --remove"
