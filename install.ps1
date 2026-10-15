param([switch]$NonInteractive)
$ErrorActionPreference = "Stop"
$MmvProjectDir = $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Install Git first for Open Actor Protocol." }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
    if (-not (Test-Path "$MmvProjectDir/.venv/Scripts/python.exe")) { & py -3 -m venv "$MmvProjectDir/.venv" }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
    if (-not (Test-Path "$MmvProjectDir/.venv/Scripts/python.exe")) { & python -m venv "$MmvProjectDir/.venv" }
} else { throw "Install Python 3.11 or newer." }
if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
$MmvPython = "$MmvProjectDir/.venv/Scripts/python.exe"
& $MmvPython -m pip install $MmvProjectDir
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
if ($NonInteractive) { & $MmvPython -m mmv.setup doctor } else { & $MmvPython -m mmv.setup configure }
if ($LASTEXITCODE -ne 0) { throw "Setup did not complete." }
Write-Host "Launch: & '$MmvProjectDir/.venv/Scripts/mondo-music-video.exe' serve"
