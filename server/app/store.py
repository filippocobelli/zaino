# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistenza su file JSON (/data/config.json) con scrittura atomica."""
import json
import os
import threading
import uuid
from copy import deepcopy

DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
RIPOSO_PATH = os.path.join(DATA_DIR, "riposo.png")  # formato vecchio, migrato
RIPOSO_DIR = os.path.join(DATA_DIR, "riposo")

_lock = threading.Lock()

WEEKDAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def _sid():
    return uuid.uuid4().hex[:8]


SEED_COLORS = ["#D32F2F", "#1E63C6", "#F2C300", "#7B3F1D", "#43A047", "#F28C28", "#E57399", "#8E44AD", "#8A8A8A", "#F7E27F"]


def _seed():
    """Configurazione iniziale, nella lingua di default (ZAINO_LANG, altrimenti italiano)."""
    import i18n
    from styles import suggest_style

    seed = i18n.strings(i18n.DEFAULT)["seed"]
    names = [x[0] for x in seed["subjects"]]
    subj = [(name, col, mats) for (name, mats), col in zip(seed["subjects"], SEED_COLORS)]

    subjects = []
    ids = {}
    for name, col, mats in subj:
        i = _sid()
        ids[name] = i
        subjects.append({"id": i, "name": name, "short": name[:2].upper(),
                         "color": col, "style": suggest_style(col), "materials": mats})

    def d(*idx):  # indici nell'elenco delle materie del seed
        return [ids[names[i]] for i in idx]

    timetable = {
        "lun": {"entry": "08:00", "exit": "16:00", "slots": d(0, 0, 1, 6, 6)},
        "mar": {"entry": "08:00", "exit": "16:00", "slots": d(1, 1, 2, 8, 8)},
        "mer": {"entry": "08:00", "exit": "16:00", "slots": d(0, 0, 3, 7, 9)},
        "gio": {"entry": "08:00", "exit": "16:00", "slots": d(1, 5, 0, 4, 2)},
        "ven": {"entry": "08:00", "exit": "16:00", "slots": d(0, 1, 9, 8, 6)},
        "sab": {"entry": "", "exit": "", "slots": []},
        "dom": {"entry": "", "exit": "", "slots": []},
    }
    return {
        "settings": {
            "child_name": "",
            "class_name": seed["class_name"],
            "lang": i18n.DEFAULT,
            "city": "",
            "lat": 0.0,
            "lon": 0.0,
            "timezone": "Europe/Rome",
            "wake_times": ["06:30", "07:00", "07:30", "13:30", "17:00", "20:00"],
            "night_start": "20:30",
            "night_end": "06:30",
            "zaino_evening_from": "17:00",
            "riposo_night": True,
            "riposo_no_school": False,
            "riposo_mode": "manuale",
            "color_labels": True,
            "accent": "rosso",
            "button_hold_minutes": 3,
            "zaino_morning": True,
            "zaino_evening_to": "",
            "schedule": [
                {"from": "06:00", "to": "13:00", "page": "home", "when": "scuola"},
                {"from": "13:00", "to": "18:00", "page": "settimana", "when": "scuola"},
                {"from": "18:00", "to": "21:00", "page": "zaino", "when": "vigilia"},
            ],
            "schedule_default": "home",
            "settimana_events": True,
            "pages": [{"id": p, "on": True} for p in ("home", "zaino", "mensa", "meteo", "settimana", "riposo")],
            "riposo_active": None,
        },
        "riposo_images": [],
        "subjects": subjects,
        "timetable": timetable,
        "extras": {k: [] for k in WEEKDAYS},
        "diary": [],
        "calendars": [],
        "mensa": {"enabled": False, "title": seed["menu_title"], "week1": "", "weeks": [[[], [], [], [], []]]},
    }


def _atomic_write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load():
    with _lock:
        if not os.path.exists(CONFIG_PATH):
            cfg = _seed()
            _atomic_write(CONFIG_PATH, cfg)
            return deepcopy(cfg)
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        # completa chiavi mancanti dopo aggiornamenti
        seed = None
        for k in ("settings", "subjects", "timetable", "extras", "diary", "calendars", "riposo_images", "mensa"):
            if k not in cfg:
                seed = seed or _seed()
                cfg[k] = seed[k]
        seed_settings = _seed()["settings"] if "settings" in cfg else {}
        for k, v in seed_settings.items():
            cfg["settings"].setdefault(k, v)
        _migrate_riposo(cfg)
        return cfg


def _migrate_riposo(cfg):
    """Importa la vecchia riposo.png singola nella galleria."""
    if os.path.exists(RIPOSO_PATH):
        os.makedirs(RIPOSO_DIR, exist_ok=True)
        i = _sid()
        os.replace(RIPOSO_PATH, os.path.join(RIPOSO_DIR, i + ".png"))
        cfg["riposo_images"].append({"id": i, "name": "Immagine", "uploaded": ""})
        cfg["settings"]["riposo_active"] = i
        _atomic_write(CONFIG_PATH, cfg)


def riposo_file(i):
    return os.path.join(RIPOSO_DIR, f"{i}.png")


def save(cfg):
    with _lock:
        _atomic_write(CONFIG_PATH, cfg)


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with _lock:
        _atomic_write(STATE_PATH, state)


def new_id():
    return _sid()
