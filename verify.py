#!/usr/bin/env python3
"""
Самопроверка решения (для команды и жюри):

    python verify.py

Что делает:
  1. дважды прогоняет пайплайн и сверяет хэши -> ДЕТЕРМИНИЗМ;
  2. проверяет все выгрузки на соответствие требованиям ТЗ;
  3. печатает отчёт PASS/FAIL и итоговый вердикт.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def run_pipeline():
    subprocess.run([sys.executable, str(ROOT / "backend" / "solution.py"),
                    "--data", str(ROOT / "data"), "--out", str(OUT)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    import pandas as pd

    results = []

    def chk(name, cond):
        results.append(bool(cond))
        print(("  ✅ " if cond else "  ❌ ") + name)

    print("=" * 60)
    print("1. ДЕТЕРМИНИЗМ (два независимых прогона)")
    print("=" * 60)
    run_pipeline(); h1 = {f: md5(OUT / f) for f in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")}
    run_pipeline(); h2 = {f: md5(OUT / f) for f in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")}
    for f in h1:
        chk(f"{f}: два прогона идентичны", h1[f] == h2[f])

    print("=" * 60)
    print("2. СХЕМА И ТРЕБОВАНИЯ ТЗ")
    print("=" * 60)
    nr = pd.read_csv(OUT / "nodes_roles.csv")
    cl = pd.read_csv(OUT / "clusters.csv")
    tp = pd.read_csv(OUT / "top_nodes.csv")

    need_nodes = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    chk("nodes_roles: ровно 2248 строк", len(nr) == 2248)
    chk("nodes_roles: gid уникальны", nr.gid.nunique() == 2248)
    chk("nodes_roles: обязательные колонки на месте", all(c in nr.columns for c in need_nodes))
    chk("role только из словаря", set(nr.role) <= ROLES)
    chk("role_score в [0,1]", nr.role_score.between(0, 1).all())
    chk("priority_score в [0,1]", nr.priority_score.between(0, 1).all())
    chk("cluster_id проставлен всем (>=0)", (nr.cluster_id >= 0).all())
    chk("evidence непустой у всех", nr.evidence.astype(str).str.len().gt(0).all())
    chk("evidence содержит числа", nr.evidence.astype(str).str.contains(r"\d").all())
    chk("evidence <= 200 символов", nr.evidence.astype(str).str.len().le(200).all())
    chk("нет артефакта '-0.0000'", (~nr.evidence.astype(str).str.contains(r"-0\.0000")).all())

    chk("clusters: обязательные колонки", all(c in cl.columns for c in
        ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]))
    chk("clusters: гипотеза у каждого", cl.hypothesis.astype(str).str.len().gt(0).all())
    chk("clusters: сумма n_nodes == 2248", int(cl.n_nodes.sum()) == 2248)

    chk("top_nodes: >= 20 строк", len(tp) >= 20)
    chk("top_nodes: отсортирован по приоритету",
        list(tp.priority_score) == sorted(tp.priority_score, reverse=True))
    chk("top_nodes: обоснование у каждого", tp.why.astype(str).str.len().gt(0).all())

    print("=" * 60)
    print("3. ОБРАБОТКА ЛОВУШЕК КЕЙСА")
    print("=" * 60)
    trunc = nr[nr.truncated_by_depth]
    chk("truncated_by_depth = (depth==4 & out_deg==0)",
        int(((nr.depth == 4) & (nr.out_deg == 0)).sum()) == int(trunc.shape[0]))
    chk("ВСЕ обрезанные 4-м коленом помечены (любая роль)",
        trunc.evidence.str.contains("ОБРЕЗАН").all() if len(trunc) else True)
    chk("обрезанные имеют ограниченную уверенность (<=0.5)",
        trunc.role_score.le(0.5).all() if len(trunc) else True)
    seed = nr[nr.is_seed]
    chk("НИ ОДИН seed не классифицирован транзитом (вход занижен)",
        int((seed.role == "transit").sum()) == 0)

    print("=" * 60)
    print("4. ВИЗУАЛИЗАЦИЯ (graph.json)")
    print("=" * 60)
    g = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    ids = {n["id"] for n in g["nodes"]}
    chk("graph.json: 2248 узлов", len(g["nodes"]) == 2248)
    chk("graph.json: id — строки (точность gid)", isinstance(g["nodes"][0]["id"], str))
    chk("graph.json: все связи ссылаются на узлы",
        all(l["source"] in ids and l["target"] in ids for l in g["links"]))

    print("=" * 60)
    print("5. КЕЙСЫ (панель аналитика)")
    print("=" * 60)
    cs = json.loads((OUT / "cases.json").read_text(encoding="utf-8"))
    need_case = ["id", "title", "severity", "priority", "key_nodes", "logs", "recommended_action"]
    chk("cases.json: есть кейсы (>=1)", len(cs) >= 1)
    chk("cases: обязательные поля у каждого", all(all(k in c for k in need_case) for c in cs))
    chk("cases: id уникальны", len({c["id"] for c in cs}) == len(cs))
    chk("cases: severity из {high,medium,low}", all(c["severity"] in {"high", "medium", "low"} for c in cs))
    chk("cases: есть ключевые узлы у каждого", all(len(c["key_nodes"]) >= 1 for c in cs))

    print("=" * 60)
    passed, total = sum(results), len(results)
    print(f"ИТОГ: {passed}/{total} проверок пройдено")
    print("ВЕРДИКТ:", "✅ ВСЁ ОК" if passed == total else "❌ ЕСТЬ ПРОБЛЕМЫ")
    print("=" * 60)
    print("Роли:", nr.role.value_counts().to_dict())
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
