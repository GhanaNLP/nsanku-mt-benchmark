"""MT systems. Every system translates ONE PARAGRAPH PER REQUEST (never a whole page or
document); results are cached per paragraph so runs are resumable and idempotent.

  translate(paras, iso) -> list[str]   (same length / order as paras)
"""
import asyncio
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import config

DIRECTIONS = ["to_en", "from_en"]  # <language> -> English, English -> <language>
HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
MAX_CHARS = 2500  # a single "paragraph" longer than this is split at sentence boundaries


def split_long(text, limit=MAX_CHARS):
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        while len(s) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:limit])
            s = s[limit:]
        if cur and len(cur) + len(s) + 1 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


class BaseMT:
    workers = 8

    def __init__(self, meta):
        self.meta = meta
        self.id = meta["id"]
        self.slug = self.id.split("/")[-1]

    def supports(self, iso, direction="to_en"):
        return iso in self.meta["codes"] and direction in self.meta.get("directions", DIRECTIONS)

    @staticmethod
    def _tag(iso, direction="to_en"):
        return iso if direction == "to_en" else f"en2{iso}"

    def _cache_file(self, iso, text):
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        d = config.CACHE / self.slug / iso
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{h}.txt"

    def translate_one(self, text, iso, direction="to_en"):  # one request
        raise NotImplementedError

    def _one_cached(self, text, iso, direction="to_en"):
        if not HAS_LETTER.search(text):
            return text  # numbers / symbols / dot leaders: nothing to translate
        f = self._cache_file(self._tag(iso, direction), text)
        if f.exists():
            return f.read_text(encoding="utf-8")
        out = " ".join(" ".join(self.translate_one(p, iso, direction).split()) for p in split_long(text))
        f.write_text(out, encoding="utf-8")
        return out

    def translate(self, paras, iso, direction="to_en"):
        unique = list(dict.fromkeys(paras))
        with ThreadPoolExecutor(self.workers) as ex:
            res = dict(zip(unique, ex.map(lambda p: self._one_cached(p, iso, direction), unique)))
        return [res[p] for p in paras]


def _retry(fn, tries=10):
    for a in range(tries):
        try:
            return fn()
        except Exception as e:
            if a == tries - 1:
                raise
            time.sleep(min(120, 2 ** a * 2))


class GeminiMT(BaseMT):
    workers = 48  # thinking is disabled for MT (budget 0): faster, and translation needs no reasoning
    PROMPT = ("Translate the following {src} text into {dst}. Output ONLY the {dst} "
              "translation of this text: no notes, no explanations, no quotes, no preamble. "
              "Keep numbers, names, acronyms and any ' | ' table separators as they are.\n\n{text}")

    def translate_one(self, text, iso, direction="to_en"):
        lang = self.meta["codes"][iso]
        src, dst = (lang, "English") if direction == "to_en" else ("English", lang)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MT_MODEL}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": self.PROMPT.format(
                    src=src, dst=dst, text=text)}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                                     "thinkingConfig": {"thinkingBudget": 0}}}

        def call():
            r = requests.post(url, json=body, headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=120)
            if r.status_code != 200:
                raise RuntimeError(f"Gemini {r.status_code}: {r.text[:200]}")
            parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        return _retry(call)


class KhayaMT(BaseMT):
    workers = 10  # 16 triggered gateway 502s
    URL = "https://translation-api.ghananlp.org/v1/translate"

    def translate_one(self, text, iso, direction="to_en"):
        c = self.meta["codes"][iso]
        body = {"in": text, "lang": f"{c}-en" if direction == "to_en" else f"en-{c}"}

        def call():
            r = requests.post(self.URL, json=body, timeout=120,
                              headers={"Ocp-Apim-Subscription-Key": config.KHAYA_API_KEY})
            if r.status_code != 200:
                raise RuntimeError(f"Khaya {r.status_code}: {r.text[:200]}")
            return r.json() if isinstance(r.json(), str) else str(r.json())
        return _retry(call)


class GoogleFreeMT(BaseMT):
    """Free Google Translate, keyless: https://clients5.google.com/translate_a/t?client=dict-chrome-ex
    (the endpoint behind the Chrome dictionary extension; POST, JSON reply).

    The translate_a/single endpoints (client=gtx / webapp, also used by py-googletrans) answer
    automated clients with a "Sorry..." block page; the py-googletrans fork hid that by returning the
    input text unchanged, which is how untranslated "translations" got scored. Here, transport errors
    raise, and SOFT-BLOCK GUARD stays as a safety net: an unchanged result for a non-trivial piece is
    re-tried, and a canary translation (a pair that always changes) decides whether the endpoint is
    blocked; while blocked we wait instead of caching untranslated text."""
    URL = "https://clients5.google.com/translate_a/t"
    workers = 4
    MIN_CHARS = 25          # shorter pieces (names, acronyms, numbers) can legitimately be unchanged
    CANARY = "The Government will increase spending on education and health."

    def _call(self, text, sl, tl):
        r = requests.post(self.URL, params={"client": "dict-chrome-ex", "sl": sl, "tl": tl}, data={"q": text},
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"google {r.status_code}")
        data = r.json()
        parts = [x if isinstance(x, str) else x[0] for x in data]  # ["text"] or [["text", "src"]]
        return " ".join(" ".join(parts).split())

    def _canary_ok(self):
        try:
            return self._call(self.CANARY, "en", "fr").strip() != self.CANARY
        except Exception:
            return False

    def translate_one(self, text, iso, direction="to_en"):
        c = self.meta["codes"][iso]
        sl, tl = (c, "en") if direction == "to_en" else ("en", c)
        for a in range(14):
            try:
                res = self._call(text, sl, tl)
            except Exception:
                time.sleep(min(90, 2 ** min(a, 6)))
                continue
            if res.strip() != text.strip() or len(text) < self.MIN_CHARS:
                return res
            if a < 2:                      # unchanged: maybe transient
                time.sleep(1.5)
                continue
            if self._canary_ok():          # endpoint healthy and still unchanged: a real pass-through
                return res
            print("   google soft-blocked: waiting 60s", flush=True)
            time.sleep(60)
        raise RuntimeError("google: piece kept failing")


class HFSeq2SeqMT(BaseMT):
    """Open-weights seq2seq models run locally on GPU (NLLB, MADLAD, ...).

    These are sentence-level models with a ~512-token limit, so a paragraph longer than
    SENT_CHARS is split at sentence boundaries (only then); pieces are batched by length,
    translated with beam search and re-joined into the paragraph. Cached per paragraph.
    Subclasses provide _load(), _encode(texts, iso) and _generate(enc)."""
    SENT_CHARS = 600
    BATCH_CHARS = 8000
    BEAMS = 4

    def _load(self):
        raise NotImplementedError

    def _encode(self, texts, iso, direction):
        raise NotImplementedError

    def _generate(self, enc, iso, direction):
        raise NotImplementedError

    def _decode_batch(self, batch, iso, direction):
        """Translate a batch; the GPU is shared with other jobs, so on CUDA OOM free the cache and
        retry with half the batch (down to one piece) instead of failing the document."""
        torch = self._torch
        for attempt in range(8):
            try:
                texts = []
                step = max(1, len(batch) >> attempt)
                for k in range(0, len(batch), step):
                    enc = self._encode([b[2] for b in batch[k:k + step]], iso, direction)
                    with torch.no_grad():
                        gen = self._generate(enc, iso, direction)
                    texts += self._tok.batch_decode(gen, skip_special_tokens=True)
                return texts
            except torch.OutOfMemoryError:
                torch.cuda.empty_cache()
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("CUDA out of memory after retries")

    def translate(self, paras, iso, direction="to_en"):
        import torch
        self._load()
        self._torch = torch
        unique = list(dict.fromkeys(paras))
        result, todo = {}, []
        for p in unique:
            if not HAS_LETTER.search(p):
                result[p] = p
                continue
            f = self._cache_file(self._tag(iso, direction), p)
            if f.exists():
                result[p] = f.read_text(encoding="utf-8")
            else:
                todo.append(p)
        pieces = [(p, i, piece) for p in todo for i, piece in enumerate(split_long(p, self.SENT_CHARS))]
        pieces.sort(key=lambda x: len(x[2]))
        out, i = {}, 0
        while i < len(pieces):
            j, longest = i, 0
            while j < len(pieces) and (j - i + 1) * max(longest, len(pieces[j][2])) <= self.BATCH_CHARS:
                longest = max(longest, len(pieces[j][2]))
                j += 1
            j = max(j, i + 1)
            batch = pieces[i:j]
            texts = self._decode_batch(batch, iso, direction)
            for b, text in zip(batch, texts):
                out[(b[0], b[1])] = " ".join(text.split())
            i = j
        for p in todo:
            n = len(split_long(p, self.SENT_CHARS))
            res = " ".join(out[(p, k)] for k in range(n))
            self._cache_file(self._tag(iso, direction), p).write_text(res, encoding="utf-8")
            result[p] = res
        return [result[p] for p in paras]


class NllbMT(HFSeq2SeqMT):
    """Meta NLLB-200: source language tag per language, English forced as target."""
    def _load(self):
        if getattr(self, "_model", None) is None:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(self.id)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.id, dtype=torch.bfloat16).to("cuda").eval()

    def _encode(self, texts, iso, direction):
        self._tok.src_lang = self.meta["codes"][iso] if direction == "to_en" else "eng_Latn"
        return self._tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=512).to("cuda")

    def _generate(self, enc, iso, direction):
        target = "eng_Latn" if direction == "to_en" else self.meta["codes"][iso]
        return self._model.generate(**enc, forced_bos_token_id=self._tok.convert_tokens_to_ids(target),
                                    num_beams=self.BEAMS, max_new_tokens=min(512, enc["input_ids"].shape[1] * 2 + 20))


class NllbLoraMT(NllbMT):
    """A LoRA adapter on facebook/nllb-200-distilled-600M, merged into the base for inference.
    Recipe follows the adapter's model card (mclanorjeff/NLLB-Twi-Human-Aligned): tokenizer from
    the adapter repo, src_lang "aka_GH" (not an NLLB tag: it maps to <unk>, as in training), 5 beams."""
    BASE = "facebook/nllb-200-distilled-600M"
    BEAMS = 5

    def _load(self):
        if getattr(self, "_model", None) is None:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(self.id)
            base = AutoModelForSeq2SeqLM.from_pretrained(self.BASE, dtype=torch.bfloat16)
            self._model = PeftModel.from_pretrained(base, self.id).merge_and_unload().to("cuda").eval()


class MadladMT(HFSeq2SeqMT):
    """Google MADLAD-400 (T5): the target is chosen with a "<2en>" prefix; there is no source tag.
    `codes` records the language's tag in MADLAD's target inventory (evidence it is in the 419)."""
    def _load(self):
        if getattr(self, "_model", None) is None:
            import torch
            from transformers import AutoTokenizer, T5ForConditionalGeneration
            self._tok = AutoTokenizer.from_pretrained(self.id)
            self._model = T5ForConditionalGeneration.from_pretrained(self.id, dtype=torch.bfloat16).to("cuda").eval()

    def _encode(self, texts, iso, direction):
        tag = "en" if direction == "to_en" else self.meta["codes"][iso]
        return self._tok([f"<2{tag}> {t}" for t in texts], return_tensors="pt", padding=True,
                         truncation=True, max_length=512).to("cuda")

    def _generate(self, enc, iso, direction):
        return self._model.generate(**enc, num_beams=self.BEAMS, max_new_tokens=min(512, enc["input_ids"].shape[1] * 2 + 20))


KINDS = {"Google/gemini-3.8-flash": GeminiMT, "KhayaAI/khaya-translate": KhayaMT,
         "Google/google-translate-free": GoogleFreeMT}


def local_class(model_id):
    if model_id.startswith("facebook/nllb"):
        return NllbMT
    if model_id.startswith("google/madlad"):
        return MadladMT
    if "NLLB" in model_id:
        return NllbLoraMT
    raise KeyError(model_id)


def load_models(only=None):
    out = []
    for m in config.models():
        if only and m["id"] not in only and m["id"].split("/")[-1] not in only:
            continue
        out.append(local_class(m["id"])(m) if m["id"] not in KINDS else KINDS[m["id"]](m))
    return out
