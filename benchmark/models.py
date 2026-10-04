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

    def supports(self, iso):
        return iso in self.meta["codes"]

    def _cache_file(self, iso, text):
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        d = config.CACHE / self.slug / iso
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{h}.txt"

    def translate_one(self, text, iso):  # one request
        raise NotImplementedError

    def _one_cached(self, text, iso):
        if not HAS_LETTER.search(text):
            return text  # numbers / symbols / dot leaders: nothing to translate
        f = self._cache_file(iso, text)
        if f.exists():
            return f.read_text(encoding="utf-8")
        out = " ".join(" ".join(self.translate_one(p, iso).split()) for p in split_long(text))
        f.write_text(out, encoding="utf-8")
        return out

    def translate(self, paras, iso):
        unique = list(dict.fromkeys(paras))
        with ThreadPoolExecutor(self.workers) as ex:
            res = dict(zip(unique, ex.map(lambda p: self._one_cached(p, iso), unique)))
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
    PROMPT = ("Translate the following {lang} text into English. Output ONLY the English "
              "translation of this text: no notes, no explanations, no quotes, no preamble. "
              "Keep numbers, names, acronyms and any ' | ' table separators as they are.\n\n{text}")

    def translate_one(self, text, iso):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MT_MODEL}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": self.PROMPT.format(
                    lang=self.meta["codes"][iso], text=text)}]}],
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

    def translate_one(self, text, iso):
        body = {"in": text, "lang": f"{self.meta['codes'][iso]}-en"}

        def call():
            r = requests.post(self.URL, json=body, timeout=120,
                              headers={"Ocp-Apim-Subscription-Key": config.KHAYA_API_KEY})
            if r.status_code != 200:
                raise RuntimeError(f"Khaya {r.status_code}: {r.text[:200]}")
            return r.json() if isinstance(r.json(), str) else str(r.json())
        return _retry(call)


class GoogleFreeMT(BaseMT):
    """Free Google Translate via the GhanaNLP fork of py-googletrans (async, web endpoint).
    One shared client, a few concurrent requests (the endpoint blocks IPs that look automated)."""
    CONCURRENCY = 4

    def translate(self, paras, iso):
        from googletrans import Translator
        unique = list(dict.fromkeys(paras))
        src = self.meta["codes"][iso]

        async def one(t, sem, text):
            if not HAS_LETTER.search(text):
                return text
            f = self._cache_file(iso, text)
            if f.exists():
                return f.read_text(encoding="utf-8")
            out = []
            for piece in split_long(text):
                for a in range(8):
                    try:
                        async with sem:
                            out.append(" ".join((await t.translate(piece, src=src, dest="en")).text.split()))
                        break
                    except Exception:
                        if a == 7:
                            raise
                        await asyncio.sleep(min(90, 2 ** a * 2))
            res = " ".join(out)
            f.write_text(res, encoding="utf-8")
            return res

        async def main():
            sem = asyncio.Semaphore(self.CONCURRENCY)
            async with Translator() as t:
                return await asyncio.gather(*(one(t, sem, p) for p in unique))

        res = dict(zip(unique, asyncio.run(main())))
        return [res[p] for p in paras]


KINDS = {"Google/gemini-3.8-flash": GeminiMT, "KhayaAI/khaya-translate": KhayaMT,
         "Google/google-translate-free": GoogleFreeMT}


def load_models(only=None):
    out = []
    for m in config.models():
        if only and m["id"] not in only and m["id"].split("/")[-1] not in only:
            continue
        out.append(KINDS[m["id"]](m))
    return out
