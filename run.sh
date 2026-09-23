#!/usr/bin/env bash
# Вершина (Vertex) — единый запуск: сырые parquet -> 3 CSV + интерактивный дашборд.
# Использование:  ./run.sh
set -e
cd "$(dirname "$0")"

PY=python3
if [ ! -d venv ]; then
  echo "[1/4] создаю venv…"
  $PY -m venv venv
fi
echo "[2/4] ставлю зависимости…"
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

echo "[3/4] считаю роли, кластеры, приоритеты -> out/*.csv…"
./venv/bin/python backend/solution.py --data data --out out

echo "[4/4] собираю дашборд out/vertex.html…"
./venv/bin/python backend/build_viz.py --out out --vendor viz/vendor

echo
echo "Готово. Выгрузки: out/nodes_roles.csv, out/clusters.csv, out/top_nodes.csv"
echo "Дашборд:  открой out/vertex.html в браузере (двойной клик, работает офлайн)"
echo "  или:    cd out && $PY -m http.server 8777  ->  http://localhost:8777/vertex.html"
