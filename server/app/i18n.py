# SPDX-License-Identifier: GPL-3.0-or-later
"""Lingue: un file JSON per lingua in lang/ (it.json è il riferimento completo).

Le chiavi mancanti in una traduzione ricadono sull'italiano, così una traduzione
parziale funziona lo stesso.
"""
import json
import os
from copy import deepcopy

LANG_DIR = os.path.join(os.path.dirname(__file__), "lang")
BASE = "it"
DEFAULT = os.environ.get("ZAINO_LANG", BASE)
_cache = {}


def _merge(base, over):
    out = deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(code):
    with open(os.path.join(LANG_DIR, f"{code}.json"), encoding="utf-8") as f:
        return json.load(f)


def available():
    """Codici delle lingue presenti in lang/."""
    return sorted(f[:-5] for f in os.listdir(LANG_DIR) if f.endswith(".json"))


def strings(code=None):
    """Testi completi di una lingua (con l'italiano come riserva)."""
    code = code if code in available() else (DEFAULT if DEFAULT in available() else BASE)
    if code not in _cache:
        base = _read(BASE)
        _cache[code] = base if code == BASE else _merge(base, _read(code))
    return _cache[code]


def languages():
    return [{"code": c, "name": _read(c).get("_name", c)} for c in available()]


def lang_of(cfg):
    return (cfg.get("settings") or {}).get("lang") or DEFAULT


# lingua della pagina in corso di disegno (impostata da render.render, sotto _render_lock)
CUR = {"s": None}


def use(cfg):
    CUR["s"] = strings(lang_of(cfg))


def get(key, lang=None):
    s = strings(lang) if lang else (CUR["s"] or strings())
    for part in key.split("."):
        s = s[part]
    return s


def t(key, lang=None, **kw):
    v = get(key, lang)
    return v.format(**kw) if kw and isinstance(v, str) else v
