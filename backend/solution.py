"""Vertex: reproducible graph analytics; roles are hypotheses, not findings of guilt."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
import networkx as nx
from cases import build_cases, validate_cases, snapshot_id

ROOT = Path(__file__).resolve().parents[1]
SEED = 42
ROLES = ["coordinator", "distributor", "consolidator", "transit", "terminal", "peripheral"]
ROLE_WEIGHT = dict(coordinator=1., consolidator=.85, distributor=.75, transit=.55, terminal=.4, peripheral=.1)
NODE_COLS = ["gid","role","role_score","cluster_id","priority_score","evidence",
 "in_deg","out_deg","in_kzt","out_kzt","pagerank","pass_through","depth","is_seed",
 "truncated_by_depth","hub","authority","betweenness","net_kzt","n_seed_in","in_cycle",
 "turnover_days","in_tx","out_tx"]
CLUSTER_COLS = ["cluster_id","n_nodes","n_seed","sum_kzt_internal","top_gids","hypothesis"]
TOP_COLS = ["rank","gid","role","priority_score","why"]

def load(data_dir):
    edges = pd.read_parquet(data_dir/"edges.parquet")
    nodes = pd.read_parquet(data_dir/"nodes.parquet")
    tx = pd.read_parquet(data_dir/"transactions.parquet")
    for frame,cols in [(edges,["src","dst","sum_kzt","n_tx","depth"]),
                       (nodes,["gid","depth","is_seed"]), (tx,["src","dst","date","sum_kzt"])]:
        if not set(cols) <= set(frame.columns) or frame[cols].isna().any().any():
            raise ValueError("Missing required input columns or values")
    if nodes.empty or nodes.gid.duplicated().any():
        raise ValueError("Node inventory must be nonempty and unique")
    for frame,cols in [(nodes,["gid","depth"]),(edges,["src","dst","n_tx","depth"]),(tx,["src","dst"])]:
        for col in cols:
            if not pd.api.types.is_integer_dtype(frame[col]):
                raise ValueError(f"{col} must be integer")
    if not pd.api.types.is_bool_dtype(nodes.is_seed) or not nodes.depth.between(0,4).all():
        raise ValueError("Expected boolean seed and depth 0..4")
    ids = set(nodes.gid)
    for frame in [edges,tx]:
        if not (set(frame.src)|set(frame.dst)) <= ids:
            raise ValueError("Unknown endpoint")
        if not np.isfinite(frame.sum_kzt).all() or (frame.sum_kzt<=0).any():
            raise ValueError("Amounts must be finite and positive")
    if edges.duplicated(["src","dst"]).any() or (edges.n_tx<=0).any():
        raise ValueError("Edges must be unique directed pairs with positive counts")
    tx["date"] = pd.to_datetime(tx.date, errors="raise")
    agg = tx.groupby(["src","dst"]).agg(amount=("sum_kzt","sum"),count=("sum_kzt","size")).sort_index()
    exp = edges.set_index(["src","dst"]).sort_index()
    if (not exp.index.equals(agg.index) or not np.allclose(exp.sum_kzt,agg.amount,rtol=1e-9,atol=.01)
        or not np.array_equal(exp.n_tx,agg["count"])):
        raise ValueError("Transaction and edge aggregates disagree")
    return (edges.sort_values(["src","dst"]).reset_index(drop=True),
            nodes.sort_values("gid").reset_index(drop=True),
            tx.sort_values(["src","dst","date"]).reset_index(drop=True))

def build_graph(edges,nodes=None):
    G = nx.DiGraph()
    if nodes is not None:
        G.add_nodes_from(int(g) for g in sorted(nodes.gid))
    for r in edges.sort_values(["src","dst"]).itertuples(index=False):
        w = float(r.sum_kzt)
        G.add_edge(int(r.src),int(r.dst),sum_kzt=w,weight=w,distance=1/w,n_tx=int(r.n_tx),depth=int(r.depth))
    return G

def _turnover_days(G,tx,df):
    ins = {int(g):np.sort(v.to_numpy(dtype="datetime64[ns]")) for g,v in tx.groupby("dst").date}
    res = {}
    for gid,dates in tx.groupby("src").date:
        di = ins.get(int(gid))
        if di is None or not len(di): continue
        do = dates.to_numpy(dtype="datetime64[ns]")
        pos = np.searchsorted(di,do,side="right")-1
        ok = pos>=0
        if ok.any():
            res[int(gid)] = float(np.median((do[ok]-di[pos[ok]])/np.timedelta64(1,"D")))
    return df.gid.map(res).fillna(-1.0)

def weighted_hits(G,max_iter=10000,tol=1e-12):
    """Team monetary HITS with fixed start and explicit convergence failure."""
    from scipy.sparse import csr_matrix
    order=sorted(G); size=len(order)
    if not size: return {},{}
    index={n:i for i,n in enumerate(order)}
    edges=list(G.edges(data=True))
    A=csr_matrix(([d["sum_kzt"] for _,_,d in edges],
                  ([index[u] for u,_,_ in edges],[index[v] for _,v,_ in edges])),shape=(size,size))
    h=np.ones(size); a=np.ones(size)
    for _ in range(max_iter):
        an=A.T@h; hn=A@an
        an/=an.max() or 1.; hn/=hn.max() or 1.
        if np.abs(an-a).sum()+np.abs(hn-h).sum()<tol:
            a,h=an,hn; break
        a,h=an,hn
    else:
        raise nx.PowerIterationFailedConvergence(max_iter)
    a/=a.sum() or 1.; h/=h.sum() or 1.
    return dict(zip(order,map(float,h))),dict(zip(order,map(float,a)))

def features(G,nodes,tx):
    df = nodes[["gid","depth","is_seed"]].copy()
    df[["gid","depth"]] = df[["gid","depth"]].astype("int64")
    for name,values in [("in_deg",G.in_degree()),("out_deg",G.out_degree()),
        ("in_kzt",G.in_degree(weight="sum_kzt")),("out_kzt",G.out_degree(weight="sum_kzt")),
        ("in_tx",G.in_degree(weight="n_tx")),("out_tx",G.out_degree(weight="n_tx"))]:
        df[name] = df.gid.map(dict(values)).fillna(0)
    for col in ["in_deg","out_deg","in_tx","out_tx"]: df[col] = df[col].astype("int64")
    for col in ["in_kzt","out_kzt"]: df[col] = df[col].astype(float)
    if G.number_of_edges():
        hubs,auth = weighted_hits(G)
        pr = nx.pagerank(G,weight="sum_kzt",tol=1e-12,max_iter=1000)
        btw = nx.betweenness_centrality(G,weight="distance",normalized=True)
    else:
        hubs = auth = btw = dict.fromkeys(G,0.)
        pr = dict.fromkeys(G,1/len(G))
    for col,values in [("pagerank",pr),("hub",hubs),("authority",auth),("betweenness",btw)]:
        df[col] = df.gid.map(values).fillna(0.).round(12)+0.0
    df["net_kzt"] = df.in_kzt-df.out_kzt
    df["pass_through"] = -1.
    valid = (df.in_kzt>0)&~df.is_seed
    df.loc[valid,"pass_through"] = df.loc[valid,"out_kzt"]/df.loc[valid,"in_kzt"]
    df["truncated_by_depth"] = (df.depth==4)&(df.out_deg==0)
    seeds,seed_in = set(df.loc[df.is_seed,"gid"]),defaultdict(int)
    for u,v in G.edges:
        if u in seeds: seed_in[v]+=1
    df["n_seed_in"] = df.gid.map(seed_in).fillna(0).astype("int64")
    cycles,cycle_nodes,cycle_edges = [],set(),set()
    for c in nx.simple_cycles(G,length_bound=5):
        start = c.index(min(c)); c = c[start:]+c[:start]
        cycles.append(c); cycle_nodes.update(c)
        cycle_edges.update(zip(c,c[1:]+c[:1]))
    G.graph["cycles"] = sorted(cycles)
    nx.set_edge_attributes(G,{e:e in cycle_edges for e in G.edges},"in_cycle")
    df["in_cycle"] = df.gid.isin(cycle_nodes)
    df["turnover_days"] = _turnover_days(G,tx,df)
    return df

def thresholds(df):
    a = df[(df.in_deg>0)|(df.out_deg>0)]
    p = lambda v,q: float(np.percentile(v,q)) if len(v) else 0.
    return dict(IN_DEG_HI=3,OUT_DEG_HI=p(a.loc[a.out_deg>0,"out_deg"],95),
        BTW_P98=p(a.betweenness,98),PR_P90=p(a.pagerank,90),KZT_P90=p(a.out_kzt,90),PT_LO=.7,PT_HI=1.3)

def assign_roles(df,T):
    df = df.copy()
    ranks = {c:df[c].rank(pct=True).to_numpy() for c in ["betweenness","pagerank","authority","hub","in_kzt","out_kzt"]}
    roles,scores,evidence = [],[],[]
    for i,x in enumerate(df.itertuples(index=False)):
        ind,outd,pt = x.in_deg,x.out_deg,x.pass_through
        role,sc,reason = "peripheral",.1,"Недостаточно структурных признаков"
        if x.truncated_by_depth:
            role,sc = "terminal",.35
            reason = "Слепая зона: 4-е колено; нужен запрос 5-го; терминал не подтверждён"
        elif outd==0 and ind>=1:
            role,sc = "terminal",.5+.5*ranks["in_kzt"][i]
            reason = "Гипотеза терминала: исходящие не наблюдаются"
        elif ind>=1 and outd>=1 and x.betweenness>=T["BTW_P98"] and x.pagerank>=T["PR_P90"]:
            role = "coordinator"
            sc = .5*ranks["betweenness"][i]+.3*ranks["pagerank"][i]+.2*min(1,(ind+outd)/20)
            reason = f"Координирующий кандидат: btw={x.betweenness:.4g}, PR={x.pagerank:.4g}"
        elif outd>0 and outd>=ind and (outd>=T["OUT_DEG_HI"] or (outd>=5 and x.out_kzt>=T["KZT_P90"])):
            role = "distributor"
            sc = .5*ranks["hub"][i]+.3*min(1,outd/30)+.2*ranks["out_kzt"][i]
            reason = f"Признаки распределения: {outd} получателей, hub={x.hub:.3g}"
        elif ind>=3 and ind>=outd:
            role = "consolidator"
            sc = .5*ranks["authority"][i]+.3*min(1,ind/10)+.2*min(1,x.n_seed_in/3)
            reason = f"Признаки консолидации: {ind} плательщиков, seed={x.n_seed_in}"
        elif ind>=1 and outd>=1 and not x.is_seed and T["PT_LO"]<=pt<=T["PT_HI"]:
            role = "transit"
            sc = .6*(1-min(1,abs(pt-1)))+.4*(1 if x.in_cycle else .3)
            reason = f"Признаки транзита: out/in={pt:.3g}, цикл={int(x.in_cycle)}"
        elif ind>=1 and outd>=1 and not x.is_seed and pt>=.5:
            role = "transit"
            sc = .4*min(1,pt)+.3*(1 if x.in_cycle else .2)+.3*ranks["pagerank"][i]
            reason = f"Двусторонний поток: out/in={pt:.3g}, цикл={int(x.in_cycle)}"
        if x.is_seed:
            detail = f"seed: вход неполон; контрагенты {ind}/{outd}; перев. {x.in_tx}/{x.out_tx}"
        else:
            detail = f"вх {x.in_kzt:.6g} KZT/{x.in_tx} перев.; исх {x.out_kzt:.6g} KZT/{x.out_tx} перев."
        ev = reason+"; "+detail
        if len(ev)>=200: raise ValueError("Evidence must be shorter than 200 characters")
        roles.append(role); scores.append(round(float(sc),3)); evidence.append(ev)
    df["role"],df["role_score"],df["evidence"] = roles,scores,evidence
    return df

def cluster(G,df):
    UG = nx.Graph(); UG.add_nodes_from(sorted(G))
    for u,v,d in G.edges(data=True):
        if UG.has_edge(u,v): UG[u][v]["weight"]+=d["sum_kzt"]
        else: UG.add_edge(u,v,weight=d["sum_kzt"])
    comms = nx.community.louvain_communities(UG,weight="weight",seed=SEED) if UG.number_of_edges() else [{n} for n in UG]
    comms = sorted(comms,key=lambda c:(-len(c),min(c)))
    df["cluster_id"] = df.gid.map({n:k for k,c in enumerate(comms) for n in c}).astype("int64")
    return df

def priority(df):
    rank = lambda s:s.rank(pct=True).fillna(0.)
    raw = (.30*df.role.map(ROLE_WEIGHT)+.20*rank(df.pagerank)+.20*rank(df.betweenness)
        +.15*rank(df.in_kzt+df.out_kzt)+.08*df.n_seed_in.clip(upper=3)/3+.07*df.in_cycle.astype(float))
    df["priority_score"] = ((raw-raw.min())/(raw.max()-raw.min())).round(4) if raw.max()>raw.min() else 0.
    return df

def ranked(df):
    return df.sort_values(["priority_score","gid"],ascending=[False,True],kind="stable")

def _hypothesis(comp,g,internal):
    cons,dist,trans = (comp.get(r,0) for r in ["consolidator","distributor","transit"])
    pattern = ("консолидация средств" if cons>=max(1,dist,trans) else
        "веерное распределение" if dist>=max(1,cons,trans) else
        "транзитная структура" if trans else "периферийный фрагмент")
    return (f"Гипотеза: {pattern}. Сборщиков {cons}, распределителей {dist}, транзитов {trans}; "
            f"внутренний оборот {internal:,.0f} KZT. Требует проверки.")

def cluster_table(df,G):
    cid = dict(zip(df.gid,df.cluster_id)); totals = defaultdict(float)
    for u,v,d in G.edges(data=True):
        if cid[u]==cid[v]: totals[cid[u]]+=d["sum_kzt"]
    rows = []
    for k,g in df.groupby("cluster_id",sort=True):
        rows.append(dict(cluster_id=int(k),n_nodes=len(g),n_seed=int(g.is_seed.sum()),
            sum_kzt_internal=round(totals[k],2),top_gids="|".join(map(str,ranked(g).head(5).gid)),
            hypothesis=_hypothesis(g.role.value_counts().to_dict(),g,totals[k])))
    return pd.DataFrame(rows,columns=CLUSTER_COLS).sort_values(
        ["sum_kzt_internal","cluster_id"],ascending=[False,True]).reset_index(drop=True)

def top_nodes(df,k=30):
    t = ranked(df).head(k).reset_index(drop=True); t.insert(0,"rank",t.index+1); t["why"]=t.evidence
    return t[TOP_COLS]

def resilience(G,df,maximum=30):
    H,removed,rows = G.copy(),[],[]
    top = list(ranked(df).head(maximum).gid)
    for k in range(len(top)+1):
        if k: H.remove_node(int(top[k-1])); removed.append(str(top[k-1]))
        sizes = sorted((len(c) for c in nx.weakly_connected_components(H)),reverse=True)
        rows.append(dict(n_removed=k,removed=list(removed),n_nodes=len(H),n_edges=H.number_of_edges(),
            components=len(sizes),largest_component=sizes[0] if sizes else 0,isolated=sum(s==1 for s in sizes)))
    return rows

def validate_outputs(df,clusters,tops,expected_gids=None):
    if expected_gids is not None and set(df.gid)!=set(expected_gids): raise ValueError("Node inventory mismatch")
    for frame,cols in [(df[NODE_COLS],NODE_COLS),(clusters,CLUSTER_COLS),(tops,TOP_COLS)]:
        if list(frame.columns)!=cols or frame.isna().any().any(): raise ValueError("Output schema/null violation")
    if df.gid.duplicated().any() or not df.role.isin(ROLES).all(): raise ValueError("Invalid gid/role")
    for col in ["role_score","priority_score"]:
        if not df[col].between(0,1).all(): raise ValueError("Score outside 0..1")
    if not df.evidence.str.len().between(1,199).all() or not df.evidence.str.contains(r"\d").all():
        raise ValueError("Evidence must contain numbers and be shorter than 200 characters")
    for col in ["gid","cluster_id","depth","in_deg","out_deg","n_seed_in","in_tx","out_tx"]:
        if not pd.api.types.is_integer_dtype(df[col]): raise ValueError(f"Invalid integer dtype: {col}")
    for col in ["is_seed","in_cycle","truncated_by_depth"]:
        if not pd.api.types.is_bool_dtype(df[col]): raise ValueError(f"Invalid boolean dtype: {col}")
    for col in ["role_score","priority_score","in_kzt","out_kzt","pagerank","pass_through",
                "hub","authority","betweenness","net_kzt","turnover_days"]:
        if not pd.api.types.is_float_dtype(df[col]): raise ValueError(f"Invalid floating dtype: {col}")
    for frame,cols in [(clusters,["cluster_id","n_nodes","n_seed"]),(tops,["rank","gid"])]:
        for col in cols:
            if not pd.api.types.is_integer_dtype(frame[col]): raise ValueError(f"Invalid integer dtype: {col}")
    if not pd.api.types.is_float_dtype(clusters.sum_kzt_internal): raise ValueError("Invalid cluster amount dtype")
    if not pd.api.types.is_float_dtype(tops.priority_score): raise ValueError("Invalid priority dtype")
    if not np.isfinite(df.select_dtypes(include="number").to_numpy()).all(): raise ValueError("Nonfinite metrics")
    if len(tops)!=min(30,len(df)) or not tops.priority_score.is_monotonic_decreasing: raise ValueError("Invalid ranking")
    if clusters.cluster_id.duplicated().any() or set(clusters.cluster_id)!=set(df.cluster_id): raise ValueError("Invalid clusters")
    if int(clusters.n_nodes.sum())!=len(df): raise ValueError("Invalid cluster sizes")

def write_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8",newline="\n")

def write_outputs(df,clusters,tops,G,out_dir,tx=None):
    validate_outputs(df,clusters,tops,G.nodes); out_dir.mkdir(parents=True,exist_ok=True)
    for frame,name in [(df[NODE_COLS],"nodes_roles"),(clusters,"clusters"),(tops,"top_nodes")]:
        frame.to_csv(out_dir/f"{name}.csv",index=False,encoding="utf-8",float_format="%.17g",lineterminator="\n")
    top_ranks = dict(zip(tops.gid,tops["rank"])); nodes = []
    for r in df.itertuples(index=False):
        nodes.append(dict(id=str(r.gid),role=r.role,cluster=int(r.cluster_id),priority=float(r.priority_score),
            role_score=float(r.role_score),in_kzt=float(r.in_kzt),out_kzt=float(r.out_kzt),
            in_deg=int(r.in_deg),out_deg=int(r.out_deg),in_tx=int(r.in_tx),out_tx=int(r.out_tx),
            depth=int(r.depth),is_seed=bool(r.is_seed),truncated=bool(r.truncated_by_depth),
            in_cycle=bool(r.in_cycle),n_seed_in=int(r.n_seed_in),
            pass_through=None if r.pass_through<0 else float(r.pass_through),
            turnover_days=None if r.turnover_days<0 else float(r.turnover_days),
            evidence=r.evidence,rank=int(top_ranks[r.gid]) if r.gid in top_ranks else None))
    links = [dict(source=str(u),target=str(v),sum_kzt=d["sum_kzt"],n_tx=d["n_tx"],
                  in_cycle=d.get("in_cycle",False)) for u,v,d in G.edges(data=True)]
    scenarios=resilience(G,df)
    cases=build_cases(df,clusters,tx) if tx is not None else []
    if tx is not None: validate_cases(cases,df,tx)
    analysis_id=snapshot_id(df[NODE_COLS],G,tx) if tx is not None else "test-fixture"
    write_json(out_dir/"cases.json",cases)
    write_json(out_dir/"resilience.json",scenarios)
    write_json(out_dir/"graph.json",dict(analysis_id=analysis_id,n_transactions=len(tx) if tx is not None else 0,
        nodes=nodes,links=links,cases=cases,
        cycles=[[str(n) for n in c] for c in G.graph.get("cycles",[])],
        clusters=clusters.to_dict("records"),resilience=scenarios))

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data",type=Path,default=ROOT/"data"); ap.add_argument("--out",type=Path,default=ROOT/"out")
    a=ap.parse_args(); start=time.perf_counter()
    print("[1/5] Проверка исходных данных",flush=True)
    e,n,t=load(a.data); G=build_graph(e,n)
    print("[2/5] Взвешенные центральности, циклы и временные признаки",flush=True)
    df=features(G,n,t); T=thresholds(df)
    print("[3/5] Роли, сообщества, приоритет",flush=True)
    df=priority(cluster(G,assign_roles(df,T))); c,top=cluster_table(df,G),top_nodes(df)
    print("[4/5] Валидация выгрузок и устойчивость сети",flush=True)
    write_outputs(df,c,top,G,a.out,t)
    summary=dict(n_nodes=len(df),n_edges=G.number_of_edges(),n_seed=int(df.is_seed.sum()),n_clusters=len(c),
        roles={r:int((df.role==r).sum()) for r in ROLES},role_weight=ROLE_WEIGHT,thresholds=T,seed=SEED,
        terminals_truncated=int(df.truncated_by_depth.sum()),in_cycle=int(df.in_cycle.sum()),
        n_cycles=len(G.graph["cycles"]),versions=dict(networkx=nx.__version__,pandas=pd.__version__,numpy=np.__version__))
    write_json(a.out/"summary.json",summary)
    print(f"[5/5] Готово за {time.perf_counter()-start:.2f} с. Узлов: {len(df)}, кластеров: {len(c)}",flush=True)
    print(json.dumps(summary["roles"],ensure_ascii=False)); print("Пороги:",json.dumps(T))

if __name__=="__main__": main()
