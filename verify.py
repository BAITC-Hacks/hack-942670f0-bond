"""Run regression tests and compare every delivery artifact from two independent builds."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ARTIFACTS=["nodes_roles.csv","clusters.csv","top_nodes.csv","graph.json","summary.json","cases.json","resilience.json","vertex.html"]

def run(*args):
    subprocess.run([sys.executable,"-X","utf8",*map(str,args)],cwd=ROOT,check=True)

def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    run("-m","unittest","discover","-s","tests","-v")
    with tempfile.TemporaryDirectory(prefix="vertex-verify-") as directory:
        folders=[Path(directory)/str(i) for i in range(2)]
        for out in folders:
            run(ROOT/"backend/solution.py","--data",ROOT/"data","--out",out)
            run(ROOT/"backend/build_viz.py","--out",out)
        for name in ARTIFACTS:
            hashes=[hashlib.sha256((out/name).read_bytes()).hexdigest() for out in folders]
            if hashes[0]!=hashes[1]:raise AssertionError("Nondeterministic artifact: "+name)
            print("PASS SHA256:",name,flush=True)
        for out in folders:
            if sorted(p.name for p in out.glob("*.csv"))!=sorted(ARTIFACTS[:3]):raise AssertionError("Unexpected CSV inventory")
            graph=json.loads((out/"graph.json").read_text(encoding="utf-8"))
            if len(graph["cases"])!=30:raise AssertionError("Expected 30 cases for supplied dataset")
    print("PASS: regression suite and all 8 artifacts reproducible. Existing out/ unchanged.")
if __name__=="__main__":main()
