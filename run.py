"""Cross-platform runner with visible progress, optional local dashboard server."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--serve",action="store_true")
    ap.add_argument("--skip-build",action="store_true")
    a=ap.parse_args()
    if not a.skip_build:
        for script in ["solution.py","build_viz.py"]:
            subprocess.run([sys.executable,"-X","utf8",str(ROOT/"backend"/script)],cwd=ROOT,check=True)
    if a.serve:
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"backend/server.py")],cwd=ROOT,check=True)
    else: print("Open out/vertex.html, or run: python run.py --serve --skip-build")
if __name__=="__main__": main()
