#!/usr/bin/env bash
# Retire tout ce qu'install.sh a posé. Les réglages sont conservés.
set -euo pipefail

UDEV_RULE="/etc/udev/rules.d/60-gigabyte-keyboard.rules"
LEGACY_RULE="/etc/udev/rules.d/99-gigabyte-keyboard.rules"

echo "═══════════════════════════════════════════════════════"
echo "      Désinstallation de Aorus RGB Keyboard Daemon      "
echo "═══════════════════════════════════════════════════════"

echo "Arrêt du service systemd..."
systemctl --user disable --now aorus-rgb.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/aorus-rgb.service"
systemctl --user daemon-reload

echo "Suppression des commandes et du démon..."
rm -f "$HOME/.local/bin/aorus-rgb" "$HOME/.local/bin/aorus"
rm -rf "$HOME/.local/share/aorus-rgb"

# La règle udev est le seul fichier hors du répertoire utilisateur : la laisser
# derrière soi accorderait encore un accès au périphérique sans rien pour s'en
# servir.
if [ -f "$UDEV_RULE" ] || [ -f "$LEGACY_RULE" ]; then
    echo "Suppression de la règle udev (demande sudo)..."
    if sudo rm -f "$UDEV_RULE" "$LEGACY_RULE"; then
        sudo udevadm control --reload-rules && sudo udevadm trigger
        echo "✓ Règle retirée."
    else
        echo "⚠ À retirer à la main : sudo rm -f $UDEV_RULE $LEGACY_RULE"
    fi
fi

echo ""
echo "✓ Désinstallation terminée."
echo "Vos réglages et presets sont conservés dans ~/.config/aorus-rgb."
echo "Pour les supprimer aussi : rm -rf ~/.config/aorus-rgb"
