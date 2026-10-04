# nsanku Machine Translation Benchmark

[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97%20Leaderboard-HF%20Space-blue)](https://huggingface.co/spaces/ghananlpcommunity/nsanku-mt-benchmark)

Ghanaian language → English machine translation, evaluated on **whole documents** rather
than isolated sentences. Companion to the nsanku
[ASR](https://github.com/GhanaNLP/nsanku-asr-benchmark) and
[TTS](https://github.com/GhanaNLP/nsanku-tts-benchmark) benchmarks: this repo is the single
source of truth (`benchmarks/`), and the leaderboard Space (`space/`) reads it.

## Data

The Ministry of Finance's [Citizens' Budget](https://mofep.gov.gh/publications/citizens-budget),
published in English and in Ghanaian languages (2021–2023). Each translated edition is paired with the
English edition of the same year (`data/documents.json`: 18 pairs, 7 languages).

| Language | iso | Years |
|---|---|---|
| Asante Twi | twi_asante | 2021, 2022, 2023 |
| Dagbani | dag | 2021, 2022, 2023 |
| Ewe | ewe | 2021, 2022, 2023 |
| Nzema | nzi | 2021, 2022, 2023 |
| Ga | gaa | 2021, 2022 |
| Dangme | ada | 2022, 2023 |
| Gonja | gjn | 2022, 2023 |

## Pipeline

1. **Extract** (`run_extract.py`): each PDF page is rendered to an image and sent to Gemini on
   its own. The prompt is a strict verbatim-OCR prompt (no translating, correcting, summarising or
   commenting) and asks for a `<<<P>>>` marker before every paragraph/heading/table row. Vision is
   used because several PDFs have broken or empty text layers. Raw page output is cached in
   `data/text/<doc>/pNNN.txt`; an audit flags empty pages, commentary-like output and length
   mismatches against the PDF's own text layer.
2. **Translate** (`run_benchmark.py`): **one paragraph per request** for every system — nothing is
   ever sent as a page or whole document (the free endpoints throttle that, and it keeps systems
   comparable). Paragraphs with no letters (numbers, dot leaders) pass through untouched. Results
   are cached per paragraph, so runs resume.
3. **Score**: paragraph outputs are re-joined in order and scored as **one segment per document**
   with sacreBLEU (BLEU, default 13a) and chrF against the English edition. Per-language score =
   mean over its documents. Ranking uses BLEU.
4. **Publish**: `benchmarks/{iso}.yaml` + `benchmarks/summary.json`; translations in
   `translations/<model>/<doc>.txt`.

## Systems

| Model | Access | Notes |
|---|---|---|
| Gemini 3.8 Flash (latest flash at time of writing; `GEMINI_MT_MODEL`) | Gemini API | temperature 0, thinking disabled for MT |
| Khaya AI | `translation-api.ghananlp.org/v1/translate` | tw, ee, gaa, dag |
| Google Translate (free) | [GhanaNLP py-googletrans fork](https://github.com/michsethowusu/py-googletrans) | ak, ee, gaa only; throttled |

A system is only scored on languages it supports (`data/mt_models.json`).

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # GEMINI_API_KEY, KHAYA_API_KEY
python3 scripts/fetch_documents.py
python3 run_extract.py          # Gemini, page by page
python3 run_benchmark.py        # translate + score  (or: python3 pipeline.py)
python3 run_benchmark.py --models khaya-translate --docs 2022_gaa   # targeted
```

## Caveats

- Document-level BLEU on a single long segment is a coarse number, and paragraph order/boundaries
  must match between editions; use it for relative ranking, and read it with chrF and the length ratio.
- The translated editions are human translations of the English edition, but layout differs
  (page counts differ), so pages are never aligned — only whole documents are compared.
- The Citizens' Budget is public and may be in some systems' training data.
