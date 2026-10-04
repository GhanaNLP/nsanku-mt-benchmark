"""Page-by-page text extraction with Gemini (vision), paragraph-marked.

Each PDF page is rendered to an image and sent to Gemini on its own, so layout,
reading order and scanned / badly-encoded PDFs (broken text layers) are handled the
same way. The prompt forbids translating, summarising or adding anything; output is
split into paragraphs by an explicit marker line so that MT can run per paragraph.

Cache: data/text/<doc_id>/p<NNN>.txt  (raw model output, one file per page)
"""
import base64
import re
import time
from concurrent.futures import ThreadPoolExecutor

import fitz  # PyMuPDF
import requests

from . import config

MARKER = "<<<P>>>"

PROMPT = f"""You are a verbatim OCR / text-extraction engine. Extract the text of this single document page exactly as printed.

Rules:
- Output ONLY the text that is visibly printed on the page. Never add, translate, correct, summarise, explain or comment. Keep the original language, spelling, diacritics, special characters (ɛ ɔ ŋ ɖ ɣ ƒ etc.), numbers and punctuation exactly.
- Follow the natural reading order (respect columns, sidebars and boxes: finish one before the next).
- Put the marker line {MARKER} on its own line before EVERY paragraph, heading, list item, caption or text box. Text of one paragraph goes on the lines after its marker; join lines that are only wrapped (and de-hyphenate words split across lines).
- Tables: one marker per table row, cells separated by " | ".
- Charts / images / logos: include only text that is printed inside them; do not describe them.
- Include headers, footers and page numbers only if printed.
- If the page has no text, output nothing at all.
- No markdown, no code fences, no preamble, no closing remarks."""

_COMMENTARY = re.compile(r"^(here is|here's|sure|okay|the (page|text)|this page|i (cannot|can't))", re.I)


def render_page(pdf_path, index, dpi=200):
    with fitz.open(pdf_path) as doc:
        pix = doc[index].get_pixmap(dpi=dpi)
        return pix.tobytes("png")


# Tried in order when the primary model returns nothing (RECITATION / PROHIBITED_CONTENT
# false positives or a transient empty reply). Same prompt, same task, different model.
FALLBACK_MODELS = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]


def _gemini(png: bytes, model=None, retries=6):
    model = model or config.GEMINI_EXTRACT_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 16384},
    }
    for attempt in range(retries):
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=180)
            if r.status_code == 200:
                cand = (r.json().get("candidates") or [{}])[0]
                parts = cand.get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if cand.get("finishReason") not in (None, "STOP", "MAX_TOKENS") and not text.strip():
                    return ""  # blocked / empty page
                return text
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
        except requests.RequestException:
            time.sleep(min(60, 2 ** attempt * 2))
    raise RuntimeError("Gemini extraction failed after retries")


def clean(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n|\n```$", "", raw)  # stray fences
    return raw.strip()


def parse_paragraphs(raw: str):
    """Split page output on MARKER lines -> list of single-line paragraphs."""
    out = []
    for block in clean(raw).split(MARKER):
        para = " ".join(block.split())
        if para:
            out.append(para)
    return out


def extract_document(doc, workers=6, force=False):
    """Extract every page of doc['source_pdf'] (and cache). Returns list of paragraphs."""
    return _extract_pdf(doc["id"], config.PDFS / doc["source_pdf"], workers, force)


def extract_reference(doc, workers=6, force=False):
    # English edition: its PDF text layer is clean, so it is the last-resort fallback
    return _extract_pdf(doc["reference_id"], config.PDFS / doc["reference_pdf"], workers, force,
                        native_fallback=True)


def native_page_text(pdf_path, index):
    """The PDF's own text layer as marked paragraphs (reading-order blocks)."""
    with fitz.open(pdf_path) as doc:
        blocks = doc[index].get_text("blocks", sort=True)
    return "\n".join(f"{MARKER}\n{' '.join(b[4].split())}" for b in blocks if b[4].strip())


def _extract_pdf(doc_id, pdf_path, workers, force, native_fallback=False):
    out_dir = config.TEXT / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as d:
        n_pages = len(d)

    def do(i):
        f = out_dir / f"p{i + 1:03d}.txt"
        if f.exists() and not force:
            return
        png = render_page(pdf_path, i)
        raw = ""
        for model in [None, None] + FALLBACK_MODELS:  # empty reply: retry, then other models
            raw = _gemini(png, model)
            if clean(raw):
                break
        if not clean(raw) and native_fallback:  # every model blocked (e.g. RECITATION)
            raw = native_page_text(pdf_path, i)
        f.write_text(clean(raw), encoding="utf-8")

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(do, range(n_pages)))
    return load_paragraphs(doc_id)


def load_paragraphs(doc_id):
    paras = []
    for f in sorted((config.TEXT / doc_id).glob("p*.txt")):
        paras.extend(parse_paragraphs(f.read_text(encoding="utf-8")))
    return paras


def audit(doc_id, pdf_path):
    """Cheap hallucination guard: flag pages whose output looks like commentary
    or whose length is far from the PDF's own text layer (when it has a usable one)."""
    flags = []
    with fitz.open(pdf_path) as d:
        for i, page in enumerate(d):
            f = config.TEXT / doc_id / f"p{i + 1:03d}.txt"
            if not f.exists():
                flags.append((i + 1, "missing"))
                continue
            txt = clean(f.read_text(encoding="utf-8"))
            if _COMMENTARY.match(txt):
                flags.append((i + 1, "commentary?"))
            native = len(page.get_text().strip())
            got = len(txt.replace(MARKER, "").strip())
            if native > 300 and not (0.5 <= got / native <= 1.6):
                flags.append((i + 1, f"length ratio {got / native:.2f}"))
    return flags
