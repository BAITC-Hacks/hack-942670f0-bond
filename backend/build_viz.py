"""Build a standalone UTF-8 dashboard from validated CSV/JSON artifacts."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def build(out, vendor):
    data = json.loads((out/"graph.json").read_text(encoding="utf-8"))
    summary = json.loads((out/"summary.json").read_text(encoding="utf-8"))
    if data.get("cases",[]) != json.loads((out/"cases.json").read_text(encoding="utf-8")):
        raise ValueError("Stale case snapshot")
    if data["resilience"] != json.loads((out/"resilience.json").read_text(encoding="utf-8")):
        raise ValueError("Stale resilience snapshot")
    def rows(name):
        with (out/name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    nodes, tops, clusters = rows("nodes_roles.csv"), rows("top_nodes.csv"), rows("clusters.csv")
    if {r["gid"] for r in nodes} != {n["id"] for n in data["nodes"]}:
        raise ValueError("CSV/JSON node inventory mismatch")
    by_id = {n["id"]: n for n in data["nodes"]}
    if len(nodes) != len(by_id) or len(nodes) != summary["n_nodes"]:
        raise ValueError("Duplicate nodes or stale summary")
    for r in nodes:
        n = by_id[r["gid"]]
        if (r["role"] != n["role"] or r["evidence"] != n["evidence"]
            or abs(float(r["priority_score"])-n["priority"])>1e-12):
            raise ValueError("Stale CSV/JSON node metrics")
        n["rank"] = None
    for r in tops:
        by_id[r["gid"]]["rank"] = int(r["rank"])
    data["clusters"] = [dict(cluster_id=int(r["cluster_id"]),n_nodes=int(r["n_nodes"]),
        n_seed=int(r["n_seed"]),sum_kzt_internal=float(r["sum_kzt_internal"]),
        top_gids=r["top_gids"],hypothesis=r["hypothesis"]) for r in clusters]
    for link in data["links"]:
        if link["source"] not in by_id or link["target"] not in by_id:
            raise ValueError("Dangling graph edge")
    template = (ROOT/"viz/dashboard.html").read_text(encoding="utf-8")
    def safe_json(x):
        return json.dumps(x,ensure_ascii=False,allow_nan=False).replace("<","\\u003c")
    html = (template.replace("/*__LIB__*/",(vendor/"force-graph.min.js").read_text(encoding="utf-8").replace("</script","<\\/script"))
        .replace("/*__DATA__*/",safe_json(data)).replace("/*__SUMMARY__*/",safe_json(summary))
        .replace("/*__APP__*/",(ROOT/"viz/dashboard.js").read_text(encoding="utf-8"))
        .replace("/*__CASE_STATE__*/",(ROOT/"viz/case-state.js").read_text(encoding="utf-8"))
        .replace("/*__TEAM_APP__*/",(ROOT/"viz/team-workspace.js").read_text(encoding="utf-8")))
    (out/"vertex.html").write_text(html.rstrip()+"\n",encoding="utf-8",newline="\n")
    return out/"vertex.html"

def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=ROOT/"out")
    ap.add_argument("--vendor",type=Path,default=ROOT/"viz/vendor")
    a=ap.parse_args()
    print(f"Dashboard: {build(a.out,a.vendor)}",flush=True)

if __name__=="__main__": main()
