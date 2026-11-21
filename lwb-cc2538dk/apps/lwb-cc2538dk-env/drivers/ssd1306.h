#ifndef SSD1306_H_
#define SSD1306_H_

#include <stdint.h>

/*
 * SSD1306 — OLED 128x64, I2C
 * Uses the configurable i2c_sw bus shared with the sensors.
 */

#define SSD1306_I2C_ADDRESS  0x3C
#define SSD1306_WIDTH        128
#define SSD1306_HEIGHT       64

/* Khởi tạo display */
void ssd1306_init(void);

/* Xóa toàn bộ buffer về 0 */
void ssd1306_clear(void);

/* Đẩy buffer lên màn hình */
void ssd1306_display(void);

/* Vẽ ký tự tại (x, y); size=1 → 6x8 pixel mỗi ký tự */
void ssd1306_draw_char(uint8_t x, uint8_t y, char c, uint8_t size);

/* Vẽ chuỗi */
void ssd1306_draw_text(uint8_t x, uint8_t y, const char *text, uint8_t size);

/* Vẽ 1 pixel */
void ssd1306_draw_pixel(uint8_t x, uint8_t y, uint8_t on);

/* Vẽ đường kẻ ngang (thanh separator) */
void ssd1306_draw_hline(uint8_t x, uint8_t y, uint8_t len);

#endif /* SSD1306_H_ */
