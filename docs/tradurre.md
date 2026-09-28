# Tradurre Zaino · Translating Zaino

Tutti i testi del display e della web app stanno in un file per lingua, in `server/app/lang/`. Per aggiungere una lingua non serve toccare il codice.

*All the text of the display and of the web app lives in one file per language, in `server/app/lang/`. Adding a language needs no code changes.*

## Passi · Steps

1. Fai un fork del repository. *Fork the repository.*
2. Copia `server/app/lang/en.json` in un file con il codice della tua lingua, per esempio `fr.json`, `de.json` o `es.json`. *Copy `en.json` to a file named with your language code.*
3. In cima al file cambia `_name` (il nome della lingua, scritto nella lingua stessa: `Français`), `_locale` (per date e orari: `fr-FR`) e metti il tuo nome in `_translators`. *At the top, set `_name`, `_locale` and your name in `_translators`.*
4. Traduci solo i **valori**, mai le chiavi a sinistra. *Translate the values only, never the keys.*
5. Prova in locale (vedi sotto), poi apri una pull request. *Test locally, then open a pull request.*

## Regole · Rules

- **Segnaposto:** le parole tra graffe (`{name}`, `{n}`, `{when}`…) vanno lasciate così, anche spostate nella frase. *Keep placeholders such as `{name}` untouched; you may move them.*
- **Liste:** `days` ha 7 voci da lunedì a domenica, `months_abbr` 12, `week_letters` 7 lettere. *Keep list lengths.*
- **Spazio sul display:** lo schermo è 400×300 pixel. Tieni corti soprattutto i titoli (`zaino_title`, `mensa_title`, `meteo_title`), le sigle dei giorni e dei mesi e gli avvisi del meteo. Se un testo è troppo lungo viene tagliato con «…». *The screen is tiny: keep titles, abbreviations and weather tips short.*
- **Ordine delle parole:** `note_with_subject` decide come si compone «Verifica di matematica». Hai a disposizione `{type}`, `{type_lower}`, `{subject}` e `{subject_lower}`: in inglese è `{subject} {type_lower}` («Maths test»). *Use the placeholders to fit your grammar.*
- **Materie di esempio** (`seed`): servono solo alle nuove installazioni avviate con `ZAINO_LANG`. Vanno adattate alla scuola del tuo paese, mantenendo 10 voci. *Example subjects for new installs: adapt them to your country, keep 10 entries.*
- **Chiavi mancanti:** se lasci fuori una chiave, compare il testo italiano. Una traduzione parziale funziona, ma è meglio completa. *Missing keys fall back to Italian.*

## Provare in locale · Test locally

```bash
cd server
pip install -r requirements.txt
cd app && DATA_DIR=../data-test ZAINO_DEMO=1 ZAINO_LANG=fr uvicorn main:app --port 3021
```

Apri `http://localhost:3021/admin` e controlla tutte le schede e, nella scheda *Schermo*, tutte le pagine del display. *Open the web app and check every tab and every display page in the Screen tab.*

Grazie! · *Thank you!*
