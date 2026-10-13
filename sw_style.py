"""CSS generation for spotify-widget.

Every selector is scoped under .sw-root (a class on the widget's window), because the CSS is
registered screen-wide and would otherwise restyle the settings window and any popup menus too.
"""
import colorsys


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h, alpha):
    r, g, b = hex_rgb(h)
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def hexcol(r, g, b):
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _luminance(h):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in hex_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def icon_color_on(a, b):
    """Dark or light icon colour, whichever reads better on the accent gradient."""
    return "#0b0f14" if (_luminance(a) + _luminance(b)) / 2 > 0.179 else "#ffffff"


def accent_from_pixbuf(pb):
    """Pick a punchy accent pair from the average colour of the album cover.

    Returns (start, end) hex strings, or None for greyscale covers (caller keeps its own accent).
    """
    from gi.repository import GdkPixbuf
    px = pb.scale_simple(1, 1, GdkPixbuf.InterpType.HYPER).get_pixels()
    h, s, v = colorsys.rgb_to_hsv(px[0] / 255, px[1] / 255, px[2] / 255)
    if s < 0.15:
        return None
    a = colorsys.hsv_to_rgb(h, max(s, 0.55), max(v, 0.92))
    b = colorsys.hsv_to_rgb((h + 0.05) % 1.0, max(s * 0.55, 0.30), 1.0)
    return hexcol(*a), hexcol(*b)


def build_css(c, accent):
    """c = settings dict, accent = (start_hex, end_hex)."""
    a, b = accent
    t = c["text_color"]
    on_accent = icon_color_on(a, b)
    font = f'font-family: "{c["font_family"]}";' if c["font_family"] else ""
    return f"""
.sw-root, .sw-root.background {{ background: transparent; background-image: none; }}

.sw-root #card {{
    background-color: {rgba(c["card_color"], c["card_opacity"])};
    background-image: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.01) 60%);
    border-radius: {c["card_radius"]}px;
    border: {c["border_width"]}px solid {rgba(c["border_color"], c["border_opacity"])};
    padding: 16px;
}}

.sw-root #title  {{ color: {t}; font-weight: 800; font-size: {c["title_size"]}px; {font} }}
.sw-root #artist {{ color: {rgba(t, 0.70)}; font-size: {c["artist_size"]}px; {font} }}
.sw-root #time   {{ color: {rgba(t, 0.60)}; font-size: 10px; font-family: monospace; }}
.sw-root #title, .sw-root #artist, .sw-root #time {{ text-shadow: 0 1px 8px rgba(0, 0, 0, 0.55); }}

/* sliders (seek + volume) */
.sw-root scale trough {{
    min-height: 4px; border: none; border-radius: 4px;
    background: {rgba(t, 0.18)};
}}
.sw-root scale highlight {{
    min-height: 4px; border: none; border-radius: 4px;
    background-image: linear-gradient(to right, {a}, {b});
}}
.sw-root scale slider {{
    min-width: 12px; min-height: 12px; margin: -5px;
    border: none; border-radius: 50%;
    background: {t}; box-shadow: 0 1px 8px rgba(0, 0, 0, 0.45);
    opacity: 0; transition: opacity 150ms ease;
}}
.sw-root scale:hover slider {{ opacity: 1; }}

/* buttons */
.sw-root button {{
    background: none; border: none; box-shadow: none; outline: none;
    color: {rgba(t, 0.92)}; padding: 4px 8px; border-radius: 14px;
    transition: all 150ms ease;
}}
.sw-root button:hover  {{ background: {rgba(t, 0.12)}; color: {a}; }}
.sw-root button:active {{ background: {rgba(t, 0.20)}; }}

.sw-root #play {{
    min-width: 40px; min-height: 40px; padding: 0; border-radius: 20px;
    background-image: linear-gradient(135deg, {a}, {b});
    color: {on_accent}; box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}}
.sw-root #play:hover {{ color: {on_accent}; background-color: transparent; }}
.sw-root #play:active {{ opacity: 0.85; }}

.sw-root #volicon {{ color: {rgba(t, 0.75)}; }}

/* close + settings buttons: invisible until the pointer is over the card */
.sw-root #close, .sw-root #gear {{
    min-width: 22px; min-height: 22px; padding: 0; border-radius: 11px;
    background: {rgba(t, 0.10)}; color: {rgba(t, 0.85)};
    opacity: 0; transition: opacity 180ms ease, background 150ms ease;
}}
.sw-root.hovering #close, .sw-root.hovering #gear {{ opacity: 1; }}
.sw-root #close:hover {{ background: rgba(255, 95, 95, 0.85); color: #ffffff; }}
.sw-root #gear:hover  {{ background: {rgba(t, 0.22)}; }}
"""
