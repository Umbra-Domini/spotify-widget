"""The settings window for spotify-widget.

Every control applies live to the card and is saved automatically (debounced by the widget).
"""
import os

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from sw_config import RANGES  # noqa: E402
from sw_style import icon_color_on, rgba  # noqa: E402

POSITION_OPTIONS = [
    ("fixed", "Fixed coordinates (X / Y)"),
    ("top-left", "Top left"),
    ("top-right", "Top right"),
    ("bottom-left", "Bottom left"),
    ("bottom-right", "Bottom right"),
    ("center", "Center"),
]
LAYER_OPTIONS = [
    ("normal", "Normal"),
    ("above", "Always on top"),
    ("below", "Below other windows"),
]


WAYLAND = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
GITHUB_URL = "https://github.com/Umbra-Domini/spotify-widget#shortcuts-on-wayland"   # CHANGE ME if the repo lives elsewhere
COFFEE_URL = "https://www.buymeacoffee.com/UmbraDomini"  
WAYLAND_NOTE = ("Wayland: this shortcut only works while an X11 window has focus. Get the shortcut "
                f'command from the <a href="{GITHUB_URL}" title="{GITHUB_URL}">GitHub page</a>.')
MODIFIER_KEYS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
                 "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift", "Caps_Lock", "Num_Lock"}


def rgba_to_hex(rgba):
    return "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))


def system_font_family():
    name = Gtk.Settings.get_default().get_property("gtk-font-name") or "Sans"
    return Pango.FontDescription.from_string(name).get_family() or "Sans"


def build_settings_css(c):
    """Dark glass look that matches the widget; uses the widget's accent colors."""
    a, b = c["accent_start"], c["accent_end"]
    on = icon_color_on(a, b)
    t = "#f4f6fb"
    return f"""
.sw-settings, .sw-settings.background {{ background-color: #10141c; background-image: none; color: {t}; }}
.sw-settings label {{ color: {rgba(t, 0.85)}; }}
.sw-settings label.dim-label {{ color: {rgba(t, 0.50)}; font-size: 11px; }}

.sw-settings notebook, .sw-settings notebook > stack,
.sw-settings scrolledwindow, .sw-settings viewport {{ background: transparent; border: none; }}
.sw-settings notebook > header {{ background: transparent; border: none; box-shadow: none; padding: 10px 12px 0 12px; }}
.sw-settings notebook > header > tabs > tab {{
    background: transparent; border: none; box-shadow: none; border-radius: 14px;
    padding: 6px 16px; margin: 0 2px; min-height: 0; color: {rgba(t, 0.55)};
}}
.sw-settings notebook > header > tabs > tab:hover {{ color: {rgba(t, 0.85)}; }}
.sw-settings notebook > header > tabs > tab:checked {{ background: {rgba(t, 0.10)}; color: {a}; }}
.sw-settings tab label, .sw-settings button label {{ color: inherit; }}
.sw-settings tab label {{ font-weight: 600; }}

.sw-settings label.wayland-note {{
    background-color: rgba(245, 196, 81, 0.14); border: 1px solid rgba(245, 196, 81, 0.45);
    border-radius: 12px; padding: 8px 12px; color: #ffe08a; font-size: 12px;
}}
.sw-settings label.wayland-note link {{ color: #ffd166; font-weight: 700; }}
.sw-settings label.coffee link {{ color: {a}; font-weight: 600; }}

.sw-settings button {{
    background-image: none; background-color: {rgba(t, 0.07)}; border: 1px solid {rgba(t, 0.10)};
    box-shadow: none; text-shadow: none; color: {rgba(t, 0.92)};
    border-radius: 12px; padding: 5px 12px; min-height: 0; transition: all 150ms ease;
}}
.sw-settings button:hover {{ background-color: {rgba(t, 0.14)}; }}
.sw-settings button:active {{ background-color: {rgba(t, 0.20)}; }}
.sw-settings button.color {{ padding: 3px; }}
.sw-settings button.suggested-action {{
    background-image: linear-gradient(135deg, {a}, {b}); border: none; color: {on}; font-weight: 700;
}}
.sw-settings button.suggested-action:hover {{ opacity: 0.9; }}

.sw-settings entry, .sw-settings spinbutton {{
    background-color: {rgba(t, 0.06)}; background-image: none; border: 1px solid {rgba(t, 0.10)};
    border-radius: 10px; box-shadow: none; color: {t}; min-height: 28px;
}}
.sw-settings entry:focus, .sw-settings spinbutton:focus {{ border-color: {a}; }}
.sw-settings spinbutton button {{ background: none; border: none; border-radius: 8px; padding: 0 6px; }}

.sw-settings scale trough {{ min-height: 4px; border: none; border-radius: 4px; background: {rgba(t, 0.18)}; }}
.sw-settings scale highlight {{
    min-height: 4px; border: none; border-radius: 4px;
    background-image: linear-gradient(to right, {a}, {b});
}}
.sw-settings scale slider {{
    min-width: 14px; min-height: 14px; margin: -6px; border: none; border-radius: 50%;
    background: {t}; box-shadow: 0 1px 6px rgba(0, 0, 0, 0.45);
}}

.sw-settings switch {{
    background-color: {rgba(t, 0.14)}; background-image: none; border: none; border-radius: 14px;
    box-shadow: none; min-height: 26px; min-width: 48px;
}}
.sw-settings switch:checked {{ background-image: linear-gradient(135deg, {a}, {b}); }}
.sw-settings switch slider {{
    background: #ffffff; background-image: none; border: none; border-radius: 50%;
    min-width: 22px; min-height: 22px; margin: 2px; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
}}
"""


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Spotify Widget Settings")
        self.app = app
        self._syncing = False       # True while we push stored values into the controls
        self._syncers = []          # one callable per control: cfg -> control
        self.capturing = False      # True while waiting for the user to press a new shortcut
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class("sw-settings")   # all our CSS is scoped to this class
        self.set_default_size(480, 600)
        self.set_position(Gtk.WindowPosition.CENTER)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        notebook = Gtk.Notebook()
        outer.pack_start(notebook, True, True, 0)
        for title, build in (("Appearance", self._appearance_page),
                             ("Layout", self._layout_page),
                             ("Behavior", self._behavior_page)):
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.add(build())
            notebook.append_page(scroller, Gtk.Label(label=title))

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_border_width(12)
        reset_btn = Gtk.Button(label="Reset to defaults")
        reset_btn.connect("clicked", self.on_reset)
        quit_btn = Gtk.Button(label="Quit widget")
        quit_btn.connect("clicked", lambda *_: self.app.quit())
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda *_: self.destroy())
        close_btn.get_style_context().add_class("suggested-action")
        coffee = Gtk.Label()
        coffee.set_markup(f'<a href="{COFFEE_URL}" title="{COFFEE_URL}">Buy me a coffee</a>')
        coffee.get_style_context().add_class("coffee")
        bar.pack_start(reset_btn, False, False, 0)
        bar.pack_start(quit_btn, False, False, 0)
        bar.pack_end(close_btn, False, False, 0)
        bar.pack_end(coffee, False, False, 8)
        outer.pack_start(bar, False, False, 0)

        self.connect("key-press-event", self.on_key_press)
        self.connect("notify::is-active", self.on_active_changed)
        self.connect("destroy", self.on_destroyed)
        self.sync()
        self.show_all()

    # ------------------------------------------------------------------ pages
    def _page(self, entries):
        """entries: (label, widget[, tooltip]) rows; label None = widget spans both columns."""
        grid = Gtk.Grid(column_spacing=16, row_spacing=10, border_width=18)
        for row, entry in enumerate(entries):
            text, widget = entry[0], entry[1]
            tip = entry[2] if len(entry) > 2 else None
            if text is None:
                grid.attach(widget, 0, row, 2, 1)
                continue
            label = Gtk.Label(label=text, xalign=0, hexpand=True)
            widget.set_halign(Gtk.Align.END)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            if tip:
                label.set_tooltip_text(tip)
                widget.set_tooltip_text(tip)
        return grid

    def _appearance_page(self):
        return self._page([
            ("Card color", self._color("card_color")),
            ("Card opacity", self._opacity("card_opacity"), "0% = clear glass, 100% = solid"),
            ("Border color", self._color("border_color")),
            ("Border opacity", self._opacity("border_opacity")),
            ("Border width (px)", self._spin("border_width")),
            ("Card corner radius (px)", self._spin("card_radius")),
            ("Album art corner radius (px)", self._spin("art_radius")),
            ("Text color", self._color("text_color")),
            ("Accent color (start)", self._color("accent_start"),
             "Sliders and the play button use a gradient from start to end"),
            ("Accent color (end)", self._color("accent_end")),
            ("Match accent to album art", self._switch("adapt_to_art"),
             "Tint the controls with each cover's color. The accent colors above are the fallback."),
            ("Font", self._font_row()),
            ("Title size (px)", self._spin("title_size")),
            ("Artist size (px)", self._spin("artist_size")),
        ])

    def _layout_page(self):
        display = Gdk.Display.get_default()
        count = display.get_n_monitors() if display else 1
        monitors = [("-1", "Primary monitor")] + [(str(i), f"Monitor {i + 1}") for i in range(count)]
        current = self.app.cfg["monitor"]
        if current >= count:
            monitors.append((str(current), f"Monitor {current + 1} (not connected)"))

        self.spin_x = self._spin("pos_x", 10)
        self.spin_y = self._spin("pos_y", 10)
        self.spin_margin = self._spin("margin", 2)
        use_now = Gtk.Button(label="Use the card's current position")
        use_now.connect("clicked", self.on_use_current_position)

        return self._page([
            ("Card width (px)", self._spin("width", 10)),
            ("Card height (px)", self._spin("height", 5)),
            ("Show album art", self._switch("show_art")),
            ("Album art size (px)", self._spin("art_size", 4)),
            ("Show time labels", self._switch("show_time")),
            ("Show volume slider", self._switch("show_volume")),
            ("Position", self._combo("position_mode", POSITION_OPTIONS)),
            ("Monitor", self._combo("monitor", monitors, int)),
            ("Distance from screen edge (px)", self.spin_margin, "Used by the corner positions"),
            ("X position", self.spin_x),
            ("Y position", self.spin_y),
            (None, use_now),
        ])

    def _behavior_page(self):
        return self._page([
            ("Player", self._entry("player"),
             "The playerctl player name. Run `playerctl -l` to list them (spotify, spotifyd, vlc, ...)"),
            ("Global shortcut", self._hotkey_row(), "Show / hide the card from anywhere"),
            (None, self.hotkey_note),
            *([(None, self.wayland_note)] if WAYLAND else []),
            ("Window layer", self._combo("layer", LAYER_OPTIONS),
             "'Below other windows' can block clicks if your desktop has an icon layer"),
            ("Start visible at login", self._switch("start_visible"),
             "Off = start hidden and wait for your toggle shortcut"),
            ("Take keyboard focus when shown", self._switch("grab_focus"),
             "Off = popping the card up never steals focus from what you're typing in"),
            ("Refresh interval (ms)", self._spin("poll_ms", 50), "Lower = smoother time bar, more CPU"),
        ])

    # --------------------------------------------------------------- controls
    def _push(self, key, value):
        if self._syncing:
            return
        self.app.update_config({key: value})
        self.update_sensitivity()
        if key in ("accent_start", "accent_end"):
            self.refresh_style()

    def _switch(self, key):
        w = Gtk.Switch()
        w.set_valign(Gtk.Align.CENTER)
        w.connect("notify::active", lambda sw, _p: self._push(key, sw.get_active()))
        self._syncers.append(lambda: w.set_active(self.app.cfg[key]))
        return w

    def _spin(self, key, step=1):
        lo, hi = RANGES[key]
        w = Gtk.SpinButton.new_with_range(lo, hi, step)
        w.set_numeric(True)
        w.connect("value-changed", lambda sp: self._push(key, sp.get_value_as_int()))
        self._syncers.append(lambda: w.set_value(self.app.cfg[key]))
        return w

    def _opacity(self, key):
        w = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        w.set_draw_value(True)
        w.set_value_pos(Gtk.PositionType.RIGHT)
        w.set_size_request(180, -1)
        w.connect("format-value", lambda _s, v: f"{int(v)}%")
        w.connect("value-changed", lambda s: self._push(key, s.get_value() / 100))
        self._syncers.append(lambda: w.set_value(self.app.cfg[key] * 100))
        return w

    def _color(self, key):
        w = Gtk.ColorButton()
        w.set_use_alpha(False)
        w.connect("color-set", lambda b: self._push(key, rgba_to_hex(b.get_rgba())))

        def sync():
            rgba = Gdk.RGBA()
            rgba.parse(self.app.cfg[key])
            w.set_rgba(rgba)
        self._syncers.append(sync)
        return w

    def _combo(self, key, options, cast=str):
        w = Gtk.ComboBoxText()
        for ident, label in options:
            w.append(ident, label)

        def on_changed(combo):
            ident = combo.get_active_id()
            if ident is not None:
                self._push(key, cast(ident))
        w.connect("changed", on_changed)
        self._syncers.append(lambda: w.set_active_id(str(self.app.cfg[key])))
        return w

    def _entry(self, key):
        w = Gtk.Entry()
        w.set_width_chars(16)

        def commit(*_):
            self._push(key, w.get_text().strip())
            if not w.get_text().strip():            # empty falls back to the default; show it
                w.set_text(self.app.cfg[key])

        def on_focus_out(*_):
            commit()
            return False
        w.connect("activate", commit)
        w.connect("focus-out-event", on_focus_out)
        self._syncers.append(lambda: w.set_text(self.app.cfg[key]))
        return w

    def _font_row(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        font_btn = Gtk.FontButton()
        font_btn.set_show_size(False)
        font_btn.set_show_style(False)
        font_btn.set_use_font(True)
        font_btn.set_title("Choose a font")

        def on_font_set(btn):
            family = Pango.FontDescription.from_string(btn.get_font()).get_family()
            self._push("font_family", family or "")

        def on_default(_b):
            self.app.update_config({"font_family": ""})
            self.sync()
        font_btn.connect("font-set", on_font_set)
        default_btn = Gtk.Button(label="Default")
        default_btn.set_tooltip_text("Use the system font")
        default_btn.connect("clicked", on_default)
        box.pack_start(font_btn, False, False, 0)
        box.pack_start(default_btn, False, False, 0)
        self._syncers.append(lambda: font_btn.set_font(self.app.cfg["font_family"] or system_font_family()))
        return box

    # ---------------------------------------------------------- global shortcut
    def _hotkey_row(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.hotkey_btn = Gtk.Button()
        self.hotkey_btn.set_size_request(170, -1)
        self.hotkey_btn.connect("clicked", self.on_hotkey_click)
        clear = Gtk.Button(label="Clear")
        clear.connect("clicked", lambda *_: self.end_capture(""))
        box.pack_start(self.hotkey_btn, False, False, 0)
        box.pack_start(clear, False, False, 0)
        self.hotkey_note = Gtk.Label(xalign=0, hexpand=True)
        self.hotkey_note.set_line_wrap(True)
        self.hotkey_note.set_max_width_chars(46)
        self.hotkey_note.get_style_context().add_class("dim-label")
        self.wayland_note = Gtk.Label(xalign=0, hexpand=True)     # bright callout, Wayland only
        self.wayland_note.set_line_wrap(True)
        self.wayland_note.set_max_width_chars(46)
        self.wayland_note.set_markup(WAYLAND_NOTE)
        self.wayland_note.get_style_context().add_class("wayland-note")
        self._syncers.append(self.refresh_hotkey_ui)
        return box

    @staticmethod
    def pretty_hotkey(accel):
        try:
            keyval, mods = Gtk.accelerator_parse(accel)
            return Gtk.accelerator_get_label(keyval, mods) or accel
        except Exception:
            return accel

    def refresh_hotkey_ui(self):
        if self.capturing:
            return
        key = self.app.cfg["hotkey"]
        self.hotkey_btn.set_label(self.pretty_hotkey(key) if key else "Click to set\u2026")
        status = self.app.hotkey_status
        if status == "off":
            text = "No shortcut set. A shortcut you made in your desktop's settings still works."
        elif status == "missing":
            text = ("Needs keybinder: sudo apt install gir1.2-keybinder-3.0, then restart the widget "
                    "(spotify-widget.py quit, then start it again).")
        elif status == "failed":
            text = ("Couldn't register this shortcut. Another app or your desktop probably already "
                    "uses it. Try a different combination.")
        else:
            text = "Active."
        self.hotkey_note.set_text(text)

    def on_hotkey_click(self, _b):
        self.capturing = True
        self.app.suspend_hotkey()          # so pressing the current combo is captured, not acted on
        self.hotkey_btn.set_label("Press a shortcut\u2026")
        self.hotkey_note.set_text("Esc cancels, Backspace clears. Use Ctrl, Alt or Super with a key "
                                  "(F-keys work on their own).")

    def end_capture(self, value=None):
        """Stop listening; value = new accelerator, "" to clear, None to keep the old one."""
        self.capturing = False
        if value is not None:
            self.app.update_config({"hotkey": value})
        self.app.apply_hotkey()
        self.sync()

    def on_key_press(self, _w, event):
        if not self.capturing:
            return False
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        if (Gdk.keyval_name(event.keyval) or "") in MODIFIER_KEYS:
            return True                    # still holding modifiers; wait for the real key
        if not mods and event.keyval == Gdk.KEY_Escape:
            self.end_capture(None)
            return True
        if not mods and event.keyval == Gdk.KEY_BackSpace:
            self.end_capture("")
            return True
        keyval = Gdk.keyval_to_lower(event.keyval)
        try:                               # the key without Shift applied (Shift+1 -> 1, not "!")
            keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
            ok, base, _g, _l, _c = keymap.translate_keyboard_state(
                event.hardware_keycode, Gdk.ModifierType(0), event.group)
            if ok and base:
                keyval = base
        except Exception:
            pass
        strong = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK
                  | Gdk.ModifierType.HYPER_MASK | Gdk.ModifierType.META_MASK)
        if not (mods & strong) and not (Gdk.KEY_F1 <= keyval <= Gdk.KEY_F24):
            self.hotkey_btn.set_label("Add Ctrl, Alt or Super")
            return True
        self.end_capture(Gtk.accelerator_name(keyval, mods))
        return True

    def on_active_changed(self, *_):
        if self.capturing and not self.is_active():
            self.end_capture(None)         # clicked away: cancel

    def on_destroyed(self, *_):
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), self.css)
        if self.capturing:
            self.capturing = False
            self.app.apply_hotkey()

    # ---------------------------------------------------------------- actions
    def sync(self):
        """Push the stored settings into every control without triggering updates."""
        self._syncing = True
        try:
            for fn in self._syncers:
                fn()
        finally:
            self._syncing = False
        self.update_sensitivity()
        self.refresh_style()

    def refresh_style(self):
        try:
            self.css.load_from_data(build_settings_css(self.app.cfg).encode())
        except GLib.Error as e:
            print(f"spotify-widget: settings CSS error: {e.message}")

    def update_sensitivity(self):
        mode = self.app.cfg["position_mode"]
        self.spin_x.set_sensitive(mode == "fixed")
        self.spin_y.set_sensitive(mode == "fixed")
        self.spin_margin.set_sensitive(mode not in ("fixed", "center"))

    def on_use_current_position(self, _b):
        x, y = self.app.current_position()
        self.app.update_config({"position_mode": "fixed", "pos_x": x, "pos_y": y})
        self.sync()

    def on_reset(self, _b):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.YES_NO,
                                text="Reset all settings to their defaults?")
        dlg.get_style_context().add_class("sw-settings")
        answer = dlg.run()
        dlg.destroy()
        if answer == Gtk.ResponseType.YES:
            self.app.reset_config()
            self.sync()
