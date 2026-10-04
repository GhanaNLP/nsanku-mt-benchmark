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


def assemble():
    """Join every translations/<model>/<doc>.score.json into benchmarks/."""
    config.BENCHMARKS.mkdir(exist_ok=True)
    docs = {d["id"]: d for d in config.documents()}
    by_iso = defaultdict(lambda: defaultdict(dict))
    for mdl in config.models():
        slug = mdl["id"].split("/")[-1]
        for f in (config.TRANSLATIONS / slug).glob("*.score.json"):
            did = f.name[:-len(".score.json")]
            if did in docs:
                by_iso[docs[did]["iso"]][mdl["id"]][did] = json.loads(f.read_text())
    names = {m["id"]: m["name"] for m in config.models()}
    summary = {"direction": "<language> -> English", "metric": "document-level BLEU (sacreBLEU) + chrF",
               "languages": {}}
    for iso, per_model in sorted(by_iso.items()):
        lang = next(d["language"] for d in docs.values() if d["iso"] == iso)
        rows = []
        for mid, per_doc in per_model.items():
            n = len(per_doc)
            rows.append({"model": mid, "name": names[mid],
                         "bleu": round(sum(v["bleu"] for v in per_doc.values()) / n, 2),
                         "chrf": round(sum(v["chrf"] for v in per_doc.values()) / n, 2),
                         "documents": n,
                         "per_document": {k: dict(v, year=docs[k]["year"]) for k, v in sorted(per_doc.items())}})
        rows.sort(key=lambda r: -r["bleu"])
        data = {"iso": iso, "language": lang, "direction": f"{lang} -> English", "benchmarks": rows}
        (config.BENCHMARKS / f"{iso}.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        summary["languages"][iso] = data
    (config.BENCHMARKS / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
