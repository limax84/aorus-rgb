#!/usr/bin/env bash
set -e

echo "═══════════════════════════════════════════════════════"
echo "      Désinstallation de Aorus RGB Keyboard Daemon      "
echo "═══════════════════════════════════════════════════════"

echo "Arrêt et désactivation du service systemd..."
systemctl --user stop aorus-rgb.service 2>/dev/null || true
systemctl --user disable aorus-rgb.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/aorus-rgb.service"
systemctl --user daemon-reload

echo "Suppression des fichiers binaires..."
rm -f "$HOME/.local/bin/aorus-rgb"
rm -f "$HOME/.local/bin/aorus"

echo "Suppression des fichiers du démon..."
rm -rf "$HOME/.local/share/aorus-rgb"

echo "✓ Désinstallation terminée."
echo ""
echo "Vos réglages et presets sont conservés dans ~/.config/aorus-rgb."
echo "Pour les supprimer aussi : rm -rf ~/.config/aorus-rgb"
