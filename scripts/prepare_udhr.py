"""Fetch official UDHR XMLs and convert them into data/text/udhr_<iso>/p001.txt.

Source: UN OHCHR / Unicode Consortium UDHR in Unicode project.
Each document is formatted with the <<<P>>> paragraph marker for batch translation,
evaluated at document/corpus level.
"""
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://raw.githubusercontent.com/unicorpus/udhr-in-unicode/master/data/xml/"
XML_CACHE = ROOT / "data" / "udhr_xml"
TEXT_DIR = ROOT / "data" / "text"
MARKER = "<<<P>>>"

DOCUMENTS = {
    "udhr_eng": ("udhr_eng.xml", "English"),
    "udhr_twi_asante": ("udhr_aka_asante.xml", "Asante Twi"),
    "udhr_twi_akuapem": ("udhr_aka_akuapem.xml", "Akuapem Twi"),
    "udhr_fante": ("udhr_aka_fante.xml", "Fante"),
    "udhr_dag": ("udhr_dag.xml", "Dagbani"),
    "udhr_ada": ("udhr_ada.xml", "Dangme"),
    "udhr_ewe": ("udhr_ewe.xml", "Ewe"),
    "udhr_gaa": ("udhr_gaa.xml", "Ga"),
    "udhr_nzi": ("udhr_nzi.xml", "Nzema"),
    "udhr_gjn": ("udhr_gjn.xml", "Gonja"),
    "udhr_dga": ("udhr_dga.xml", "Dagaare"),
    "udhr_xsm": ("udhr_xsm.xml", "Kasem"),
}


def get_text(node):
    return " ".join("".join(node.itertext()).split())


def extract_paragraphs(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    paras = []
    # Document title
    title = root.find("title")
    if title is not None:
        txt = get_text(title)
        if txt:
            paras.append(txt)

    # Preamble
    preamble = root.find("preamble")
    if preamble is not None:
        pt = preamble.find("title")
        if pt is not None:
            txt = get_text(pt)
            if txt:
                paras.append(txt)
        for child in preamble:
            if child.tag == "para":
                txt = get_text(child)
                if txt:
                    paras.append(txt)

    # Articles 1..30
    for art in root.findall("article"):
        at = art.find("title")
        if at is not None:
            txt = get_text(at)
            if txt:
                paras.append(txt)
        for child in art:
            if child.tag == "para":
                txt = get_text(child)
                if txt:
                    paras.append(txt)
            elif child.tag == "orderedlist":
                for item in child.findall("listitem"):
                    txt = get_text(item)
                    if txt:
                        paras.append(txt)
    return paras


def main():
    XML_CACHE.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    for doc_id, (xml_name, lang_name) in DOCUMENTS.items():
        cache_path = XML_CACHE / xml_name
        if not cache_path.exists():
            url = BASE_URL + xml_name
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            cache_path.write_bytes(urllib.request.urlopen(req, timeout=60).read())

        xml_bytes = cache_path.read_bytes()
        paras = extract_paragraphs(xml_bytes)

        doc_dir = TEXT_DIR / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        out_file = doc_dir / "p001.txt"

        lines = []
        for p in paras:
            lines.append(MARKER)
            lines.append(p)
        out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        word_count = sum(len(p.split()) for p in paras)
        print(f"Prepared {doc_id:18} ({lang_name:12}): {len(paras):2d} paras, {word_count:5d} words -> {out_file.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
