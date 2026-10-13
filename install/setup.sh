#!/usr/bin/env bash
# spotify-widget setup: installs the dependencies and sets Ctrl+Alt+S as the show/hide shortcut.
# Usage: ./install/setup.sh [--no-deps] [--no-shortcut]
set -euo pipefail

SHORTCUT='<Control><Alt>s'      # GTK/GNOME form of the key combo
SHORTCUT_LABEL='Ctrl+Alt+S'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIDGET="$(cd "$HERE/.." && pwd)/spotify-widget.py"

DO_DEPS=1
DO_SHORTCUT=1
for arg in "$@"; do
  case "$arg" in
    --no-deps)     DO_DEPS=0 ;;
    --no-shortcut) DO_SHORTCUT=0 ;;
    -h|--help)     sed -n '2,3p' "$0"; exit 0 ;;
    *)             echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

# colours only when writing to a terminal (set NO_COLOR=1 to turn them off)
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; RESET=$'\033[0m'
  KEYCAP=$'\033[1;30;42m'      # bold dark text on a green background
else
  BOLD=''; DIM=''; GREEN=''; YELLOW=''; CYAN=''; RESET=''; KEYCAP=''
fi

say()  { printf '\n%s==>%s %s%s%s\n' "$CYAN" "$RESET" "$BOLD" "$*" "$RESET"; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
line() { printf '      %s\n' "$*"; }
box() {
  local width=46 bar text="$1" gap
  bar="$(printf '─%.0s' $(seq 1 "$width"))"
  gap=$(( width - 6 - ${#text} ))
  printf '\n  %s╭%s╮%s\n' "$GREEN" "$bar" "$RESET"
  printf '  %s│%s%*s%s│%s\n' "$GREEN" "$RESET" "$width" '' "$GREEN" "$RESET"
  printf '  %s│%s   %s✓%s  %s%s%s%*s%s│%s\n' "$GREEN" "$RESET" "$GREEN" "$RESET" "$BOLD" "$text" "$RESET" "$gap" '' "$GREEN" "$RESET"
  printf '  %s│%s%*s%s│%s\n' "$GREEN" "$RESET" "$width" '' "$GREEN" "$RESET"
  printf '  %s╰%s╯%s\n' "$GREEN" "$bar" "$RESET"
}
# "Ctrl+Alt+S" -> highlighted key badges: [ Ctrl ] + [ Alt ] + [ S ]
keycaps() {
  local IFS='+' key out='' first=1
  for key in $1; do
    [ "$first" -eq 1 ] || out+=" ${DIM}+${RESET} "
    first=0
    if [ -n "$KEYCAP" ]; then out+="${KEYCAP} ${key} ${RESET}"; else out+="[${key}]"; fi
  done
  printf '%s' "$out"
}
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

[ -f "$WIDGET" ] || { echo "Can't find $WIDGET (run this from the repo)." >&2; exit 1; }
chmod +x "$WIDGET"

# ---------------------------------------------------------------- dependencies
install_deps() {
  local sudo=""
  if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then sudo="sudo"; else
      warn "Not root and sudo is missing, skipping dependency install."; return 0
    fi
  fi

  if command -v apt-get >/dev/null 2>&1; then
    $sudo apt-get update
    $sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-keybinder-3.0 playerctl
  elif command -v dnf >/dev/null 2>&1; then
    $sudo dnf install -y python3-gobject python3-cairo gtk3 keybinder3 playerctl
  elif command -v pacman >/dev/null 2>&1; then
    $sudo pacman -S --needed --noconfirm python-gobject python-cairo gtk3 libkeybinder3 playerctl
  else
    warn "Unsupported package manager. Install these yourself: PyGObject (python3-gi), GTK 3, playerctl, keybinder3 (optional)."
  fi
}

# -------------------------------------------------------------------- shortcut
# 1) the widget's own "Global shortcut" setting (what Settings > Behavior shows)
set_app_hotkey() {
  # stop a running widget first, so it can't overwrite the file with its old settings
  python3 "$WIDGET" quit >/dev/null 2>&1 || true
  sleep 1
  python3 - "$SHORTCUT" <<'PY'
import json, os, sys
base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
path = os.path.join(base, "spotify-widget", "config.json")
try:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        cfg = {}
except (OSError, ValueError):
    cfg = {}
cfg["hotkey"] = sys.argv[1]
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, path)
PY
}

# 2) a desktop-level shortcut (needed on Wayland, where the built-in one only works
#    while an X11 window has focus)
set_gnome_shortcut() {
  local schema=org.gnome.settings-daemon.plugins.media-keys
  local path=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/spotify-widget/
  local key="$schema.custom-keybinding:$path"

  # add our entry to the list of custom shortcuts without touching the existing ones
  python3 - "$schema" "$path" <<'PY'
import ast, subprocess, sys
schema, path = sys.argv[1:3]
cur = subprocess.check_output(["gsettings", "get", schema, "custom-keybindings"], text=True).strip()
cur = ast.literal_eval(cur.replace("@as ", ""))
if path not in cur:
    cur.append(path)
subprocess.run(["gsettings", "set", schema, "custom-keybindings", str(cur)], check=True)
PY

  gsettings set "$key" name 'Spotify Widget'
  gsettings set "$key" command "python3 '$WIDGET' toggle"
  gsettings set "$key" binding "$SHORTCUT"
}

setup_shortcut() {
  local desktop session
  desktop="$(lower "${XDG_CURRENT_DESKTOP:-}")"
  session="$(lower "${XDG_SESSION_TYPE:-}")"

  set_app_hotkey
  ok "Widget setting saved: Global shortcut = $SHORTCUT_LABEL"

  if [ "$session" = "wayland" ]; then
    if [[ "$desktop" == *gnome* ]] && command -v gsettings >/dev/null 2>&1; then
      set_gnome_shortcut
      ok "Desktop shortcut set, so $SHORTCUT_LABEL works from any app (Wayland)"
    else
      warn "Wayland: the built-in shortcut only works while an X11 window has focus."
      warn "Add a custom shortcut in your desktop's settings to use it everywhere:"
      line "key:      $SHORTCUT_LABEL"
      line "command:  python3 '$WIDGET' toggle"
    fi
  fi

  # start it (hidden) so the shortcut is live right away
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    nohup python3 "$WIDGET" >/dev/null 2>&1 &
    disown
  fi
}

# ------------------------------------------------------------------------ main
if [ "$DO_DEPS" -eq 1 ]; then
  say "Installing dependencies"
  install_deps
fi

say "Checking"
if python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null; then
  ok "GTK 3 + PyGObject"
else
  warn "PyGObject / GTK 3 not importable. The widget won't start until that's installed."
fi
if command -v playerctl >/dev/null 2>&1; then ok "playerctl"; else warn "playerctl not found."; fi

if [ "$DO_SHORTCUT" -eq 1 ]; then
  say "Setting the shortcut"
  setup_shortcut
fi

box "Spotify Widget is ready"
echo
if [ "$DO_SHORTCUT" -eq 1 ]; then
  printf '   %sShow / hide%s   %s\n' "$DIM" "$RESET" "$(keycaps "$SHORTCUT_LABEL")"
else
  printf '   %sShow / hide%s   python3 %s toggle\n' "$DIM" "$RESET" "$WIDGET"
fi
printf '\n   %sSettings%s      python3 %s settings\n\n' "$DIM" "$RESET" "$WIDGET"
