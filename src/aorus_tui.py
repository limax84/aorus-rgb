#!/usr/bin/env python3
"""Interactive terminal console for the Aorus RGB keyboard (`aorus rgb config`).

Nested menus over the same config the CLI writes, plus a navigable keyboard map
for the per-key colors. Every change is saved and pushed to the daemon at once,
so the keyboard under your hands is the preview. Standard library only: curses.
"""

import curses
import locale

from aorus_rgb import (
    EVDEV_TO_LED, PRESET_KEYS, active_workspace, delete_preset, describe_preset,
    fmt_brightness, fmt_color, is_service_active, list_presets, load_config,
    notify_daemon, parse_brightness_arg, parse_color_arg, preset_exists,
    read_preset, resolve_keys, resolve_lighting, restart_service, save_config,
    write_preset,
)

# Physical layout, row by row. Each cell is (evdev name, 3-char label); None is
# the gap before the numeric island. KEY_COMPOSE is left out: it shares LED 66
# with KEY_MENU and would just be a second cursor stop on the same light.
KEYBOARD_ROWS = [
    [("KEY_ESC", "Esc"), ("KEY_F1", "F1"), ("KEY_F2", "F2"), ("KEY_F3", "F3"),
     ("KEY_F4", "F4"), ("KEY_F5", "F5"), ("KEY_F6", "F6"), ("KEY_F7", "F7"),
     ("KEY_F8", "F8"), ("KEY_F9", "F9"), ("KEY_F10", "F10"), ("KEY_F11", "F11"),
     ("KEY_F12", "F12"), None,
     ("KEY_PAUSE", "Pau"), ("KEY_DELETE", "Del"), ("KEY_HOME", "Hom"),
     ("KEY_PAGEUP", "PgU"), ("KEY_PAGEDOWN", "PgD"), ("KEY_END", "End")],

    [("KEY_GRAVE", "`"), ("KEY_1", "1"), ("KEY_2", "2"), ("KEY_3", "3"),
     ("KEY_4", "4"), ("KEY_5", "5"), ("KEY_6", "6"), ("KEY_7", "7"),
     ("KEY_8", "8"), ("KEY_9", "9"), ("KEY_0", "0"), ("KEY_MINUS", "-"),
     ("KEY_EQUAL", "="), ("KEY_BACKSPACE", "Bks"), None,
     ("KEY_NUMLOCK", "Num"), ("KEY_KPSLASH", "/"), ("KEY_KPASTERISK", "*"),
     ("KEY_KPMINUS", "-")],

    [("KEY_TAB", "Tab"), ("KEY_Q", "Q"), ("KEY_W", "W"), ("KEY_E", "E"),
     ("KEY_R", "R"), ("KEY_T", "T"), ("KEY_Y", "Y"), ("KEY_U", "U"),
     ("KEY_I", "I"), ("KEY_O", "O"), ("KEY_P", "P"), ("KEY_LEFTBRACE", "["),
     ("KEY_RIGHTBRACE", "]"), ("KEY_BACKSLASH", "\\"), None,
     ("KEY_KP7", "7"), ("KEY_KP8", "8"), ("KEY_KP9", "9"), ("KEY_KPPLUS", "+")],

    [("KEY_CAPSLOCK", "Cap"), ("KEY_A", "A"), ("KEY_S", "S"), ("KEY_D", "D"),
     ("KEY_F", "F"), ("KEY_G", "G"), ("KEY_H", "H"), ("KEY_J", "J"),
     ("KEY_K", "K"), ("KEY_L", "L"), ("KEY_SEMICOLON", ";"),
     ("KEY_APOSTROPHE", "'"), ("KEY_ENTER", "Ent"), None,
     ("KEY_KP4", "4"), ("KEY_KP5", "5"), ("KEY_KP6", "6")],

    [("KEY_LEFTSHIFT", "Sft"), ("KEY_102ND", "<"), ("KEY_Z", "Z"), ("KEY_X", "X"),
     ("KEY_C", "C"), ("KEY_V", "V"), ("KEY_B", "B"), ("KEY_N", "N"),
     ("KEY_M", "M"), ("KEY_COMMA", ","), ("KEY_DOT", "."), ("KEY_SLASH", "/"),
     ("KEY_RIGHTSHIFT", "Sft"), ("KEY_UP", "↑"), None,
     ("KEY_KP1", "1"), ("KEY_KP2", "2"), ("KEY_KP3", "3"), ("KEY_KPENTER", "Ent")],

    [("KEY_LEFTCTRL", "Ctl"), ("KEY_FN", "Fn"), ("KEY_LEFTMETA", "Sup"),
     ("KEY_LEFTALT", "Alt"), ("KEY_SPACE", "Spc"), ("KEY_RIGHTALT", "AGr"),
     ("KEY_MENU", "Mnu"), ("KEY_RIGHTCTRL", "Ctl"), ("KEY_LEFT", "←"),
     ("KEY_DOWN", "↓"), ("KEY_RIGHT", "→"), None,
     ("KEY_KP0", "0"), ("KEY_KPDOT", ".")],
]

CELL = 4            # width of one key cell, label included
MIN_WIDTH = 82      # widest row plus the side borders
MIN_HEIGHT = 22

# Groups offered by the `g` shortcut on the keyboard map.
GROUPS = ["wasd", "zqsd", "fkeys", "modifiers", "nav", "numpad", "digits",
          "arrows", "lettres", "all"]


# ----------------- COLORS -----------------

class Palette:
    """Maps RGB to curses color pairs, over the 256-color cube.

    Pairs are allocated on demand and cached: a keyboard map holds at most a
    handful of distinct colors, far below the terminal's pair budget.
    """

    def __init__(self):
        self.pairs = {}
        self.next_pair = 1
        self.enabled = curses.has_colors()
        if self.enabled:
            curses.start_color()
            curses.use_default_colors()

    @staticmethod
    def to_256(rgb):
        """Nearest xterm-256 index for an RGB triplet."""
        r, g, b = (max(0, min(255, int(c))) for c in rgb)
        if abs(r - g) < 12 and abs(g - b) < 12:          # grey ramp, finer than the cube
            level = round((r + g + b) / 3 / 255 * 25)
            return 16 if level == 0 else (231 if level == 25 else 231 + level)
        return 16 + 36 * round(r / 51) + 6 * round(g / 51) + round(b / 51)

    def attr(self, rgb):
        """Curses attribute drawing text in (approximately) this color."""
        if not self.enabled:
            return curses.A_DIM if max(rgb) < 40 else curses.A_NORMAL
        idx = self.to_256(rgb)
        if idx not in self.pairs:
            if self.next_pair >= min(curses.COLOR_PAIRS, 256):
                return curses.A_NORMAL
            curses.init_pair(self.next_pair, idx, -1)
            self.pairs[idx] = curses.color_pair(self.next_pair)
            self.next_pair += 1
        return self.pairs[idx]


# ----------------- CONSOLE -----------------

class Console:
    """The whole console: config state, screens and key handling."""

    def __init__(self, stdscr):
        self.scr = stdscr
        self.cfg = load_config()
        self.palette = Palette()
        self.history = []       # config snapshots, for undo
        self.message = ""
        self.workspace = active_workspace()

    # --- config plumbing -------------------------------------------------

    def commit(self, changes, message=""):
        """Save a change and hand it to the daemon straight away."""
        self.history.append(dict(self.cfg))
        del self.history[:-30]
        self.cfg.update(changes)
        save_config(self.cfg)
        notify_daemon()
        self.message = message

    def undo(self):
        if not self.history:
            self.message = "Rien à annuler."
            return
        self.cfg = self.history.pop()
        save_config(self.cfg)
        notify_daemon()
        self.message = "Annulé."

    def lighting(self):
        return resolve_lighting(self.cfg, self.workspace)

    def set_keys(self, names, color, brightness):
        custom = dict(self.cfg.get("custom_keys", {}))
        for name in names:
            custom[name] = {"color": color, "brightness": brightness}
        self.commit({"custom_keys": custom},
                    f"{len(names)} touche(s) : {fmt_color(color)} ({fmt_brightness(brightness)})")

    def reset_keys(self, names):
        custom = dict(self.cfg.get("custom_keys", {}))
        removed = [n for n in names if custom.pop(n, None) is not None]
        self.commit({"custom_keys": custom}, f"{len(removed)} touche(s) réinitialisée(s).")

    # --- drawing ---------------------------------------------------------

    def frame(self, title, subtitle=""):
        """Clear the screen and draw the title bar. Returns the first free row."""
        self.scr.erase()
        width = self.scr.getmaxyx()[1]
        self.scr.attron(curses.A_BOLD)
        self.scr.addnstr(0, 0, f" AORUS RGB · {title}".ljust(width - 1), width - 1)
        self.scr.attroff(curses.A_BOLD)
        if subtitle:
            self.scr.addnstr(1, 1, subtitle, width - 2, curses.A_DIM)
        return 3 if subtitle else 2

    def footer(self, hint):
        """Draw the hint line and the last message at the bottom of the screen."""
        height, width = self.scr.getmaxyx()
        if self.message:
            self.scr.addnstr(height - 2, 1, self.message, width - 2, curses.A_BOLD)
        self.scr.addnstr(height - 1, 1, hint, width - 2, curses.A_DIM)
        self.scr.refresh()

    def ask(self, label, default=""):
        """Read a line of text at the bottom of the screen. Returns None on Esc."""
        height, width = self.scr.getmaxyx()
        self.scr.move(height - 1, 0)
        self.scr.clrtoeol()
        self.scr.addnstr(height - 1, 1, label, width - 2, curses.A_BOLD)
        self.scr.refresh()

        curses.curs_set(1)
        curses.echo()
        try:
            raw = self.scr.getstr(height - 1, min(len(label) + 2, width - 2), 40)
            text = raw.decode("utf-8", "replace").strip()
        except (curses.error, KeyboardInterrupt):
            text = ""
        finally:
            curses.noecho()
            curses.curs_set(0)
        return text or default

    def menu(self, title, items, hint="↑↓ naviguer · ↵ ouvrir · q retour"):
        """Run a vertical menu. `items` is a list of (label, value, handler).

        The handler takes the console and returns True to stay on the menu.
        Redrawn after every action so the shown values always match the config.
        """
        index = 0
        while True:
            rows = items(self) if callable(items) else items
            index = max(0, min(index, len(rows) - 1))
            top = self.frame(title)
            width = self.scr.getmaxyx()[1]
            for i, (label, value, _) in enumerate(rows):
                attr = curses.A_REVERSE if i == index else curses.A_NORMAL
                line = f"  {label:<26}{value}"
                self.scr.addnstr(top + i, 1, line.ljust(width - 3), width - 3, attr)
            self.footer(hint)

            key = self.scr.getch()
            self.message = ""
            if key in (curses.KEY_UP, ord("k")):
                index -= 1
            elif key in (curses.KEY_DOWN, ord("j")):
                index += 1
            elif key in (ord("u"),):
                self.undo()
            elif key in (27, ord("q")):
                return
            elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
                if rows[index][2](self) is False:
                    return
            index %= max(1, len(rows))


# ----------------- PROMPT HELPERS -----------------

def ask_color(console, label="Couleur (nom, #hex, inherit, theme) : "):
    """Prompt for a color. Returns the value, or None if invalid or empty."""
    text = console.ask(label)
    if not text:
        return None
    value = parse_color_arg(text)
    if value is None:
        console.message = f"Couleur '{text}' non reconnue."
    return value


def ask_brightness(console, label="Intensité (0-10, inherit) : "):
    text = console.ask(label)
    if not text:
        return None
    value = parse_brightness_arg(text)
    if value is None:
        console.message = f"Intensité '{text}' invalide."
    return value


# ----------------- SCREENS -----------------

def screen_backlight(console):
    def rows(c):
        lit = c.cfg.get("backlight", True) and c.cfg.get("brightness", 10) > 0
        return [
            ("État", "allumé" if lit else "éteint", toggle_backlight),
            ("Couleur", fmt_color(c.cfg.get("bg_color")), set_bg_color),
            ("Intensité", fmt_brightness(c.cfg.get("brightness")), set_brightness),
            ("Durée du fondu", f"{c.cfg.get('fade_duration', 0.45)} s", set_fade),
            ("Retour", "", lambda c: False),
        ]

    def toggle_backlight(c):
        on = not (c.cfg.get("backlight", True) and c.cfg.get("brightness", 10) > 0)
        changes = {"backlight": on}
        if on and c.cfg.get("brightness", 10) == 0:
            changes["brightness"] = 10
        c.commit(changes, "Rétroéclairage " + ("allumé." if on else "éteint."))

    def set_bg_color(c):
        color = ask_color(c)
        if color in (None, "inherit"):
            return
        changes = {"bg_color": color, "backlight": color != [0, 0, 0]}
        if color != [0, 0, 0]:
            changes["saved_color"] = color
        c.commit(changes, f"Fond : {fmt_color(color)}")

    def set_brightness(c):
        value = ask_brightness(c, "Intensité du clavier (0-10) : ")
        if isinstance(value, int):
            c.commit({"brightness": value, "backlight": value > 0},
                     f"Intensité : {value}/10")

    def set_fade(c):
        text = c.ask("Durée du fondu en secondes (ex. 0.45) : ")
        try:
            c.commit({"fade_duration": max(0.05, float(text))}, f"Fondu : {text} s")
        except (TypeError, ValueError):
            c.message = "Durée invalide."

    console.menu("Rétroéclairage", rows)


def screen_flash(console):
    def rows(c):
        return [
            ("État", "activé" if c.cfg.get("flash", True) else "désactivé", toggle),
            ("Couleur", fmt_color(c.cfg.get("flash_color")), set_color),
            ("Intensité", fmt_brightness(c.cfg.get("flash_brightness")), set_brightness),
            ("Tout hériter", "couleur et intensité de chaque touche", inherit_all),
            ("Retour", "", lambda c: False),
        ]

    def toggle(c):
        state = not c.cfg.get("flash", True)
        c.commit({"flash": state}, "Flash " + ("activé." if state else "désactivé."))

    def set_color(c):
        color = ask_color(c, "Couleur du flash (nom, #hex, inherit) : ")
        if color is not None:
            c.commit({"flash_color": color, "flash": True}, f"Flash : {fmt_color(color)}")

    def set_brightness(c):
        value = ask_brightness(c, "Intensité du flash (0-10, inherit) : ")
        if value is not None:
            c.commit({"flash_brightness": value, "flash": True},
                     f"Flash : {fmt_brightness(value)}")

    def inherit_all(c):
        c.commit({"flash_color": "inherit", "flash_brightness": "inherit", "flash": True},
                 "Flash entièrement hérité.")

    console.menu("Flash à la frappe", rows)


def screen_os(console):
    def rows(c):
        found = c.workspace or "Hyprland injoignable"
        return [
            ("Indicateur workspace", "activé" if c.cfg.get("workspace_key") else "désactivé", toggle),
            ("Intensité du chiffre", fmt_brightness(c.cfg.get("workspace_brightness", 10)), set_brightness),
            ("Sur clavier éteint", "oui (coûte le 0 % CPU)" if c.cfg.get("workspace_dark") else "non", toggle_dark),
            ("Workspace actif", found, refresh),
            ("Redémarrer le service", "systemctl --user restart", restart),
            ("Retour", "", lambda c: False),
        ]

    def refresh(c):
        c.workspace = active_workspace()
        c.message = f"Workspace actif : {c.workspace or 'inconnu'}"

    def toggle(c):
        state = not c.cfg.get("workspace_key")
        c.commit({"workspace_key": state}, "Indicateur " + ("activé." if state else "désactivé."))

    def toggle_dark(c):
        state = not c.cfg.get("workspace_dark")
        c.commit({"workspace_dark": state},
                 "Visible clavier éteint." if state else "Masqué clavier éteint.")

    def set_brightness(c):
        value = ask_brightness(c, "Intensité du workspace actif (0-10) : ")
        if isinstance(value, int):
            c.commit({"workspace_brightness": value, "workspace_key": True},
                     f"Workspace actif : {value}/10")

    def restart(c):
        restart_service()
        c.message = "Service redémarré."

    console.menu("Intégration OS", rows,
                 "La touche du chiffre du workspace actif garde sa couleur et monte en intensité.")


def screen_presets(console):
    def rows(c):
        items = [(f"Charger « {name} »", describe_preset(data), _loader(name))
                 for name, data in list_presets()]
        return items + [
            ("Enregistrer la config actuelle", "", save),
            ("Supprimer un preset", "", remove),
            ("Retour", "", lambda c: False),
        ]

    def _loader(name):
        def load(c):
            data = read_preset(name)
            if data is None:
                c.message = f"Preset « {name} » illisible."
                return
            c.commit({k: data[k] for k in PRESET_KEYS if k in data}, f"Preset « {name} » appliqué.")
        return load

    def save(c):
        name = c.ask("Nom du preset : ")
        if not name:
            return
        if preset_exists(name) and not _confirm(c, f"Écraser « {name} » ? (o/N) "):
            return
        c.message = (f"Preset « {name} » enregistré." if write_preset(name, c.cfg)
                     else "Nom invalide (lettres, chiffres, - et _).")

    def remove(c):
        name = c.ask("Preset à supprimer : ")
        if not name:
            return
        if not _confirm(c, f"Supprimer « {name} » ? (o/N) "):
            return
        c.message = (f"Preset « {name} » supprimé." if delete_preset(name)
                     else f"Preset « {name} » introuvable.")

    console.menu("Presets", rows)


def _confirm(console, label):
    return console.ask(label).lower().startswith("o")


# ----------------- KEYBOARD MAP -----------------

def screen_keys(console):
    """Navigable keyboard map: mark keys, paint them, reset them."""
    nav = [[i for i, cell in enumerate(row) if cell] for row in KEYBOARD_ROWS]
    row, col = 0, 0
    marks = set()
    brush = None        # (color, brightness) while painting on the move

    def current():
        return KEYBOARD_ROWS[row][nav[row][col]][0]

    def targets():
        """Keys an action applies to: every mark, or the one under the cursor."""
        return sorted(marks) if marks else [current()]

    while True:
        light = console.lighting()
        top = console.frame(
            "Touches personnalisées",
            f"Fond {fmt_color(console.cfg.get('bg_color'))} "
            f"({fmt_brightness(console.cfg.get('brightness'))}) · "
            f"{len(console.cfg.get('custom_keys', {}))} touche(s) personnalisée(s)")

        height, width = console.scr.getmaxyx()
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            console.scr.addnstr(top, 1, f"Terminal trop petit : {MIN_WIDTH}x{MIN_HEIGHT} minimum.", width - 2)
            console.footer("q retour")
            if console.scr.getch() in (27, ord("q")):
                return
            continue

        for r, cells in enumerate(KEYBOARD_ROWS):
            x = 1
            for i, cell in enumerate(cells):
                if cell is None:
                    x += CELL // 2
                    continue
                name, label = cell
                rgb = light.base_map.get(EVDEV_TO_LED[name], (0, 0, 0))
                attr = console.palette.attr(rgb) if max(rgb) else curses.A_DIM
                if name in marks:
                    attr |= curses.A_BOLD | curses.A_UNDERLINE
                if r == row and i == nav[r][col]:
                    attr |= curses.A_REVERSE
                console.scr.addnstr(top + r, x, label.center(CELL - 1), CELL - 1, attr)
                x += CELL

        name = current()
        info = console.cfg.get("custom_keys", {}).get(name)
        detail = (f"{fmt_color(info.get('color'))} ({fmt_brightness(info.get('brightness'))})"
                  if info else "hérite du clavier")
        status = top + len(KEYBOARD_ROWS) + 1
        console.scr.addnstr(status, 1, f"{name} · {detail}", width - 2, curses.A_BOLD)
        selection = f"{len(marks)} marquée(s)" if marks else "aucune marque"
        painting = f" · pinceau {fmt_color(brush[0])} ({fmt_brightness(brush[1])})" if brush else ""
        console.scr.addnstr(status + 1, 1, selection + painting, width - 2, curses.A_DIM)

        console.footer("←→↑↓ déplacer · espace marquer · c couleur · b intensité · "
                       "p pinceau · g groupe · a tout · r reset · u annuler · q retour")

        key = console.scr.getch()
        console.message = ""

        if key in (27, ord("q")):
            return
        elif key == curses.KEY_LEFT:
            col -= 1
        elif key == curses.KEY_RIGHT:
            col += 1
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            row = (row + (1 if key == curses.KEY_DOWN else -1)) % len(nav)
        elif key == ord(" "):
            marks.symmetric_difference_update({name})
        elif key == ord("a"):
            marks = set() if marks else {c[0] for r in KEYBOARD_ROWS for c in r if c}
        elif key == ord("c"):
            color = ask_color(console)
            if color is not None:
                console.set_keys(targets(), color, _current_brightness(console, targets()))
                marks.clear()
        elif key == ord("b"):
            value = ask_brightness(console)
            if value is not None:
                console.set_keys(targets(), _current_color(console, targets()), value)
                marks.clear()
        elif key == ord("r"):
            console.reset_keys(targets())
            marks.clear()
        elif key == ord("p"):
            brush = None if brush else _ask_brush(console)
        elif key == ord("g"):
            group = _ask_group(console)
            if group:
                marks.symmetric_difference_update(resolve_keys(group))
        elif key == ord("u"):
            console.undo()

        col = max(0, min(col, len(nav[row]) - 1))
        if brush and key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN):
            console.set_keys([current()], brush[0], brush[1])


def _current_color(console, names):
    """Color already set on the first target, so `b` alone does not erase it."""
    info = console.cfg.get("custom_keys", {}).get(names[0], {})
    return info.get("color", "inherit")


def _current_brightness(console, names):
    info = console.cfg.get("custom_keys", {}).get(names[0], {})
    return info.get("brightness", "inherit")


def _ask_brush(console):
    color = ask_color(console, "Pinceau — couleur : ")
    if color is None:
        return None
    brightness = ask_brightness(console, "Pinceau — intensité : ")
    return (color, "inherit" if brightness is None else brightness)


def _ask_group(console):
    text = console.ask(f"Groupe ({', '.join(GROUPS)}) : ")
    if text and not resolve_keys(text):
        console.message = f"Groupe '{text}' inconnu."
        return None
    return text


# ----------------- ENTRY POINT -----------------

def screen_main(console):
    def rows(c):
        lit = c.cfg.get("backlight", True) and c.cfg.get("brightness", 10) > 0
        bg = f"{fmt_color(c.cfg.get('bg_color'))} ({fmt_brightness(c.cfg.get('brightness'))})"
        return [
            ("Rétroéclairage", bg if lit else "éteint", _open(screen_backlight)),
            ("Flash à la frappe",
             f"{fmt_color(c.cfg.get('flash_color'))} ({fmt_brightness(c.cfg.get('flash_brightness'))})"
             if c.cfg.get("flash", True) else "désactivé", _open(screen_flash)),
            ("Touches personnalisées", f"{len(c.cfg.get('custom_keys', {}))} configurée(s)", _open(screen_keys)),
            ("Presets", f"{len(list_presets())} enregistré(s)", _open(screen_presets)),
            ("Intégration OS",
             f"workspace {c.workspace}" if c.cfg.get("workspace_key") else "désactivée", _open(screen_os)),
            ("Quitter", "", lambda c: False),
        ]

    service = "service actif" if is_service_active() else "SERVICE INACTIF"
    console.menu("Console de configuration", rows,
                 f"↑↓ naviguer · ↵ ouvrir · u annuler · q quitter · {service}")


def _open(screen):
    def handler(console):
        screen(console)
    return handler


def run_tui():
    """Entry point behind `aorus rgb config`."""
    def main(stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        screen_main(Console(stdscr))

    # curses draws bytes: without the user locale the arrow glyphs come out mangled.
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(main)
