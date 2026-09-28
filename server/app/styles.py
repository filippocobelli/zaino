# SPDX-License-Identifier: GPL-3.0-or-later
"""Inchiostri del pannello BWRY e stili delle materie.

Codici 2bpp del firmware NOTE4C (rawdraw.h): 00=nero 01=bianco 10=giallo 11=rosso.
Le immagini vengono disegnate in modalità "P" usando direttamente questi indici.
"""
K, W, Y, R = 0, 1, 2, 3

# colori usati solo per anteprima PNG e per il dithering delle foto
INK_RGB = {K: (24, 24, 24), W: (246, 246, 240), Y: (242, 196, 0), R: (196, 36, 36)}
PALETTE = [c for i in (K, W, Y, R) for c in INK_RGB[i]]

# Colore d'accento del display, utile con più figli: si riconosce a colpo d'occhio di chi è.
# accent/on_accent: barra laterale di Oggi e giorno scelto in Mensa
# bar/on_bar/bar_hi: intestazioni di Zaino e Mensa, fascia bassa di Meteo e Settimana
# today/on_today: colonna di oggi nella Settimana
# web/on_web: colori della web app
THEMES = {
    "rosso":  {"label": "Rosso",  "accent": R, "on_accent": W, "bar": K, "on_bar": W, "bar_hi": Y,
               "today": R, "on_today": W, "web": "#C42424", "on_web": "#FAFAF7"},
    "nero":   {"label": "Nero",   "accent": K, "on_accent": W, "bar": R, "on_bar": W, "bar_hi": Y,
               "today": R, "on_today": W, "web": "#1C1C1C", "on_web": "#FAFAF7"},
    "giallo": {"label": "Giallo", "accent": Y, "on_accent": K, "bar": Y, "on_bar": K, "bar_hi": R,
               "today": Y, "on_today": K, "web": "#F2C400", "on_web": "#1C1C1C"},
}
DEFAULT_THEME = "rosso"


def theme(cfg):
    return THEMES.get((cfg.get("settings") or {}).get("accent"), THEMES[DEFAULT_THEME])


# id -> (etichetta, tipo, inchiostro1, inchiostro2, colore rappresentativo per l'abbinamento)
STYLES = {
    "rosso":        ("Rosso",              "solid",   R, None, "#C62828"),
    "giallo":       ("Giallo",             "solid",   Y, None, "#F2C300"),
    "nero":         ("Nero",               "solid",   K, None, "#1A1A1A"),
    "arancione":    ("Arancione (R+G)",    "mix",     R, Y,    "#E8791A"),
    "rosa":         ("Rosa (R+B)",         "mix",     R, W,    "#E88F96"),
    "giallo_chiaro":("Giallo chiaro (G+B)","mix",     Y, W,    "#F6E27A"),
    "grigio":       ("Grigio (N+B)",       "mix",     K, W,    "#8A8A8A"),
    "bordeaux":     ("Bordeaux (R+N)",     "mix",     R, K,    "#6E1E1E"),
    "oliva":        ("Oliva (G+N)",        "mix",     Y, K,    "#857214"),
    "righe_nere":   ("Righe nere (per blu)",   "stripes", K, W, "#2466C8"),
    "puntini_neri": ("Puntini neri (per verde)","dots",   K, W, "#3C9A48"),
    "righe_rosse":  ("Righe rosse (per viola)","stripes", R, W, "#8A3FB0"),
    "nessuno":      ("Nessun colore",      "none",    W, None, "#FFFFFF"),
}


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def is_pattern(style_id):
    """Stili che non riproducono il colore (righe, puntini): meritano il nome scritto."""
    return STYLES.get(style_id, STYLES["nero"])[1] in ("stripes", "dots")


COLOR_NAMES = [("rosso", "#D32F2F"), ("arancione", "#F28C28"), ("arancione", "#F05A1E"), ("giallo", "#F2C300"), ("verde", "#3C9A48"),
               ("verde chiaro", "#8BC34A"), ("azzurro", "#4FB3E8"), ("blu", "#1E4FC0"), ("blu scuro", "#1A237E"),
               ("viola", "#8E44AD"), ("lilla", "#B39DDB"), ("rosa", "#F06292"), ("marrone", "#7B4A26"),
               ("grigio", "#8A8A8A"), ("nero", "#1A1A1A"), ("bianco", "#FFFFFF")]


def color_name(color_hex):
    """Nome italiano del colore più vicino."""
    try:
        r, g, b = _hex(color_hex)
    except Exception:
        return ""
    best, bd = "", 1e18
    for name, rep in COLOR_NAMES:
        r2, g2, b2 = _hex(rep)
        rm = (r + r2) / 2
        dist = (2 + rm / 256) * (r - r2) ** 2 + 4 * (g - g2) ** 2 + (2 + (255 - rm) / 256) * (b - b2) ** 2
        if dist < bd:
            best, bd = name, dist
    return best


def suggest_style(color_hex):
    """Stile e-paper più vicino al colore reale (distanza RGB pesata)."""
    try:
        r, g, b = _hex(color_hex)
    except Exception:
        return "nero"
    best, bd = "nero", 1e18
    for sid, (_, _, _, _, rep) in STYLES.items():
        r2, g2, b2 = _hex(rep)
        rm = (r + r2) / 2
        d = (2 + rm / 256) * (r - r2) ** 2 + 4 * (g - g2) ** 2 + (2 + (255 - rm) / 256) * (b - b2) ** 2
        if d < bd:
            best, bd = sid, d
    return best


def fill_swatch(img, box, style_id, outline=True):
    """Riempie un rettangolo con lo stile (pixel per pixel, niente antialiasing)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    label, kind, a, b, _ = STYLES.get(style_id, STYLES["nero"])
    px = img.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            if kind == "solid":
                c = a
            elif kind == "mix":
                c = a if (x + y) % 2 == 0 else b
            elif kind == "none":
                c = W
            elif kind == "stripes":
                c = a if (x + y) % 4 < 2 else b
            else:  # dots
                c = a if (x % 3 == 0 and y % 3 == 0) or (x % 3 == 1 and y % 3 == 1) else b
            px[x, y] = c
    if outline and kind != "solid":
        from PIL import ImageDraw
        ImageDraw.Draw(img).rectangle([x0, y0, x1 - 1, y1 - 1], outline=K)
