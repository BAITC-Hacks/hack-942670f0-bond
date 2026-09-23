#!/usr/bin/env python3
"""
Кроссплатформенный запуск (Windows / macOS / Linux):

    pip install -r requirements.txt
    python run.py

Считает роли/кластеры/приоритеты и собирает офлайн-дашборд.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], check=True)


def main():
    run(ROOT / "backend" / "solution.py", "--data", ROOT / "data", "--out", ROOT / "out")
    run(ROOT / "backend" / "build_viz.py", "--out", ROOT / "out", "--vendor", ROOT / "viz" / "vendor")
    print("\nГотово.")
    print("Выгрузки: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv")
    print("Дашборд:  out/vertex.html (открыть в браузере)")


if __name__ == "__main__":
    main()
