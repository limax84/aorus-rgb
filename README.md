# ⌨️ Aorus RGB Keyboard Controller for Linux

Contrôleur de rétroéclairage et effet réactif touche-par-touche pour ordinateurs portables **Gigabyte Aorus** (testé sur **Aorus 17X**, contrôleur USB `0414:8007`, sous Arch Linux / Omarchy).

---

## ✨ Fonctionnalités

- 🖥️ **Console de configuration** : `aorus rgb config` ouvre une interface dans le terminal, avec un plan du clavier où l'on peint les touches au curseur.
- 💡 **Rétroéclairage** : allumage, extinction, intensité de 0 à 10.
- 🎨 **Couleurs** : par nom (`cyan`, `purple`, `red`…), par code hexadécimal (`#00b4d8`, `00b4d8`), ou `theme` pour suivre le thème Omarchy actif.
- 🌈 **Coloration par touche** : couleur et intensité fixes sur les touches de votre choix, par-dessus la couleur globale.
- ⚡ **Flash réactif** : la touche frappée s'illumine puis revient en fondu vers sa couleur de repos.
- 🧬 **Héritage en cascade** : clavier → touche → flash. Ce qu'on laisse en `inherit` suit le niveau au-dessus, donc un flash hérité prend la couleur *de la touche frappée*.
- 💾 **Presets** : configurations complètes enregistrées et rappelées par un nom.
- 🪟 **Indicateur de workspace** : sous Hyprland, la touche chiffre du workspace actif ressort, avec sa propre couleur et intensité.
- 🚀 **Zéro CPU en fond noir** : bascule automatique sur le mode réactif matériel (1000 Hz, 0 % CPU, aucun paquet USB) quand le clavier est éteint.
- 🌊 **Fondu sans clignotement** : interpolation *smoothstep* calibrée sur la bande passante du contrôleur (~93 ms par trame).
- 🔄 **Rechargement instantané** : le démon recharge ses réglages en moins d'une milliseconde, sans redémarrage.

---

## 🔌 Compatibilité

Ce projet pilote un contrôleur précis : le **Gigabyte `0414:8007`**, présent sur
certains portables Aorus (développé et testé sur un **Aorus 17X**). Il ne
fonctionne pas sur d'autres claviers RGB.

Pour savoir si votre machine est concernée, avant même d'installer :

```bash
lsusb | grep 0414:8007        # une ligne = contrôleur présent
```

Il faut par ailleurs Linux avec **systemd** (service utilisateur) et **udev**
(accès au périphérique sans root). L'indicateur de workspace demande en plus
**Hyprland** ; tout le reste fonctionne sans.

---

## 📦 Installation

```bash
git clone https://github.com/limax84/aorus-rgb.git
cd aorus-rgb
./install.sh
```

Le script est **idempotent** : relancez-le après un `git pull`, il met à jour ce
qui a changé. Il installe les dépendances Python (`hidapi`, `evdev`), la règle
udev donnant accès au périphérique sans root, le démon et la console, les
commandes `aorus` et `aorus-rgb`, puis active le service systemd utilisateur.
Il demande `sudo` **une fois**, uniquement pour poser la règle udev.

Il termine par un diagnostic, que vous pouvez relancer à tout moment :

```bash
aorus rgb doctor
```

```
  ✓ Contrôleur d'éclairage  0414:8007 interface 3 sur /dev/hidraw3
  ✓ Accès au contrôleur     ouverture en écriture réussie
  ✓ Clavier de frappe       GIGABYTE USB-HID Keyboard sur /dev/input/event6
  ✓ Règle udev              /etc/udev/rules.d/60-gigabyte-keyboard.rules
  ✓ Service systemd         aorus-rgb.service actif
```

Chaque ligne fausse est accompagnée du correctif. Si la règle udev vient d'être
posée, rebranchez le clavier ou redémarrez pour qu'elle s'applique.

Désinstallation : `./uninstall.sh` (retire aussi la règle udev ; vos réglages
restent dans `~/.config/aorus-rgb`).

### 🔒 Accès au périphérique

La règle udev accorde l'accès via `TAG+="uaccess"`, c'est-à-dire une ACL pour
l'utilisateur de la session locale active — la façon normale de partager un
périphérique d'entrée. Son préfixe `60-` compte : systemd applique le tag depuis
`73-seat-late.rules`, et udev lit les fichiers dans l'ordre des noms, donc un tag
posé par un fichier `99-` n'aurait aucun effet.

> **Mise à jour importante.** Les versions antérieures à cette règle utilisaient
> `MODE="0666"`, qui donnait le même accès à **tout processus local** : sur le
> nœud `event*` du clavier, n'importe quel programme pouvait lire toutes les
> frappes, mots de passe compris. Si vous avez installé le projet avant, relancez
> `./install.sh` : il pose la nouvelle règle **et supprime l'ancienne**
> `99-gigabyte-keyboard.rules`, qui accorderait encore cet accès si elle restait.
> `aorus rgb doctor` le signale tant que ce n'est pas fait.

---

## 🚀 Utilisation

`aorus rgb <commande>` et `aorus-rgb <commande>` sont équivalents. Sans argument, la commande affiche l'état complet et la liste des commandes.

### Console de configuration

```bash
aorus rgb config                  # Ouvre la console interactive
```

Une interface plein écran qui reste ouverte tant qu'on ne la quitte pas. Elle est
organisée en menus — rétroéclairage, flash, touches, presets, intégration OS — et
**chaque modification part vers le clavier immédiatement** : le vrai clavier est
l'aperçu. `u` annule la dernière action, `q` revient en arrière puis quitte.

La console et la ligne de commande peuvent servir en même temps : chacune n'écrit
que ce qu'elle change, et la console affiche en direct ce que l'autre a fait.

L'entrée « Touches personnalisées » ouvre un plan du clavier où chaque touche
s'affiche dans sa couleur réelle :

```
 Esc  F1  F2  F3  F4  F5  F6  F7  F8  F9 F10 F11 F12   Pau Del Hom PgU PgD End
  `   1   2   3   4   5   6   7   8   9   0   -   =  Bks   Num  /   *   -
 Tab  Q   W   E   R   T   Y   U   I   O   P   [   ]   \     7   8   9   +
 Cap  A   S   D   F   G   H   J   K   L   ;   '  Ent    4   5   6
 Sft  <   Z   X   C   V   B   N   M   ,   .   /  Sft  ↑     1   2   3  Ent
 Ctl  Fn Sup Alt Spc AGr Mnu Ctl  ←   ↓   →     0   .
```

| Touche | Effet |
|---|---|
| `←→↑↓` | Déplacer le curseur |
| `espace` | Marquer / démarquer une touche (les actions s'appliquent à toutes les marques) |
| `g` | Marquer un groupe entier (`wasd`, `fkeys`, `modifiers`, `nav`…) |
| `a` | Tout marquer / tout démarquer |
| `c` / `b` | Couleur / intensité des touches visées |
| `p` | Mode pinceau : on choisit une couleur, puis chaque déplacement peint la touche traversée |
| `r` | Réinitialiser (retour à la couleur globale) |
| `u` | Annuler |
| `?` | Manuel intégré |
| `q` | Retour au menu |

`?` ouvre à tout moment un manuel qui reprend les touches de la console, les
valeurs acceptées, la cascade d'héritage et l'ensemble des commandes de la
ligne de commande. `Ctrl+C` ferme la console aussi bien que `q`.

Le plan du clavier demande un terminal d'au moins 82 × 17 ; les menus s'accommodent
de bien moins.

### Rétroéclairage

```bash
aorus rgb status                  # État complet du clavier
aorus rgb on | off | toggle       # Allume, éteint, alterne
aorus rgb brightness 5            # Intensité 0 à 10
aorus rgb color cyan              # Couleur globale : nom, #hex, ou "theme"
aorus rgb color theme             # Suit le thème Omarchy, y compris ses changements
```

### Coloration par touche

Assigne une couleur et une intensité fixes à certaines touches, par-dessus la couleur globale.

```bash
aorus rgb key super,ctrl,alt,shift red:10
aorus rgb key echap,return,suppre,backspace cyan:8
aorus rgb key wasd yellow 10        # <couleur> <luminosité> équivaut à <couleur>:<luminosité>

# Groupes prédéfinis
aorus rgb key modifiers red:10      # super, ctrl, alt, shift
aorus rgb key nav cyan:8            # debut, fin, pageup, pagedown, suppr, retour
aorus rgb key fkeys blue:6          # f1 à f12
aorus rgb key numpad purple:7       # pavé numérique
aorus rgb key digits green:10       # chiffres 0 à 9

aorus rgb key wasd reset            # Retour à la couleur globale
aorus rgb key list                  # Touches personnalisées actives
aorus rgb key clear                 # Efface toutes les personnalisations
```

> **Aliases (français & anglais)** : `super`, `win`, `ctrl`, `alt`, `shift`, `maj`, `echap`, `escape`, `return`, `entree`, `suppre`, `suppr`, `delete`, `backspace`, `retour`, `tab`, `space`, `espace`, `fleches`, `arrows`, `haut`, `bas`, `gauche`, `droite`, `wasd`, `zqsd`, `fkeys`, `modifiers`, `nav`, `numpad`, `digits`…

### Flash à la frappe

```bash
aorus rgb flash on | off | toggle
aorus rgb flash brightness 10     # Intensité 0 à 10, ou "inherit"
aorus rgb flash color white       # Couleur, ou "inherit"
aorus rgb flash inherit           # Raccourci : couleur ET intensité héritées
```

### Héritage en cascade (`inherit`)

Partout où une couleur ou une intensité est attendue, `inherit` reprend le réglage du niveau au-dessus au lieu de le figer. Synonymes : `auto`, `null`, ou une valeur vide.

```
clavier (bg_color + brightness)
   └─> touche personnalisée (custom_keys[*].color + brightness)
          └─> flash (flash_color + flash_brightness)
```

L'indicateur de workspace se greffe au-dessus de la touche personnalisée, avec
les mêmes règles : `workspace_color` et `workspace_brightness` écrasent, ou
héritent de ce que la touche avait résolu.

```bash
aorus rgb key wasd red:10         # Rouge, intensité 10 : rien n'est hérité
aorus rgb key wasd red:           # Rouge, intensité héritée du clavier
aorus rgb key wasd :10            # Couleur héritée du clavier, intensité 10
aorus rgb key wasd inherit        # Couleur et intensité héritées
```

Sur un clavier cyan où Échap est rouge, `aorus rgb flash color inherit` fait flasher Échap vers le rouge et toutes les touches non personnalisées vers le cyan. De même, `aorus rgb key fkeys inherit:10` met F1–F12 dans la teinte du clavier mais à pleine intensité : elles ressortent sans changer de couleur, et suivront le prochain `aorus rgb color`.

> **À noter** : `flash brightness inherit` fait flasher chaque touche à sa propre intensité de repos — donc sans effet visible sur une touche déjà à 10/10. Pour un flash hérité bien visible, combinez `flash color inherit` et `flash brightness 10`.
>
> `none` reste un synonyme de *noir* (`aorus rgb color none` éteint le fond) et n'est donc pas une valeur d'héritage.

### Presets

Un preset enregistre la configuration complète — fond, intensité, flash, durée de fondu et toutes les touches personnalisées — dans `~/.config/aorus-rgb/presets/<nom>.json`.

```bash
aorus rgb preset save gaming      # Enregistre la configuration active
aorus rgb preset load gaming      # Recharge et applique
aorus rgb gaming                  # Raccourci équivalent
aorus rgb preset list             # Presets disponibles, avec leur contenu
aorus rgb preset delete gaming
```

### Indicateur de workspace (Hyprland)

La touche du chiffre correspondant au workspace actif ressort du lot — le même
chiffre que `Super + N`. Couleur et intensité se règlent comme celles du flash,
et `inherit` laisse passer ce que la cascade avait résolu pour cette touche.

```bash
aorus rgb workspace on | off | toggle
aorus rgb workspace color white     # Couleur de la touche active, ou "inherit"
aorus rgb workspace brightness 10   # Intensité de la touche active
aorus rgb workspace dark on         # Montrer l'indicateur même clavier éteint

aorus rgb workspace cyan            # Raccourcis : une couleur ou une intensité
aorus rgb workspace 8               # se passent du sous-mot
```

Par défaut `workspace color` vaut `inherit` : le chiffre actif garde sa couleur
et ne fait que monter en intensité, donc la personnalisation des chiffres est
préservée. Une couleur explicite prend le dessus sur tout, y compris sur une
touche personnalisée — c'est l'étage le plus haut de la cascade.

> Par défaut, un clavier éteint reste en mode matériel (0 % CPU) et l'indicateur
> est masqué. `workspace dark on` l'affiche quand même, au prix du passage en
> mode matrice. Un workspace nommé (plutôt que numéroté) n'allume rien.

### Service

```bash
aorus rgb status                  # État du clavier
aorus rgb doctor                  # Matériel, permissions, service
aorus rgb restart                 # Redémarre le démon
systemctl --user status aorus-rgb.service
journalctl --user -u aorus-rgb.service -f
```

---

## 🩺 Dépannage

| Symptôme | Cause probable | Correctif |
|---|---|---|
| `aorus rgb doctor` : contrôleur absent | machine non équipée du `0414:8007` | `lsusb \| grep 0414` pour confirmer ; le projet ne peut rien faire |
| `doctor` : accès au contrôleur refusé | règle udev absente ou non appliquée | `./install.sh`, puis rebranchez le clavier ou redémarrez |
| `doctor` : règle udev périmée | règle d'une version antérieure | `./install.sh` la remplace |
| Le clavier ne réagit pas | service arrêté | `aorus rgb restart`, puis `journalctl --user -u aorus-rgb.service` |
| Le flash ne part pas | clavier de frappe illisible | `doctor` le signale ; règle udev, ou appartenance au groupe `input` |
| `aorus : commande introuvable` | `~/.local/bin` hors du `PATH` | ajoutez-le à votre shell |
| Workspace « Hyprland injoignable » | pas sous Hyprland, ou session non détectée | fonctionnalité optionnelle ; le reste marche |

Le démon **n'a pas besoin du clavier pour démarrer** : s'il est absent ou
débranché, il attend et reprend dès son retour, sans boucler sur des
redémarrages.

---

## 🧑‍💻 Développement

```bash
git clone https://github.com/limax84/aorus-rgb.git && cd aorus-rgb
python3 tests/test_aorus_rgb.py        # aucune dépendance en plus, aucun matériel requis
./bin/aorus-rgb status                 # la CLI du dépôt prime sur la copie installée
```

`bin/aorus-rgb` place les sources du dépôt avant `~/.local/share/aorus-rgb` dans
`sys.path` : lancée depuis le dépôt, la commande exécute **le code que vous êtes
en train de modifier**. Le démon, lui, tourne sur la copie installée — après
avoir touché à `src/`, relancez `./install.sh` pour qu'il en tienne compte.

La suite de tests couvre la cascade d'héritage, l'indicateur de workspace, le
thème, l'analyse des événements Hyprland, la réactivité du démon et les
invariants de la configuration. Les couches USB et curses en sont absentes :
elles demandent le vrai matériel et un vrai terminal.

Les détails du protocole USB, du mapping des touches et des règles d'héritage
sont dans [AGENTS.md](AGENTS.md).

---

## 🛠️ Fonctionnement

Le démon lit `~/.config/aorus-rgb/config.json`, résout la cascade d'héritage, et pilote le contrôleur LED (interface USB HID 3) selon deux modes : le mode matériel `0x04`, monochrome mais gratuit en CPU, quand le clavier est noir sans touche personnalisée ; le mode matrice `0x33`/`0x12` sinon, qui transmet les 128 positions de LED par trame.

Il n'émet une trame que lorsque quelque chose change réellement — configuration, workspace actif ou thème — et attend le reste du temps dans un `select()` : au repos, sa consommation CPU est nulle.

Le protocole USB, le mapping des touches et les règles d'héritage sont documentés en détail dans [AGENTS.md](AGENTS.md).

---

## 📄 Licence

MIT — voir [LICENSE](LICENSE).
