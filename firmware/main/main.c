// SPDX-License-Identifier: GPL-3.0-or-later
// Zaino — firmware thin client per ZECTRIX NOTE4C.
// Ciclo: risveglio (timer o tasto) -> Wi-Fi -> GET pagina dal server -> refresh se cambiata -> deep sleep.
//  - timer / accensione: /device/current.bin con If-None-Match (304 = niente refresh)
//  - tasto BOOT (frontale): pagina successiva nell'ordine deciso dal server (/device/nav/<n>.bin);
//    resta visibile per il tempo deciso dal server (X-Sleep-Seconds), poi torna automatica
//  - tasto Giù: torna subito alla pagina automatica
// Credenziali Wi-Fi: lette da NVS namespace "wifi" (chiavi ssid/password), le stesse
// salvate dal firmware di riferimento.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/rtc_io.h"
#include "epd.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sleep.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#define PIN_PWR_HOLD GPIO_NUM_17
#define PIN_BTN_BOOT GPIO_NUM_0
#define PIN_BTN_DOWN GPIO_NUM_18
#define PIN_LED      GPIO_NUM_3

static const char *TAG = "zaino";

RTC_DATA_ATTR static char s_etag[48];
RTC_DATA_ATTR static int s_page = -1;   // -1 = automatica, altrimenti indice nell'ordine del server
RTC_DATA_ATTR static int s_npages = 5;  // aggiornato dall'header X-Page-Count
RTC_DATA_ATTR static uint32_t s_boots;

static EventGroupHandle_t s_wifi_ev;
#define WIFI_OK BIT0
#define WIFI_FAIL BIT1

// ------------------------------------------------------------- alimentazione

static void hold_power(void) {
    // GPIO17 tiene acceso il circuito della batteria: deve restare alto anche in deep sleep
    gpio_hold_dis(PIN_PWR_HOLD);
    gpio_set_direction(PIN_PWR_HOLD, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_PWR_HOLD, 1);
    gpio_hold_en(PIN_PWR_HOLD);
}

static void led(int on) {
    gpio_hold_dis(PIN_LED);
    gpio_set_direction(PIN_LED, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_LED, on ? 0 : 1);  // LED attivo basso
    gpio_hold_en(PIN_LED);
}

static int battery_mv(void) {
    adc_oneshot_unit_handle_t adc;
    adc_oneshot_unit_init_cfg_t ucfg = {.unit_id = ADC_UNIT_1};
    if (adc_oneshot_new_unit(&ucfg, &adc) != ESP_OK) return 0;
    adc_oneshot_chan_cfg_t ccfg = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_12};
    adc_oneshot_config_channel(adc, ADC_CHANNEL_3, &ccfg);  // GPIO4
    adc_cali_handle_t cali = NULL;
    adc_cali_curve_fitting_config_t cc = {.unit_id = ADC_UNIT_1, .chan = ADC_CHANNEL_3,
                                          .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_12};
    adc_cali_create_scheme_curve_fitting(&cc, &cali);
    int sum = 0, n = 0;
    for (int i = 0; i < 8; i++) {
        int raw = 0, mv = 0;
        if (adc_oneshot_read(adc, ADC_CHANNEL_3, &raw) == ESP_OK && cali &&
            adc_cali_raw_to_voltage(cali, raw, &mv) == ESP_OK) {
            sum += mv;
            n++;
        }
    }
    if (cali) adc_cali_delete_scheme_curve_fitting(cali);
    adc_oneshot_del_unit(adc);
    return n ? (sum / n) * 2 : 0;  // partitore 1:2
}

// ------------------------------------------------------------- Wi-Fi

static void wifi_evt(void *arg, esp_event_base_t base, int32_t id, void *data) {
    static int retries = 0;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        if (++retries <= 3) {
            esp_wifi_connect();
        } else {
            xEventGroupSetBits(s_wifi_ev, WIFI_FAIL);
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(s_wifi_ev, WIFI_OK);
    }
}

static bool wifi_connect(void) {
    nvs_handle_t h;
    char ssid[33] = {0}, pass[65] = {0};
    size_t l1 = sizeof(ssid), l2 = sizeof(pass);
    if (nvs_open("wifi", NVS_READONLY, &h) != ESP_OK) {
        ESP_LOGE(TAG, "nessuna rete Wi-Fi salvata (namespace wifi assente)");
        return false;
    }
    esp_err_t e1 = nvs_get_str(h, "ssid", ssid, &l1);
    esp_err_t e2 = nvs_get_str(h, "password", pass, &l2);
    nvs_close(h);
    if (e1 != ESP_OK) {
        ESP_LOGE(TAG, "SSID non trovato in NVS");
        return false;
    }
    if (e2 != ESP_OK) pass[0] = 0;
    ESP_LOGI(TAG, "connessione a %s", ssid);

    s_wifi_ev = xEventGroupCreate();
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_evt, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_evt, NULL);
    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, pass, sizeof(wc.sta.password));
    wc.sta.threshold.authmode = pass[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    wc.sta.scan_method = WIFI_FAST_SCAN;
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wc);
    esp_wifi_start();
    EventBits_t b = xEventGroupWaitBits(s_wifi_ev, WIFI_OK | WIFI_FAIL, pdFALSE, pdFALSE, pdMS_TO_TICKS(20000));
    return (b & WIFI_OK) != 0;
}

static void wifi_off(void) {
    esp_wifi_disconnect();
    esp_wifi_stop();
}

// ------------------------------------------------------------- HTTP

typedef struct {
    uint8_t *buf;
    int len;
    char etag[48];
    int sleep_s;
    int npages;
} fetch_t;

static esp_err_t http_evt(esp_http_client_event_t *e) {
    fetch_t *f = (fetch_t *)e->user_data;
    if (e->event_id == HTTP_EVENT_ON_HEADER) {
        if (strcasecmp(e->header_key, "ETag") == 0) {
            const char *v = e->header_value;
            if (*v == '"') v++;
            strlcpy(f->etag, v, sizeof(f->etag));
            char *q = strchr(f->etag, '"');
            if (q) *q = 0;
        } else if (strcasecmp(e->header_key, "X-Sleep-Seconds") == 0) {
            f->sleep_s = atoi(e->header_value);
        } else if (strcasecmp(e->header_key, "X-Page-Count") == 0) {
            f->npages = atoi(e->header_value);
        }
    } else if (e->event_id == HTTP_EVENT_ON_DATA && e->data_len > 0) {
        int room = EPD_FB_BYTES - f->len;
        int n = e->data_len < room ? e->data_len : room;
        if (n > 0) {
            memcpy(f->buf + f->len, e->data, n);
            f->len += n;
        }
    }
    return ESP_OK;
}

// ritorna lo status HTTP (200, 304, ...) o -1
static int fetch(const char *path, int mv, bool conditional, fetch_t *f) {
    char url[160];
    snprintf(url, sizeof(url), "%s%s?battery_mv=%d", CONFIG_ZAINO_SERVER_URL, path, mv);
    esp_http_client_config_t cfg = {
        .url = url, .event_handler = http_evt, .user_data = f,
        .timeout_ms = 20000, .buffer_size = 2048,
    };
    esp_http_client_handle_t c = esp_http_client_init(&cfg);
    if (conditional && s_etag[0]) {
        char v[56];
        snprintf(v, sizeof(v), "\"%s\"", s_etag);
        esp_http_client_set_header(c, "If-None-Match", v);
    }
    esp_err_t err = esp_http_client_perform(c);
    int status = err == ESP_OK ? esp_http_client_get_status_code(c) : -1;
    esp_http_client_cleanup(c);
    ESP_LOGI(TAG, "GET %s -> %d, %d byte, sleep %d s", url, status, f->len, f->sleep_s);
    return status;
}

// ------------------------------------------------------------- sleep

static void go_sleep(int seconds) {
    if (seconds < 60) seconds = 60;
    // il timer RC interno può sbagliare di qualche %: niente sonni lunghi, il server
    // ricalcola comunque il tempo che manca al prossimo orario
    if (seconds > CONFIG_ZAINO_MAX_SLEEP_SECONDS) seconds = CONFIG_ZAINO_MAX_SLEEP_SECONDS;
    ESP_LOGI(TAG, "deep sleep per %d s", seconds);
    epd_power_off();
    led(0);
    // attende il rilascio dei tasti, altrimenti si risveglierebbe subito
    for (int i = 0; i < 100 && (gpio_get_level(PIN_BTN_BOOT) == 0 || gpio_get_level(PIN_BTN_DOWN) == 0); i++) {
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    rtc_gpio_pullup_en(PIN_BTN_BOOT);
    rtc_gpio_pulldown_dis(PIN_BTN_BOOT);
    rtc_gpio_pullup_en(PIN_BTN_DOWN);
    rtc_gpio_pulldown_dis(PIN_BTN_DOWN);
    esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
    esp_sleep_enable_ext1_wakeup_io((1ULL << PIN_BTN_BOOT) | (1ULL << PIN_BTN_DOWN), ESP_EXT1_WAKEUP_ANY_LOW);
    esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
    gpio_deep_sleep_hold_en();
    esp_deep_sleep_start();
}

// ------------------------------------------------------------- main

void app_main(void) {
    hold_power();
    s_boots++;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();

    // accensione a freddo col tasto Giù/Power: aspetta il rilascio (max 3 s)
    if (cause == ESP_SLEEP_WAKEUP_UNDEFINED) {
        gpio_set_direction(PIN_BTN_DOWN, GPIO_MODE_INPUT);
        for (int i = 0; i < 150 && gpio_get_level(PIN_BTN_DOWN) == 0; i++) vTaskDelay(pdMS_TO_TICKS(20));
        s_etag[0] = 0;
        s_page = -1;
    }

    bool conditional = true;
    if (cause == ESP_SLEEP_WAKEUP_EXT1) {
        uint64_t pins = esp_sleep_get_ext1_wakeup_status();
        if (pins & (1ULL << PIN_BTN_BOOT)) {
            s_page = (s_page + 1) % (s_npages > 0 ? s_npages : 1);  // da automatica (-1) parte dalla prima
            conditional = false;
        } else {
            s_page = -1;  // Giù: pagina automatica
            s_etag[0] = 0;
        }
    } else if (cause == ESP_SLEEP_WAKEUP_TIMER) {
        s_page = -1;  // allo scadere torna sempre alla pagina automatica
    }
    ESP_LOGI(TAG, "risveglio %d, causa %d, pagina %d", (int)s_boots, (int)cause, s_page);
    led(1);

    esp_err_t r = nvs_flash_init();
    if (r != ESP_OK) {
        // non cancelliamo la NVS: conterrebbe le credenziali Wi-Fi
        ESP_LOGE(TAG, "NVS non inizializzabile: %s", esp_err_to_name(r));
        go_sleep(CONFIG_ZAINO_RETRY_SECONDS);
    }

    int mv = battery_mv();
    ESP_LOGI(TAG, "batteria %d mV", mv);

    if (!wifi_connect()) {
        ESP_LOGE(TAG, "Wi-Fi non disponibile");
        wifi_off();
        go_sleep(CONFIG_ZAINO_RETRY_SECONDS);
    }

    fetch_t f = {.buf = malloc(EPD_FB_BYTES), .len = 0, .etag = "", .sleep_s = 0, .npages = 0};
    char path[48];
    if (s_page < 0) {
        strcpy(path, "/device/current.bin");
    } else {
        snprintf(path, sizeof(path), "/device/nav/%d.bin", s_page);
    }
    int status = f.buf ? fetch(path, mv, conditional && s_page < 0, &f) : -1;
    wifi_off();
    if (f.npages > 0) {
        s_npages = f.npages;
        if (s_page >= s_npages) s_page = 0;
    }

    int sleep_s = f.sleep_s > 0 ? f.sleep_s : CONFIG_ZAINO_RETRY_SECONDS;
    if (status == 200 && f.len == EPD_FB_BYTES) {
        epd_show(f.buf);
        if (s_page < 0) {
            strlcpy(s_etag, f.etag, sizeof(s_etag));
        } else {
            s_etag[0] = 0;  // al ritorno in automatico ridisegna sempre
            // il server manda il tempo di visione scelto nella web app; se manca, default del firmware
            if (f.sleep_s <= 0) sleep_s = CONFIG_ZAINO_BUTTON_PAGE_SECONDS;
        }
    } else if (status == 304) {
        ESP_LOGI(TAG, "contenuto invariato, nessun refresh");
    } else {
        ESP_LOGE(TAG, "risposta non valida (%d, %d byte)", status, f.len);
        sleep_s = CONFIG_ZAINO_RETRY_SECONDS;
    }
    free(f.buf);
    go_sleep(sleep_s);
}
