"""Deterministic review cases. Logs preserve separate same-day equal-value transfers."""
import hashlib
import json
import pandas as pd

def snapshot_id(df, G, tx):
    # Includes analytics + all transfer rows: notes cannot silently attach to a new analysis.
    digest=hashlib.sha256(df.sort_values("gid").to_csv(index=False,float_format="%.17g",lineterminator="\n").encode("utf-8"))
    for r in tx.sort_values(["src","dst","date","sum_kzt"]).itertuples(index=False):
        digest.update(f"{r.src}|{r.dst}|{r.date.isoformat()}|{float(r.sum_kzt):.17g}\n".encode())
    for u,v,d in sorted(G.edges(data=True)):
        digest.update(f"{u}|{v}|{d['sum_kzt']:.17g}|{d['n_tx']}\n".encode())
    return digest.hexdigest()[:24]

def transaction_records(tx):
    records=[]
    # Canonical row sequence preserves duplicate transactions instead of deduplicating facts.
    for i,r in enumerate(tx.sort_values(["date","src","dst","sum_kzt"],kind="stable").itertuples(index=False),1):
        records.append(dict(tx_id=f"TX-{i:06d}",date=r.date.isoformat(),src=str(int(r.src)),
                            dst=str(int(r.dst)),sum_kzt=float(r.sum_kzt)))
    return records

def build_cases(df,clusters,tx,max_cases=30):
    logs=transaction_records(tx)
    rows=[]
    for c in clusters.itertuples(index=False):
        g=df[df.cluster_id==c.cluster_id]
        roles={str(k):int(v) for k,v in g.role.value_counts().items()}
        if not (roles.get("coordinator",0) or roles.get("consolidator",0) or (c.n_seed and c.sum_kzt_internal>0)):
            continue
        key=g.sort_values(["priority_score","gid"],ascending=[False,True]).head(5)
        members={str(int(n)) for n in g.gid};keys={str(int(n)) for n in key.gid}
        selected=[r for r in logs if r["src"] in members and r["dst"] in members
                  and (r["src"] in keys or r["dst"] in keys)]
        priority=float(g.priority_score.max())
        identity=hashlib.sha256("|".join(sorted(members)).encode()).hexdigest()[:16]
        rows.append(dict(id="CASE-"+identity,cluster_id=int(c.cluster_id),
            title=f"Проверка сообщества {int(c.cluster_id)}",hypothesis=c.hypothesis,
            severity="high" if roles.get("coordinator",0) or priority>=.8 else "medium" if priority>=.5 else "low",
            priority=priority,n_nodes=len(g),n_seed=int(c.n_seed),turnover_kzt=float(c.sum_kzt_internal),
            roles=roles,log_total=len(selected),logs=selected[:12],
            key_nodes=[dict(gid=str(int(n.gid)),role=n.role,priority=float(n.priority_score),evidence=n.evidence)
                       for n in key.itertuples(index=False)],
            recommended_action="Проверить первичные данные и связи. При подтверждении гипотезы передать ответственному аналитику."))
    return sorted(rows,key=lambda c:(-c["priority"],-c["turnover_kzt"],c["id"]))[:max_cases]

def validate_cases(cases,df,tx):
    ids={str(int(g)) for g in df.gid};known={r["tx_id"]:r for r in transaction_records(tx)}
    if len({c["id"] for c in cases})!=len(cases): raise ValueError("Duplicate case IDs")
    for c in cases:
        if c["severity"] not in {"high","medium","low"} or not 0<=c["priority"]<=1: raise ValueError("Invalid case priority")
        members={str(int(g)) for g in df.loc[df.cluster_id==c["cluster_id"],"gid"]}
        if not c["key_nodes"] or any(n["gid"] not in members for n in c["key_nodes"]): raise ValueError("Unknown case node")
        if c["log_total"]<len(c["logs"]): raise ValueError("Invalid log count")
        for r in c["logs"]:
            if r!=known.get(r["tx_id"]) or r["src"] not in members or r["dst"] not in members:
                raise ValueError("Case log does not match source transactions")
