#!/usr/bin/env python3
"""AORUS RGB keyboard controller and reactive lighting daemon (Aorus 17X, USB 0414:8007).

Drives the backlight, the per-key colors and the keypress flash, resolving the
`inherit` chain (keyboard -> custom key -> flash) on every config reload. Also
serves as the library behind the `aorus-rgb` CLI. See AGENTS.md for the USB
protocol and the inheritance rules.
"""

import os
import re
import sys
import time
import json
import glob
import copy
import socket
import select
import fcntl
import signal
import subprocess
import unicodedata
from collections import namedtuple

import hid
import evdev

CONFIG_DIR = os.path.expanduser("~/.config/aorus-rgb")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PID_FILE = os.path.join(CONFIG_DIR, "daemon.pid")
PRESETS_DIR = os.path.join(CONFIG_DIR, "presets")
# Omarchy theme, newest layout first. `keyboard.rgb` is the hue the theme picks
# for the backlight itself, so it wins over the generic accent color.
OMARCHY_THEME_DIRS = [os.path.expanduser("~/.local/state/omarchy/current/theme"),
                      os.path.expanduser("~/.config/omarchy/current/theme")]
OMARCHY_THEME_FILES = ("keyboard.rgb", "colors.toml")
SERVICE = "aorus-rgb.service"

# 101 keys layout mapping (evdev keyname -> Aorus LED position 0..127)
EVDEV_TO_LED = {
    # Function row
    "KEY_ESC": 11, "KEY_F1": 17, "KEY_F2": 23, "KEY_F3": 29,
    "KEY_F4": 35, "KEY_F5": 41, "KEY_F6": 47, "KEY_F7": 53,
    "KEY_F8": 59, "KEY_F9": 65, "KEY_F10": 71, "KEY_F11": 77,
    "KEY_F12": 83, "KEY_PAUSE": 89, "KEY_DELETE": 95, "KEY_HOME": 101,
    "KEY_PAGEUP": 107, "KEY_PAGEDOWN": 113, "KEY_END": 119,

    # Number row
    "KEY_GRAVE": 10, "KEY_1": 16, "KEY_2": 22, "KEY_3": 28,
    "KEY_4": 34, "KEY_5": 40, "KEY_6": 46, "KEY_7": 52,
    "KEY_8": 58, "KEY_9": 64, "KEY_0": 70, "KEY_MINUS": 76,
    "KEY_EQUAL": 82, "KEY_BACKSPACE": 94, "KEY_NUMLOCK": 100,
    "KEY_KPSLASH": 106, "KEY_KPASTERISK": 112, "KEY_KPMINUS": 118,

    # QWERTY / Tab row
    "KEY_TAB": 9, "KEY_Q": 15, "KEY_W": 21, "KEY_E": 27,
    "KEY_R": 33, "KEY_T": 39, "KEY_Y": 45, "KEY_U": 51,
    "KEY_I": 57, "KEY_O": 63, "KEY_P": 69, "KEY_LEFTBRACE": 75,
    "KEY_RIGHTBRACE": 81, "KEY_BACKSLASH": 87, "KEY_KP7": 99,
    "KEY_KP8": 105, "KEY_KP9": 111, "KEY_KPPLUS": 116,

    # Home row / Caps
    "KEY_CAPSLOCK": 8, "KEY_A": 14, "KEY_S": 20, "KEY_D": 26,
    "KEY_F": 32, "KEY_G": 38, "KEY_H": 44, "KEY_J": 50,
    "KEY_K": 56, "KEY_L": 62, "KEY_SEMICOLON": 68, "KEY_APOSTROPHE": 74,
    "KEY_ENTER": 92, "KEY_KP4": 98, "KEY_KP5": 104, "KEY_KP6": 110,

    # Bottom letter row / Shift
    "KEY_LEFTSHIFT": 7, "KEY_102ND": 13, "KEY_Z": 19, "KEY_X": 25,
    "KEY_C": 31, "KEY_V": 37, "KEY_B": 43, "KEY_N": 49,
    "KEY_M": 55, "KEY_COMMA": 61, "KEY_DOT": 67, "KEY_SLASH": 73,
    "KEY_RIGHTSHIFT": 85, "KEY_UP": 91, "KEY_KP1": 97, "KEY_KP2": 103,
    "KEY_KP3": 109, "KEY_KPENTER": 114,

    # Space row / Modifiers
    "KEY_LEFTCTRL": 6, "KEY_FN": 12, "KEY_LEFTMETA": 18, "KEY_LEFTALT": 24,
    "KEY_SPACE": 42, "KEY_RIGHTALT": 60, "KEY_COMPOSE": 66, "KEY_MENU": 66,
    "KEY_RIGHTCTRL": 72, "KEY_LEFT": 84, "KEY_DOWN": 90, "KEY_RIGHT": 96,
    "KEY_KP0": 102, "KEY_KPDOT": 108
}

VALID_POSITIONS = sorted(set(EVDEV_TO_LED.values()))

# Human-friendly French & English key name aliases (normalized without accents)
KEY_ALIASES = {
    # Modifiers & System
    "esc": ["KEY_ESC"], "echap": ["KEY_ESC"], "escape": ["KEY_ESC"],
    "super": ["KEY_LEFTMETA"], "win": ["KEY_LEFTMETA"], "windows": ["KEY_LEFTMETA"], "meta": ["KEY_LEFTMETA"], "cmd": ["KEY_LEFTMETA"],
    "ctrl": ["KEY_LEFTCTRL", "KEY_RIGHTCTRL"], "control": ["KEY_LEFTCTRL", "KEY_RIGHTCTRL"],
    "lctrl": ["KEY_LEFTCTRL"], "rctrl": ["KEY_RIGHTCTRL"],
    "ctrl_gauche": ["KEY_LEFTCTRL"], "ctrl_droit": ["KEY_RIGHTCTRL"],
    "alt": ["KEY_LEFTALT", "KEY_RIGHTALT"], "lalt": ["KEY_LEFTALT"], "ralt": ["KEY_RIGHTALT"], "altgr": ["KEY_RIGHTALT"],
    "alt_gauche": ["KEY_LEFTALT"], "alt_droit": ["KEY_RIGHTALT"],
    "shift": ["KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"], "maj": ["KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"],
    "lshift": ["KEY_LEFTSHIFT"], "rshift": ["KEY_RIGHTSHIFT"],
    "shift_gauche": ["KEY_LEFTSHIFT"], "shift_droit": ["KEY_RIGHTSHIFT"],
    "enter": ["KEY_ENTER"], "entree": ["KEY_ENTER"], "return": ["KEY_ENTER"],
    "kpenter": ["KEY_KPENTER"], "kp_enter": ["KEY_KPENTER"],
    "backspace": ["KEY_BACKSPACE"], "retour": ["KEY_BACKSPACE"], "bksp": ["KEY_BACKSPACE"], "effacer": ["KEY_BACKSPACE"], "retour_arriere": ["KEY_BACKSPACE"],
    "del": ["KEY_DELETE"], "delete": ["KEY_DELETE"], "suppr": ["KEY_DELETE"], "suppre": ["KEY_DELETE"], "supprime": ["KEY_DELETE"], "supprimer": ["KEY_DELETE"],
    "space": ["KEY_SPACE"], "espace": ["KEY_SPACE"],
    "tab": ["KEY_TAB"], "tabulation": ["KEY_TAB"],
    "caps": ["KEY_CAPSLOCK"], "capslock": ["KEY_CAPSLOCK"], "verrmaj": ["KEY_CAPSLOCK"], "verr_maj": ["KEY_CAPSLOCK"],
    "fn": ["KEY_FN"],
    "compose": ["KEY_COMPOSE"], "menu": ["KEY_MENU"],
    "pause": ["KEY_PAUSE"], "arret_defil": ["KEY_PAUSE"],
    "numlock": ["KEY_NUMLOCK"], "verrnum": ["KEY_NUMLOCK"], "verr_num": ["KEY_NUMLOCK"],

    # Navigation
    "home": ["KEY_HOME"], "debut": ["KEY_HOME"],
    "end": ["KEY_END"], "fin": ["KEY_END"],
    "pageup": ["KEY_PAGEUP"], "pgup": ["KEY_PAGEUP"], "page_up": ["KEY_PAGEUP"],
    "pagedown": ["KEY_PAGEDOWN"], "pgdown": ["KEY_PAGEDOWN"], "pgdn": ["KEY_PAGEDOWN"], "page_down": ["KEY_PAGEDOWN"],

    # Direction arrows
    "up": ["KEY_UP"], "haut": ["KEY_UP"], "fleche_haut": ["KEY_UP"],
    "down": ["KEY_DOWN"], "bas": ["KEY_DOWN"], "fleche_bas": ["KEY_DOWN"],
    "left": ["KEY_LEFT"], "gauche": ["KEY_LEFT"], "fleche_gauche": ["KEY_LEFT"],
    "right": ["KEY_RIGHT"], "droite": ["KEY_RIGHT"], "fleche_droite": ["KEY_RIGHT"],
    "arrows": ["KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"],
    "fleches": ["KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"],
    "fleche": ["KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"],
    "directionnelles": ["KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"],

    # ISO 102nd key (< >)
    "102nd": ["KEY_102ND"], "<": ["KEY_102ND"], ">": ["KEY_102ND"], "chevrons": ["KEY_102ND"],

    # Groups
    "wasd": ["KEY_W", "KEY_A", "KEY_S", "KEY_D"],
    "zqsd": ["KEY_Z", "KEY_Q", "KEY_S", "KEY_D"],
    "fkeys": [f"KEY_F{i}" for i in range(1, 13)],
    "fonctions": [f"KEY_F{i}" for i in range(1, 13)],
    "modifiers": ["KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_LEFTMETA"],
    "nav": ["KEY_HOME", "KEY_END", "KEY_PAGEUP", "KEY_PAGEDOWN", "KEY_DELETE", "KEY_BACKSPACE"],
    "numpad": [
        "KEY_NUMLOCK", "KEY_KPSLASH", "KEY_KPASTERISK", "KEY_KPMINUS", "KEY_KPPLUS", "KEY_KPENTER", "KEY_KPDOT",
        "KEY_KP0", "KEY_KP1", "KEY_KP2", "KEY_KP3", "KEY_KP4", "KEY_KP5", "KEY_KP6", "KEY_KP7", "KEY_KP8", "KEY_KP9"
    ],
    "pavenum": [
        "KEY_NUMLOCK", "KEY_KPSLASH", "KEY_KPASTERISK", "KEY_KPMINUS", "KEY_KPPLUS", "KEY_KPENTER", "KEY_KPDOT",
        "KEY_KP0", "KEY_KP1", "KEY_KP2", "KEY_KP3", "KEY_KP4", "KEY_KP5", "KEY_KP6", "KEY_KP7", "KEY_KP8", "KEY_KP9"
    ],
    "digits": [f"KEY_{i}" for i in range(10)],
    "chiffres": [f"KEY_{i}" for i in range(10)],
    "nombres": [f"KEY_{i}" for i in range(10)],
    "lettres": [f"KEY_{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
    "all": list(EVDEV_TO_LED.keys()),
}


def _strip_accents(s):
    return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8').lower()


def resolve_keys(key_spec):
    """Resolve comma-separated string or list of key names / aliases into valid evdev keys."""
    if isinstance(key_spec, str):
        parts = [p.strip() for p in key_spec.split(",") if p.strip()]
    else:
        parts = list(key_spec)

    result = []
    for part in parts:
        low = _strip_accents(part)
        up = part.upper()
        if low in KEY_ALIASES:
            for k in KEY_ALIASES[low]:
                if k in EVDEV_TO_LED and k not in result:
                    result.append(k)
        elif up in EVDEV_TO_LED:
            if up not in result:
                result.append(up)
        elif f"KEY_{up}" in EVDEV_TO_LED and f"KEY_{up}" not in result:
            result.append(f"KEY_{up}")
    return result


DEFAULT_CONFIG = {
    "backlight": True,
    "flash": True,
    "bg_color": [0, 180, 216],
    "saved_color": [0, 180, 216],
    "brightness": 10,               # 0 to 10 scale for backlight
    "flash_brightness": 10,         # 0 to 10 scale for flash
    "flash_color": [255, 255, 255], # Flash color (white by default)
    "fade_duration": 0.45,          # Duration of flash fade in seconds
    "custom_keys": {},              # { "KEY_ESC": {"color": [255, 0, 0], "brightness": 10}, ... }
    "workspace_key": False,         # Light the digit key of the active Hyprland workspace
    "workspace_color": "inherit",   # Color of that digit, or inherit to keep the cascade's
    "workspace_brightness": 10,     # Brightness of that digit, 0 to 10
    "workspace_dark": False,        # Show it on an unlit keyboard too, at the cost of the 0% CPU mode
}


CONFIG_POLL_INTERVAL = 2.0   # seconds between config reloads (SIGUSR1 is the fast path)
IDLE_TIMEOUT = 0.5           # select() timeout when no fade is running
FADE_TIMEOUT = 0.01          # select() timeout while animating a fade
MIN_RETRIGGER_DELAY = 0.08   # ignore a key re-firing within this delay
HW_FULL_BRIGHTNESS = 50      # matrix mode drives brightness in software
SUSPEND_GAP = 5.0            # a loop iteration longer than this means we resumed from sleep
DEVICE_RETRY_DELAY = 2.0     # wait before reopening a keyboard that went away


def is_inherit(val):
    """Check if a color or brightness value is left to the inheritance chain.

    The chain runs keyboard background -> custom key -> flash: each level
    falls back to the one above it for every value left to `inherit`.
    """
    if val is None:
        return True
    if isinstance(val, str):
        v = val.lower().strip()
        # "none" is deliberately absent: it is the historical alias for black.
        return v in ("inherit", "auto", "clavier", "kbl", "null", "default", "")
    return False


def scale_color(col, brightness):
    """Attenuate an unattenuated color by a 0-10 brightness level."""
    f = max(0, min(10, brightness)) / 10.0
    return (int(col[0] * f), int(col[1] * f), int(col[2] * f))


def resolve_brightness(raw, fallback):
    """Resolve a brightness setting to the 0-10 scale, inheriting when unset."""
    if is_inherit(raw):
        return fallback
    try:
        return max(0, min(10, int(raw)))
    except (ValueError, TypeError):
        return fallback


def resolve_key_settings(cfg, raw_bg, global_b, ws_pos=None):
    """Resolve the unattenuated color and brightness of every LED position.

    First rung of the inheritance chain: a custom key falls back to the keyboard
    background color and/or brightness for each value it leaves to `inherit`.
    Brightness stays on the 0-10 scale rather than being pre-multiplied, so that
    the flash can inherit it in turn. Returns {pos: (raw_color, brightness)}.

    `ws_pos`, the active workspace digit, sits above the custom keys: like the
    flash, each of its two settings either overrides the cascade or inherits
    what the cascade resolved for that key.
    """
    raw_bg = tuple(raw_bg)
    settings = {pos: (raw_bg, global_b) for pos in VALID_POSITIONS}

    for kname, cinfo in cfg.get("custom_keys", {}).items():
        pos = EVDEV_TO_LED.get(kname)
        if pos not in settings:
            continue
        parsed = parse_color(cinfo.get("color"), default=None)
        settings[pos] = (tuple(parsed) if parsed is not None else raw_bg,
                         resolve_brightness(cinfo.get("brightness"), global_b))

    if ws_pos in settings:
        ws_color = parse_color(cfg.get("workspace_color"), default=None)
        settings[ws_pos] = (tuple(ws_color) if ws_color is not None else settings[ws_pos][0],
                            resolve_brightness(cfg.get("workspace_brightness"), 10))
    return settings


def compute_key_base_colors(key_settings, effective_bg, backlight_on=True, lit_positions=()):
    """Compute the resting color of every LED position.

    `lit_positions` stay lit even when the backlight is off: that is how the
    workspace indicator can show on an otherwise dark keyboard.
    """
    if not backlight_on:
        base = {pos: tuple(effective_bg) for pos in VALID_POSITIONS}
        base.update({pos: scale_color(*key_settings[pos])
                     for pos in lit_positions if pos in key_settings})
        return base
    return {pos: scale_color(col, bri) for pos, (col, bri) in key_settings.items()}


def workspace_led_pos(cfg, workspace):
    """LED position of the digit key naming the active workspace, if any.

    Workspaces are matched by name, so "3" lights KEY_3; "10" lights KEY_0, the
    digit its Super shortcut actually uses.
    """
    if not cfg.get("workspace_key") or workspace is None:
        return None
    name = str(workspace).strip()
    if name == "10":
        name = "0"
    return EVDEV_TO_LED.get(f"KEY_{name}") if name.isdigit() else None


def compute_key_flash_colors(key_settings, base_map, flash_color, flash_brightness):
    """Compute the peak flash color of every LED position.

    Second rung of the inheritance chain: the flash falls back to each key's own
    resolved color and/or brightness, so a key already inheriting from the
    keyboard propagates that color all the way to its flash. The peak blends the
    key's resting color toward the flash color by the flash brightness, which
    leaves a non-inherited flash behaving exactly as it did before.
    """
    inherit_color = is_inherit(flash_color)
    inherit_brightness = is_inherit(flash_brightness)
    target = None if inherit_color else parse_color(flash_color, default=[255, 255, 255])
    factor = None if inherit_brightness else resolve_brightness(flash_brightness, 10) / 10.0

    peaks = {}
    for pos, (key_col, key_bri) in key_settings.items():
        peak = key_col if inherit_color else target
        f = key_bri / 10.0 if inherit_brightness else factor
        base = base_map.get(pos, (0, 0, 0))
        peaks[pos] = tuple(int(b + (t - b) * f) for b, t in zip(base, peak))
    return peaks


def first_lit_color(*candidates):
    """First candidate parsing to a non-black color: the hue keys inherit from."""
    for c in candidates:
        col = parse_color(c, default=None)
        if col and col != [0, 0, 0]:
            return col
    return list(DEFAULT_CONFIG["bg_color"])


Lighting = namedtuple("Lighting", (
    "backlight flash fade_duration brightness flash_brightness "
    "raw_bg effective_bg hw_flash_color is_dark base_map flash_map ws_pos"
))


def resolve_fade_duration(raw):
    """Fade length in seconds, floored: a zero would divide by zero mid-fade."""
    try:
        return max(0.05, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_CONFIG["fade_duration"]


def resolve_lighting(cfg, workspace=None):
    """Resolve a config into everything the render loop needs.

    Pure function: the whole inheritance chain (keyboard -> custom key -> flash)
    is settled here, so the daemon loop only has to render and send frames.
    `workspace` is the active Hyprland workspace, or None when unknown.
    """
    backlight = bool(cfg.get("backlight", True))
    brightness = resolve_brightness(cfg.get("brightness"), 10)
    raw_bg = first_lit_color(cfg.get("bg_color"), cfg.get("saved_color"))
    effective_bg = [0, 0, 0] if (not backlight or brightness == 0) else list(scale_color(raw_bg, brightness))

    flash_color = cfg.get("flash_color", [255, 255, 255])
    flash_brightness = cfg.get("flash_brightness", 10)

    # The hardware mode can render a dark keyboard, but not a single lit key,
    # so the indicator is dropped there unless it was explicitly asked for.
    dark = effective_bg == [0, 0, 0] and (not backlight or not cfg.get("custom_keys"))
    ws_pos = workspace_led_pos(cfg, workspace)
    if ws_pos is not None and dark and not cfg.get("workspace_dark"):
        ws_pos = None

    key_settings = resolve_key_settings(cfg, raw_bg, brightness, ws_pos)
    base_map = compute_key_base_colors(key_settings, effective_bg, backlight,
                                       () if ws_pos is None else (ws_pos,))

    return Lighting(
        backlight=backlight,
        flash=bool(cfg.get("flash", True)),
        fade_duration=resolve_fade_duration(cfg.get("fade_duration")),
        brightness=brightness,
        # Global flash brightness, for the hardware mode and the on/off test;
        # in matrix mode each key's own value is already baked into flash_map.
        flash_brightness=resolve_brightness(flash_brightness, brightness),
        raw_bg=raw_bg,
        effective_bg=effective_bg,
        # The hardware reactive mode is monochrome, so an inherited flash can
        # only fall back to the background color there.
        hw_flash_color=raw_bg if is_inherit(flash_color) else parse_color(flash_color, default=[255, 255, 255]),
        is_dark=dark and ws_pos is None,
        base_map=base_map,
        flash_map=compute_key_flash_colors(key_settings, base_map, flash_color, flash_brightness),
        ws_pos=ws_pos,
    )


def load_config():
    """Load the config on top of the defaults, dropping keys we no longer know.

    A file we failed to read is never overwritten: the daemon polls this path
    while the CLI writes it, and a config wiped by a bad read would cost the
    user every custom key they had set.
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r") as f:
            stored = json.load(f)
    except FileNotFoundError:
        save_config(cfg)
        return cfg
    except (OSError, ValueError):
        return cfg
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config(cfg):
    """Write the config atomically, so a concurrent reader never sees a partial file.

    Returns what was actually stored: keys we do not know are dropped here.
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    stored = {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG}
    tmp = f"{CONFIG_FILE}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(stored, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
    return stored


def update_config(changes):
    """Apply changes to the stored config and return the result."""
    cfg = load_config()
    cfg.update(changes)
    return save_config(cfg)


# ----------------- DAEMON CONTROL -----------------

def daemon_pid():
    """PID of the running daemon, or None.

    The command line is checked so that a stale pid file left by a crash cannot
    make us signal whichever unrelated process inherited that pid.
    """
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if b"aorus_rgb" in f.read() else None
    except (OSError, ValueError):
        return None


def is_service_active():
    try:
        res = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return res.stdout.strip() == "active"
    except OSError:
        return False


def restart_service():
    subprocess.run(["systemctl", "--user", "restart", SERVICE])


def notify_daemon():
    """Start the service if needed, then wake its select() so it reloads at once."""
    if not is_service_active():
        subprocess.run(["systemctl", "--user", "start", SERVICE])
    pid = daemon_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGUSR1)
        except OSError:
            pass


# ----------------- ARGUMENT PARSING & DISPLAY -----------------

def parse_color_arg(text):
    """Parse a color argument: "inherit", an [r, g, b] list, or None if unrecognized."""
    if is_inherit(text):
        return "inherit"
    if isinstance(text, str) and text.strip().lower() == "theme":
        # Kept literal so the daemon re-reads the Omarchy accent on every reload.
        return "theme"
    return parse_color(text)


def parse_brightness_arg(text):
    """Parse a brightness argument: "inherit", an int 0-10, or None if invalid."""
    if is_inherit(text):
        return "inherit"
    try:
        value = int(text)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 10 else None


def fmt_color(val):
    """Format a color value for display ('inherit', 'theme' or [r, g, b])."""
    if is_inherit(val):
        return "inherit"
    if isinstance(val, (list, tuple)):
        return str(list(val))
    return str(val)


def fmt_brightness(val):
    """Format a brightness value for display ('inherit' or 'n/10')."""
    return "inherit" if is_inherit(val) else f"{val}/10"


def group_custom_keys(custom_keys):
    """Group keys sharing the same color and brightness, for display."""
    groups = {}
    for kname, cinfo in sorted(custom_keys.items()):
        label = (fmt_color(cinfo.get("color")), fmt_brightness(cinfo.get("brightness")))
        groups.setdefault(label, []).append(kname)
    return groups


# ----------------- PRESETS -----------------

# Config keys a preset captures and restores. saved_color rides along so that
# `on` restores the right hue after a preset that had the backlight off.
PRESET_KEYS = ("backlight", "brightness", "bg_color", "saved_color", "flash",
               "flash_brightness", "flash_color", "fade_duration", "custom_keys")


def preset_path(name):
    """Path of a preset, from a user-typed name. Returns None if the name is invalid."""
    name = str(name).strip().lower()
    if name.endswith(".json"):
        name = name[:-5]
    if not re.fullmatch(r"[a-z0-9_-]+", name):
        return None
    return os.path.join(PRESETS_DIR, f"{name}.json")


def preset_exists(name):
    path = preset_path(name)
    return bool(path) and os.path.exists(path)


def read_preset(name):
    """Load a preset by name, or None if it is missing or unreadable."""
    path = preset_path(name)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_preset(name, cfg):
    """Save the preset-relevant part of a config. Returns its data, or None on a bad name."""
    path = preset_path(name)
    if not path:
        return None
    data = {"name": os.path.basename(path)[:-5], "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    data.update({k: cfg[k] for k in PRESET_KEYS if k in cfg})
    os.makedirs(PRESETS_DIR, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return data


def delete_preset(name):
    path = preset_path(name)
    if not path or not os.path.exists(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


def list_presets():
    """All saved presets as (name, data); data is None when the file is unreadable."""
    out = []
    for path in sorted(glob.glob(os.path.join(PRESETS_DIR, "*.json"))):
        name = os.path.basename(path)[:-5]
        out.append((name, read_preset(name)))
    return out


def describe_preset(data):
    """One-line summary of a preset's content."""
    if not data:
        return "fichier illisible"
    return (f"Fond {fmt_color(data.get('bg_color'))} ({fmt_brightness(data.get('brightness'))}) | "
            f"Flash {fmt_color(data.get('flash_color'))} ({fmt_brightness(data.get('flash_brightness'))}) | "
            f"{len(data.get('custom_keys', {}))} touche(s) persos")


def omarchy_theme_file():
    """Path of the active Omarchy theme file to read the keyboard hue from."""
    for directory in OMARCHY_THEME_DIRS:
        for name in OMARCHY_THEME_FILES:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
    return None


def _hex_to_rgb(text):
    """[r, g, b] from a #rrggbb or rrggbb string, or None."""
    clean = text.strip().strip("\"'").lstrip("#")
    if len(clean) != 6 or any(c not in "0123456789abcdefABCDEF" for c in clean):
        return None
    return [int(clean[i:i + 2], 16) for i in (0, 2, 4)]


def get_theme_accent_color():
    """Keyboard hue of the active Omarchy theme, or the default cyan."""
    path = omarchy_theme_file()
    if path:
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") and len(line) != 7:
                        continue
                    # keyboard.rgb is a bare hex line; colors.toml is key = "#hex".
                    field, sep, value = line.partition("=")
                    if sep and field.strip() not in ("accent", "blue"):
                        continue
                    rgb = _hex_to_rgb(value if sep else line)
                    if rgb:
                        return rgb
        except OSError:
            pass
    return list(DEFAULT_CONFIG["bg_color"])


# Color names accepted by parse_color, in French and English.
NAMED_COLORS = {
    "off": (0, 0, 0), "black": (0, 0, 0), "noir": (0, 0, 0),
    "none": (0, 0, 0), "dark": (0, 0, 0), "0": (0, 0, 0),
    "white": (255, 255, 255), "blanc": (255, 255, 255),
    "red": (255, 0, 0), "rouge": (255, 0, 0),
    "green": (0, 255, 0), "vert": (0, 255, 0),
    "blue": (0, 120, 255), "bleu": (0, 120, 255),
    "cyan": (0, 220, 255),
    "orange": (255, 120, 0),
    "yellow": (255, 200, 0), "jaune": (255, 200, 0),
    "purple": (180, 0, 255), "violet": (180, 0, 255),
    "magenta": (255, 0, 150), "rose": (255, 0, 150), "pink": (255, 0, 150),
}


def parse_color(c, default=None):
    """Parse a color name, "r,g,b" triplet, hex code (with or without #) or RGB list.

    Returns None for values left to the inheritance chain, so callers must test
    is_inherit() first to tell "inherit" apart from an unparsable color.
    """
    if is_inherit(c):
        return None
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return [max(0, min(255, int(x))) for x in c]
    if not isinstance(c, str):
        return default

    c = c.lower().strip()
    if c == "theme":
        return get_theme_accent_color()
    if c in NAMED_COLORS:
        return list(NAMED_COLORS[c])

    if "," in c:
        parts = c.split(",")
        if len(parts) == 3:
            try:
                return [max(0, min(255, int(p.strip()))) for p in parts]
            except ValueError:
                pass

    clean = c.lstrip("#")
    if len(clean) == 3:
        clean = "".join(ch * 2 for ch in clean)
    if len(clean) == 6 and all(ch in "0123456789abcdef" for ch in clean):
        return [int(clean[i:i + 2], 16) for i in (0, 2, 4)]
    return default


def get_hw_color_code(rgb):
    """Map RGB to hardware color code (1: Red, 2: Green, 3: Yellow, 4: Blue, 5: Orange, 6: Purple, 7: White)."""
    r, g, b = rgb
    if min(r, g, b) > 130:
        return 0x07 # White
    if b > r and b > g:
        if r > 100:
            return 0x06 # Purple
        return 0x04 # Blue
    if g > r and g > b:
        if r > 100:
            return 0x03 # Yellow
        return 0x02 # Green
    if r > g and r > b:
        if b > 80:
            return 0x06 # Purple
        if g > 150:
            return 0x03 # Yellow
        if g > 50:
            return 0x05 # Orange
        return 0x01 # Red
    return 0x07 # Default White


def get_keyboard_hid_path():
    """Locate keyboard USB controller (0414:8007, interface 3)."""
    for d in hid.enumerate(0x0414, 0x8007):
        if d.get("interface_number") == 3:
            return d["path"]
    return b"/dev/hidraw3"


def get_keyboard_input_device():
    """Open the keyboard evdev node (0414:8007 input0), or None if it is absent.

    Returning None rather than raising lets the daemon wait for the keyboard to
    come back (suspend, USB reset) instead of dying into a systemd restart loop.
    """
    by_id = "/dev/input/by-id/usb-GIGABYTE_USB-HID_Keyboard_AP0000000003-event-kbd"
    candidates = [by_id] if os.path.exists(by_id) else []
    candidates += sorted(glob.glob("/dev/input/event*"))
    for path in candidates:
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if path == by_id or ("GIGABYTE" in dev.name and
                             ("8007" in str(dev.phys) or "input0" in str(dev.phys))):
            fcntl.fcntl(dev.fd, fcntl.F_SETFL, os.O_NONBLOCK)
            return dev
        dev.close()
    return None


# ----------------- HYPRLAND WORKSPACE WATCHER -----------------

def active_workspace():
    """Name of the active Hyprland workspace right now, or None."""
    path = WorkspaceWatcher._socket_dir()
    return WorkspaceWatcher._query(path) if path else None



class WorkspaceWatcher:
    """Follows the active Hyprland workspace over its IPC socket.

    Exposes fileno() so the daemon can select() on it and react to a switch
    without polling. Stays inert, and keeps retrying quietly, when Hyprland is
    not running -- the daemon must work the same on a plain session.
    """

    def __init__(self):
        self.active = None
        self.sock = None
        self.buf = b""
        self.next_retry = 0.0
        self.connect()

    @staticmethod
    def _socket_dir():
        """Hyprland's runtime directory for the live instance.

        The signature is read from the environment when systemd imported it, and
        otherwise from the newest instance directory: a user service does not
        always inherit the compositor's environment.
        """
        base = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "hypr")
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        if sig and os.path.isdir(os.path.join(base, sig)):
            return os.path.join(base, sig)
        dirs = [d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d)]
        return max(dirs, key=os.path.getmtime) if dirs else None

    def connect(self):
        """Attach to the event socket and read the current workspace once."""
        self.close()
        self.next_retry = time.time() + DEVICE_RETRY_DELAY
        path = self._socket_dir()
        if not path:
            return
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(os.path.join(path, ".socket2.sock"))
            sock.setblocking(False)
        except OSError:
            return
        self.sock = sock
        self.buf = b""
        self.active = self._query(path)

    @staticmethod
    def _query(path):
        """Ask the command socket for the active workspace name."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                sock.connect(os.path.join(path, ".socket.sock"))
                sock.sendall(b"j/activeworkspace")
                chunks = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            return str(json.loads(b"".join(chunks)).get("name"))
        except (OSError, ValueError):
            return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def fileno(self):
        return self.sock.fileno()

    def poll(self):
        """Drain pending events. Returns True when the active workspace changed."""
        if not self.sock:
            if time.time() >= self.next_retry:
                before = self.active
                self.connect()
                return self.active != before
            return False
        try:
            data = self.sock.recv(65536)
        except BlockingIOError:
            return False
        except OSError:
            data = b""
        if not data:            # Hyprland went away; retry later
            self.close()
            self.next_retry = time.time() + DEVICE_RETRY_DELAY
            return False

        self.buf += data
        lines, _, self.buf = self.buf.rpartition(b"\n")
        before = self.active
        for line in lines.decode("utf-8", "replace").splitlines():
            event, _, payload = line.partition(">>")
            if event == "workspace":
                self.active = payload
            elif event == "workspacev2":
                self.active = payload.split(",", 1)[-1]
            elif event == "focusedmon":
                self.active = payload.split(",", 1)[-1]
        return self.active != before


class KeyboardController:
    """Controls the Aorus keyboard RGB over USB HID."""

    def __init__(self):
        self.dev_path = get_keyboard_hid_path()
        self.handle = None
        self.current_mode = None
        self.current_hw_brightness = None
        self.connect()

    def connect(self):
        if self.handle:
            try:
                self.handle.close()
            except Exception:
                pass
        self.handle = hid.device()
        self.handle.open_path(self.dev_path)
        self.current_mode = None
        self.current_hw_brightness = None

    @staticmethod
    def _packet(*payload):
        """Build a feature report: leading 0x00, 7 payload bytes, trailing checksum."""
        return bytes([0x00, *payload, (0xFF - sum(payload)) & 0xFF])

    def _send_feature(self, pkt):
        """Send a feature report, reconnecting once if the handle went stale."""
        if not self.handle:
            self.connect()
        try:
            self.handle.send_feature_report(pkt)
        except Exception:
            self.connect()
            self.handle.send_feature_report(pkt)

    def set_hardware_reactive(self, brightness_byte=50, color_code=0x07):
        """Native hardware reactive mode (0x04). Runs at 1000 Hz on the MCU, 0 CPU."""
        self._send_feature(self._packet(0x08, 0x00, 0x04, 0x01, brightness_byte, color_code, 0x01))
        self.current_mode = "reactive"
        self.current_hw_brightness = brightness_byte

    def set_hardware_off(self):
        """Turn all keyboard lights off."""
        self._send_feature(self._packet(0x08, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01))
        self.current_mode = "off"
        self.current_hw_brightness = 0

    def enter_custom_mode(self, hw_brightness=50):
        """Switch to per-key matrix mode (0x33).

        Must be sent only on an actual mode change: re-sending it every frame
        resets the MCU lighting engine and makes the keyboard stutter.
        """
        self._send_feature(self._packet(0x08, 0x00, 0x33, 0x01, hw_brightness, 0x05, 0x01))
        self.current_mode = "custom"
        self.current_hw_brightness = hw_brightness

    def send_frame(self, key_rgb, hw_brightness=50):
        """Send one per-key frame (report 0x12, 8 chunks of 64 bytes)."""
        if self.current_mode != "custom" or self.current_hw_brightness != hw_brightness:
            self.enter_custom_mode(hw_brightness)

        color_data = bytearray(512)
        for pos, (r, g, b) in key_rgb.items():
            if pos in VALID_POSITIONS:
                color_data[pos * 4 + 1] = int(r)
                color_data[pos * 4 + 2] = int(g)
                color_data[pos * 4 + 3] = int(b)

        header = bytes([0x00, 0x12, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0xE5])

        def _write_frame():
            self.handle.send_feature_report(header)
            for i in range(8):
                self.handle.write(bytes([0x00]) + color_data[64 * i:64 * (i + 1)])

        try:
            _write_frame()
        except Exception:
            try:
                self.connect()
                self.enter_custom_mode(hw_brightness)
                _write_frame()
            except Exception:
                self.current_mode = None
                return
        self.current_mode = "custom"
        self.current_hw_brightness = hw_brightness


def drain_input(input_dev):
    """Read the pending key presses. Returns LED positions, or None if the device died."""
    try:
        return [EVDEV_TO_LED[name]
                for ev in input_dev.read()
                if ev.type == evdev.ecodes.EV_KEY and ev.value == 1
                for name in (evdev.ecodes.KEY.get(ev.code),)
                if name in EVDEV_TO_LED]
    except BlockingIOError:
        return []
    except OSError:
        return None


def render_frame(lighting, active_fades, now):
    """Build the frame for the running fades, dropping the ones that are over."""
    frame = dict(lighting.base_map)
    for pos, started in list(active_fades.items()):
        elapsed = now - started
        if elapsed >= lighting.fade_duration:
            del active_fades[pos]
            continue
        ratio = elapsed / lighting.fade_duration
        # Smoothstep easing: the USB endpoint caps us at ~10 FPS, and a linear
        # fade is visibly stepped at that rate.
        factor = 1.0 - (3.0 * ratio * ratio - 2.0 * ratio * ratio * ratio)
        base = lighting.base_map.get(pos, (0, 0, 0))
        peak = lighting.flash_map.get(pos, base)
        frame[pos] = tuple(int(p * factor + b * (1.0 - factor)) for p, b in zip(peak, base))
    return frame


def theme_stamp(cfg):
    """Mtime of the Omarchy theme, but only while the background follows it.

    This is what makes `aorus rgb color theme` track the theme instead of
    freezing the accent it had the day it was set.
    """
    bg = cfg.get("bg_color")
    if not (isinstance(bg, str) and bg.strip().lower() == "theme"):
        return ""
    path = omarchy_theme_file()
    try:
        return str(os.path.getmtime(path)) if path else ""
    except OSError:
        return ""


def _wakeup_pipe():
    """Self-pipe so SIGUSR1 breaks select() instead of only shortening its timeout."""
    read_fd, write_fd = os.pipe()
    for fd in (read_fd, write_fd):
        os.set_blocking(fd, False)
    signal.set_wakeup_fd(write_fd)
    return read_fd


def run_daemon():
    """Main daemon loop: reload config, resolve lighting, render."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    def on_exit(signum, frame):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)
    # SIGUSR1 from the CLI only needs to break the select() below.
    signal.signal(signal.SIGUSR1, lambda signum, frame: None)
    wake_fd = _wakeup_pipe()

    controller = KeyboardController()
    workspaces = WorkspaceWatcher()
    input_dev = None

    active_fades = {}  # {led_pos: flash start time}
    cfg, fingerprint, light = load_config(), None, None
    last_reload = last_tick = 0.0

    while True:
        now = time.time()
        if now - last_tick > SUSPEND_GAP:
            # Resumed from sleep, or first pass: the MCU state is unknown again.
            try:
                controller.connect()
            except Exception:
                controller.current_mode = None
            fingerprint = None
        last_tick = now

        if input_dev is None:
            input_dev = get_keyboard_input_device()
            if input_dev is None:
                time.sleep(DEVICE_RETRY_DELAY)
                continue

        if now - last_reload > CONFIG_POLL_INTERVAL:
            cfg, last_reload = load_config(), now

        current = (json.dumps(cfg, sort_keys=True), workspaces.active, theme_stamp(cfg))
        changed = current != fingerprint
        if changed:
            light, fingerprint = resolve_lighting(cfg, workspaces.active), current
            active_fades.clear()

        flash_on = light.flash and light.flash_brightness > 0

        # Keyboard dark and nothing per-key to show: the MCU can do the whole
        # effect itself, at 1000 Hz for 0% CPU and no USB traffic.
        if light.is_dark:
            if changed:
                if flash_on:
                    controller.set_hardware_reactive(
                        brightness_byte=max(5, min(50, light.flash_brightness * 5)),
                        color_code=get_hw_color_code(light.hw_flash_color))
                else:
                    controller.set_hardware_off()
            timeout = IDLE_TIMEOUT
        else:
            # Colored background, custom keys or workspace indicator: matrix mode.
            if changed:
                controller.send_frame(light.base_map, hw_brightness=HW_FULL_BRIGHTNESS)
            timeout = FADE_TIMEOUT if (flash_on and active_fades) else IDLE_TIMEOUT

        pressed = wait_events(input_dev, workspaces, wake_fd, timeout)
        if pressed is None:
            input_dev.close()
            input_dev = None
            continue

        if flash_on and not light.is_dark:
            now = time.time()
            for pos in pressed:
                # Ignore key repeat: restarting a fade that just began looks like a stutter.
                if now - active_fades.get(pos, 0) > MIN_RETRIGGER_DELAY:
                    active_fades[pos] = now
            if active_fades:
                controller.send_frame(render_frame(light, active_fades, time.time()),
                                      hw_brightness=HW_FULL_BRIGHTNESS)


def wait_events(input_dev, workspaces, wake_fd, timeout):
    """Block until a keypress, a workspace switch, a CLI signal or the timeout.

    Returns the LED positions just pressed, or None if the keyboard went away.
    """
    fds = [input_dev, wake_fd] + ([workspaces] if workspaces.sock else [])
    try:
        ready, _, _ = select.select(fds, [], [], timeout)
    except OSError:
        return None

    if wake_fd in ready:
        try:
            os.read(wake_fd, 4096)
        except OSError:
            pass
    if workspaces in ready or not workspaces.sock:
        workspaces.poll()
    return drain_input(input_dev) if input_dev in ready else []


if __name__ == "__main__":
    run_daemon()
