#ifndef SI7021_H_
#define SI7021_H_

#include <stdint.h>

#define SI7021_ADDR 0x40

int si7021_probe(void);
int si7021_init(void);
int si7021_read_x10(int16_t *temp_x10, uint16_t *hum_x10);

#endif /* SI7021_H_ */
