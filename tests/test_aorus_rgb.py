#!/usr/bin/env python3
"""Regression tests for the parts that break silently: the inheritance cascade,
the workspace rung, the theme lookup and the config store.

No test framework, no dependency beyond the daemon's own: `python3 tests/test_aorus_rgb.py`.
The USB and curses layers are not covered here -- they need the real hardware.
"""

import ast
import copy
import json
import os
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import aorus_rgb as A  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + name + ("" if condition else f"  <- {detail}"))
    if not condition:
        FAILURES.append(name)


def pos(key):
    return A.EVDEV_TO_LED[key]


def test_inheritance():
    print("héritage en cascade")
    base = copy.deepcopy(A.DEFAULT_CONFIG)
    cfg = dict(base, bg_color=[0, 220, 255], brightness=10,
               custom_keys={"KEY_ESC": {"color": [255, 0, 0], "brightness": 10}})
    light = A.resolve_lighting(cfg)
    check("la touche perso garde sa couleur", light.base_map[pos("KEY_ESC")] == (255, 0, 0))
    check("les autres touches suivent le fond", light.base_map[pos("KEY_A")] == (0, 220, 255))

    inherited = A.resolve_lighting(dict(cfg, flash_color="inherit", flash_brightness=10))
    check("le flash hérite par touche", inherited.flash_map[pos("KEY_ESC")] == (255, 0, 0))

    check("'none' reste noir, pas un héritage",
          A.parse_color("none") == [0, 0, 0] and not A.is_inherit("none"))
    check("les synonymes d'héritage sont reconnus",
          all(A.is_inherit(v) for v in (None, "inherit", "auto", "null", "")))


def test_fade_duration():
    print("durée de fondu")
    base = copy.deepcopy(A.DEFAULT_CONFIG)
    zero = A.resolve_lighting(dict(base, fade_duration=0))
    check("une durée nulle est bornée", zero.fade_duration == 0.05, zero.fade_duration)
    A.render_frame(zero, {11: 0.0}, 1.0)   # divisait par zéro avant le plancher
    check("une durée illisible retombe sur le défaut",
          A.resolve_lighting(dict(base, fade_duration="x")).fade_duration == 0.45)


def test_workspace():
    print("indicateur de workspace")
    base = copy.deepcopy(A.DEFAULT_CONFIG)
    cfg = dict(base, bg_color=[0, 220, 255], brightness=2,
               workspace_key=True, workspace_brightness=10)

    check("le workspace actif passe à 10/10",
          A.resolve_lighting(cfg, "3").base_map[pos("KEY_3")] == (0, 220, 255))
    check("les autres chiffres gardent leur réglage",
          A.resolve_lighting(cfg, "3").base_map[pos("KEY_4")] == (0, 44, 51))
    colored = A.resolve_lighting(
        dict(cfg, custom_keys={"KEY_3": {"color": [255, 0, 0], "brightness": 1}}), "3")
    check("par défaut l'indicateur hérite de la couleur de la touche",
          colored.base_map[pos("KEY_3")] == (255, 0, 0))

    forced_color = dict(cfg, workspace_color=[255, 255, 255])
    check("une couleur explicite écrase la cascade",
          A.resolve_lighting(forced_color, "3").base_map[pos("KEY_3")] == (255, 255, 255))
    check("elle écrase aussi une touche personnalisée",
          A.resolve_lighting(dict(forced_color,
                                  custom_keys={"KEY_3": {"color": [255, 0, 0], "brightness": 1}}),
                             "3").base_map[pos("KEY_3")] == (255, 255, 255))
    check("elle est atténuée par l'intensité du workspace",
          A.resolve_lighting(dict(forced_color, workspace_brightness=5),
                             "3").base_map[pos("KEY_3")] == (127, 127, 127))
    check("elle ne touche pas les autres chiffres",
          A.resolve_lighting(forced_color, "3").base_map[pos("KEY_4")] == (0, 44, 51))
    check("une couleur illisible retombe sur la cascade",
          A.resolve_lighting(dict(cfg, workspace_color="pas-une-couleur"),
                             "3").base_map[pos("KEY_3")] == (0, 220, 255))
    inherited = dict(cfg, workspace_brightness="inherit")
    check("workspace_brightness 'inherit' garde l'intensité de la touche",
          A.resolve_lighting(inherited, "3").base_map[pos("KEY_3")] == A.scale_color((0, 220, 255), 2))
    check("et celle d'une touche personnalisée",
          A.resolve_lighting(dict(inherited, custom_keys={"KEY_3": {"color": [255, 0, 0], "brightness": 8}}),
                             "3").base_map[pos("KEY_3")] == A.scale_color((255, 0, 0), 8))
    check("le workspace 10 vise la touche 0", A.resolve_lighting(cfg, "10").ws_pos == pos("KEY_0"))
    check("un workspace nommé n'allume rien", A.resolve_lighting(cfg, "Work").ws_pos is None)
    check("désactivé, aucun effet",
          A.resolve_lighting(dict(cfg, workspace_key=False), "3").ws_pos is None)

    dark = dict(base, backlight=False, workspace_key=True)
    check("clavier éteint : le mode matériel 0 % CPU est préservé",
          A.resolve_lighting(dark, "3").is_dark)
    forced = A.resolve_lighting(dict(dark, workspace_dark=True), "3")
    check("workspace_dark bascule en mode matrice", not forced.is_dark)
    check("workspace_dark allume bien le chiffre", forced.base_map[pos("KEY_3")] != (0, 0, 0))
    check("workspace_dark laisse le reste éteint", forced.base_map[pos("KEY_A")] == (0, 0, 0))


def test_theme():
    print("thème Omarchy")
    base = copy.deepcopy(A.DEFAULT_CONFIG)
    if not A.omarchy_theme_file():
        print("  (ignoré : aucun thème Omarchy installé)")
        return
    check("bg_color 'theme' se résout au rendu",
          A.resolve_lighting(dict(base, bg_color="theme")).raw_bg == A.get_theme_accent_color())
    check("l'empreinte suit le thème",
          A.theme_stamp(json.dumps(dict(base, bg_color="theme"))) != "")
    # Le fond n'est pas le seul réglage qui peut valoir "theme".
    check("l'empreinte couvre aussi le flash",
          A.theme_stamp(json.dumps(dict(base, flash_color="theme"))) != "")
    check("l'empreinte couvre aussi une touche personnalisée",
          A.theme_stamp(json.dumps(dict(base, custom_keys={"KEY_A": {"color": "theme"}}))) != "")
    check("l'empreinte est vide sans aucun 'theme'",
          A.theme_stamp(json.dumps(dict(base, bg_color=[1, 2, 3]))) == "")


def test_hostile_config():
    print("config éditée à la main")
    directory = tempfile.mkdtemp()
    A.CONFIG_DIR, A.CONFIG_FILE = directory, os.path.join(directory, "config.json")

    # Une valeur du mauvais type ne doit pas tuer le démon en boucle de
    # redémarrage : load_config normalise, resolve_lighting se garde aussi.
    for label, stored in (("custom_keys = chaîne", {"custom_keys": "nawak"}),
                          ("custom_keys = liste", {"custom_keys": [1, 2, 3]}),
                          ("entrée non-dict", {"custom_keys": {"KEY_A": "rouge"}}),
                          ("entrée nulle", {"custom_keys": {"KEY_A": None}})):
        with open(A.CONFIG_FILE, "w") as f:
            json.dump(stored, f)
        try:
            A.resolve_lighting(A.load_config(), "3")
            ok, detail = True, ""
        except Exception as err:
            ok, detail = False, f"{type(err).__name__}: {err}"
        check(f"survit à {label}", ok, detail)

    with open(A.CONFIG_FILE, "w") as f:
        json.dump({"custom_keys": {"KEY_A": "rouge",
                                   "KEY_B": {"color": [1, 2, 3], "brightness": 5}}}, f)
    check("l'entrée valide survit au nettoyage",
          A.load_config()["custom_keys"] == {"KEY_B": {"color": [1, 2, 3], "brightness": 5}})
    check("resolve_lighting se garde sans passer par load_config",
          A.resolve_lighting(dict(copy.deepcopy(A.DEFAULT_CONFIG),
                                  custom_keys={"KEY_A": "rouge"}), "3") is not None)


def test_config_store():
    print("stockage de la configuration")
    directory = tempfile.mkdtemp()
    A.CONFIG_DIR, A.CONFIG_FILE = directory, os.path.join(directory, "config.json")

    precious = dict(copy.deepcopy(A.DEFAULT_CONFIG),
                    custom_keys={f"KEY_F{i}": {"color": [1, 2, 3], "brightness": 5}
                                 for i in range(1, 13)})
    A.save_config(precious)

    corrupt = '{"backlight": tr'
    with open(A.CONFIG_FILE, "w") as f:
        f.write(corrupt)
    check("une config illisible n'est jamais écrasée",
          A.load_config()["custom_keys"] == {} and open(A.CONFIG_FILE).read() == corrupt)

    A.save_config(precious)
    with open(A.CONFIG_FILE, "w") as f:
        f.write(corrupt)
    A.update_config({"brightness": 7})
    # Écrire les défauts par-dessus détruirait exactement ce que read_config()
    # refuse de détruire : le fichier est mis de côté, pas écrasé.
    check("update_config met l'illisible de côté",
          open(A.CONFIG_FILE + ".corrupt").read() == corrupt)
    check("et la commande aboutit quand même",
          json.load(open(A.CONFIG_FILE))["brightness"] == 7)

    A.save_config(precious)
    check("les clés inconnues sont purgées", "enabled" not in A.update_config({"enabled": True}))
    check("les réglages survivent à l'écriture", len(A.load_config()["custom_keys"]) == 12)

    # Le démon relit ce fichier pendant que la CLI l'écrit : aucune lecture ne
    # doit tomber sur du JSON tronqué.
    stop, seen = [False], []

    def reader():
        while not stop[0]:
            seen.append(len(A.load_config().get("custom_keys", {})))

    thread = threading.Thread(target=reader)
    thread.start()
    for i in range(200):
        A.save_config(dict(precious, brightness=i % 11))
    stop[0] = True
    thread.join()
    check(f"{len(seen)} lectures concurrentes, aucune config vide",
          seen.count(0) == 0, f"{seen.count(0)} lectures vides")


def test_workspace_events():
    print("analyse des événements Hyprland")
    server, client = socket.socketpair()
    client.setblocking(False)
    watcher = A.WorkspaceWatcher.__new__(A.WorkspaceWatcher)
    watcher.active, watcher.sock, watcher.buf, watcher.next_retry = "1", client, b"", 0.0

    def send(payload):
        server.sendall(payload)
        select.select([watcher], [], [], 0.5)
        return watcher.poll()

    check("workspace>>", send(b"workspace>>3\n") and watcher.active == "3")
    check("workspacev2>>", send(b"workspacev2>>7,7\n") and watcher.active == "7")
    check("focusedmon>>", send(b"focusedmon>>eDP-1,2\n") and watcher.active == "2")
    check("les autres événements sont ignorés",
          not send(b"openwindow>>a,b,c,d\nactivewindow>>x,y\n") and watcher.active == "2")
    check("un workspace identique n'est pas un changement", not send(b"workspace>>2\n"))
    check("un lot d'événements est traité",
          send(b"activewindow>>a,b\nworkspace>>4\nopenwindow>>z\n") and watcher.active == "4")

    server.sendall(b"workspace>>")          # ligne coupée entre deux paquets
    select.select([watcher], [], [], 0.5)
    watcher.poll()
    check("une ligne partielle est mise en attente", watcher.active == "4")
    check("une ligne partielle est complétée", send(b"5\n") and watcher.active == "5")

    server.close()
    select.select([watcher], [], [], 0.5)
    watcher.poll()
    check("la disparition d'Hyprland est gérée", watcher.sock is None)
    # Garder le dernier workspace laisserait une touche allumée sans compositeur.
    check("et ne laisse pas de workspace périmé", watcher.active is None, watcher.active)


def test_device_access():
    print("accès au périphérique")
    rule = A.reference_udev_rule()
    check("la règle udev de référence est trouvable", rule is not None)
    if rule:
        # Les commentaires de la règle citent MODE="0666" pour expliquer
        # pourquoi il est proscrit ; seules les directives comptent.
        directives = [l for l in rule.splitlines() if l.strip() and not l.startswith("#")]
        # MODE="0666" sur le nœud event* du clavier, c'est un enregistreur de
        # frappe offert à tout processus local. La règle d'origine faisait ça.
        check('aucune directive MODE="0666"', not any("0666" in l for l in directives),
              "exposerait les frappes à toute application de la machine")
        check("l'accès passe par uaccess", all("uaccess" in l for l in directives))
        check("chaque directive est restreinte au 0414:8007",
              all('idVendor}=="0414"' in l and 'idProduct}=="8007"' in l for l in directives))

    source = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "src", "aorus_rgb.py")).read()
    # Un numéro de nœud change d'un démarrage à l'autre et un numéro de série ne
    # vaut que pour un exemplaire : ni l'un ni l'autre n'a sa place dans le code.
    # Les docstrings qui expliquent pourquoi, et les motifs glob, sont exclus.
    tree = ast.parse(source)
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    literals = [n.value.decode("utf-8", "replace") if isinstance(n.value, bytes) else n.value
                for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))
                and n.value not in docs]
    hardcoded = [v for v in literals if re.search(r"/dev/(?:hidraw|input/event)\d", v)
                 or "AP0000000003" in v]
    check("aucun nœud ni numéro de série codé en dur", not hardcoded, hardcoded)
    check("le contrôleur absent renvoie None, pas un chemin deviné",
          A.find_lighting_path.__doc__ and "None" in A.find_lighting_path.__doc__)


def test_controller_failure():
    print("clavier absent")

    class DeadHandle:
        def send_feature_report(self, packet): raise OSError("parti")
        def close(self): pass

    controller = A.KeyboardController.__new__(A.KeyboardController)
    controller.handle, controller.current_mode = DeadHandle(), "custom"
    controller.current_hw_brightness, controller.dev_path = 50, b"/dev/nonexistent"
    original, A.find_lighting_path = A.find_lighting_path, lambda: b"/dev/nonexistent"
    try:
        # Un clavier débranché doit être attendu, pas emporter le démon avec lui.
        check("set_hardware_off signale l'échec sans lever", controller.set_hardware_off() is False)
        check("send_frame signale l'échec sans lever",
              controller.send_frame({11: (1, 2, 3)}) is False)
        check("aucun handle inutilisable ne survit",
              controller.handle is None and controller.current_mode is None)
    except Exception as err:
        check("le contrôleur ne lève pas", False, f"{type(err).__name__}: {err}")
    finally:
        A.find_lighting_path = original


# The daemon with its hardware stubbed out: every frame it would send is
# timestamped on stdout, which is enough to time how fast it reacts.
HARNESS = """
import os, sys, time
sys.path.insert(0, {src!r})
import aorus_rgb as A
d = sys.argv[1]
A.CONFIG_DIR, A.CONFIG_FILE, A.PID_FILE = d, os.path.join(d, "config.json"), os.path.join(d, "pid")
def frame(*a, **k):
    print("FRAME %.4f" % time.time(), flush=True)
    return True                 # the loop retries whatever reports a failed send
class Controller:
    current_mode = None
    def connect(self): pass
    set_hardware_reactive = set_hardware_off = send_frame = frame
class Keyboard:
    # A pipe nobody writes to, so select() blocks on it the way a real evdev
    # node does. /dev/null would read as always-ready and spin the loop.
    def __init__(self): self.fd, self._w = os.pipe()
    def fileno(self): return self.fd
    def read(self): return []
    def close(self): os.close(self.fd); os.close(self._w)
class Watcher:
    # Reads the active workspace from a file, so the test can switch it.
    sock = None
    def __init__(self): self.active = None
    def poll(self):
        try:
            with open(os.path.join(d, "workspace")) as f: new = f.read().strip() or None
        except OSError: new = None
        changed, self.active = new != self.active, new
        return changed
A.KeyboardController, A.open_keyboard_input, A.WorkspaceWatcher = Controller, Keyboard, Watcher
A.run_daemon()
"""


def test_reload_latency():
    print("réactivité du démon")
    directory = tempfile.mkdtemp()
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
    harness = os.path.join(directory, "harness.py")
    with open(harness, "w") as f:
        f.write(HARNESS.format(src=src))

    A.CONFIG_DIR, A.CONFIG_FILE = directory, os.path.join(directory, "config.json")
    A.save_config(copy.deepcopy(A.DEFAULT_CONFIG))
    daemon = subprocess.Popen([sys.executable, harness, directory],
                              stdout=subprocess.PIPE, text=True, bufsize=1)

    def next_frame(limit):
        """Timestamp of the daemon's next frame, or None."""
        deadline = time.time() + limit
        while time.time() < deadline:
            if select.select([daemon.stdout], [], [], max(0, deadline - time.time()))[0]:
                line = daemon.stdout.readline()
                if line.startswith("FRAME"):
                    return float(line.split()[-1])
        return None

    try:
        check("le démon démarre et allume le clavier", next_frame(5) is not None)

        delays = []
        for i in range(3):
            start = time.time()
            A.save_config(dict(A.load_config(), brightness=(i % 9) + 1))
            os.kill(daemon.pid, signal.SIGUSR1)
            seen = next_frame(5)
            delays.append((seen - start) if seen else float("inf"))
        worst = max(delays)
        # SIGUSR1 has to break the wait *and* force the re-read. Gating the
        # reload behind the poll interval made this silently 2 s.
        check(f"SIGUSR1 applique la config en {worst * 1000:.1f} ms", worst < 0.2, f"{worst:.3f} s")

        start = time.time()
        A.save_config(dict(A.load_config(), brightness=10))
        seen = next_frame(3 * A.CONFIG_POLL_INTERVAL)
        check("sans signal, le sondage rattrape quand même",
              seen is not None and seen - start < 2.5 * A.CONFIG_POLL_INTERVAL)

        # Une bascule de workspace ne doit rien réémettre quand l'indicateur est
        # éteint : sinon elle coupe le fondu en cours et ré-arme le mode matériel.
        for enabled, expected in ((False, 0), (True, 3)):
            A.save_config(dict(A.load_config(), workspace_key=enabled))
            os.kill(daemon.pid, signal.SIGUSR1)
            next_frame(1.0)
            frames = 0
            for name in ("2", "3", "4"):
                with open(os.path.join(directory, "workspace"), "w") as f:
                    f.write(name)
                if next_frame(1.0) is not None:
                    frames += 1
            check(f"workspace_key={enabled} : {frames} trame(s) sur 3 bascules",
                  frames == expected, f"attendu {expected}")
    finally:
        daemon.kill()
        daemon.wait()


def main():
    for test in (test_inheritance, test_fade_duration, test_workspace, test_theme,
                 test_workspace_events, test_device_access, test_controller_failure,
                 test_reload_latency,
                 test_hostile_config, test_config_store):
        test()
    print(f"\n{len(FAILURES)} échec(s)" + (f" : {', '.join(FAILURES)}" if FAILURES else ""))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
