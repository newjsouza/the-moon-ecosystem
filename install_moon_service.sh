#!/bin/bash
# install_moon_service.sh
# Installs The Moon as a systemd service (starts automatically on boot).
#
# USAGE: bash install_moon_service.sh
# Requires: sudo
#
# What this does:
#   1. Copies the-moon.service to /etc/systemd/system/
#   2. Reloads systemd
#   3. Enables the service (starts on boot)
#   4. Starts the service immediately
#   5. Shows status

set -euo pipefail

SERVICE_FILE="$(dirname "$(realpath "$0")")/the-moon.service"
SERVICE_NAME="the-moon.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}"

echo "🌕 The Moon — Service Installer"
echo "================================"

# Check service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Service file not found: $SERVICE_FILE"
    exit 1
fi

echo "📋 Service file: $SERVICE_FILE"
echo "📁 Installing to: $SERVICE_DEST"
echo ""

# Copy service file
sudo cp "$SERVICE_FILE" "$SERVICE_DEST"
echo "✅ Service file copied"

# Reload systemd
sudo systemctl daemon-reload
echo "✅ systemd reloaded"

# Enable service (start on boot)
sudo systemctl enable "$SERVICE_NAME"
echo "✅ Service enabled (starts on boot)"

# Start service now
sudo systemctl start "$SERVICE_NAME"
echo "✅ Service started"

echo ""
echo "📊 Status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true

echo ""
echo "📝 To follow logs in real time:"
echo "   journalctl -u the-moon -f"
echo ""
echo "🛑 To stop:   sudo systemctl stop the-moon"
echo "🔄 To restart: sudo systemctl restart the-moon"
echo "🗑️  To remove:  sudo systemctl disable the-moon && sudo rm $SERVICE_DEST"
