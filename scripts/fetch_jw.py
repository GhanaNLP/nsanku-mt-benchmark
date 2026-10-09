"""Download Watchtower Study Edition PDFs for Ghanaian languages and English into data/pdfs/.

Issues are discovered through the JW PubMedia API rather than hardcoded, then for each
language the newest issues are taken up to CAP_PER_LANG (newest first). A language that is
only published for some issues simply gets fewer documents. English reference editions are
downloaded for every issue any language selected.

The selection is written to data/jw_selected.json so the document list can be updated
without re-querying the API.

  python3 scripts/fetch_jw.py                 # (re)discover issues, then download the PDFs
  python3 scripts/fetch_jw.py --plan          # only print/write the selection, download nothing
  python3 scripts/fetch_jw.py --from-manifest # download exactly the issues already in data/jw_selected.json
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
SELECTION = ROOT / "data" / "jw_selected.json"

API = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
PUB = "w"  # Watchtower (Study)
CAP_PER_LANG = 5
LOOKBACK_MONTHS = 36

# iso -> (JW language code, display name); the code matches w_<CODE>_<issue>.pdf
LANGUAGES = {
    "twi_asante": ("TW", "Asante Twi"),
    "fante": ("FA", "Fante"),
    "ewe": ("EW", "Ewe"),
    "gaa": ("GA", "Ga"),
    "ada": ("DG", "Dangme"),
    "nzi": ("NZ", "Nzema"),
    "dga": ("DGA", "Dagaare"),
    "gur": ("FF", "Frafra"),
    "sfw": ("SHW", "Sehwi"),
    "aha": ("AHN", "Ahanta"),
}
REFERENCE_ISO, REFERENCE_CODE = "eng", "E"


def _candidate_issues():
    """Recent issue codes (YYYYMM), newest first."""
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(LOOKBACK_MONTHS):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def pdf_url(lang_code, issue):
    """Direct PDF URL for one language/issue, or None if not published."""
    q = urllib.parse.urlencode({
        "output": "json", "fileformat": "PDF", "pub": PUB,
        "issue": issue, "langwritten": lang_code, "txtCMSLang": lang_code,
    })
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception:
        return None
    pdfs = (d.get("files", {}).get(lang_code, {}) or {}).get("PDF") or []
    return pdfs[0]["file"]["url"] if pdfs else None


def select():
    """For each language, the newest up to CAP_PER_LANG issues that are actually published."""
    issues = _candidate_issues()
    picked = {}  # iso -> [issue, ...] newest first
    for iso, (code, name) in LANGUAGES.items():
        got = []
        for issue in issues:
            if len(got) >= CAP_PER_LANG:
                break
            if pdf_url(code, issue):
                got.append(issue)
            time.sleep(0.15)
        picked[iso] = got
        print(f"{name:14s} ({iso:11s}) {len(got)} issue(s): {', '.join(got) or '-'}")
    ref_issues = sorted({i for v in picked.values() for i in v}, reverse=True)
    return picked, ref_issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="write/inspect selection, download nothing")
    ap.add_argument("--from-manifest", action="store_true",
                    help="download the issues already listed in data/jw_selected.json (no re-discovery)")
    a = ap.parse_args()

    if a.from_manifest:
        manifest = json.loads(SELECTION.read_text(encoding="utf-8"))
        picked, ref_issues = manifest["languages"], manifest["reference_issues"]
        n = sum(len(v) for v in picked.values())
        print(f"using manifest: {n} Ghanaian documents across {len(picked)} languages; "
              f"{len(ref_issues)} English reference issue(s)")
    else:
        picked, ref_issues = select()
        manifest = {"generated": date.today().isoformat(), "cap_per_lang": CAP_PER_LANG,
                    "languages": picked, "reference_issues": ref_issues,
                    "issues": sorted({i for v in picked.values() for i in v}, reverse=True)}
        SELECTION.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        n = sum(len(v) for v in picked.values())
        print(f"\nselected {n} Ghanaian documents across {len(picked)} languages; "
              f"{len(ref_issues)} English reference issue(s)")
        print(f"wrote {SELECTION.relative_to(ROOT)}")

    if a.plan:
        return

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for iso, (code, name) in LANGUAGES.items():
        for issue in picked[iso]:
            jobs[f"jw_{issue}_{iso}.pdf"] = ("src", code, issue)
    for issue in ref_issues:
        jobs[f"jw_{issue}_{REFERENCE_ISO}.pdf"] = ("ref", REFERENCE_CODE, issue)

    for fname, (kind, code, issue) in sorted(jobs.items()):
        dest = PDF_DIR / fname
        if dest.exists() and dest.stat().st_size > 500_000:
            print(f"Already have {fname} ({dest.stat().st_size / 1024 / 1024:.2f} MB)")
            continue
        url = pdf_url(code, issue)
        if not url:
            print(f"!! no URL for {fname}, skipping")
            continue
        print(f"Downloading {fname} ...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
        dest.write_bytes(data)
        print(f"Saved {fname} ({len(data) / 1024 / 1024:.2f} MB)")
        time.sleep(0.15)


if __name__ == "__main__":
    main()
