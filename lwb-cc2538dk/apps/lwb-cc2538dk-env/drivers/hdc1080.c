#include "contiki.h"
#include "hdc1080.h"
#include "i2c_sw.h"
#include "clock.h"

#include <stddef.h>

#define HDC1080_REG_TEMP             0x00
#define HDC1080_REG_CONFIG           0x02
#define HDC1080_REG_MANUFACTURER_ID  0xFE
#define HDC1080_REG_DEVICE_ID        0xFF

#define HDC1080_MANUFACTURER_ID      0x5449
#define HDC1080_DEVICE_ID            0x1050

/* MODE=1: temperature followed by humidity.
 * Temperature resolution = 14 bit, humidity resolution = 14 bit.
 */
#define HDC1080_CONFIG_VALUE         0x1000

#define HDC1080_STARTUP_US           20000
#define HDC1080_CONVERSION_US        20000
#define HDC1080_RETRY_DELAY_US       3000
#define HDC1080_MAX_RETRIES          3

static int
write_pointer(uint8_t reg)
{
  i2c_sw_start();

  if(!i2c_sw_write(HDC1080_ADDR << 1)) {
    i2c_sw_stop();
    return -1;
  }

  if(!i2c_sw_write(reg)) {
    i2c_sw_stop();
    return -1;
  }

  i2c_sw_stop();
  return 0;
}

static int
write16(uint8_t reg, uint16_t value)
{
  i2c_sw_start();

  if(!i2c_sw_write(HDC1080_ADDR << 1) ||
     !i2c_sw_write(reg) ||
     !i2c_sw_write((uint8_t)(value >> 8)) ||
     !i2c_sw_write((uint8_t)(value & 0xff))) {
    i2c_sw_stop();
    return -1;
  }

  i2c_sw_stop();
  return 0;
}

static int
read_bytes(uint8_t *buffer, uint8_t len)
{
  uint8_t i;

  if(buffer == NULL || len == 0) {
    return -1;
  }

  i2c_sw_start();

  if(!i2c_sw_write((HDC1080_ADDR << 1) | 1)) {
    i2c_sw_stop();
    return -1;
  }

  for(i = 0; i < len; i++) {
    buffer[i] = i2c_sw_read(i + 1 < len);
  }

  i2c_sw_stop();
  return 0;
}

static int
read16_register(uint8_t reg, uint16_t *value)
{
  uint8_t buffer[2];

  if(value == NULL) {
    return -1;
  }

  if(write_pointer(reg) != 0) {
    return -1;
  }

  clock_delay_usec(1000);

  if(read_bytes(buffer, sizeof(buffer)) != 0) {
    return -1;
  }

  *value = ((uint16_t)buffer[0] << 8) | buffer[1];
  return 0;
}

int
hdc1080_probe(void)
{
  uint8_t retry;
  uint16_t manufacturer_id;
  uint16_t device_id;

  for(retry = 0; retry < HDC1080_MAX_RETRIES; retry++) {
    if(read16_register(HDC1080_REG_MANUFACTURER_ID,
                       &manufacturer_id) == 0 &&
       read16_register(HDC1080_REG_DEVICE_ID,
                       &device_id) == 0 &&
       manufacturer_id == HDC1080_MANUFACTURER_ID &&
       device_id == HDC1080_DEVICE_ID) {
      return 0;
    }

    i2c_sw_recover();
    clock_delay_usec(HDC1080_RETRY_DELAY_US);
  }

  return -1;
}

int
hdc1080_init(void)
{
  uint8_t retry;

  clock_delay_usec(HDC1080_STARTUP_US);

  if(hdc1080_probe() != 0) {
    return -1;
  }

  for(retry = 0; retry < HDC1080_MAX_RETRIES; retry++) {
    if(write16(HDC1080_REG_CONFIG, HDC1080_CONFIG_VALUE) == 0) {
      clock_delay_usec(HDC1080_RETRY_DELAY_US);
      return 0;
    }

    i2c_sw_recover();
    clock_delay_usec(HDC1080_RETRY_DELAY_US);
  }

  return -1;
}

int
hdc1080_read_x10(int16_t *temp_x10, uint16_t *hum_x10)
{
  uint8_t buffer[4];
  uint8_t retry;
  uint16_t raw_temp;
  uint16_t raw_hum;
  int32_t temperature;
  int32_t humidity;

  if(temp_x10 == NULL || hum_x10 == NULL) {
    return -1;
  }

  for(retry = 0; retry < HDC1080_MAX_RETRIES; retry++) {
    if(write_pointer(HDC1080_REG_TEMP) == 0) {
      clock_delay_usec(HDC1080_CONVERSION_US);

      if(read_bytes(buffer, sizeof(buffer)) == 0) {
        raw_temp = ((uint16_t)buffer[0] << 8) | buffer[1];
        raw_hum = ((uint16_t)buffer[2] << 8) | buffer[3];

        temperature = ((int32_t)raw_temp * 1650L) / 65536L - 400L;
        humidity = ((int32_t)raw_hum * 1000L) / 65536L;

        if(humidity < 0) {
          humidity = 0;
        } else if(humidity > 1000) {
          humidity = 1000;
        }

        *temp_x10 = (int16_t)temperature;
        *hum_x10 = (uint16_t)humidity;
        return 0;
      }
    }

    i2c_sw_recover();
    clock_delay_usec(HDC1080_RETRY_DELAY_US);
  }

  return -1;
}
