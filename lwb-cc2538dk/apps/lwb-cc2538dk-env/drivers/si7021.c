#include "contiki.h"
#include "si7021.h"
#include "i2c_sw.h"
#include "clock.h"

#include <stddef.h>

#define CMD_MEAS_RH_HOLD       0xE5
#define CMD_READ_PREV_TEMP     0xE0
#define CMD_RESET              0xFE
#define CMD_ID2_MSB            0xFC
#define CMD_ID2_LSB            0xC9

#define SI7021_DEVICE_ID       0x15
#define SI7021_STARTUP_US      20000
#define SI7021_MEASURE_US      60000
#define SI7021_RETRY_US        3000
#define SI7021_MAX_RETRIES     3

static int
send_command1(uint8_t command)
{
  i2c_sw_start();

  if(!i2c_sw_write(SI7021_ADDR << 1) ||
     !i2c_sw_write(command)) {
    i2c_sw_stop();
    return -1;
  }

  i2c_sw_stop();
  return 0;
}

static int
send_command2(uint8_t command_msb, uint8_t command_lsb)
{
  i2c_sw_start();

  if(!i2c_sw_write(SI7021_ADDR << 1) ||
     !i2c_sw_write(command_msb) ||
     !i2c_sw_write(command_lsb)) {
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

  if(!i2c_sw_write((SI7021_ADDR << 1) | 1)) {
    i2c_sw_stop();
    return -1;
  }

  for(i = 0; i < len; i++) {
    buffer[i] = i2c_sw_read(i + 1 < len);
  }

  i2c_sw_stop();
  return 0;
}

int
si7021_probe(void)
{
  uint8_t retry;
  uint8_t id_buffer[8];

  for(retry = 0; retry < SI7021_MAX_RETRIES; retry++) {
    if(send_command2(CMD_ID2_MSB, CMD_ID2_LSB) == 0) {
      clock_delay_usec(1000);

      if(read_bytes(id_buffer, sizeof(id_buffer)) == 0 &&
         id_buffer[0] == SI7021_DEVICE_ID) {
        return 0;
      }
    }

    i2c_sw_stop();
    i2c_sw_recover();
    clock_delay_usec(SI7021_RETRY_US);
  }

  return -1;
}

int
si7021_init(void)
{
  /* Keep the reset-based initialization used by the known-good demo.
   * AUTO mode already excludes HDC1080 first using its TI/device IDs.
   */
  if(send_command1(CMD_RESET) != 0) {
    return -1;
  }

  clock_delay_usec(SI7021_STARTUP_US);
  return 0;
}

int
si7021_read_x10(int16_t *temp_x10, uint16_t *hum_x10)
{
  uint8_t retry;
  uint8_t buffer[3];
  uint16_t raw;
  int32_t value;

  if(temp_x10 == NULL || hum_x10 == NULL) {
    return -1;
  }

  for(retry = 0; retry < SI7021_MAX_RETRIES; retry++) {
    /* Preserve the transaction sequence used by the known-good demo:
     * issue the hold-master RH command, wait, then use a repeated START.
     */
    i2c_sw_start();
    if(i2c_sw_write(SI7021_ADDR << 1) &&
       i2c_sw_write(CMD_MEAS_RH_HOLD)) {
      clock_delay_usec(SI7021_MEASURE_US);

      if(read_bytes(buffer, sizeof(buffer)) == 0) {
        raw = ((uint16_t)buffer[0] << 8) | buffer[1];
        raw &= 0xfffc;

        value = ((int32_t)1250L * raw) / 65536L - 60L;
        if(value < 0) {
          value = 0;
        } else if(value > 1000) {
          value = 1000;
        }
        *hum_x10 = (uint16_t)value;

        if(send_command1(CMD_READ_PREV_TEMP) == 0) {
          clock_delay_usec(1000);

          if(read_bytes(buffer, 2) == 0) {
            raw = ((uint16_t)buffer[0] << 8) | buffer[1];
            raw &= 0xfffc;
            value = ((int32_t)17572L * raw) / 655360L - 469L;
            *temp_x10 = (int16_t)value;
            return 0;
          }
        }
      }
    }

    i2c_sw_recover();
    clock_delay_usec(SI7021_RETRY_US);
  }

  return -1;
}
