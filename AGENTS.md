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
| `src/aorus_rgb.py` | Démon **et** bibliothèque partagée : mapping des touches, parsing des couleurs, résolution de l'héritage, `KeyboardController` (USB HID), boucle de rendu. |
| `bin/aorus-rgb` | CLI. N'écrit que la config, ne parle jamais au périphérique. Importe tout le reste de `aorus_rgb`. |
| `bin/aorus` | Dispatcher : `aorus rgb …` → `aorus-rgb …`. |
| `install.sh` / `uninstall.sh` | Dépendances, règle udev, copie vers `~/.local/{bin,share}`, service systemd. |

Règles de découpage à respecter :
- **Une seule source de vérité pour la config** : `CONFIG_DIR`, `DEFAULT_CONFIG`, `load_config()` et `save_config()` vivent dans `src/aorus_rgb.py`. La CLI les importe — ne pas les redéfinir.
- **`bin/aorus-rgb` insère `LOCAL_SRC` puis `REPO_SRC` dans `sys.path`** via `insert(0, …)`, dans cet ordre, pour que le repo prime sur la copie installée dans `~/.local/share/aorus-rgb`. Inverser cette boucle fait silencieusement exécuter l'ancienne version installée lors des tests depuis les sources.
- Côté CLI, `apply(changes, message)` est le seul chemin d'écriture (sauvegarde, signale le démon, affiche l'état) et `fmt_color()` / `fmt_brightness()` les seuls formateurs d'affichage (ils gèrent `inherit`).

### Communication CLI ↔ démon

- **Configuration** : `~/.config/aorus-rgb/config.json`, relue toutes les `CONFIG_POLL_INTERVAL` secondes.
- **Presets** : `~/.config/aorus-rgb/presets/<nom>.json`, écrits et lus uniquement par la CLI ; le démon ne les connaît pas.
- **PID du démon** : `~/.config/aorus-rgb/daemon.pid`.
- La CLI écrit le JSON puis envoie `SIGUSR1` au démon, ce qui débloque son `select()` : la nouvelle configuration s'applique en moins d'une milliseconde, sans redémarrer le service.

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

Trois étages : **clavier → touche personnalisée → flash**. Chaque niveau reprend la valeur du niveau au-dessus pour chaque champ laissé en `inherit`.

- `is_inherit(val)` est le point de vérité unique : `True` pour `None` et pour les chaînes `inherit`, `auto`, `clavier`, `kbl`, `null`, `default` et la chaîne vide.
- **`none` en est volontairement exclu** : c'est l'alias historique de *noir* dans `NAMED_COLORS` (`aorus rgb color none` éteint le fond). Ne pas le réintroduire dans `is_inherit()` sans traiter la régression sur `cmd_color`.
- `parse_color()` renvoie `None` pour toute valeur d'héritage, donc un appelant doit distinguer « couleur invalide » de « héritage » en testant `is_inherit()` **avant**.

### Pipeline de résolution

`resolve_lighting(cfg)` est une fonction pure qui produit un `Lighting` : tout est résolu là, et la boucle du démon n'a plus qu'à rendre et envoyer des trames. Elle enchaîne :

1. `resolve_key_settings(cfg, raw_bg, global_b)` → `{pos: (raw_color, brightness)}`. **Étage 1** : chaque touche personnalisée retombe sur `raw_bg` (couleur de fond non atténuée) et/ou sur l'intensité globale. La brillance reste sur l'échelle 0-10, non pré-multipliée, précisément pour que le flash puisse en hériter ensuite.
2. `compute_key_base_colors(key_settings, effective_bg, backlight_on)` → couleurs de repos (`raw_color × brightness/10`, via `scale_color`).
3. `compute_key_flash_colors(key_settings, base_map, flash_color, flash_brightness)` → couleur de **pic** du flash, par position. **Étage 2** : un `flash_color` hérité prend la `raw_color` de la touche, un `flash_brightness` hérité prend sa `brightness`. Le pic vaut `base + (cible − base) × facteur`, ce qui reproduit à l'identique le comportement d'un flash qui n'hérite de rien.

Le flash est donc résolu **par touche**, jamais globalement. Les champs `Lighting.hw_flash_color` et `Lighting.flash_brightness` ne servent qu'au mode matériel `0x04`, monochrome par construction, et au test d'activation du flash.

`Lighting.state` est la sérialisation JSON de la config : la boucle ne réémet une trame que lorsque cette chaîne change.

Conséquence à connaître : `flash_brightness: "inherit"` fait flasher chaque touche à sa propre intensité de repos — sans effet visible sur une touche déjà à 10/10. Le réglage utile est `flash_color: "inherit"` avec `flash_brightness: 10`.

---

## 6. Boucle de rendu

- `run_daemon()` recharge la config, appelle `resolve_lighting()`, puis choisit son mode :
  - **Mode matériel `0x04`** si `Lighting.is_dark` (fond noir *et* aucune touche personnalisée) : le MCU fait tout, 0 % CPU.
  - **Mode matrice** sinon : `hw_brightness` reste calé à `HW_FULL_BRIGHTNESS` (50) et chaque touche est modulée en RGB logiciel.
- `drain_input()` attend les frappes et renvoie les positions LED pressées ; `MIN_RETRIGGER_DELAY` filtre la répétition clavier, qui donnerait un flash saccadé.
- `render_frame()` compose la trame des fondus en cours et retire ceux qui sont terminés.
- Les constantes de la boucle (`CONFIG_POLL_INTERVAL`, `IDLE_TIMEOUT`, `FADE_TIMEOUT`, `MIN_RETRIGGER_DELAY`, `HW_FULL_BRIGHTNESS`) sont regroupées en tête de `src/aorus_rgb.py`.

---

## 7. Commandes CLI

`aorus rgb` sans argument affiche l'état complet et la liste à jour des commandes ; le README en donne les exemples. Ne pas recopier cette liste ici, elle se périmerait.
