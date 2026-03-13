#!/bin/bash
# setup_sports_deps.sh - Install dependencies for Sports Analysis Module

echo "🚀 Installing system dependencies..."
# Update and install ffmpeg (required for audio processing)
sudo apt update && sudo apt install -y ffmpeg

echo "🐍 Installing Python dependencies..."
# Use the virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

pip install python-telegram-bot pydub
pip install playwright
playwright install chromium

echo "✅ Dependencies installation complete!"
