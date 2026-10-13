"""Settings for spotify-widget: defaults, validation, and load/save (JSON).

The file lives at  ~/.config/spotify-widget/config.json  (or $XDG_CONFIG_HOME/...).
Delete it, or use "Reset to defaults" in the settings window, to start over.
"""
import json
import os
import re

POSITIONS = ("fixed", "top-left", "top-right", "bottom-left", "bottom-right", "center")
LAYERS = ("normal", "above", "below")

DEFAULTS = {
    # ---- layout ----
    "width": 420,                 # card size in px
    "height": 140,
    "art_size": 100,              # album art size in px
    "art_radius": 20,             # album art corner radius
    "card_radius": 28,            # card corner radius
    "show_art": True,
    "show_time": True,            # elapsed / total time labels
    "show_volume": True,          # volume icon + slider
    "position_mode": "center",        # fixed | top-left | top-right | bottom-left | bottom-right | center
    "pos_x": 1385,                # used when position_mode == "fixed" (screen coordinates)
    "pos_y": 752,
    "margin": 24,                 # distance from the screen edge for the corner modes
    "monitor": -1,                # -1 = primary monitor, otherwise the monitor index (0, 1, ...)
    # ---- colours & text ----
    "card_color": "#10141c",
    "card_opacity": 0.28,         # 0 = clear glass, 1 = solid
    "border_color": "#ffffff",
    "border_opacity": 0.12,
    "border_width": 1,
    "text_color": "#f4f6fb",
    "accent_start": "#2ec27e",    # seek/volume bars, play button (gradient start)
    "accent_end": "#5fe0a4",      # gradient end
    "adapt_to_art": False,        # tint with each album cover's colour
    "font_family": "",            # "" = system default
    "title_size": 15,
    "artist_size": 12,
    # ---- behaviour ----
    "player": "spotify",          # playerctl player name (see `playerctl -l`)
    "layer": "normal",            # normal | above | below
    "start_visible": False,       # False = start hidden and wait for the shortcut
    "grab_focus": False,          # False = showing the card never steals keyboard focus
    "poll_ms": 500,               # how often to refresh while visible
    "hotkey": "",                 # global show/hide shortcut, GTK form e.g. "<Control><Alt>s"; "" = off
}

# integer settings -> (min, max)
RANGES = {
    "width": (260, 900),
    "height": (120, 400),
    "art_size": (48, 300),
    "art_radius": (0, 150),
    "card_radius": (0, 60),
    "border_width": (0, 6),
    "title_size": (8, 40),
    "artist_size": (8, 32),
    "margin": (0, 400),
    "pos_x": (-10000, 20000),
    "pos_y": (-10000, 20000),
    "monitor": (-1, 15),
    "poll_ms": (250, 5000),
}
FLOATS = {"card_opacity": (0.0, 1.0), "border_opacity": (0.0, 1.0)}
COLORS = ("card_color", "border_color", "text_color", "accent_start", "accent_end")
BOOLS = ("show_art", "show_time", "show_volume", "adapt_to_art", "start_visible", "grab_focus")

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_HOTKEY = re.compile(r"^(<[A-Za-z0-9_]+>)*[A-Za-z0-9_]+$")


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "spotify-widget", "config.json")


def sanitize(raw):
    """Return a complete, valid settings dict. Unknown keys are dropped, bad values fall back."""
    out = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    for key in DEFAULTS:
        if key not in raw:
            continue
        val = raw[key]
        try:
            if key in RANGES:
                lo, hi = RANGES[key]
                out[key] = max(lo, min(hi, int(round(float(val)))))
            elif key in FLOATS:
                lo, hi = FLOATS[key]
                out[key] = max(lo, min(hi, float(val)))
            elif key in COLORS:
                text = str(val).strip()
                if _HEX.match(text):
                    out[key] = text.lower()
            elif key in BOOLS:
                if isinstance(val, bool):
                    out[key] = val
            elif key == "position_mode":
                if val in POSITIONS:
                    out[key] = val
            elif key == "layer":
                if val in LAYERS:
                    out[key] = val
            elif key == "player":
                text = str(val).strip().lstrip("-")[:80]
                if text:
                    out[key] = text
            elif key == "hotkey":
                text = str(val).strip()
                if text == "" or (len(text) <= 60 and _HOTKEY.match(text)):
                    out[key] = text
            elif key == "font_family":
                # goes into the CSS, so strip anything that could break out of the string
                out[key] = re.sub(r'["\\;{}\r\n]', "", str(val)).strip()[:80]
        except (TypeError, ValueError):
            pass
    return out


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            return sanitize(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(cfg):
    """Write atomically so a crash can't leave a half-written file. Returns True on success."""
    path = config_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        return False
