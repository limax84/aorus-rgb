# Guide Technique et Spécifications Matérielles - Aorus RGB

Ce document est destiné aux agents IA et développeurs travaillant sur la gestion du rétroéclairage RGB du clavier Gigabyte Aorus (notamment Aorus 17X sous Linux / Omarchy).

---

## 1. Contexte Matériel & Architecture USB

- **Périphérique cible** : Contrôleur USB Gigabyte `0414:8007` (parfois accompagné du contrôleur secondaire `0414:8010`).
- **Interfaces USB (`0414:8007`)** :
  - `Interface 0` : Clavier USB Boot (`/dev/input/by-id/usb-GIGABYTE_USB-HID_Keyboard_AP0000000003-event-kbd`, typiquement `event6`).
  - `Interface 1` : Clavier / touches de contrôle (`input2`).
  - `Interface 2` : Souris / contrôles consommateurs (`input2`).
  - `Interface 3` : **Contrôleur d'éclairage RGB** (noeud `hidraw3`, Endpoint `0x85` IN, Endpoint `0x06` OUT).

---

## 2. Protocole USB & Découvertes Clés

### A. Modes Matériels Internes (Mode 0x04 - Reactive)
- **Fonctionnement** : Le firmware du microcontrôleur gère lui-même la détection de frappe et l'effet réactif à 1000 Hz, avec **0 % CPU** et **0 paquet USB**.
- **Couleurs supportées** : Le matériel intègre nativement 7 couleurs fixes :
  - `0x01` : Rouge
  - `0x02` : Vert
  - `0x03` : Jaune
  - `0x04` : Bleu
  - `0x05` : Orange
  - `0x06` : Violet
  - `0x07` : Blanc
- **Format du paquet Feature Report** :
  - `[0x00, 0x08, 0x00, 0x04, 0x01, brightness, color_code, 0x01, checksum]`
  - `brightness` : Octet de luminosité (`0x05` à `0x32`, soit 5 à 50).
  - `checksum` : `(0xFF - sum(bytes[1:8])) & 0xFF`.
- **Usage dans le projet** : Utilisé dès que le fond du clavier est éteint/noir (`is_dark = True`).

### D. Couleur du thème Omarchy
- Le thème actif vit dans `~/.local/state/omarchy/current/theme/` (l'ancien `~/.config/omarchy/current/theme/` est conservé en repli).
- `keyboard.rgb` — un simple `#rrggbb` — est la teinte que le thème destine au clavier ; elle prime sur `accent` de `colors.toml`.
- Le chemin était auparavant codé en dur sur l'ancien emplacement : `color theme` retombait silencieusement sur le cyan par défaut.

### B. Mode Matrice Personnalisée (Mode 0x33 & Rapport 0x12)
- **Activation du mode personnalisé** :
  - Pour basculer depuis un mode matériel (comme Reactive ou Off) vers le contrôle par touche (custom), il faut envoyer **une seule fois** le rapport de mode `0x33` :
    `[0x00, 0x08, 0x00, 0x33, 0x01, hw_brightness, 0x05, 0x01, checksum]`
  - `hw_brightness` : `5` à `50` (échelle 0-10 mappée sur `val * 5`).
  - **ATTENTION (Crucial)** : Ne JAMAIS réenvoyer ce paquet `0x33` à chaque trame d'animation ! S'il est renvoyé à chaque trame, le microcontrôleur réinitialise son moteur d'éclairage, ce qui crée un clignotement / bégaiement violent.
- **Envoi des couleurs de touches (Rapport 0x12)** :
  1. Envoi d'un Feature Report d'en-tête :
     `[0x00, 0x12, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0xE5]`
  2. Envoi de 8 blocs consécutifs de 64 octets (512 octets au total) via `handle.write()` (hidapi) sur l'Endpoint `0x06` OUT.
  3. Chaque touche occupe 4 octets à la position `pos * 4` :
     - `pos*4 + 0` : `0x00`
     - `pos*4 + 1` : Composante Rouge (0..255)
     - `pos*4 + 2` : Composante Verte (0..255)
     - `pos*4 + 3` : Composante Bleue (0..255)
- **PIÈGE ÉVITÉ - Le rapport `0x92`** :
  - Dans les captures Gigabyte Control Center (GCC), un rapport `0x92` apparaît. C'est une commande de **lecture d'état (GET_REPORT)** vers l'hôte.
  - Écrire des données après `0x92` provoquait un blocage USB et une duplication de l'affichage de chaque trame. Ne jamais émettre de paquet `0x92` en écriture.

### C. Contrainte de Fréquence USB (bInterval 10ms)
- L'Endpoint `0x06` OUT a un descripteur USB avec `bInterval = 10` (Full Speed 12 Mbps).
- L'envoi des 8 blocs de 64 octets prend physiquement **~80 à 93 ms** par trame.
- La fréquence maximale de streaming logiciel est donc de **~10.7 FPS**.
- Pour éviter un effet de "marches d'escalier" visuelles à 10 FPS, une interpolation **Smoothstep** (`factor = 1.0 - (3*r^2 - 2*r^3)`) est appliquée sur l'estompement du flash réactif.

---

## 3. Carte du code

| Fichier | Rôle |
|---|---|
| `src/aorus_rgb.py` | Démon **et** bibliothèque partagée : mapping des touches, parsing des couleurs, résolution de l'héritage, store de config et de presets, contrôle du service, `KeyboardController` (USB HID), `WorkspaceWatcher` (IPC Hyprland), boucle de rendu. |
| `src/aorus_tui.py` | Console interactive curses (`aorus rgb config`). Ne parle ni au périphérique ni à systemd directement : elle passe par la bibliothèque. |
| `bin/aorus-rgb` | CLI. N'écrit que la config, ne parle jamais au périphérique. Importe tout le reste de `aorus_rgb`. |
| `bin/aorus` | Dispatcher : `aorus rgb …` → `aorus-rgb …`. |
| `tests/test_aorus_rgb.py` | Tests de régression sans dépendance : `python3 tests/test_aorus_rgb.py`. Couvre la cascade, l'étage workspace, le thème, l'analyse des événements Hyprland et les invariants de la config. Les couches USB et curses en sont absentes (matériel requis). |
| `install.sh` / `uninstall.sh` | Dépendances, règle udev, copie vers `~/.local/{bin,share}`, service systemd. |

Règles de découpage à respecter :
- **Une seule source de vérité, dans `src/aorus_rgb.py`**, pour tout ce que plus d'un appelant utilise : config (`CONFIG_DIR`, `DEFAULT_CONFIG`, `load_config()`, `save_config()`, `update_config()`), presets (`read_preset()`, `write_preset()`, `list_presets()`, `delete_preset()`), contrôle du service (`notify_daemon()`, `is_service_active()`, `restart_service()`, `daemon_pid()`), parsing (`parse_color_arg()`, `parse_brightness_arg()`) et affichage (`fmt_color()`, `fmt_brightness()`, `describe_preset()`). La CLI et la TUI les importent — ne pas les redéfinir.
- **`bin/aorus-rgb` insère `LOCAL_SRC` puis `REPO_SRC` dans `sys.path`** via `insert(0, …)`, dans cet ordre, pour que le repo prime sur la copie installée dans `~/.local/share/aorus-rgb`. Inverser cette boucle fait silencieusement exécuter l'ancienne version installée lors des tests depuis les sources.
- Côté CLI, `apply(changes, message)` est le seul chemin d'écriture ; côté TUI, `Console.commit(changes, message)`. Les deux passent par `update_config()` — **lecture, fusion, écriture** — et signalent le démon. Ne jamais réécrire une config gardée en mémoire : la CLI et la console peuvent tourner en même temps, et une écriture en bloc annulerait silencieusement les changements de l'autre. La console relit d'ailleurs le fichier à chaque redessin, ce qui lui fait afficher en direct ce que la CLI écrit.
- `install.sh` copie `src/*.py` en bloc : ajouter un module à `src/` suffit, rien à déclarer ailleurs.

### Communication CLI / TUI ↔ démon

- **Configuration** : `~/.config/aorus-rgb/config.json`, relue sur `SIGUSR1` et, en filet de sécurité, toutes les `CONFIG_POLL_INTERVAL` secondes.
- **Presets** : `~/.config/aorus-rgb/presets/<nom>.json`. Le démon ne les connaît pas : un preset est chargé en écrivant ses champs dans la config.
- **PID du démon** : `~/.config/aorus-rgb/daemon.pid`. `daemon_pid()` vérifie `/proc/<pid>/cmdline` avant de signaler : un fichier PID périmé ne doit jamais faire envoyer `SIGUSR1` au processus qui a hérité de ce PID.
- L'écrivain écrit le JSON puis envoie `SIGUSR1`, ce qui débloque le `select()` du démon **via un self-pipe** (`signal.set_wakeup_fd`) : sans lui, PEP 475 ferait simplement reprendre l'attente avec le temps restant au lieu de réveiller la boucle.

### Invariants de la config — à ne pas casser

- **`save_config()` écrit dans un fichier temporaire puis `os.replace()`.** Le démon relit ce fichier pendant que la CLI l'écrit ; une écriture en place lui ferait lire du JSON tronqué.
- **`load_config()` ne réécrit jamais un fichier qu'il n'a pas su lire.** L'ancienne version retombait sur `save_config(DEFAULT_CONFIG)` en cas d'erreur de lecture : une seule lecture malheureuse effaçait toutes les touches personnalisées de l'utilisateur.
- `save_config()` filtre sur les clés de `DEFAULT_CONFIG` : les réglages devenus obsolètes disparaissent d'eux-mêmes, et une clé inconnue ne survit pas à un enregistrement.

---

## 4. Layout, mapping et coloration par touche

- `EVDEV_TO_LED` mappe les codes evdev (`KEY_SPACE`) vers les positions de LED Gigabyte (`42`). `VALID_POSITIONS` en est l'ensemble trié.
- `KEY_ALIASES` et `resolve_keys()` résolvent les noms usuels français et anglais, avec ou sans accents : modificateurs (`super`, `ctrl`, `maj`…), navigation (`echap`, `entree`, `suppre`…), directions (`fleches`, `haut`…) et groupes (`wasd`, `zqsd`, `fkeys`, `modifiers`, `nav`, `numpad`, `digits`, `all`).
- Format de `custom_keys` dans la config :
  ```json
  "custom_keys": {
    "KEY_ESC": {"color": [255, 0, 0], "brightness": 10},
    "KEY_W":   {"color": "inherit",   "brightness": 10},
    "KEY_F1":  {"color": [255, 0, 0], "brightness": "inherit"}
  }
  ```

---

## 5. Héritage en cascade (`inherit`)

Trois étages : **clavier → touche personnalisée → flash**. Chaque niveau reprend la valeur du niveau au-dessus pour chaque champ laissé en `inherit`. L'indicateur de workspace se greffe au-dessus des touches personnalisées, mais ne touche que l'intensité (§ 7).

- `is_inherit(val)` est le point de vérité unique : `True` pour `None` et pour les chaînes `inherit`, `auto`, `clavier`, `kbl`, `null`, `default` et la chaîne vide.
- **`none` en est volontairement exclu** : c'est l'alias historique de *noir* dans `NAMED_COLORS` (`aorus rgb color none` éteint le fond). Ne pas le réintroduire dans `is_inherit()` sans traiter la régression sur `cmd_color`.
- `parse_color()` renvoie `None` pour toute valeur d'héritage, donc un appelant doit distinguer « couleur invalide » de « héritage » en testant `is_inherit()` **avant**.

### Pipeline de résolution

`resolve_lighting(cfg)` est une fonction pure qui produit un `Lighting` : tout est résolu là, et la boucle du démon n'a plus qu'à rendre et envoyer des trames. Elle enchaîne :

1. `resolve_key_settings(cfg, raw_bg, global_b, ws_pos)` → `{pos: (raw_color, brightness)}`. **Étage 1** : chaque touche personnalisée retombe sur `raw_bg` (couleur de fond non atténuée) et/ou sur l'intensité globale. La brillance reste sur l'échelle 0-10, non pré-multipliée, précisément pour que le flash puisse en hériter ensuite. `ws_pos`, s'il est fourni, écrase ensuite la seule intensité de cette position.
2. `compute_key_base_colors(key_settings, effective_bg, backlight_on, lit_positions)` → couleurs de repos (`raw_color × brightness/10`, via `scale_color`). `lit_positions` est la porte de sortie qui permet à l'indicateur de workspace de rester allumé alors que le rétroéclairage est coupé.
3. `compute_key_flash_colors(key_settings, base_map, flash_color, flash_brightness)` → couleur de **pic** du flash, par position. **Étage 2** : un `flash_color` hérité prend la `raw_color` de la touche, un `flash_brightness` hérité prend sa `brightness`. Le pic vaut `base + (cible − base) × facteur`, ce qui reproduit à l'identique le comportement d'un flash qui n'hérite de rien.

Le flash est donc résolu **par touche**, jamais globalement. Les champs `Lighting.hw_flash_color` et `Lighting.flash_brightness` ne servent qu'au mode matériel `0x04`, monochrome par construction, et au test d'activation du flash.

La boucle ne réémet une trame que lorsque son *empreinte* change : `(config sérialisée, workspace actif, mtime du thème)`. Le mtime du thème n'est calculé que si `bg_color` vaut littéralement `"theme"` — c'est ce qui rend `aorus rgb color theme` réellement dynamique au lieu de figer l'accent du jour où la commande a été tapée.

Conséquence à connaître : `flash_brightness: "inherit"` fait flasher chaque touche à sa propre intensité de repos — sans effet visible sur une touche déjà à 10/10. Le réglage utile est `flash_color: "inherit"` avec `flash_brightness: 10`.

---

## 6. Boucle de rendu

- `run_daemon()` recharge la config, appelle `resolve_lighting()`, puis choisit son mode :
  - **Mode matériel `0x04`** si `Lighting.is_dark` (fond noir *et* aucune touche personnalisée) : le MCU fait tout, 0 % CPU.
  - **Mode matrice** sinon : `hw_brightness` reste calé à `HW_FULL_BRIGHTNESS` (50) et chaque touche est modulée en RGB logiciel.
- `drain_input()` attend les frappes et renvoie les positions LED pressées ; `MIN_RETRIGGER_DELAY` filtre la répétition clavier, qui donnerait un flash saccadé.
- `render_frame()` compose la trame des fondus en cours et retire ceux qui sont terminés.
- `wait_events()` est l'unique `select()` : périphérique evdev, socket d'événements Hyprland et self-pipe des signaux y sont attendus ensemble. Il renvoie `None` quand le clavier a disparu, et la boucle le rouvre après `DEVICE_RETRY_DELAY` au lieu de mourir dans une boucle de redémarrage systemd.
- **Reprise de veille** : une itération plus longue que `SUSPEND_GAP` signifie qu'on sort de suspension. Le contrôleur est reconnecté et l'empreinte remise à `None`, ce qui force le réenvoi d'une trame — sans cela le clavier restait sur l'état que le MCU avait perdu.
- Les constantes de la boucle (`CONFIG_POLL_INTERVAL`, `IDLE_TIMEOUT`, `FADE_TIMEOUT`, `MIN_RETRIGGER_DELAY`, `HW_FULL_BRIGHTNESS`, `SUSPEND_GAP`, `DEVICE_RETRY_DELAY`) sont regroupées en tête de `src/aorus_rgb.py`.
- `resolve_fade_duration()` plancher à 0,05 s : une `fade_duration` à zéro dans la config divisait par zéro en plein fondu.

---

---

## 7. Intégration Hyprland (indicateur de workspace)

- `WorkspaceWatcher` suit le workspace actif sur la socket d'événements `$XDG_RUNTIME_DIR/hypr/<signature>/.socket2.sock`, et lit l'état initial via `j/activeworkspace` sur `.socket.sock`.
- La signature vient de `HYPRLAND_INSTANCE_SIGNATURE` quand systemd l'a importée (c'est le cas sous uwsm), sinon du répertoire d'instance le plus récent : un service utilisateur n'hérite pas toujours de l'environnement du compositeur.
- Événements pris en compte : `workspace>>`, `workspacev2>>` et `focusedmon>>`. Le watcher se reconnecte tout seul si Hyprland redémarre, et reste inerte hors Hyprland.
- `workspace_led_pos()` fait correspondre le **nom** du workspace à la touche chiffre : `3` → `KEY_3`, et `10` → `KEY_0`, parce que le binding Omarchy est `SUPER + code:N` sur `1..9` puis `0`. Un workspace nommé (`Work`) n'allume rien.
- L'indicateur se règle comme le flash : `workspace_color` et `workspace_brightness` écrasent chacun la cascade, ou la laissent passer sur `inherit`. Par défaut `workspace_color` vaut `inherit`, donc la touche garde sa couleur et ne fait que monter en intensité. Une couleur explicite écrase aussi une touche personnalisée — c'est l'étage le plus haut.
- Il n'est jamais écrit dans `custom_keys` : c'est un étage calculé au rendu, sinon les presets et la config se pollueraient à chaque bascule.
- Sur un clavier éteint, l'indicateur est **abandonné** pour préserver le mode matériel à 0 % CPU, sauf si `workspace_dark` est vrai : cette option assume explicitement le passage en mode matrice.

---

## 8. Console de configuration (`src/aorus_tui.py`)

- Lancée par `aorus rgb config`. Bibliothèque standard uniquement (`curses`) : aucune dépendance ajoutée au projet.
- Structure en menus imbriqués, plus un plan du clavier pour les touches personnalisées et un manuel intégré (`?`).
- **Tout écran passe par `Console.frame(titre, sous-titre)`**, qui dessine le cadre et renvoie `(première ligne de contenu, largeur intérieure)`. `AORUS RGB` ancre le coin haut-gauche, le nom de l'écran le coin haut-droit. Le bas du cadre porte le séparateur, le rappel des touches et la bordure, plus une ligne de message **seulement quand il y a un message** : une place réservée en permanence laisserait une ligne vide au-dessus des touches la plupart du temps. Seul le séparateur bouge ; les touches et la bordure restent ancrées en bas.
- `Console.write()` est le seul point de dessin : il borne à la fenêtre et avale le `curses.error` de la toute dernière cellule, qui est un faux positif. Ne pas appeler `addnstr()` directement, la bordure droite se ferait manger.
- `Console.body_rows`, posé par `frame()`, est la hauteur de contenu réellement disponible ; le manuel s'en sert pour paginer. Ne pas la recalculer depuis `getmaxyx()`, elle dépend de la présence du message.
- `MIN_WIDTH` et `MIN_HEIGHT` sont **dérivés de `KEYBOARD_ROWS`**, pas écrits en dur : ajouter une touche au plan met à jour la contrainte toute seule.
- **`KeyboardInterrupt` est rattrapé dans `run_tui()`** : Ctrl+C est une façon légitime de fermer la console. `curses.wrapper()` a déjà rendu le terminal à ce moment-là, une trace d'appels par-dessus ne serait que du bruit.
- `KEYBOARD_ROWS` est la disposition physique affichée ; c'est de la présentation, elle n'a donc rien à faire dans `aorus_rgb.py`. `KEY_COMPOSE` en est volontairement absent : il partage la LED 66 avec `KEY_MENU` et ne serait qu'un second arrêt du curseur sur la même lumière.
- `Palette` convertit le RGB vers le cube 256 couleurs et alloue les paires curses à la demande : chaque touche s'affiche dans sa vraie couleur résolue.
- Toute modification est écrite et signalée immédiatement (`Console.commit`), le vrai clavier servant d'aperçu ; `u` annule sur une pile de 30 états.

---

## 9. Commandes CLI

`aorus rgb` sans argument affiche l'état complet et la liste à jour des commandes ; le README en donne les exemples. Ne pas recopier cette liste ici, elle se périmerait.
