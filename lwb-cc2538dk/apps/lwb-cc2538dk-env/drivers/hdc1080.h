#ifndef HDC1080_H_
#define HDC1080_H_

#include <stdint.h>

#define HDC1080_ADDR 0x40

int hdc1080_probe(void);
int hdc1080_init(void);
int hdc1080_read_x10(int16_t *temp_x10, uint16_t *hum_x10);

#endif /* HDC1080_H_ */
