# Create Desktop Shortcut for E.V.E. (Windows PowerShell 5.1 / 7+ compatible, 7-bit ASCII)
param(
    [switch]$AddToStartMenu
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$pythonwExe = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    Write-Error "pythonw.exe not found at $pythonwExe. Please run scripts\setup.ps1 first."
    exit 1
}

$iconPath = Join-Path $ProjectRoot "assets\eve.ico"
if (-not (Test-Path $iconPath)) {
    Write-Output "assets\eve.ico not found. Generating icons..."
    $pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    & $pythonExe (Join-Path $PSScriptRoot "generate_icon.py")
}

$wshShell = New-Object -ComObject WScript.Shell

# 1. Desktop Shortcut
$desktopPath = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktopPath "E.V.E.lnk"

Write-Output "Creating Desktop shortcut at: $desktopShortcutPath"
$shortcut = $wshShell.CreateShortcut($desktopShortcutPath)
$shortcut.TargetPath = $pythonwExe
$shortcut.Arguments = "-m eve app"
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "E.V.E. - Extensible Virtual Entity (Personal AI Assistant)"
$shortcut.WindowStyle = 1 # Normal window
$shortcut.Save()

Write-Output "Successfully created desktop shortcut: $desktopShortcutPath"

# 2. Optional: Start Menu Shortcut
if ($AddToStartMenu) {
    $startMenuPrograms = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
    $startMenuShortcutPath = Join-Path $startMenuPrograms "E.V.E.lnk"
    Write-Output "Creating Start Menu shortcut at: $startMenuShortcutPath"
    $smShortcut = $wshShell.CreateShortcut($startMenuShortcutPath)
    $smShortcut.TargetPath = $pythonwExe
    $smShortcut.Arguments = "-m eve app"
    $smShortcut.WorkingDirectory = $ProjectRoot
    $smShortcut.IconLocation = "$iconPath,0"
    $smShortcut.Description = "E.V.E. - Extensible Virtual Entity (Personal AI Assistant)"
    $smShortcut.WindowStyle = 1
    $smShortcut.Save()
    Write-Output "Successfully created Start Menu shortcut: $startMenuShortcutPath"
}
