#!/usr/bin/env bash
# Installe le démon, les commandes et le service utilisateur.
# Idempotent : relancez-le après un git pull, il met à jour ce qui a changé.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_DIR="$HOME/.local/share/aorus-rgb"
BIN_DIR="$HOME/.local/bin"
UDEV_RULE="/etc/udev/rules.d/99-gigabyte-keyboard.rules"

echo "═══════════════════════════════════════════════════════"
echo "        Installation de Aorus RGB Keyboard Daemon       "
echo "═══════════════════════════════════════════════════════"

# 1. Dépendances Python
echo "[1/5] Modules Python (hidapi, evdev)..."
if python3 -c "import hid, evdev" 2>/dev/null; then
    echo "✓ Déjà installés."
else
    echo "Installation des dépendances..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm python-hidapi python-evdev
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y python3-hid python3-evdev
    else
        pip install --user hidapi evdev
    fi
    python3 -c "import hid, evdev" || {
        echo "✗ Les modules restent introuvables. Installez python-hidapi et python-evdev, puis relancez."
        exit 1
    }
fi

# 2. Règle udev. Elle est comparée, pas seulement testée pour sa présence :
#    une règle périmée laissait les versions antérieures exposer les frappes
#    clavier à tous les processus locaux (MODE="0666").
echo "[2/5] Permissions du périphérique (udev)..."
if [ ! -d /etc/udev/rules.d ]; then
    echo "⚠ Pas de /etc/udev/rules.d : système sans udev, étape ignorée."
elif cmp -s "$REPO_DIR/udev/99-gigabyte-keyboard.rules" "$UDEV_RULE"; then
    echo "✓ Règle à jour."
else
    if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
    if $SUDO cp "$REPO_DIR/udev/99-gigabyte-keyboard.rules" "$UDEV_RULE"; then
        $SUDO udevadm control --reload-rules
        $SUDO udevadm trigger --subsystem-match=hidraw --subsystem-match=input
        echo "✓ Règle installée et rechargée."
    else
        echo "⚠ Installation manuelle nécessaire :"
        echo "   sudo cp $REPO_DIR/udev/99-gigabyte-keyboard.rules $UDEV_RULE"
        echo "   sudo udevadm control --reload-rules && sudo udevadm trigger"
    fi
fi

# 3. Démon et console
echo "[3/5] Démon et console dans $SHARE_DIR..."
mkdir -p "$SHARE_DIR"
cp "$REPO_DIR"/src/*.py "$SHARE_DIR/"
cp "$REPO_DIR/udev/99-gigabyte-keyboard.rules" "$SHARE_DIR/"   # référence pour `aorus rgb doctor`
chmod +x "$SHARE_DIR/aorus_rgb.py"
echo "✓ Installés."

# 4. Commandes
echo "[4/5] Commandes dans $BIN_DIR..."
mkdir -p "$BIN_DIR"
install -m 755 "$REPO_DIR/bin/aorus-rgb" "$REPO_DIR/bin/aorus" "$BIN_DIR/"
echo "✓ 'aorus' et 'aorus-rgb' installées."
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "⚠ $BIN_DIR n'est pas dans votre PATH. Ajoutez-le à votre shell." ;;
esac

# 5. Service utilisateur
echo "[5/5] Service systemd utilisateur..."
mkdir -p "$HOME/.config/systemd/user"
install -m 644 "$REPO_DIR/systemd/aorus-rgb.service" "$HOME/.config/systemd/user/aorus-rgb.service"
systemctl --user daemon-reload
systemctl --user enable aorus-rgb.service >/dev/null
systemctl --user restart aorus-rgb.service
echo "✓ Service activé et démarré."

echo ""
echo "═══════════════════════════════════════════════════════"
"$BIN_DIR/aorus-rgb" doctor || {
    echo ""
    echo "Installation terminée, mais le diagnostic signale un problème ci-dessus."
    echo "Si la règle udev vient d'être posée, rebranchez le clavier ou redémarrez."
    exit 1
}
echo ""
echo "Essayez : aorus rgb config"
echo "═══════════════════════════════════════════════════════"
