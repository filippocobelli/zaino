# Installazione

Tre passi: il server, la configurazione dalla web app, il firmware sul display. Tempo stimato: un'ora la prima volta.

## 1. Il server

Serve un computer sempre acceso in casa con Docker. Il server usa la porta **3021**: controlla che sia libera (`ss -tlnp | grep 3021`), altrimenti cambia la prima metà di `"3021:3021"` in `docker-compose.yml`.

### Con Docker Compose

```bash
git clone https://github.com/filippocobelli/zaino.git
cd zaino/server
docker compose up -d --build
```

I dati finiscono in `server/data/` (`config.json`, `state.json`, immagini a riposo). Per aggiornare: `git pull && docker compose up -d --build`.

### Con Portainer

*Stacks → Add stack → Repository*

- Repository URL: l'indirizzo di questo repository
- Compose path: `server/docker-compose.yml`
- Deploy

Per aggiornare: apri lo stack e usa *Pull and redeploy*.

### Docker su Proxmox

Se il container si riavvia in continuazione e il log mostra `PermissionError: [Errno 13] Permission denied` su `socketpair()`, il profilo AppArmor di Docker blocca Python. In `docker-compose.yml` togli il commento a:

```yaml
    security_opt:
      - apparmor=unconfined
```

### Verifica

Apri `http://IP-DEL-SERVER:3021/admin` dal telefono. Poi, da un computer:

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://IP-DEL-SERVER:3021/device/current.bin
```

Deve rispondere `200 30000`.

**Consiglio**: dal telefono, *Condividi → Aggiungi alla schermata Home* per avere la web app come un'app.

## 2. Configurazione

Nella web app, in quest'ordine:

1. **Impostazioni**: nome del bambino, classe, località del meteo (scrivi il nome e premi *Cerca*), lingua (italiano o inglese), colore del display (rosso, nero o giallo: con più figli, uno per ciascuno), orari in cui il display si aggiorna, orario della notte; quali pagine usare e in che ordine, per quanto restano visibili dopo un tasto; il programma della giornata (quale pagina in quale fascia oraria: giorni di scuola, sera prima di scuola, giorni senza scuola); il nome del colore accanto alle materie a righe o puntini.
2. **Materie**: per ognuna il colore usato dalla maestra; lo stile sullo schermo viene proposto da solo e si può cambiare. Aggiungi il materiale da portare, una voce per riga. Per la Mensa togli la spunta *Compare nello zaino*.
3. **Orario**: entrata, uscita e materia di ogni ora; gli extra fissi di ogni giorno (la tuta, il flauto).
4. **Diario**: compiti, verifiche, avvisi, gite e vacanze. Nei giorni di vacanza lo zaino non viene mostrato.
5. **Mensa**: dai un nome al menù, scegli quale settimana della rotazione è quella in corso e inserisci i piatti (uno per riga). Il pranzo compare nella pagina di oggi e nella pagina Mensa.
6. **Calendari**: link iCal pubblici (`webcal://…` o `https://…/*.ics`). Da iPhone: *Calendario → Calendari → (i) → Calendario pubblico → Condividi link*.
7. **Immagini**: foto per la notte, convertite a 4 colori.

La scheda **Schermo** mostra l'anteprima esatta di ogni pagina.

## 3. Il firmware

### 3.1 Backup della flash

Prima di tutto salva i 16 MB originali. Con [WebSerial ESPTool](https://jason2866.github.io/WebSerial_ESPTool/) da Chrome o Edge: *Connect*, poi *Read Flash* con offset `0x0` e dimensione `0x1000000`. Conserva il file.

Se il display non viene riconosciuto: tieni premuto il tasto frontale (BOOT), premi il foro RESET sul lato sinistro, rilascia BOOT e riprova.

### 3.2 Wi-Fi con il firmware di riferimento

Zaino legge le credenziali Wi-Fi salvate dal firmware di riferimento ZECTRIX. Quindi:

1. Installa il firmware di riferimento NOTE4C dal [firmware updater](https://zectrix.com/en/firmware-updater.html) (vedi la [guida ZECTRIX](https://wiki.zectrix.com/en/hardware/note4c/quick-start)).
2. Al primo avvio il display crea la rete `ZecTrix-XXXX`: collegati col telefono, apri `http://192.168.4.1`, scegli la rete di casa (2,4 GHz) e salva.
3. Premi RESET e verifica in *Impostazioni → Rete* che compaia un indirizzo IP.

Consiglio: nel router assegna al display un IP fisso.

### 3.3 Compilare Zaino

L'indirizzo del server è scritto nel firmware. Serve solo Docker:

```bash
cd firmware
./build.sh http://IP-DEL-SERVER:3021
```

Dopo qualche minuto trovi `firmware/zaino-firmware.bin`.

Senza Docker, con ESP-IDF 5.4 installato: scrivi l'indirizzo in `sdkconfig.defaults` (`CONFIG_ZAINO_SERVER_URL="http://…"`), poi `idf.py build` e `cd build && python -m esptool --chip esp32s3 merge_bin -o ../zaino-firmware.bin @flash_args`.

### 3.4 Installare

1. Apri il [firmware updater ZECTRIX](https://zectrix.com/en/firmware-updater.html) con Chrome o Edge.
2. *Connect device*, scegli `zaino-firmware.bin`, indirizzo `0x0000`.
3. Scegli di **mantenere le impostazioni** (lì ci sono le credenziali Wi-Fi).
4. *Install firmware*.

Dopo il riavvio, entro una ventina di secondi compare la pagina automatica. Con il cavo collegato, il log dell'updater mostra ogni passaggio (`GET … -> 200`, `refresh completato`, `deep sleep per … s`).

### Tornare indietro

Modalità download (BOOT + RESET), poi reinstalla il firmware di riferimento o il tuo backup all'indirizzo `0x0`.

## Problemi comuni

| Sintomo | Causa probabile |
|---|---|
| Lo schermo non cambia mai | Il server non è raggiungibile dal display: controlla l'indirizzo usato in `build.sh` e il firewall |
| Log: `nessuna rete Wi-Fi salvata` | Le impostazioni non sono state mantenute: ripeti il passo 3.2 e reinstalla Zaino mantenendo le impostazioni |
| Meteo assente | Località non impostata (latitudine e longitudine a 0) |
| Il container si riavvia di continuo su Proxmox | Vedi *Docker su Proxmox* |
| Gli aggiornamenti arrivano in ritardo | Il display si sveglia solo agli orari impostati: premi il tasto Giù per un aggiornamento immediato |
