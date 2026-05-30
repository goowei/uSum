<#
.SYNOPSIS
  Convenience launcher for Windows (PowerShell).
.EXAMPLE
  .\run.ps1 -Setup
  .\run.ps1 https://youtu.be/xxxx -f md,docx,pdf
#>
param(
    [switch]$Setup,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$venv = ".venv"

# Resolve a Python launcher.
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { $python = "py" } else { $python = "python" }

if ($Setup) {
    & $python -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install --upgrade pip
    & "$venv\Scripts\python.exe" -m pip install -r requirements.txt
    Write-Host "Setup complete. Copy .env.example to .env and add your ANTHROPIC_API_KEY."
    exit 0
}

if (-not (Test-Path $venv)) {
    Write-Error "No virtualenv found. Run: .\run.ps1 -Setup"
    exit 1
}

& "$venv\Scripts\python.exe" -m usum @Rest
