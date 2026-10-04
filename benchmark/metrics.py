"""Document-level BLEU / chrF: the whole document is ONE segment (paragraph outputs are
re-joined in order), scored with sacreBLEU against the English edition of the same year."""
from sacrebleu.metrics import BLEU, CHRF

_bleu, _chrf = BLEU(), CHRF()


def norm(paras):
    return " ".join(" ".join(paras).split())


def score(hyp_paras, ref_paras):
    hyp, ref = norm(hyp_paras), norm(ref_paras)
    b = _bleu.corpus_score([hyp], [[ref]])
    return {"bleu": round(b.score, 2), "chrf": round(_chrf.corpus_score([hyp], [[ref]]).score, 2),
            "length_ratio": round(b.sys_len / max(b.ref_len, 1), 3),
            "hyp_words": len(hyp.split()), "ref_words": len(ref.split())}
