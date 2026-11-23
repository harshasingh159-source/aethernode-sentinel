# Build dist\AetherNode.exe (single file). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
python -m pip install --quiet pyinstaller pillow pystray -r requirements.txt
python packaging\make_icon.py
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name AetherNode `
    --icon packaging\aethernode.ico `
    --add-data "aethernode\static;aethernode\static" `
    --collect-submodules uvicorn `
    --collect-submodules pystray `
    --collect-submodules scapy.layers `
    --hidden-import scapy.libs.manuf `
    --exclude-module tkinter --exclude-module matplotlib --exclude-module IPython `
    packaging\aethernode_app.py
Write-Host "Built: dist\AetherNode.exe"
