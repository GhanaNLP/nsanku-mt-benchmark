"""Download Watchtower Study Edition (w202601) PDFs for Ghanaian languages and English into data/pdfs/."""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"

# Issue w 202601 PDF URLs from JW PubMedia API
PDF_URLS = {
    "jw_202601_eng.pdf": "https://cfp2.jw-cdn.org/a/21b28cc/1/o/w_E_202601.pdf",
    "jw_202601_twi_asante.pdf": "https://cfp2.jw-cdn.org/a/f6abdb/1/o/w_TW_202601.pdf",
    "jw_202601_fante.pdf": "https://cfp2.jw-cdn.org/a/9df15d/1/o/w_FA_202601.pdf",
    "jw_202601_ewe.pdf": "https://cfp2.jw-cdn.org/a/488a84d/1/o/w_EW_202601.pdf",
    "jw_202601_gaa.pdf": "https://cfp2.jw-cdn.org/a/b25283/1/o/w_GA_202601.pdf",
    "jw_202601_ada.pdf": "https://cfp2.jw-cdn.org/a/1199a79/1/o/w_DG_202601.pdf",
    "jw_202601_nzi.pdf": "https://cfp2.jw-cdn.org/a/3ffe48e/1/o/w_NZ_202601.pdf",
    "jw_202601_dga.pdf": "https://cfp2.jw-cdn.org/a/5a163a0/1/o/w_DGA_202601.pdf",
    "jw_202601_gur.pdf": "https://cfp2.jw-cdn.org/a/58c2b72/2/o/w_FF_202601.pdf",
    "jw_202601_sfw.pdf": "https://cfp2.jw-cdn.org/a/ba14af/2/o/w_SHW_202601.pdf",
    "jw_202601_aha.pdf": "https://cfp2.jw-cdn.org/a/64bc0b1/1/o/w_AHN_202601.pdf",
}


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in PDF_URLS.items():
        dest = PDF_DIR / fname
        if dest.exists() and dest.stat().st_size > 500000:
            print(f"Already downloaded {fname} ({dest.stat().st_size / 1024 / 1024:.2f} MB)")
            continue
        print(f"Downloading {fname} ...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
        dest.write_bytes(data)
        print(f"Saved {fname} ({len(data) / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
