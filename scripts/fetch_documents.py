"""Download the Citizens' Budget PDFs listed in data/documents.json into data/pdfs/."""
import json
import sys
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent.parent
BASES = ["https://mofep.gov.gh/sites/default/files/basic-page/", "https://mofep.gov.gh/sites/default/files/citizens-budget/"]
(root / "data/pdfs").mkdir(parents=True, exist_ok=True)
for d in json.load(open(root / "data/documents.json"))["documents"]:
    for name in (d["source_pdf"], d["reference_pdf"]):
        f = root / "data/pdfs" / name
        if f.exists():
            continue
        for b in BASES:
            try:
                req = urllib.request.Request(b + name, headers={"User-Agent": "Mozilla/5.0"})
                f.write_bytes(urllib.request.urlopen(req, timeout=120).read())
                print("got", name)
                break
            except Exception:
                continue
        else:
            print("MISSING", name, file=sys.stderr)
