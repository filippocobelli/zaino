# API del server

## Per il display

| Endpoint | Descrizione |
|---|---|
| `GET /device/current.bin?battery_mv=3900` | Pagina automatica del momento. Con `If-None-Match` risponde `304` se il contenuto non è cambiato |
| `GET /device/nav/{n}.bin` | n-esima pagina attiva nell'ordine scelto (header `X-Page-Count`; `X-Sleep-Seconds` = tempo di visione impostato) |
| `GET /device/page/{home,zaino,mensa,meteo,settimana,riposo}.bin` | Pagina per nome |
| `GET /device/pages` | Pagine attive in ordine (Mensa e Riposo solo se hanno contenuti) |

Header di risposta: `ETag` (calcolato sul contenuto, senza l'orario di aggiornamento stampato), `X-Page`, `X-Sleep-Seconds` (secondi al prossimo orario di risveglio).

Pagina automatica:
- di notte, immagine a riposo (se c'è e se attivata);
- poi la prima fascia del programma che corrisponde all'ora e al tipo di giorno (`scuola`, `vigilia` = la sera prima di un giorno di scuola, `no_scuola`, `sempre`);
- altrimenti la pagina "negli altri momenti".

Programma di default: 6–13 Oggi (giorni di scuola), 13–18 Settimana (giorni di scuola), 18–21 Zaino (sera prima di scuola).

## Anteprime

`GET /preview/{auto,home,zaino,mensa,meteo,settimana,riposo}.png`: PNG 800×600 identica a ciò che vedrà il display.

## Web app

| Endpoint | Descrizione |
|---|---|
| `GET /api/lang` | Testi della web app nella lingua scelta ed elenco delle lingue disponibili |
| `GET /api/config` | Configurazione completa, stili e colori d'accento disponibili, stato del device |
| `PUT /api/{settings,subjects,timetable,extras,diary,calendars,mensa}` | Sostituisce una sezione (`settings` viene unita a quella esistente; `accent` = `rosso`, `nero` o `giallo`; `lang` = codice di un file in `server/app/lang/`) |
| `GET /api/geocode?q=Bologna` | Ricerca località per il meteo |
| `GET /api/suggest?color=%231E63C6` | Stile e-paper più vicino a un colore |
| `GET /api/swatch/{stile}.png` | Campione dello stile |
| `GET /api/calendars/test` | Eventi dei prossimi 7 giorni ed eventuali errori |
| `POST /api/riposo` | Carica un'immagine (multipart: `file`, `mode` = `cover` o `contain`) |
| `POST /api/riposo/{id}/attiva` · `DELETE /api/riposo/{id}` | Sceglie o elimina un'immagine |

Esempio, importare un orario da script:

```bash
curl -X PUT -H "Content-Type: application/json" --data @orario.json http://IP:3021/api/timetable
```

Formato della mensa: `{"enabled": true, "title": "Menù estivo", "week1": "2026-09-14", "weeks": [[["Primo", "Secondo", "Contorno"], …5 giorni], …settimane]}`, dove `week1` è il lunedì della prima settimana della rotazione.

Formato di `orario.json`: `{"lun": {"entry": "08:00", "exit": "16:00", "slots": ["<id materia>", …]}, …, "dom": {…}}`.
