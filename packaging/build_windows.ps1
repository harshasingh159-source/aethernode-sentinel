# Build dist\AetherNode.exe (single file, system-tray app). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Also writes dist\THIRD_PARTY_NOTICES.txt (bundled into the .exe and attached to releases).
# -OutDir <folder> builds somewhere else (e.g. while dist\AetherNode.exe is running).
param([string]$OutDir = "dist")
$ErrorActionPreference = "Stop"
python -m pip install --quiet pyinstaller pillow pystray packaging -r requirements.txt
if ($LASTEXITCODE) { throw "pip install failed" }

python packaging\make_icon.py
python packaging\make_version_info.py
python packaging\third_party_notices.py "$OutDir\THIRD_PARTY_NOTICES.txt"
if ($LASTEXITCODE) { throw "preparing build files failed" }

python -m PyInstaller --noconfirm --clean --onefile --windowed --distpath $OutDir `
    --name AetherNode `
    --icon packaging\aethernode.ico `
    --version-file packaging\version_info.txt `
    --add-data "aethernode\static;aethernode\static" `
    --add-data "$OutDir\THIRD_PARTY_NOTICES.txt;aethernode\static" `
    --add-data "LICENSE;aethernode\static" `
    --collect-submodules uvicorn `
    --collect-submodules pystray `
    --collect-submodules scapy.layers `
    --hidden-import scapy.libs.manuf `
    --exclude-module tkinter --exclude-module matplotlib --exclude-module IPython `
    packaging\aethernode_app.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }
Write-Host "Built: $OutDir\AetherNode.exe (+ $OutDir\THIRD_PARTY_NOTICES.txt)"
