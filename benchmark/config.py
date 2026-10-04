"""Paths, env and model settings shared by every stage."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # .env is optional when the vars are already exported
    pass

DATA = ROOT / "data"
PDFS = DATA / "pdfs"
TEXT = DATA / "text"            # extracted text, one folder per document, one file per page
CACHE = DATA / "cache"          # per-chunk translation cache (resumable)
BENCHMARKS = ROOT / "benchmarks"
TRANSLATIONS = ROOT / "translations"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
KHAYA_API_KEY = os.environ.get("KHAYA_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

GEMINI_EXTRACT_MODEL = os.environ.get("GEMINI_EXTRACT_MODEL", "gemini-3.8-flash")
GEMINI_MT_MODEL = os.environ.get("GEMINI_MT_MODEL", "gemini-3.8-flash")

REPO = "GhanaNLP/nsanku-mt-benchmark"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def documents():
    """All benchmark documents: [{id, year, iso, language, source_pdf, reference_pdf, ...}]."""
    return load_json(DATA / "documents.json")["documents"]


def models():
    return load_json(DATA / "mt_models.json")["models"]
