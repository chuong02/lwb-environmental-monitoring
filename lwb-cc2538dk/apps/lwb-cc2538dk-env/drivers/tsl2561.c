#include "contiki.h"
#include "tsl2561.h"
#include "i2c_sw.h"
#include "clock.h"

#define TSL_CMD        0x80
#define TSL_REG_CTRL   0x00
#define TSL_REG_TIMING 0x01
#define TSL_REG_CH0_L  0x0c
#define TSL_POWER_ON   0x03
#define TSL_INTEG_402  0x02

static int
write8(uint8_t reg, uint8_t val)
{
  i2c_sw_start();
  if(!i2c_sw_write(TSL2561_ADDR << 1)) {
    i2c_sw_stop();
    return -1;
  }
  if(!i2c_sw_write(TSL_CMD | reg)) {
    i2c_sw_stop();
    return -1;
  }
  if(!i2c_sw_write(val)) {
    i2c_sw_stop();
    return -1;
  }
  i2c_sw_stop();
  return 0;
}

static int
read8(uint8_t reg, uint8_t *val)
{
  i2c_sw_start();
  if(!i2c_sw_write(TSL2561_ADDR << 1)) {
    i2c_sw_stop();
    return -1;
  }
  if(!i2c_sw_write(TSL_CMD | reg)) {
    i2c_sw_stop();
    return -1;
  }
  i2c_sw_stop();

  i2c_sw_start();
  if(!i2c_sw_write((TSL2561_ADDR << 1) | 1)) {
    i2c_sw_stop();
    return -1;
  }
  *val = i2c_sw_read(0);
  i2c_sw_stop();
  return 0;
}

int
tsl2561_init(void)
{
  if(write8(TSL_REG_CTRL, TSL_POWER_ON) != 0) {
    return -1;
  }
  if(write8(TSL_REG_TIMING, TSL_INTEG_402) != 0) {
    return -1;
  }
  clock_wait(CLOCK_SECOND / 2);
  return 0;
}

uint16_t
tsl2561_read_ch0_raw(void)
{
  uint8_t lo, hi;
  if(read8(TSL_REG_CH0_L, &lo) != 0) {
    return 0xffff;
  }
  if(read8(TSL_REG_CH0_L + 1, &hi) != 0) {
    return 0xffff;
  }
  return ((uint16_t)hi << 8) | lo;
}
