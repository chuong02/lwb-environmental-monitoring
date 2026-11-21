#ifndef TSL2561_H_
#define TSL2561_H_

#include <stdint.h>

#define TSL2561_ADDR 0x39

int tsl2561_init(void);
uint16_t tsl2561_read_ch0_raw(void);

#endif /* TSL2561_H_ */
