#ifndef ENV_PACKET_H_
#define ENV_PACKET_H_

#include <stdint.h>

/* Sentinel values used when a sensor is not mounted or cannot be read.
 * Packed application payload size: 18 bytes.
 */
#define ENV_INVALID_TEMP_X10      ((int16_t)-32768)
#define ENV_INVALID_U16           ((uint16_t)0xffff)
#define ENV_INVALID_PRESSURE_PA   ((int32_t)(-2147483647L - 1L))

typedef struct __attribute__((packed)) {
  uint16_t node_id;        /* 2 bytes */
  uint32_t seq;            /* 4 bytes */
  int16_t hdc_temp_x10;    /* 2 bytes: HDC1080/SI7021 temperature x10 */
  uint16_t hdc_hum_x10;    /* 2 bytes: HDC1080/SI7021 humidity x10 */
  uint16_t light_raw;      /* 2 bytes: TSL2561 channel 0 raw value */
  int16_t bmp_temp_x10;    /* 2 bytes: BMP180 temperature x10 */
  int32_t pressure_pa;     /* 4 bytes: BMP180 pressure in Pa */
} env_packet_t;             /* total: 18 bytes */

#endif /* ENV_PACKET_H_ */
