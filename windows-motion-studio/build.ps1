$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Root "src"
$Entry = Join-Path $Src "windows_motion_studio\__main__.py"
$IconScript = Join-Path $Root "scripts\generate_icon.py"
$Icon = Join-Path $Root "assets\windows_motion_studio_icon.ico"
$Name = "WindowsMotionStudio"

if (-not (Test-Path $Entry)) {
    throw "Entry file not found: $Entry"
}

Write-Host "Installing build dependency..."
python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "Generating app icon..."
python $IconScript

Write-Host "Building standalone executable..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name $Name `
    --icon $Icon `
    --add-data "$Icon;assets" `
    --paths $Src `
    --distpath (Join-Path $Root "dist") `
    --workpath (Join-Path $Root "build") `
    --specpath (Join-Path $Root "build") `
    $Entry

Write-Host "Done: $(Join-Path $Root "dist\$Name.exe")"
