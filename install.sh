#!/bin/bash

# xzSSH Installation Script
# This script sets up a virtual environment, installs dependencies,
# and makes the 'xzssh' command available.

set -e

echo "------------------------------------------------"
echo "  Installing xzSSH..."
echo "------------------------------------------------"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Create a virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment and install
echo "Installing dependencies and xzssh package..."
source venv/bin/activate
pip install --upgrade pip
pip install -e .

# Offer to create symlink for global access
INSTALL_DIR="/usr/local/bin"
EXECUTABLE_PATH="$(pwd)/venv/bin/xzssh"

echo ""
echo "------------------------------------------------"
echo "  Global Access Setup"
echo "------------------------------------------------"
echo "To run 'xzssh' from anywhere without sourcing 'venv',"
echo "you can create a symlink in your PATH ($INSTALL_DIR)."
echo ""
read -p "Would you like to create a symlink to $INSTALL_DIR/xzssh? [y/N] " confirm
if [[ "$confirm" == [yY] ]]; then
    if [ -w "$INSTALL_DIR" ]; then
        ln -sf "$EXECUTABLE_PATH" "$INSTALL_DIR/xzssh"
        echo "Symlink created! You can now run 'xzssh' directly."
    else
        echo "Requires sudo permissions to write to $INSTALL_DIR."
        sudo ln -sf "$EXECUTABLE_PATH" "$INSTALL_DIR/xzssh"
        echo "Symlink created! You can now run 'xzssh' directly."
    fi
else
    echo "Skipped symlink creation."
fi

echo "------------------------------------------------"
echo "Installation Complete! ✔"
echo "------------------------------------------------"
echo ""
echo "To run 'xzssh' from anywhere, ensure the symlink was created."
echo "If you skipped it, you can manually run:"
echo "  ln -sf $(pwd)/venv/bin/xzssh /usr/local/bin/xzssh"
echo ""
echo "Or use it manually by activating the virtual environment:"
echo "  source venv/bin/activate"
echo "  xzssh list"
echo ""
echo "Alternatively, add an alias to your shell config (~/.zshrc or ~/.bashrc):"
echo "  alias xzssh='$(pwd)/venv/bin/xzssh'"
echo ""
