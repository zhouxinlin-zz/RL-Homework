$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv venv .venv --python 3.12
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        & python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required. Install Python 3.12 or uv, then run setup again.' }
        & python.exe -m venv .venv
    } else {
        throw 'Install uv or Python 3.12, then run Setup-Game.cmd again. See README.md.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $taskPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv requires Python 3.12 or newer. Rename it and run setup again.' }
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install --python $taskPython -r requirements.txt
} else {
    & $taskPython -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'web\dist\index.html'))) {
    $taskNpm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $taskNpm) { throw 'Node.js 24 is required to build the game. Install it and run setup again.' }
    Push-Location (Join-Path $taskRoot 'web')
    try {
        & $taskNpm.Source ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
        & $taskNpm.Source run build
        if ($LASTEXITCODE -ne 0) { throw 'Could not build the game.' }
    } finally { Pop-Location }
}
& $taskPython -m server.doctor
if ($LASTEXITCODE -ne 0) { throw 'Installation check failed.' }
