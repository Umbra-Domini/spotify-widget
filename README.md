# Spotify Widget

A small translucent glass card for your Linux desktop that shows what Spotify is playing. It has album art, title and artist, previous / play-pause / next, a seek bar and a volume slider. Show or hide it with a keyboard shortcut.

<p align="center">
  <img src="https://github.com/user-attachments/assets/321f421c-dab8-47ac-b0fd-b66e6621a393" alt="Spotify Widget" width="578">
</p>

<p align="center">
  <a href="https://www.buymeacoffee.com/UmbraDomini"><img src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-FFDD00?logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee"></a>
</p>

## Features

- Glass card with album art, track info, seek bar and volume
- Optional accent color taken from the album cover
- Settings window with live preview: colors, opacity, corner radius, font, size, position, monitor
- Works with any player that `playerctl` can see, not just Spotify
- Show / hide with one keyboard shortcut (Ctrl+Alt+S by default after setup)
- Pick a corner, or set Position to Fixed and drag the card anywhere: it remembers the spot
- Does no work while hidden

## Install

```bash
git clone https://github.com/Umbra-Domini/spotify-widget.git
cd spotify-widget
bash install/setup.sh
```

The setup script installs the dependencies (apt, dnf and pacman are supported), sets **Ctrl+Alt+S** as the show / hide shortcut, and starts the widget hidden. Press the shortcut to see it.

Options: `--no-deps` skips the package install, `--no-shortcut` skips the shortcut.

If you'd rather do it by hand, you need Python 3, PyGObject with GTK 3, and `playerctl`. For the built-in shortcut you also need keybinder:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 playerctl gir1.2-keybinder-3.0
```

## Usage

```bash
python3 spotify-widget.py            # start (hidden until you press the shortcut)
python3 spotify-widget.py toggle     # show / hide
python3 spotify-widget.py settings   # open the settings window
python3 spotify-widget.py quit       # stop the widget
```

You can also right-click the card, or hover it and click the gear icon, to open settings.

## Settings

Open the settings window with the gear icon on the card, the right-click menu, or `python3 spotify-widget.py settings`. Every change shows on the card straight away and saves automatically to `~/.config/spotify-widget/config.json`.

The buttons at the bottom of the window: **Reset to defaults** puts everything back (it asks first), **Quit widget** stops the widget, and **Close** closes the window.

### Appearance

<p align="center">
  <img src="https://github.com/user-attachments/assets/6feea8ee-21ec-4618-a80b-82962f76d1db" alt="Appearance settings" width="380">
</p>

| Setting | What it does |
| --- | --- |
| Card color | Background color of the card |
| Card opacity | 0% is clear glass, 100% is solid |
| Border color / opacity / width | The thin outline around the card. Set the width to 0 for no border |
| Card corner radius | How round the card corners are |
| Album art corner radius | How round the album cover corners are |
| Text color | Color for the title, artist and time labels |
| Accent color (start / end) | The gradient used by the sliders and the play button |
| Match accent to album art | Tints the controls with each cover's color. The accent colors above are the fallback for gray covers |
| Font | Pick a font, or click Default for the system font |
| Title size / Artist size | Text sizes in pixels |

### Layout

<p align="center">
  <img src="https://github.com/user-attachments/assets/ce2b54ab-549b-4027-8f0b-767e3c0831a1" alt="Layout settings" width="380">
</p>

| Setting | What it does |
| --- | --- |
| Card width / height | Size of the card in pixels |
| Show album art | Turn the cover on or off |
| Album art size | Size of the cover in pixels |
| Show time labels | The elapsed and total time next to the seek bar |
| Show volume slider | The volume icon and slider |
| Position | Fixed coordinates, one of the four corners, or Center (the default) |
| Monitor | Primary monitor, or pick a specific one |
| Distance from screen edge | Gap to the screen edge. Only used by the corner positions |
| X position / Y position | Only used by Fixed. Dragging the card in Fixed mode updates these |
| Use the card's current position | Switches to Fixed and saves where the card is right now |

### Behavior

<p align="center">
  <img src="https://github.com/user-attachments/assets/f96f3a5b-9adf-4668-8f14-2aff2bf6dac6" alt="Behavior settings" width="380">
</p>

| Setting | What it does |
| --- | --- |
| Player | The `playerctl` name of the player to show. Run `playerctl -l` to list them (spotify, spotifyd, vlc, ...) |
| Global shortcut | Click it, then press a key combo (use Ctrl, Alt or Super, or an F-key). Esc cancels, Backspace clears. See [Shortcuts on Wayland](#shortcuts-on-wayland) |
| Window layer | Normal, Always on top, or Below other windows. Below can block clicks if your desktop has an icon layer |
| Start visible at login | On shows the card as soon as the widget starts. Off keeps it hidden until you use the shortcut |
| Take keyboard focus when shown | Off means the card never steals focus from what you're typing in |
| Refresh interval (ms) | How often the card updates. Lower is a smoother time bar but uses more CPU |

To start the widget when you log in, add `python3 /full/path/to/spotify-widget.py` to your desktop's startup applications.

## Shortcuts on Wayland

On X11 the built-in shortcut (Settings > Behavior > Global shortcut) works from anywhere.

On Wayland it only works while an X11 window has focus, so you need a shortcut from your desktop instead. On GNOME, `bash install/setup.sh` sets this up for you. On other desktops, add a custom shortcut in your keyboard settings with this command (use the real path to the file):

```bash
python3 /full/path/to/spotify-widget.py toggle
```

- **KDE Plasma:** System Settings > Shortcuts > Add Command
- **XFCE:** Settings > Keyboard > Application Shortcuts
- **Others:** look for "custom shortcuts" in your keyboard settings

The command also starts the widget if it isn't running.

## Troubleshooting

- **"Spotify isn't running":** start the player, or check the name with `playerctl -l`.
- **"playerctl isn't installed":** `sudo apt install playerctl`.
- **Shortcut does nothing:** see [Shortcuts on Wayland](#shortcuts-on-wayland). If the settings window says the shortcut couldn't be registered, another app already uses that combination.
- **Run it in a terminal** (`python3 spotify-widget.py`) to see any errors.

## Files

| File | What it does |
| --- | --- |
| `spotify-widget.py` | The widget itself |
| `sw_config.py` | Defaults, validation, loading and saving settings |
| `sw_style.py` | Builds the CSS from your settings |
| `sw_settings.py` | The settings window |
| `install/setup.sh` | Installs dependencies and sets the shortcut |

Keep the four `.py` files in the same folder.

## Support

If you like the widget and want to say thanks, you can [buy me a coffee](https://www.buymeacoffee.com/YOUR_USERNAME). It's never expected, and it's appreciated.

## License

MIT, see [LICENSE](LICENSE).
