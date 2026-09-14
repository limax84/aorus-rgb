#!/usr/bin/env python3
"""
AORUS RGB Keyboard Controller & Reactive Lighting Daemon.
Specifically targets Aorus 17X (0414:8007 keyboard controller).
Supports:
  - Backlight ON/OFF
  - Backlight intensity (0-10)
  - Keypress Flash ON/OFF
  - Flash intensity (0-10)
  - Flash custom color
  - Automatic color detection (black/off vs color)
"""

import os
import sys
import time
import json
import glob
import select
import fcntl
import signal
import hid
import evdev

CONFIG_DIR = os.path.expanduser("~/.config/aorus-rgb")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
PID_FILE = os.path.join(CONFIG_DIR, "daemon.pid")
OMARCHY_THEME_FILE = os.path.expanduser("~/.config/omarchy/current/theme/colors.toml")

import unicodedata

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

VALID_POSITIONS = sorted(list(set(EVDEV_TO_LED.values())))

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
        elif f"KEY_{up}" in EVDEV_TO_LED:
            k = f"KEY_{up}"
            if k not in result:
                result.append(k)
        elif len(part) == 1:
            if f"KEY_{up}" in EVDEV_TO_LED:
                k = f"KEY_{up}"
                if k not in result:
                    result.append(k)
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
    "custom_keys": {}               # { "KEY_ESC": {"color": [255, 0, 0], "brightness": 10}, ... }
}


def compute_key_base_colors(cfg, effective_bg):
    """Compute base (idle) color for each of the valid LED positions."""
    custom_keys = cfg.get("custom_keys", {})
    backlight_on = cfg.get("backlight", True)
    base_map = {pos: tuple(effective_bg) for pos in VALID_POSITIONS}
    if not backlight_on:
        return base_map
    for kname, cinfo in custom_keys.items():
        if kname in EVDEV_TO_LED:
            pos = EVDEV_TO_LED[kname]
            col = parse_color(cinfo.get("color", [255, 255, 255]), default=[255, 255, 255])
            br = max(0, min(10, int(cinfo.get("brightness", 10)))) / 10.0
            base_map[pos] = (int(col[0] * br), int(col[1] * br), int(col[2] * br))
    return base_map


def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                res = DEFAULT_CONFIG.copy()
                res.update(cfg)
                return res
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_theme_accent_color():
    """Detect Omarchy active theme accent color."""
    if os.path.exists(OMARCHY_THEME_FILE):
        try:
            with open(OMARCHY_THEME_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("accent") or line.startswith("blue"):
                        val = line.split("=")[-1].strip().strip("\"'")
                        val_clean = val.lstrip("#")
                        if len(val_clean) == 6:
                            return [int(val_clean[0:2], 16), int(val_clean[2:4], 16), int(val_clean[4:6], 16)]
        except Exception:
            pass
    return [0, 180, 216]


def parse_color(c, default=None):
    """Parse color string, array, or hex (with or without #)."""
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return [max(0, min(255, int(x))) for x in c]
    if isinstance(c, str):
        c = c.lower().strip()
        if c == "theme":
            return get_theme_accent_color()
        if c in ("off", "black", "noir", "none", "dark", "0"):
            return [0, 0, 0]
        if c in ("white", "blanc"):
            return [255, 255, 255]
        if c in ("red", "rouge"):
            return [255, 0, 0]
        if c in ("green", "vert"):
            return [0, 255, 0]
        if c in ("blue", "bleu"):
            return [0, 120, 255]
        if c == "cyan":
            return [0, 220, 255]
        if c == "orange":
            return [255, 120, 0]
        if c in ("yellow", "jaune"):
            return [255, 200, 0]
        if c in ("purple", "violet"):
            return [180, 0, 255]
        if c in ("magenta", "rose", "pink"):
            return [255, 0, 150]

        if "," in c:
            parts = c.split(",")
            if len(parts) == 3:
                try:
                    return [max(0, min(255, int(p.strip()))) for p in parts]
                except ValueError:
                    pass

        # Hex support (#123456 or 123456 or #123 or 123)
        clean = c.lstrip("#")
        if len(clean) == 3 and all(ch in "0123456789abcdef" for ch in clean):
            clean = "".join([ch * 2 for ch in clean])
        if len(clean) == 6 and all(ch in "0123456789abcdef" for ch in clean):
            try:
                return [int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)]
            except ValueError:
                pass
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
    """Locate keyboard evdev node (0414:8007 input0)."""
    by_id = "/dev/input/by-id/usb-GIGABYTE_USB-HID_Keyboard_AP0000000003-event-kbd"
    if os.path.exists(by_id):
        try:
            return evdev.InputDevice(by_id)
        except Exception:
            pass
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            dev = evdev.InputDevice(path)
            if "GIGABYTE" in dev.name and ("8007" in str(dev.phys) or "14.0-6/input0" in str(dev.phys)):
                return dev
        except Exception:
            pass
    return evdev.InputDevice("/dev/input/event6")


class KeyboardController:
    """Controls Aorus keyboard RGB via USB HID."""
    def __init__(self):
        self.dev_path = get_keyboard_hid_path()
        self.handle = None
        self.current_mode = None
        self.current_hw_brightness = None
        self.connect()

    def connect(self):
        if self.handle:
            try: self.handle.close()
            except: pass
        self.handle = hid.device()
        self.handle.open_path(self.dev_path)
        self.current_mode = None
        self.current_hw_brightness = None

    def ensure_connected(self):
        if not self.handle:
            self.connect()

    def set_hardware_reactive(self, brightness_byte=50, color_code=0x07):
        """Native hardware reactive (Mode 0x04, Color 0x01..0x07). Instant, 0 CPU."""
        self.ensure_connected()
        s = 0x08 + 0x00 + 0x04 + 0x01 + brightness_byte + color_code + 0x01
        cs = (0xFF - s) & 0xFF
        pkt = bytes([0x00, 0x08, 0x00, 0x04, 0x01, brightness_byte, color_code, 0x01, cs])
        try:
            self.handle.send_feature_report(pkt)
            self.current_mode = "reactive"
            self.current_hw_brightness = brightness_byte
        except Exception:
            self.connect()
            self.handle.send_feature_report(pkt)
            self.current_mode = "reactive"
            self.current_hw_brightness = brightness_byte

    def set_hardware_off(self):
        """Turn off keyboard lights."""
        self.ensure_connected()
        s = 0x08 + 0x00 + 0x01 + 0x01 + 0x00 + 0x00 + 0x01
        cs = (0xFF - s) & 0xFF
        pkt = bytes([0x00, 0x08, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, cs])
        try:
            self.handle.send_feature_report(pkt)
            self.current_mode = "off"
            self.current_hw_brightness = 0
        except Exception:
            self.connect()
            self.handle.send_feature_report(pkt)
            self.current_mode = "off"
            self.current_hw_brightness = 0

    def enter_custom_mode(self, hw_brightness=50):
        """Send mode 0x33 packet once to enter custom per-key matrix mode."""
        self.ensure_connected()
        s = 0x08 + 0x00 + 0x33 + 0x01 + hw_brightness + 0x05 + 0x01
        cs = (0xFF - s) & 0xFF
        mode_pkt = bytes([0x00, 0x08, 0x00, 0x33, 0x01, hw_brightness, 0x05, 0x01, cs])
        self.handle.send_feature_report(mode_pkt)
        self.current_mode = "custom"
        self.current_hw_brightness = hw_brightness

    def send_frame(self, key_rgb_dict, hw_brightness=50):
        """Sends per-key custom frame directly to keyboard LED buffer via 0x12."""
        self.ensure_connected()
        if self.current_mode != "custom" or self.current_hw_brightness != hw_brightness:
            try:
                self.enter_custom_mode(hw_brightness)
            except Exception:
                self.connect()
                self.enter_custom_mode(hw_brightness)

        color_data = bytearray(512)
        for pos, (r, g, b) in key_rgb_dict.items():
            if pos in VALID_POSITIONS:
                color_data[pos*4 + 1] = int(r)
                color_data[pos*4 + 2] = int(g)
                color_data[pos*4 + 3] = int(b)

        pkt = bytes([0x00, 0x12, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0xE5])

        def _do_send():
            self.handle.send_feature_report(pkt)
            for i in range(8):
                chunk = bytes([0x00]) + color_data[64*i : 64*(i+1)]
                self.handle.write(chunk)
            self.current_mode = "custom"
            self.current_hw_brightness = hw_brightness

        try:
            _do_send()
        except Exception:
            self.connect()
            self.enter_custom_mode(hw_brightness)
            try:
                _do_send()
            except Exception:
                pass


def run_daemon():
    """Main daemon loop."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    def on_exit(signum, frame):
        if os.path.exists(PID_FILE):
            try: os.remove(PID_FILE)
            except: pass
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    def on_sigusr1(signum, frame):
        pass
    signal.signal(signal.SIGUSR1, on_sigusr1)

    controller = KeyboardController()
    input_dev = get_keyboard_input_device()
    fcntl.fcntl(input_dev.fd, fcntl.F_SETFL, os.O_NONBLOCK)

    active_fades = {} # {led_pos: start_time}
    last_applied_state = None
    last_cfg_check = 0

    while True:
        now = time.time()

        if now - last_cfg_check > 0.2:
            cfg = load_config()
            last_cfg_check = now

        backlight_on = cfg.get("backlight", True)
        flash_enabled = cfg.get("flash", True)
        b_val = max(0, min(10, int(cfg.get("brightness", 10))))
        fb_val = max(0, min(10, int(cfg.get("flash_brightness", 10))))
        flash_col = parse_color(cfg.get("flash_color", [255, 255, 255]), default=[255, 255, 255])
        fade_duration = float(cfg.get("fade_duration", 0.45))

        custom_keys = cfg.get("custom_keys", {})
        has_custom_keys = bool(custom_keys)

        # Determine effective background color
        if not backlight_on or b_val == 0:
            effective_bg = [0, 0, 0]
        else:
            raw_bg = parse_color(cfg.get("bg_color", [0, 180, 216]), default=[0, 180, 216])
            if raw_bg == [0, 0, 0]:
                raw_bg = parse_color(cfg.get("saved_color", [0, 180, 216]), default=[0, 180, 216])
                if raw_bg == [0, 0, 0]:
                    raw_bg = [0, 180, 216]
            b_factor = b_val / 10.0
            effective_bg = [int(c * b_factor) for c in raw_bg]

        # Dark hardware reactive mode is used ONLY if whole keyboard is dark AND (backlight is off OR no custom keys)
        is_dark = (effective_bg == [0, 0, 0] and (not backlight_on or not has_custom_keys))

        # Compute per-key base colors
        base_map = compute_key_base_colors(cfg, effective_bg)
        ck_hash = json.dumps(custom_keys, sort_keys=True)

        current_state_key = (backlight_on, flash_enabled, b_val, fb_val, tuple(effective_bg), tuple(flash_col), ck_hash)

        # --- CASE 1: Clavier éteint (fond noir sans touches personnalisées) ---
        if is_dark:
            hw_color = get_hw_color_code(flash_col)
            use_hw_reactive = (flash_enabled and fb_val > 0)
            hw_b = max(5, min(50, fb_val * 5))

            if current_state_key != last_applied_state:
                if use_hw_reactive:
                    controller.set_hardware_reactive(brightness_byte=hw_b, color_code=hw_color)
                elif not flash_enabled or fb_val == 0:
                    controller.set_hardware_off()
                last_applied_state = current_state_key
                active_fades.clear()

            if use_hw_reactive or not flash_enabled or fb_val == 0:
                # Sleep waiting for input
                try:
                    r, _, _ = select.select([input_dev], [], [], 0.2)
                    if r:
                        for _ in input_dev.read(): pass
                except Exception:
                    pass
                continue

        # --- CASE 2: Clavier coloré ou touches personnalisées actives ---
        hw_b = 50

        if not flash_enabled or fb_val == 0:
            if current_state_key != last_applied_state:
                controller.send_frame(base_map, hw_brightness=hw_b)
                last_applied_state = current_state_key
                active_fades.clear()

            try:
                r, _, _ = select.select([input_dev], [], [], 0.2)
                if r:
                    for _ in input_dev.read(): pass
            except Exception:
                pass
            continue

        # Active reactive flash mode on colored/custom background
        if current_state_key != last_applied_state:
            controller.send_frame(base_map, hw_brightness=hw_b)
            last_applied_state = current_state_key
            active_fades.clear()

        # Listen for keystrokes
        timeout = 0.01 if active_fades else 0.2
        try:
            r, _, _ = select.select([input_dev], [], [], timeout)
        except Exception:
            r = False

        if r:
            try:
                for ev in input_dev.read():
                    if ev.type == evdev.ecodes.EV_KEY and ev.value == 1:
                        kname = evdev.ecodes.KEY.get(ev.code)
                        if kname and kname in EVDEV_TO_LED:
                            pos = EVDEV_TO_LED[kname]
                            now_ev = time.time()
                            if pos not in active_fades or (now_ev - active_fades[pos]) > 0.08:
                                active_fades[pos] = now_ev
            except Exception:
                pass

        # Update animation frame
        if active_fades:
            cur_time = time.time()
            frame_keys = {}
            to_remove = []
            f_factor = fb_val / 10.0

            for pos in VALID_POSITIONS:
                base_col = base_map.get(pos, tuple(effective_bg))
                if pos in active_fades:
                    elapsed = cur_time - active_fades[pos]
                    if elapsed >= fade_duration:
                        to_remove.append(pos)
                        frame_keys[pos] = base_col
                    else:
                        ratio = elapsed / fade_duration
                        # Smoothstep easing for fluid LED fade without stepping
                        factor = 1.0 - (3.0 * ratio * ratio - 2.0 * ratio * ratio * ratio)
                        peak_col = [int(bc + (fl - bc) * f_factor) for bc, fl in zip(base_col, flash_col)]
                        r = int(peak_col[0] * factor + base_col[0] * (1.0 - factor))
                        g = int(peak_col[1] * factor + base_col[1] * (1.0 - factor))
                        b = int(peak_col[2] * factor + base_col[2] * (1.0 - factor))
                        frame_keys[pos] = (r, g, b)
                else:
                    frame_keys[pos] = base_col

            for p in to_remove:
                del active_fades[p]

            controller.send_frame(frame_keys, hw_brightness=hw_b)


if __name__ == "__main__":
    run_daemon()
