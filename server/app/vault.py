# SPDX-License-Identifier: GPL-3.0-or-later
"""Segreti cifrati (per ora solo la chiave API per leggere i menù dalle foto).

I segreti stanno in DATA_DIR/secrets.enc, cifrati con Fernet (AES-128-CBC + HMAC).
La chiave di cifratura viene da:
  1. la variabile ZAINO_SECRET del container (consigliato: non sta nella cartella dati);
  2. altrimenti un file DATA_DIR/.zaino-master creato al primo uso (permessi 600).
Così config.json, le esportazioni e gli screenshot non contengono mai la chiave in chiaro.
"""
import base64
import hashlib
import json
import os
import threading

from cryptography.fernet import Fernet, InvalidToken

import store

SECRETS_PATH = os.path.join(store.DATA_DIR, "secrets.enc")
MASTER_PATH = os.path.join(store.DATA_DIR, ".zaino-master")
_lock = threading.Lock()


def _fernet():
    env = os.environ.get("ZAINO_SECRET", "")
    if env:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(env.encode()).digest()))
    if not os.path.exists(MASTER_PATH):
        os.makedirs(store.DATA_DIR, exist_ok=True)
        fd = os.open(MASTER_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
    with open(MASTER_PATH, "rb") as f:
        return Fernet(f.read().strip())


def _read():
    if not os.path.exists(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, "rb") as f:
            return json.loads(_fernet().decrypt(f.read()))
    except (InvalidToken, ValueError, OSError):
        return {}  # chiave di cifratura cambiata o file rovinato: come se non ci fosse


def _write(d):
    tmp = SECRETS_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(_fernet().encrypt(json.dumps(d).encode()))
    os.replace(tmp, SECRETS_PATH)


def get(name):
    with _lock:
        return _read().get(name, "")


def put(name, value):
    with _lock:
        d = _read()
        if value:
            d[name] = value
        else:
            d.pop(name, None)
        _write(d)
