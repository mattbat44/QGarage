#!/bin/bash
# Install pixi (conda package manager)
# For Linux and macOS

set -e

echo -e "\033[32mInstalling pixi...\033[0m"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    curl -fsSL https://pixi.sh/install.sh | bash
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    curl -fsSL https://pixi.sh/install.sh | bash
else
    echo -e "\033[31mUnsupported OS. Please install pixi manually from https://pixi.sh\033[0m"
    exit 1
fi

# Add to PATH for current session
export PATH="$HOME/.pixi/bin:$PATH"

echo -e "\033[32mpixi installed successfully!\033[0m"

# Verify installation
if command -v pixi &> /dev/null; then
    pixi --version
else
    echo -e "\033[33mWarning: pixi not found in PATH. You may need to restart your shell.\033[0m"
fi
