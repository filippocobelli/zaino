# Firmware

Firmware "thin client" in C per ESP-IDF 5.4. Il display non disegna nulla da solo: scarica dal server un'immagine già pronta e la manda al pannello.

## Ciclo di funzionamento

1. Risveglio: timer, tasto frontale (GPIO0) o tasto Giù (GPIO18), oppure accensione.
2. Lettura della batteria (ADC1 canale 3, GPIO4, partitore 1:2).
3. Wi-Fi con le credenziali in NVS (namespace `wifi`, chiavi `ssid` e `password`, come il firmware di riferimento).
4. Richiesta HTTP al server:
   - timer o accensione: `GET /device/current.bin?battery_mv=…` con `If-None-Match` (l'ETag è conservato in RTC memory);
   - tasto frontale: `GET /device/nav/<n>.bin`, pagina successiva nell'ordine deciso dal server (l'header `X-Page-Count` dice quante sono);
   - tasto Giù: pagina automatica senza ETag, cioè ridisegno forzato.
5. Se la risposta è `200` con 30000 byte: Wi-Fi spento, refresh del pannello. Se è `304`: nessun refresh.
6. Deep sleep per `X-Sleep-Seconds` (limitato a 3600 s perché il timer RC interno deriva; dopo un tasto è il tempo di visione scelto nella web app). In caso di errore riprova dopo 900 s.

L'alimentazione della batteria resta agganciata durante il sonno tenendo alto GPIO17 (`gpio_hold_en` + `gpio_deep_sleep_hold_en`).

## Formato dell'immagine

400×300 pixel, 2 bit per pixel, 4 pixel per byte con il più significativo a sinistra, righe da 100 byte: 30000 byte in tutto.

| Bit | Colore |
|---|---|
| `00` | nero |
| `01` | bianco |
| `10` | giallo |
| `11` | rosso |

## Pin

| Funzione | GPIO |
|---|---|
| EPD alimentazione | 6 |
| EPD BUSY (basso = occupato) | 8 |
| EPD RST | 9 |
| EPD DC | 10 |
| EPD CS | 11 |
| EPD SCK | 12 |
| EPD MOSI | 13 |
| Mantenimento alimentazione batteria | 17 |
| Tasto frontale (BOOT) | 0 |
| Tasto Giù | 18 |
| LED (attivo basso) | 3 |
| Batteria (ADC1_CH3) | 4 |

Sequenza del pannello SSD2683: reset, `0xE9 0x01`, `0x10` + 30000 byte, `0x04`, `0x12 0x00`, `0x02 0x00`, `0x07 0xA5`. Ripresa dal firmware di riferimento ZECTRIX (MIT, vedi `THIRD_PARTY_NOTICES.md`).

## Opzioni (menuconfig → Zaino)

| Opzione | Default | Significato |
|---|---|---|
| `ZAINO_SERVER_URL` | `http://192.168.1.100:3021` | Indirizzo del server |
| `ZAINO_BUTTON_PAGE_SECONDS` | 180 | Dopo un tasto, secondi prima di tornare alla pagina automatica |
| `ZAINO_RETRY_SECONDS` | 900 | Attesa prima di riprovare se Wi-Fi o server non rispondono |
| `ZAINO_MAX_SLEEP_SECONDS` | 3600 | Sonno massimo in un colpo |

## Tabella delle partizioni

Identica a quella del firmware di riferimento (NVS a `0x9000`, 16 KB), così le credenziali Wi-Fi sopravvivono all'installazione se nell'updater scegli di mantenere le impostazioni.
