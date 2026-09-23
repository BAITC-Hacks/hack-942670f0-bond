$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
    if (Get-Command python -ErrorAction SilentlyContinue) { python -m venv .venv }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv }
    else { throw "Install Python 3.12+ and add it to PATH." }
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment" }
}
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies" }
& ./.venv/Scripts/python.exe -X utf8 run.py @args
if ($LASTEXITCODE -ne 0) { throw "Pipeline failed" }
