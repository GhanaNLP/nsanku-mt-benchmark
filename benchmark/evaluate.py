"""Stage 2: translate each document paragraph-by-paragraph with each model, in each direction,
score at document level, write translations/ and benchmarks/{iso}.yaml + benchmarks/summary.json.

Directions
  to_en    <language> -> English   source = language edition, reference = English edition
  from_en  English -> <language>   source = English edition, reference = language edition
Both are scored and recorded separately; there is deliberately no combined score across directions.
"""
import json
from collections import defaultdict

import yaml

from . import config, extract, metrics, models

DIRECTIONS = models.DIRECTIONS
LABELS = {"to_en": "X → English", "from_en": "English → X"}


def _stem(doc_id, direction):
    return doc_id if direction == "to_en" else f"{doc_id}.{direction}"


def run(doc_ids=None, model_ids=None, isos=None, directions=None):
    directions = directions or DIRECTIONS
    docs = [d for d in config.documents()
            if (not doc_ids or d["id"] in doc_ids) and (not isos or d["iso"] in isos)]
    for mdl in models.load_models(model_ids):
        for direction in directions:
            for d in docs:
                if not mdl.supports(d["iso"], direction):
                    continue
                lang = extract.load_paragraphs(d["id"])
                eng = extract.load_paragraphs(d["reference_id"])
                src, ref = (lang, eng) if direction == "to_en" else (eng, lang)
                if not src or not ref:
                    print(f"  skip {d['id']}: run run_extract.py first")
                    continue
                print(f"{mdl.slug} · {direction} · {d['id']} · {len(src)} paragraphs", flush=True)
                try:
                    hyp = mdl.translate(src, d["iso"], direction)
                except Exception as e:  # keep going; the paragraph cache makes a rerun resume here
                    print(f"   FAILED {d['id']}: {str(e)[:120]} (rerun to resume; no score written)", flush=True)
                    continue
                out = config.TRANSLATIONS / mdl.slug
                out.mkdir(parents=True, exist_ok=True)
                stem = _stem(d["id"], direction)
                (out / f"{stem}.txt").write_text("\n\n".join(hyp), encoding="utf-8")
                res = metrics.score(hyp, ref)
                (out / f"{stem}.score.json").write_text(json.dumps(res, indent=1))
                print(f"   BLEU {res['bleu']}  chrF {res['chrf']}", flush=True)
    assemble()


def _mean(xs):
    return round(sum(xs) / len(xs), 2)


def _direction_block(per_ds):
    ds_out = {ds: {"bleu": _mean([v["bleu"] for v in dd.values()]),
                   "chrf": _mean([v["chrf"] for v in dd.values()]),
                   "length_ratio": _mean([v["length_ratio"] for v in dd.values()]),
                   "documents": len(dd), "per_document": dict(sorted(dd.items()))}
              for ds, dd in sorted(per_ds.items())}
    return {"bleu": _mean([v["bleu"] for v in ds_out.values()]),
            "chrf": _mean([v["chrf"] for v in ds_out.values()]),
            "length_ratio": _mean([v["length_ratio"] for v in ds_out.values()]),
            "documents": sum(v["documents"] for v in ds_out.values()), "per_dataset": ds_out}


def assemble():
    """Join every translations/<model>/<doc>[.<direction>].score.json into benchmarks/.

    Results are recorded PER DIRECTION and PER DATASET, and directions are never averaged together.
    Within a direction a language's score is the mean of its per-dataset scores (each dataset weighs
    the same), so adding a dataset never rewrites the existing numbers.
    """
    config.BENCHMARKS.mkdir(exist_ok=True)
    docs = {d["id"]: d for d in config.documents()}
    mdls = config.models()
    scores = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
    for m in mdls:  # iso -> model -> direction -> dataset -> doc
        slug = m["id"].split("/")[-1]
        for f in (config.TRANSLATIONS / slug).glob("*.score.json"):
            stem = f.name[:-len(".score.json")]
            direction = "from_en" if stem.endswith(".from_en") else "to_en"
            did = stem[:-len(".from_en")] if direction == "from_en" else stem
            if did in docs:
                d = docs[did]
                scores[d["iso"]][m["id"]][direction][d["dataset"]][did] = dict(json.loads(f.read_text()), year=d["year"])
    langs = {}
    for d in docs.values():
        langs.setdefault(d["iso"], {"language": d["language"], "datasets": set()})["datasets"].add(d["dataset"])
    summary = {"metric": "document-level BLEU (sacreBLEU) + chrF; per direction, per dataset (no cross-direction mean)",
               "directions": LABELS,
               "datasets": {x["id"]: dict(x, n_documents=sum(d["dataset"] == x["id"] for d in docs.values()))
                            for x in config.datasets()},
               "models": {m["id"]: {"name": m["name"], "track": m["kind"], "url": m.get("url")} for m in mdls},
               "languages": {}}
    for iso, info in sorted(langs.items()):
        rows, missing = [], []
        for m in mdls:
            by_dir = {dr: _direction_block(per_ds) for dr, per_ds in scores[iso].get(m["id"], {}).items() if per_ds}
            for dr in DIRECTIONS:
                if dr not in by_dir:
                    reason = ("language not supported" if iso not in m["codes"] else
                              "direction not supported" if dr not in m.get("directions", DIRECTIONS) else "not run yet")
                    missing.append({"model": m["id"], "name": m["name"], "direction": dr, "reason": reason})
            if not by_dir:
                continue
            rows.append({"model": m["id"], "name": m["name"], "track": m["kind"], "url": m.get("url"),
                         "directions": {dr: by_dir[dr] for dr in DIRECTIONS if dr in by_dir}})
        rows.sort(key=lambda r: -(r["directions"].get("from_en") or r["directions"]["to_en"])["bleu"])
        data = {"iso": iso, "language": info["language"], "datasets": sorted(info["datasets"]),
                "benchmarks": rows, "missing": missing}
        (config.BENCHMARKS / f"{iso}.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        summary["languages"][iso] = data
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    (config.BENCHMARKS / "summary.json").write_text(text, encoding="utf-8")
    (config.ROOT / "space").mkdir(exist_ok=True)
    (config.ROOT / "space" / "bundled_data.json").write_text(text, encoding="utf-8")
