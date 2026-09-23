#!/usr/bin/env python3
"""Быстрая разведка данных: распределения метрик и ловушки кейса."""
from pathlib import Path
import numpy as np, pandas as pd, networkx as nx

D = Path(__file__).resolve().parent.parent / "data"
edges = pd.read_parquet(D / "edges.parquet")
nodes = pd.read_parquet(D / "nodes.parquet")
tx = pd.read_parquet(D / "transactions.parquet"); tx["date"] = pd.to_datetime(tx["date"])

G = nx.DiGraph()
for r in edges.itertuples(index=False):
    G.add_edge(r.src, r.dst, sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))

in_deg = dict(G.in_degree()); out_deg = dict(G.out_degree())
in_kzt = dict(G.in_degree(weight="sum_kzt")); out_kzt = dict(G.out_degree(weight="sum_kzt"))
pr = nx.pagerank(G, weight="sum_kzt")
hubs, auth = nx.hits(G, max_iter=1000)
bc = nx.betweenness_centrality(G, weight=None, normalized=True)

df = nodes[["gid","depth","is_seed"]].copy()
for name, d in [("in_deg",in_deg),("out_deg",out_deg),("in_kzt",in_kzt),("out_kzt",out_kzt),
                ("pagerank",pr),("hub",hubs),("authority",auth),("betweenness",bc)]:
    df[name] = df.gid.map(d).fillna(0.0)
df["in_deg"]=df.in_deg.astype(int); df["out_deg"]=df.out_deg.astype(int)
df["pass_through"] = np.where(df.in_kzt>0, df.out_kzt/df.in_kzt.replace(0,np.nan), np.nan)
df["truncated"] = (df.depth==4)&(df.out_deg==0)

print("=== СЧЁТЧИКИ ===")
print("узлов:", len(df), "| seed:", int(df.is_seed.sum()))
print("orphans (0 рёбер):", int(((df.in_deg==0)&(df.out_deg==0)).sum()))
print("out_deg==0 всего:", int((df.out_deg==0).sum()), "| из них truncated(depth4):", int(df.truncated.sum()),
      "| настоящие терминалы(depth<4):", int(((df.out_deg==0)&(~df.truncated)&(df.in_deg>0)).sum()))
print("sent>received (out_kzt>in_kzt):", int((df.out_kzt>df.in_kzt).sum()))
print("in_deg>=3:", int((df.in_deg>=3).sum()), "| out_deg>=10:", int((df.out_deg>=10).sum()),
      "| и вход и выход:", int(((df.in_deg>0)&(df.out_deg>0)).sum()))
print("WCC:", nx.number_weakly_connected_components(G),
      "| крупнейшая:", max(len(c) for c in nx.weakly_connected_components(G)))

print("\n=== ПЕРЦЕНТИЛИ (среди узлов с активностью) ===")
act = df[(df.in_deg>0)|(df.out_deg>0)]
for col in ["in_deg","out_deg","in_kzt","out_kzt","pagerank","hub","authority","betweenness"]:
    q = np.nanpercentile(act[col], [50,75,90,95,98,99])
    print(f"{col:12} p50={q[0]:.4g} p75={q[1]:.4g} p90={q[2]:.4g} p95={q[3]:.4g} p98={q[4]:.4g} p99={q[5]:.4g}")

print("\n=== pass_through (не-seed, есть и вход и выход) ===")
pt = df[(~df.is_seed)&(df.in_kzt>0)&(df.out_kzt>0)].pass_through
print("p10..p90:", np.round(np.nanpercentile(pt,[10,25,50,75,90]),2))
print("seed pass_through медиана:", round(float(df[df.is_seed].pass_through.median(skipna=True) or 0),2))

# циклы (возвратные потоки)
try:
    cyc = list(nx.simple_cycles(G, length_bound=5))
    innodes = set().union(*[set(c) for c in cyc]) if cyc else set()
    print("\nциклов (<=5):", len(cyc), "| узлов в циклах:", len(innodes))
except Exception as e:
    print("cycles err:", e)

# сколько разных seed платит каждому узлу
seed_set = set(df[df.is_seed].gid)
seed_in = {}
for u,v in G.edges():
    if u in seed_set:
        seed_in[v] = seed_in.get(v,0)+1
ms = pd.Series(seed_in)
print("узлов, получающих от >=2 разных seed:", int((ms>=2).sum()), "| max seed-плательщиков:", int(ms.max() if len(ms) else 0))
