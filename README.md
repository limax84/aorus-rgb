# ⌨️ Aorus RGB Keyboard Controller for Linux

Contrôleur de rétroéclairage complet et effet réactif touche-par-touche pour ordinateurs portables **Gigabyte Aorus** (testé et optimisé sur **Aorus 17X**, contrôleur USB `0414:8007` sous Arch Linux / Omarchy).

---

## ✨ Fonctionnalités

- 💡 **Rétroéclairage général** : Allumage/extinction, intensité réglable de 0 à 10.
- 🎨 **Palette complète & Thème Omarchy** : Couleurs par nom (`cyan`, `purple`, `red`, `blue`, etc.), détection automatique du thème Omarchy (`theme`), ou codes hexadécimaux (`#00b4d8`, `00b4d8`).
- ⚡ **Effet Flash Réactif** : Effet de flash à la frappe avec fondu progressif (*fade-out*) personnalisable (couleur et intensité sur 10 indépendantes).
- 🚀 **Zéro latence & Zéro CPU en fond noir** : Bascule automatique sur le mode réactif matériel natif (Mode 0x04 à 1000 Hz, 0% CPU, 0 paquet USB) lorsque le fond du clavier est éteint.
- 🌊 **Fondu fluide sans clignotement** : Interpolation *Smoothstep* conçue spécifiquement pour la bande passante USB du contrôleur (93 ms par trame), éliminant tout clignotement ou bégaiement.
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
