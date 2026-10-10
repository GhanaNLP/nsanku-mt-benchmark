"""Build the `folktales` dataset from R. S. Rattray, *Akan-Ashanti Folk-Tales* (Oxford, 1930).

The book prints each of its 75 tales twice, in parallel: the Asante Twi original on the even
(left) PDF pages and Rattray's English translation on the facing odd (right) pages, PDF pp. 26-323.
Tales start and end mid-page and run over several spreads, so the text is NOT paired page by page:
each language is read as one continuous stream, re-joined across page breaks, and cut into tales
at their title headings. Tale i in Twi is then paired with tale i in English.

  python3 scripts/extract_folktales.py          # OCR (cached) + build
  python3 scripts/extract_folktales.py --build  # rebuild from the OCR cache only

Stage 1  Gemini vision OCR of every text page with a book-specific prompt that tags each block as
         paragraph / tale title / illustration caption / page furniture / continued-from-previous-page.
         Cache: data/cache/folktales_tagged/p<NNN>.txt
Stage 2  Drop captions and page furniture, re-join paragraphs split by page breaks or pictures,
         split each stream at the titles (the opening formula "Ye' nse se, nse se o" / "We do not
         really mean ..." goes with the tale it introduces), check the start pages against the
         book's table of contents, and write
           data/text/folktale_<NN>_twi_asante/p001.txt   (Twi tale = source document)
           data/text/folktale_<NN>_eng/p001.txt          (English tale = its reference)
         plus the 75 entries in data/documents.json.

Source: https://archive.org/details/akanashantifolkt0000ratt  -> data/pdfs/akan_folktales.pdf
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from benchmark import config, extract

PDF_URL = "https://archive.org/download/akanashantifolkt0000ratt/akanashantifolkt0000ratt.pdf"
PDF_PATH = config.PDFS / "akan_folktales.pdf"
CACHE = config.DATA / "cache" / "folktales_tagged"
FIRST, LAST = 26, 323          # 1-indexed PDF pages holding the tales
N_TALES = 75
# Full-page plates and their blank backs (no tale text)
PLATES = {39, 40, 51, 52, 83, 84, 151, 152, 155, 156, 171, 172,
          205, 206, 247, 248, 265, 266, 293, 294, 301, 302, 311, 312}

P, TITLE, CAPTION, FURN, CONT = "<<<P>>>", "<<<TITLE>>>", "<<<CAPTION>>>", "<<<FURNITURE>>>", "<<<CONT>>>"
TAGS = (P, TITLE, CAPTION, FURN, CONT)

PROMPT = extract.PROMPT + f"""

This page is from a 1930 book of Ashanti folk-tales (Asante Twi on left-hand pages, English on
right-hand pages), with small drawings set into the text. Use these markers instead of {P} where they apply:
- {TITLE} before the title heading of a tale (printed in capitals). One marker per printed heading.
- {CAPTION} before every caption of a drawing/illustration (short text printed under or beside a picture).
- {FURN} before page numbers, running headers and printer's marks (e.g. "823148", a lone capital letter at the foot of the page).
- {CONT} instead of {P} before the first text on the page if it continues a paragraph or sentence from the previous page (it is not the start of a new, indented paragraph).
Everything else (story paragraphs, songs, verses, the opening formula "Ye' nse se ..." / "We do not really mean ...", closing formulas) uses {P}."""

# Anchored: the closing formula "M'anansesem ..." also contains "nse se"
OPENING = {"twi": re.compile(r"^\W*Ye\W*\s*nse\s*se", re.I), "eng": re.compile(r"^\W*We do not really mean", re.I)}
END_PUNCT = tuple('.!?:;"”’\')]')
OLD_ORTHOGRAPHY = str.maketrans("ɛɔƐƆ", "eoEO")


def printed(page):
    """Printed page number of a PDF page: front matter is 24 pages and the plates are unnumbered."""
    return page - 24 - sum(q < page for q in PLATES)


def pages():
    return [p for p in range(FIRST, LAST + 1) if p not in PLATES]


def lang_of(page):
    return "twi" if page % 2 == 0 else "eng"


# ---------------------------------------------------------------- stage 1: OCR
def ocr_page(page, force=False):
    f = CACHE / f"p{page:03d}.txt"
    if f.exists() and f.stat().st_size > 10 and not force:
        return page, "cached"
    png = extract.render_page(PDF_PATH, page - 1, dpi=200)
    raw = ""
    for model in [None, None] + extract.FALLBACK_MODELS:  # empty reply: retry, then other models
        raw = extract._gemini(png, model, prompt=PROMPT)
        if extract.clean(raw):
            break
    f.write_text(extract.clean(raw), encoding="utf-8")
    return page, f"ok {len(raw)} chars"


def ocr(workers=12, force=False):
    if not PDF_PATH.exists():
        sys.exit(f"missing {PDF_PATH}; download it from {PDF_URL}")
    CACHE.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for n, (page, status) in enumerate(ex.map(lambda p: ocr_page(p, force), pages()), 1):
            if status != "cached":
                print(f"[{n}/{len(pages())}] p{page:03d} {status}", flush=True)
    print(f"OCR done in {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- stage 2: build
def blocks(page):
    """[(tag, text)] for one cached page."""
    raw = (CACHE / f"p{page:03d}.txt").read_text(encoding="utf-8")
    if lang_of(page) == "twi":  # the book prints plain e / o; the OCR sometimes "modernises" them
        raw = raw.translate(OLD_ORTHOGRAPHY)
    out, tag = [], P
    for part in re.split("(" + "|".join(re.escape(t) for t in TAGS) + ")", raw):
        if part in TAGS:
            tag = part
            continue
        # Several paragraphs / verse lines sometimes share one marker: a line that ends a sentence
        # ends a paragraph, any other line break is joined.
        seg = ""
        for line in (" ".join(l.split()) for l in part.splitlines()):
            if line:
                seg = f"{seg} {line}" if seg else line
                if seg.endswith(END_PUNCT):
                    out.append((tag, seg))
                    tag, seg = (P if tag in (CONT, P) else tag), ""
        if seg:
            out.append((tag, seg))
    return out


def _join(a, b):
    return a + b if a.endswith("-") else f"{a} {b}"


def stream(lang):
    """One language as [(kind, text, page)], kind in {title, para}; captions/furniture dropped and
    paragraphs split by a page break or a picture re-joined."""
    out = []
    for page in (p for p in pages() if lang_of(p) == lang):
        for tag, text in blocks(page):
            if tag in (CAPTION, FURN) or re.fullmatch(r"[\d\s|]+[A-Z]?|[A-Z]|[ivxlc]+", text):
                continue
            prev = out[-1] if out else None
            if tag == TITLE:
                if prev and prev[0] == "title":  # multi-line / multi-heading title
                    out[-1] = ("title", f"{prev[1]} / {text}", prev[2])
                else:
                    out.append(("title", text, page))
            elif prev and prev[0] == "para" and (
                    tag == CONT or (not prev[1].endswith(END_PUNCT) and text[:1].islower())):
                out[-1] = ("para", _join(prev[1], text), prev[2])
            else:
                out.append(("para", text, page))
    return out


def split_tales(lang):
    s = stream(lang)
    starts = [i for i, (k, _, _) in enumerate(s) if k == "title"]
    tales = []
    for n, i in enumerate(starts):
        j = starts[n + 1] if n + 1 < len(starts) else len(s)
        if n + 1 < len(starts) and OPENING[lang].search(s[j - 1][1]) and len(s[j - 1][1]) < 160:
            j -= 1  # the next tale's opening formula
        begin = i - 1 if i and OPENING[lang].search(s[i - 1][1]) and len(s[i - 1][1]) < 160 else i
        tales.append({"title": s[i][1], "page": s[i][2],
                      "paragraphs": [t for _, t, _ in s[begin:j]]})
    lead = s[:starts[0] - (1 if starts[0] and OPENING[lang].search(s[starts[0] - 1][1]) else 0)] if starts else s
    if lead:
        print(f"  ! {lang}: {len(lead)} paragraph(s) before the first title ignored: {lead[0][1][:60]!r}")
    return tales


def toc():
    """{tale number: (title, printed start page or None)} from the book's contents (PDF pp. 21-23)."""
    with extract.fitz.open(PDF_PATH) as d:
        text = "\n".join(d[i].get_text() for i in range(20, 23))
    text = re.sub(r"\s*\n\s*", " ", text)
    out = {}
    for m in re.finditer(r"(?<![\d.])(\d{1,2})\. (.+?)(?=\s(?:\d{1,2})\. [A-Z“\"]|\s*LIST OF PLATES|$)", text):
        n, body = int(m.group(1)), m.group(2)
        pg = re.search(r"[.\s]*(\d{2,3})\s*(?:[xvi]+\s*)?$", body)
        title = re.sub(r"[\s.•]+\d*\s*$", "", body).strip()
        title = re.sub(r"\s*(\.\s*){2,}.*$", "", title).strip()
        out.setdefault(n, (title, int(pg.group(1)) if pg else None))
    # entry 22 is a three-line braced heading and 57 shares its page number with 56
    out[22] = ("Men commit evil by night; children play by moonlight; "
               "matters in dispute are heard in the daytime", None)
    out[57] = ("Child-Kwasi-Gyinamoa", 220)
    return out


def build():
    twi, eng = split_tales("twi"), split_tales("eng")
    print(f"tales found: twi {len(twi)}, eng {len(eng)} (expected {N_TALES})")
    contents = toc()
    problems = []
    for n, (t, e) in enumerate(zip(twi, eng), 1):
        toc_pg = contents.get(n, (None, None))[1]
        twi_pg, eng_pg = printed(t["page"]), printed(e["page"])
        ratio = sum(map(len, e["paragraphs"])) / max(1, sum(map(len, t["paragraphs"])))
        flag = []
        if not t["page"] < e["page"] <= t["page"] + 7:  # English runs longer, so it can drift a spread or two
            flag.append("English start too far from Twi start")
        if toc_pg and toc_pg not in (twi_pg, twi_pg - 1):
            flag.append(f"TOC says p.{toc_pg}")
        if not 0.9 <= ratio <= 2.6:
            flag.append(f"len ratio {ratio:.2f}")
        line = (f"{n:2d} p.{twi_pg:3d}/{eng_pg:3d} {len(t['paragraphs']):3d}/{len(e['paragraphs']):3d} para "
                f"x{ratio:.2f}  {t['title'][:38]:38s} | {e['title'][:45]}")
        print(("!! " if flag else "   ") + line + (f"   <-- {', '.join(flag)}" if flag else ""))
        if flag:
            problems.append(n)
    if len(twi) != N_TALES or len(eng) != N_TALES:
        sys.exit("tale count mismatch: fix the OCR tags (see list above) before writing anything")
    if problems:
        print(f"!! check tales {problems}")

    for n, (t, e) in enumerate(zip(twi, eng), 1):
        for doc_id, tale in ((f"folktale_{n:02d}_twi_asante", t), (f"folktale_{n:02d}_eng", e)):
            out = config.TEXT / doc_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "p001.txt").write_text(
                "".join(f"{extract.MARKER}\n{p}\n" for p in tale["paragraphs"]), encoding="utf-8")

    path = config.DATA / "documents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["documents"] = [d for d in data["documents"] if d["dataset"] != "folktales"] + [
        {"id": f"folktale_{n:02d}_twi_asante", "year": 1930, "iso": "twi_asante", "language": "Asante Twi",
         "reference_id": f"folktale_{n:02d}_eng", "dataset": "folktales",
         "title": contents.get(n, (e["title"].title(),))[0] or e["title"].title()}
        for n, e in enumerate(eng, 1)]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {N_TALES} tale pairs to data/text/ and data/documents.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="skip OCR, rebuild from the cache")
    ap.add_argument("--force", action="store_true", help="re-OCR every page")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    if not args.build:
        ocr(args.workers, args.force)
    build()


if __name__ == "__main__":
    main()
