# E.V.E. Runtime Launcher (Windows PowerShell 5.1 / 7+ compatible, 7-bit ASCII)
param(
    [ValidateSet("app", "serve", "devices", "live", "dashboard", "tray")]
    [string]$Mode = "app",
    [string]$Title = "Lecture Session",
    [string]$Course = "",
    [switch]$StartOllama,
    [switch]$CreateShortcut
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# If requested, create Windows Desktop and Start Menu shortcuts
if ($CreateShortcut) {
    & (Join-Path $PSScriptRoot "create_desktop_shortcut.ps1") -AddToStartMenu
    exit 0
}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment not found. Please run scripts\setup.ps1 first."
    exit 1
}

# Optional: Ensure headless Ollama daemon is running with RTX 4060 VRAM optimizations
if ($StartOllama) {
    $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaExe) {
        $existingOllama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Where-Object { $_.ProcessId -ne $PID }
        if (-not $existingOllama) {
            Write-Output "[E.V.E.] Starting headless Ollama daemon (Flash Attention + Q8 KV Cache for 8GB RTX VRAM)..."
            $env:OLLAMA_FLASH_ATTENTION = "1"
            $env:OLLAMA_KV_CACHE_TYPE = "q8_0"
            Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
            Start-Sleep -Seconds 2
        }
    }
}

# Run selected E.V.E. mode
switch ($Mode) {
    "app" {
        Write-Output "[E.V.E.] Launching Native Windows Desktop App..."
        & $venvPython -m eve app
    }
    "devices" {
        Write-Output "[E.V.E.] Audio Devices:"
        & $venvPython -m eve devices
    }
    "live" {
        $argsList = @("-m", "eve", "live", "--title", $Title)
        if ($Course -ne "") {
            $argsList += @("--course", $Course)
        }
        & $venvPython @argsList
    }
    "dashboard" {
        $dashDir = Join-Path $ProjectRoot "dashboard"
        $tokenFile = Join-Path $ProjectRoot "data\api_token"
        $tokenVal = if (Test-Path $tokenFile) { (Get-Content $tokenFile -Raw).Trim() } else { "" }
        Write-Output "[E.V.E.] Dashboard URL: http://localhost:3000"
        if ($tokenVal -ne "") {
            Write-Output "[E.V.E.] Local API Token: $tokenVal"
        }
        Push-Location $dashDir
        try {
            & npm run dev
        } finally {
            Pop-Location
        }
    }
    "tray" {
        Write-Output "[E.V.E.] Launching Windows System Tray Icon..."
        & $venvPython -m eve tray
    }
    default {
        Write-Output "[E.V.E.] Launching FastAPI Server on 127.0.0.1:8765..."
        & $venvPython -m eve serve
    }
}

