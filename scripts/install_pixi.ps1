# Install pixi (conda package manager)
# For Windows (PowerShell)

Write-Host "Installing pixi..." -ForegroundColor Green

# Check if Windows
if ($PSVersionTable.OS -notlike "*Windows*") {
    Write-Host "This script is for Windows. Use install_pixi.sh on Linux/macOS." -ForegroundColor Red
    exit 1
}

try {
    # Install via PowerShell
    powershell -Command "irm https://pixi.sh/install.ps1 | iex"
    Write-Host "pixi installed successfully!" -ForegroundColor Green

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

    # Verify installation
    pixi --version
}
catch {
    Write-Host "Failed to install pixi automatically." -ForegroundColor Red
    Write-Host "Please visit https://pixi.sh for manual installation instructions." -ForegroundColor Yellow
    exit 1
}
