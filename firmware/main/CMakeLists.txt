idf_component_register(SRCS "main.c" "epd.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_wifi esp_netif esp_event nvs_flash esp_http_client esp_adc driver esp_driver_spi esp_driver_gpio)
