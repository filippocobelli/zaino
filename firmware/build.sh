#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Compila il firmware Zaino con l'indirizzo del tuo server, usando l'immagine Docker ufficiale di ESP-IDF.
# Uso:  ./build.sh http://192.168.1.50:3021
# Risultato: zaino-firmware.bin (da installare all'indirizzo 0x0 con il firmware updater ZECTRIX)
set -e
URL="$1"
if [ -z "$URL" ]; then
  echo "Uso: ./build.sh http://IP-DEL-SERVER:3021"
  exit 1
fi
cd "$(dirname "$0")"
rm -rf build sdkconfig
printf 'CONFIG_ZAINO_SERVER_URL="%s"\n' "$URL" > sdkconfig.url
docker run --rm -v "$PWD":/project -w /project espressif/idf:v5.4.2 sh -c '
  idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.url" build &&
  cd build && python -m esptool --chip esp32s3 merge_bin -o ../zaino-firmware.bin @flash_args'
rm -f sdkconfig.url
echo
echo "Pronto: $(pwd)/zaino-firmware.bin  (server: $URL)"
