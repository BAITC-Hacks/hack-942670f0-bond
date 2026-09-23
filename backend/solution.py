#!/usr/bin/env python3
"""
«Вершина» (Vertex) — восстановление финансовой структуры организованной группы.
Кейс «Граф денег», HackAlem AI.

Единая команда: raw parquet -> nodes_roles.csv, clusters.csv, top_nodes.csv + graph.json

    python solution.py --data ../data --out ../out

Всё детерминировано (seed=42), локально, без облака/GPU/платных сервисов.
Каждая роль — формальное правило с ПОРОГОМ (перцентиль), в evidence всегда числа.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]
SEED = 42

# ---- инвестигативная важность роли (для приоритета проверки) ----
ROLE_WEIGHT = {
    "coordinator": 1.00,   # кандидат в организаторы — проверять первым
    "consolidator": 0.85,  # собирает деньги
    "distributor": 0.75,   # распределяет деньги
    "transit": 0.55,       # мул / layering
    "terminal": 0.40,      # деньги осели (бенефициар/дроп)
    "peripheral": 0.10,    # нет признаков роли
}


# ============================================================ загрузка
def load(data_dir: Path):
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    tx["date"] = pd.to_datetime(tx["date"])
    return edges, nodes, tx


def build_graph(edges) -> nx.DiGraph:
    G = nx.DiGraph()
    for r in edges.itertuples(index=False):
        G.add_edge(int(r.src), int(r.dst),
                   sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return G


# ============================================================ признаки
def features(G: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame) -> pd.DataFrame:
    in_deg  = dict(G.in_degree());              out_deg = dict(G.out_degree())
    in_kzt  = dict(G.in_degree(weight="sum_kzt"));  out_kzt = dict(G.out_degree(weight="sum_kzt"))
    in_tx   = dict(G.in_degree(weight="n_tx"));     out_tx  = dict(G.out_degree(weight="n_tx"))
    pr      = nx.pagerank(G, weight="sum_kzt")
    hubs, auth = nx.hits(G, max_iter=1000, normalized=True)
    # betweenness: посредничество (кто «между» потоками). Без веса = структурная брокерность.
    btw = nx.betweenness_centrality(G, weight=None, normalized=True)

    df = nodes[["gid", "depth", "is_seed"]].copy()
    m = lambda d: df.gid.map(d)
    df["in_deg"]  = m(in_deg).fillna(0).astype(int)
    df["out_deg"] = m(out_deg).fillna(0).astype(int)
    df["in_kzt"]  = m(in_kzt).fillna(0.0)
    df["out_kzt"] = m(out_kzt).fillna(0.0)
    df["in_tx"]   = m(in_tx).fillna(0).astype(int)
    df["out_tx"]  = m(out_tx).fillna(0).astype(int)
    df["pagerank"]    = m(pr).fillna(0.0)
    df["hub"]         = m(hubs).fillna(0.0)
    df["authority"]   = m(auth).fillna(0.0)
    df["betweenness"] = m(btw).fillna(0.0)
    df["net_kzt"] = df.in_kzt - df.out_kzt
    df["pass_through"] = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt.replace(0, np.nan), np.nan)
    # Ловушка №1: узел на 4-м колене без исходящих — обход оборвался, а не «сток».
    df["truncated_by_depth"] = (df.depth == 4) & (df.out_deg == 0)

    # --- сколько РАЗНЫХ seed платят напрямую этому узлу (сигнал структуры) ---
    seed_set = set(df.loc[df.is_seed, "gid"])
    seed_in = {}
    for u, v in G.edges():
        if u in seed_set:
            seed_in[v] = seed_in.get(v, 0) + 1
    df["n_seed_in"] = m(seed_in).fillna(0).astype(int)

    # --- членство в возвратных циклах (layering) ---
    try:
        cyc = list(nx.simple_cycles(G, length_bound=5))
        in_cyc = set().union(*[set(c) for c in cyc]) if cyc else set()
    except Exception:
        in_cyc = set()
    df["in_cycle"] = df.gid.isin(in_cyc)

    # --- временной сигнал: медианный лаг «получил -> отправил» (быстрый оборот = транзит) ---
    df["turnover_days"] = _turnover_days(G, tx, df)
    return df


def _turnover_days(G, tx, df) -> pd.Series:
    """Для узлов с входом и выходом: медиана (дата отправки - ближайшая предыдущая дата получения)."""
    ins, outs = {}, {}
    for r in tx.itertuples(index=False):
        outs.setdefault(int(r.src), []).append(r.date)
        ins.setdefault(int(r.dst), []).append(r.date)
    res = {}
    for gid in df.gid:
        di = sorted(ins.get(int(gid), [])); do = sorted(outs.get(int(gid), []))
        if not di or not do:
            continue
        di = np.array(di); lags = []
        for t in do:
            prev = di[di <= t]
            if len(prev):
                lags.append((t - prev.max()).days)
        if lags:
            res[int(gid)] = float(np.median(lags))
    return df.gid.map(res)


# ============================================================ пороги (data-driven)
def thresholds(df: pd.DataFrame) -> dict:
    act = df[(df.in_deg > 0) | (df.out_deg > 0)]
    p = lambda col, q: float(np.nanpercentile(act[col], q))
    return {
        "IN_DEG_HI":  max(3, int(np.nanpercentile(act.in_deg[act.in_deg > 0], 95))),   # «от многих»
        "OUT_DEG_HI": max(10, int(np.nanpercentile(act.out_deg[act.out_deg > 0], 95))),# «на многих»
        "BTW_P98":  p("betweenness", 98),   # брокерность — координатор
        "PR_P90":   p("pagerank", 90),
        "AUTH_P85": p("authority", 85),     # авторитет — сборщик
        "HUB_P85":  p("hub", 85),           # хаб — распределитель
        "KZT_P90":  p("out_kzt", 90),
        "PT_LO": 0.7, "PT_HI": 1.3,         # «прошло насквозь» ~ 1.0
    }


# ============================================================ роли
def assign_roles(df: pd.DataFrame, T: dict) -> pd.DataFrame:
    roles, scores, evid = [], [], []

    def rank01(col):
        r = df[col].rank(pct=True)
        return r.fillna(0.0)
    btw_r, pr_r, auth_r, hub_r = rank01("betweenness"), rank01("pagerank"), rank01("authority"), rank01("hub")

    for i, x in df.iterrows():
        ind, outd = int(x.in_deg), int(x.out_deg)
        pt = x.pass_through
        role, sc, ev = "peripheral", 0.10, ""

        # 1) КООРДИНАТОР — высокая брокерность + вес, есть и вход и выход (узел «между»)
        if (x.betweenness >= T["BTW_P98"] and x.pagerank >= T["PR_P90"]
                and ind >= 1 and outd >= 1):
            role = "coordinator"
            sc = round(float(0.5 * btw_r[i] + 0.3 * pr_r[i] + 0.2 * min(1, (ind + outd) / 20)), 3)
            ev = (f"betweenness={x.betweenness:.4f}(топ~2%), pagerank={x.pagerank:.4f}, "
                  f"мост: получает от {ind}, шлёт {outd}; seed-плательщиков {int(x.n_seed_in)}")

        # 2) РАСПРЕДЕЛИТЕЛЬ — веер на многих, выход доминирует
        elif (outd >= T["OUT_DEG_HI"] or (outd >= 5 and x.out_kzt >= T["KZT_P90"])) and outd >= ind:
            role = "distributor"
            sc = round(float(0.5 * hub_r[i] + 0.3 * min(1, outd / 30) + 0.2 * rank01("out_kzt")[i]), 3)
            ev = (f"разослал на {outd} получателей, {x.out_kzt:,.0f}₸ за {int(x.out_tx)} перев., "
                  f"hub={x.hub:.4f}; out/in по узлам {outd}/{ind}")

        # 3) СБОРЩИК — от многих, вход доминирует (для seed вход занижен -> опираемся на in_deg)
        elif ind >= T["IN_DEG_HI"] and ind >= outd:
            role = "consolidator"
            sc = round(float(0.5 * auth_r[i] + 0.3 * min(1, ind / 10) + 0.2 * min(1, int(x.n_seed_in) / 3)), 3)
            base = f"получил от {ind} плательщиков"
            if not x.is_seed:
                base += f", {x.in_kzt:,.0f}₸"
            ev = f"{base}; authority={x.authority:.4f}; seed-плательщиков {int(x.n_seed_in)}, циклы={bool(x.in_cycle)}"

        # 4) ТРАНЗИТ — есть вход и выход, деньги проходят насквозь (pass_through ~ 1)
        elif ind >= 1 and outd >= 1 and pd.notna(pt) and (not x.is_seed) and T["PT_LO"] <= pt <= T["PT_HI"]:
            role = "transit"
            closeness = 1 - min(1, abs(pt - 1.0))
            sc = round(float(0.6 * closeness + 0.4 * (1.0 if x.in_cycle else 0.3)), 3)
            td = "" if pd.isna(x.turnover_days) else f", оборот ~{x.turnover_days:.0f}д"
            ev = (f"pass_through={pt:.2f}: получил {x.in_kzt:,.0f}₸ -> отдал {x.out_kzt:,.0f}₸{td}; "
                  f"цикл={bool(x.in_cycle)}")

        # 5) ТЕРМИНАЛ — только вход, денег дальше не идёт (деньги осели)
        elif outd == 0 and ind >= 1:
            role = "terminal"
            if x.truncated_by_depth:
                sc = 0.35
                ev = (f"вход {x.in_kzt:,.0f}₸ от {ind}; ОБРЕЗАН 4-м коленом — исход не наблюдаем, "
                      f"статус терминала не подтверждён")
            else:
                sc = round(float(0.5 + 0.5 * rank01("in_kzt")[i]), 3)
                ev = (f"получил {x.in_kzt:,.0f}₸ от {ind} за {int(x.in_tx)} перев., исходящих нет "
                      f"(глубина {int(x.depth)}<4) -> деньги осели")

        # 6) остаток с двусторонним потоком, что не попал в транзит
        elif ind >= 1 and outd >= 1:
            if pd.notna(pt) and pt >= 0.5:
                role = "transit"
                sc = round(float(0.4 * min(1, pt) + 0.3 * (1 if x.in_cycle else 0.2) + 0.3 * pr_r[i]), 3)
                ev = f"pass_through={pt:.2f}, {x.in_kzt:,.0f}₸ -> {x.out_kzt:,.0f}₸; двусторонний поток"
            else:
                role = "peripheral"
                sc = 0.2
                ev = (f"удерживает средства: получил {x.in_kzt:,.0f}₸, отдал {x.out_kzt:,.0f}₸ "
                      f"(pass_through={pt:.2f}), in_deg={ind}")

        # 7) ПЕРИФЕРИЯ — нет признаков роли
        else:
            role = "peripheral"
            sc = 0.1
            if ind == 0 and outd == 0:
                ev = "изолированный узел: 0 входящих и 0 исходящих рёбер в выгрузке"
            else:
                ev = (f"слабая активность: in_deg={ind}, out_deg={outd}, "
                      f"вход {x.in_kzt:,.0f}₸, выход {x.out_kzt:,.0f}₸")

        roles.append(role); scores.append(round(float(sc), 3)); evid.append(ev[:200])

    df["role"] = roles
    df["role_score"] = scores
    df["evidence"] = evid
    return df


# ============================================================ кластеры
def cluster(G: nx.DiGraph, df: pd.DataFrame) -> pd.DataFrame:
    # Louvain на НЕОРИЕНТИРОВАННОЙ взвешенной проекции (направление теряется — оговорено явно, ловушка №4).
    UG = nx.Graph()
    UG.add_nodes_from(df.gid)
    for u, v, d in G.edges(data=True):
        w = d["sum_kzt"]
        if UG.has_edge(u, v):
            UG[u][v]["weight"] += w
        else:
            UG.add_edge(u, v, weight=w)
    comms = nx.community.louvain_communities(UG, weight="weight", seed=SEED)
    comms = sorted(comms, key=len, reverse=True)
    cid = {}
    for k, c in enumerate(comms):
        for n in c:
            cid[n] = k
    df["cluster_id"] = df.gid.map(cid).fillna(-1).astype(int)
    return df


def cluster_table(df: pd.DataFrame, G: nx.DiGraph) -> pd.DataFrame:
    rows = []
    for cidv, g in df.groupby("cluster_id"):
        gids = set(g.gid)
        internal = sum(d["sum_kzt"] for u, v, d in G.edges(data=True) if u in gids and v in gids)
        top = g.sort_values("priority_score", ascending=False).head(5)
        comp = g.role.value_counts().to_dict()
        rows.append({
            "cluster_id": int(cidv),
            "n_nodes": int(len(g)),
            "n_seed": int(g.is_seed.sum()),
            "sum_kzt_internal": round(float(internal), 0),
            "top_gids": "|".join(str(int(x)) for x in top.gid),
            "hypothesis": _hypothesis(comp, g, internal),
        })
    return pd.DataFrame(rows).sort_values("sum_kzt_internal", ascending=False)


def _hypothesis(comp: dict, g: pd.DataFrame, internal: float) -> str:
    c = comp.get
    coord, cons, dist, trans, term = c("coordinator", 0), c("consolidator", 0), c("distributor", 0), c("transit", 0), c("terminal", 0)
    n = len(g); kzt = f"{internal:,.0f}₸"
    if coord and (cons or trans):
        top = int(g.sort_values("priority_score", ascending=False).gid.iloc[0])
        return (f"Пирамида сбора: {coord} координатор(ов) над {cons} сборщик./{trans} транзит.; "
                f"вершина gid {top}; внутр. оборот {kzt}")
    if dist >= 2 and term >= dist:
        return f"Веерная рассылка: {dist} распределит. -> {term} терминалов; вывод/дробление, оборот {kzt}"
    if trans >= max(2, cons, dist):
        return f"Транзитная цепочка (layering): {trans} транзит.-узлов, {term} терминалов; оборот {kzt}"
    if cons >= 2:
        return f"Узел сбора: {cons} сборщик. аккумулируют от {trans} транзит./{term} терм.; оборот {kzt}"
    return f"Периферийный фрагмент: {n} узлов, слабая структура; оборот {kzt}"


# ============================================================ приоритет
def priority(df: pd.DataFrame) -> pd.DataFrame:
    def rank01(col):
        return df[col].rank(pct=True).fillna(0.0)
    vol = (df.in_kzt + df.out_kzt)
    df["_vol_r"] = vol.rank(pct=True).fillna(0.0)
    rw = df.role.map(ROLE_WEIGHT).fillna(0.1)
    raw = (0.30 * rw
           + 0.20 * rank01("pagerank")
           + 0.20 * rank01("betweenness")
           + 0.15 * df["_vol_r"]
           + 0.08 * (df.n_seed_in.clip(0, 3) / 3)
           + 0.07 * df.in_cycle.astype(float))
    mn, mx = raw.min(), raw.max()
    df["priority_score"] = ((raw - mn) / (mx - mn)).round(4) if mx > mn else 0.0
    df.drop(columns=["_vol_r"], inplace=True)
    return df


def top_nodes(df: pd.DataFrame, k: int = 30) -> pd.DataFrame:
    t = df.sort_values("priority_score", ascending=False).head(k).reset_index(drop=True)
    t.insert(0, "rank", t.index + 1)
    t["why"] = t.evidence
    return t[["rank", "gid", "role", "priority_score", "why"]]


# ============================================================ выгрузки
NODE_COLS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
             "in_deg", "out_deg", "in_kzt", "out_kzt", "pagerank", "pass_through",
             "depth", "is_seed", "truncated_by_depth",
             # доп. колонки (разрешено) — прозрачность метрик:
             "hub", "authority", "betweenness", "net_kzt", "n_seed_in", "in_cycle", "turnover_days"]


def write_outputs(df, clusters, tops, G, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df[NODE_COLS].to_csv(out_dir / "nodes_roles.csv", index=False)
    clusters.to_csv(out_dir / "clusters.csv", index=False)
    tops.to_csv(out_dir / "top_nodes.csv", index=False)
    _write_graph_json(df, G, out_dir)


def _write_graph_json(df, G, out_dir: Path):
    """Данные для интерактивной визуализации (направленный граф, роли, приоритет)."""
    # gid > 2^53 -> сериализуем id строками, иначе JS в JSON теряет точность и рвёт связи.
    nodes = [{
        "id": str(int(r.gid)), "role": r.role, "cluster": int(r.cluster_id),
        "priority": float(r.priority_score), "role_score": float(r.role_score),
        "in_kzt": float(r.in_kzt), "out_kzt": float(r.out_kzt),
        "in_deg": int(r.in_deg), "out_deg": int(r.out_deg),
        "depth": int(r.depth), "is_seed": bool(r.is_seed),
        "truncated": bool(r.truncated_by_depth), "evidence": r.evidence,
    } for r in df.itertuples(index=False)]
    links = [{"source": str(int(u)), "target": str(int(v)),
              "sum_kzt": float(d["sum_kzt"]), "n_tx": int(d["n_tx"])}
             for u, v, d in G.edges(data=True)]
    (out_dir / "graph.json").write_text(json.dumps({"nodes": nodes, "links": links},
                                                   ensure_ascii=False))


# ============================================================ main
def main():
    ap = argparse.ArgumentParser(description="Vertex — восстановление структуры по транзакциям")
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="../out")
    a = ap.parse_args()

    edges, nodes, tx = load(Path(a.data))
    G = build_graph(edges)
    df = features(G, nodes, tx)
    T = thresholds(df)
    df = assign_roles(df, T)
    df = cluster(G, df)
    df = priority(df)
    clusters = cluster_table(df, G)
    tops = top_nodes(df, 30)
    out = Path(a.out)
    write_outputs(df, clusters, tops, G, out)

    # summary.json — для визуализации и документации
    summary = {
        "n_nodes": int(len(df)), "n_edges": int(G.number_of_edges()),
        "n_seed": int(df.is_seed.sum()), "n_clusters": int(df.cluster_id.nunique()),
        "roles": {r: int((df.role == r).sum()) for r in ROLES},
        "role_weight": ROLE_WEIGHT,
        "thresholds": {k: (float(v) if isinstance(v, float) else int(v)) for k, v in T.items()},
        "terminals_truncated": int(df[(df.role == "terminal") & df.truncated_by_depth].shape[0]),
        "in_cycle": int(df.in_cycle.sum()),
        "top_clusters": clusters.head(6)[["cluster_id", "n_nodes", "n_seed",
                                          "sum_kzt_internal", "hypothesis"]].to_dict("records"),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    # --- отчёт в консоль (для защиты) ---
    print("=" * 60)
    print("VERTEX — готово. Пороги (data-driven):")
    for k, v in T.items():
        print(f"  {k:10} = {v}")
    print("-" * 60)
    print("Роли:")
    for role in ROLES:
        print(f"  {role:13}: {int((df.role == role).sum()):>5}")
    print(f"  ИТОГО строк : {len(df)}  (должно быть 2248)")
    print("-" * 60)
    print(f"Кластеров: {df.cluster_id.nunique()}  |  топ-узлов: {len(tops)}")
    print("Топ-5 к проверке:")
    for r in tops.head(5).itertuples(index=False):
        print(f"  #{r.rank} gid {r.gid:<6} {r.role:12} prio={r.priority_score}")
    print("=" * 60)


if __name__ == "__main__":
    main()
