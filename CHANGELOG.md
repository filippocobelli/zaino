# Changelog

## 1.3 — prima versione pubblica

- Licenza GNU GPL v3.0 o successiva; avvisi delle licenze di terze parti in `THIRD_PARTY_NOTICES.md`.
- Testi del display e della web app in file di lingua (`server/app/lang/*.json`), con la scelta della lingua nelle Impostazioni.
- Inglese completo, italiano come riferimento; le chiavi mancanti in una traduzione ricadono sull'italiano.
- `ZAINO_LANG` sceglie la lingua (e le materie di esempio) di una nuova installazione.
- Pagina Zaino: l'intestazione si adatta alla lunghezza dei testi (rimpicciolisce la data, poi toglie il giorno della settimana).
- Guida per chi vuole tradurre: `docs/tradurre.md`.

## 1.2

**Server**
- Pagine: Oggi, Zaino, Mensa, Meteo, Settimana, Riposo (400×300, 4 colori).
- Programma della giornata: pagina per fascia oraria e tipo di giorno (scuola, sera prima di scuola, senza scuola, sempre).
- Pagine attivabili e ordinabili; tempo di visione dopo un tasto configurabile.
- Mensa con menù a rotazione su più settimane; pranzo nella pagina di oggi.
- Colore d'accento del display e della web app (rosso, nero, giallo), per distinguere i display di più figli.
- Nome del colore accanto alle materie rese con righe o puntini (blu, verde, viola…).
- Appuntamenti iCal nella pagina di oggi e sotto l'orario settimanale.
- Avvisi meteo: ombrello o impermeabile, neve, freddo, caldo.
- Galleria di immagini a riposo con rotazione giornaliera.
- Ricerca della località del meteo per nome; modalità demo (`ZAINO_DEMO=1`).
- Web app installabile sulla schermata Home.
- Sonno calcolato correttamente al cambio dell'ora legale; orari non validi nella configurazione ignorati invece di bloccare il display; data di default del diario nel fuso locale.

**Firmware**
- Thin client ESP-IDF 5.4: risveglio a orario o col tasto, download della pagina solo se cambiata (ETag), deep sleep.
- Pagine scorse col tasto frontale nell'ordine deciso dal server (`/device/nav/<n>.bin`).
- Tempo di visione dopo un tasto indicato dal server.
- Credenziali Wi-Fi riprese dal firmware di riferimento ZECTRIX.
