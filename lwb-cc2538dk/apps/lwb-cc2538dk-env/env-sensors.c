#include "contiki.h"
#include "project-conf.h"
#include "env-sensors.h"
#include "i2c_sw.h"
#include "si7021.h"
#include "hdc1080.h"
#include "tsl2561.h"
#include "bmp180.h"

#include <stdint.h>
#include <stdio.h>

#ifndef ENV_TEMP_RH_SENSOR_CONF
#define ENV_TEMP_RH_SENSOR_CONF ENV_TEMP_RH_SENSOR_AUTO
#endif

#ifndef ENV_USE_TEMP_RH_CONF
#define ENV_USE_TEMP_RH_CONF 1
#endif

#ifndef ENV_USE_LIGHT_CONF
#define ENV_USE_LIGHT_CONF 1
#endif

#ifndef ENV_USE_BMP180_CONF
#define ENV_USE_BMP180_CONF 1
#endif

static uint8_t active_temp_rh_sensor;
static uint8_t temp_rh_init_ok;
static uint8_t light_init_ok;
static uint8_t bmp_init_ok;

static uint8_t
init_temp_rh_sensor(void)
{
#if !ENV_USE_TEMP_RH_CONF
  active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_AUTO;
  return 0;
#else

#if ENV_TEMP_RH_SENSOR_CONF == ENV_TEMP_RH_SENSOR_HDC1080
  active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_HDC1080;
  return hdc1080_init() == 0;
#elif ENV_TEMP_RH_SENSOR_CONF == ENV_TEMP_RH_SENSOR_SI7021
  active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_SI7021;
  return si7021_init() == 0;
#else
  /* Both devices use address 0x40. Detect HDC1080 first by its
   * manufacturer/device ID, then fall back to SI7021 electronic ID.
   */
  if(hdc1080_init() == 0) {
    active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_HDC1080;
    return 1;
  }

  i2c_sw_recover();

  if(si7021_init() == 0) {
    active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_SI7021;
    return 1;
  }

  active_temp_rh_sensor = ENV_TEMP_RH_SENSOR_AUTO;
  return 0;
#endif

#endif
}

void
env_sensors_init(void)
{
  i2c_sw_init();

  temp_rh_init_ok = init_temp_rh_sensor();

#if ENV_USE_LIGHT_CONF
  light_init_ok = (tsl2561_init() == 0);
#else
  light_init_ok = 0;
#endif

#if ENV_USE_BMP180_CONF
  bmp_init_ok = (bmp180_init() == 0);
#else
  bmp_init_ok = 0;
#endif

  printf("ENV I2C: SW-I2C SCL=PB%d SDA=PB%d\r\n",
         I2C_SW_SCL_PIN_CONF,
         I2C_SW_SDA_PIN_CONF);

  printf("ENV Temp/RH: %s addr=0x40 init=%u\r\n",
         env_temp_rh_sensor_name(),
         temp_rh_init_ok);

  printf("ENV init: temp_rh,%u,tsl,%u,bmp,%u\r\n",
         temp_rh_init_ok,
         light_init_ok,
         bmp_init_ok);
}

uint8_t
env_temp_rh_sensor_type(void)
{
  return active_temp_rh_sensor;
}

const char *
env_temp_rh_sensor_name(void)
{
  if(active_temp_rh_sensor == ENV_TEMP_RH_SENSOR_HDC1080) {
    return "HDC1080";
  }

  if(active_temp_rh_sensor == ENV_TEMP_RH_SENSOR_SI7021) {
    return "SI7021";
  }

#if ENV_USE_TEMP_RH_CONF
  return "TEMP/RH";
#else
  return "TEMP/RH";
#endif
}

uint8_t
env_read_temp_rh(int16_t *t_x10, uint16_t *rh_x10)
{
#if !ENV_USE_TEMP_RH_CONF
  (void)t_x10;
  (void)rh_x10;
  return 1;
#else
  if(!temp_rh_init_ok) {
    temp_rh_init_ok = init_temp_rh_sensor();

    if(!temp_rh_init_ok) {
      return 1;
    }

    printf("ENV recover: temp_rh,%s\r\n",
           env_temp_rh_sensor_name());
  }

  if(active_temp_rh_sensor == ENV_TEMP_RH_SENSOR_HDC1080) {
    if(hdc1080_read_x10(t_x10, rh_x10) == 0) {
      return 0;
    }
  } else if(active_temp_rh_sensor == ENV_TEMP_RH_SENSOR_SI7021) {
    if(si7021_read_x10(t_x10, rh_x10) == 0) {
      return 0;
    }
  }

  temp_rh_init_ok = 0;
  i2c_sw_recover();
  return 1;
#endif
}

uint8_t
env_read_hdc1080(int16_t *t_x10, uint16_t *rh_x10)
{
  return env_read_temp_rh(t_x10, rh_x10);
}

uint16_t
env_read_light_raw(void)
{
#if !ENV_USE_LIGHT_CONF
  return 0xffff;
#else
  uint16_t value;

  if(!light_init_ok) {
    light_init_ok = (tsl2561_init() == 0);

    if(!light_init_ok) {
      return 0xffff;
    }

    printf("ENV recover: tsl,1\r\n");
  }

  value = tsl2561_read_ch0_raw();
  if(value == 0xffff) {
    light_init_ok = 0;
    i2c_sw_recover();
  }

  return value;
#endif
}

uint8_t
env_read_bmp180(int16_t *t_x10, int32_t *p_pa)
{
#if !ENV_USE_BMP180_CONF
  (void)t_x10;
  (void)p_pa;
  return 1;
#else
  if(!bmp_init_ok) {
    bmp_init_ok = (bmp180_init() == 0);

    if(!bmp_init_ok) {
      return 1;
    }

    printf("ENV recover: bmp,1\r\n");
  }

  if(bmp180_read_x10_pa(t_x10, p_pa) == 0) {
    return 0;
  }

  bmp_init_ok = 0;
  i2c_sw_recover();
  return 1;
#endif
}

