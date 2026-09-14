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
  2. Envoi de 8 blocs consécutifs de 64 octets (512 octets au total) via `hid_write()` sur l'Endpoint `0x06` OUT.
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

## 3. Communication Inter-Processus (CLI & Démon)

- **Fichier de configuration** : `~/.config/aorus-rgb/config.json`
- **Presets** : `~/.config/aorus-rgb/presets/<nom>.json` (un fichier par preset, écrits et lus uniquement par la CLI ; le démon ne les connaît pas).
- **PID du démon** : `~/.config/aorus-rgb/daemon.pid`
- **Signal de mise à jour** : La commande CLI `aorus rgb` modifie le JSON puis envoie un signal `SIGUSR1` au PID du démon.
- Le démon intercepte `SIGUSR1`, débloque instantanément son appel `select()` et applique la nouvelle configuration en moins de 1 ms sans redémarrer le service.
- **Import des sources** : `bin/aorus-rgb` insère `LOCAL_SRC` puis `REPO_SRC` dans `sys.path` via `insert(0, …)`, dans cet ordre, pour que **le repo prime** sur la copie installée dans `~/.local/share/aorus-rgb`. Inverser cette boucle fait silencieusement exécuter l'ancienne version installée lors des tests depuis le repo.

---

## 4. Layout, Mapping et Coloration par Touche (Per-Key)

- Le dictionnaire `EVDEV_TO_LED` dans `src/aorus_rgb.py` mappe les codes evdev Linux (ex: `KEY_SPACE`) vers les positions de LED internes Gigabyte (ex: `42`).
- Le dictionnaire `KEY_ALIASES` et la fonction `resolve_keys()` résolvent les noms usuels français et anglais (avec ou sans accents) vers les identifiants evdev :
  - Modificateurs : `super`, `win`, `ctrl`, `alt`, `shift`, `maj`, `caps`, `fn`...
  - Navigation/édition : `echap`, `escape`, `return`, `entree`, `suppre`, `suppr`, `delete`, `backspace`, `retour`...
  - Direction : `fleches`, `arrows`, `haut`, `bas`, `gauche`, `droite`...
  - Groupes : `wasd`, `zqsd`, `fkeys`, `modifiers`, `nav`, `numpad`, `digits`...
- **Format de configuration `custom_keys`** :
  ```json
  "custom_keys": {
    "KEY_ESC": {"color": [255, 0, 0], "brightness": 10},
    "KEY_LEFTMETA": {"color": [0, 220, 255], "brightness": 8},
    "KEY_W": {"color": "inherit", "brightness": 10},
    "KEY_F1": {"color": [255, 0, 0], "brightness": "inherit"}
  }
  ```
- **Héritage dynamique (`inherit`)** :
  - `is_inherit(val)` (dans `src/aorus_rgb.py`) est le point de vérité unique : renvoie `True` pour `None` et pour les chaînes `inherit`, `auto`, `clavier`, `kbl`, `null`, `default` et la chaîne vide.
  - **`none` est volontairement exclu** de cette liste : c'est l'alias historique de *noir* dans `parse_color()` (`aorus rgb color none` éteint le fond). Ne pas le réintroduire dans `is_inherit()` sans traiter la régression sur `cmd_color`.
  - `parse_color()` renvoie `None` pour toute valeur d'héritage ; les appelants doivent donc distinguer « couleur invalide » et « héritage » via `is_inherit()` **avant** d'appeler `parse_color()`.
  - S'applique à `flash_color`, `flash_brightness` et à chaque entrée de `custom_keys`.
  - Résolution côté démon (`run_daemon`) : `raw_bg` est la couleur de fond **non atténuée**, `b_val` l'intensité globale. Une couleur héritée reçoit `raw_bg` ; une intensité héritée reçoit `b_val`. `compute_key_base_colors(cfg, effective_bg, raw_bg, global_b)` reçoit ces deux valeurs en paramètres.
  - Conséquence utile : `color: "inherit"` + `brightness: 10` donne la teinte du clavier à pleine intensité — la touche ressort sans changer de teinte et suit les changements de `bg_color`.
  - Côté CLI, `fmt_color()` et `fmt_brightness()` sont les helpers d'affichage à réutiliser (ils gèrent le cas `inherit`) ; ne pas réécrire de formatage inline.

- **Rendu & Flash réactif** :
  - `compute_key_base_colors(cfg, effective_bg, raw_bg, global_b)` calcule la couleur de repos de chaque LED.
  - En mode matrice personnalisée, la luminosité matérielle (`hw_b`) reste calée à 50 (pleine échelle), et chaque touche est modulée directement en valeur RGB logicielle.
  - Lorsqu'une touche personnalisée est pressée, elle flashe selon `flash_color` et revient en fondu progressif vers sa couleur personnalisée spécifique.

---

## 5. Commandes CLI

Le binaire `aorus-rgb` (et son alias `aorus rgb`) supporte :
- `aorus rgb on` / `aorus rgb off` / `aorus rgb toggle`
- `aorus rgb brightness <0-10>`
- `aorus rgb color <couleur>` (nom usuel, `theme`, ou code `#hex` / `hex`)
- `aorus rgb flash on` / `aorus rgb flash off` / `aorus rgb flash toggle`
- `aorus rgb flash brightness <0-10|inherit>`
- `aorus rgb flash color <couleur|inherit>`
- `aorus rgb flash inherit` (couleur + luminosité héritées)
- `aorus rgb key <touches> <couleur[:luminosité]> [luminosité]` — chaque partie accepte `inherit` ; `red:`, `:10` et `inherit` seul sont des raccourcis.
- `aorus rgb key <touches> reset`
- `aorus rgb key list`
- `aorus rgb key clear`
- `aorus rgb preset save|load|list|delete <nom>`
- `aorus rgb <nom-de-preset>` (raccourci de `preset load`)
- `aorus rgb status`
- `aorus rgb restart`
