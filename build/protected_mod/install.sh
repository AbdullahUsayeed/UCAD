#!/bin/bash
# install.sh — one-click installer for UCAD Assistant on Linux/macOS

# Determine FreeCAD user Mod directory
if [[ "$OSTYPE" == "darwin"* ]]; then
    MOD_PARENT="$HOME/Library/Application Support/FreeCAD/Mod"
else
    MOD_PARENT="$HOME/.local/share/FreeCAD/Mod"
fi

MOD_DIR="$MOD_PARENT/AICompanion"

if [ ! -d "$MOD_PARENT" ]; then
    echo "FreeCAD not found. Install FreeCAD first."
    read -rp "Press Enter to exit..."
    exit 1
fi

if [ -d "$MOD_DIR" ]; then
    echo "Updating existing installation..."
    rm -rf "$MOD_DIR"
fi

cp -r "$(dirname "$0")/AICompanion" "$MOD_DIR"
echo "UCAD installed! Restart FreeCAD and activate UCAD Assistant workbench."
read -rp "Press Enter to exit..."
