<#
.SYNOPSIS
    Deploy QHub plugin to the QGIS plugins directory.
.DESCRIPTION
    Auto-detects QGIS4 or QGIS3 plugins directory and copies the qhub package.
#>

$qgis4Dir = Join-Path $env:APPDATA "QGIS\QGIS4\profiles\default\python\plugins\qhub"

$qgis3Dir = Join-Path $env:APPDATA "QGIS\QGIS3\profiles\default\python\plugins\qhub"

# Prefer QGIS4, fall back to QGIS3
$qgis4Parent = Split-Path $qgis4Dir -Parent
$qgis3Parent = Split-Path $qgis3Dir -Parent

if (Test-Path (Split-Path $qgis4Parent -Parent)) {
    $targetDir = $qgis4Dir
    Write-Host "Deploying to QGIS 4: $targetDir"
}
elseif (Test-Path (Split-Path $qgis3Parent -Parent)) {
    $targetDir = $qgis3Dir
    Write-Host "Deploying to QGIS 3: $targetDir"
}
else {
    Write-Error "No QGIS plugins directory found. Is QGIS installed?"
    exit 1
}

# Remove old deployment
if (Test-Path $targetDir) {
    Remove-Item $targetDir -Recurse -Force
    Write-Host "Removed old deployment"
}

# Copy plugin package
$sourceDir = Join-Path $PSScriptRoot "qhub"
Copy-Item $sourceDir $targetDir -Recurse -Force
Write-Host "Deployed qhub plugin to $targetDir"
Write-Host "Restart QGIS or use Plugin Reloader to activate."

#Install uv if not already installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    # Use powerShell to install uv
    Invoke-Expression (New-Object System.Net.WebClient).DownloadString('https://uv.io/install.ps1')
    Write-Host "uv installed successfully."
}