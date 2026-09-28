# Server Zaino

FastAPI + Pillow. Disegna le pagine 400×300 a 4 colori e ospita la web app di gestione.

```bash
docker compose up -d --build        # http://localhost:3021/admin
```

Sviluppo senza Docker:

```bash
pip install -r requirements.txt
cd app && DATA_DIR=../data ZAINO_DEMO=1 uvicorn main:app --reload --port 3021
```

| Variabile | Default | |
|---|---|---|
| `DATA_DIR` | `/data` | Dove salvare configurazione, stato e immagini |
| `ZAINO_DEMO` | vuoto | `1` = meteo ed eventi di esempio |
| `ZAINO_LANG` | `it` | Lingua di una nuova installazione (`it`, `en`…); poi si cambia dalla web app |
| `TZ` | `Europe/Rome` | Fuso orario del container |

Struttura di `app/`: `main.py` (API e logica del display), `render.py` (pagine), `data.py` (scuola, iCal, meteo), `styles.py` (inchiostri e stili delle materie), `store.py` (persistenza JSON), `i18n.py` e `lang/` (lingue), `static/` (web app), `fonts/`.
