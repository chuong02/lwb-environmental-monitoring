#include "contiki.h"
#include "bmp180.h"
#include "i2c_sw.h"
#include "clock.h"

#define BMP_REG_CALIB   0xaa
#define BMP_REG_CTRL    0xf4
#define BMP_REG_OUT     0xf6
#define BMP_CMD_TEMP    0x2e
#define BMP_CMD_PRESS   0x34

static int16_t AC1, AC2, AC3, B1, B2, MB, MC, MD;
static uint16_t AC4, AC5, AC6;
static uint8_t calib_ok;

static int
write8(uint8_t reg, uint8_t val)
{
  i2c_sw_start();
  if(!i2c_sw_write(BMP180_ADDR << 1)) {
    i2c_sw_stop();
    return -1;
  }
  if(!i2c_sw_write(reg)) {
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
read_bytes(uint8_t reg, uint8_t *buf, uint8_t n)
{
  uint8_t i;

  i2c_sw_start();
  if(!i2c_sw_write(BMP180_ADDR << 1)) {
    i2c_sw_stop();
    return -1;
  }
  if(!i2c_sw_write(reg)) {
    i2c_sw_stop();
    return -1;
  }
  i2c_sw_stop();

  i2c_sw_start();
  if(!i2c_sw_write((BMP180_ADDR << 1) | 1)) {
    i2c_sw_stop();
    return -1;
  }
  for(i = 0; i < n; i++) {
    buf[i] = i2c_sw_read(i < (n - 1));
  }
  i2c_sw_stop();
  return 0;
}

int
bmp180_init(void)
{
  uint8_t raw[22];
  uint8_t id;

  if(read_bytes(0xd0, &id, 1) != 0 || id != 0x55) {
    return -1;
  }

  if(read_bytes(BMP_REG_CALIB, raw, 22) != 0) {
    return -1;
  }

  AC1 = (int16_t)((raw[0] << 8) | raw[1]);
  AC2 = (int16_t)((raw[2] << 8) | raw[3]);
  AC3 = (int16_t)((raw[4] << 8) | raw[5]);
  AC4 = (uint16_t)((raw[6] << 8) | raw[7]);
  AC5 = (uint16_t)((raw[8] << 8) | raw[9]);
  AC6 = (uint16_t)((raw[10] << 8) | raw[11]);
  B1  = (int16_t)((raw[12] << 8) | raw[13]);
  B2  = (int16_t)((raw[14] << 8) | raw[15]);
  MB  = (int16_t)((raw[16] << 8) | raw[17]);
  MC  = (int16_t)((raw[18] << 8) | raw[19]);
  MD  = (int16_t)((raw[20] << 8) | raw[21]);

  calib_ok = 1;
  return 0;
}

int
bmp180_read_x10_pa(int16_t *temp_x10, int32_t *pressure_pa)
{
  const uint8_t OSS = 0;
  uint8_t buf[3];
  int32_t UT, UP;
  int32_t X1, X2, X3, B3, B5, B6, p;
  uint32_t B4, B7;

  if(!calib_ok && bmp180_init() != 0) {
    return -1;
  }

  if(write8(BMP_REG_CTRL, BMP_CMD_TEMP) != 0) {
    return -1;
  }
  clock_delay_usec(5000);
  if(read_bytes(BMP_REG_OUT, buf, 2) != 0) {
    return -1;
  }
  UT = ((int32_t)buf[0] << 8) | buf[1];

  X1 = ((UT - (int32_t)AC6) * (int32_t)AC5) >> 15;
  X2 = ((int32_t)MC << 11) / (X1 + MD);
  B5 = X1 + X2;
  *temp_x10 = (int16_t)((B5 + 8) >> 4);

  if(write8(BMP_REG_CTRL, (uint8_t)(BMP_CMD_PRESS + (OSS << 6))) != 0) {
    return -1;
  }
  clock_delay_usec(8000);
  if(read_bytes(BMP_REG_OUT, buf, 3) != 0) {
    return -1;
  }
  UP = (((int32_t)buf[0] << 16) | ((int32_t)buf[1] << 8) | buf[2]) >> (8 - OSS);

  B6 = B5 - 4000;
  X1 = (B2 * ((B6 * B6) >> 12)) >> 11;
  X2 = (AC2 * B6) >> 11;
  X3 = X1 + X2;
  B3 = ((((int32_t)AC1 * 4 + X3) << OSS) + 2) >> 2;
  X1 = (AC3 * B6) >> 13;
  X2 = (B1 * ((B6 * B6) >> 12)) >> 16;
  X3 = ((X1 + X2) + 2) >> 2;
  B4 = ((uint32_t)AC4 * (uint32_t)(X3 + 32768)) >> 15;
  B7 = ((uint32_t)UP - (uint32_t)B3) * (uint32_t)(50000 >> OSS);

  if(B7 < 0x80000000UL) {
    p = (int32_t)((B7 << 1) / B4);
  } else {
    p = (int32_t)((B7 / B4) << 1);
  }

  X1 = (p >> 8) * (p >> 8);
  X1 = (X1 * 3038) >> 16;
  X2 = (-7357 * p) >> 16;
  p = p + ((X1 + X2 + 3791) >> 4);

  *pressure_pa = p;
  return 0;
}
