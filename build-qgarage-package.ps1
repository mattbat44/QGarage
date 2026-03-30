<#
.SYNOPSIS
    Run QA/security checks and package the QGarage plugin.

.DESCRIPTION
    Executes the targeted flake8 rule set used for recent cleanup, runs Bandit
    against the plugin source, scans the repository with detect-secrets, and
    then creates a versioned ZIP containing only the qgarage plugin folder.
    Python cache folders and bytecode files are excluded from the archive.
#>

[CmdletBinding()]
param(
    [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
}

function Assert-Success {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ToolName
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$ToolName failed with exit code $LASTEXITCODE."
    }
}

function Get-MetadataVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MetadataPath
    )

    $versionLine = Get-Content -Path $MetadataPath |
    Where-Object { $_ -match '^version=' } |
    Select-Object -First 1

    if (-not $versionLine) {
        throw "Could not find a version entry in $MetadataPath."
    }

    $version = ($versionLine -replace '^version=', '').Trim()
    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "The version entry in $MetadataPath is empty."
    }

    return $version
}

function Test-ArchiveEligible {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $normalized = $RelativePath.Replace('\', '/')
    if ($normalized -match '(^|/)__pycache__(/|$)') {
        return $false
    }
    if ($normalized -match '\.(pyc|pyo)$') {
        return $false
    }

    return $true
}

$repoRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
else {
    $PSScriptRoot
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repoRoot "dist"
}

$metadataPath = Join-Path $repoRoot "qgarage\metadata.txt"
$pluginDir = Join-Path $repoRoot "qgarage"
$scriptsDir = Join-Path $repoRoot ".venv\Scripts"
$tempDir = if ([string]::IsNullOrWhiteSpace($env:TEMP)) {
    [System.IO.Path]::GetTempPath()
}
else {
    $env:TEMP
}
$detectSecretsBaseline = Join-Path $tempDir (
    "qgarage-detect-secrets-" + [guid]::NewGuid().ToString() + ".json"
)

if (-not (Test-Path $metadataPath)) {
    throw "Metadata file not found: $metadataPath"
}

if (-not (Test-Path $pluginDir)) {
    throw "Plugin folder not found: $pluginDir"
}

$tools = @{
    Flake8        = Join-Path $scriptsDir "flake8.exe"
    Pytest        = Join-Path $scriptsDir "pytest.exe"
    Bandit        = Join-Path $scriptsDir "bandit.exe"
    DetectSecrets = Join-Path $scriptsDir "detect-secrets.exe"
}

foreach ($tool in $tools.GetEnumerator()) {
    if (-not (Test-Path $tool.Value)) {
        throw "Required tool not found: $($tool.Value)"
    }
}

$version = Get-MetadataVersion -MetadataPath $metadataPath
$packagePath = Join-Path $OutputDir ("qgarage_v$version.zip")
$detectSecretsExclude = '(^|[\\/])(\.git|\.venv|dist|build|__pycache__|\.pytest_cache)([\\/]|$)|\.(pyc|pyo|zip)$'

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if (Test-Path $packagePath) {
    Remove-Item -Path $packagePath -Force
}

try {
    Invoke-Step -Name "Flake8 targeted lint" -Action {
        & $tools.Flake8 "qgarage" "qhub" "tests" "--select=W292,F821,F401,F811,W503"
        Assert-Success -ToolName "flake8"
    }

    Invoke-Step -Name "Run full test suite" -Action {
        & $tools.Pytest
        Assert-Success -ToolName "pytest"
    }

    Invoke-Step -Name "Bandit security scan" -Action {
        & $tools.Bandit "-r" "qgarage" "--severity-level" "medium" "--confidence-level" "medium"
        Assert-Success -ToolName "bandit"
    }

    Invoke-Step -Name "detect-secrets scan" -Action {
        & $tools.DetectSecrets "scan" "--all-files" "--exclude-files" $detectSecretsExclude |
        Out-File -FilePath $detectSecretsBaseline -Encoding utf8
        Assert-Success -ToolName "detect-secrets"

        $baseline = Get-Content -Path $detectSecretsBaseline -Raw | ConvertFrom-Json
        $findings = @()

        if ($null -ne $baseline.results) {
            foreach ($property in $baseline.results.PSObject.Properties) {
                $entries = @($property.Value)
                if ($entries.Count -gt 0) {
                    $findings += [pscustomobject]@{
                        Path  = $property.Name
                        Count = $entries.Count
                    }
                }
            }
        }

        if ($findings.Count -gt 0) {
            $summary = ($findings | ForEach-Object { "$($_.Path) [$($_.Count)]" }) -join ", "
            throw "detect-secrets found potential secrets: $summary"
        }
    }

    Invoke-Step -Name "Create plugin archive" -Action {
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::Open(
            $packagePath,
            [System.IO.Compression.ZipArchiveMode]::Create
        )

        try {
            Get-ChildItem -Path $pluginDir -Recurse -File |
            ForEach-Object {
                $relativePath = $_.FullName.Substring($repoRoot.Length).TrimStart('\')
                if (Test-ArchiveEligible -RelativePath $relativePath) {
                    $entryName = $relativePath.Replace('\', '/')
                    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                        $archive,
                        $_.FullName,
                        $entryName,
                        [System.IO.Compression.CompressionLevel]::Optimal
                    ) | Out-Null
                }
            }
        }
        finally {
            $archive.Dispose()
        }
    }
}
finally {
    if ((-not [string]::IsNullOrWhiteSpace($detectSecretsBaseline)) -and (Test-Path $detectSecretsBaseline)) {
        Remove-Item -Path $detectSecretsBaseline -Force
    }
}

Write-Host "Build succeeded: $packagePath" -ForegroundColor Green
