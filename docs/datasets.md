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

## udhr: Universal Declaration of Human Rights

| | |
|---|---|
| Publisher | United Nations / Office of the High Commissioner for Human Rights (OHCHR) & Unicode Consortium |
| Source | <https://www.ohchr.org/en/human-rights/universal-declaration/universal-declaration-human-rights> |
| Domain | Legal / Human Rights charter |
| Years | 1948 |
| Pairs | 11 document pairs: a Ghanaian-language edition + the English reference edition |
| Direction | Bidirectional (`to_en` and `from_en`) |

The Universal Declaration of Human Rights (UDHR) is the most translated document in the world.
The translations for Ghanaian languages were prepared by official linguistic bodies (including the Bureau of Ghana Languages) and published by the UN OHCHR and the Unicode UDHR project.
Like the Citizens' Budget, whole documents are compared at corpus/document level (paragraphs are re-joined into full document text and scored with sacreBLEU and chrF against the English reference).

| Language | iso | Words (approx) |
|---|---|---|
| Asante Twi | `twi_asante` | 2,098 |
| Akuapem Twi | `twi_akuapem` | 1,890 |
| Fante | `fante` | 1,944 |
| Dagbani | `dag` | 2,174 |
| Dangme | `ada` | 2,912 |
| Ewe | `ewe` | 2,230 |
| Ga | `gaa` | 2,039 |
| Nzema | `nzi` | 2,176 |
| Gonja | `gjn` | 1,937 |
| Dagaare | `dga` | 2,582 |
| Kasem | `xsm` | 2,171 |
| *English (Reference)* | `eng` | 1,747 |

### Where things are in this repo

| What | Path |
|---|---|
| Preparation script | `scripts/prepare_udhr.py` |
| Cached XML sources | `data/udhr_xml/` |
| Document text | `data/text/udhr_<iso>/p001.txt` |
| System translations | `translations/<model>/udhr_<iso>[.from_en].txt` |
| Per-document scores | `translations/<model>/udhr_<iso>[.from_en].score.json` |

## jw: Watchtower (Study Edition)

| | |
|---|---|
| Publisher | Watch Tower Bible and Tract Society |
| Source | <https://www.jw.org/> |
| Domain | Religion / Community / Moral |
| Years | 2026 |
| Pairs | 10 document pairs: a Ghanaian-language edition + the English reference edition |
| Direction | Bidirectional (`to_en` and `from_en`) |

The Watchtower Study Edition is published monthly and translated by human translators into hundreds of languages worldwide.
Issue `w 202601` (January 2026) was selected as a recent, settled publication covering 10 Ghanaian languages.
Because Watchtower PDFs feature non-standard font encodings for African characters (`ɛ`, `ɔ`), page-by-page vision OCR using Gemini is used to extract clean, diacritically accurate text chunks.
Scored at document level against the English reference edition.

| Language | iso | Words (approx) |
|---|---|---|
| Asante Twi | `twi_asante` | 13,335 |
| Fante | `fante` | 14,464 |
| Ewe | `ewe` | 13,442 |
| Ga | `gaa` | 14,903 |
| Dangme | `ada` | 18,071 |
| Nzema | `nzi` | 12,709 |
| Dagaare | `dga` | 15,791 |
| Frafra | `gur` | 13,245 |
| Sehwi | `sfw` | 13,286 |
| Ahanta | `aha` | 10,897 |
| *English (Reference)* | `eng` | 11,657 |

### Where things are in this repo

| What | Path |
|---|---|
| Download script | `scripts/fetch_jw.py` |
| Source PDFs | `data/pdfs/jw_202601_<iso>.pdf` |
| Extracted text | `data/text/jw_202601_<iso>/p*.txt` |
| System translations | `translations/<model>/jw_202601_<iso>[.from_en].txt` |
| Per-document scores | `translations/<model>/jw_202601_<iso>[.from_en].score.json` |

## Adding a dataset

1. Add an entry to `data/datasets.json` (id, name, publisher, `source_url`, description, `info_doc`).
2. Add its documents to `data/documents.json` with `"dataset": "<id>"`, a unique `id` prefixed
   with the dataset id (`<id>_<...>`), and a source / reference pair (PDFs in `data/pdfs/`; plain text can be
   put straight into `data/text/<id>/p001.txt` using the `<<<P>>>` marker format).
3. `python3 run_extract.py --docs <ids>` then `python3 run_benchmark.py --docs <ids>`.
4. Add a section to this file. The leaderboard picks the dataset up automatically (new column and a card on the Datasets tab).
