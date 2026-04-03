#!/bin/bash
# timelapsrr Launcher for macOS/Linux

set -e

# Change to the script's directory
cd "$(dirname "$0")"

echo "==================================="
echo "timelapsrr Launcher"
echo "==================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed!"
    echo "Please install Python 3.8 or higher from python.org"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION found"

# Check if FFmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "❌ Error: FFmpeg is not installed!"
    echo ""
    echo "To install FFmpeg:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  macOS: brew install ffmpeg"
    else
        echo "  Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg"
        echo "  Fedora: sudo dnf install ffmpeg"
        echo "  Arch: sudo pacman -S ffmpeg"
    fi
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "✓ FFmpeg found"

# Check if pip is installed
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "❌ Error: pip is not installed!"
    read -p "Press Enter to exit..."
    exit 1
fi

# Try pip3 first, fall back to pip
PIP_CMD=pip3
if ! command -v pip3 &> /dev/null; then
    PIP_CMD=pip
fi
echo "✓ pip found"

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found!"
    read -p "Press Enter to exit..."
    exit 1
fi

# Install dependencies if needed
echo ""
echo "Checking dependencies..."
if $PIP_CMD install -q -r requirements.txt; then
    echo "✓ Dependencies installed"
else
    echo "❌ Error: Failed to install dependencies!"
    read -p "Press Enter to exit..."
    exit 1
fi

# Launch the application
echo ""
echo "==================================="
echo "Launching timelapsrr..."
echo "==================================="
echo ""

python3 main.py
