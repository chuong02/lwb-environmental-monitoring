#ifndef BMP180_H_
#define BMP180_H_

#include <stdint.h>

#define BMP180_ADDR 0x77

int bmp180_init(void);
int bmp180_read_x10_pa(int16_t *temp_x10, int32_t *pressure_pa);

#endif /* BMP180_H_ */
