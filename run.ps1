# Вершина (Vertex) — запуск под Windows (PowerShell):  ./run.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path "venv")) {
    Write-Host "[1/4] создаю venv..."
    python -m venv venv
}
Write-Host "[2/4] ставлю зависимости..."
venv\Scripts\python.exe -m pip install -q --upgrade pip
venv\Scripts\python.exe -m pip install -q -r requirements.txt

Write-Host "[3/4] считаю роли/кластеры/приоритеты -> out\*.csv ..."
venv\Scripts\python.exe backend\solution.py --data data --out out

Write-Host "[4/4] собираю дашборд out\vertex.html ..."
venv\Scripts\python.exe backend\build_viz.py --out out --vendor viz\vendor

Write-Host ""
Write-Host "Готово. Выгрузки в out\, дашборд: out\vertex.html"
