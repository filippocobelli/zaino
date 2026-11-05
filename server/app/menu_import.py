# SPDX-License-Identifier: GPL-3.0-or-later
"""Lettura del menù della mensa da un file (PDF o immagine).

- PDF con testo (come quelli che le ditte di ristorazione mandano alle scuole): la
  tabella si legge in locale con pdfplumber, senza servizi esterni.
- Foto, screenshot e PDF scansionati: servono un modello che legga le immagini.
  Si usa l'API di Anthropic solo se c'è una chiave: quella salvata (cifrata) dalla
  web app in Impostazioni, oppure la variabile ZAINO_AI_KEY (o ANTHROPIC_API_KEY).
  Il file del menù viene inviato ad Anthropic; il menù
  non contiene dati personali.

Il risultato ha la stessa forma di cfg["mensa"]["weeks"]:
una lista di settimane, ognuna con 5 giorni (lun–ven), ognuno con la lista dei piatti.
"""
import base64
import io
import json
import os
import re

import httpx

import vault

ENV_KEY = os.environ.get("ZAINO_AI_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
AI_MODEL = os.environ.get("ZAINO_AI_MODEL", "claude-sonnet-5-5")
AI_URL = "https://api.anthropic.com/v1/messages"

DAY_TOKENS = [("lun", "mon"), ("mar", "tue"), ("mer", "wed"), ("gio", "thu"), ("ven", "fri")]
GRADES = ("primaria", "infanzia", "secondaria")


class MenuError(Exception):
    """Errore da mostrare all'utente (chiave del testo in lang/*.json -> server)."""

    def __init__(self, key, **kw):
        super().__init__(key)
        self.key, self.kw = key, kw


def ai_key():
    """Chiave in uso: prima quella salvata dalla web app, poi la variabile d'ambiente."""
    return vault.get("ai_key") or ENV_KEY


def ai_key_source():
    if vault.get("ai_key"):
        return "saved"
    return "env" if ENV_KEY else ""


def ai_available():
    return bool(ai_key())


def check_key(key):
    """True se Anthropic accetta la chiave, False se la rifiuta, None se non si riesce a sentirlo."""
    try:
        r = httpx.get("https://api.anthropic.com/v1/models", timeout=15,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    except httpx.HTTPError:
        return None
    if r.status_code in (401, 403):
        return False
    return True if r.status_code == 200 else None


# ---------------------------------------------------------------- pulizia dei piatti

_LABEL = re.compile(r"^\s*(primo|secondo|contorno|dessert|frutta|piatto unico)\s*(piatto)?\s*:\s*", re.I)
_GRADE = re.compile(r"\b(infanzia|primaria|secondaria)\s*:\s*", re.I)


def clean_dish(s, grade="primaria"):
    """Una cella del menù -> testo del piatto ('' se vuota)."""
    if s is None:
        return ""
    s = " ".join(str(s).replace(" ", " ").split())
    # «Infanzia: fettina di pollo  Primaria: cosce di pollo» -> la variante del grado scelto
    parts = _GRADE.split(s)
    if len(parts) >= 3:
        variants = {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
        s = variants.get(grade) or variants.get("primaria") or next(iter(variants.values()))
    s = s.replace("*", "").strip(" \"“”«»'")
    s = _LABEL.sub("", s)
    if re.match(r"^p\.\s?u\.\s*", s, re.I):  # P.U. = piatto unico
        s = re.sub(r"^p\.\s?u\.\s*", "", s, flags=re.I) + " (piatto unico)"
    s = s.strip(" \"“”«»-–·,;:")
    if s.endswith("'") and not s.lower().endswith(" po'"):  # «Fusilli all'olio'»
        s = s.rstrip("'")
    s = s.lstrip("'")
    s = re.sub(r"\s+([,.;:])", r"\1", s).strip()
    return s[:1].upper() + s[1:] if s else ""


def _day_index(text):
    t = (text or "").strip().lower()
    for i, toks in enumerate(DAY_TOKENS):
        if any(t.startswith(k) for k in toks):
            return i
    return None


def _normalize(weeks, grade):
    out = []
    for wk in weeks or []:
        days = []
        for d in (list(wk or []) + [[]] * 5)[:5]:
            items = d if isinstance(d, list) else [d]
            dishes = [c for c in (clean_dish(x, grade) for x in items) if c]
            days.append(dishes)
        if any(days):
            out.append(days)
    return out


def _title_from_text(text):
    for line in (text or "").splitlines()[:6]:
        if re.search(r"\bmen[uùú]\b", line, re.I):
            return " ".join(line.split())[:60]
    return ""


# ---------------------------------------------------------------- PDF con testo

def _parse_tables(rows):
    """Righe di tabelle (liste di celle) -> settimane. Riconosce l'intestazione con i giorni
    e separa le settimane alle righe vuote o con «Settimana» nella prima colonna."""
    cols, weeks, cur = None, [], None

    def flush():
        nonlocal cur
        if cur and any(cur):
            weeks.append(cur)
        cur = None

    for row in rows:
        cells = [(c or "") for c in row]
        days = {}
        for j, c in enumerate(cells):
            k = _day_index(c)
            if k is not None and k not in days:
                days[k] = j
        if len(days) >= 4:  # intestazione: lunedì … venerdì
            cols = days
            flush()
            cur = [[] for _ in range(5)]
            continue
        if cols is None:
            continue
        day_texts = {k: cells[j] if j < len(cells) else "" for k, j in cols.items()}
        others = " ".join(c for j, c in enumerate(cells) if j not in cols.values())
        empty = not any(v.strip() for v in day_texts.values())
        if empty or re.search(r"sett|week|\d\s*°", others, re.I):
            if cur and any(cur):
                flush()
            if cur is None:
                cur = [[] for _ in range(5)]
            if empty:
                continue
        if cur is None:
            cur = [[] for _ in range(5)]
        for k, v in day_texts.items():
            if v and v.strip():
                cur[k].append(v)
    flush()
    return weeks


def read_pdf_tables(raw):
    """(titolo, settimane) da un PDF con testo; settimane vuote se non c'è una tabella leggibile."""
    import pdfplumber

    rows, title = [], ""
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages[:6]:
            if not title:
                title = _title_from_text(page.extract_text() or "")
            for table in page.extract_tables():
                rows.extend(table)
    return title, _parse_tables(rows)


# ---------------------------------------------------------------- immagini (AI)

PROMPT = """Questa è la tabella del menù di una mensa scolastica italiana, a rotazione su più settimane.
Trascrivila in JSON, senza altro testo:
{"title": "titolo del menù come scritto, es. Menù invernale 2026-27",
 "weeks": [ [ ["piatto", "piatto", ...], ...5 liste, da lunedì a venerdì ], ...una per settimana ] }
Regole:
- una voce per ogni settimana, nell'ordine (1ª, 2ª, …); per ogni giorno i piatti dall'alto in basso;
- copia ogni piatto com'è scritto, senza asterischi; non inventare e non correggere i nomi;
- una cella unita che occupa più righe (es. «P.U. Lasagne», piatto unico) vale una volta sola;
- se una cella ha varianti per gradi diversi (es. «Infanzia: … Primaria: …») tieni solo quella per {grade};
- ignora intestazioni, legenda, note sugli allergeni e loghi."""


def _band(profile, min_count, gap):
    """Tratto più lungo di valori >= min_count, unendo i buchi più corti di gap."""
    best, start, last = (0, 0), None, None
    for i, v in enumerate(profile + [0] * (gap + 1)):
        if v >= min_count:
            if start is None or i - last > gap:
                start = i
            last = i
            if last - start > best[1] - best[0]:
                best = (start, last + 1)
    return best


def _image_for_ai(raw):
    """Tiene solo la tabella (toglie barre del telefono e margini) e ricodifica in JPEG."""
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    small = im.copy()
    small.thumbnail((800, 800))
    k = im.width / small.width
    dark = small.convert("L").point(lambda v: 1 if v < 160 else 0)
    w, h = dark.size
    px = dark.load()
    rows = [sum(px[x, y] for x in range(w)) for y in range(h)]
    y0, y1 = _band(rows, max(2, w // 50), max(6, h // 60))
    cols = [sum(px[x, y] for y in range(y0, y1)) for x in range(w)]
    x0, x1 = _band(cols, 1, max(6, w // 40))
    if (x1 - x0) * (y1 - y0) > 0.12 * w * h:
        m = 10
        im = im.crop((max(0, int((x0 - m) * k)), max(0, int((y0 - m) * k)),
                      min(im.width, int((x1 + m) * k)), min(im.height, int((y1 + m) * k))))
    if max(im.size) > 2400:
        im.thumbnail((2400, 2400))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    return b.getvalue()


def _ask_ai(block, grade):
    key = ai_key()
    if not key:
        raise MenuError("menu_ai_missing")
    body = {"model": AI_MODEL, "max_tokens": 8000,
            "messages": [{"role": "user", "content": [block, {"type": "text", "text": PROMPT.replace("{grade}", grade)}]}]}
    try:
        r = httpx.post(AI_URL, json=body, timeout=120, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    except httpx.HTTPError as ex:
        raise MenuError("menu_ai_error", error=ex)
    if r.status_code != 200:
        raise MenuError("menu_ai_error", error=f"HTTP {r.status_code} {r.text[:120]}")
    text = "".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text")
    a, b = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[a:b + 1])
    except ValueError:
        raise MenuError("menu_ai_error", error="risposta non in JSON")
    return str(data.get("title") or "")[:60], data.get("weeks") or []


def read_with_ai(raw, kind, grade):
    if kind == "pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                 "data": base64.b64encode(raw).decode()}}
    else:
        try:
            jpg = _image_for_ai(raw)
        except Exception as ex:
            raise MenuError("image_unreadable", error=ex)
        block = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": base64.b64encode(jpg).decode()}}
    return _ask_ai(block, grade)


# ---------------------------------------------------------------- ingresso

def read_menu(raw, filename="", grade="primaria"):
    """File -> {"title", "weeks", "source"}. Solleva MenuError con un messaggio per l'utente."""
    grade = grade if grade in GRADES else "primaria"
    if not raw:
        raise MenuError("menu_empty")
    is_pdf = raw[:5] == b"%PDF-" or filename.lower().endswith(".pdf")
    source = "pdf"
    if is_pdf:
        try:
            title, weeks = read_pdf_tables(raw)
        except Exception as ex:
            raise MenuError("menu_pdf_unreadable", error=ex)
        weeks = _normalize(weeks, grade)
        if not weeks:  # PDF scansionato o senza tabella: prova con l'AI
            if not ai_available():
                raise MenuError("menu_pdf_no_table")
            title, weeks = read_with_ai(raw, "pdf", grade)
            weeks, source = _normalize(weeks, grade), "ai"
    else:
        title, weeks = read_with_ai(raw, "image", grade)
        weeks, source = _normalize(weeks, grade), "ai"
    if not weeks:
        raise MenuError("menu_not_found")
    return {"title": clean_dish(title) if title else "", "weeks": weeks, "source": source}
