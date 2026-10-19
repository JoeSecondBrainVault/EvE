# E.V.E. Setup Script (Windows PowerShell 5.1 / 7+ compatible, 7-bit ASCII)
param(
    [switch]$SkipGpu
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Output "[E.V.E.] Starting local environment setup..."

# 1. Verify Python 3.13 / 3.12 availability
$pyCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyCmd = "py -3.13"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} else {
    Write-Error "Python 3.13 or 3.12 is required but not found on PATH or py launcher."
    exit 1
}

# 2. Virtual environment setup
$venvPath = Join-Path $ProjectRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Output "[E.V.E.] Creating Python virtual environment at .venv..."
    Invoke-Expression "$pyCmd -m venv `"$venvPath`""
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

# 3. Pip upgrade and dependencies
Write-Output "[E.V.E.] Upgrading pip..."
& $venvPython -m pip install --upgrade pip -q

Write-Output "[E.V.E.] Installing core backend dependencies..."
& $venvPython -m pip install -e "$ProjectRoot\backend"

if (-not $SkipGpu) {
    Write-Output "[E.V.E.] Installing CUDA 12 runtime wheels for RTX 4060 GPU acceleration..."
    try {
        & $venvPython -m pip install "nvidia-cublas-cu12>=12.4,<13" "nvidia-cudnn-cu12>=9.1,<10" --timeout 45
    } catch {
        Write-Warning "[E.V.E.] GPU wheel installation failed or was skipped. Will run in CPU mode."
    }
}

# 4. Copy .env template if missing
$envFile = Join-Path $ProjectRoot ".env"
$envExample = Join-Path $ProjectRoot ".env.example"
if ((-not (Test-Path $envFile)) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Output "[E.V.E.] Created .env from template."
}

# 5. Dashboard dependencies
$dashboardDir = Join-Path $ProjectRoot "dashboard"
if ((Test-Path $dashboardDir) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Output "[E.V.E.] Installing dashboard dependencies..."
    Push-Location $dashboardDir
    try {
        & npm install --no-fund
    } finally {
        Pop-Location
    }
}

Write-Output "[E.V.E.] Setup completed successfully!"

