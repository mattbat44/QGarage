# Install uv (Python package manager)
# For Windows (PowerShell)

Write-Host "Installing uv..." -ForegroundColor Green

# Check if Windows
if ($PSVersionTable.OS -notlike "*Windows*") {
    Write-Host "This script is for Windows. Use install_uv.sh on Linux/macOS." -ForegroundColor Red
    exit 1
}

try {
    # Try to install via PowerShell
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Write-Host "uv installed successfully!" -ForegroundColor Green

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

    # Verify installation
    uv --version
}
catch {
    Write-Host "Failed to install uv automatically." -ForegroundColor Red
    Write-Host "Please visit https://github.com/astral-sh/uv for manual installation instructions." -ForegroundColor Yellow
    exit 1
}
