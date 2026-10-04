# Datasets

Results are recorded **per dataset** (`per_dataset` in each `benchmarks/<iso>.yaml`). Within a direction, a
language's score is the mean of its per-dataset scores (directions are never averaged), so adding a dataset never changes the numbers of the
existing ones. Registry: [`data/datasets.json`](../data/datasets.json); every document in
[`data/documents.json`](../data/documents.json) carries a `dataset` id.

## finance: Citizens' Budget

| | |
|---|---|
| Publisher | Ministry of Finance, Ghana |
| Source | <https://mofep.gov.gh/publications/citizens-budget> |
| Domain | Finance / public administration (plain-language explainer of the national budget) |
| Years | 2021, 2022, 2023 |
| Pairs | 18 document pairs: a Ghanaian-language edition + the English edition of the same year |
| Direction | Ghanaian language → English |

The language editions are human translations of the English edition. Layout differs between
editions (page counts differ), so pages are never aligned; whole documents are compared.

| Language | iso | Years |
|---|---|---|
| Asante Twi | `twi_asante` | 2021, 2022, 2023 |
| Dagbani | `dag` | 2021, 2022, 2023 |
| Dangme | `ada` | 2022, 2023 |
| Ewe | `ewe` | 2021, 2022, 2023 |
| Ga | `gaa` | 2021, 2022 |
| Gonja | `gjn` | 2022, 2023 |
| Nzema | `nzi` | 2021, 2022, 2023 |

### Where things are in this repo

| What | Path |
|---|---|
| Document list (PDF names, language, year, English reference) | [`data/documents.json`](../data/documents.json) |
| Extracted text, one file per page, paragraphs marked `<<<P>>>` | [`data/text/finance_<year>_<iso>/`](../data/text) (English: `finance_<year>_eng`) |
| System translations (paragraph outputs re-joined) | [`translations/<model>/finance_<year>_<iso>.txt`](../translations) |
| Per-document scores | `translations/<model>/finance_<year>_<iso>.score.json` |
| Aggregated results | [`benchmarks/`](../benchmarks) |
| Re-download the PDFs | `python3 scripts/fetch_documents.py` |

### How the text was prepared

Each PDF page is rendered to an image and sent to Gemini alone, with a verbatim-extraction prompt
(no translating, correcting or commenting) that puts a `<<<P>>>` marker before every paragraph,
heading, list item or table row. Vision is used because several PDFs have broken or empty text
layers (for example 2021 Asante Twi and 2021 Ga). Pages that Gemini's safety filters blocked are
retried on other Gemini models; as a last resort the **English** reference falls back to the PDF's own
text layer. Pages that stay empty are blank or back covers. `run_extract.py` audits every document
(empty pages, commentary-like output, length mismatch against the PDF text layer).

### Caveats

- The budget is public and may appear in some systems' training data.
- Extraction is OCR by an LLM: small errors in the source text affect every system equally.
- Budget vocabulary (macro-economics, programmes, acronyms) is narrow; this is one domain, not general-purpose MT.

## Adding a dataset

1. Add an entry to `data/datasets.json` (id, name, publisher, `source_url`, description, `info_doc`).
2. Add its documents to `data/documents.json` with `"dataset": "<id>"`, a unique `id` prefixed
   with the dataset id (`<id>_<...>`), and a source / reference pair (PDFs in `data/pdfs/`; plain text can be
   put straight into `data/text/<id>/p001.txt` using the `<<<P>>>` marker format).
3. `python3 run_extract.py --docs <ids>` then `python3 run_benchmark.py --docs <ids>`.
4. Add a section to this file. The leaderboard picks the dataset up automatically (new column and a card on the Datasets tab).
