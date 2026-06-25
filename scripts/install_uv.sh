#!/bin/bash
# Install uv (Python package manager)
# For Linux and macOS

set -e

echo -e "\033[32mInstalling uv...\033[0m"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    curl -LsSf https://astral.sh/uv/install.sh | sh
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo -e "\033[31mUnsupported OS. Please install uv manually from https://github.com/astral-sh/uv\033[0m"
    exit 1
fi

# Add to PATH for current session
source "$HOME/.cargo/env" 2>/dev/null || true
export PATH="$HOME/.local/bin:$PATH"

echo -e "\033[32muv installed successfully!\033[0m"

# Verify installation
if command -v uv &> /dev/null; then
    uv --version
else
    echo -e "\033[33mWarning: uv not found in PATH. You may need to restart your shell.\033[0m"
fi
