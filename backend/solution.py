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
import argparse, json, sys
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


def build_graph(edges, nodes) -> nx.DiGraph:
    G = nx.DiGraph()
    # СНАЧАЛА все узлы (в т.ч. 19 изолированных) -> центральности считаются по всем 2248
    G.add_nodes_from(int(g) for g in nodes.gid)
    for r in edges.itertuples(index=False):
        G.add_edge(int(r.src), int(r.dst),
                   sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return G


# ============================================================ денежно-взвешенный HITS
def weighted_hits(G: nx.DiGraph, max_iter: int = 500, tol: float = 1e-12):
    """
    HITS, взвешенный по сумме переводов (networkx игнорирует веса рёбер).
    authority(v) = Σ_{u->v} sum_kzt(u,v)·hub(u)   — к кому стекаются БОЛЬШИЕ деньги (сборщик)
    hub(u)       = Σ_{u->v} sum_kzt(u,v)·authority(v) — кто рассылает БОЛЬШИЕ деньги (распределитель)
    Детерминирован (старт из единиц), нормировка sum=1 как в nx.hits.
    """
    from scipy.sparse import csr_matrix
    order = list(G.nodes())
    idx = {n: i for i, n in enumerate(order)}
    n = len(order)
    if n == 0:
        return {}, {}
    rows, cols, data = [], [], []
    for u, v, d in G.edges(data=True):
        rows.append(idx[u]); cols.append(idx[v]); data.append(float(d["sum_kzt"]))
    A = csr_matrix((data, (rows, cols)), shape=(n, n))
    At = A.transpose().tocsr()
    h = np.ones(n); a = np.ones(n)
    for _ in range(max_iter):
        a_new = At.dot(h); h_new = A.dot(a_new)
        am = a_new.max() or 1.0; hm = h_new.max() or 1.0
        a_new /= am; h_new /= hm
        if np.abs(a_new - a).sum() + np.abs(h_new - h).sum() < tol:
            a, h = a_new, h_new; break
        a, h = a_new, h_new
    a = a / (a.sum() or 1.0); h = h / (h.sum() or 1.0)
    return {order[i]: float(h[i]) for i in range(n)}, {order[i]: float(a[i]) for i in range(n)}


# ============================================================ признаки
def features(G: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame) -> pd.DataFrame:
    in_deg  = dict(G.in_degree());              out_deg = dict(G.out_degree())
    in_kzt  = dict(G.in_degree(weight="sum_kzt"));  out_kzt = dict(G.out_degree(weight="sum_kzt"))
    in_tx   = dict(G.in_degree(weight="n_tx"));     out_tx  = dict(G.out_degree(weight="n_tx"))
    pr      = nx.pagerank(G, weight="sum_kzt")
    # HITS, взвешенный по деньгам: authority=сборщик, hub=распределитель (см. weighted_hits)
    hubs, auth = weighted_hits(G)
    # betweenness, взвешенный: расстояние = 1/сумма -> крупные потоки = «короче» пути,
    # посредничество считается ПО ДЕНЬГАМ. Это выбранная аналитическая модель (не факт. маршрут денег).
    for _u, _v, _d in G.edges(data=True):
        _d["dist"] = 1.0 / _d["sum_kzt"] if _d["sum_kzt"] > 0 else 1.0
    btw = nx.betweenness_centrality(G, weight="dist", normalized=True)

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
    # HITS суммирует в недетерминированном порядке (~1e-16 шум) -> флипает ранги при ничьих.
    # Округляем метрики до 12 знаков: шум убирается, значимая точность сохраняется. Итог воспроизводим.
    for _c in ("pagerank", "hub", "authority", "betweenness"):
        df[_c] = df[_c].round(12) + 0.0   # +0.0 нормализует -0.0 -> 0.0 (иначе "-0.0000" в evidence)
    df["net_kzt"] = df.in_kzt - df.out_kzt
    # pass_through = out/in. Неопределённость -> сентинел -1 (не выдуманный 0):
    #   -1 = входа нет ИЛИ узел seed (у seed вход занижен, отношение неприменимо).
    pt = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt.replace(0, np.nan), -1.0)
    pt = np.where(df.is_seed.values, -1.0, pt)
    df["pass_through"] = pt
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
        cyc = list(nx.simple_cycles(G, length_bound=5))       # networkx >= 3.1
    except TypeError:
        # старый networkx без length_bound — ограничиваем длину вручную, но НЕ прячем сбой
        print("ВНИМАНИЕ: networkx без length_bound, фильтрую циклы вручную (обнови до >=3.2)")
        cyc = [c for c in nx.simple_cycles(G) if len(c) <= 5]
    in_cyc = set().union(*[set(c) for c in cyc]) if cyc else set()
    df["in_cycle"] = df.gid.isin(in_cyc)

    # --- временной сигнал: медианный лаг «получил -> отправил» (быстрый оборот = транзит) ---
    #     -1 = нет наблюдаемой пары получения/отправки (не выдуманный 0).
    df["turnover_days"] = _turnover_days(G, tx, df).fillna(-1.0)
    return df


def _turnover_days(G, tx, df) -> pd.Series:
    """Для узлов с входом и выходом: медиана (дата отправки - ближайшая предыдущая дата получения)."""
    ins, outs = {}, {}
    for r in tx.itertuples(index=False):
        outs.setdefault(int(r.src), []).append(r.date)
        ins.setdefault(int(r.dst), []).append(r.date)
    res = {}
    for gid in df.gid:
        di = np.array(sorted(ins.get(int(gid), [])))
        do = outs.get(int(gid), [])
        if di.size == 0 or not do:
            continue
        lags = []
        for t in do:  # бинарный поиск ближайшей ПРЕДШЕСТВУЮЩЕЙ даты получения
            k = int(np.searchsorted(di, t, side="right")) - 1
            if k >= 0:
                lags.append((t - di[k]).days)
        if lags:
            res[int(gid)] = float(np.median(lags))
    return df.gid.map(res)


# ============================================================ пороги (data-driven)
def thresholds(df: pd.DataFrame) -> dict:
    act = df[(df.in_deg > 0) | (df.out_deg > 0)]
    p = lambda col, q: float(np.nanpercentile(act[col], q))
    return {
        "IN_DEG_HI":  3,                                                   # документированный порог «от нескольких»
        "OUT_DEG_HI": float(np.nanpercentile(act.out_deg[act.out_deg > 0], 95)),  # p95 дробный, без скрытого пола
        "BTW_P98":  p("betweenness", 98),   # брокерность (по деньгам) — координатор
        "PR_P90":   p("pagerank", 90),
        "KZT_P90":  p("out_kzt", 90),
        "PT_LO": 0.7, "PT_HI": 1.3,         # «прошло насквозь» ~ 1.0 (структурные константы, оставлены явно)
    }


# ============================================================ роли
def assign_roles(df: pd.DataFrame, T: dict) -> pd.DataFrame:
    roles, scores, evid = [], [], []

    def rank01(col):
        r = df[col].rank(pct=True)
        return r.fillna(0.0)
    # все ранги считаем ОДИН раз (не внутри цикла — замечание аудита по производительности)
    btw_r, pr_r, auth_r, hub_r = rank01("betweenness"), rank01("pagerank"), rank01("authority"), rank01("hub")
    outkzt_r, inkzt_r = rank01("out_kzt"), rank01("in_kzt")

    # ПОРЯДОК ПРАВИЛ (precedence) — первое подходящее выигрывает:
    #   1 обрезка 4-м коленом → terminal(0.35)   2 сток (out=0) → terminal
    #   3 coordinator   4 distributor   5 consolidator   6 transit   7 transit(резерв)   8 peripheral
    # Слепая зона и сток проверяются РАНЬШЕ ролей с исходящими, чтобы out_deg=0 не попал в сборщика.
    # Для SEED pass_through неприменим (вход занижен) -> seed НЕ классифицируются транзитом и НЕ
    # показывают сырую ВХОДЯЩУЮ сумму (исходящую показываем — она полностью наблюдаема).
    for i, x in df.iterrows():
        ind, outd = int(x.in_deg), int(x.out_deg)
        pt = float(x.pass_through)     # -1 => неприменимо (нет входа или seed)
        seed = bool(x.is_seed)
        role, sc, ev = "peripheral", 0.10, ""

        # 1) СЛЕПАЯ ЗОНА — обрезка 4-м коленом (раньше всех): terminal, не подтверждён
        if x.truncated_by_depth:
            role = "terminal"; sc = 0.35
            ev = (f"вход от {ind} плательщиков; ОБРЕЗАН 4-м коленом — исход не наблюдаем, "
                  f"статус терминала не подтверждён")

        # 2) ТЕРМИНАЛ — нет исходящих, есть входящие: деньги осели (гипотеза)
        elif outd == 0 and ind >= 1:
            role = "terminal"
            sc = round(float(0.5 + 0.5 * inkzt_r[i]), 3)
            if seed:
                ev = (f"получил от {ind} за {int(x.in_tx)} перев. (вход seed занижен), исходящих нет "
                      f"(depth {int(x.depth)}<4) -> вероятный сток")
            else:
                ev = (f"получил {x.in_kzt:,.0f}₸ от {ind} за {int(x.in_tx)} перев., исходящих нет "
                      f"(глубина {int(x.depth)}<4) -> деньги осели")

        # 3) КООРДИНАТОР — денежная брокерность + вес, есть вход и выход (узел-«мост»)
        elif (x.betweenness >= T["BTW_P98"] and x.pagerank >= T["PR_P90"] and ind >= 1 and outd >= 1):
            role = "coordinator"
            sc = round(float(0.5 * btw_r[i] + 0.3 * pr_r[i] + 0.2 * min(1, (ind + outd) / 20)), 3)
            ev = (f"betweenness={x.betweenness:.4f}(топ~2%), pagerank={x.pagerank:.4f}, "
                  f"мост: получает от {ind}, шлёт {outd}; seed-плательщиков {int(x.n_seed_in)}")

        # 4) РАСПРЕДЕЛИТЕЛЬ — веер на многих (fan-out), выход доминирует
        elif ((outd >= T["OUT_DEG_HI"] or (outd >= 5 and x.out_kzt >= T["KZT_P90"])) and outd >= ind):
            role = "distributor"
            avg = x.out_kzt / max(1, int(x.out_tx))
            sc = round(float(0.5 * outkzt_r[i] + 0.3 * min(1, outd / 30) + 0.2 * hub_r[i]), 3)
            ev = (f"разослал на {outd} получателей, {x.out_kzt:,.0f}₸ за {int(x.out_tx)} перев. "
                  f"(≈{avg:,.0f}₸/перевод); out/in по узлам {outd}/{ind}")

        # 5) СБОРЩИК — получает от >=3 (структурный порог), вход доминирует, есть исходящие
        elif ind >= T["IN_DEG_HI"] and ind >= outd:
            role = "consolidator"
            sc = round(float(0.5 * auth_r[i] + 0.3 * min(1, ind / 10) + 0.2 * min(1, int(x.n_seed_in) / 3)), 3)
            base = f"получил от {ind} плательщиков"
            if not seed:
                base += f", {x.in_kzt:,.0f}₸"       # для seed сырой вход не показываем (занижен)
            ev = f"{base}; authority={x.authority:.4f}; seed-плательщиков {int(x.n_seed_in)}, циклы={bool(x.in_cycle)}"

        # 6) ТРАНЗИТ — не-seed, вход и выход, деньги проходят насквозь (pass_through ~ 1)
        elif (not seed) and ind >= 1 and outd >= 1 and T["PT_LO"] <= pt <= T["PT_HI"]:
            role = "transit"
            closeness = 1 - min(1, abs(pt - 1.0))
            sc = round(float(0.6 * closeness + 0.4 * (1.0 if x.in_cycle else 0.3)), 3)
            td = f", оборот ~{x.turnover_days:.0f}д" if x.turnover_days >= 0 else ""
            ev = (f"pass_through={pt:.2f}: получил {x.in_kzt:,.0f}₸ -> отдал {x.out_kzt:,.0f}₸{td}; "
                  f"цикл={bool(x.in_cycle)}")

        # 7) ТРАНЗИТ (резерв) — не-seed, двусторонний поток, прошло >=50%
        elif (not seed) and ind >= 1 and outd >= 1 and pt >= 0.5:
            role = "transit"
            sc = round(float(0.4 * min(1, pt) + 0.3 * (1 if x.in_cycle else 0.2) + 0.3 * pr_r[i]), 3)
            ev = f"pass_through={pt:.2f}, {x.in_kzt:,.0f}₸ -> {x.out_kzt:,.0f}₸; двусторонний поток"

        # 8) ПЕРИФЕРИЯ — нет признаков роли
        else:
            role = "peripheral"; sc = 0.1
            if ind == 0 and outd == 0:
                ev = "изолированный узел: 0 входящих и 0 исходящих рёбер в выгрузке" + (" (seed)" if seed else "")
            elif seed and ind >= 1 and outd >= 1:
                sc = 0.2
                ev = (f"seed с входом/выходом: pass_through неприменим (вход занижен); "
                      f"отдал {x.out_kzt:,.0f}₸ на {outd}, in_deg={ind}")
            else:
                inpart = "" if seed else f"вход {x.in_kzt:,.0f}₸, "
                ev = f"слабая активность: in_deg={ind}, out_deg={outd}, {inpart}выход {x.out_kzt:,.0f}₸"

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
    # при равном приоритете упорядочиваем по gid -> детерминированный порядок
    t = df.sort_values(["priority_score", "gid"], ascending=[False, True]).head(k).reset_index(drop=True)
    t.insert(0, "rank", t.index + 1)
    t["why"] = t.evidence
    return t[["rank", "gid", "role", "priority_score", "why"]]


# ============================================================ кейсы (для панели аналитика)
def build_cases(df: pd.DataFrame, clusters: pd.DataFrame, tx: pd.DataFrame, max_cases: int = 30) -> list:
    """
    Автоматически заводит кейсы по подозрительным кластерам: собирает «логи» (транзакции
    между ключевыми узлами) и рекомендованное действие. Аналитик закрывает кейсы в интерфейсе.
    """
    # индекс транзакций по узлу (для «логов»)
    tx_by_node = {}
    for r in tx.itertuples(index=False):
        tx_by_node.setdefault(int(r.src), []).append((r.date, int(r.src), int(r.dst), float(r.sum_kzt)))
        tx_by_node.setdefault(int(r.dst), []).append((r.date, int(r.src), int(r.dst), float(r.sum_kzt)))
    maxp = df.groupby("cluster_id").priority_score.max()

    cases = []
    for row in clusters.itertuples(index=False):
        cid = int(row.cluster_id)
        g = df[df.cluster_id == cid]
        roles = g.role.value_counts().to_dict()
        has_coord = roles.get("coordinator", 0) > 0
        has_cons = roles.get("consolidator", 0) > 0
        # кейс заводим только на «действенные» кластеры
        if not (has_coord or has_cons or (int(row.n_seed) > 0 and float(row.sum_kzt_internal) > 0)):
            continue
        key = g.sort_values("priority_score", ascending=False).head(5)
        key_set = set(int(x) for x in key.gid)
        cluster_set = set(int(x) for x in g.gid)

        # «логи»: транзакции, затрагивающие ключевые узлы, внутри кластера
        seen, recs = set(), []
        for gid in key_set:
            for dt, s, d, amt in tx_by_node.get(gid, []):
                if (s in key_set or d in key_set) and s in cluster_set and d in cluster_set:
                    k = (s, d, dt, amt)
                    if k in seen:
                        continue
                    seen.add(k); recs.append((dt, s, d, amt))
        recs.sort(key=lambda t: (t[0], -t[3]))
        logs = [f"{dt.strftime('%d.%m')} · …{str(s)[-6:]}→…{str(d)[-6:]} · {amt:,.0f}₸"
                for dt, s, d, amt in recs[:12]]

        mp = float(maxp.get(cid, 0.0) or 0.0)
        sev = "high" if (has_coord or mp >= 0.8) else ("medium" if mp >= 0.5 else "low")
        if has_coord:
            tc = int(g[g.role == "coordinator"].sort_values("priority_score", ascending=False).gid.iloc[0])
            action = f"Запрос в правоохранительные органы по вершине …{str(tc)[-6:]} (координатор)"
        elif has_cons:
            action = "Углублённая проверка точки консолидации и её плательщиков"
        else:
            action = "Мониторинг активности кластера"

        cases.append({
            "id": None,
            "cluster_id": cid,
            "title": str(row.hypothesis).split(";")[0][:90],
            "severity": sev,
            "priority": round(mp, 3),
            "hypothesis": str(row.hypothesis),
            "n_nodes": int(row.n_nodes), "n_seed": int(row.n_seed),
            "turnover_kzt": float(row.sum_kzt_internal),
            "roles": {k: int(v) for k, v in roles.items()},
            "key_nodes": [{"gid": str(int(x.gid)), "role": x.role,
                           "priority": round(float(x.priority_score), 3), "evidence": x.evidence}
                          for x in key.itertuples(index=False)],
            "logs": logs,
            "recommended_action": action,
        })

    cases.sort(key=lambda c: (-c["priority"], -c["turnover_kzt"]))
    cases = cases[:max_cases]
    for i, c in enumerate(cases, 1):
        c["id"] = f"CASE-{i:03d}"
    return cases


# ============================================================ выгрузки
NODE_COLS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
             "in_deg", "out_deg", "in_kzt", "out_kzt", "pagerank", "pass_through",
             "depth", "is_seed", "truncated_by_depth",
             # доп. колонки (разрешено) — прозрачность метрик:
             "hub", "authority", "betweenness", "net_kzt", "n_seed_in", "in_cycle", "turnover_days",
             "in_tx", "out_tx"]


def write_outputs(df, clusters, tops, G, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    df[NODE_COLS].to_csv(out_dir / "nodes_roles.csv", index=False, encoding="utf-8")
    clusters.to_csv(out_dir / "clusters.csv", index=False, encoding="utf-8")
    tops.to_csv(out_dir / "top_nodes.csv", index=False, encoding="utf-8")
    _write_graph_json(df, G, out_dir)


def _write_graph_json(df, G, out_dir: Path):
    """Данные для интерактивной визуализации (направленный граф, роли, приоритет, циклы)."""
    # рёбра, входящие в простые циклы (<=5) -> для подсветки возвратных потоков (layering)
    try:
        cyc = list(nx.simple_cycles(G, length_bound=5))
    except TypeError:
        cyc = [c for c in nx.simple_cycles(G) if len(c) <= 5]
    cyc_edges = set()
    for c in cyc:
        for j in range(len(c)):
            cyc_edges.add((c[j], c[(j + 1) % len(c)]))
    # gid > 2^53 -> сериализуем id строками, иначе JS в JSON теряет точность и рвёт связи.
    nodes = [{
        "id": str(int(r.gid)), "role": r.role, "cluster": int(r.cluster_id),
        "priority": float(r.priority_score), "role_score": float(r.role_score),
        "in_kzt": float(r.in_kzt), "out_kzt": float(r.out_kzt),
        "in_deg": int(r.in_deg), "out_deg": int(r.out_deg),
        "depth": int(r.depth), "is_seed": bool(r.is_seed),
        "truncated": bool(r.truncated_by_depth), "cycle": bool(r.in_cycle),
        "n_seed_in": int(r.n_seed_in), "evidence": r.evidence,
    } for r in df.itertuples(index=False)]
    links = [{"source": str(int(u)), "target": str(int(v)),
              "sum_kzt": float(d["sum_kzt"]), "n_tx": int(d["n_tx"]),
              "cyc": ((u, v) in cyc_edges)}
             for u, v, d in G.edges(data=True)]
    (out_dir / "graph.json").write_text(json.dumps({"nodes": nodes, "links": links},
                                                   ensure_ascii=False), encoding="utf-8")


# ============================================================ main
# ============================================================ валидатор выходов
def validate_outputs(df: pd.DataFrame, clusters: pd.DataFrame, tops: pd.DataFrame) -> bool:
    """Строгая проверка: схема, типы, диапазоны, полнота, ловушки. Падает при нарушении."""
    assert len(df) == 2248, f"ожидалось 2248 узлов, получено {len(df)}"
    assert df.gid.is_unique, "gid не уникальны"
    for c in NODE_COLS:
        assert c in df.columns, f"нет обязательной колонки {c}"
    assert set(df.role) <= set(ROLES), f"недопустимые роли: {set(df.role) - set(ROLES)}"
    assert df.role_score.between(0, 1).all(), "role_score вне [0,1]"
    assert df.priority_score.between(0, 1).all(), "priority_score вне [0,1]"
    assert (df.cluster_id >= 0).all(), "есть узлы без кластера"
    ev = df.evidence.astype(str)
    assert ev.str.len().between(1, 200).all(), "evidence пустой или >200 символов"
    assert ev.str.contains(r"\d").all(), "evidence без чисел"
    assert df.depth.between(0, 4).all(), "depth вне диапазона 0..4"
    tr = df[df.truncated_by_depth]
    assert (tr.role == "terminal").all(), "обрезанные 4-м коленом должны быть terminal"
    assert tr.evidence.str.contains("ОБРЕЗАН").all(), "обрезанные без пометки в evidence"
    assert int((df[df.is_seed].role == "transit").sum()) == 0, "seed не должен быть transit"
    assert int(clusters.n_nodes.sum()) == 2248, "сумма n_nodes кластеров != 2248"
    assert clusters.hypothesis.astype(str).str.len().gt(0).all(), "пустая гипотеза кластера"
    assert len(tops) >= 20, "top_nodes должно быть >= 20"
    assert list(tops.priority_score) == sorted(tops.priority_score, reverse=True), "top не отсортирован"
    return True


# ============================================================ устойчивость сети
def compute_resilience(G: nx.DiGraph, ranked_gids: list, ks=(0, 5, 10, 20, 30)) -> list:
    """Последовательно удаляем топ-N узлов рейтинга и меряем слабую связность оставшейся сети."""
    rows = []
    for k in ks:
        H = G.copy()
        H.remove_nodes_from(ranked_gids[:k])
        comps = list(nx.weakly_connected_components(H))
        rows.append({
            "removed": int(k),
            "nodes": int(H.number_of_nodes()),
            "edges": int(H.number_of_edges()),
            "components": int(len(comps)),
            "largest": int(max((len(c) for c in comps), default=0)),
            "singletons": int(sum(1 for c in comps if len(c) == 1)),
        })
    return rows


def main():
    # Windows-консоль по умолчанию не utf-8 -> кириллица/emoji в print падают. Чиним.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Vertex — восстановление структуры по транзакциям")
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="../out")
    a = ap.parse_args()

    edges, nodes, tx = load(Path(a.data))
    G = build_graph(edges, nodes)
    df = features(G, nodes, tx)
    T = thresholds(df)
    df = assign_roles(df, T)
    df = cluster(G, df)
    df = priority(df)
    clusters = cluster_table(df, G)
    tops = top_nodes(df, 30)
    validate_outputs(df, clusters, tops)          # строгий контракт: падает при нарушении
    out = Path(a.out)
    write_outputs(df, clusters, tops, G, out)

    # resilience.json — устойчивость сети при удалении топ-N узлов рейтинга
    ranked = [int(g) for g in df.sort_values(["priority_score", "gid"], ascending=[False, True]).gid]
    (out / "resilience.json").write_text(
        json.dumps(compute_resilience(G, ranked), ensure_ascii=False), encoding="utf-8")

    # cases.json — автосозданные кейсы для панели аналитика
    cases = build_cases(df, clusters, tx)
    (out / "cases.json").write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")

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
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

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
