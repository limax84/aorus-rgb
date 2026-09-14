# ⌨️ Aorus RGB Keyboard Controller for Linux

Contrôleur de rétroéclairage complet et effet réactif touche-par-touche pour ordinateurs portables **Gigabyte Aorus** (testé et optimisé sur **Aorus 17X**, contrôleur USB `0414:8007` sous Arch Linux / Omarchy).

---

## ✨ Fonctionnalités

- 💡 **Rétroéclairage général** : Allumage/extinction, intensité réglable de 0 à 10.
- 🎨 **Palette complète & Thème Omarchy** : Couleurs par nom (`cyan`, `purple`, `red`, `blue`, etc.), détection automatique du thème Omarchy (`theme`), ou codes hexadécimaux (`#00b4d8`, `00b4d8`).
- ⚡ **Effet Flash Réactif** : Effet de flash à la frappe avec fondu progressif (*fade-out*) personnalisable (couleur et intensité sur 10 indépendantes).
- 🚀 **Zéro latence & Zéro CPU en fond noir** : Bascule automatique sur le mode réactif matériel natif (Mode 0x04 à 1000 Hz, 0% CPU, 0 paquet USB) lorsque le fond du clavier est éteint.
- 🌊 **Fondu fluide sans clignotement** : Interpolation *Smoothstep* conçue spécifiquement pour la bande passante USB du contrôleur (93 ms par trame), éliminant tout clignotement ou bégaiement.
- 🧬 **Héritage dynamique (`inherit`)** : Le flash et les touches personnalisées peuvent hériter de la couleur et/ou de l'intensité du clavier ; elles suivent alors automatiquement tout changement de couleur globale ou de thème.
- 💾 **Presets** : Enregistrement, rechargement et suppression de configurations complètes (fond, flash, touches personnalisées) par un simple nom.
- 🔄 **Rechargement instantané** : Communication inter-processus par signal (`SIGUSR1`) pour une mise à jour des paramètres en moins d'une milliseconde.
- ⚙️ **Service Systemd Utilisateur** : Gestion propre en tâche de fond, démarrage automatique avec la session graphique.

---

## 📦 Installation rapide

Clonez le dépôt et exécutez le script d'installation :

```bash
git clone https://github.com/limax84/aorus-rgb.git
cd aorus-rgb
./install.sh
```

Le script installe automatiquement :
1. Les dépendances Python (`hidapi`, `evdev`).
2. Les règles udev pour l'accès aux périphériques USB sans root.
3. Le démon dans `~/.local/share/aorus-rgb/`.
4. Les commandes `aorus-rgb` et `aorus` dans `~/.local/bin/`.
5. Le service systemd utilisateur `aorus-rgb.service` et le démarre.

---

## 🚀 Utilisation

Les commandes peuvent être appelées indifféremment avec `aorus rgb <commande>` ou `aorus-rgb <commande>`.

### État du clavier
```bash
aorus rgb status
```

### Rétroéclairage principal
```bash
aorus rgb on                      # Allume le clavier
aorus rgb off                     # Éteint le clavier
aorus rgb toggle                  # Alterne allumé / éteint
aorus rgb brightness <0-10>       # Règle l'intensité (ex: aorus rgb brightness 5)
aorus rgb color <couleur>         # Règle la couleur (ex: cyan, purple, theme, #ff8800, 00b4d8)
```

### Effet Réactif (Flash à la frappe)
```bash
aorus rgb flash on                # Active l'effet flash
aorus rgb flash off               # Désactive l'effet flash
aorus rgb flash toggle            # Alterne on / off
aorus rgb flash brightness <0-10> # Intensité du flash (ex: aorus rgb flash brightness 10)
aorus rgb flash color <couleur>   # Couleur du flash (ex: white, green, yellow, purple, #ffffff)

# Héritage : le flash suit la couleur / l'intensité du clavier
aorus rgb flash color inherit     # Le flash prend la couleur globale du clavier
aorus rgb flash brightness inherit # Le flash prend l'intensité globale du clavier
aorus rgb flash inherit           # Raccourci : couleur ET intensité héritées
```

### Coloration par touche (Per-Key RGB fixe)
Permet d'assigner une couleur et une intensité fixes à des touches spécifiques en superposition de la couleur globale :

```bash
# Couleur et luminosité combinées (<couleur>:<luminosité> ou <couleur> <luminosité>)
aorus rgb key super,ctrl,alt,shift red:10
aorus rgb key echap,return,suppre,backspace cyan:8
aorus rgb key wasd yellow 10
aorus rgb key fleches orange:9

# Groupes prédéfinis
aorus rgb key modifiers red:10      # super, ctrl, alt, shift
aorus rgb key nav cyan:8            # debut, fin, pageup, pagedown, suppr, retour
aorus rgb key fkeys blue:6          # f1 à f12
aorus rgb key numpad purple:7       # pavé numérique complet
aorus rgb key digits green:10       # chiffres 0 à 9

# Réinitialiser des touches (retour à la couleur globale)
aorus rgb key wasd reset
aorus rgb key super,ctrl reset

# Lister ou tout réinitialiser
aorus rgb key list                  # Affiche les touches personnalisées actives
aorus rgb key clear                 # Efface toutes les personnalisations par touche
```

> **Aliases disponibles (français & anglais)** : `super`, `win`, `ctrl`, `alt`, `shift`, `maj`, `echap`, `escape`, `return`, `entree`, `suppre`, `suppr`, `delete`, `backspace`, `retour`, `tab`, `space`, `espace`, `fleches`, `arrows`, `haut`, `bas`, `gauche`, `droite`, `wasd`, `zqsd`, `fkeys`, `modifiers`, `nav`, `numpad`, `digits`...

### Héritage dynamique (`inherit`)

Partout où une couleur ou une intensité est attendue, la valeur spéciale `inherit` fait suivre le réglage du clavier au lieu de le figer. Synonymes acceptés : `inherit`, `auto`, `null`, ou une valeur vide.

```bash
aorus rgb key wasd red:10           # Rouge fixe, intensité 10
aorus rgb key wasd red:inherit      # Rouge, intensité héritée du clavier
aorus rgb key wasd red:             # Raccourci pour red:inherit
aorus rgb key wasd inherit:10       # Couleur héritée du clavier, intensité 10
aorus rgb key wasd :10              # Raccourci pour inherit:10
aorus rgb key wasd inherit          # Couleur ET intensité héritées
```

Concrètement, `aorus rgb key fkeys inherit:10` met les touches F1–F12 dans la teinte du clavier mais à pleine intensité : elles ressortent sans être d'une autre couleur, et elles suivront le prochain `aorus rgb color`.

> **À noter** : `none` reste le synonyme de *noir* (`aorus rgb color none` éteint le fond) et n'est donc pas une valeur d'héritage.

### Presets

Un preset enregistre la configuration complète : fond, intensité, flash, durée de fondu et toutes les touches personnalisées. Les fichiers sont stockés dans `~/.config/aorus-rgb/presets/<nom>.json`.

```bash
aorus rgb preset save gaming       # Enregistre la configuration active sous "gaming"
aorus rgb preset load gaming       # Recharge et applique le preset
aorus rgb gaming                   # Raccourci équivalent à "preset load gaming"
aorus rgb preset list              # Liste les presets avec leur date et leur contenu
aorus rgb preset delete gaming     # Supprime le preset
```

### Gestion du service
```bash
aorus rgb restart                 # Redémarre le démon en tâche de fond
systemctl --user status aorus-rgb.service
```

---

## 🛠️ Architecture & Protocole USB

Le contrôleur USB Gigabyte `0414:8007` expose plusieurs interfaces :
- **Interface 0** : Événements clavier Boot (`/dev/input/by-id/usb-GIGABYTE_USB-HID_Keyboard_AP0000000003-event-kbd`).
- **Interface 3** : Contrôleur LED USB HID (`hidraw3`, Endpoint 0x06 OUT).

### Modes d'éclairage
1. **Mode Matériel 0x04 (Reactive)** : Utilisé quand le fond est noir. Le microcontrôleur gère nativement l'effet à 1000 Hz pour 7 couleurs prédéfinies.
2. **Mode Matrice 0x33 & 0x12** : Utilisé pour le rétroéclairage couleur et les animations personnalisées.
   - Le paquet de mode `0x33` bascule le contrôleur en mode matrice.
   - Les trames sont transmises via le rapport `0x12` découpé en 8 blocs de 64 octets (512 octets au total pour 128 positions de touches).

Pour plus de détails techniques, consultez [AGENTS.md](AGENTS.md).

---

## 🗑️ Désinstallation

```bash
./uninstall.sh
```

---

## 📄 Licence

MIT License - voir le fichier LICENSE pour plus de détails.
