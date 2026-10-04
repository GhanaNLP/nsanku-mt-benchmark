"""Stage 1: extract paragraph-marked text from every PDF with Gemini (page by page).

  python3 run_extract.py                  # all documents + English references
  python3 run_extract.py --docs finance_2022_gaa   # one document
  python3 run_extract.py --pilot          # first 3 pages of one document, prints output
"""
import argparse
import sys

sys.path.insert(0, ".")
from benchmark import config, extract


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", nargs="*", help="document ids (default: all)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()

    docs = [d for d in config.documents() if not args.docs or d["id"] in args.docs]
    if args.pilot:
        d = docs[0]
        for i in range(3):
            raw = extract._gemini(extract.render_page(config.PDFS / d["source_pdf"], i))
            print(f"--- {d['id']} page {i + 1} ---\n{raw}\n")
        return

    refs_done = set()
    for n, d in enumerate(docs, 1):
        print(f"[{n}/{len(docs)}] {d['id']}", flush=True)
        extract.extract_document(d, args.workers, args.force)
        for page, why in extract.audit(d["id"], config.PDFS / d["source_pdf"]):
            print(f"   ! page {page}: {why}")
        if d["reference_id"] not in refs_done:
            refs_done.add(d["reference_id"])
            print(f"   reference {d['reference_id']}", flush=True)
            extract.extract_reference(d, args.workers, args.force)
            for page, why in extract.audit(d["reference_id"], config.PDFS / d["reference_pdf"]):
                print(f"   ! ref page {page}: {why}")


if __name__ == "__main__":
    main()
