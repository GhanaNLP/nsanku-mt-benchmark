"""Stage 2: translate each document paragraph-by-paragraph with each model, score at
document level, write translations/ and benchmarks/{iso}.yaml + benchmarks/summary.json."""
import json
from collections import defaultdict

import yaml

from . import config, extract, metrics, models


def run(doc_ids=None, model_ids=None, isos=None):
    docs = [d for d in config.documents()
            if (not doc_ids or d["id"] in doc_ids) and (not isos or d["iso"] in isos)]
    for mdl in models.load_models(model_ids):
        for d in docs:
            if not mdl.supports(d["iso"]):
                continue
            src = extract.load_paragraphs(d["id"])
            ref = extract.load_paragraphs(d["reference_id"])
            if not src or not ref:
                print(f"  skip {d['id']}: run run_extract.py first")
                continue
            print(f"{mdl.slug} · {d['id']} · {len(src)} paragraphs", flush=True)
            try:
                hyp = mdl.translate(src, d["iso"])
            except Exception as e:  # keep going; the paragraph cache makes a rerun resume here
                print(f"   FAILED {d['id']}: {str(e)[:120]} (rerun to resume; no score written)", flush=True)
                continue
            out = config.TRANSLATIONS / mdl.slug
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{d['id']}.txt").write_text("\n\n".join(hyp), encoding="utf-8")
            res = metrics.score(hyp, ref)
            (out / f"{d['id']}.score.json").write_text(json.dumps(res, indent=1))
            print(f"   BLEU {res['bleu']}  chrF {res['chrf']}", flush=True)
    assemble()


def _mean(xs):
    return round(sum(xs) / len(xs), 2)


def assemble():
    """Join every translations/<model>/<doc>.score.json into benchmarks/.

    Results are recorded PER DATASET (per_dataset). A language's headline BLEU/chrF is the
    mean of its per-dataset scores (each dataset weighs the same, however many documents
    it has), so adding datasets later never rewrites the existing per-dataset numbers.
    """
    config.BENCHMARKS.mkdir(exist_ok=True)
    docs = {d["id"]: d for d in config.documents()}
    mdls = config.models()
    scores = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # iso -> model -> dataset -> doc
    for m in mdls:
        slug = m["id"].split("/")[-1]
        for f in (config.TRANSLATIONS / slug).glob("*.score.json"):
            did = f.name[:-len(".score.json")]
            if did in docs:
                d = docs[did]
                scores[d["iso"]][m["id"]][d["dataset"]][did] = dict(json.loads(f.read_text()), year=d["year"])
    langs = {}
    for d in docs.values():
        langs.setdefault(d["iso"], {"language": d["language"], "datasets": set()})["datasets"].add(d["dataset"])
    summary = {"direction": "<language> -> English",
               "metric": "document-level BLEU (sacreBLEU) + chrF; headline = mean over datasets",
               "datasets": {x["id"]: dict(x, n_documents=sum(d["dataset"] == x["id"] for d in docs.values()))
                            for x in config.datasets()},
               "models": {m["id"]: {"name": m["name"], "track": m["kind"], "url": m.get("url")} for m in mdls},
               "languages": {}}
    for iso, info in sorted(langs.items()):
        rows, missing = [], []
        for m in mdls:
            per_ds = scores[iso].get(m["id"], {})
            if not per_ds:
                missing.append({"model": m["id"], "name": m["name"],
                                "reason": "language not supported" if iso not in m["codes"] else "not run yet"})
                continue
            ds_out = {ds: {"bleu": _mean([v["bleu"] for v in dd.values()]),
                           "chrf": _mean([v["chrf"] for v in dd.values()]),
                           "length_ratio": _mean([v["length_ratio"] for v in dd.values()]),
                           "documents": len(dd), "per_document": dict(sorted(dd.items()))}
                      for ds, dd in sorted(per_ds.items())}
            rows.append({"model": m["id"], "name": m["name"], "track": m["kind"], "url": m.get("url"),
                         "bleu": _mean([v["bleu"] for v in ds_out.values()]),
                         "chrf": _mean([v["chrf"] for v in ds_out.values()]),
                         "length_ratio": _mean([v["length_ratio"] for v in ds_out.values()]),
                         "documents": sum(v["documents"] for v in ds_out.values()),
                         "per_dataset": ds_out})
        rows.sort(key=lambda r: -r["bleu"])
        data = {"iso": iso, "language": info["language"], "direction": f"{info['language']} -> English",
                "datasets": sorted(info["datasets"]), "benchmarks": rows, "missing": missing}
        (config.BENCHMARKS / f"{iso}.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        summary["languages"][iso] = data
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    (config.BENCHMARKS / "summary.json").write_text(text, encoding="utf-8")
    (config.ROOT / "space" / "bundled_data.json").write_text(text, encoding="utf-8")
