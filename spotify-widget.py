#!/usr/bin/env python3
"""
Spotify desktop widget: a translucent glass card with album art, title/artist,
prev / play-pause / next, a draggable seek bar and a volume slider.

Keep these files together in one folder:
    spotify-widget.py   this file: the widget itself
    sw_config.py        defaults + loading/saving ~/.config/spotify-widget/config.json
    sw_style.py         builds the CSS from your settings
    sw_settings.py      the settings window

Usage:
    spotify-widget.py            start in the background (hidden unless "Start visible" is on)
    spotify-widget.py toggle     show / hide the card  <- bind this to a keyboard shortcut
                                 (or set a global shortcut in Settings > Behavior)
    spotify-widget.py settings   open the settings window
    spotify-widget.py quit       stop the widget
You can also right-click the card, or hover it and click the gear icon.

Needs: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 playerctl
"""
import os
os.environ["GDK_BACKEND"] = "x11"  # lets us position the window (works via XWayland too)

import argparse
import atexit
import hashlib
import math
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

try:                                   # optional: global keyboard shortcut support
    gi.require_version("Keybinder", "3.0")
    from gi.repository import Keybinder  # noqa: E402
    Keybinder.init()
except Exception:                      # package not installed (sudo apt install gir1.2-keybinder-3.0)
    Keybinder = None

from sw_config import DEFAULTS, load_config, sanitize, save_config  # noqa: E402
from sw_settings import SettingsWindow  # noqa: E402
from sw_style import accent_from_pixbuf, build_css  # noqa: E402

SCRIPT_NAME = os.path.basename(sys.argv[0]) or "spotify-widget.py"
PID_FILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "spotify-widget.pid")

SEP = "\x1f"
FORMAT = SEP.join(["{{status}}", "{{title}}", "{{artist}}", "{{mpris:artUrl}}",
                   "{{position}}", "{{mpris:length}}", "{{volume}}"])
MAX_ART_BYTES = 8 * 1024 * 1024
ART_RETRY_SECONDS = 10


def fmt_time(us):
    s = max(0, int(us / 1_000_000))
    return f"{s // 60}:{s % 60:02d}"


def ctl(player, *args):
    """Fire-and-forget playerctl command (runs in a thread so it never blocks the UI)."""
    def run():
        try:
            subprocess.run(["playerctl", "-p", player, *args], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


class Art(Gtk.DrawingArea):
    """Album art with rounded corners."""

    def __init__(self, size, radius):
        super().__init__()
        self.pb = None
        self.size = size
        self.radius = radius
        self.set_valign(Gtk.Align.CENTER)
        self.configure(size, radius)
        self.connect("draw", self.on_draw)

    def configure(self, size, radius):
        self.size, self.radius = size, radius
        self.pb = None                       # an old pixbuf would have the wrong size
        self.set_size_request(size, size)
        self.queue_draw()

    def set_pixbuf(self, pb):
        self.pb = pb
        self.queue_draw()

    def on_draw(self, _w, cr):
        s = self.size
        r = min(self.radius, s / 2)
        cr.new_sub_path()
        cr.arc(s - r, r, r, -math.pi / 2, 0)
        cr.arc(s - r, s - r, r, 0, math.pi / 2)
        cr.arc(r, s - r, r, math.pi / 2, math.pi)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        if self.pb:
            cr.clip()
            Gdk.cairo_set_source_pixbuf(cr, self.pb, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgba(1, 1, 1, 0.08)
            cr.fill()


class SpotifyWidget(Gtk.Window):
    def __init__(self, force_visible=False, open_settings=False):
        super().__init__()
        self.cfg = load_config()
        self.wanted = force_visible or self.cfg["start_visible"]   # toggled by the shortcut
        self.settings_win = None

        self.set_title("Spotify Widget")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_app_paintable(True)
        self.stick()
        self.get_style_context().add_class("sw-root")   # all our CSS is scoped to this class

        # drag anywhere on the card (except sliders/buttons) to move it; right-click for the menu
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("button-press-event", self.on_press)
        self.connect("enter-notify-event", self.on_enter)
        self.connect("leave-notify-event", self.on_leave)
        self.connect("configure-event", self.on_configure)

        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # ---------- layout ----------
        self.card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.card.set_name("card")

        self.close_btn = self._overlay_button("window-close-symbolic", "close", 14, "Hide", self.on_close)
        self.gear_btn = self._overlay_button("preferences-system-symbolic", "gear", 42, "Settings",
                                             self.open_settings)
        overlay = Gtk.Overlay()
        overlay.add(self.card)
        overlay.add_overlay(self.close_btn)
        overlay.add_overlay(self.gear_btn)
        self.add(overlay)

        self.art = Art(self.cfg["art_size"], self.cfg["art_radius"])
        self.art.set_no_show_all(True)
        self.card.pack_start(self.art, False, False, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        col.set_hexpand(True)
        col.set_valign(Gtk.Align.CENTER)
        self.card.pack_start(col, True, True, 0)

        self.title_lbl = self._label("title")
        self.title_lbl.set_margin_end(40)        # leave room for the close + settings buttons
        self.artist_lbl = self._label("artist")
        col.pack_start(self.title_lbl, False, False, 0)
        col.pack_start(self.artist_lbl, False, False, 0)

        # seek row
        prog = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prog.set_margin_top(8)
        self.elapsed = Gtk.Label(label="0:00")
        self.elapsed.set_name("time")
        self.elapsed.set_no_show_all(True)
        self.total = Gtk.Label(label="0:00")
        self.total.set_name("time")
        self.total.set_no_show_all(True)
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.set_can_focus(False)
        self.seek.connect("change-value", self.on_seek)
        prog.pack_start(self.elapsed, False, False, 0)
        prog.pack_start(self.seek, True, True, 0)
        prog.pack_start(self.total, False, False, 0)
        col.pack_start(prog, False, False, 0)

        # controls + volume row
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bottom.set_margin_top(4)
        self.prev_btn = self._button("media-skip-backward-symbolic",
                                     lambda *_: ctl(self.cfg["player"], "previous"))
        self.play_img = Gtk.Image.new_from_icon_name("media-playback-pause-symbolic",
                                                     Gtk.IconSize.LARGE_TOOLBAR)
        self.play_btn = self._button(None, lambda *_: ctl(self.cfg["player"], "play-pause"))
        self.play_btn.set_image(self.play_img)
        self.play_btn.set_always_show_image(True)
        self.play_btn.set_name("play")
        self.playing = None
        self.next_btn = self._button("media-skip-forward-symbolic",
                                     lambda *_: ctl(self.cfg["player"], "next"))
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            bottom.pack_start(b, False, False, 2)
        bottom.pack_start(Gtk.Box(), True, True, 0)       # spacer

        self.vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.vol_icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic", Gtk.IconSize.MENU)
        self.vol_icon.set_name("volicon")
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.vol.set_draw_value(False)
        self.vol.set_size_request(86, -1)
        self.vol.set_valign(Gtk.Align.CENTER)
        self.vol.set_can_focus(False)
        self.vol.set_increments(0.05, 0.1)
        self.vol.connect("change-value", self.on_vol)
        self.vol_box.pack_start(self.vol_icon, False, False, 0)
        self.vol_box.pack_start(self.vol, False, False, 0)
        self.vol_box.show_all()
        self.vol_box.set_no_show_all(True)
        bottom.pack_start(self.vol_box, False, False, 0)
        col.pack_start(bottom, False, False, 0)

        # ---------- state ----------
        self.art_url = None
        self.art_gen = 0                # bumped for every cover load; stale results are dropped
        self.art_accent = None
        self.art_fail_url = None
        self.art_fail_until = 0.0
        self.cache_dir = tempfile.mkdtemp(prefix="spotify-widget-")
        self.shown = False
        self.length_us = 0
        self.seek_hold = 0.0
        self.seek_value = 0.0
        self.seek_timer = 0
        self.vol_hold = 0.0
        self.vol_pending = 0.0
        self.vol_timer = 0
        self.polling = False
        self.poll_source = 0
        self.save_source = 0
        self.dragging = False           # True from a left-press on the card until the move is saved
        self.drag_save = 0
        self.bound_hotkey = None
        self.hotkey_status = "off"      # off | ok | failed | missing  (read by the settings window)
        atexit.register(self.cleanup)

        self.apply_config(None)

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.on_sig_toggle)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self.on_sig_settings)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.on_sig_quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.on_sig_quit)

        self.restart_poll_timer()
        if open_settings:
            self.open_settings()
        if self.wanted:
            self.request_poll()

    # ---------- small widget helpers ----------
    def _label(self, name):
        lbl = Gtk.Label()
        lbl.set_name(name)
        lbl.set_xalign(0)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        return lbl

    def _button(self, icon, cb):
        b = Gtk.Button() if icon is None else Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_can_focus(False)
        b.connect("clicked", cb)
        return b

    def _overlay_button(self, icon, name, margin_end, tip, cb):
        b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
        b.set_name(name)
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_can_focus(False)
        b.set_halign(Gtk.Align.END)
        b.set_valign(Gtk.Align.START)
        b.set_margin_top(12)
        b.set_margin_end(margin_end)
        b.set_tooltip_text(tip)
        b.connect("clicked", cb)
        return b

    @staticmethod
    def _set_text(label, text):
        if label.get_text() != text:
            label.set_text(text)

    def set_play_icon(self, playing):
        if playing == self.playing:
            return
        self.playing = playing
        self.play_img.set_from_icon_name(
            "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic",
            Gtk.IconSize.LARGE_TOOLBAR)

    def set_vol_icon(self, v):
        name = ("audio-volume-muted-symbolic" if v <= 0.01 else
                "audio-volume-low-symbolic" if v < 0.34 else
                "audio-volume-medium-symbolic" if v < 0.67 else
                "audio-volume-high-symbolic")
        self.vol_icon.set_from_icon_name(name, Gtk.IconSize.MENU)

    # ---------- settings ----------
    def apply_config(self, changed):
        """Apply settings to the UI. changed = list of changed keys, or None for everything."""
        c = self.cfg
        keys = set(changed or ())

        def touched(*names):
            return changed is None or any(n in keys for n in names)

        if touched("art_size", "art_radius"):
            self.art.configure(c["art_size"], c["art_radius"])
        if touched("art_size", "art_radius", "adapt_to_art"):
            self.art_url = None            # reload the cover (from cache) on the next poll, which
                                           # re-renders it at the new size / works out its accent color
        if touched("show_art", "show_time", "show_volume"):
            self.art.set_visible(c["show_art"])
            self.elapsed.set_visible(c["show_time"])
            self.total.set_visible(c["show_time"])
            self.vol_box.set_visible(c["show_volume"])
        if touched("width", "height", "art_size", "show_art", "title_size", "artist_size"):
            self.card.set_size_request(c["width"], c["height"])
            self.update_text_limits()
            self.resize(1, 1)
        self.refresh_style()
        if touched("layer", "grab_focus"):
            self.apply_window_hints()
        if touched("hotkey"):
            self.apply_hotkey()
        if touched("poll_ms") and self.poll_source:
            self.restart_poll_timer()
        if touched("position_mode", "pos_x", "pos_y", "margin", "monitor", "width", "height") and self.shown:
            self.place()

    # ---------- global shortcut ----------
    def suspend_hotkey(self):
        if self.bound_hotkey and Keybinder is not None:
            try:
                Keybinder.unbind(self.bound_hotkey)
            except Exception:
                pass
        self.bound_hotkey = None

    def apply_hotkey(self):
        """(Re)register the global show/hide shortcut; hotkey_status says how it went."""
        self.suspend_hotkey()
        key = self.cfg["hotkey"]
        if not key:
            self.hotkey_status = "off"
        elif Keybinder is None:
            self.hotkey_status = "missing"
        else:
            try:
                ok = bool(Keybinder.bind(key, self.on_hotkey))
            except Exception:
                ok = False
            if ok:
                self.bound_hotkey = key
            self.hotkey_status = "ok" if ok else "failed"

    def on_hotkey(self, *_):
        self.set_wanted(not self.wanted)

    def update_config(self, changes):
        """Called by the settings window: validate, apply live, save soon."""
        new = sanitize({**self.cfg, **changes})
        changed = [k for k in new if new[k] != self.cfg.get(k)]
        if not changed:
            return
        self.cfg = new
        self.apply_config(changed)
        self.schedule_save()

    def reset_config(self):
        self.cfg = dict(DEFAULTS)
        self.apply_config(None)
        self.schedule_save()

    def schedule_save(self):
        if self.save_source:
            GLib.source_remove(self.save_source)
        self.save_source = GLib.timeout_add(400, self.flush_save)

    def flush_save(self):
        self.save_source = 0
        if not save_config(self.cfg):
            print("spotify-widget: could not write settings file", file=sys.stderr)
        return False

    def open_settings(self, *_):
        if not self.wanted:
            self.set_wanted(True)          # show the card so changes are visible live
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self)
            self.settings_win.connect("destroy", self.on_settings_closed)
        else:
            self.settings_win.present()

    def on_settings_closed(self, *_):
        self.settings_win = None

    # ---------- style ----------
    def current_accent(self):
        c = self.cfg
        if c["adapt_to_art"] and self.art_accent:
            return self.art_accent
        return c["accent_start"], c["accent_end"]

    def refresh_style(self):
        try:
            self.css.load_from_data(build_css(self.cfg, self.current_accent()).encode())
        except GLib.Error as e:
            print(f"spotify-widget: CSS error: {e.message}", file=sys.stderr)

    def update_text_limits(self):
        """Cap the labels' natural width so long titles ellipsize instead of widening the card."""
        c = self.cfg
        avail = c["width"] - 32
        if c["show_art"]:
            avail -= c["art_size"] + 16
        self.title_lbl.set_max_width_chars(max(8, int((avail - 40) / (c["title_size"] * 0.58))))
        self.artist_lbl.set_max_width_chars(max(8, int(avail / (c["artist_size"] * 0.58))))

    def apply_window_hints(self):
        layer = self.cfg["layer"]
        self.set_keep_above(layer == "above")
        self.set_keep_below(layer == "below")
        self.set_accept_focus(self.cfg["grab_focus"])
        self.set_focus_on_map(self.cfg["grab_focus"])

    # ---------- positioning ----------
    def monitor_workarea(self):
        display = Gdk.Display.get_default()
        idx = self.cfg["monitor"]
        mon = display.get_monitor(idx) if 0 <= idx < display.get_n_monitors() else None
        if mon is None:
            mon = display.get_primary_monitor() or display.get_monitor(0)
        return mon.get_workarea()

    @staticmethod
    def point_on_a_monitor(x, y):
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            g = display.get_monitor(i).get_geometry()
            if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height:
                return True
        return False

    def target_pos(self):
        c = self.cfg
        w, h, m = c["width"], c["height"], c["margin"]
        mode = c["position_mode"]
        if mode == "fixed":
            if self.point_on_a_monitor(c["pos_x"] + w // 2, c["pos_y"] + h // 2):
                return c["pos_x"], c["pos_y"]
            mode = "center"                # the saved spot is off-screen (monitor unplugged, etc.)
        wa = self.monitor_workarea()
        left, right = wa.x + m, wa.x + wa.width - w - m
        top, bottom = wa.y + m, wa.y + wa.height - h - m
        if mode == "center":
            return wa.x + (wa.width - w) // 2, wa.y + (wa.height - h) // 2
        x = left if mode.endswith("left") else right
        y = top if mode.startswith("top") else bottom
        return x, y

    def place(self):
        self.move(*self.target_pos())

    def current_position(self):
        return self.get_position()

    # ---------- showing / hiding ----------
    def set_wanted(self, value):
        self.wanted = value
        if value:
            self.request_poll()
        else:
            self.hide_card()

    def show_card(self):
        self.place()                       # position first so it doesn't flash elsewhere
        self.show_all()
        self.place()
        self.apply_window_hints()
        self.shown = True

    def hide_card(self):
        if self.shown:
            self.hide()
            self.get_style_context().remove_class("hovering")
            self.shown = False

    def on_close(self, *_):
        """Hide the card (the process keeps running so your shortcut can bring it back)."""
        self.set_wanted(False)

    def on_sig_toggle(self):
        self.set_wanted(not self.wanted)
        return True                        # keep the signal handler registered

    def on_sig_settings(self):
        self.open_settings()
        return True

    def on_sig_quit(self):
        self.quit()
        return False

    def quit(self, *_):
        if self.save_source:
            GLib.source_remove(self.save_source)
            self.save_source = 0
            save_config(self.cfg)
        Gtk.main_quit()

    def cleanup(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        try:
            with open(PID_FILE) as f:
                if int(f.read().strip()) == os.getpid():
                    os.remove(PID_FILE)
        except (OSError, ValueError):
            pass

    # ---------- mouse ----------
    def on_press(self, _w, event):
        if event.button == 1:
            self.dragging = True
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        elif event.button == 3:
            self.show_menu(event)
        return False

    def on_configure(self, _w, _event):
        """The window moved: if the user dragged it, remember the new spot (fixed mode only)."""
        if self.dragging and self.shown and self.cfg["position_mode"] == "fixed":
            if self.drag_save:
                GLib.source_remove(self.drag_save)
            self.drag_save = GLib.timeout_add(500, self.save_dragged_pos)
        return False

    def save_dragged_pos(self):
        self.drag_save = 0
        self.dragging = False
        x, y = self.get_position()
        self.update_config({"pos_x": x, "pos_y": y})
        return False

    def show_menu(self, event):
        menu = Gtk.Menu()
        for label, cb in (("Settings…", self.open_settings),
                          ("Hide", lambda *_: self.set_wanted(False)),
                          ("Quit", lambda *_: self.quit())):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def on_enter(self, _w, _event):
        self.get_style_context().add_class("hovering")
        return False

    def on_leave(self, _w, event):
        # moving onto a child (button/slider) also fires a leave on the window; ignore that
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.get_style_context().remove_class("hovering")
        return False

    # ---------- seek + volume ----------
    def on_seek(self, _s, _scroll, value):
        value = max(0.0, min(1.0, value))
        self.seek_hold = time.monotonic() + 1.2          # stop polling from fighting the drag
        self.seek_value = value
        self.elapsed.set_text(fmt_time(value * self.length_us))
        if self.seek_timer:
            GLib.source_remove(self.seek_timer)
        self.seek_timer = GLib.timeout_add(180, self.flush_seek)   # send once you pause/let go
        return False

    def flush_seek(self):
        self.seek_timer = 0
        if self.length_us > 0:
            ctl(self.cfg["player"], "position", f"{self.seek_value * self.length_us / 1_000_000:.2f}")
            self.seek_hold = time.monotonic() + 1.0
        return False

    def on_vol(self, _s, _scroll, value):
        value = max(0.0, min(1.0, value))
        self.vol_hold = time.monotonic() + 1.5
        self.vol_pending = value
        self.set_vol_icon(value)
        if not self.vol_timer:
            self.vol_timer = GLib.timeout_add(80, self.flush_vol)
        return False

    def flush_vol(self):
        self.vol_timer = 0
        ctl(self.cfg["player"], "volume", f"{self.vol_pending:.3f}")
        return False

    # ---------- album art ----------
    def set_art(self, url):
        if url == self.art_url:
            return
        if url and url == self.art_fail_url and time.monotonic() < self.art_fail_until:
            return                                   # failed recently; don't hammer the server
        self.art_url = url
        self.art_gen += 1
        if not url or not url.startswith(("http://", "https://", "file://")):
            self.art.set_pixbuf(None)
            self.set_art_accent(None)
            return
        threading.Thread(target=self.art_worker, daemon=True,
                         args=(url, self.art_gen, self.cfg["art_size"], self.cfg["adapt_to_art"])).start()

    def art_worker(self, url, gen, size, adapt):
        path = None
        try:
            path = self.fetch_art(url)
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, False)
            accent = accent_from_pixbuf(pb) if adapt else None
        except Exception:
            if path and path.startswith(self.cache_dir):
                try:
                    os.remove(path)                  # never keep a corrupt cache entry
                except OSError:
                    pass
            GLib.idle_add(self.on_art_failed, url, gen)
            return
        GLib.idle_add(self.on_art, gen, pb, accent)

    def fetch_art(self, url):
        """Return a local path for the cover, downloading it (with timeout + size cap) if needed."""
        if url.startswith("file://"):
            return urllib.parse.unquote(urllib.parse.urlparse(url).path)
        path = os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest())
        if not os.path.exists(path):
            req = urllib.request.Request(url, headers={"User-Agent": "spotify-widget"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read(MAX_ART_BYTES + 1)
            if len(data) > MAX_ART_BYTES:
                raise ValueError("cover too large")
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)                    # atomic: readers never see a half-written file
            self.prune_cache()
        return path

    def prune_cache(self, keep=40):
        try:
            files = [os.path.join(self.cache_dir, n) for n in os.listdir(self.cache_dir)]
            files.sort(key=os.path.getmtime)
            for old in files[:-keep]:
                os.remove(old)
        except OSError:
            pass

    def on_art(self, gen, pb, accent):
        if gen == self.art_gen:                      # ignore covers for tracks we've moved on from
            self.art.set_pixbuf(pb)
            self.set_art_accent(accent)
        return False

    def on_art_failed(self, url, gen):
        if gen == self.art_gen:
            self.art.set_pixbuf(None)
            self.set_art_accent(None)
            self.art_fail_url = url
            self.art_fail_until = time.monotonic() + ART_RETRY_SECONDS
            self.art_url = None                      # allow a retry once the cool-down is over
        return False

    def set_art_accent(self, accent):
        if accent != self.art_accent:
            self.art_accent = accent
            self.refresh_style()

    # ---------- polling (playerctl runs in a worker thread, never on the UI thread) ----------
    def restart_poll_timer(self):
        if self.poll_source:
            GLib.source_remove(self.poll_source)
        self.poll_source = GLib.timeout_add(self.cfg["poll_ms"], self.on_tick)

    def on_tick(self):
        if self.wanted:                              # hidden = no work at all
            self.request_poll()
        return True

    def request_poll(self):
        if self.polling:
            return
        self.polling = True
        threading.Thread(target=self.poll_worker, args=(self.cfg["player"],), daemon=True).start()

    def poll_worker(self, player):
        if shutil.which("playerctl") is None:
            result = ("missing", "")
        else:
            try:
                out = subprocess.run(["playerctl", "-p", player, "metadata", "--format", FORMAT],
                                     capture_output=True, text=True, timeout=1.5)
                if out.returncode == 0 and out.stdout.strip("\n"):
                    result = ("ok", out.stdout.rstrip("\n"))
                else:
                    result = ("none", "")
            except Exception:
                result = ("none", "")
        GLib.idle_add(self.on_poll_result, result)

    def show_idle(self, message):
        """Nothing to show: reset every control so no stale track info is left behind."""
        self._set_text(self.title_lbl, message)
        self._set_text(self.artist_lbl, "")
        self.set_art(None)
        self.length_us = 0
        self._set_text(self.elapsed, "0:00")
        self._set_text(self.total, "0:00")
        if time.monotonic() > self.seek_hold:
            self.seek.set_value(0)
        self.set_play_icon(False)

    def on_poll_result(self, result):
        self.polling = False
        if not self.wanted:
            return False
        state, text = result
        if not self.shown:
            self.show_card()

        if state == "missing":
            self.show_idle("playerctl isn't installed")
            return False
        if state != "ok":
            self.show_idle(f"{self.cfg['player'].capitalize()} isn't running")
            return False

        parts = (text.split(SEP) + [""] * 7)[:7]
        status, title, artist, art_url, pos, length, vol = parts

        self._set_text(self.title_lbl, title or "Nothing playing")
        self._set_text(self.artist_lbl, artist)
        self.set_art(art_url)
        self.set_play_icon(status == "Playing")

        now = time.monotonic()
        try:
            pos_us, len_us = int(pos), int(length)
            self.length_us = len_us
            self._set_text(self.total, fmt_time(len_us))
            if now > self.seek_hold:
                self.seek.set_value(min(1.0, pos_us / len_us) if len_us > 0 else 0)
                self._set_text(self.elapsed, fmt_time(pos_us))
        except ValueError:
            pass

        try:
            v = max(0.0, min(1.0, float(vol)))
            if now > self.vol_hold:
                self.vol.set_value(v)
                self.set_vol_icon(v)
        except ValueError:
            pass
        return False


def running_pid():
    """PID of an already-running widget instance, or None."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return None
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if SCRIPT_NAME.encode() in f.read():
                return pid
    except (OSError, ValueError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Spotify desktop widget")
    parser.add_argument("command", nargs="?", choices=["toggle", "settings", "quit"],
                        help="toggle: show/hide the card; settings: open settings; quit: stop the widget")
    cmd = parser.parse_args().command

    pid = running_pid()
    if pid:                                   # already running: just forward the request
        sig = {"toggle": signal.SIGUSR1, "settings": signal.SIGUSR2, "quit": signal.SIGTERM}.get(cmd)
        if sig:
            os.kill(pid, sig)
        return
    if cmd == "quit":
        return

    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    SpotifyWidget(force_visible=cmd in ("toggle", "settings"), open_settings=(cmd == "settings"))
    Gtk.main()


if __name__ == "__main__":
    main()
