# SPDX-License-Identifier: GPL-3.0-or-later
"""Disegno delle pagine 400x300 in modalità P con indici BWRY del pannello."""
import hashlib
import io
import os
from datetime import timedelta

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

import data as D
import i18n
import store
from i18n import t
from styles import DEFAULT_THEME, INK_RGB, K, PALETTE, R, THEMES, W, Y, fill_swatch, is_pattern, color_name, theme

WIDTH, HEIGHT = 400, 300
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_fonts = {}


def F(size, weight="SemiBold"):
    key = (size, weight)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, f"BarlowCondensed-{weight}.ttf"), size)
    return _fonts[key]


def canvas(bg=W):
    img = Image.new("P", (WIDTH, HEIGHT), bg)
    img.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # niente antialiasing: pixel netti sull'e-paper
    return img, d


def tw(d, s, font):
    return d.textlength(s, font=font)


def fit(d, s, font, maxw):
    if tw(d, s, font) <= maxw:
        return s
    while s and tw(d, s + "…", font) > maxw:
        s = s[:-1]
    return s.rstrip() + "…"


def text(d, xy, s, size, weight="SemiBold", fill=K, maxw=None, anchor="la"):
    f = F(size, weight)
    if maxw:
        s = fit(d, s, f, maxw)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)
    return tw(d, s, f)


def color_label(cfg, s):
    """Nome del colore vero per le materie rese con righe o puntini ("" se non serve)."""
    if not cfg["settings"].get("color_labels", True) or not is_pattern(s.get("style")):
        return ""
    if s.get("color_name"):
        return s["color_name"]
    auto = color_name(s.get("color", ""))
    return t("display.colors").get(auto, auto)


def day_name(i):
    return t("display.days")[i]


def day_abbr(i):
    return t("display.days_abbr")[i]


def mon_abbr(m):
    return t("display.months_abbr")[m - 1]


def note_label(n, sub):
    """"Verifica di matematica" / "Maths test"."""
    typ = t("display.note_types")[n["type"]]
    if not sub:
        return typ
    return t("display.note_with_subject", type=typ, type_lower=typ.lower(),
             subject=sub["name"], subject_lower=sub["name"].lower())


# ---------------------------------------------------------------- icone meteo

def _sun(d, cx, cy, r, rays=True):
    if rays:
        import math
        for i in range(8):
            a = i * math.pi / 4
            x0, y0 = cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35
            x1, y1 = cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75
            d.line([x0, y0, x1, y1], fill=Y, width=max(2, int(r / 5)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=Y)


def _cloud(d, cx, cy, s, t=None):
    t = t or max(2, int(s / 14))
    shapes = [
        ("e", cx - 0.05 * s, cy - 0.12 * s, 0.36 * s),
        ("e", cx - 0.42 * s, cy + 0.10 * s, 0.24 * s),
        ("e", cx + 0.33 * s, cy + 0.06 * s, 0.27 * s),
        ("r", cx - 0.62 * s, cy + 0.06 * s, cx + 0.58 * s, cy + 0.34 * s),
    ]
    for pad, col in ((t, K), (0, W)):
        for sh in shapes:
            if sh[0] == "e":
                _, x, y, r = sh
                d.ellipse([x - r - pad, y - r - pad, x + r + pad, y + r + pad], fill=col)
            else:
                _, x0, y0, x1, y1 = sh
                rad = (y1 - y0) / 2
                d.rounded_rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], radius=rad + pad, fill=col)


def weather_icon(d, kind, cx, cy, s):
    """Icona centrata in (cx, cy), dimensione indicativa s (px)."""
    if kind == "sole":
        _sun(d, cx, cy, s * 0.28)
    elif kind == "sole_nuvola":
        _sun(d, cx - s * 0.18, cy - s * 0.16, s * 0.2)
        _cloud(d, cx + s * 0.06, cy + s * 0.1, s * 0.62)
    elif kind == "nebbia":
        _cloud(d, cx, cy - s * 0.1, s * 0.7)
        for i in range(3):
            y = cy + s * (0.2 + i * 0.1)
            d.line([cx - s * 0.4, y, cx + s * 0.4, y], fill=K, width=max(2, int(s / 18)))
    else:
        _cloud(d, cx, cy - s * 0.08, s * 0.72)
        if kind == "pioggia":
            for i in (-1, 0, 1):
                x, y = cx + i * s * 0.22, cy + s * 0.4
                rr = max(3, s * 0.07)
                d.ellipse([x - rr, y - rr, x + rr, y + rr * 1.3], fill=K)
                d.polygon([(x - rr, y), (x + rr, y), (x, y - rr * 2.2)], fill=K)
        elif kind == "neve":
            for i in (-1, 0, 1):
                x, y, rr = cx + i * s * 0.2, cy + s * 0.36, s * 0.07
                d.line([x - rr, y, x + rr, y], fill=K, width=2)
                d.line([x, y - rr, x, y + rr], fill=K, width=2)
                d.line([x - rr * .7, y - rr * .7, x + rr * .7, y + rr * .7], fill=K, width=2)
                d.line([x - rr * .7, y + rr * .7, x + rr * .7, y - rr * .7], fill=K, width=2)
        elif kind == "temporale":
            x, y = cx, cy + s * 0.18
            pts = [(x + s * .06, y), (x - s * .1, y + s * .22), (x, y + s * .22),
                   (x - s * .06, y + s * .4), (x + s * .14, y + s * .14), (x + s * .03, y + s * .14)]
            d.polygon(pts, fill=Y, outline=K)


def umbrella(d, cx, cy, s, col=Y):
    """Ombrello stilizzato centrato in (cx, cy), larghezza s."""
    r = s / 2
    d.pieslice([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], 180, 360, fill=col)
    t = max(2, int(s / 10))
    d.line([cx, cy, cx, cy + r * 0.9], fill=col, width=t)
    d.arc([cx - r * 0.35, cy + r * 0.6, cx + t / 2, cy + r * 1.1], 0, 180, fill=col, width=t)


# ---------------------------------------------------------------- elementi comuni

def sidebar(img, d, cfg, now, w):
    A, O = T["accent"], T["on_accent"]
    d.rectangle([0, 0, 118, HEIGHT], fill=A)
    text(d, (14, 10), day_abbr(now.weekday()), 26, "SemiBold", O)
    text(d, (10, 30), str(now.day), 84, "Bold", O)
    text(d, (14, 116), mon_abbr(now.month), 26, "SemiBold", O)
    # settimana
    x = 14
    for i, l in enumerate(t("display.week_letters")[:7]):
        f = F(17, "Bold")
        if i == now.weekday():
            d.rectangle([x - 3, 150, x + 11, 170], fill=O)
            d.text((x + 4, 160), l, font=f, fill=A, anchor="mm")
        else:
            d.text((x + 4, 160), l, font=f, fill=O, anchor="mm")
        x += 14
    # meteo sintetico
    if w.get("ok"):
        kind = D.wmo(w["code"])[0]
        d.ellipse([10, 196, 58, 244], fill=W)
        weather_icon(d, kind, 34, 220, 40)
        text(d, (66, 200), f"{w['temp']}°", 38, "Bold", O)
        td = next((x for x in w.get("days", []) if x["date"] == now.date()), None)
        if td:
            text(d, (14, 250), t("display.sidebar_minmax", max=td["max"], min=td["min"]), 16, "Medium", O, maxw=100)
    wk = now.isocalendar()[1]
    text(d, (14, 270), t("display.sidebar_week", n=wk), 17, "Medium", O, maxw=100)


def footer_time(d, now, x=392, y=296):
    if not STAMP["on"]:
        return
    text(d, (x, y), t("display.updated", time=f"{now:%H:%M}"), 13, "Medium", K, anchor="rd")


def battery_warn(d, state, x, y):
    b = state.get("battery_pct")
    if b is not None and b <= 20:
        text(d, (x, y), t("display.battery_low", pct=b), 14, "Bold", R, anchor="ld")


# ---------------------------------------------------------------- pagine

def page_home(cfg, now, w, state):
    img, d = canvas()
    sidebar(img, d, cfg, now, w)
    today = now.date()
    x0, xmax = 130, 392
    maxw = xmax - x0
    y = 8
    text(d, (x0, y), t("display.home_title", day=now.day, month=mon_abbr(now.month)), 21, "Bold", R, maxw=maxw)
    y += 28

    if D.is_school_day(cfg, today):
        tt = cfg["timetable"][store.WEEKDAYS[today.weekday()]]
        text(d, (x0, y), t("display.home_school", entry=tt.get("entry", ""), exit=tt.get("exit", "")), 26, "Bold", K, maxw=maxw)
        y += 32
        sx = x0
        has_lab = False
        for s in D.day_subjects(cfg, today, zaino_only=True):
            if sx + 30 > xmax:
                break
            fill_swatch(img, (sx, y, sx + 30, y + 12), s["style"])
            text(d, (sx + 15, y + 15), (s.get("short") or s["name"][:2]).upper(), 15, "Bold", K, anchor="ma")
            lab = color_label(cfg, s)
            if lab:
                text(d, (sx + 15, y + 31), lab, 13, "Medium", K, maxw=36, anchor="ma")
                has_lab = True
            sx += 36
        y += 38 + (13 if has_lab else 0)
        menu = D.menu_for(cfg, today)
        if menu:  # pranzo di oggi sotto le materie
            lw = text(d, (x0, y), t("display.home_lunch"), 18, "Bold", R)
            for dish in menu[:2]:
                fs = 18 if tw(d, dish, F(18, "SemiBold")) <= maxw - lw else 16
                text(d, (x0 + lw, y + (18 - fs)), dish, fs, "SemiBold", K, maxw=maxw - lw)
                y += 21
            y += 4
    elif D.is_holiday(cfg, today):
        text(d, (x0, y), t("display.home_holiday"), 26, "Bold", K)
        y += 34

    for n in D.diary_for(cfg, today, {"verifica", "avviso", "gita"}):
        lab = note_label(n, D.subjects_by_id(cfg).get(n.get("subject_id")))
        text(d, (x0, y), t("display.note_line", label=lab, text=n.get("text", "")), 19, "SemiBold", R, maxw=maxw)
        y += 24

    evs, _ = D.events(cfg, today, 8)
    ev_today = [e for e in evs if e["start"].date() <= today < (e["end"] - timedelta(seconds=1)).date() + timedelta(days=1)
                and (e["all_day"] or e["end"] > now)]
    for e in ev_today[:3]:
        if y > 200:
            break
        hhmm = "" if e["all_day"] else f"{e['start']:%H:%M} "
        wt = text(d, (x0, y), hhmm, 20, "Bold", K) if hhmm else 0
        text(d, (x0 + wt, y), e["title"], 20, "SemiBold", K, maxw=maxw - wt)
        y += 25
    if y == 36:
        text(d, (x0, y), t("display.home_nothing"), 22, "Medium", K, maxw=maxw)
        y += 30

    nxt = [e for e in evs if e["start"].date() > today]
    if nxt and y < 200:
        y = max(y + 6, 176)
        e = nxt[0]
        delta = (e["start"].date() - today).days
        when = t("display.home_tomorrow") if delta == 1 else t("display.home_in_days", n=delta)
        text(d, (x0, y), t("display.home_next", when=when, day=e["start"].day, month=mon_abbr(e["start"].month)),
             19, "Bold", R, maxw=maxw)
        y += 24
        hhmm = "" if e["all_day"] else f"{e['start']:%H:%M} "
        text(d, (x0, y), hhmm + e["title"], 20, "SemiBold", K, maxw=maxw)
        y += 24
        for e2 in nxt[1:]:
            if e2["start"].date() != e["start"].date() or y > 222:
                break
            hhmm = "" if e2["all_day"] else f"{e2['start']:%H:%M} "
            text(d, (x0, y), hhmm + e2["title"], 20, "SemiBold", K, maxw=maxw)
            y += 24

    tip = D.weather_tip(w, today)
    if tip:
        f = F(19, "Bold")
        msg = fit(d, tip[1] + tip[2], f, maxw - 14)
        wt = tw(d, msg, f) + 14
        d.rectangle([x0, 250, x0 + wt, 274], fill=Y)
        text(d, (x0 + 7, 262), msg, 19, "Bold", K, anchor="lm")
    battery_warn(d, state, x0, 296)
    footer_time(d, now)
    return img


def page_zaino(cfg, now, w, state):
    img, d = canvas()
    day = D.zaino_day(cfg, now)
    d.rectangle([0, 0, WIDTH, 44], fill=T["bar"])
    tw_title = text(d, (12, 2), t("display.zaino_title"), 36, "Bold", T["on_bar"])
    if not day:
        text(d, (200, 150), t("display.no_school_ahead"), 24, "SemiBold", K, anchor="mm", maxw=380)
        return img
    z = D.zaino(cfg, day)
    wx = max(110, 12 + int(tw_title) + 12)  # icona meteo dopo il titolo, qualunque sia la lingua
    right = wx  # dove finisce il meteo: la data va nello spazio che resta

    # meteo del giorno dello zaino, tra titolo e data
    wd = next((x for x in (w.get("days") or []) if x["date"] == day), None) if w.get("ok") else None
    if wd:
        kind = D.wmo(wd["code"])[0]
        d.ellipse([wx, 3, wx + 38, 41], fill=W)
        weather_icon(d, kind, wx + 19, 20, 28)
        text(d, (wx + 44, 22), f"{wd['max']}°", 24, "Bold", T["on_bar"], anchor="lm")
        mx = wx + 44 + tw(d, f"{wd['max']}°", F(24, "Bold"))
        right = mx + 4 + text(d, (mx + 4, 25), f"{wd['min']}°", 18, "SemiBold", T["on_bar"], anchor="lm")

    # "per domani, venerdì": se non ci sta rimpicciolisce, poi toglie il giorno della settimana
    when = D.label_day(day, now.date())
    labs = [t("display.zaino_for", when=when)]
    if D.is_near(day, now.date()):
        labs.insert(0, t("display.zaino_for_near", when=when, weekday=day_name(day.weekday())))
    room = 390 - right - 10
    lab, fs = next(((l, f) for l in labs for f in (24, 20) if tw(d, l, F(f, "SemiBold")) <= room), (labs[-1], 20))
    text(d, (390, 22), lab, fs, "SemiBold", T["bar_hi"], anchor="rm", maxw=room)
    banner = None
    if wd:
        if kind in ("pioggia", "temporale") or wd.get("rain", 0) >= 50:
            banner = t("display.zaino_rain")
        elif kind == "neve":
            banner = t("display.zaino_snow")

    rows = z["subjects"]
    extra_lines = (1 if z["extras"] else 0) + len(z["notes"])
    avail = 290 - 52 - extra_lines * 26 - (32 if banner else 0)
    rh = max(24, min(40, avail // max(1, len(rows))))
    fs = 24 if rh >= 34 else 20
    y = 52
    for r in rows:
        s = r["subject"]
        fill_swatch(img, (10, y + 2, 26, y + rh - 4), s["style"])
        lab = color_label(cfg, s)
        lw = text(d, (34, y + (rh - 6) // 2 + 2), lab + " ", 15, "SemiBold", K, anchor="lm") if lab else 0
        nw = lw + text(d, (34 + lw, y + (rh - 6) // 2), s["name"], fs, "Bold", K, anchor="lm")
        mats = ", ".join(r["materials"])
        if mats:
            text(d, (34 + max(nw, 92) + 10, y + (rh - 6) // 2), mats, fs - 4, "Medium", K,
                 maxw=390 - (34 + max(nw, 92) + 10), anchor="lm")
        y += rh
    if z["extras"]:
        s = t("display.zaino_also") + ", ".join(z["extras"])
        wdt = min(380, tw(d, s, F(20, "Bold")) + 12)
        d.rectangle([10, y, 10 + wdt, y + 24], fill=Y)
        text(d, (16, y + 12), s, 20, "Bold", K, maxw=368, anchor="lm")
        y += 28
    for n in z["notes"]:
        lab2 = note_label(n, n.get("subject"))
        text(d, (12, y + 2), t("display.note_line", label=lab2, text=n["text"]), 19, "SemiBold", R, maxw=378)
        y += 26
    if banner:
        d.rounded_rectangle([8, 266, 392, 296], radius=5, fill=K)
        umbrella(d, 26, 279, 22)
        a = text(d, (44, 281), banner[0], 21, "Bold", W, anchor="lm")
        text(d, (44 + a, 281), banner[1], 21, "Bold", Y, anchor="lm", maxw=384 - 44 - a)
    return img


def page_meteo(cfg, now, w, state):
    img, d = canvas()
    if not w.get("ok"):
        msg = t("display.meteo_unavailable") if D.weather_configured(cfg) else t("display.meteo_set_location")
        text(d, (200, 150), msg, 26, "SemiBold", K, anchor="mm", maxw=380)
        footer_time(d, now)
        return img
    today = w["days"][0]
    kind, desc = D.wmo(w["code"])
    weather_icon(d, kind, 66, 78, 104)
    text(d, (122, 6), f"{w['temp']}", 118, "Bold", K)
    tx = 122 + tw(d, f"{w['temp']}", F(118, "Bold"))
    d.ellipse([tx - 2, 40, tx + 14, 56], outline=K, width=4)
    d.line([262, 12, 262, 150], fill=K, width=2)
    x = 274
    text(d, (x, 4), t("display.meteo_title"), 32, "Bold", K, maxw=120)
    text(d, (x, 34), cfg["settings"].get("city", "").upper(), 26, "Bold", R, maxw=120)
    d.line([x, 68, 392, 68], fill=K, width=2)
    text(d, (x, 72), f"{day_abbr(now.weekday())} {now.day} {mon_abbr(now.month)}", 20, "SemiBold", K, maxw=120)
    text(d, (x, 96), desc.upper(), 18, "SemiBold", K, maxw=118)
    text(d, (x, 120), t("display.meteo_max"), 18, "SemiBold", K)
    text(d, (x + 27, 114), f"{today['max']}°", 28, "Bold", R)
    text(d, (x + 62, 120), t("display.meteo_min"), 18, "SemiBold", K)
    text(d, (x + 87, 114), f"{today['min']}°", 28, "Bold", K)

    bw, gap, by, bh = 124, 6, 160, 100
    for i, dd in enumerate(w["days"][1:4]):
        bx = 8 + i * (bw + gap)
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, outline=K, width=2)
        wkend = dd["date"].weekday() >= 5
        text(d, (bx + 8, by + 4), day_abbr(dd["date"].weekday()), 22, "Bold", R if wkend else K)
        weather_icon(d, D.wmo(dd["code"])[0], bx + 32, by + 62, 46)
        text(d, (bx + bw - 8, by + 4), f"{dd['max']}°", 34, "Bold", K, anchor="ra")
        text(d, (bx + bw - 8, by + 48), t("display.meteo_max_val", v=dd["max"]), 17, "SemiBold", R, anchor="ra")
        text(d, (bx + bw - 8, by + 70), t("display.meteo_min_val", v=dd["min"]), 17, "SemiBold", K, anchor="ra")

    d.rounded_rectangle([8, 268, 392, 296], radius=5, fill=T["bar"])
    tip = D.weather_tip(w, now.date())
    if tip:
        tx0 = 20
        if tip[0] == "rain":
            umbrella(d, 26, 279, 22, T["bar_hi"])
            tx0 = 44
        a = text(d, (tx0, 282), tip[1].upper(), 20, "Bold", T["on_bar"], anchor="lm", maxw=300 - tx0)
        text(d, (tx0 + a, 282), tip[2].upper(), 20, "Bold", T["bar_hi"], anchor="lm", maxw=max(20, 310 - tx0 - a))
    if STAMP["on"]:
        text(d, (384, 282), t("display.updated", time=f"{now:%H:%M}"), 15, "Medium", T["on_bar"], anchor="rm")
    return img


def page_settimana(cfg, now, w, state):
    """Griglia come l'orario di classe: righe = ore, colonne = giorni, ore uguali unite."""
    img, d = canvas()
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:
        monday += timedelta(days=7)
    sid = D.subjects_by_id(cfg)
    days = [cfg["timetable"].get(store.WEEKDAYS[i], {}) for i in range(5)]
    nrows = max([len(x.get("slots", [])) for x in days] + [1])
    base = D.hm(next((x.get("entry") for x in days if x.get("entry")), "08:00")) or 480

    tc, hh = 34, 22                      # colonna orari, altezza intestazione
    cw = (WIDTH - tc - 2) // 5
    # striscia in basso con gli appuntamenti (oggi e prossimi giorni)
    strip = []
    if cfg["settings"].get("settimana_events", True):
        evs, _ = D.events(cfg, today, 7)
        for e in evs:
            if e["end"] <= now and not e["all_day"]:
                continue
            if e["all_day"] and e["end"].date() <= today:
                continue
            strip.append(e)
    foot = 40 if strip else 0
    rh = (HEIGHT - hh - 2 - foot) // nrows
    # intestazione
    for i in range(5):
        day = monday + timedelta(days=i)
        x = tc + i * cw
        is_today = day == today
        d.rectangle([x, 0, x + cw - 2, hh - 2], fill=T["today"] if is_today else K)
        text(d, (x + cw // 2, hh // 2 - 1), f"{day_abbr(i)} {day.day}", 17, "Bold",
             T["on_today"] if is_today else W, anchor="mm")
    # orari
    for r in range(nrows):
        y = hh + r * rh
        h0 = (base // 60) + r
        text(d, (tc - 4, y + rh // 2), f"{h0}-{h0 + 1}", 13, "SemiBold", K, anchor="rm")
        d.line([0, y, tc + 5 * cw - 1, y], fill=K, width=1)
    d.line([0, hh + nrows * rh, tc + 5 * cw - 1, hh + nrows * rh], fill=K, width=1)
    # celle (ore consecutive uguali unite)
    for i in range(5):
        day = monday + timedelta(days=i)
        x = tc + i * cw
        d.line([x - 1, hh, x - 1, hh + nrows * rh], fill=K, width=1)
        if D.is_holiday(cfg, day):
            text(d, (x + cw // 2, hh + nrows * rh // 2), t("display.week_holiday"), 17, "Bold", R, anchor="mm", maxw=cw - 6)
            continue
        slots = days[i].get("slots", [])
        r = 0
        while r < len(slots):
            span = 1
            while r + span < len(slots) and slots[r + span] == slots[r]:
                span += 1
            s = sid.get(slots[r])
            if s:
                y0, y1 = hh + r * rh, hh + (r + span) * rh
                if span > 1:  # copre le righe interne
                    d.rectangle([x, y0 + 1, x + cw - 2, y1 - 1], fill=W)
                cy = (y0 + y1) // 2
                name = s["name"].upper()
                f = F(15, "SemiBold")
                if tw(d, name, f) > cw - 6:
                    f = F(13, "SemiBold")
                has_bar = s.get("style") != "nessuno"
                ty = cy - 5 if has_bar else cy
                d.text((x + (cw - 1) // 2, ty), fit(d, name, f, cw - 5), font=f, fill=K, anchor="mm")
                if has_bar:  # linea colorata sotto il nome, come sul foglio della maestra
                    lab = color_label(cfg, s)
                    if lab:
                        lf = F(11, "SemiBold")
                        lw = int(tw(d, lab, lf)) + 3
                        bw = max(16, min(cw - 10 - lw, int(tw(d, name, f)) - lw))
                        bx = x + (cw - 1 - bw - lw) // 2 + lw
                        d.text((bx - 3, cy + 9), lab, font=lf, fill=K, anchor="rm")
                    else:
                        bw = min(cw - 12, max(30, int(tw(d, name, f))))
                        bx = x + (cw - 1 - bw) // 2
                    fill_swatch(img, (bx, cy + 6, bx + bw, cy + 13), s["style"])
            r += span
    d.line([tc + 5 * cw - 1, hh, tc + 5 * cw - 1, hh + nrows * rh], fill=K, width=1)
    if strip:
        y0 = hh + nrows * rh + 4
        d.rectangle([0, y0, WIDTH, HEIGHT], fill=T["bar"])
        x = 8
        for e in strip[:3]:
            dd = e["start"].date()
            when = t("display.week_today") if dd <= today else (
                t("display.week_tomorrow") if dd == today + timedelta(days=1)
                else f"{day_abbr(dd.weekday()).capitalize()} {dd.day}")
            hhmm = "" if e["all_day"] else f" {e['start']:%H:%M}"
            a = text(d, (x, y0 + 18), f"{when}{hhmm} ", 16, "Bold", T["bar_hi"], anchor="lm")
            b = text(d, (x + a, y0 + 18), e["title"], 16, "SemiBold", T["on_bar"], maxw=max(40, WIDTH - x - a - 8), anchor="lm")
            x += a + b + 16
            if x > WIDTH - 60:
                break
    return img


def current_riposo(cfg, now):
    """Immagine da mostrare: quella scelta, oppure una diversa ogni giorno."""
    imgs = cfg.get("riposo_images", [])
    if not imgs:
        return None
    if cfg["settings"].get("riposo_mode") == "giornaliera":
        return imgs[now.date().toordinal() % len(imgs)]["id"]
    act = cfg["settings"].get("riposo_active")
    return act if any(x["id"] == act for x in imgs) else imgs[-1]["id"]


def page_riposo(cfg, now, w, state):
    i = current_riposo(cfg, now)
    if i and os.path.exists(store.riposo_file(i)):
        img = Image.open(store.riposo_file(i))
        img.load()
        return img
    img, d = canvas()
    text(d, (200, 140), t("display.riposo_upload"), 24, "SemiBold", K, anchor="mm", maxw=380)
    return img


def page_mensa(cfg, now, w, state):
    img, d = canvas()
    m = cfg.get("mensa") or {}
    weeks = m.get("weeks") or []
    d.rectangle([0, 0, WIDTH, 40], fill=T["bar"])
    text(d, (12, 20), t("display.mensa_title"), 32, "Bold", T["on_bar"], anchor="lm")
    if not m.get("enabled") or not weeks:
        text(d, (200, 160), t("display.mensa_setup"), 24, "SemiBold", K, anchor="mm", maxw=380)
        return img
    day = D.zaino_day(cfg, now)
    if not day:
        text(d, (200, 160), t("display.no_school_ahead"), 24, "SemiBold", K, anchor="mm", maxw=380)
        return img
    wi = D.menu_week_index(cfg, day)
    title = m.get("title") or t("display.mensa_default_title")
    text(d, (390, 20), t("display.mensa_week", title=title, i=wi + 1, n=len(weeks)), 18, "SemiBold", T["bar_hi"],
         maxw=250, anchor="rm")
    # il pasto del giorno, grande
    when = D.label_day(day, now.date())
    if D.is_near(day, now.date()):
        head = t("display.mensa_head_near", when=when, weekday=day_name(day.weekday()), day=day.day)
    else:
        head = when
    text(d, (12, 48), head.upper(), 20, "Bold", R, maxw=376)
    y = 74
    menu = D.menu_for(cfg, day)
    if not menu:
        text(d, (12, y), t("display.mensa_none"), 24, "Bold", K)
        y += 32
    for i, dish in enumerate(menu[:4]):
        size, weight = ((26, "Bold") if i == 0 else (23, "SemiBold") if i < 3 else (18, "Medium"))
        text(d, (12, y), dish, size, weight, K, maxw=376)
        y += size + 5
    # la settimana, compatta
    top = max(y + 8, 186)
    d.line([8, top - 4, 392, top - 4], fill=K, width=2)
    mon = day - timedelta(days=day.weekday())
    rh = (296 - top) // 5
    for i in range(5):
        dd = mon + timedelta(days=i)
        yy = top + i * rh
        dishes = D.menu_for(cfg, dd)
        is_sel = dd == day
        if is_sel:
            d.rectangle([8, yy, 44, yy + rh - 3], fill=T["accent"])
        text(d, (26, yy + (rh - 3) // 2), day_abbr(i), 15, "Bold", T["on_accent"] if is_sel else K, anchor="mm")
        txt = " · ".join(dishes[:2]) if dishes else "—"
        text(d, (52, yy + (rh - 3) // 2), txt, 16, "SemiBold" if is_sel else "Medium", K, maxw=340, anchor="lm")
    return img


PAGES = {"home": page_home, "zaino": page_zaino, "meteo": page_meteo, "mensa": page_mensa,
         "settimana": page_settimana, "riposo": page_riposo}


STAMP = {"on": True}
T = dict(THEMES[DEFAULT_THEME])  # colore d'accento della pagina in corso (vedi render)


def render(page, cfg, now, state=None, w=None, stamp=True):
    """stamp=False omette l'orario di aggiornamento: serve a calcolare l'ETag
    sul solo contenuto, così il device non ridisegna se cambia solo l'ora."""
    w = D.weather(cfg) if w is None else w
    STAMP["on"] = stamp
    T.clear()
    T.update(theme(cfg))
    i18n.use(cfg)
    try:
        return PAGES[page](cfg, now, w, state or {})
    finally:
        STAMP["on"] = True


# ---------------------------------------------------------------- conversioni

def to_2bpp(img):
    """400x300 P (indici 0..3) -> 30000 byte, 4 pixel per byte, MSB first."""
    px = img.tobytes()
    out = bytearray(len(px) // 4)
    for i in range(0, len(px), 4):
        out[i >> 2] = ((px[i] & 3) << 6) | ((px[i + 1] & 3) << 4) | ((px[i + 2] & 3) << 2) | (px[i + 3] & 3)
    return bytes(out)


def etag(buf):
    return hashlib.sha1(buf).hexdigest()[:16]


def to_png(img, scale=2):
    rgb = img.convert("RGB")
    if scale != 1:
        rgb = rgb.resize((WIDTH * scale, HEIGHT * scale), Image.NEAREST)
    b = io.BytesIO()
    rgb.save(b, "PNG")
    return b.getvalue()


def swatch_png(style_id, w=48, h=20, scale=3):
    img, _ = canvas()
    img = img.crop((0, 0, w, h))
    fill_swatch(img, (0, 0, w, h), style_id)
    return to_png(img.resize((w * scale, h * scale), Image.NEAREST), 1)


def photo_to_bwry(raw, mode="cover"):
    """Foto qualsiasi -> 400x300 a 4 colori con Floyd-Steinberg."""
    src = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    if mode == "contain":
        src = ImageOps.pad(src, (WIDTH, HEIGHT), color=INK_RGB[W])
    else:
        src = ImageOps.fit(src, (WIDTH, HEIGHT), Image.LANCZOS)
    src = ImageEnhance.Color(src).enhance(1.4)
    src = ImageEnhance.Contrast(src).enhance(1.15)
    pal = Image.new("P", (1, 1))
    pal.putpalette(PALETTE + PALETTE[:3] * 252)
    q = src.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
    q = q.point([i if i < 4 else K for i in range(256)])  # indici fuori palette -> nero
    q.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    return q
