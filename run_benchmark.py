"""Stage 2: paragraph-level MT + document-level BLEU.

  python3 run_benchmark.py --models khaya-translate --docs finance_2022_gaa
  python3 run_benchmark.py                 # everything
  python3 run_benchmark.py --assemble      # only rebuild benchmarks/ from stored scores
"""
import argparse
import sys

sys.path.insert(0, ".")
from benchmark import evaluate

ap = argparse.ArgumentParser()
ap.add_argument("--models", nargs="*")
ap.add_argument("--docs", nargs="*")
ap.add_argument("--langs", nargs="*")
ap.add_argument("--assemble", action="store_true")
a = ap.parse_args()
evaluate.assemble() if a.assemble else evaluate.run(a.docs, a.models, a.langs)
