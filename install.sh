#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════"
echo "        Installation de Aorus RGB Keyboard Daemon       "
echo "═══════════════════════════════════════════════════════"

# 1. Dépendances Python
echo "[1/5] Vérification des modules Python (hidapi, evdev)..."
if ! python3 -c "import hid, evdev" 2>/dev/null; then
    echo "Installation des dépendances..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm python-hidapi python-evdev 2>/dev/null || pip install --user hidapi evdev
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y python3-hid python3-evdev 2>/dev/null || pip install --user hidapi evdev
    else
        pip install --user hidapi evdev
    fi
else
    echo "✓ Modules Python déjà installés."
fi

# 2. Règles udev
echo "[2/5] Configuration des permissions USB (udev)..."
if [ -d /etc/udev/rules.d ]; then
    if [ ! -f /etc/udev/rules.d/99-gigabyte-keyboard.rules ]; then
        if [ "$EUID" -eq 0 ]; then
            cp "$REPO_DIR/udev/99-gigabyte-keyboard.rules" /etc/udev/rules.d/
            udevadm control --reload-rules && udevadm trigger
            echo "✓ Règle udev installée."
        elif sudo -n true 2>/dev/null; then
            sudo cp "$REPO_DIR/udev/99-gigabyte-keyboard.rules" /etc/udev/rules.d/
            sudo udevadm control --reload-rules && sudo udevadm trigger
            echo "✓ Règle udev installée via sudo."
        else
            echo "⚠ Pour utiliser le clavier sans être root, exécutez :"
            echo "   sudo cp $REPO_DIR/udev/99-gigabyte-keyboard.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger"
        fi
    else
        echo "✓ Règle udev déjà présente."
    fi
fi

# 3. Copie du démon dans ~/.local/share/aorus-rgb
echo "[3/5] Installation du démon dans ~/.local/share/aorus-rgb..."
mkdir -p "$HOME/.local/share/aorus-rgb"
cp "$REPO_DIR/src/aorus_rgb.py" "$HOME/.local/share/aorus-rgb/aorus_rgb.py"
chmod +x "$HOME/.local/share/aorus-rgb/aorus_rgb.py"
echo "✓ Démon installé."

# 4. Installation des binaires CLI dans ~/.local/bin
echo "[4/5] Installation des commandes CLI dans ~/.local/bin..."
mkdir -p "$HOME/.local/bin"
cp "$REPO_DIR/bin/aorus-rgb" "$HOME/.local/bin/aorus-rgb"
cp "$REPO_DIR/bin/aorus" "$HOME/.local/bin/aorus"
chmod +x "$HOME/.local/bin/aorus-rgb" "$HOME/.local/bin/aorus"
echo "✓ Commandes 'aorus' et 'aorus-rgb' installées."

# 5. Service systemd utilisateur
echo "[5/5] Configuration et démarrage du service systemd..."
mkdir -p "$HOME/.config/systemd/user"
cp "$REPO_DIR/systemd/aorus-rgb.service" "$HOME/.config/systemd/user/aorus-rgb.service"
systemctl --user daemon-reload
systemctl --user enable aorus-rgb.service
systemctl --user restart aorus-rgb.service
echo "✓ Service aorus-rgb.service activé et démarré."

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✓ Installation terminée avec succès !"
echo "Essayez : aorus rgb status"
echo "═══════════════════════════════════════════════════════"
