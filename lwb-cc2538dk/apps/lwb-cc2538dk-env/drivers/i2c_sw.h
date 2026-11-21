#ifndef I2C_SW_H_
#define I2C_SW_H_

#include <stdint.h>

/* Software I2C shared by sensors and OLED.
 * Default wiring is configured by project-conf.h / Makefile.
 */
void i2c_sw_init(void);
void i2c_sw_recover(void);
void i2c_sw_start(void);
void i2c_sw_stop(void);
int i2c_sw_write(uint8_t data);
uint8_t i2c_sw_read(int ack);

#endif /* I2C_SW_H_ */
