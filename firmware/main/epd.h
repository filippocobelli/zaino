// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdint.h>
#define EPD_WIDTH 400
#define EPD_HEIGHT 300
#define EPD_ROW_BYTES 100
#define EPD_FB_BYTES (EPD_ROW_BYTES * EPD_HEIGHT)
void epd_show(const uint8_t *fb);
void epd_power_off(void);
