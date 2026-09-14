# ⌨️ Aorus RGB Keyboard Controller for Linux

Contrôleur de rétroéclairage et effet réactif touche-par-touche pour ordinateurs portables **Gigabyte Aorus** (testé sur **Aorus 17X**, contrôleur USB `0414:8007`, sous Arch Linux / Omarchy).

---

## ✨ Fonctionnalités

- 💡 **Rétroéclairage** : allumage, extinction, intensité de 0 à 10.
- 🎨 **Couleurs** : par nom (`cyan`, `purple`, `red`…), par code hexadécimal (`#00b4d8`, `00b4d8`), ou `theme` pour suivre le thème Omarchy actif.
- 🌈 **Coloration par touche** : couleur et intensité fixes sur les touches de votre choix, par-dessus la couleur globale.
- ⚡ **Flash réactif** : la touche frappée s'illumine puis revient en fondu vers sa couleur de repos.
- 🧬 **Héritage en cascade** : clavier → touche → flash. Ce qu'on laisse en `inherit` suit le niveau au-dessus, donc un flash hérité prend la couleur *de la touche frappée*.
- 💾 **Presets** : configurations complètes enregistrées et rappelées par un nom.
- 🚀 **Zéro CPU en fond noir** : bascule automatique sur le mode réactif matériel (1000 Hz, 0 % CPU, aucun paquet USB) quand le clavier est éteint.
- 🌊 **Fondu sans clignotement** : interpolation *smoothstep* calibrée sur la bande passante du contrôleur (~93 ms par trame).
- 🔄 **Rechargement instantané** : le démon recharge ses réglages en moins d'une milliseconde, sans redémarrage.

---

## 📦 Installation

```bash
git clone https://github.com/limax84/aorus-rgb.git
cd aorus-rgb
./install.sh
```

Le script installe les dépendances Python (`hidapi`, `evdev`), la règle udev donnant accès au périphérique sans root, le démon, les commandes `aorus` et `aorus-rgb`, puis active le service systemd utilisateur.

Désinstallation : `./uninstall.sh`.

---

## 🚀 Utilisation

`aorus rgb <commande>` et `aorus-rgb <commande>` sont équivalents. Sans argument, la commande affiche l'état complet et la liste des commandes.

### Rétroéclairage

```bash
aorus rgb status                  # État complet du clavier
aorus rgb on | off | toggle       # Allume, éteint, alterne
aorus rgb brightness 5            # Intensité 0 à 10
aorus rgb color cyan              # Couleur globale : nom, #hex, ou "theme"
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

### Service

```bash
aorus rgb restart
systemctl --user status aorus-rgb.service
```

---

## 🛠️ Fonctionnement

Le démon lit `~/.config/aorus-rgb/config.json`, résout la cascade d'héritage, et pilote le contrôleur LED (interface USB HID 3) selon deux modes : le mode matériel `0x04`, monochrome mais gratuit en CPU, quand le clavier est noir sans touche personnalisée ; le mode matrice `0x33`/`0x12` sinon, qui transmet les 128 positions de LED par trame.

Le protocole USB, le mapping des touches et les règles d'héritage sont documentés en détail dans [AGENTS.md](AGENTS.md).

---

## 📄 Licence

MIT — voir [LICENSE](LICENSE).
