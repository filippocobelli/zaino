# SPDX-License-Identifier: GPL-3.0-or-later
"""Zaino — server della dashboard scolastica e-paper per ZECTRIX NOTE4C (porta 3021)."""
import os
import threading
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

import data as D
import i18n
import render as RD
import store
from styles import STYLES, THEMES, color_name, suggest_style

from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Zaino")
STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/fonts", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "fonts")), name="fonts")
_render_lock = threading.Lock()
SECTIONS = {"settings", "subjects", "timetable", "extras", "diary", "calendars", "mensa"}


# ---------------------------------------------------------------- admin

@app.get("/")
def root():
    return RedirectResponse("/admin")


@app.get("/apple-touch-icon.png")
def touch_icon():
    return FileResponse(os.path.join(STATIC, "apple-touch-icon.png"))


@app.get("/favicon.ico")
def favicon():
    return FileResponse(os.path.join(STATIC, "favicon.png"), media_type="image/png")


@app.get("/admin")
def admin():
    return FileResponse(os.path.join(STATIC, "admin.html"), headers={"Cache-Control": "no-store"})


def msg(cfg, key, **kw):
    """Messaggio d'errore nella lingua scelta."""
    return i18n.t("server." + key, i18n.lang_of(cfg), **kw)


@app.get("/api/lang")
def api_lang():
    """Testi della web app nella lingua scelta, più l'elenco delle lingue disponibili."""
    cfg = store.load()
    s = i18n.strings(i18n.lang_of(cfg))
    return {"lang": i18n.lang_of(cfg), "locale": s.get("_locale", "it-IT"), "web": s["web"],
            "languages": i18n.languages()}


@app.get("/api/config")
def get_config():
    cfg = store.load()
    return {
        **cfg,
        "styles": [{"id": k, "label": v[0]} for k, v in STYLES.items()],
        "themes": [{"id": k, "label": v["label"], "web": v["web"], "on_web": v["on_web"]} for k, v in THEMES.items()],
        "state": store.load_state(),
        "has_riposo": bool(cfg.get("riposo_images")),
        "demo": D.DEMO,
    }


@app.put("/api/{section}")
async def put_section(section: str, request: Request):
    cfg = store.load()
    if section not in SECTIONS:
        raise HTTPException(404, msg(cfg, "unknown_section"))
    body = await request.json()
    if section == "subjects":
        for s in body:
            s.setdefault("id", store.new_id())
            s["name"] = (s.get("name") or "").strip() or "?"
            s["short"] = (s.get("short") or s["name"][:2]).strip()[:3]
            if s.get("style") not in STYLES:
                s["style"] = suggest_style(s.get("color", "#000000"))
            s["materials"] = [m.strip() for m in s.get("materials", []) if m.strip()]
            s["zaino"] = s.get("zaino", True) is not False
            s["color_name"] = (s.get("color_name") or "").strip()[:14]
        valid = {s["id"] for s in body}
        for day in cfg["timetable"].values():  # rimuove dall'orario le materie cancellate
            day["slots"] = [i for i in day.get("slots", []) if i in valid]
    if section == "diary":
        for e in body:
            e.setdefault("id", store.new_id())
            e["bring"] = [b.strip() for b in e.get("bring", []) if b.strip()]
    if section == "calendars":
        for c in body:
            c.setdefault("id", store.new_id())
    if section == "settings":
        body = {**cfg["settings"], **body}
        if body.get("accent") not in THEMES:
            body["accent"] = "rosso"
        if body.get("lang") not in i18n.available():
            body["lang"] = i18n.DEFAULT
    if section == "mensa":
        weeks = []
        for wk in body.get("weeks") or [[]]:
            wk = (list(wk) + [[]] * 5)[:5]
            weeks.append([[x.strip() for x in day if x and x.strip()] for day in wk])
        body = {"enabled": bool(body.get("enabled")), "title": (body.get("title") or "").strip(),
                "week1": body.get("week1") or "", "weeks": weeks or [[[], [], [], [], []]]}
    cfg[section] = body
    store.save(cfg)
    return {"ok": True}


@app.get("/api/geocode")
def api_geocode(q: str):
    try:
        return {"results": D.geocode(q)}
    except Exception as ex:
        raise HTTPException(502, msg(store.load(), "search_unavailable", error=ex))


@app.get("/api/suggest")
def api_suggest(color: str):
    name = color_name(color)
    lang = i18n.lang_of(store.load())
    return {"style": suggest_style(color), "name": i18n.t("display.colors", lang).get(name, name)}


@app.get("/api/swatch/{style_id}.png")
def api_swatch(style_id: str):
    if style_id not in STYLES:
        raise HTTPException(404)
    return Response(RD.swatch_png(style_id), media_type="image/png",
                    headers={"Cache-Control": "max-age=86400"})


@app.get("/api/calendars/test")
def api_cal_test():
    cfg = store.load()
    evs, errors = D.events(cfg, D.now(cfg).date(), 7)
    return {"errors": errors, "events": [
        {"title": e["title"], "calendar": e["calendar"], "all_day": e["all_day"],
         "start": e["start"].strftime("%a %d/%m %H:%M")} for e in evs[:40]]}


@app.post("/api/riposo")
async def api_riposo(file: UploadFile = File(...), mode: str = Form("cover")):
    raw = await file.read()
    cfg = store.load()
    try:
        img = RD.photo_to_bwry(raw, mode)
    except Exception as ex:
        raise HTTPException(400, msg(cfg, "image_unreadable", error=ex))
    i = store.new_id()
    os.makedirs(store.RIPOSO_DIR, exist_ok=True)
    img.save(store.riposo_file(i))
    name = os.path.splitext(file.filename or msg(cfg, "image_default_name"))[0][:40]
    cfg["riposo_images"].append({"id": i, "name": name, "uploaded": D.now(cfg).strftime("%d/%m/%Y")})
    cfg["settings"]["riposo_active"] = i  # l'ultima caricata diventa quella mostrata
    store.save(cfg)
    return {"ok": True, "id": i}


@app.post("/api/riposo/{img_id}/attiva")
def api_riposo_active(img_id: str):
    cfg = store.load()
    if not any(x["id"] == img_id for x in cfg["riposo_images"]):
        raise HTTPException(404, msg(cfg, "image_not_found"))
    cfg["settings"]["riposo_active"] = img_id
    store.save(cfg)
    return {"ok": True}


@app.delete("/api/riposo/{img_id}")
def api_riposo_del(img_id: str):
    cfg = store.load()
    cfg["riposo_images"] = [x for x in cfg["riposo_images"] if x["id"] != img_id]
    if cfg["settings"].get("riposo_active") == img_id:
        cfg["settings"]["riposo_active"] = cfg["riposo_images"][-1]["id"] if cfg["riposo_images"] else None
    store.save(cfg)
    f = store.riposo_file(img_id)
    if os.path.exists(f):
        os.remove(f)
    return {"ok": True}


@app.get("/api/riposo/{img_id}.png")
def api_riposo_img(img_id: str):
    f = store.riposo_file(img_id)
    if not os.path.exists(f):
        raise HTTPException(404)
    from PIL import Image
    return Response(RD.to_png(Image.open(f), 1), media_type="image/png",
                    headers={"Cache-Control": "max-age=86400"})


@app.get("/preview/{page}.png")
def preview(page: str):
    if page == "auto":
        page = auto_page(store.load(), None)
    if page not in RD.PAGES:
        raise HTTPException(404)
    cfg = store.load()
    with _render_lock:
        img = RD.render(page, cfg, D.now(cfg), store.load_state())
    return Response(RD.to_png(img, 2), media_type="image/png", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- logica device

def _in_window(t, start, end):
    a, b = D.hm(start), D.hm(end)
    if a is None or b is None or a == b:
        return False
    return a <= t < b if a < b else (t >= a or t < b)


def pages_on(cfg):
    """Pagine attive, nell'ordine scelto nelle impostazioni."""
    known = list(RD.PAGES)
    cfg_pages = cfg["settings"].get("pages") or []
    seen, out = set(), []
    for p in cfg_pages:
        if p.get("id") in known and p["id"] not in seen:
            seen.add(p["id"])
            if p.get("on", True):
                out.append(p["id"])
    for p in known:  # pagine nuove non ancora in elenco: attive in coda
        if p not in seen:
            out.append(p)
    if "riposo" in out and not cfg.get("riposo_images"):
        out.remove("riposo")
    menu = (cfg.get("mensa") or {}).get("weeks") or []
    if "mensa" in out and not any(dish for wk in menu for day in wk for dish in day):
        out.remove("mensa")  # nessun menù inserito
    return out or ["home"]


def auto_page(cfg, now=None):
    now = now or D.now(cfg)
    s = cfg["settings"]
    on = pages_on(cfg)
    t = now.hour * 60 + now.minute
    rip = "riposo" in on
    if s.get("riposo_night") and rip and _in_window(t, s.get("night_start"), s.get("night_end")):
        return "riposo"
    today = now.date()
    school = D.is_school_day(cfg, today)
    if not school and s.get("riposo_no_school") and rip:
        return "riposo"
    # programma della giornata: la prima fascia che corrisponde decide la pagina
    eve = D.next_school_day(cfg, today) == today + timedelta(days=1)
    cond = {"sempre": True, "scuola": school, "no_scuola": not school, "vigilia": eve}
    for slot in s.get("schedule") or []:
        if slot.get("page") in on and cond.get(slot.get("when", "sempre"), True) \
                and _in_window(t, slot.get("from"), slot.get("to")):
            return slot["page"]
    dflt = s.get("schedule_default") or "home"
    return dflt if dflt in on else ("home" if "home" in on else on[0])


def sleep_seconds(cfg, now):
    s = cfg["settings"]
    edges = list(s.get("wake_times", []))
    for slot in s.get("schedule") or []:  # si sveglia anche a inizio e fine di ogni fascia
        edges += [slot.get("from"), slot.get("to")]
    times = sorted({x for x in (D.hm(v) for v in edges if v) if x is not None and x < 24 * 60})
    if not times:
        return 1800
    base = now.replace(second=0, microsecond=0)
    t = now.hour * 60 + now.minute
    for m in times:
        if m > t:
            target = base.replace(hour=m // 60, minute=m % 60)
            break
    else:
        target = (base + timedelta(days=1)).replace(hour=times[0] // 60, minute=times[0] % 60)
    # differenza in UTC: con l'ora legale la differenza tra orari locali sbaglierebbe di un'ora
    delta = target.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    return max(60, int(delta.total_seconds()))


def _battery_pct(mv):
    return max(0, min(100, round((mv - 3300) / (4150 - 3300) * 100)))


def _device_response(request, page, battery_mv):
    cfg = store.load()
    now = D.now(cfg)
    state = store.load_state()
    state["last_seen"] = now.isoformat(timespec="seconds")
    state["last_page"] = page
    if battery_mv:
        state["battery_mv"] = battery_mv
        state["battery_pct"] = _battery_pct(battery_mv)
    with _render_lock:
        w = D.weather(cfg)
        tag = RD.etag(RD.to_2bpp(RD.render(page, cfg, now, state, w, stamp=False)))
        headers = {"ETag": f'"{tag}"', "X-Page": page, "X-Sleep-Seconds": str(sleep_seconds(cfg, now))}
        if request.headers.get("if-none-match", "").strip('"') == tag:
            store.save_state(state)
            return Response(status_code=304, headers=headers)
        buf = RD.to_2bpp(RD.render(page, cfg, now, state, w, stamp=True))
    state["last_etag"] = tag
    store.save_state(state)
    return Response(buf, media_type="application/octet-stream", headers=headers)


@app.get("/device/current.bin")
def device_current(request: Request, battery_mv: int = 0):
    """Risveglio a timer: pagina automatica. 304 se il contenuto non è cambiato."""
    cfg = store.load()
    return _device_response(request, auto_page(cfg), battery_mv)


@app.get("/device/page/{page}.bin")
def device_page(page: str, request: Request, battery_mv: int = 0):
    """Pagina richiesta coi tasti."""
    if page not in RD.PAGES:
        raise HTTPException(404)
    return _device_response(request, page, battery_mv)


def nav_order(cfg):
    """Ordine delle pagine scorse col tasto frontale."""
    return pages_on(cfg)


@app.get("/device/pages")
def device_pages():
    return {"order": nav_order(store.load())}


@app.get("/device/nav/{index}.bin")
def device_nav(index: int, request: Request, battery_mv: int = 0):
    """Pagina n-esima dell'ordine dei tasti (il firmware manda solo l'indice)."""
    cfg = store.load()
    order = nav_order(cfg)
    resp = _device_response(request, order[index % len(order)], battery_mv)
    resp.headers["X-Page-Count"] = str(len(order))
    # quanto resta visibile una pagina scelta col tasto prima di tornare a quella automatica
    try:
        hold = int(float(cfg["settings"].get("button_hold_minutes") or 3) * 60)
    except (TypeError, ValueError):
        hold = 180
    resp.headers["X-Sleep-Seconds"] = str(max(60, min(hold, 3600)))
    return resp


@app.get("/health")
def health():
    return JSONResponse({"ok": True, "time": datetime.now().isoformat(timespec="seconds")})
