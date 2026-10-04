# nsanku Machine Translation Benchmark

[![Hugging Face Space](https://img.shields.io/badge/%F0%9F%A4%97%20Leaderboard-HF%20Space-blue)](https://huggingface.co/spaces/ghananlpcommunity/nsanku-mt-benchmark)

Ghanaian language ↔ English machine translation, evaluated on **whole documents** rather
than isolated sentences, **in both directions** (X → English and English → X, scored and reported separately). Companion to the nsanku
[ASR](https://github.com/GhanaNLP/nsanku-asr-benchmark) and
[TTS](https://github.com/GhanaNLP/nsanku-tts-benchmark) benchmarks: this repo is the single
source of truth (`benchmarks/`), and the leaderboard Space (`space/`) reads it.

## Datasets

Results are recorded **per dataset**; a language's headline score is the mean of its per-dataset
scores. Details, file locations and how to add a dataset: [`docs/datasets.md`](docs/datasets.md).

| Dataset | Domain | Source | Pairs |
|---|---|---|---|
| `finance` | Citizens' Budget (Ministry of Finance, 2021–2023) | [mofep.gov.gh](https://mofep.gov.gh/publications/citizens-budget) | 18 documents, 7 languages |

### finance: Citizens' Budget

The budget is published in English and in Ghanaian languages; each translated edition is paired with
the English edition of the same year (`data/documents.json`).

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
4. **Publish**: `benchmarks/{iso}.yaml` + `benchmarks/summary.json` (results per dataset);
   translations in `translations/<model>/<doc>.txt`.

## Directions

| Direction | Source text | Reference |
|---|---|---|
| `to_en` (X → English) | the language edition | the English edition of the same year |
| `from_en` (English → X) | the English edition | the language edition |

Each is scored on its own (`directions.to_en` / `directions.from_en` in `benchmarks/*.yaml`, and side by
side on the leaderboard). The headline score is the **mean of the directions a system has**; a system that
supports one direction only (the Twi adapter) is averaged over that direction and flagged `n_directions: 1`.
BLEU on a low-resource *target* language is harsh, so read English → X through chrF and relative to other systems.

## Systems

| Model | Track | Access | Languages scored | Notes |
|---|---|---|---|---|
| Gemini 3.8 Flash (`GEMINI_MT_MODEL`) | LLM | Gemini API | all 7 | temperature 0, thinking disabled for MT |
| Khaya AI | Hosted API | `translation-api.ghananlp.org/v1/translate` | Twi, Ewe, Ga, Dagbani | both directions |
| Google Translate (free) | Hosted API | keyless `clients5.google.com/translate_a/t` | Twi, Ewe, Ga | see note below |
| NLLB-200 600M (distilled), 1.3B, 3.3B | Open | local GPU | Twi, Ewe | beam 4, bf16 |
| NLLB-Twi Human-Aligned | Open | local GPU, [QLoRA adapter](https://huggingface.co/mclanorjeff/NLLB-Twi-Human-Aligned) on NLLB-600M | Twi | X → English only; model-card recipe (`src_lang="aka_GH"`, 5 beams) |
| MADLAD-400 3B, 10B | Open | local GPU | Twi, Ewe, Dangme, Nzema | `<2en>` / `<2xx>` target tags; no source tag, so coverage is inferred from its target-tag inventory |

A system is only scored on the languages and directions it supports (`data/mt_models.json`); unsupported
ones are listed on the leaderboard, never scored as zero. Open models run on a single GPU
(`HFSeq2SeqMT` in `benchmark/models.py`): sentence-level models, so a paragraph over 600 characters is split at
sentence boundaries (only then), pieces are batched and re-joined, and the GPU code halves its batch on CUDA OOM.

**Google Translate note.** The `translate_a/single` endpoints (what py-googletrans uses) answer automated
clients with a "Sorry…" block page, and the py-googletrans fork hid that by returning the input *unchanged*, which
silently produced untranslated "translations" (some runs were 93–98% untranslated). Google is therefore called through
`clients5.google.com/translate_a/t`, errors raise, and a guard re-tries any unchanged non-trivial output (and waits while a
canary translation shows the endpoint is blocked). MADLAD copies some proper names / table headers through unchanged
(up to ~20%); that is model behaviour, not a harness fault.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # + torch, transformers, sentencepiece, peft for the open models (GPU)
cp .env.example .env            # GEMINI_API_KEY, KHAYA_API_KEY
python3 scripts/fetch_documents.py
python3 run_extract.py          # Gemini, page by page
python3 run_benchmark.py        # translate + score  (or: python3 pipeline.py)
python3 run_benchmark.py --models khaya-translate --docs finance_2022_gaa   # targeted
python3 run_benchmark.py --models gemini-3.8-flash --directions from_en        # one direction
```

## Caveats

- Document-level BLEU on a single long segment is a coarse number, and paragraph order/boundaries
  must match between editions; use it for relative ranking, and read it with chrF and the length ratio.
- The translated editions are human translations of the English edition, but layout differs
  (page counts differ), so pages are never aligned — only whole documents are compared.
- The Citizens' Budget is public and may be in some systems' training data.
