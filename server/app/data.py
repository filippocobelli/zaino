# SPDX-License-Identifier: GPL-3.0-or-later
"""Dati: logica scolastica, eventi iCal, meteo."""
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from i18n import t
from store import WEEKDAYS


# ZAINO_DEMO=1: meteo ed eventi fittizi, per provare il pannello senza configurare nulla
DEMO = os.environ.get("ZAINO_DEMO") == "1"


def tz(cfg):
    return ZoneInfo(cfg["settings"].get("timezone") or "Europe/Rome")


def now(cfg):
    return datetime.now(tz(cfg))


def hm(s):
    """'08:30' -> minuti dalla mezzanotte, None se vuoto o non valido."""
    if not s:
        return None
    try:
        h, m = str(s).strip().split(":")[:2]
        v = int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None
    return v if 0 <= v <= 24 * 60 else None


# ---------------------------------------------------------------- scuola

def _parse_d(s):
    return date.fromisoformat(s) if s else None


def is_holiday(cfg, d):
    for e in cfg["diary"]:
        if e.get("type") == "vacanza":
            a = _parse_d(e.get("date"))
            b = _parse_d(e.get("end_date")) or a
            if a and a <= d <= b:
                return True
    return False


def is_school_day(cfg, d):
    day = cfg["timetable"].get(WEEKDAYS[d.weekday()], {})
    return bool(day.get("slots")) and not is_holiday(cfg, d)


def next_school_day(cfg, d, include_today=False):
    x = d if include_today else d + timedelta(days=1)
    for _ in range(60):
        if is_school_day(cfg, x):
            return x
        x += timedelta(days=1)
    return None


def zaino_day(cfg, dt):
    """Oggi se c'è scuola e non è ancora finita, altrimenti il prossimo giorno di scuola."""
    today = dt.date()
    if is_school_day(cfg, today):
        ex = hm(cfg["timetable"][WEEKDAYS[today.weekday()]].get("exit")) or 24 * 60
        if dt.hour * 60 + dt.minute < ex:
            return today
    return next_school_day(cfg, today)


def subjects_by_id(cfg):
    return {s["id"]: s for s in cfg["subjects"]}


def day_subjects(cfg, d, zaino_only=False):
    """Materie del giorno in ordine, senza doppioni (zaino_only: esclude Mensa & co.)."""
    sid = subjects_by_id(cfg)
    out, seen = [], set()
    for i in cfg["timetable"].get(WEEKDAYS[d.weekday()], {}).get("slots", []):
        if zaino_only and i in sid and sid[i].get("zaino") is False:
            continue
        if i in sid and i not in seen:
            seen.add(i)
            out.append(sid[i])
    return out


def diary_for(cfg, d, types=None):
    out = []
    for e in cfg["diary"]:
        a = _parse_d(e.get("date"))
        b = _parse_d(e.get("end_date")) or a
        if a and a <= d <= b and (types is None or e.get("type") in types):
            out.append(e)
    return out


def zaino(cfg, d):
    """Contenuto dello zaino per il giorno d."""
    sid = subjects_by_id(cfg)
    subs = [{"subject": s, "materials": list(s.get("materials", []))} for s in day_subjects(cfg, d, zaino_only=True)]
    extras = list(cfg["extras"].get(WEEKDAYS[d.weekday()], []))
    notes = []
    for e in diary_for(cfg, d, {"compito", "verifica", "avviso", "gita"}):
        for item in e.get("bring", []):
            if item and item not in extras:
                extras.append(item)
        notes.append({"type": e["type"], "text": e.get("text", ""),
                      "subject": sid.get(e.get("subject_id"))})
    return {"date": d, "subjects": subs, "extras": extras, "notes": notes}


# ---------------------------------------------------------------- mensa

def menu_week_index(cfg, d):
    """Indice (0..N-1) della settimana di menù in cui cade la data d."""
    m = cfg.get("mensa") or {}
    n = len(m.get("weeks") or [])
    if not n:
        return 0
    try:
        w1 = date.fromisoformat(m.get("week1") or "")
    except ValueError:
        return 0
    w1 = w1 - timedelta(days=w1.weekday())
    mon = d - timedelta(days=d.weekday())
    return ((mon - w1).days // 7) % n


def menu_for(cfg, d):
    """Piatti del giorno d (lista di stringhe), [] se niente mensa quel giorno."""
    m = cfg.get("mensa") or {}
    if not m.get("enabled") or d.weekday() > 4 or not is_school_day(cfg, d):
        return []
    weeks = m.get("weeks") or []
    if not weeks:
        return []
    days = weeks[menu_week_index(cfg, d)]
    return [x for x in (days[d.weekday()] if d.weekday() < len(days) else []) if x.strip()]


def is_near(d, today):
    """Oggi o domani."""
    return 0 <= (d - today).days <= 1


def label_day(d, today):
    delta = (d - today).days
    if delta == 0:
        return t("display.today")
    if delta == 1:
        return t("display.tomorrow")
    return t("display.other_day", weekday=t("display.days")[d.weekday()], day=d.day)


# ---------------------------------------------------------------- iCal

_ical_cache = {}  # url -> (ts, bytes)


def _fetch_ical(url):
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    hit = _ical_cache.get(url)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    r = httpx.get(url, timeout=15, follow_redirects=True)
    r.raise_for_status()
    _ical_cache[url] = (time.time(), r.content)
    return r.content


def events(cfg, start, days):
    """Eventi da tutti i calendari attivi tra start (date) e start+days."""
    import icalendar
    import recurring_ical_events

    z = tz(cfg)
    if DEMO:
        return _demo_events(start, z), []
    a = datetime.combine(start, datetime.min.time(), z)
    b = a + timedelta(days=days)
    out, errors = [], []
    for c in cfg.get("calendars", []):
        if not c.get("enabled", True) or not c.get("url"):
            continue
        try:
            cal = icalendar.Calendar.from_ical(_fetch_ical(c["url"]))
            for ev in recurring_ical_events.of(cal).between(a, b):
                s = ev.get("DTSTART").dt
                all_day = not isinstance(s, datetime)
                if ev.get("DTEND"):
                    e = ev.get("DTEND").dt
                elif ev.get("DURATION"):
                    e = s + ev.get("DURATION").dt
                else:  # RFC 5545: senza fine, un evento di un giorno dura tutto il giorno
                    e = s + timedelta(days=1) if all_day else s
                if all_day:
                    s_dt = datetime.combine(s, datetime.min.time(), z)
                    e_dt = datetime.combine(e, datetime.min.time(), z)
                else:
                    s_dt = s.astimezone(z) if s.tzinfo else s.replace(tzinfo=z)
                    e_dt = e.astimezone(z) if e.tzinfo else e.replace(tzinfo=z)
                out.append({"title": str(ev.get("SUMMARY", "")).strip(), "start": s_dt, "end": e_dt,
                            "all_day": all_day, "calendar": c.get("name", "")})
        except Exception as ex:  # un calendario rotto non blocca gli altri
            errors.append(f"{c.get('name', c['url'])}: {ex}")
    out.sort(key=lambda x: (x["start"], not x["all_day"]))
    return out, errors


# ---------------------------------------------------------------- meteo

_weather_cache = {"ts": 0, "key": None, "data": None}

# WMO weather code -> (icona, chiave della descrizione in lang/*.json -> display.weather)
WMO = {
    0: ("sole", "sereno"), 1: ("sole", "poco_nuvoloso"), 2: ("sole_nuvola", "parz_nuvoloso"),
    3: ("nuvola", "nuvoloso"), 45: ("nebbia", "nebbia"), 48: ("nebbia", "nebbia"),
    51: ("pioggia", "pioviggine"), 53: ("pioggia", "pioviggine"), 55: ("pioggia", "pioviggine"),
    56: ("pioggia", "pioggia_gelata"), 57: ("pioggia", "pioggia_gelata"),
    61: ("pioggia", "pioggia_debole"), 63: ("pioggia", "pioggia"), 65: ("pioggia", "pioggia_forte"),
    66: ("pioggia", "pioggia_gelata"), 67: ("pioggia", "pioggia_gelata"),
    71: ("neve", "neve_debole"), 73: ("neve", "neve"), 75: ("neve", "neve_forte"), 77: ("neve", "nevischio"),
    80: ("pioggia", "rovesci"), 81: ("pioggia", "rovesci"), 82: ("pioggia", "rovesci_forti"),
    85: ("neve", "neve"), 86: ("neve", "neve"),
    95: ("temporale", "temporale"), 96: ("temporale", "temporale"), 99: ("temporale", "temporale"),
}


def wmo(code):
    """(icona, descrizione nella lingua corrente)."""
    icon, key = WMO.get(int(code or 0), ("nuvola", "sconosciuto"))
    return icon, t("display.weather")[key]


def weather_configured(cfg):
    s = cfg["settings"]
    try:
        return not (float(s.get("lat") or 0) == 0 and float(s.get("lon") or 0) == 0)
    except (TypeError, ValueError):
        return False


def geocode(q):
    """Cerca una località per nome (Open-Meteo geocoding)."""
    r = httpx.get("https://geocoding-api.open-meteo.com/v1/search", timeout=10,
                  params={"name": q, "count": 6, "language": "it", "format": "json"})
    r.raise_for_status()
    return [{"name": x.get("name"), "admin": x.get("admin1") or "", "country": x.get("country") or "",
             "lat": round(x["latitude"], 3), "lon": round(x["longitude"], 3)}
            for x in r.json().get("results", [])]


def weather(cfg):
    s = cfg["settings"]
    if DEMO:
        return _demo_weather(now(cfg).date())
    if not weather_configured(cfg):
        return {"ok": False, "reason": "località non impostata"}
    key = (s.get("lat"), s.get("lon"))
    if _weather_cache["data"] and _weather_cache["key"] == key and time.time() - _weather_cache["ts"] < 1800:
        return _weather_cache["data"]
    try:
        r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
            "latitude": s["lat"], "longitude": s["lon"],
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": s.get("timezone") or "Europe/Rome", "forecast_days": 5,
        })
        r.raise_for_status()
        j = r.json()
        dly = j["daily"]
        data = {
            "ok": True,
            "temp": round(j["current"]["temperature_2m"]),
            "code": j["current"]["weather_code"],
            "days": [{
                "date": date.fromisoformat(dly["time"][i]),
                "code": dly["weather_code"][i],
                "max": round(dly["temperature_2m_max"][i]),
                "min": round(dly["temperature_2m_min"][i]),
                "rain": dly["precipitation_probability_max"][i] or 0,
            } for i in range(len(dly["time"]))],
        }
        _weather_cache.update(ts=time.time(), key=key, data=data)
        return data
    except Exception:
        return _weather_cache["data"] or {"ok": False}


def weather_tip(w, today):
    """Consiglio pratico per il bambino, dal meteo di oggi e domani: (tipo, testo1, testo2)."""
    if not w.get("ok"):
        return None
    tips = t("display.tips")

    def tip(kind, when=""):
        a, b = tips[kind]
        return kind, a, b.format(when=when)

    days = {d["date"]: d for d in w["days"]}
    for d, lab in ((today, t("display.today")), (today + timedelta(days=1), t("display.tomorrow"))):
        x = days.get(d)
        if not x:
            continue
        icon = wmo(x["code"])[0]
        if icon == "neve":
            return tip("snow", lab)
        if icon in ("pioggia", "temporale") or x["rain"] >= 50:
            return tip("rain", lab)
    x = days.get(today)
    if x and x["min"] <= 5:
        return tip("cold")
    if x and x["max"] >= 28:
        return tip("hot")
    return None


# ---------------------------------------------------------------- demo

def _demo_events(start, z):
    def at(days, h, m, title, dur=60, all_day=False):
        d0 = start + timedelta(days=days)
        s = datetime(d0.year, d0.month, d0.day, 0 if all_day else h, 0 if all_day else m, tzinfo=z)
        return {"title": title, "start": s, "end": s + timedelta(days=1) if all_day else s + timedelta(minutes=dur),
                "all_day": all_day, "calendar": "Demo"}
    ev = t("demo.events")
    return [at(0, 17, 0, ev[0]), at(1, 16, 30, ev[1]), at(2, 0, 0, ev[2], all_day=True), at(4, 10, 0, ev[3])]


def _demo_weather(today):
    rows = [(2, 21, 12, 10), (61, 17, 11, 80), (0, 20, 10, 0), (3, 19, 11, 20), (1, 22, 12, 5)]
    return {"ok": True, "temp": 16, "code": 2, "days": [
        {"date": today + timedelta(days=i), "code": c, "max": mx, "min": mn, "rain": r}
        for i, (c, mx, mn, r) in enumerate(rows)]}
