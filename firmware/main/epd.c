// SPDX-License-Identifier: GPL-3.0-or-later
// Driver minimo SSD2683 4 colori (BWRY) per ZECTRIX NOTE4C.
// Sequenza ripresa da custom_lcd_display.cc del firmware di riferimento LazyYoun
// (MIT, Copyright (c) 2026 macheng2017: vedi THIRD_PARTY_NOTICES.md).
// Formato: 2bpp, 4 pixel/byte MSB-first, 100 byte per riga; 00 nero 01 bianco 10 giallo 11 rosso.
#include "epd.h"

#include <string.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define PIN_PWR  GPIO_NUM_6
#define PIN_BUSY GPIO_NUM_8
#define PIN_RST  GPIO_NUM_9
#define PIN_DC   GPIO_NUM_10
#define PIN_CS   GPIO_NUM_11
#define PIN_SCK  GPIO_NUM_12
#define PIN_MOSI GPIO_NUM_13

static const char *TAG = "epd";
static spi_device_handle_t s_spi;

static void send(const uint8_t *buf, int len, int dc) {
    gpio_set_level(PIN_DC, dc);
    gpio_set_level(PIN_CS, 0);
    spi_transaction_t t = {.length = 8 * len, .tx_buffer = buf};
    spi_device_polling_transmit(s_spi, &t);
    gpio_set_level(PIN_CS, 1);
}

static void cmd(uint8_t c) { send(&c, 1, 0); }
static void data(uint8_t d) { send(&d, 1, 1); }

static void wait_busy(void) {
    // BUSY basso = occupato
    int64_t waited = 0;
    while (gpio_get_level(PIN_BUSY) == 0) {
        vTaskDelay(pdMS_TO_TICKS(20));
        waited += 20;
        if (waited > 120000) {
            ESP_LOGE(TAG, "timeout busy");
            return;
        }
    }
}

static void power(int on) {
    gpio_hold_dis(PIN_PWR);
    gpio_set_level(PIN_PWR, on);
    gpio_hold_en(PIN_PWR);
}

void epd_power_off(void) {
    gpio_reset_pin(PIN_PWR);
    gpio_set_direction(PIN_PWR, GPIO_MODE_OUTPUT);
    power(0);
}

static void io_init(void) {
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << PIN_PWR) | (1ULL << PIN_RST) | (1ULL << PIN_DC) | (1ULL << PIN_CS),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&out);
    gpio_config_t in = {.pin_bit_mask = 1ULL << PIN_BUSY, .mode = GPIO_MODE_INPUT};
    gpio_config(&in);
    gpio_set_level(PIN_CS, 1);

    spi_bus_config_t bus = {
        .mosi_io_num = PIN_MOSI, .miso_io_num = -1, .sclk_io_num = PIN_SCK,
        .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 4096,
    };
    spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO);
    spi_device_interface_config_t dev = {
        .clock_speed_hz = 20 * 1000 * 1000, .mode = 0, .spics_io_num = -1, .queue_size = 1,
    };
    spi_bus_add_device(SPI3_HOST, &dev, &s_spi);
}

void epd_show(const uint8_t *fb) {
    io_init();
    power(1);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(PIN_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();

    cmd(0xE9);
    data(0x01);

    cmd(0x10);  // DTM1: stream 2bpp
    wait_busy();
    for (int y = 0; y < EPD_HEIGHT; y++) {
        send(fb + y * EPD_ROW_BYTES, EPD_ROW_BYTES, 1);
    }

    cmd(0x04);  // power on
    wait_busy();
    vTaskDelay(pdMS_TO_TICKS(10));
    cmd(0x12);  // refresh
    data(0x00);
    vTaskDelay(pdMS_TO_TICKS(10));
    wait_busy();
    cmd(0x02);  // power off
    data(0x00);
    wait_busy();
    vTaskDelay(pdMS_TO_TICKS(20));
    cmd(0x07);  // deep sleep pannello
    data(0xA5);
    power(0);
    ESP_LOGI(TAG, "refresh completato");
}
