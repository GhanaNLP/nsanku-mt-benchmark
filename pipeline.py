"""Full pipeline: extract (Gemini, page by page) -> translate (per paragraph) -> score -> publish."""
import subprocess
import sys

for cmd in ([sys.executable, "scripts/fetch_documents.py"], [sys.executable, "run_extract.py"],
            [sys.executable, "run_benchmark.py"]):
    subprocess.run(cmd, check=True)
